# H3B-2 single-motor bench test

## Phạm vi và cảnh báo

H3B-2 chỉ dùng để kiểm tra từng motor trên bench. Đây không phải flight
control, mixer, arming, ESC calibration hay throttle mapping.

Luôn tháo toàn bộ cánh quạt trước khi cấp nguồn ESC. Cố định frame và motor,
dùng USB-TTL logic 3.3 V, và ngắt LiPo ngay nếu motor rung kéo dài, ESC/motor
nóng nhanh hoặc STM32 reset.

Firmware không tự chạy motor khi boot hoặc sau reset. Giá trị idle và mọi
đường dừng là 1000 us.

## Cấu hình H3B-2

| Thành phần | Cấu hình |
| --- | --- |
| PWM timer | TIM4, 50 Hz |
| Motor 1 | PD12 / TIM4 CH1 |
| Motor 2 | PD13 / TIM4 CH2 |
| Motor 3 | PD14 / TIM4 CH3 |
| Motor 4 | PD15 / TIM4 CH4 |
| Idle/safe pulse | 1000 us |
| Test pulse hợp lệ | 1020–1100 us |
| Test duration hợp lệ | 100–2000 ms |
| Số motor hoạt động | Tối đa một motor |

Threshold quan sát trong phần Hardware Results không thay đổi giới hạn command
1020–1100 us của firmware.

## Kết nối USART1 debug/command

| USB-TTL | STM32H743 |
| --- | --- |
| RX | PA9 / USART1_TX |
| TX | PA10 / USART1_RX |
| GND | GND |

USART1 dùng 115200 baud, 8 data bits, no parity, 1 stop bit. Không nối nguồn
5 V từ USB-TTL vào board.

Chỉ một chương trình được sở hữu COM port. Đóng PuTTY trước khi dùng
`tools/ibus_monitor.py`.

## Safety gates

Firmware kiểm tra lại toàn bộ gate trước khi thay đổi CCR:

- ESC PWM state phải là SAFE;
- `started_mask` phải bằng `0x0F`;
- iBUS phải valid, stream alive và frame age không quá 50 ms lúc nhận RUN;
- CH3 throttle không quá 1050;
- CH5 và CH6 phải ít nhất 1900;
- CH3, CH5 và CH6 phải nằm trong range hợp lý 800–2200;
- motor phải từ 1 đến 4;
- pulse phải từ 1020 đến 1100 us;
- duration phải từ 100 đến 2000 ms;
- state phải là READY và không có motor khác đang RUNNING.

Trong lúc RUNNING, firmware đưa toàn bộ output về 1000 us khi:

- hết duration;
- nhận `MTEST STOP`;
- nhận emergency byte `!`;
- CH3 vượt 1050;
- CH5 hoặc CH6 giảm dưới ngưỡng abort 1700;
- iBUS invalid, stream mất hoặc frame age đạt 100 ms;
- ESC không còn SAFE hoặc mask khác `0x0F`;
- CCR không còn đúng cấu hình một-motor;
- parser/UART gặp lỗi nghiêm trọng.

FAULT nghiêm trọng được latch đến lần reset kế tiếp; không có bypass từ GUI.
Firmware vẫn là lớp safety chính nếu GUI, USB hoặc PC ngừng hoạt động.

## Command

```text
MTEST STATUS
MTEST RUN <motor> <pulse_us> <duration_ms>
MTEST STOP
!
```

Ví dụ bắt đầu ở mức thấp, thời gian ngắn:

```text
MTEST RUN 1 1020 100
```

Command sai bị reject, không clamp. Không gửi RUN thứ hai khi test đang chạy.
Không dùng script sweep, run-all hoặc tự động chuyển motor.

Configurator hiển thị confirmation dialog và chỉ gửi RUN sau khi toàn bộ GUI
checklist PASS. GUI không thay thế kiểm tra an toàn trong firmware.

## Quy trình bench test

1. Tháo toàn bộ cánh quạt và cố định frame.
2. Bật transmitter/receiver và xác nhận iBUS LINK OK.
3. Đưa CH3 xuống thấp, sau đó enable CH5 và CH6.
4. Xác nhận ESC SAFE, `started_mask=0x0F` và Motor Test READY.
5. Bắt đầu từng motor riêng ở 1020 us / 100 ms.
6. Tăng từng bước nhỏ trong range cho phép nếu cần xác định threshold.
7. Xác nhận output trở lại 1000 us trước khi kiểm tra motor kế tiếp.
8. Dùng STOP hoặc `!` ngay khi có hành vi bất thường.

## Hardware Results

Threshold quay lần đầu được người dùng đo và xác nhận:

| Motor | Output | First-spin threshold | Kết quả |
| --- | --- | ---: | --- |
| MOTOR1 | PD12 / TIM4 CH1 | 1060 us | PASS |
| MOTOR2 | PD13 / TIM4 CH2 | 1060 us | PASS |
| MOTOR3 | PD14 / TIM4 CH3 | 1060 us | PASS |
| MOTOR4 | PD15 / TIM4 CH4 | 1060 us | PASS |

- Idle: 1000 us.
- PWM frequency trong H3B-2: 50 Hz.
- Cả bốn bài kiểm tra ESC/motor: PASS.
- Motor Test không còn báo `INTERNAL_ERROR` trong hardware test đã xác nhận.

### Hardware/software verification matrix

| Hạng mục | Tiêu chí đã kiểm tra | Kết quả |
| --- | --- | --- |
| Boot safety | Không motor tự chạy; bốn output ở 1000 us | PASS |
| Single motor | Chỉ motor được chọn nhận pulse lớn hơn idle | PASS |
| Timeout | Hết duration đưa tất cả output về 1000 us | PASS |
| STOP | `MTEST STOP` dừng motor và trả safe | PASS |
| Emergency stop | Byte `!` dừng motor và trả safe | PASS |
| CH5 gate | CH5 OFF dừng motor | PASS |
| CH6 gate | CH6 OFF dừng motor | PASS |
| Throttle gate | Throttle high dừng motor | PASS |
| Transmitter off | Mất điều kiện receiver dừng motor | PASS |
| Correct channel | Motor 1–4 điều khiển đúng PD12–PD15 | PASS |
| MCU stability | STM32 không reset trong các test | PASS |
| Thermal observation | ESC/motor không nóng nhanh | PASS |
| BMI270 regression | BMI270 tiếp tục hoạt động | PASS |
| BMP388 regression | BMP388 tiếp tục hoạt động | PASS |
| iBUS regression | iBUS và telemetry tiếp tục hoạt động | PASS |
| H1 regression | Heartbeat và TIM2 `micros()` tiếp tục hoạt động | PASS |
| Configurator | GUI và COM6 telemetry hoạt động | PASS |

## Kết luận H3B-2

H3B-2 single-motor bench test đã hardware/software PASS theo kết quả người dùng
xác nhận. Phạm vi hoàn thành dừng ở single-motor bench testing; chưa triển khai
H3B-3 runtime motor-control code, mixer, flight arming hay throttle mapping.
