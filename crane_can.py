"""Simulator-defined crane CANopen TPDOs on GCAN-II CAN2."""
import math
import struct

from fms_can import (ENGINE_MESSAGES, EngineTransmitter, GcanInterface,
                     engine_frames, TIRE_PGN, TIRE_LOCATIONS, tire_frame,
                     tire_interval)

NODE_ID = 1
CRANE_MESSAGES = ((0x180 + NODE_ID, None, 0.100),
                  (0x280 + NODE_ID, None, 0.100),
                  (0x700 + NODE_ID, None, 1.000))


def crane_frames(values):
    """Unsigned 16-bit, little endian; invalid/nonfinite values use 0xffff."""
    def encode(key, maximum, scale):
        value = float(values[key])
        if not math.isfinite(value) or not 0 <= value <= maximum:
            return 0xFFFF
        return math.floor(value * scale + 0.5)

    return {
        0x180 + NODE_ID: struct.pack('<HHHH', encode('angle', 70, 100),
                                   encode('extension', 100, 100),
                                   encode('slew', 360, 100),
                                   encode('pressure', 320, 10)),
        0x280 + NODE_ID: struct.pack('<H', encode('load_kg', 10000, 1)),
        0x700 + NODE_ID: b'\x05',
    }


class VehicleInterface(GcanInterface):
    # One owner opens/closes the shared adapter; both channels start together.
    channels = (0, 1)


class VehicleTransmitter(EngineTransmitter):
    messages = ENGINE_MESSAGES + CRANE_MESSAGES
    connected_message = 'CAN1 engine/tires + CAN2 crane · 250 kbps · transmitting'

    def __init__(self, values, interface_factory=VehicleInterface):
        self._tire_index = 0
        if 'wheels' in values:
            tire_interval(values.get('tire_interval', 10))
            self.messages = self.messages + ((TIRE_PGN, 6, 10.0),)
        super().__init__(values, interface_factory)

    def frames(self, values):
        frames = {**engine_frames(values), **crane_frames(values)}
        if 'wheels' in values:
            name, location = TIRE_LOCATIONS[self._tire_index]
            frames[TIRE_PGN] = tire_frame(location, values['wheels'][name]['pressure'])
        return frames

    def message_period(self, key, default, values):
        if key == TIRE_PGN:
            return tire_interval(values.get('tire_interval', 10))
        return default

    def frame_sent(self, key):
        if key == TIRE_PGN:
            self._tire_index = (self._tire_index + 1) % len(TIRE_LOCATIONS)

    def send_frame(self, interface, key, priority, payload):
        if priority is None:
            return interface.send(key, payload, channel=1, extended=False)
        # Select CAN1 explicitly: never inherit an interface's default channel.
        return interface.send((priority << 26) | (key << 8), payload,
                              channel=0, extended=True)
