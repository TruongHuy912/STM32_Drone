#include "hmc5883l_app.h"

#include "hmc5883l_port.h"
#include "i2c.h"
#include "usart.h"

#include <stdio.h>

#define HMC5883L_I2C_ADDRESS             0x1EU
#define QMC5883L_I2C_ADDRESS             0x0DU

#define HMC5883L_REG_CONFIG_A            0x00U
#define HMC5883L_REG_CONFIG_B            0x01U
#define HMC5883L_REG_MODE                0x02U
#define HMC5883L_REG_DATA_X_MSB          0x03U
#define HMC5883L_REG_STATUS              0x09U
#define HMC5883L_REG_ID_A                0x0AU
#define HMC5883L_REG_ID_B                0x0BU
#define HMC5883L_REG_ID_C                0x0CU

#define HMC5883L_ID_A_EXPECTED           0x48U
#define HMC5883L_ID_B_EXPECTED           0x34U
#define HMC5883L_ID_C_EXPECTED           0x33U

#define HMC5883L_CONFIG_A_VALUE          0x70U
#define HMC5883L_CONFIG_B_VALUE          0xE0U
#define HMC5883L_MODE_CONTINUOUS         0x00U
#define HMC5883L_MODE_SINGLE             0x01U
#define HMC5883L_MODE_IDLE               0x03U
#define HMC5883L_CONFIG_A_POSITIVE_BIAS  0x71U
#define HMC5883L_CONFIG_A_NEGATIVE_BIAS  0x72U
#define HMC5883L_CONFIG_B_SELF_TEST      0x60U

#define HMC5883L_STATUS_RDY_MASK         0x01U
#define HMC5883L_STATUS_LOCK_MASK        0x02U
#define HMC5883L_OVERFLOW_VALUE          ((int16_t)-4096)
#define HMC5883L_GAIN_LSB_PER_GAUSS      230LL
#define HMC5883L_NT_PER_GAUSS            100000LL

#define HMC5883L_I2C_TIMEOUT_MS          50U
#define HMC5883L_UART_TIMEOUT_MS         25U
#define HMC5883L_DIAG_UART_TIMEOUT_MS    50U
#define HMC5883L_POLL_PERIOD_US       66667U
#define HMC5883L_DIAG_PERIOD_US      1000000U
#define HMC5883L_PRINT_SAMPLE_COUNT       3U
#define HMC5883L_RANGE_SETTLE_MS         150U
#define HMC5883L_RANGE_SAMPLE_TARGET      20U
#define HMC5883L_RANGE_TIMEOUT_US    2500000U
#define HMC5883L_SELF_TEST_TIMEOUT_US   30000U
#define HMC5883L_SELF_TEST_SAMPLE_COUNT    5U
#define HMC5883L_SELF_TEST_MAX_ATTEMPTS    8U
#define HMC5883L_SELF_TEST_MIN_COUNTS     100

#define HMC5883L_AXIS_X_MASK            0x01U
#define HMC5883L_AXIS_Y_MASK            0x02U
#define HMC5883L_AXIS_Z_MASK            0x04U
#define HMC5883L_ALL_AXES_MASK          0x07U

static HMC5883L_PortContext_t hmc5883l_context;
static HMC5883L_Sample_t hmc5883l_sample;
static uint32_t hmc5883l_last_poll_us;
static uint32_t hmc5883l_last_diag_us;
static uint32_t hmc5883l_process_call_count;
static uint32_t hmc5883l_poll_count;
static uint32_t hmc5883l_sample_count;
static uint32_t hmc5883l_read_error_count;
static uint32_t hmc5883l_not_ready_count;
static uint32_t hmc5883l_overflow_count;
static uint32_t hmc5883l_print_count;
static uint32_t hmc5883l_uart_print_count;
static HAL_StatusTypeDef hmc5883l_last_status_result;
static HAL_StatusTypeDef hmc5883l_last_data_result;
static HAL_StatusTypeDef hmc5883l_mode_read_result;
static int16_t hmc5883l_last_raw_x;
static int16_t hmc5883l_last_raw_y;
static int16_t hmc5883l_last_raw_z;
static uint8_t hmc5883l_last_raw_bytes[6];
static uint8_t hmc5883l_last_status;
static uint8_t hmc5883l_mode_value;
static uint8_t hmc5883l_ready;

static void HMC5883L_App_PrintIdentifyPass(const uint8_t id[3]);
static void HMC5883L_App_PrintBadId(const uint8_t id[3]);
static void HMC5883L_App_PrintNoDevice(uint8_t qmc_ack);
static void HMC5883L_App_ReadConfigBestEffort(uint8_t readback[3]);
static void HMC5883L_App_PrintConfigFailure(
    const char *stage,
    HAL_StatusTypeDef result,
    const uint8_t readback[3]);
static int16_t HMC5883L_App_ParseBigEndian(const uint8_t data[2]);
static int32_t HMC5883L_App_RawToNt(int16_t raw);
static uint32_t HMC5883L_App_IntegerSqrt(uint64_t value);
static void HMC5883L_App_PrintSample(const HMC5883L_Sample_t *sample);
static void HMC5883L_App_PrintDiagnostic(uint32_t now_us);
static HAL_StatusTypeDef HMC5883L_App_ConfigureAndVerify(
    uint8_t config_a,
    uint8_t config_b,
    uint8_t mode,
    uint8_t readback[3]);
static void HMC5883L_App_SaveRawFrame(
    const uint8_t data[6],
    int16_t raw_x,
    int16_t raw_y,
    int16_t raw_z);
static uint8_t HMC5883L_App_GetOverflowMask(
    int16_t raw_x,
    int16_t raw_y,
    int16_t raw_z);
static void HMC5883L_App_PrintRangeTest(
    const uint8_t readback[3],
    uint8_t overflow_mask,
    uint32_t valid_count,
    uint32_t overflow_count);
static HAL_StatusTypeDef HMC5883L_App_ReadSingleMeasurement(
    int16_t *raw_x,
    int16_t *raw_y,
    int16_t *raw_z);
static uint8_t HMC5883L_App_RunBiasTest(
    uint8_t config_a,
    uint8_t positive_bias,
    int16_t average[3]);
static HAL_StatusTypeDef HMC5883L_App_RunAxisTest(void);
static void HMC5883L_App_PrintAxisConclusion(
    int16_t range_z,
    const int16_t positive_average[3],
    const int16_t negative_average[3],
    uint8_t range_axes_valid,
    uint8_t positive_axes_pass,
    uint8_t negative_axes_pass);

HAL_StatusTypeDef HMC5883L_App_Init(void)
{
  uint8_t id[3] = {0U, 0U, 0U};
  uint8_t readback[3] = {0U, 0U, 0U};
  HAL_StatusTypeDef result;
  HAL_StatusTypeDef qmc_status;

  hmc5883l_sample = (HMC5883L_Sample_t){0};
  hmc5883l_last_diag_us = micros();
  hmc5883l_process_call_count = 0U;
  hmc5883l_poll_count = 0U;
  hmc5883l_sample_count = 0U;
  hmc5883l_read_error_count = 0U;
  hmc5883l_not_ready_count = 0U;
  hmc5883l_overflow_count = 0U;
  hmc5883l_print_count = 0U;
  hmc5883l_uart_print_count = 0U;
  hmc5883l_last_status_result = HAL_ERROR;
  hmc5883l_last_data_result = HAL_ERROR;
  hmc5883l_mode_read_result = HAL_ERROR;
  hmc5883l_last_raw_x = 0;
  hmc5883l_last_raw_y = 0;
  hmc5883l_last_raw_z = 0;
  hmc5883l_last_raw_bytes[0] = 0U;
  hmc5883l_last_raw_bytes[1] = 0U;
  hmc5883l_last_raw_bytes[2] = 0U;
  hmc5883l_last_raw_bytes[3] = 0U;
  hmc5883l_last_raw_bytes[4] = 0U;
  hmc5883l_last_raw_bytes[5] = 0U;
  hmc5883l_last_status = 0U;
  hmc5883l_mode_value = 0xFFU;
  hmc5883l_ready = 0U;

  hmc5883l_context.hi2c = &hi2c2;
  hmc5883l_context.address_7bit = HMC5883L_I2C_ADDRESS;
  hmc5883l_context.timeout_ms = HMC5883L_I2C_TIMEOUT_MS;

  result = HMC5883L_Port_IsDeviceReady(&hmc5883l_context,
                                       HMC5883L_I2C_ADDRESS);
  if (result != HAL_OK)
  {
    qmc_status = HMC5883L_Port_IsDeviceReady(&hmc5883l_context,
                                             QMC5883L_I2C_ADDRESS);
    HMC5883L_App_PrintNoDevice((uint8_t)(qmc_status == HAL_OK));
    return result;
  }

  result = HMC5883L_Port_ReadRegisters(
      &hmc5883l_context, HMC5883L_REG_ID_A, id, 3U);
  if ((result != HAL_OK) ||
      (id[0] != HMC5883L_ID_A_EXPECTED) ||
      (id[1] != HMC5883L_ID_B_EXPECTED) ||
      (id[2] != HMC5883L_ID_C_EXPECTED))
  {
    HMC5883L_App_PrintBadId(id);
    return (result == HAL_OK) ? HAL_ERROR : result;
  }
  HMC5883L_App_PrintIdentifyPass(id);

  result = HMC5883L_Port_WriteRegister(
      &hmc5883l_context, HMC5883L_REG_CONFIG_A,
      HMC5883L_CONFIG_A_VALUE);
  if (result != HAL_OK)
  {
    HMC5883L_App_ReadConfigBestEffort(readback);
    HMC5883L_App_PrintConfigFailure("WRITE_CONFIG_A", result, readback);
    return result;
  }

  result = HMC5883L_Port_WriteRegister(
      &hmc5883l_context, HMC5883L_REG_CONFIG_B,
      HMC5883L_CONFIG_B_VALUE);
  if (result != HAL_OK)
  {
    HMC5883L_App_ReadConfigBestEffort(readback);
    HMC5883L_App_PrintConfigFailure("WRITE_CONFIG_B", result, readback);
    return result;
  }

  result = HMC5883L_Port_WriteRegister(
      &hmc5883l_context, HMC5883L_REG_MODE,
      HMC5883L_MODE_CONTINUOUS);
  if (result != HAL_OK)
  {
    HMC5883L_App_ReadConfigBestEffort(readback);
    HMC5883L_App_PrintConfigFailure("WRITE_MODE", result, readback);
    return result;
  }

  result = HMC5883L_Port_ReadRegisters(
      &hmc5883l_context, HMC5883L_REG_CONFIG_A, readback, 3U);
  if ((result != HAL_OK) ||
      (readback[0] != HMC5883L_CONFIG_A_VALUE) ||
      (readback[1] != HMC5883L_CONFIG_B_VALUE) ||
      (readback[2] != HMC5883L_MODE_CONTINUOUS))
  {
    HMC5883L_App_PrintConfigFailure(
        "VERIFY_CONFIG", (result == HAL_OK) ? HAL_ERROR : result,
        readback);
    return (result == HAL_OK) ? HAL_ERROR : result;
  }

  {
    static const char message[] =
        "HMC5883L DATA INIT: PASS, avg=8, odr=15Hz, range=8.1G, "
        "mode=CONTINUOUS\r\n";

    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)(sizeof(message) - 1U),
                            HMC5883L_UART_TIMEOUT_MS);
  }

  result = HMC5883L_App_RunAxisTest();
  if (result != HAL_OK)
  {
    return result;
  }

  hmc5883l_last_poll_us = micros();
  hmc5883l_ready = 1U;
  return HAL_OK;
}

void HMC5883L_App_Process(void)
{
  uint8_t status = hmc5883l_last_status;
  uint8_t data[6];
  int16_t raw_x;
  int16_t raw_y;
  int16_t raw_z;
  uint64_t magnitude_squared;
  uint32_t now_us;
  HAL_StatusTypeDef result;

  hmc5883l_process_call_count++;
  now_us = micros();
  HMC5883L_App_PrintDiagnostic(now_us);

  if (hmc5883l_ready == 0U)
  {
    return;
  }

  if ((uint32_t)(now_us - hmc5883l_last_poll_us) <
      HMC5883L_POLL_PERIOD_US)
  {
    return;
  }

  hmc5883l_last_poll_us = now_us;
  hmc5883l_poll_count++;
  result = HMC5883L_Port_ReadRegisters(
      &hmc5883l_context, HMC5883L_REG_STATUS, &status, 1U);
  hmc5883l_last_status_result = result;
  if (result != HAL_OK)
  {
    hmc5883l_read_error_count++;
    return;
  }
  hmc5883l_last_status = status;
  if ((status & HMC5883L_STATUS_RDY_MASK) == 0U)
  {
    hmc5883l_not_ready_count++;
    return;
  }

  result = HMC5883L_Port_ReadRegisters(
      &hmc5883l_context, HMC5883L_REG_DATA_X_MSB, data, 6U);
  hmc5883l_last_data_result = result;
  if (result != HAL_OK)
  {
    hmc5883l_read_error_count++;
    return;
  }

  raw_x = HMC5883L_App_ParseBigEndian(&data[0]);
  raw_z = HMC5883L_App_ParseBigEndian(&data[2]);
  raw_y = HMC5883L_App_ParseBigEndian(&data[4]);
  HMC5883L_App_SaveRawFrame(data, raw_x, raw_y, raw_z);
  if ((raw_x == HMC5883L_OVERFLOW_VALUE) ||
      (raw_y == HMC5883L_OVERFLOW_VALUE) ||
      (raw_z == HMC5883L_OVERFLOW_VALUE))
  {
    hmc5883l_overflow_count++;
    return;
  }

  hmc5883l_sample.timestamp_us = now_us;
  hmc5883l_sample.raw_x = raw_x;
  hmc5883l_sample.raw_y = raw_y;
  hmc5883l_sample.raw_z = raw_z;
  hmc5883l_sample.magnetic_nt_x = HMC5883L_App_RawToNt(raw_x);
  hmc5883l_sample.magnetic_nt_y = HMC5883L_App_RawToNt(raw_y);
  hmc5883l_sample.magnetic_nt_z = HMC5883L_App_RawToNt(raw_z);
  magnitude_squared =
      (uint64_t)((int64_t)hmc5883l_sample.magnetic_nt_x *
                 hmc5883l_sample.magnetic_nt_x) +
      (uint64_t)((int64_t)hmc5883l_sample.magnetic_nt_y *
                 hmc5883l_sample.magnetic_nt_y) +
      (uint64_t)((int64_t)hmc5883l_sample.magnetic_nt_z *
                 hmc5883l_sample.magnetic_nt_z);
  hmc5883l_sample.magnitude_nt =
      HMC5883L_App_IntegerSqrt(magnitude_squared);
  hmc5883l_sample.status =
      (uint8_t)(status & (HMC5883L_STATUS_RDY_MASK |
                          HMC5883L_STATUS_LOCK_MASK));
  hmc5883l_sample.valid = 1U;

  hmc5883l_sample_count++;
  hmc5883l_print_count++;
  if (hmc5883l_print_count >= HMC5883L_PRINT_SAMPLE_COUNT)
  {
    hmc5883l_print_count = 0U;
    hmc5883l_uart_print_count++;
    HMC5883L_App_PrintSample(&hmc5883l_sample);
  }
}

static void HMC5883L_App_PrintIdentifyPass(const uint8_t id[3])
{
  char message[96];
  int length;

  length = snprintf(message, sizeof(message),
                    "HMC5883L IDENTIFY: PASS, address=0x1E, "
                    "id=[0x%02X,0x%02X,0x%02X]\r\n",
                    (unsigned int)id[0], (unsigned int)id[1],
                    (unsigned int)id[2]);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_UART_TIMEOUT_MS);
  }
}

static void HMC5883L_App_PrintBadId(const uint8_t id[3])
{
  char message[112];
  int length;

  length = snprintf(message, sizeof(message),
                    "HMC5883L IDENTIFY: FAIL, address=0x1E, "
                    "id=[0x%02X,0x%02X,0x%02X], reason=BAD_ID\r\n",
                    (unsigned int)id[0], (unsigned int)id[1],
                    (unsigned int)id[2]);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_UART_TIMEOUT_MS);
  }
}

static void HMC5883L_App_PrintNoDevice(uint8_t qmc_ack)
{
  char message[128];
  const char *reason = "NO_DEVICE";
  int length;

  if (qmc_ack != 0U)
  {
    reason = "POSSIBLE_QMC5883L";
  }

  length = snprintf(message, sizeof(message),
                    "HMC5883L IDENTIFY: FAIL, hmc_ack=0, "
                    "qmc_address_ack=%u, reason=%s\r\n",
                    (unsigned int)qmc_ack, reason);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_UART_TIMEOUT_MS);
  }
}

static void HMC5883L_App_ReadConfigBestEffort(uint8_t readback[3])
{
  (void)HMC5883L_Port_ReadRegisters(
      &hmc5883l_context, HMC5883L_REG_CONFIG_A, readback, 3U);
}

static void HMC5883L_App_PrintConfigFailure(
    const char *stage,
    HAL_StatusTypeDef result,
    const uint8_t readback[3])
{
  char message[144];
  int length;

  length = snprintf(message, sizeof(message),
                    "HMC5883L DATA INIT: FAIL, stage=%s, result=%u, "
                    "readback=[0x%02X,0x%02X,0x%02X]\r\n",
                    stage, (unsigned int)result,
                    (unsigned int)readback[0],
                    (unsigned int)readback[1],
                    (unsigned int)readback[2]);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_UART_TIMEOUT_MS);
  }
}

static int16_t HMC5883L_App_ParseBigEndian(const uint8_t data[2])
{
  return (int16_t)(((uint16_t)data[0] << 8U) | data[1]);
}

static int32_t HMC5883L_App_RawToNt(int16_t raw)
{
  return (int32_t)(((int64_t)raw * HMC5883L_NT_PER_GAUSS) /
                   HMC5883L_GAIN_LSB_PER_GAUSS);
}

static uint32_t HMC5883L_App_IntegerSqrt(uint64_t value)
{
  uint64_t result = 0U;
  uint64_t bit = UINT64_C(1) << 62U;

  while (bit > value)
  {
    bit >>= 2U;
  }

  while (bit != 0U)
  {
    if (value >= (result + bit))
    {
      value -= result + bit;
      result = (result >> 1U) + bit;
    }
    else
    {
      result >>= 1U;
    }
    bit >>= 2U;
  }

  return (uint32_t)result;
}

static void HMC5883L_App_PrintSample(const HMC5883L_Sample_t *sample)
{
  char message[192];
  int length;

  length = snprintf(
      message, sizeof(message),
      "HMC5883L DATA: t_us=%lu, raw=[%d,%d,%d], mag_nt=[%ld,%ld,%ld], "
      "magnitude_nt=%lu, status=0x%02X\r\n",
      (unsigned long)sample->timestamp_us,
      (int)sample->raw_x, (int)sample->raw_y, (int)sample->raw_z,
      (long)sample->magnetic_nt_x, (long)sample->magnetic_nt_y,
      (long)sample->magnetic_nt_z,
      (unsigned long)sample->magnitude_nt,
      (unsigned int)sample->status);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_UART_TIMEOUT_MS);
  }
}

static void HMC5883L_App_PrintDiagnostic(uint32_t now_us)
{
  char message[448];
  uint8_t mode_value = hmc5883l_mode_value;
  int length;

  if ((uint32_t)(now_us - hmc5883l_last_diag_us) <
      HMC5883L_DIAG_PERIOD_US)
  {
    return;
  }

  hmc5883l_last_diag_us = now_us;
  hmc5883l_mode_read_result = HMC5883L_Port_ReadRegisters(
      &hmc5883l_context, HMC5883L_REG_MODE, &mode_value, 1U);
  if (hmc5883l_mode_read_result == HAL_OK)
  {
    hmc5883l_mode_value = mode_value;
  }

  length = snprintf(
      message, sizeof(message),
      "HMC5883L DIAG: state=%u, process_calls=%lu, poll_count=%lu, "
      "status_result=%u, status=0x%02X, rdy=%u, lock=%u, "
      "data_result=%u, raw_bytes=[0x%02X,0x%02X,0x%02X,0x%02X,0x%02X,0x%02X], "
      "raw=[%d,%d,%d], sample_count=%lu, "
      "not_ready_count=%lu, read_error_count=%lu, overflow_count=%lu, "
      "uart_print_count=%lu, mode_read_result=%u, mode_value=0x%02X\r\n",
      (unsigned int)hmc5883l_ready,
      (unsigned long)hmc5883l_process_call_count,
      (unsigned long)hmc5883l_poll_count,
      (unsigned int)hmc5883l_last_status_result,
      (unsigned int)hmc5883l_last_status,
      (unsigned int)((hmc5883l_last_status &
                      HMC5883L_STATUS_RDY_MASK) != 0U),
      (unsigned int)((hmc5883l_last_status &
                      HMC5883L_STATUS_LOCK_MASK) != 0U),
      (unsigned int)hmc5883l_last_data_result,
      (unsigned int)hmc5883l_last_raw_bytes[0],
      (unsigned int)hmc5883l_last_raw_bytes[1],
      (unsigned int)hmc5883l_last_raw_bytes[2],
      (unsigned int)hmc5883l_last_raw_bytes[3],
      (unsigned int)hmc5883l_last_raw_bytes[4],
      (unsigned int)hmc5883l_last_raw_bytes[5],
      (int)hmc5883l_last_raw_x, (int)hmc5883l_last_raw_y,
      (int)hmc5883l_last_raw_z,
      (unsigned long)hmc5883l_sample_count,
      (unsigned long)hmc5883l_not_ready_count,
      (unsigned long)hmc5883l_read_error_count,
      (unsigned long)hmc5883l_overflow_count,
      (unsigned long)hmc5883l_uart_print_count,
      (unsigned int)hmc5883l_mode_read_result,
      (unsigned int)hmc5883l_mode_value);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_DIAG_UART_TIMEOUT_MS);
  }
}

static HAL_StatusTypeDef HMC5883L_App_ConfigureAndVerify(
    uint8_t config_a,
    uint8_t config_b,
    uint8_t mode,
    uint8_t readback[3])
{
  HAL_StatusTypeDef result;

  result = HMC5883L_Port_WriteRegister(
      &hmc5883l_context, HMC5883L_REG_CONFIG_A, config_a);
  if (result == HAL_OK)
  {
    result = HMC5883L_Port_WriteRegister(
        &hmc5883l_context, HMC5883L_REG_CONFIG_B, config_b);
  }
  if (result == HAL_OK)
  {
    result = HMC5883L_Port_WriteRegister(
        &hmc5883l_context, HMC5883L_REG_MODE, mode);
  }
  if (result == HAL_OK)
  {
    result = HMC5883L_Port_ReadRegisters(
        &hmc5883l_context, HMC5883L_REG_CONFIG_A, readback, 3U);
  }
  if ((result == HAL_OK) &&
      ((readback[0] != config_a) || (readback[1] != config_b) ||
       (readback[2] != mode)))
  {
    result = HAL_ERROR;
  }

  return result;
}

static void HMC5883L_App_SaveRawFrame(
    const uint8_t data[6],
    int16_t raw_x,
    int16_t raw_y,
    int16_t raw_z)
{
  uint8_t index;

  for (index = 0U; index < 6U; index++)
  {
    hmc5883l_last_raw_bytes[index] = data[index];
  }
  hmc5883l_last_raw_x = raw_x;
  hmc5883l_last_raw_y = raw_y;
  hmc5883l_last_raw_z = raw_z;
}

static uint8_t HMC5883L_App_GetOverflowMask(
    int16_t raw_x,
    int16_t raw_y,
    int16_t raw_z)
{
  uint8_t mask = 0U;

  if (raw_x == HMC5883L_OVERFLOW_VALUE)
  {
    mask |= HMC5883L_AXIS_X_MASK;
  }
  if (raw_y == HMC5883L_OVERFLOW_VALUE)
  {
    mask |= HMC5883L_AXIS_Y_MASK;
  }
  if (raw_z == HMC5883L_OVERFLOW_VALUE)
  {
    mask |= HMC5883L_AXIS_Z_MASK;
  }

  return mask;
}

static void HMC5883L_App_PrintRangeTest(
    const uint8_t readback[3],
    uint8_t overflow_mask,
    uint32_t valid_count,
    uint32_t overflow_count)
{
  char message[256];
  int length;

  length = snprintf(
      message, sizeof(message),
      "HMC RANGE TEST: config=[0x%02X,0x%02X,0x%02X], "
      "raw_bytes=[0x%02X,0x%02X,0x%02X,0x%02X,0x%02X,0x%02X], "
      "raw=[%d,%d,%d], overflow_axes=0x%02X, valid_count=%lu, "
      "overflow_count=%lu\r\n",
      (unsigned int)readback[0], (unsigned int)readback[1],
      (unsigned int)readback[2],
      (unsigned int)hmc5883l_last_raw_bytes[0],
      (unsigned int)hmc5883l_last_raw_bytes[1],
      (unsigned int)hmc5883l_last_raw_bytes[2],
      (unsigned int)hmc5883l_last_raw_bytes[3],
      (unsigned int)hmc5883l_last_raw_bytes[4],
      (unsigned int)hmc5883l_last_raw_bytes[5],
      (int)hmc5883l_last_raw_x, (int)hmc5883l_last_raw_y,
      (int)hmc5883l_last_raw_z, (unsigned int)overflow_mask,
      (unsigned long)valid_count, (unsigned long)overflow_count);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_DIAG_UART_TIMEOUT_MS);
  }
}

static HAL_StatusTypeDef HMC5883L_App_ReadSingleMeasurement(
    int16_t *raw_x,
    int16_t *raw_y,
    int16_t *raw_z)
{
  uint8_t data[6];
  uint8_t status = hmc5883l_last_status;
  uint32_t start_us;
  HAL_StatusTypeDef result;

  result = HMC5883L_Port_WriteRegister(
      &hmc5883l_context, HMC5883L_REG_MODE, HMC5883L_MODE_SINGLE);
  if (result != HAL_OK)
  {
    return result;
  }

  start_us = micros();
  do
  {
    result = HMC5883L_Port_ReadRegisters(
        &hmc5883l_context, HMC5883L_REG_STATUS, &status, 1U);
    hmc5883l_last_status_result = result;
    if (result != HAL_OK)
    {
      return result;
    }
    hmc5883l_last_status = status;

    if ((status & HMC5883L_STATUS_RDY_MASK) != 0U)
    {
      result = HMC5883L_Port_ReadRegisters(
          &hmc5883l_context, HMC5883L_REG_DATA_X_MSB, data, 6U);
      hmc5883l_last_data_result = result;
      if (result != HAL_OK)
      {
        return result;
      }

      *raw_x = HMC5883L_App_ParseBigEndian(&data[0]);
      *raw_z = HMC5883L_App_ParseBigEndian(&data[2]);
      *raw_y = HMC5883L_App_ParseBigEndian(&data[4]);
      HMC5883L_App_SaveRawFrame(data, *raw_x, *raw_y, *raw_z);
      return HAL_OK;
    }

    HAL_Delay(1U);
  } while ((uint32_t)(micros() - start_us) <
           HMC5883L_SELF_TEST_TIMEOUT_US);

  return HAL_TIMEOUT;
}

static uint8_t HMC5883L_App_RunBiasTest(
    uint8_t config_a,
    uint8_t positive_bias,
    int16_t average[3])
{
  int32_t sum_x = 0;
  int32_t sum_y = 0;
  int32_t sum_z = 0;
  int16_t raw_x = 0;
  int16_t raw_y = 0;
  int16_t raw_z = 0;
  uint8_t readback[3] = {0U, 0U, 0U};
  uint8_t axes_valid = HMC5883L_ALL_AXES_MASK;
  uint8_t axes_pass = 0U;
  uint8_t discard_pending = 1U;
  uint8_t valid_count = 0U;
  uint8_t attempts = 0U;
  HAL_StatusTypeDef result;
  char message[144];
  const char *label = positive_bias ? "positive" : "negative";
  int length;

  result = HMC5883L_Port_WriteRegister(
      &hmc5883l_context, HMC5883L_REG_MODE, HMC5883L_MODE_IDLE);
  if (result == HAL_OK)
  {
    result = HMC5883L_Port_WriteRegister(
        &hmc5883l_context, HMC5883L_REG_CONFIG_A, config_a);
  }
  if (result == HAL_OK)
  {
    result = HMC5883L_Port_WriteRegister(
        &hmc5883l_context, HMC5883L_REG_CONFIG_B,
        HMC5883L_CONFIG_B_SELF_TEST);
  }
  if (result == HAL_OK)
  {
    result = HMC5883L_Port_ReadRegisters(
        &hmc5883l_context, HMC5883L_REG_CONFIG_A, readback, 3U);
  }
  if ((result == HAL_OK) &&
      ((readback[0] != config_a) ||
       (readback[1] != HMC5883L_CONFIG_B_SELF_TEST) ||
       ((readback[2] & 0x03U) != HMC5883L_MODE_IDLE)))
  {
    result = HAL_ERROR;
  }

  while ((result == HAL_OK) &&
         (valid_count < HMC5883L_SELF_TEST_SAMPLE_COUNT) &&
         (attempts < HMC5883L_SELF_TEST_MAX_ATTEMPTS))
  {
    uint8_t overflow_mask;

    attempts++;
    result = HMC5883L_App_ReadSingleMeasurement(
        &raw_x, &raw_y, &raw_z);
    if (result != HAL_OK)
    {
      hmc5883l_read_error_count++;
      result = HAL_OK;
      continue;
    }

    if (discard_pending != 0U)
    {
      discard_pending = 0U;
      continue;
    }

    overflow_mask = HMC5883L_App_GetOverflowMask(raw_x, raw_y, raw_z);
    axes_valid &= (uint8_t)~overflow_mask;
    if (overflow_mask != 0U)
    {
      hmc5883l_overflow_count++;
    }

    sum_x += raw_x;
    sum_y += raw_y;
    sum_z += raw_z;
    valid_count++;
  }

  if (valid_count > 0U)
  {
    average[0] = (int16_t)(sum_x / valid_count);
    average[1] = (int16_t)(sum_y / valid_count);
    average[2] = (int16_t)(sum_z / valid_count);
  }

  if (valid_count == HMC5883L_SELF_TEST_SAMPLE_COUNT)
  {
    if (((axes_valid & HMC5883L_AXIS_X_MASK) != 0U) &&
        ((positive_bias && (average[0] > HMC5883L_SELF_TEST_MIN_COUNTS)) ||
         (!positive_bias && (average[0] < -HMC5883L_SELF_TEST_MIN_COUNTS))))
    {
      axes_pass |= HMC5883L_AXIS_X_MASK;
    }
    if (((axes_valid & HMC5883L_AXIS_Y_MASK) != 0U) &&
        ((positive_bias && (average[1] > HMC5883L_SELF_TEST_MIN_COUNTS)) ||
         (!positive_bias && (average[1] < -HMC5883L_SELF_TEST_MIN_COUNTS))))
    {
      axes_pass |= HMC5883L_AXIS_Y_MASK;
    }
    if (((axes_valid & HMC5883L_AXIS_Z_MASK) != 0U) &&
        ((positive_bias && (average[2] > HMC5883L_SELF_TEST_MIN_COUNTS)) ||
         (!positive_bias && (average[2] < -HMC5883L_SELF_TEST_MIN_COUNTS))))
    {
      axes_pass |= HMC5883L_AXIS_Z_MASK;
    }
  }

  length = snprintf(message, sizeof(message),
                    "HMC5883L SELF TEST: %s_avg=[%d,%d,%d], "
                    "valid_count=%u, axis_pass_mask=0x%02X\r\n",
                    label, (int)average[0], (int)average[1],
                    (int)average[2], (unsigned int)valid_count,
                    (unsigned int)axes_pass);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_DIAG_UART_TIMEOUT_MS);
  }

  return axes_pass;
}

static HAL_StatusTypeDef HMC5883L_App_RunAxisTest(void)
{
  uint8_t readback[3] = {0U, 0U, 0U};
  uint8_t data[6];
  uint8_t status = 0U;
  uint8_t range_axes_valid = 0U;
  uint8_t last_overflow_mask = 0U;
  uint8_t positive_axes_pass;
  uint8_t negative_axes_pass;
  int16_t raw_x;
  int16_t raw_y;
  int16_t raw_z = 0;
  int16_t range_z = HMC5883L_OVERFLOW_VALUE;
  int16_t positive_average[3] = {0, 0, 0};
  int16_t negative_average[3] = {0, 0, 0};
  uint32_t range_sample_count = 0U;
  uint32_t range_valid_count = 0U;
  uint32_t range_overflow_count = 0U;
  uint32_t start_us;
  uint32_t last_report_us;
  HAL_StatusTypeDef result;

  result = HMC5883L_App_ConfigureAndVerify(
      HMC5883L_CONFIG_A_VALUE, HMC5883L_CONFIG_B_VALUE,
      HMC5883L_MODE_CONTINUOUS, readback);
  if (result != HAL_OK)
  {
    HMC5883L_App_PrintConfigFailure("VERIFY_CONFIG", result, readback);
    return result;
  }

  HAL_Delay(HMC5883L_RANGE_SETTLE_MS);
  start_us = micros();
  last_report_us = start_us;
  while ((range_sample_count < HMC5883L_RANGE_SAMPLE_TARGET) &&
         ((uint32_t)(micros() - start_us) < HMC5883L_RANGE_TIMEOUT_US))
  {
    result = HMC5883L_Port_ReadRegisters(
        &hmc5883l_context, HMC5883L_REG_STATUS, &status, 1U);
    hmc5883l_last_status_result = result;
    if (result == HAL_OK)
    {
      hmc5883l_last_status = status;
      if ((status & HMC5883L_STATUS_RDY_MASK) != 0U)
      {
        result = HMC5883L_Port_ReadRegisters(
            &hmc5883l_context, HMC5883L_REG_DATA_X_MSB, data, 6U);
        hmc5883l_last_data_result = result;
        if (result == HAL_OK)
        {
          raw_x = HMC5883L_App_ParseBigEndian(&data[0]);
          raw_z = HMC5883L_App_ParseBigEndian(&data[2]);
          raw_y = HMC5883L_App_ParseBigEndian(&data[4]);
          HMC5883L_App_SaveRawFrame(data, raw_x, raw_y, raw_z);
          last_overflow_mask = HMC5883L_App_GetOverflowMask(
              raw_x, raw_y, raw_z);
          range_axes_valid |=
              (uint8_t)(HMC5883L_ALL_AXES_MASK & ~last_overflow_mask);
          if (raw_z != HMC5883L_OVERFLOW_VALUE)
          {
            range_z = raw_z;
          }
          if (last_overflow_mask == 0U)
          {
            range_valid_count++;
          }
          else
          {
            range_overflow_count++;
            hmc5883l_overflow_count++;
          }
          range_sample_count++;
        }
        else
        {
          hmc5883l_read_error_count++;
        }
      }
      else
      {
        hmc5883l_not_ready_count++;
      }
    }
    else
    {
      hmc5883l_read_error_count++;
    }

    if ((uint32_t)(micros() - last_report_us) >=
        HMC5883L_DIAG_PERIOD_US)
    {
      last_report_us = micros();
      HMC5883L_App_PrintRangeTest(
          readback, last_overflow_mask, range_valid_count,
          range_overflow_count);
    }
    HAL_Delay(1U);
  }

  HMC5883L_App_PrintRangeTest(
      readback, last_overflow_mask, range_valid_count,
      range_overflow_count);

  positive_axes_pass = HMC5883L_App_RunBiasTest(
      HMC5883L_CONFIG_A_POSITIVE_BIAS, 1U, positive_average);
  negative_axes_pass = HMC5883L_App_RunBiasTest(
      HMC5883L_CONFIG_A_NEGATIVE_BIAS, 0U, negative_average);

  HMC5883L_App_PrintAxisConclusion(
      range_z, positive_average, negative_average, range_axes_valid,
      positive_axes_pass, negative_axes_pass);

  readback[0] = 0U;
  readback[1] = 0U;
  readback[2] = 0U;
  result = HMC5883L_App_ConfigureAndVerify(
      HMC5883L_CONFIG_A_VALUE, HMC5883L_CONFIG_B_VALUE,
      HMC5883L_MODE_CONTINUOUS, readback);
  if (result != HAL_OK)
  {
    HMC5883L_App_PrintConfigFailure("RESTORE_CONFIG", result, readback);
  }

  return result;
}

static void HMC5883L_App_PrintAxisConclusion(
    int16_t range_z,
    const int16_t positive_average[3],
    const int16_t negative_average[3],
    uint8_t range_axes_valid,
    uint8_t positive_axes_pass,
    uint8_t negative_axes_pass)
{
  char message[192];
  uint8_t self_test_axes_pass =
      (uint8_t)(positive_axes_pass & negative_axes_pass);
  int length;

  if ((range_axes_valid == HMC5883L_ALL_AXES_MASK) &&
      (self_test_axes_pass == HMC5883L_ALL_AXES_MASK))
  {
    length = snprintf(
        message, sizeof(message),
        "HMC5883L AXIS TEST: PASS, range_z=%d, positive=[%d,%d,%d], "
        "negative=[%d,%d,%d]\r\n",
        (int)range_z,
        (int)positive_average[0], (int)positive_average[1],
        (int)positive_average[2],
        (int)negative_average[0], (int)negative_average[1],
        (int)negative_average[2]);
  }
  else if (self_test_axes_pass == 0U)
  {
    length = snprintf(message, sizeof(message),
                      "HMC5883L AXIS TEST: FAIL_SELF_TEST, "
                      "reason=SENSOR_OR_MODULE_FAULT\r\n");
  }
  else if (((range_axes_valid & HMC5883L_AXIS_Z_MASK) == 0U) &&
           (self_test_axes_pass == HMC5883L_ALL_AXES_MASK))
  {
    length = snprintf(message, sizeof(message),
                      "HMC5883L AXIS TEST: FAIL_NORMAL_ONLY, "
                      "reason=EXTERNAL_OR_OFFSET_SATURATION\r\n");
  }
  else if (((range_axes_valid & HMC5883L_AXIS_Z_MASK) == 0U) &&
           ((self_test_axes_pass & HMC5883L_AXIS_Z_MASK) == 0U))
  {
    length = snprintf(message, sizeof(message),
                      "HMC5883L AXIS TEST: FAIL_Z_CHANNEL, "
                      "reason=Z_AXIS_HARDWARE_OR_CLONE_FAULT\r\n");
  }
  else
  {
    length = snprintf(message, sizeof(message),
                      "HMC5883L AXIS TEST: FAIL_SELF_TEST, "
                      "reason=SENSOR_OR_MODULE_FAULT\r\n");
  }

  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            HMC5883L_DIAG_UART_TIMEOUT_MS);
  }
}
