# H3B-0 ESC PWM CubeMX plan

Status: resource audit and CubeMX plan only. This file does not authorize motor
operation, does not change the `.ioc`, and does not add PWM runtime code.

Audit baseline: `main` at `8f41f1afd732488d38444fa8d4f89a3b1bd55303`.

## 1. Selected timer

Use **TIM4**, a general-purpose 16-bit timer with four independent
capture/compare channels. TIM2 remains dedicated to the 1 MHz `micros()`
counter and must not be changed or reused.

TIM4 is preferred because one timer can generate all four ESC PWM outputs from
the same counter, so all outputs have the same period and tick. The selected
alternate pin group is physically compact on header P1 and does not consume
another UART instance.

## 2. Pin and channel assignment

| Motor label | TIM4 channel | MCU pin | Alternate function | WeAct V1.2 header |
| --- | --- | --- | --- | --- |
| `MOTOR1_PWM` | TIM4_CH1 | PD12 | AF2 | P1 pin 34 |
| `MOTOR2_PWM` | TIM4_CH2 | PD13 | AF2 | P1 pin 33 |
| `MOTOR3_PWM` | TIM4_CH3 | PD14 | AF2 | P1 pin 32 |
| `MOTOR4_PWM` | TIM4_CH4 | PD15 | AF2 | P1 pin 31 |

All four pins are available in the STM32H743VIT6 LQFP100 package, are broken
out on the WeAct MiniSTM32H743VIT6 V1.2 board, and are unassigned in the current
`.ioc`.

### Why PB6-PB9 were not selected

PB6-PB9 support TIM4_CH1 through TIM4_CH4 on AF2 and are unassigned in the
current `.ioc`, but the board schematic shows physical sharing:

- PB6 is connected to the on-board QSPI flash chip-select (`QSPI_BK1_NCS`).
- PB7 is connected to the DVP camera `VSYNC` net.
- PB8 is connected to the DVP camera I2C1 SCL net.
- PB9 is connected to the DVP camera I2C1 SDA net.

They also consume useful alternate UART routes: PB6/PB7 can carry USART1 or
LPUART1, and PB8/PB9 can carry UART4. The PD12-PD15 group therefore has fewer
board-level and future-UART costs.

### Board-level limitation of the selected group

PD12 and PD13 are also connected to the on-board QSPI flash as IO1 and IO3.
PD14 and PD15 have no additional on-board peripheral connection shown in the
V1.2 schematic. The current `.ioc` does not enable QSPI and PB6/QSPI_NCS is
held inactive by the board pull-up, so there is no active project-resource
conflict. H3B must not initialize or use the on-board QSPI flash while PD12 and
PD13 are assigned to motor PWM. If future QSPI use is required, the motor pin
assignment must be revisited.

## 3. Protected resources and expansion audit

The following assignments must remain unchanged when CubeMX is edited:

- TIM2: 1 MHz, 32-bit free-running `micros()` timebase.
- PE3: `STATUS_LED`.
- PA9/PA10: USART1 debug, 115200 8N1.
- PA2/PA3: USART2 iBUS, 115200 8N1 with RX interrupt.
- PB10/PB11: I2C2 for BMP388.
- PB12-PB15: SPI2 and BMI270 chip select.
- PA13/PA14: SWD.
- PH0/PH1: HSE crystal.
- PC14/PC15: LSE crystal.
- BOOT0 and NRST: board boot/reset functions.
- PA11/PA12: currently unassigned by this project; leave available for USB.

The current `.ioc` contains no TIM4, QSPI, USB, DCMI, SDMMC, USART3, USART6,
or UART4 peripheral instance. The following future serial pairs remain possible
and must be re-audited when they are actually added:

- USART3 on PD8/PD9 for a Raspberry Pi link.
- USART6 on PC6/PC7 for GNSS.
- UART4 on PB8/PB9 as another option.

PD8/PD9 and PC6/PC7 are currently unassigned and broken out on the board.
PC6/PC7 are also routed to the DVP connector, and PB8/PB9 are the DVP I2C
pair, so these options assume that the camera interface is not used.

## 4. Actual timer clock and calculations

TIM4 is on APB1. The current generated clock tree is:

- HCLK: 200 MHz.
- APB1 prescaler: divide by 2.
- PCLK1: 100 MHz.
- APB1 timer kernel clock: `2 * PCLK1 = 200 MHz`, because the APB1 prescaler
  is not 1. CubeMX already reports a 200 MHz timer output clock for this clock
  domain.

For a 1 MHz counter tick:

```text
counter_clock = timer_kernel_clock / (PSC + 1)
1,000,000     = 200,000,000 / (PSC + 1)
PSC           = 199
```

Therefore one counter tick is exactly 1 microsecond.

For the initial 50 Hz PWM:

```text
PWM_frequency = 1,000,000 / (ARR + 1)
50            = 1,000,000 / 20,000
ARR           = 19,999
```

With PWM Mode 1 and active-high polarity, CCR values directly represent pulse
width in microseconds:

- Minimum pulse: CCR = 1000, or 1000 microseconds.
- Initial/idle pulse: CCR = 1000.
- Maximum planned pulse: CCR = 2000, or 2000 microseconds.

The 16-bit TIM4 ARR range is sufficient for 19,999.

## 5. Exact STM32CubeMX configuration

Do not edit the `.ioc` in a text editor. Open
`weact_h743_fc_bringup.ioc` in STM32CubeMX and make only the following changes:

1. Open **Timers > TIM4**.
2. Select **Internal Clock** as the TIM4 clock source.
3. Enable **PWM Generation CH1**, **PWM Generation CH2**,
   **PWM Generation CH3**, and **PWM Generation CH4**.
4. In Pinout, explicitly map the channels to PD12, PD13, PD14, and PD15.
   Confirm CubeMX shows AF2 TIM4 for each pin.
5. Apply the user labels `MOTOR1_PWM`, `MOTOR2_PWM`, `MOTOR3_PWM`, and
   `MOTOR4_PWM` in channel order.
6. Set **Prescaler** to `199`.
7. Set **Counter Mode** to `Up`.
8. Set **Counter Period** to `19999`.
9. Set **Clock Division** to `DIV1`.
10. Set **Auto-reload preload** to `Enable`.
11. For each of CH1-CH4, set:
    - OC mode: `PWM Mode 1`.
    - Pulse: `1000`.
    - Output compare polarity: `High`.
    - Output compare fast mode: `Disable`.
12. Leave TIM4 DMA requests disabled.
13. Leave the TIM4 global interrupt disabled for H3B.
14. Do not configure break/dead-time; TIM4 is a general-purpose timer and has
    no complementary motor-power stage in this plan.
15. Save the `.ioc` and select **Generate Code**.

CubeMX generation should create or update these items:

- `TIM_HandleTypeDef htim4`.
- `void MX_TIM4_Init(void)` and its generated call from `main()`.
- `HAL_TIM_PWM_MspInit()` for the TIM4 peripheral clock, as applicable to the
  generated HAL template.
- `HAL_TIM_MspPostInit()` for GPIO alternate-function setup.
- PD12-PD15 configured as `GPIO_AF2_TIM4`.
- Pin-label defines in `Core/Inc/main.h`, if generated for alternate-function
  user labels.

Generation and timer initialization alone must not be followed by
`HAL_TIM_PWM_Start()` in H3B-0. No motor PWM channel is to be started until a
separate, reviewed runtime bring-up step.

## 6. Regression checklist after CubeMX generation

Before writing any runtime PWM code:

- Confirm the diff contains only the intended TIM4 and PD12-PD15 generation.
- Confirm SYSCLK remains 400 MHz, HCLK remains 200 MHz, PCLK1 remains 100 MHz,
  and the APB1 timer clock remains 200 MHz.
- Confirm TIM2 remains prescaler 199, 32-bit period `0xFFFFFFFF`, and is still
  started by the existing H1 code.
- Confirm PE3 heartbeat and USART1 debug configuration are unchanged.
- Confirm USART2 PA2/PA3, its IRQ priority, and iBUS callbacks are unchanged.
- Confirm SPI2 PB12-PB15 and I2C2 PB10/PB11 are unchanged.
- Confirm HSE, LSE, SWD, BOOT0, NRST, and any reserved USB pins are unchanged.
- Confirm no QSPI/DCMI/SDMMC peripheral was enabled.
- Confirm no DMA or TIM4 interrupt was enabled.
- Confirm no generated or user code calls `HAL_TIM_PWM_Start()`.
- Run `cmake --preset Debug` and `cmake --build --preset Debug` and require a
  warning-free build before any hardware test.

## 7. Why bring-up starts at 50 Hz

50 Hz is the conservative first test because the 20 ms frame leaves ample
space around a 1-2 ms pulse, is easy to verify on an oscilloscope or logic
analyzer, and is broadly compatible with conventional PWM-input ESCs. It is a
signal-generation test only; a 1000 microsecond value must not be treated as
permission to arm or spin a motor.

## 8. Conditional transition to 400 Hz

Change to 400 Hz only after all four channels pass a 50 Hz scope/logic-analyzer
test and the exact ESC documentation or a controlled ESC test confirms 400 Hz
PWM compatibility. Keep the 1 MHz tick and prescaler 199, then change only the
period:

```text
400 = 1,000,000 / 2,500
ARR = 2,499
```

CCR values 1000-2000 continue to represent 1000-2000 microseconds. Re-run the
complete resource, build, and waveform checks after the change. Do not use
DShot, OneShot, DMA, throttle mapping, arming logic, or actuator control during
this initial bring-up.

## 9. Safety requirements

- Remove all propellers before any ESC work.
- Do not connect the flight LiPo while merely generating or reviewing code.
- First inspect every output using an oscilloscope or logic analyzer with ESCs
  disconnected.
- Do not connect multiple ESC BEC 5 V outputs in parallel. Use one intentional
  5 V source or isolate the other BEC 5 V wires according to the power design.
- STM32 ground and every ESC signal ground must be common before applying a
  control signal.
- Do not map iBUS throttle directly to PWM.
- Do not add arming or motor-start behavior as part of this plan.

## 10. Audit sources

- STMicroelectronics, STM32H742xI/G and STM32H743xI/G datasheet, timer feature
  table and pin alternate-function tables:
  https://www.st.com/resource/en/datasheet/stm32h743ag.pdf
- WeAct Studio MiniSTM32H7xx official repository and V1.2 schematic:
  https://github.com/WeActStudio/MiniSTM32H7xx
  https://github.com/WeActStudio/MiniSTM32H7xx/blob/master/Hardware/STM32H7xx%20SchDoc%20V12.pdf
- Project clock, pin, and peripheral state audited from
  `weact_h743_fc_bringup.ioc`, `Core/Src/main.c`, `Core/Src/tim.c`, and
  `Core/Inc/tim.h` at the baseline commit above.
