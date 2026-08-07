# STM32H743 Drone Bench Configurator

This dependency-light Python/Tkinter desktop application monitors STM32H743
H3B-2 telemetry and provides a deliberately constrained single-motor bench
test interface. The STM32 firmware remains the authoritative safety layer.
The UI redesign does not change any firmware safety gate, command, telemetry
format, PWM configuration or motor mapping.

## Requirements and startup

- Python 3 with Tkinter
- `pyserial` for a physical COM connection
- 3.3 V USB-TTL adapter

Install pyserial:

```powershell
py -m pip install pyserial
```

Start without auto-connecting:

```powershell
py tools\ibus_monitor.py
```

Preselect COM6 and 115200 baud:

```powershell
py tools\ibus_monitor.py --port COM6 --baud 115200
```

Run the simulated interface without opening a COM port:

```powershell
py tools\ibus_monitor.py --demo
```

Replay a raw or configurator CSV log without enabling commands:

```powershell
py tools\ibus_monitor.py --replay logs\bench_example.csv
```

Close PuTTY and every other serial terminal before connecting. Windows permits
only one application to own a COM port. If the app reports:

```text
COM port is busy. Close PuTTY or any other serial application.
```

close the competing program, refresh the port list and reconnect.

## Layout and navigation

The default dark theme uses a fixed sidebar, fixed safety header, resizable
page area and compact status bar. It is designed for 1366x768 through
1920x1080 and has a minimum window size of 1180x720. The Motor Test safety
list scrolls locally; important RUN, STOP and Emergency Stop controls remain
visible without scrolling the entire application.

Sidebar pages:

- **Dashboard** — read-only board overview and combined bench-readiness list.
- **Connection** — COM controls, protocol state and firmware log mode.
- **Receiver** — iBUS link, safety switches and eight animated channel bars.
- **ESC Outputs** — read-only TIM4 PWM monitor for PD12 through PD15.
- **Motor Test** — safety-gated, single-motor command workflow.
- **Diagnostics** — bounded console, counters, filters and CSV capture.

The sidebar footer shows COM, baud, protocol and app version. The fixed header
shows COM, protocol, iBUS and ESC status. Its global red Emergency Stop sends
the existing raw `!` byte and is enabled only when a command-capable connection
exists. Changing pages never sends a command.

The bottom status bar shows port/baud, RX byte rate, line count, packet ages,
TX count, protocol version and worker state. Stale data is also stated in page
badges; color is never the only status indicator.

## Status colors

- Green with text such as PASS, SAFE, READY or ONLINE: valid/safe state.
- Amber with text such as RUNNING, TEST or STALE: attention or active test.
- Red with text such as FAIL, FAULT, LOST or ERROR: unsafe/error state.
- Gray with text such as NO DATA or DISCONNECTED: unavailable/inactive state.

Dark mode is the only theme in this revision. This keeps the UI predictable
without adding a settings subsystem or any safety-related persistence.
Propeller confirmation and pending commands are never persisted.

## Dashboard

The Dashboard is monitoring-only. Cards summarize Serial, Board Protocol,
Receiver, ESC PWM, Motor Test and sensor log activity. The Ready for Bench Test
section combines all GUI prerequisites and links to Motor Test; it never sends
RUN. BMI270/BMP388 status is inferred only from existing recent log text, so
missing periodic logs are shown as no recent log rather than a hidden success.

## Connection

The Connection page provides Refresh, Connect and Disconnect, RX metrics,
worker state, last exception and firmware log controls:

- `LOG QUIET` suppresses periodic human-readable output while retaining
  machine telemetry, command replies and critical messages.
- `LOG FULL` restores periodic logs.
- `LOG STATUS` requests the current mode.

Disconnect and application close request one best-effort `MTEST STOP` before
the real SerialWorker closes. This is only an extra precaution; firmware does
not depend on the PC for failsafe behavior. Replay mode is strictly read-only.

## Receiver

Eight Canvas bars cover 800–2200 us with 1000, 1500 and 2000 markers and a
highlighted normal region of 1000–2000 us. The page displays:

- CH1 Roll, CH2 Pitch, CH3 Throttle, CH4 Yaw
- CH5 Safety 1, CH6 Safety 2, CH7 AUX3, CH8 AUX4

Safety cards state current values and required thresholds: CH3 <= 1050 us,
CH5 >= 1900 us and CH6 >= 1900 us. When no telemetry exists, an empty-state
panel recommends checking COM, USB-TTL wiring, receiver power and firmware.

## ESC Outputs

Four read-only cards show Motor 1/PD12/TIM4 CH1 through
Motor 4/PD15/TIM4 CH4. A 1000 us pulse is SAFE/IDLE, 1020–1100 us is TEST,
out-of-range output is INVALID, and stale telemetry is stated explicitly.
The page has no RUN button.

## Motor Test

The page has three areas:

1. **Safety Gate** — status, current value, requirement and remediation for
   every prerequisite.
2. **Test Setup** — one-of-four motor selector, bounded pulse/duration controls,
   safe presets and propeller-removal confirmation.
3. **Live Test** — firmware state, active/commanded output, countdown, ACK,
   abort reason, counters, STOP and Emergency Stop.

RUN remains disabled until all of these pass:

- command-capable serial connection and online protocol
- valid/fresh iBUS with reported age <= 50 ms
- CH3 <= 1050 us, CH5 >= 1900 us, CH6 >= 1900 us
- ESC SAFE, mask `0x0F`, fresh `@ESC`
- fresh `@MTEST`, firmware READY and active output 1000 us
- explicit **I confirm that all propellers are removed** checkbox

Limits are unchanged: one motor, 1020–1100 us in 10 us steps, and 100–2000 ms
in 100 ms steps. Presets are 1020 us/100 ms and 1050 us/500 ms. There is no
run-all, sweep, calibration, throttle mapping, automatic retry or auto-next.

Before RUN, a themed dialog shows motor/pin, pulse, duration and
`PROPELLERS MUST BE REMOVED`. Enter is not bound to confirmation. Only
**CONFIRM AND RUN** sends the existing command:

```text
MTEST RUN <motor> <pulse_us> <duration_ms>\r\n
```

STOP sends `MTEST STOP\r\n`; Emergency Stop sends raw `!` without newline and
clears an unsent RUN. A firmware FAULT is shown prominently with its original
reason and no bypass control.

The collapsible Bench Test Guide describes this manual sequence:

1. Remove all propellers and secure the frame.
2. Verify receiver LINK OK and throttle below 1050.
3. Enable CH5 and CH6.
4. Verify ESC SAFE and mask `0x0F`.
5. Select one motor and begin at 1020 us/100 ms.
6. Confirm output returns to 1000 us before testing another motor.

## Diagnostics and CSV

The counter dashboard covers RX, iBUS errors, malformed packets and TX. The
console has packet and severity filters, search, Pause/Resume, Clear, Copy,
Save and Auto-scroll. Lines are color-classified while retaining text labels.
The parser still receives every line even when the console is paused or
filtered. Memory is bounded to 2000 stored and 1000 visible lines; UI inserts
are batched at the shared refresh cadence.

Optional CSV logging selects `@IBUS`, `@ESC`, `@MTEST` and `@MACK` and writes:

```text
logs/bench_YYYYMMDD_HHMMSS.csv
```

## Demo and replay

Demo Controls are visible only with `--demo`. They cover READY, AUX switches
off, RUNNING, TIME_EXPIRED, emergency, FAULT, stale telemetry, disconnected
and an automatic sequence. Demo mode never creates a SerialWorker and never
calls `serial.write()`.

Replay uses the shared parser in a separate read-only worker. Motor controls
and Emergency Stop are disabled, so replay cannot enqueue a hardware command.

## Safety boundary

The GUI remains an additional operator layer. Firmware independently validates
receiver state, channel thresholds, ESC state, single-motor selection, pulse
range, duration, timeout and STOP/emergency behavior. If the GUI, USB link or
PC fails, firmware remains responsible for returning every output to 1000 us.
This redesign changes presentation only; it does not relax firmware safety.
