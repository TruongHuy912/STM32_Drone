# HMC5883L Z-axis fault report

## Test context

- Test date: 2026-08-05
- MCU/board: STM32H743VIT6
- Interface: I2C2 on PB10/PB11 at 400 kHz
- Detected 7-bit address: `0x1E`
- Identification registers (`0x0A` through `0x0C`): `0x48, 0x34, 0x33` (`H43`)

The device acknowledged only at the expected HMC5883L address. Register
identification and configuration readback passed, and I2C transactions returned
`HAL_OK`. During measurement, the status register reported `RDY=1`, `LOCK=0`,
and the mode register remained in continuous mode (`0x00`).

## Normal-range test

The normal measurement test used the widest available range:

- `CONFIG_A = 0x70`
- `CONFIG_B = 0xE0`
- `MODE = 0x00`
- Range: +/-8.1 G (230 LSB/Gauss)

Observed Z-axis bytes were persistently `0xF0, 0x00`, which parse as signed
16-bit value `-4096`. For the bounded 20-frame range test:

- `overflow_axes = 0x04` (Z axis)
- `valid_count = 0`
- `overflow_count = 20`

`-4096` is the HMC5883L overflow/saturation code and is not a valid magnetic
measurement. Firmware therefore rejected every affected frame instead of
substituting zero or publishing partial X/Y-only data.

## Built-in self-test

Positive-bias result:

- `positive_avg = [66, -134, -4096]`
- `valid_count = 5`
- `axis_pass_mask = 0x00`

Negative-bias result:

- `negative_avg = [242, 233, -4096]`
- `valid_count = 5`
- `axis_pass_mask = 0x00`

The Z channel remained at the overflow code in normal measurements and in both
self-test directions. The measured axis responses did not satisfy the firmware's
self-test acceptance criteria.

## Environmental checks

The following checks were performed to rule out an obvious external field or
installation effect:

- Moved the soldering iron, magnet, screwdriver, and power wiring away.
- Moved the module away from the STM32 board and USB connection.
- Rotated the module through multiple orientations.
- Repeated observations with the external items removed.

The Z result remained fixed at `-4096` throughout these checks.

## Verdict

Firmware verdict:

- `HMC5883L AXIS TEST: FAIL_SELF_TEST`
- `reason=SENSOR_OR_MODULE_FAULT`

The tested module fails the required three-axis behavior and must not be used as
a flight-controller magnetometer. The evidence is consistent with a defective Z
channel, a faulty module, or a nonconforming/clone device. Calibration cannot
repair a permanently saturated channel.

Specifically:

- Do not replace `-4096` with zero.
- Do not derive a drone heading from X/Y alone.
- Do not use this H2B-4 runtime implementation as a completed phase on `main`.

## Recommendation

Replace the magnetometer module. Before integrating the replacement:

1. Repeat address and ID identification.
2. Repeat the normal-range measurement test on all three axes.
3. Repeat positive- and negative-bias self-tests.
4. Accept the module only after all three axes produce valid, repeatable results.
5. In the final airframe, mount the magnetometer away from motors, ESCs, and
   high-current power wiring.

This diagnostic branch preserves the H2B-4 implementation and fault evidence for
reference only. It is intentionally not merged into `main`.
