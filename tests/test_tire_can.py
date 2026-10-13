import math
import time
import unittest

from crane_can import VehicleTransmitter
from fms_can import TIRE_LOCATIONS, TIRE_PGN, tire_frame, tire_interval
from test_fms_can import VALUES, FakeInterface, wait_until
from test_crane_can import CRANE


def readings(interval=10):
    return {**VALUES, **CRANE, 'tire_interval': interval,
            'wheels': {name: {'pressure': 8.0, 'temperature': 35}
                       for name, _ in TIRE_LOCATIONS}}


class TireTests(unittest.TestCase):
    def test_fms_payload_and_resolution(self):
        self.assertEqual(tire_frame(0x00, 8), bytes.fromhex('00 C8 FF FF FF FF FF FF'))
        self.assertEqual(tire_frame(0x23, 8.1), bytes.fromhex('23 CB FF FF FF FF FF FF'))
        self.assertEqual(tire_frame(0x30, 0)[1], 0)
        self.assertEqual(tire_frame(0x30, 10)[1], 250)
        for value in (-1, math.inf, math.nan):
            self.assertEqual(tire_frame(0, value)[1], 255)

    def test_interval_validation_and_default(self):
        worker = VehicleTransmitter(readings())
        self.assertEqual(worker.message_period(TIRE_PGN, 10, readings()), 10)
        self.assertEqual(tire_interval('2.5'), 2.5)
        for value in ('', 'abc', 0, -1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                tire_interval(value)

    def test_round_robin_live_interval_values_retries_and_channel(self):
        class Driver(FakeInterface):
            def send(self, identifier, payload, channel=0, extended=True):
                if identifier == 0x18FEF400:
                    if self.fail.is_set():
                        self.attempts += 1
                        return False
                    self.sent.append((identifier, payload, time.monotonic(), channel, extended))
                return True
        driver = Driver()
        worker = VehicleTransmitter(readings(), lambda: driver)
        worker.start()
        try:
            wait_until(lambda: driver.attempts >= 2)
            self.assertEqual(worker._tire_index, 0)
            driver.fail.clear()
            wait_until(lambda: len(driver.sent) == 1)
            self.assertEqual(driver.sent[0][1][0], 0)
            # Shortening the interval takes effect without waiting ten seconds.
            values = readings(0.06)
            values['wheels']['Front 1']['pressure'] = 1
            worker.update(values)
            wait_until(lambda: len(driver.sent) >= 5)
            frames = driver.sent[:5]
            self.assertEqual([f[1][0] for f in frames], [0, 0x10, 0x20, 0x30, 0])
            self.assertEqual(frames[1][1][1], 25)
            self.assertTrue(all(f[3:] == (0, True) for f in frames))
            self.assertTrue(all(b[2] - a[2] >= 0.055 for a, b in zip(frames, frames[1:])))
            # Increasing the interval postpones the next tire.
            worker.update(readings(10))
            count = len(driver.sent)
            time.sleep(0.1)
            self.assertEqual(len(driver.sent), count)
        finally:
            worker.stop()
            worker.thread.join(2)
        self.assertTrue(driver.closed)
        self.assertFalse(worker.thread.is_alive())


if __name__ == '__main__':
    unittest.main()
