# Engine transmission with GCAN-II

Run `python can_vehicle_simulator.py` on Windows with the GCAN/USBCAN-II
USB driver installed and the adapter connected. Keep `fms_can.py` and
`ECanVci.dll` beside the simulator. The bundled DLL is **64-bit**, so use
64-bit Python with Tkinter. Other DLL versions must match Python's architecture.

Click **Connect GCAN-II**. The first adapter (device index 0) opens and starts
**CAN1** (driver channel index 0) at **250 kbps**, then immediately transmits
engine data. Engine sliders update the transmitted values. The same button
becomes **Disconnect GCAN-II**; closing the window also stops transmission and
closes the device. CAN2, tires, and crane messages are reserved for later work.

All messages are eight-byte extended CAN data frames. Multi-byte signals are
little-endian; unused signals are marked unavailable (`FF`). Source address is
fixed to `00` (engine #1). This is a simulator for a test bus: it does not implement
J1939 address claiming or a complete FMS gateway. Avoid another sender using the
same source address on that bus.

| Message | PGN | CAN identifier | Interval | Signals |
| --- | --- | --- | --- | --- |
| EEC1 | 61444 (`F004`) | `0CF00400` | 20 ms | Engine speed, SPN 190, bytes 4–5, 0.125 rpm/bit |
| ET1 | 65262 (`FEEE`) | `18FEEE00` | 1000 ms | Coolant temperature, SPN 110, byte 1, 1 °C/bit, offset −40 °C; oil temperature, SPN 175, bytes 3–4, 0.03125 °C/bit, offset −273 °C |
| EFL/P1 | 65263 (`FEEF`) | `18FEEF00` | 500 ms | Oil pressure, SPN 100, byte 4, 4 kPa/bit; coolant pressure, SPN 109, byte 7, 2 kPa/bit |
| CCVS | 65265 (`FEF1`) | `18FEF100` | 100 ms | Wheel based speed, SPN 84, bytes 2–3, 1/256 km/h/bit |
| HOURS | 65253 (`FEE5`) | `18FEE500` | 1000 ms | Engine total hours of operation, SPN 247, bytes 1–4, 0.05 h/bit |

Engine speed, coolant temperature, wheel based speed, and engine running time
are FMS signals. Oil temperature and the
pressure signals use their standard J1939 definitions as supplementary engine
telemetry; an FMS-only receiver may ignore them. This does not emulate other
FMS signals that the UI does not supply.

For the default sliders, the payloads are:

- EEC1: `FF FF FF 10 27 FF FF FF`
- ET1: `7D FF 20 2D FF FF FF FF`
- EFL/P1: `FF FF FF 69 FF FF 4B FF`
- CCVS: `FF 00 3C FF FF FF FF FF`
- HOURS: `70 17 00 00 FF FF FF FF`

Wheel based speed ranges from 0–120 km/h (default 60 km/h). Engine running time
ranges from 0–5000 h (default 300 h); it is a manually simulated accumulated
running time, not an automatically advancing timer. Both use the existing compact
engine slider style and update the engine's live parameter gauges.

Transmission runs in a worker thread. Failed sends (including exceptions) are
retried every 20 ms using current slider values. If failures persist, CAN1 is
reset/restarted at most once per second to attempt recovery from bus-off. Failed
recovery attempts do not stop the send loop. The UI shows retry status and returns
to transmitting status after failed messages succeed. Successful DLL sends do
not independently prove a receiver decoded the data. Connection failures require
clicking Connect again after correcting the driver, adapter, or DLL problem.

Connect CAN-H, CAN-L and the appropriate common ground, with correct termination
and a second active CAN node at 250 kbps to acknowledge frames. A disconnected or
unacknowledged bus can produce transmission errors even when USB connection works.
Unplug/replug recovery may require Disconnect and Connect if the driver invalidates
the open device handle.

## Validation

Run `python -m unittest discover -s tests -v` from the repository directory.
Tests cover reference payloads, slider limits, DLL structure layouts, channel and
frame configuration, connection cleanup, continued retries/recovery failures,
live value updates, and shutdown using a simulated driver. Physical GCAN/CAN
validation must be performed on Windows with the adapter and a CAN receiver.
