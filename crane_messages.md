# Crane CANopen messages

## Scope and assumptions

This is the simulator's application-specific mapping, not a manufacturer or
CiA crane profile. No crane EDS/DCF or existing object dictionary was supplied.
A receiver must use this exact mapping; default CANopen PDO identifiers alone
do not define the contents of a PDO. The proposed object dictionary entries
below describe the wire contract; the simulator does not implement SDO access,
PDO remapping, NMT reception, EMCY, or a complete CANopen stack.

The simulated crane is node **1**, already in **Operational** state when the
adapter connects. No NMT Start command or boot-up message is sent. Frames start
immediately after channel initialization. This mode remains fixed until
disconnect; received NMT commands do not change it.

## CAN interface

- Adapter: GCAN/USBCAN-II, device type `4`, device index `0`.
- Crane output: **second physical CAN output (CAN2), driver channel index `1`**.
- Bit rate: **250 kbit/s**, `Timing0=0x01`, `Timing1=0x1C`, normal mode `0`.
- Classical CAN, standard **11-bit** identifiers, data frames (no RTR).
- `ExternFlag=0`, `RemoteFlag=0`, `SendType=1` (single attempt).
- CAN1/channel `0` continues to transmit existing extended J1939 engine frames.
- Both channels share one device open/close lifecycle and have separate buses.

`VehicleInterface` initializes and starts both channels. `VehicleTransmitter`
sends every crane frame explicitly through channel `1`. Connect/disconnect in
the GUI controls both outputs. This is telemetry: slider readings are simulated
measurements, not motion commands. No RPDO command messages are transmitted.

## Message identifiers and timing

TPDO direction is from the simulated crane node to listeners.

| Message | Default COB-ID formula | Node 1 ID | DLC | Period | Purpose |
| --- | --- | --- | --- | --- | --- |
| TPDO1 | `0x180 + node_id` | `0x181` | 8 | 100 ms | Boom angle, extension, slew, hydraulic pressure |
| TPDO2 | `0x280 + node_id` | `0x281` | 2 | 100 ms | Suspended load |
| Heartbeat | `0x700 + node_id` | `0x701` | 1 | 1000 ms | Operational state (`0x05`) |

Only TPDO1 and TPDO2 are needed for the five readings. Heartbeat is a separate
CANopen service, not data inside a PDO. TPDO3/4, SYNC, SDO, and EMCY are unused.
The corresponding proposed PDO transmission type is `254` (manufacturer-specific
asynchronous), with 100 ms event timers. No SYNC producer is needed.

On connection, all three frames are due immediately. Each successful send
schedules the next send after its period. A failed send is retried after 20 ms;
channel recovery is attempted at most once per second while failures persist.
Timing uses a background thread and is best effort, not real time. GUI values
are sampled every 50 ms; a scheduled PDO encodes the latest worker snapshot.
Disconnect stops transmission and closes the adapter, without sending NMT Stop.
Heartbeat consumers should detect loss of this producer using their configured
timeout (for example 3000 ms).

## Data and encoding

Offsets below are **zero based**. All signals are CANopen `UNSIGNED16`, little
endian (low byte first), with zero offset. No application checksum, counter,
status word, or padding is included. The CAN controller supplies the CAN CRC.
Each field is encoded independently as `floor(value / resolution + 0.5)`.
Out-of-range or nonfinite numeric readings encode as `0xFFFF` (unavailable);
receivers must check this sentinel before scaling. Missing or nonnumeric inputs
are programming errors. The normal GUI confines each reading to its stated range.

### TPDO1 — `0x181`, 8 bytes

| Byte offset | Signal | Proposed OD entry | Resolution | Physical range | Raw range |
| --- | --- | --- | --- | --- | --- |
| 0–1 | Boom angle | `0x2000:01` | 0.01 degree | 0–70 degrees | 0–7000 |
| 2–3 | Boom extension | `0x2000:02` | 0.01 percent | 0–100% | 0–10000 |
| 4–5 | Slewing angle | `0x2000:03` | 0.01 degree | 0–360 degrees | 0–36000 |
| 6–7 | Hydraulic pressure | `0x2000:04` | 0.1 bar | 0–320 bar | 0–3200 |

Boom angle is measured above horizontal in the drawing. Extension is the
simulator's percentage, not a length in meters. Slew 0 degrees points forward
along the truck axis and increases clockwise in the top view. The GUI permits
360 degrees; it is transmitted as 36000, not wrapped to zero.

### TPDO2 — `0x281`, 2 bytes

| Byte offset | Signal | Proposed OD entry | Resolution | Physical range | Raw range |
| --- | --- | --- | --- | --- | --- |
| 0–1 | Suspended load | `0x2000:05` | 1 kg | 0–10000 kg | 0–10000 |

The GUI snaps load to 100 kg increments, but the protocol resolution is 1 kg.
DLC is exactly 2; bytes 2–7 are not transmitted.

### Heartbeat — `0x701`, 1 byte

Byte 0 is `05`, the CANopen Operational state. It describes the simulator's
assumed communication state, not the crane's mechanical readiness or safety.

## Proposed object dictionary/PDO mapping

Application record `0x2000` has subindex 0 = 5 and read-only, PDO-mappable
`UNSIGNED16` values at subindices 1–5. A compatible receiver/device configuration
would use the following producer configuration. These entries are documentation,
not SDO objects exposed by the current simulator.

| Object | Subindex/value |
| --- | --- |
| TPDO1 communication `0x1800` | `01=0x00000181` (enabled), `02=254`, `03=0` inhibit, `05=100` ms event timer |
| TPDO1 mapping `0x1A00` | `00=4`, `01=0x20000110`, `02=0x20000210`, `03=0x20000310`, `04=0x20000410` |
| TPDO2 communication `0x1801` | `01=0x00000281` (enabled), `02=254`, `03=0` inhibit, `05=100` ms event timer |
| TPDO2 mapping `0x1A01` | `00=1`, `01=0x20000510` |
| Producer heartbeat `0x1017:00` | `1000` ms |

A mapping descriptor is `(index << 16) | (subindex << 8) | bit_length`.
`0x10` means 16 bits. TPDO1 maps 64 bits and TPDO2 maps 16 bits, within the
classical CAN limit of 64 bits. Node ID changes require regenerating all three
COB-IDs consistently; `NODE_ID` is defined in `crane_can.py`.

## Reference frames

At GUI startup: angle 35 degrees, extension 35%, slew 0 degrees, pressure
160 bar, load 0 kg:

```text
CAN2  ID=181  DLC=8  DATA=AC 0D AC 0D 00 00 40 06
CAN2  ID=281  DLC=2  DATA=00 00
CAN2  ID=701  DLC=1  DATA=05
```

At maximum slider values (70 degrees, 100%, 360 degrees, 320 bar, 10000 kg):

```text
CAN2  ID=181  DLC=8  DATA=58 1B 10 27 A0 8C 80 0C
CAN2  ID=281  DLC=2  DATA=10 27
```

For example, `40 06` decodes to `0x0640=1600`, hence 160.0 bar. An unavailable
signal occupies `FF FF` in its own field; valid neighboring signals remain valid.

## Verification

Run `python -m unittest discover -s tests -v` from this directory. Tests cover
reference bytes, boundaries, invalid readings, channel selection, frame flags,
DLC, shared device lifecycle, scheduling, live updates, and failure cleanup.
Physical transmission requires Windows, the GCAN driver, and a matching
Python/DLL architecture. Hardware bus operation has not been verified in this
Linux workspace. Confirm a capture on CAN2 shows standard IDs `181`, `281`,
and `701`, while CAN1 retains the engine frames.

Every vehicle send selects its channel explicitly: FMS uses channel `0` with
extended frames; crane PDOs and heartbeat use channel `1` with standard frames.
The routing regression test verifies every identifier at the DLL boundary even
when the interface default is set to CAN2.

For a hardware isolation check, clear the capture and monitor each physical bus
separately. CAN1 should contain only `0CF00400`, `18FEEE00`, `18FEEF00`,
`18FEF100`, and `18FEE500`; CAN2 should contain only `181`, `281`, and `701`
from this simulator. The two outputs must not share CAN-H/CAN-L wiring. Check
that any adapter/tool forwarding or bridge mode is disabled. Receive entries
identify traffic observed on a bus, but do not identify which sender or bridge
put it there.
