import ctypes
from types import SimpleNamespace
import threading
import time
import unittest

from fms_can import CAN_OBJ, INIT_CONFIG, EngineTransmitter, GcanInterface, engine_frames

VALUES = {'RPM': 1250, 'Oil temp': 88, 'Oil pressure': 4.2,
          'Coolant temp': 85, 'Coolant pressure': 1.5}


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError('Timed out waiting for worker')


class EncodingTests(unittest.TestCase):
    def test_reference_payloads(self):
        frames = engine_frames(VALUES)
        self.assertEqual(frames[61444], bytes.fromhex('FF FF FF 10 27 FF FF FF'))
        self.assertEqual(frames[65262], bytes.fromhex('7D FF 20 2D FF FF FF FF'))
        self.assertEqual(frames[65263], bytes.fromhex('FF FF FF 69 FF FF 4B FF'))

    def test_slider_limits(self):
        low = engine_frames(dict.fromkeys(VALUES, 0))
        self.assertEqual(low[61444][3:5], b'\x00\x00')
        self.assertEqual(low[65262][0], 40)
        self.assertEqual(int.from_bytes(low[65262][2:4], 'little'), 8736)
        high = engine_frames({'RPM': 4000, 'Oil temp': 160, 'Oil pressure': 10,
                              'Coolant temp': 130, 'Coolant pressure': 4})
        self.assertEqual(int.from_bytes(high[61444][3:5], 'little'), 32000)
        self.assertEqual(high[65263][3], 250)
        self.assertEqual(high[65263][6], 200)

    def test_windows_abi(self):
        self.assertEqual(ctypes.sizeof(CAN_OBJ), 24)
        self.assertEqual(ctypes.sizeof(INIT_CONFIG), 16)
        self.assertEqual(CAN_OBJ.Data.offset, 13)


class DriverTests(unittest.TestCase):
    def interface(self, init_result=1, start_result=1):
        calls = []
        def init(dev, index, channel, ptr):
            config = ctypes.cast(ptr, ctypes.POINTER(INIT_CONFIG)).contents
            calls.append(('init', dev, index, channel, config.Timing0, config.Timing1, config.Mode))
            return init_result
        def send(dev, index, channel, ptr, length):
            frame = ctypes.cast(ptr, ctypes.POINTER(CAN_OBJ)).contents
            calls.append(('send', dev, index, channel, length, frame.ID,
                          frame.ExternFlag, frame.RemoteFlag, frame.SendType, bytes(frame.Data)))
            return 1
        interface = GcanInterface.__new__(GcanInterface)
        interface.opened = False
        interface.dll = SimpleNamespace(
            OpenDevice=lambda *args: 1, InitCAN=init,
            StartCAN=lambda *args: start_result, Transmit=send,
            CloseDevice=lambda *args: calls.append(('close',)),
            ResetCAN=lambda *args: calls.append(('reset',)))
        return interface, calls

    def test_channel_configuration_and_frame_flags(self):
        interface, calls = self.interface()
        interface.connect()
        payload = engine_frames(VALUES)[61444]
        self.assertTrue(interface.send(0x0CF00400, payload))
        self.assertEqual(calls[0], ('init', 4, 0, 0, 1, 0x1C, 0))
        self.assertEqual(calls[1], ('send', 4, 0, 0, 1, 0x0CF00400, 1, 0, 1, payload))
        interface.close()
        interface.close()
        self.assertEqual(calls.count(('close',)), 1)

    def test_failed_initialization_closes_device(self):
        for init, start in ((0, 1), (1, 0)):
            interface, calls = self.interface(init, start)
            with self.assertRaises(RuntimeError):
                interface.connect()
            self.assertFalse(interface.opened)
            self.assertIn(('close',), calls)


class FakeInterface:
    def __init__(self):
        self.fail = threading.Event()
        self.fail.set()
        self.closed = False
        self.recovered = False
        self.sent = []
        self.attempts = 0

    def connect(self):
        pass

    def send(self, identifier, payload):
        self.attempts += 1
        if self.fail.is_set():
            if self.attempts % 2:
                raise OSError('simulated bus failure')
            return False
        self.sent.append((identifier, payload, time.monotonic()))
        return True

    def recover(self):
        self.recovered = True
        raise OSError('simulated recovery failure')

    def close(self):
        self.closed = True


class WorkerTests(unittest.TestCase):
    def test_continuous_retry_recovery_live_values_and_stop(self):
        interface = FakeInterface()
        worker = EngineTransmitter(VALUES, lambda: interface)
        worker.start()
        try:
            wait_until(lambda: worker.status()[0] == 'retrying')
            wait_until(lambda: interface.recovered)
            self.assertTrue(worker.thread.is_alive())
            self.assertGreater(interface.attempts, 10)
            updated = dict(VALUES, RPM=2000)
            worker.update(updated)
            interface.fail.clear()
            wait_until(lambda: {frame[0] for frame in interface.sent} ==
                       {0x0CF00400, 0x18FEEE00, 0x18FEEF00})
            wait_until(lambda: worker.status()[0] == 'connected')
            rpm_frames = [payload for identifier, payload, _ in interface.sent
                          if identifier == 0x0CF00400]
            self.assertEqual(rpm_frames[-1][3:5], (16000).to_bytes(2, 'little'))
            count = len(rpm_frames)
            wait_until(lambda: sum(frame[0] == 0x0CF00400 for frame in interface.sent) >= count + 3)
        finally:
            worker.stop()
            worker.thread.join(2)
        self.assertFalse(worker.thread.is_alive())
        self.assertTrue(interface.closed)
        self.assertEqual(worker.status()[0], 'disconnected')

    def test_connect_failure_is_reported_and_cleaned_up(self):
        interface = FakeInterface()
        def fail_connect():
            raise RuntimeError('no USB device')
        interface.connect = fail_connect
        worker = EngineTransmitter(VALUES, lambda: interface)
        worker.start()
        worker.thread.join(2)
        self.assertEqual(worker.status(), ('error', 'no USB device'))
        self.assertTrue(interface.closed)


if __name__ == '__main__':
    unittest.main()
