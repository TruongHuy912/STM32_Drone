# STM32H743 Drone Bench Configurator

`tools/ibus_monitor.py` is a Windows-friendly Python/Tkinter application for
the STM32H743 H3B-2 bench firmware. It monitors iBUS, ESC PWM, motor-test
telemetry and command acknowledgments. It can send bounded single-motor test
commands, but the STM32 firmware remains the authoritative safety layer.

## Requirements

- Python 3 with Tkinter.
- `pyserial` for a physical COM connection.
- A USB-TTL adapter using 3.3 V logic.

Install pyserial:

```powershell
py -m pip install pyserial
```

## Starting the application

Open the application and select a port:

```powershell
python tools/ibus_monitor.py
```

Open with COM6 preselected at 115200 baud:

```powershell
python tools/ibus_monitor.py --port COM6 --baud 115200
```

Run the simulated interface without opening a COM port:

```powershell
python tools/ibus_monitor.py --demo
```

Demo mode simulates receiver channels, ESC SAFE state, READY/RUNNING motor
tests, countdown, TIME_EXPIRED, emergency stop, rejected command, iBUS loss and
stale telemetry. Demo mode creates no SerialWorker and never calls
`serial.write()`.

Close PuTTY, STM32 serial terminals and any other program using the selected
port before connecting. Windows normally permits only one application to own a
COM port.

## Application tabs

### Connection

Select/refresh the COM port, connect/disconnect, inspect RX/TX counters and
telemetry age, and choose the firmware log mode:

- `LOG QUIET` suppresses periodic human-readable samples and diagnostics while
  retaining machine telemetry, command replies, aborts and critical errors.
- `LOG FULL` restores all periodic diagnostics.
- `LOG STATUS` queries the current mode.

Disconnect and application close request one best-effort `MTEST STOP` before
the SerialWorker closes the port. This is an additional precaution only;
firmware failsafe does not depend on the GUI.

### Receiver

Displays `@IBUS` LINK state, frame age, counters and CH1–CH8 on an 800–2200
scale with 1000/1500/2000 markers. The safety indicators show:

- THROTTLE LOW: CH3 <= 1050;
- CH5 ENABLED: CH5 >= 1900;
- CH6 ENABLED: CH6 >= 1900.

### ESC Outputs

Displays `@ESC` state, started mask, frequency and TIM4 MOTOR1–MOTOR4 pulses.
State other than SAFE, mask other than `0x0F`, stale telemetry, or a pulse
outside the firmware idle/test ranges is shown in red. This tab has no RUN
control.

### Motor Test

This is the only tab that can send `MTEST` commands. Before RUN becomes
available, every GUI checklist item must pass:

- serial connected;
- valid/fresh iBUS, reported frame age <= 50 ms;
- CH3 <= 1050;
- CH5 and CH6 >= 1900;
- ESC SAFE with started mask `0x0F`;
- fresh `@ESC` and `@MTEST` telemetry;
- firmware motor-test state READY;
- **I confirm that all propellers are removed** checked.

The confirmation checkbox is never saved. It clears on startup, disconnect,
serial error and detected firmware reset.

Hard GUI and firmware limits:

- one motor from 1 through 4;
- pulse from 1020 through 1100 us, step 10 us;
- duration from 100 through 2000 ms, step 100 ms;
- no sweep, run-all, calibration, mixer, throttle mapping or automatic retry.

RUN shows a final confirmation dialog. After confirmation it sends exactly one:

```text
MTEST RUN <motor> <pulse_us> <duration_ms>
```

RUN remains locked while waiting for `@MACK` and until new `@MTEST` telemetry
confirms that the test has ended. STOP sends `MTEST STOP`. The large red
Emergency Stop button sends the raw byte `!` without newline, removes an
unsent RUN from the TX queue and immediately shows `STOP REQUESTED`.

When the GUI sees RUNNING and then detects iBUS loss, high throttle or loss of
CH5/CH6 enable, it queues one STOP for that event. It does not spam STOP.
Firmware independently checks the same conditions and stops even if the GUI,
USB cable or PC fails.

### Diagnostics & Logs

The bounded raw console supports ALL, IBUS, ESC, MTEST, MACK, SENSORS and
ERRORS filters plus Pause/Resume, Clear and Auto-scroll. It retains at most
2000 lines in memory and 1000 visible lines.

Optional CSV logging can independently include `@IBUS`, `@ESC`, `@MTEST` and
`@MACK`. Files are created as:

```text
logs/bench_YYYYMMDD_HHMMSS.csv
```

CSV logging is not required to control a test.

## Single-motor bench sequence

1. Remove all propellers and secure the airframe.
2. Connect USB-TTL RX to PA9, TX to PA10 and GND to GND; use 3.3 V logic only.
3. Connect and verify fresh Receiver, ESC and Motor Test telemetry.
4. Put CH3 low and enable both CH5 and CH6.
5. Check the propeller-removal confirmation.
6. Select one motor and start with 1020 us for 100 ms.
7. Confirm the selected motor returns to 1000 us before testing the next motor.
8. Use Emergency Stop or disconnect LiPo immediately on abnormal behavior.

Never exceed 1100 us or 2000 ms. Never attach propellers during H3B-2.

## `@MACK` command acknowledgment

Firmware replies once per processed command:

```text
@MACK,<timestamp_us>,<command>,<accepted>,<reason>,<motor>,<pulse_us>,<duration_ms>
```

Examples:

```text
@MACK,12345678,RUN,1,NONE,1,1050,500
@MACK,12345780,RUN,0,CH5_NOT_ENABLED,1,1050,500
@MACK,12345900,STOP,1,USER_STOP,0,1000,0
```

## Common COM errors

`COM port is busy. Close PuTTY or any other serial application.` means Windows
returned Access denied/PermissionError because another program owns the port.
Close that program, press Refresh and reconnect. Also verify the port name,
USB-TTL driver and physical USB connection.

Unexpected disconnects clear the propeller confirmation, disable Motor Test
controls and trigger a best-effort STOP. Reconnect only after checking that all
four ESC outputs are back at 1000 us.

## Safety boundary

The GUI never bypasses firmware state, range or iBUS checks. The STM32 remains
responsible for enforcing one motor, 1020–1100 us, 100–2000 ms, timeout,
receiver gates, STOP/`!`, safe CCR restoration and latched FAULT behavior.
