# FlySky iBUS Monitor for Windows

The monitor displays only firmware lines beginning with `@IBUS,`. USART1 logs
from BMI270, BMP388, H1, and other diagnostics are ignored.

## Requirements

- Python 3 with Tkinter.
- `pyserial` for a physical COM connection. Demo mode does not require a COM
  port.

Install `pyserial` manually:

```powershell
py -m pip install pyserial
```

## Run

Open the interface and select a COM port:

```powershell
py tools\ibus_monitor.py
```

Open COM6 directly at 115200 baud:

```powershell
py tools\ibus_monitor.py --port COM6 --baud 115200
```

Close PuTTY or any other terminal before connecting. Windows does not allow two
applications to own the same COM port at the same time.

Test the interface without hardware or a serial port:

```powershell
py tools\ibus_monitor.py --demo
```

Demo mode animates all channel bars and alternates between `LINK OK` and
`LINK LOST`.

## Channel display

The first eight iBUS channels are shown as:

- CH1 Roll
- CH2 Pitch
- CH3 Throttle
- CH4 Yaw
- CH5 AUX1
- CH6 AUX2
- CH7 AUX3
- CH8 AUX4

Expected transmitter values are approximately 1000 at the low endpoint, 1500
at center, and 2000 at the high endpoint. The visual bar is limited to
800–2200, while the numeric label always shows the received value unchanged.

To test `LINK LOST`, disconnect the iBUS signal wire from PA3. The GUI retains
the last valid channel values but grays the channel bars. This status detects
the UART frame stream only; a receiver can continue sending failsafe channel
values after its RF link is lost.

## CSV logging

CSV logging is optional. Press **Start CSV Log** to create:

```text
logs/ibus_YYYYMMDD_HHMMSS.csv
```

Press **Stop CSV Log** before inspecting or moving the file. Each row contains
the PC timestamp, firmware timestamp, stream state, frame age, CH1–CH8, and the
four diagnostic counters.
