# CAN Vehicle Simulator

A Python desktop simulator that draws a truck-mounted crane and lets you adjust crane position, tire conditions, and engine readings. It uses Tkinter for the interface and can optionally transmit engine telemetry as J1939/FMS CAN messages through a GCAN-II / USBCAN-II USB adapter.

The graphics are drawn directly on a Tkinter Canvas; no image assets or third-party Python packages are required.

## Features

- Adjust boom angle, telescopic extension, hydraulic pressure, slewing angle, and suspended load.
- Set pressure and temperature independently for four wheels. Low pressure changes tire shape, and warning conditions change tire colors.
- Adjust engine RPM, oil temperature and pressure, and coolant temperature and pressure, with live gauges and warning colors.
- Optionally send engine readings on CAN1 at 250 kbps using extended 29-bit CAN identifiers.
- Keep the interface responsive while a background worker handles CAN transmission, retries, and device cleanup.

This is a visual and telemetry simulator. The crane drawing and warning colors are illustrative; the application does not calculate lifting capacity, stability, or vehicle dynamics.

## Requirements

### Desktop simulation

- Python 3 with Tkinter available.
- A graphical desktop session.

The visual simulator can run without a CAN adapter on Windows, Linux, or macOS where Python/Tkinter is supported. Check Tkinter with:

```sh
python -m tkinter
```

This should open a small test window. If Tkinter is missing, install it through your Python installer or operating system package manager; on Debian/Ubuntu, the package is typically `python3-tk`.

### CAN transmission

- Windows with the GCAN / USBCAN USB driver installed.
- A GCAN-II / USBCAN-II adapter.
- Python and `ECanVci.dll` with matching architectures. The bundled DLL is 64-bit, so use 64-bit Python.
- A correctly wired and terminated CAN test bus, with another active node configured for 250 kbps to acknowledge frames.

Keep `ECanVci.dll` beside `fms_can.py`. The application loads the DLL directly through Python's standard-library `ctypes` module.

## Quick start

Open a terminal in the repository directory and run:

```sh
python can_vehicle_simulator.py
```

On systems where Python 3 is named `python3`, use that command instead. There is no Python dependency installation step.

The window starts with CAN disconnected. You can use all visual controls immediately without connecting hardware.

**Simulation: OFF/ON** and **Connect GCAN-II** sit inside the drawing's top-left area, with their status labels beside them. **Simulate flat** and **Reset wheel** are in the Tires panel beside the wheel controls. The drawing resizes with the window, allowing a shorter window while keeping the crane, tire, and engine controls visible at the bottom.

## Using the controls

| Panel | Controls | Behavior |
| --- | --- | --- |
| Crane | Boom angle: 0–70°; extension: 0–100%; hydraulic pressure: 0–320 bar; slew: 0–360° | Updates the boom drawing, pressure indicator, and top-view slew indicator. |
| Crane load | 0–10,000 kg in 100 kg steps | Displays a suspended load whose size changes with the selected mass. |
| Tires | Select Rear 1, Rear 2, Front 1, or Front 2; pressure: 0–10 bar; temperature: 0–120 °C | Each wheel retains its own readings. **Simulate flat** sets the selected wheel to 1 bar; **Reset wheel** restores it to 8 bar and 35 °C. |
| Engine | RPM: 0–4,000; oil temperature: 0–160 °C; oil pressure: 0–10 bar; coolant temperature: 0–130 °C; coolant pressure: 0–4 bar | Updates gauges and, when connected, the transmitted engine values. |

### Automatic simulation

Click **Simulation: OFF** to activate automatic operation. The button changes to
**Simulation: ON**. Engine readings, vehicle speed, crane position, hydraulic
pressure, load, and each wheel’s pressure and temperature vary continuously
together. Blended oscillations with different periods and phases give each
parameter smooth, organic movement. The crane continues moving while the engine
is running and the vehicle has speed.
Running hours accumulate from their value when simulation starts. Loads remain
in 100 kg increments.

Click the button again to stop and resume manual control at the current values.
While simulation is active, its updates overwrite manual slider changes.
Simulation does not connect CAN hardware automatically; if CAN is already
connected, the existing transmitter sends the changing engine and crane readings.
The motion is illustrative and does not model lifting capacity or vehicle dynamics.

### Connecting CAN hardware

1. Install the GCAN Windows driver and connect the adapter by USB.
2. Connect CAN-H, CAN-L, and the appropriate common ground to your test bus. Use correct termination, typically 120 Ω at each end, and an active CAN receiver at 250 kbps.
3. Launch the simulator and click **Connect GCAN-II**.
4. Check the status beside the button, then change engine sliders to update the transmitted readings.
5. Click **Disconnect GCAN-II** to stop transmission. Closing the window also stops the worker and closes the device.

The implementation selects the first adapter (device index `0`), CAN1 (channel index `0`), and USBCAN-II device type `4`. These settings are defined in `GcanInterface` in `fms_can.py`; the GUI has no adapter or baud-rate selector.

## CAN messages

Engine telemetry and FMS TIRE1 tire pressure transmit on CAN1; crane CANopen telemetry transmits on CAN2. Both channels use 250 kbps. Tire pressure sends one wheel at a time in rotation. The Tires panel has a **Send interval (sec)** numeric input defaulting to **10** seconds per tire, adjustable while connected. Temperature remains a visual control. See [crane_messages.md](crane_messages.md) for crane telemetry and [FMS_CAN.md](FMS_CAN.md) for tire location mapping.

| Message | PGN | CAN identifier | Nominal interval | Encoded readings |
| --- | --- | --- | --- | --- |
| EEC1 | 61444 (`F004`) | `0CF00400` | 20 ms | Engine speed, SPN 190 |
| ET1 | 65262 (`FEEE`) | `18FEEE00` | 1,000 ms | Coolant temperature, SPN 110; oil temperature, SPN 175 |
| TIRE1 | 65268 (`FEF4`) | `18FEF400` | Adjustable, default 10 sec per tire | Tire location, SPN 929; pressure, SPN 241 |
| EFL/P1 | 65263 (`FEEF`) | `18FEEF00` | 500 ms | Oil pressure, SPN 100; coolant pressure, SPN 109 |

Each message has an eight-byte payload. Multi-byte signals use little-endian encoding, unsupported signals remain `FF` (not available), and the source address is fixed to `00` (engine #1). Engine speed and coolant temperature are FMS signals; the other readings are supplementary J1939 telemetry that an FMS-only receiver may ignore.

The simulator does not implement J1939 address claiming, CAN reception, or a complete FMS gateway. Use a test bus without another sender using source address `00`. Message intervals are scheduled by a Python worker and are not hard real-time guarantees.

See [FMS_CAN.md](FMS_CAN.md) for signal scaling, byte positions, reference payloads, and retry behavior.

## Repository structure

| File | Purpose |
| --- | --- |
| `can_vehicle_simulator.py` | Application entry point: Tkinter drawing, sliders, gauges, and CAN connection controls. |
| `fms_can.py` | Engine signal encoding, GCAN DLL structures and calls, and the threaded transmission worker. |
| `tests/test_fms_can.py` | Unit tests for encoding, driver configuration, connection cleanup, retries, live updates, and shutdown using a simulated driver. |
| `ECanVci.dll` | Bundled 64-bit Windows GCAN interface library. |
| [FMS_CAN.md](FMS_CAN.md) | Details of the implemented engine transmission. |
| [gcan_programming.md](gcan_programming.md) | Broader GCAN programming guide. Some examples reference `J1939_simulator.py`, which is not included here; the current entry point is `can_vehicle_simulator.py`. |
| [ECAN_ECanVci_Function_Library_Manual_V5.2.md](ECAN_ECanVci_Function_Library_Manual_V5.2.md) | Markdown reference for the vendor DLL API. |
| `Guangcheng Technology USBCAN Interface Function Library Instruction Manual.pdf` | Vendor CAN interface manual. |
| `fms document_v_05_vers.11.11.2025.pdf` | FMS reference document. |

The GUI polls worker status and copies current engine values to the worker every 50 ms. The worker protects shared state with a lock and performs DLL calls outside the Tkinter thread. Failed sends are retried every 20 ms; persistent failures trigger a CAN1 reset/restart attempt at most once per second.

## Tests

From the repository directory:

```sh
python -m unittest discover -s tests -v
```

These tests do not require a GUI, Windows, the vendor DLL, or physical CAN hardware. They validate the encoder and transport logic with a simulated driver. Actual USB communication and reception must be checked separately on Windows with the adapter and a CAN receiver.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Tkinter import fails or no window opens | Install Tkinter and run from a graphical desktop session. A headless environment needs a display server. |
| Connection reports that GCAN requires Windows | Use Windows for hardware transmission; the visual simulator can still be used on other supported platforms. |
| `ECanVci.dll` cannot be loaded | Keep it beside `fms_can.py`, install the GCAN driver, and match Python/DLL architectures. |
| `OpenDevice` fails | Check the USB connection, driver installation, and whether the first adapter is available. |
| `InitCAN` or `StartCAN` fails | Check adapter compatibility and CAN1 setup; the application uses fixed 250 kbps timing. |
| Status shows transmission errors and retries | Check wiring, termination, receiver baud rate, and an active node to acknowledge frames. USB connection alone does not establish a working CAN bus. |
| Connection fails or the adapter is unplugged | Correct the problem and reconnect using the button. Unplugging can invalidate the driver's device handle. |

A successful DLL send does not independently confirm that a receiver decoded the data. Verify the identifiers and payloads with your CAN receiver or analyzer.
