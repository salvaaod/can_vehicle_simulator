"""Continuous illustrative telemetry motion (no hardware access)."""
import math


def organic_wave(seconds, period, phase=0):
    """Blend slow oscillations to avoid synchronized, repetitive motion."""
    return (0.65 * math.sin(seconds * 2 * math.pi / period + phase)
            + 0.25 * math.sin(seconds * 2 * math.pi / (period * 1.73) + phase * 1.4)
            + 0.10 * math.sin(seconds * 2 * math.pi / (period * 0.47) + phase * 0.7))


def simulation_values(seconds, initial_hours=300):
    """Vary all systems together smoothly, within the GUI's sensor ranges."""
    travel = organic_wave(seconds, 39, 0.4)
    lifting = organic_wave(seconds, 27, 1.2)
    rpm = 1600 + 500 * travel + 200 * lifting
    values = {
        'RPM': rpm,
        'Oil temp': 90 + 12 * organic_wave(seconds, 61, 0.8),
        'Oil pressure': 3.8 + (rpm - 1600) / 1000 + 0.3 * organic_wave(seconds, 17, 2),
        'Coolant temp': 86 + 9 * organic_wave(seconds, 73, 1.7),
        'Coolant pressure': 1.6 + 0.35 * organic_wave(seconds, 31, 0.6),
        'Wheel based speed': 45 + 30 * travel,
        'Engine running time': min(5000, initial_hours + seconds / 3600),
        'angle': 38 + 23 * organic_wave(seconds, 29, 0.3),
        'extension': 45 + 35 * organic_wave(seconds, 37, 2.1),
        'pressure': 160 + 65 * lifting + 20 * organic_wave(seconds, 13, 0.5),
        'slew': 180 + 150 * organic_wave(seconds, 53, 1.3),
        'load_kg': round((3500 + 2500 * organic_wave(seconds, 43, 2.8)) / 100) * 100,
    }
    wheels = {
        name: {'pressure': 8 + 0.45 * organic_wave(seconds, 19 + i * 3, i + 0.2),
               'temperature': 43 + 10 * organic_wave(seconds, 47 + i * 5, i * 0.8)
               + 2 * travel}
        for i, name in enumerate(('Rear 1', 'Rear 2', 'Front 1', 'Front 2'))
    }
    return values, wheels, 'Organic motion · vehicle + crane'
