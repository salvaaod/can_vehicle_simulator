import unittest
from operation_simulation import simulation_values


class OperationSimulationTests(unittest.TestCase):
    def test_continuous_motion_bounds(self):
        bounds = {'RPM': (0, 4000), 'Oil temp': (0, 160),
                  'Oil pressure': (0, 10), 'Coolant temp': (0, 130),
                  'Coolant pressure': (0, 4), 'Wheel based speed': (0, 120),
                  'Engine running time': (0, 5000), 'angle': (0, 70),
                  'extension': (0, 100), 'pressure': (0, 320),
                  'slew': (0, 360), 'load_kg': (0, 10000)}
        for tick in range(1801):
            values, wheels, phase = simulation_values(tick / 10)
            for key, (low, high) in bounds.items():
                self.assertTrue(low <= values[key] <= high, (tick, key))
            self.assertEqual(values['load_kg'] % 100, 0)
            self.assertEqual(len(wheels), 4)
            for wheel in wheels.values():
                self.assertTrue(6.5 < wheel['pressure'] < 10)
                self.assertTrue(0 < wheel['temperature'] < 70)

    def test_running_hours_accumulate_across_cycles(self):
        before = simulation_values(89, 123)[0]
        after = simulation_values(91, 123)[0]
        self.assertAlmostEqual(after['Engine running time'] - before['Engine running time'], 2 / 3600)
        self.assertEqual(simulation_values(3600, 5000)[0]['Engine running time'], 5000)

    def test_all_parameters_move_while_vehicle_has_speed(self):
        samples = [simulation_values(t / 10) for t in range(600)]
        for key in samples[0][0]:
            readings = [sample[0][key] for sample in samples]
            self.assertGreater(max(readings), min(readings), key)
        for name in samples[0][1]:
            for key in ('pressure', 'temperature'):
                readings = [sample[1][name][key] for sample in samples]
                self.assertGreater(max(readings), min(readings), (name, key))
        for values, _, _ in samples:
            self.assertGreater(values['RPM'], 0)
            self.assertGreater(values['Wheel based speed'], 0)
            self.assertGreater(values['load_kg'], 0)

    def test_motion_has_no_abrupt_jumps(self):
        previous, previous_wheels, _ = simulation_values(0)
        for tick in range(1, 1801):
            values, wheels, _ = simulation_values(tick / 10)
            for key in values:
                limit = 100 if key == 'load_kg' else 20 if key == 'RPM' else 3
                self.assertLessEqual(abs(values[key] - previous[key]), limit, key)
            for name in wheels:
                for key in wheels[name]:
                    self.assertLess(abs(wheels[name][key] - previous_wheels[name][key]), 0.3)
            previous, previous_wheels = values, wheels


if __name__ == '__main__':
    unittest.main()
