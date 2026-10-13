"""GCAN-II CAN1 transport and J1939/FMS engine signal encoding."""
import ctypes
import math
import os
from pathlib import Path
import threading
import time


class CAN_OBJ(ctypes.Structure):
    _fields_ = [('ID', ctypes.c_uint32), ('TimeStamp', ctypes.c_uint32),
                ('TimeFlag', ctypes.c_uint8), ('SendType', ctypes.c_uint8),
                ('RemoteFlag', ctypes.c_uint8), ('ExternFlag', ctypes.c_uint8),
                ('DataLen', ctypes.c_uint8), ('Data', ctypes.c_uint8 * 8),
                ('Reserved', ctypes.c_uint8 * 3)]


class INIT_CONFIG(ctypes.Structure):
    _fields_ = [('AccCode', ctypes.c_uint32), ('AccMask', ctypes.c_uint32),
                ('Reserved', ctypes.c_uint32), ('Filter', ctypes.c_uint8),
                ('Timing0', ctypes.c_uint8), ('Timing1', ctypes.c_uint8),
                ('Mode', ctypes.c_uint8)]


# PGN, priority, period (seconds). Source address 0 = engine #1.
ENGINE_MESSAGES = ((61444, 3, 0.020), (65262, 6, 1.000), (65263, 6, 0.500),
                   (65265, 6, 0.100), (65253, 6, 1.000))


def engine_frames(values):
    """Encode little-endian SPNs; unsupported signals remain not-available (FF)."""
    eec1 = bytearray(b'\xff' * 8)
    rpm = round(max(0, min(4000, values['RPM'])) / 0.125)
    eec1[3:5] = rpm.to_bytes(2, 'little')  # SPN 190, bytes 4-5
    et1 = bytearray(b'\xff' * 8)
    et1[0] = round(max(0, min(130, values['Coolant temp'])) + 40)  # SPN 110
    oil = round((max(0, min(160, values['Oil temp'])) + 273) / 0.03125)
    et1[2:4] = oil.to_bytes(2, 'little')  # SPN 175
    eflp1 = bytearray(b'\xff' * 8)
    eflp1[3] = round(max(0, min(10, values['Oil pressure'])) / 0.04)  # SPN 100
    eflp1[6] = round(max(0, min(4, values['Coolant pressure'])) / 0.02)  # SPN 109
    ccvs = bytearray(b'\xff' * 8)
    speed = round(max(0, min(120, values['Wheel based speed'])) * 256)
    ccvs[1:3] = speed.to_bytes(2, 'little')  # SPN 84, bytes 2-3, 1/256 km/h
    hours = bytearray(b'\xff' * 8)
    running_time = round(max(0, min(5000, values['Engine running time'])) / 0.05)
    hours[0:4] = running_time.to_bytes(4, 'little')  # SPN 247, bytes 1-4
    return {61444: bytes(eec1), 65262: bytes(et1), 65263: bytes(eflp1),
            65265: bytes(ccvs), 65253: bytes(hours)}


TIRE_PGN = 65268
# Side-view wheels represent the left tire on each axle, front to rear.
TIRE_LOCATIONS = (('Front 2', 0x00), ('Front 1', 0x10),
                  ('Rear 2', 0x20), ('Rear 1', 0x30))


def tire_frame(location, pressure_bar):
    """FMS TIRE1: SPN 929 location, SPN 241 pressure (4 kPa/bit)."""
    pressure = float(pressure_bar)
    raw = (min(250, math.floor(pressure * 25 + 0.5))
           if math.isfinite(pressure) and pressure >= 0 else 0xFF)
    return bytes((location, raw)) + b'\xff' * 6


def tire_interval(value):
    interval = float(value)
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError('Tire interval must be a positive number of seconds')
    return interval


class GcanInterface:
    device_type, device_index, channel = 4, 0, 0  # USBCAN-II, first device, CAN1
    channels = (0,)

    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('GCAN requires Windows, its USB driver, and matching Python/DLL architecture.')
        path = Path(__file__).resolve().with_name('ECanVci.dll')
        try:
            self.dll = ctypes.WinDLL(str(path))
        except OSError as exc:
            raise RuntimeError('Cannot load ECanVci.dll. Install the GCAN driver and use matching Python/DLL architecture (bundled DLL is 64-bit).') from exc
        uint = ctypes.c_uint32  # Windows DWORD/ULONG stay 32-bit
        for name, arguments in {
            'OpenDevice': [uint, uint, uint], 'CloseDevice': [uint, uint],
            'InitCAN': [uint, uint, uint, ctypes.POINTER(INIT_CONFIG)],
            'StartCAN': [uint, uint, uint], 'ResetCAN': [uint, uint, uint],
            'Transmit': [uint, uint, uint, ctypes.POINTER(CAN_OBJ), uint],
        }.items():
            function = getattr(self.dll, name)
            function.argtypes = arguments
            function.restype = uint
        self.opened = False

    def connect(self):
        if self.dll.OpenDevice(self.device_type, self.device_index, 0) != 1:
            raise RuntimeError('OpenDevice failed: check the GCAN USB connection and driver.')
        self.opened = True
        try:
            config = INIT_CONFIG(0, 0xFFFFFFFF, 0, 0, 0x01, 0x1C, 0)
            for channel in self.channels:
                if self.dll.InitCAN(self.device_type, self.device_index, channel, ctypes.byref(config)) != 1:
                    raise RuntimeError(f'InitCAN failed on CAN{channel + 1} at 250 kbps.')
                if self.dll.StartCAN(self.device_type, self.device_index, channel) != 1:
                    raise RuntimeError(f'StartCAN failed on CAN{channel + 1}.')
        except Exception:
            self.close()
            raise

    def send(self, identifier, payload, channel=None, extended=True):
        frame = CAN_OBJ()
        frame.ID = identifier
        frame.SendType = 1  # Single attempt; the worker schedules bounded retries.
        frame.ExternFlag = int(extended)
        frame.DataLen = len(payload)
        frame.Data[:len(payload)] = payload
        return self.dll.Transmit(self.device_type, self.device_index, self.channel if channel is None else channel,
                                 ctypes.byref(frame), 1) == 1

    def recover(self):
        for channel in self.channels:
            self.dll.ResetCAN(self.device_type, self.device_index, channel)
            self.dll.StartCAN(self.device_type, self.device_index, channel)

    def close(self):
        if self.opened:
            try:
                self.dll.CloseDevice(self.device_type, self.device_index)
            finally:
                self.opened = False


class EngineTransmitter:
    """All DLL calls run off the Tk thread; shared state is protected by a lock."""
    def __init__(self, values, interface_factory=GcanInterface):
        self._lock = threading.Lock()
        self._values = dict(values)
        self._status = ('connecting', 'Connecting to GCAN-II…')
        self._stop = threading.Event()
        self._factory = interface_factory
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def update(self, values):
        with self._lock:
            self._values = dict(values)

    def status(self):
        with self._lock:
            return self._status

    def _set_status(self, state, message):
        with self._lock:
            self._status = state, message

    def stop(self):
        self._stop.set()

    def _run(self):
        interface = None
        connected = False
        try:
            interface = self._factory()
            interface.connect()
            connected = True
            self._set_status('connected', self.connected_message)
            due = {pgn: 0.0 for pgn, _, _ in self.messages}
            last_sent = {}
            periods = {}
            pending_errors = set()
            last_recovery = time.monotonic()
            while not self._stop.is_set():
                with self._lock:
                    frames = self.frames(self._values)
                failed = False
                for pgn, priority, period in self.messages:
                    now = time.monotonic()
                    with self._lock:
                        period = self.message_period(pgn, period, self._values)
                    if periods.get(pgn) != period:
                        if pgn in last_sent and pgn not in pending_errors:
                            due[pgn] = last_sent[pgn] + period
                        periods[pgn] = period
                    if now < due[pgn]:
                        continue
                    try:
                        sent = self.send_frame(interface, pgn, priority, frames[pgn])
                        if not sent:
                            raise RuntimeError('Transmit returned no sent frame')
                    except Exception as exc:
                        failed = True
                        pending_errors.add(pgn)
                        self._set_status('retrying', f'CAN transmission error; retrying: {exc}')
                        due[pgn] = now + 0.020
                    else:
                        pending_errors.discard(pgn)
                        last_sent[pgn] = now
                        due[pgn] = now + period
                        self.frame_sent(pgn)
                if failed and time.monotonic() - last_recovery >= 1.0:
                    try:
                        interface.recover()
                    except Exception:
                        pass  # Keep attempting transmission even if recovery fails.
                    last_recovery = time.monotonic()
                elif not pending_errors and self.status()[0] == 'retrying':
                    self._set_status('connected', self.connected_message)
                self._stop.wait(0.005)
        except Exception as exc:
            self._set_status('error', str(exc))
        finally:
            if interface is not None:
                try:
                    interface.close()
                except Exception as exc:
                    self._set_status('error', f'CloseDevice failed: {exc}')
            if connected and self.status()[0] != 'error':
                self._set_status('disconnected', 'Disconnected')
    messages = ENGINE_MESSAGES
    connected_message = 'CAN1 · 250 kbps · transmitting engine data'

    def frames(self, values):
        return engine_frames(values)

    def send_frame(self, interface, key, priority, payload):
        return interface.send((priority << 26) | (key << 8), payload)

    def message_period(self, key, default, values):
        return default

    def frame_sent(self, key):
        pass
