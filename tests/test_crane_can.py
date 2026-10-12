import math
import ctypes
import unittest

from crane_can import VehicleInterface, VehicleTransmitter, crane_frames
import test_fms_can as fms_tests
from fms_can import CAN_OBJ, ENGINE_MESSAGES

FakeInterface = fms_tests.FakeInterface
VALUES = fms_tests.VALUES
wait_until = fms_tests.wait_until

CRANE = dict(angle=35, extension=35, slew=0, pressure=160, load_kg=0)


class CraneTests(unittest.TestCase):
    def test_reference_and_limits(self):
        self.assertEqual(crane_frames(CRANE), {
            0x181: bytes.fromhex('AC 0D AC 0D 00 00 40 06'),
            0x281: b'\x00\x00', 0x701: b'\x05'})
        high = crane_frames(dict(angle=70, extension=100, slew=360,
                                 pressure=320, load_kg=10000))
        self.assertEqual(high[0x181], bytes.fromhex('58 1B 10 27 A0 8C 80 0C'))
        self.assertEqual(high[0x281], bytes.fromhex('10 27'))
        self.assertEqual(crane_frames(dict.fromkeys(CRANE, 0))[0x181], bytes(8))

    def test_invalid_and_rounding(self):
        for value in (-1, 71, math.nan, math.inf):
            frame = crane_frames(dict(CRANE, angle=value))[0x181]
            self.assertEqual(frame[:2], b'\xff\xff')
            self.assertEqual(frame[2:], crane_frames(CRANE)[0x181][2:])
        self.assertEqual(crane_frames(dict(CRANE, angle=1.125))[0x181][:2],
                         (113).to_bytes(2, 'little'))

    def test_dual_channel_and_dlc(self):
        driver, calls = fms_tests.DriverTests().interface()
        lengths = []
        transmit = driver.dll.Transmit
        def record_length(dev, index, channel, ptr, count):
            lengths.append(ctypes.cast(ptr, ctypes.POINTER(CAN_OBJ)).contents.DataLen)
            return transmit(dev, index, channel, ptr, count)
        driver.dll.Transmit = record_length
        driver.channels = VehicleInterface.channels
        driver.connect()
        self.assertEqual([c[3] for c in calls if c[0] == 'init'], [0, 1])
        worker = VehicleTransmitter({**VALUES, **CRANE})
        for identifier, payload in crane_frames(CRANE).items():
            self.assertTrue(worker.send_frame(driver, identifier, None, payload))
        sends = [c for c in calls if c[0] == 'send']
        self.assertEqual(lengths, [8, 2, 1])
        for call, (identifier, payload) in zip(sends, crane_frames(CRANE).items()):
            self.assertEqual(call[3:9], (1, 1, identifier, 0, 0, 1))
            self.assertEqual(call[9][:len(payload)], payload)
            self.assertEqual(call[9][len(payload):], bytes(8 - len(payload)))
        driver.close()
        driver.close()
        self.assertEqual(calls.count(('close',)), 1)

    def test_second_channel_failure_closes_shared_device(self):
        driver, calls = fms_tests.DriverTests().interface()
        driver.channels = VehicleInterface.channels
        initialize = driver.dll.InitCAN
        driver.dll.InitCAN = lambda dev, index, channel, ptr: (
            initialize(dev, index, channel, ptr) if channel == 0 else 0)
        with self.assertRaisesRegex(RuntimeError, 'CAN2'):
            driver.connect()
        self.assertFalse(driver.opened)
        self.assertEqual(calls.count(('close',)), 1)

    def test_every_message_selects_its_physical_channel(self):
        driver, calls = fms_tests.DriverTests().interface()
        # A CAN2 default must not redirect FMS traffic to that bus.
        driver.channel = 1
        worker = VehicleTransmitter({**VALUES, **CRANE})
        payloads = worker.frames({**VALUES, **CRANE})
        for key, priority, _period in worker.messages:
            worker.send_frame(driver, key, priority, payloads[key])
        sends = [call for call in calls if call[0] == 'send']
        self.assertEqual(len(sends), len(worker.messages))
        engine_ids = {(priority << 26) | (key << 8)
                      for key, priority, _ in ENGINE_MESSAGES}
        for call in sends:
            channel, identifier, extended = call[3], call[5], call[6]
            if identifier in engine_ids:
                self.assertEqual((channel, extended), (0, 1))
            else:
                self.assertIn(identifier, {0x181, 0x281, 0x701})
                self.assertEqual((channel, extended), (1, 0))

    def test_live_periodic_crane_transmission(self):
        class DualFake(FakeInterface):
            def send(self, identifier, payload, channel=0, extended=True):
                self.sent.append((identifier, payload, channel, extended))
                return True
        driver = DualFake()
        worker = VehicleTransmitter({**VALUES, **CRANE}, lambda: driver)
        worker.start()
        try:
            wait_until(lambda: len(driver.sent) >= 8)
            self.assertEqual({f[0] for f in driver.sent},
                             {0x0CF00400, 0x18FEEE00, 0x18FEEF00, 0x18FEF100,
                              0x18FEE500, 0x181, 0x281, 0x701})
            self.assertTrue(all(f[2:] == (1, False) for f in driver.sent if f[0] < 0x800))
            self.assertTrue(all(f[2:] == (0, True) for f in driver.sent if f[0] >= 0x800))
            worker.update({**VALUES, **CRANE, 'load_kg': 5000})
            wait_until(lambda: any(f[0] == 0x281 and f[1] == bytes.fromhex('88 13')
                                   for f in driver.sent))
            wait_until(lambda: sum(f[0] == 0x181 for f in driver.sent) >= 3)
        finally:
            worker.stop()
            worker.thread.join(2)
        self.assertFalse(worker.thread.is_alive())
        self.assertTrue(driver.closed)


if __name__ == '__main__':
    unittest.main()
