#include "bmi270_app.h"

#include "bmi270_port.h"
#include "spi.h"
#include "usart.h"

#include <stdio.h>

#define BMI270_APP_SPI_TIMEOUT_MS       50U
#define BMI270_APP_UART_TIMEOUT_MS      25U
#define BMI270_APP_SAMPLE_PERIOD_US   5000U
#define BMI270_APP_PRINT_SAMPLE_COUNT   20U

static struct bmi2_dev bmi270_device;
static struct bmi270_port_context bmi270_context;
static BMI270_Sample_t bmi270_sample;
static uint32_t bmi270_last_sample_us;
static uint32_t bmi270_read_ok_count;
static uint32_t bmi270_read_error_count;
static uint32_t bmi270_not_ready_count;
static uint32_t bmi270_print_count;
static uint8_t bmi270_ready;

static void BMI270_App_PrintApiInit(int8_t result, uint8_t internal_status);
static void BMI270_App_PrintDataInitFailure(const char *stage, int8_t result);
static uint8_t BMI270_App_ConfigMatches(
    const struct bmi2_sens_config config[2]);
static int32_t BMI270_App_AccelToMg(int16_t raw);
static int32_t BMI270_App_GyroToMdps(int16_t raw);
static void BMI270_App_PrintSample(const BMI270_Sample_t *sample);

int8_t BMI270_App_Init(void)
{
  struct bmi2_sens_config config[2] = {0};
  struct bmi2_sens_config verify_config[2] = {0};
  uint8_t sensor_list[2] = {BMI2_ACCEL, BMI2_GYRO};
  uint8_t internal_status = 0xFFU;
  int8_t result;

  bmi270_ready = 0U;
  bmi270_read_ok_count = 0U;
  bmi270_read_error_count = 0U;
  bmi270_not_ready_count = 0U;
  bmi270_print_count = 0U;

  bmi270_context.spi = &hspi2;
  bmi270_context.cs_port = BMI270_CS_GPIO_Port;
  bmi270_context.cs_pin = BMI270_CS_Pin;
  bmi270_context.timeout_ms = BMI270_APP_SPI_TIMEOUT_MS;

  HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);
  HAL_Delay(10U);

  result = BMI270_Port_Configure(&bmi270_device, &bmi270_context);
  if (result == BMI2_OK)
  {
    result = bmi270_init(&bmi270_device);
  }
  if (result == BMI2_OK)
  {
    result = bmi2_get_internal_status(&internal_status, &bmi270_device);
  }

  BMI270_App_PrintApiInit(result, internal_status);

  if (result != BMI2_OK)
  {
    BMI270_App_PrintDataInitFailure("INIT", result);
    return result;
  }
  if (bmi270_device.chip_id != BMI270_CHIP_ID)
  {
    result = BMI2_E_DEV_NOT_FOUND;
    BMI270_App_PrintDataInitFailure("INIT", result);
    return result;
  }
  if (internal_status != BMI2_INIT_OK)
  {
    result = BMI2_E_CONFIG_LOAD;
    BMI270_App_PrintDataInitFailure("INIT", result);
    return result;
  }

  config[0].type = BMI2_ACCEL;
  config[1].type = BMI2_GYRO;
  result = bmi2_get_sensor_config(config, 2U, &bmi270_device);
  if (result != BMI2_OK)
  {
    BMI270_App_PrintDataInitFailure("GET_CONFIG", result);
    return result;
  }

  config[0].cfg.acc.odr = BMI2_ACC_ODR_200HZ;
  config[0].cfg.acc.range = BMI2_ACC_RANGE_16G;
  config[0].cfg.acc.bwp = BMI2_ACC_NORMAL_AVG4;
  config[0].cfg.acc.filter_perf = BMI2_PERF_OPT_MODE;

  config[1].cfg.gyr.odr = BMI2_GYR_ODR_200HZ;
  config[1].cfg.gyr.range = BMI2_GYR_RANGE_2000;
  config[1].cfg.gyr.bwp = BMI2_GYR_NORMAL_MODE;
  config[1].cfg.gyr.filter_perf = BMI2_PERF_OPT_MODE;
  config[1].cfg.gyr.noise_perf = BMI2_POWER_OPT_MODE;

  result = bmi2_set_sensor_config(config, 2U, &bmi270_device);
  if (result != BMI2_OK)
  {
    BMI270_App_PrintDataInitFailure("SET_CONFIG", result);
    return result;
  }

  result = bmi2_sensor_enable(sensor_list, 2U, &bmi270_device);
  if (result != BMI2_OK)
  {
    BMI270_App_PrintDataInitFailure("ENABLE", result);
    return result;
  }

  verify_config[0].type = BMI2_ACCEL;
  verify_config[1].type = BMI2_GYRO;
  result = bmi2_get_sensor_config(verify_config, 2U, &bmi270_device);
  if (result != BMI2_OK)
  {
    BMI270_App_PrintDataInitFailure("VERIFY_CONFIG", result);
    return result;
  }
  if (BMI270_App_ConfigMatches(verify_config) == 0U)
  {
    result = BMI2_E_INVALID_INPUT;
    BMI270_App_PrintDataInitFailure("VERIFY_CONFIG", result);
    return result;
  }

  {
    static const char message[] =
        "BMI270 DATA INIT: PASS, acc_odr=200, acc_range=16g, "
        "gyr_odr=200, gyr_range=2000dps\r\n";

    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)(sizeof(message) - 1U),
                            BMI270_APP_UART_TIMEOUT_MS);
  }

  bmi270_last_sample_us = micros();
  bmi270_ready = 1U;
  return BMI2_OK;
}

void BMI270_App_Process(void)
{
  struct bmi2_sens_data sensor_data = {0};
  uint32_t now_us;
  int8_t result;

  if (bmi270_ready == 0U)
  {
    return;
  }

  now_us = micros();
  if ((uint32_t)(now_us - bmi270_last_sample_us) <
      BMI270_APP_SAMPLE_PERIOD_US)
  {
    return;
  }

  /* Resume from now rather than running an unbounded catch-up loop. */
  bmi270_last_sample_us = now_us;
  result = bmi2_get_sensor_data(&sensor_data, &bmi270_device);
  if (result != BMI2_OK)
  {
    bmi270_read_error_count++;
    return;
  }

  if ((sensor_data.status & (BMI2_DRDY_ACC | BMI2_DRDY_GYR)) !=
      (BMI2_DRDY_ACC | BMI2_DRDY_GYR))
  {
    bmi270_not_ready_count++;
    return;
  }

  bmi270_sample.timestamp_us = now_us;
  bmi270_sample.acc_raw_x = sensor_data.acc.x;
  bmi270_sample.acc_raw_y = sensor_data.acc.y;
  bmi270_sample.acc_raw_z = sensor_data.acc.z;
  bmi270_sample.gyr_raw_x = sensor_data.gyr.x;
  bmi270_sample.gyr_raw_y = sensor_data.gyr.y;
  bmi270_sample.gyr_raw_z = sensor_data.gyr.z;
  bmi270_sample.acc_mg_x = BMI270_App_AccelToMg(sensor_data.acc.x);
  bmi270_sample.acc_mg_y = BMI270_App_AccelToMg(sensor_data.acc.y);
  bmi270_sample.acc_mg_z = BMI270_App_AccelToMg(sensor_data.acc.z);
  bmi270_sample.gyr_mdps_x = BMI270_App_GyroToMdps(sensor_data.gyr.x);
  bmi270_sample.gyr_mdps_y = BMI270_App_GyroToMdps(sensor_data.gyr.y);
  bmi270_sample.gyr_mdps_z = BMI270_App_GyroToMdps(sensor_data.gyr.z);
  bmi270_sample.status = sensor_data.status;

  bmi270_read_ok_count++;
  bmi270_print_count++;
  if (bmi270_print_count >= BMI270_APP_PRINT_SAMPLE_COUNT)
  {
    bmi270_print_count = 0U;
    BMI270_App_PrintSample(&bmi270_sample);
  }
}

static void BMI270_App_PrintApiInit(int8_t result, uint8_t internal_status)
{
  char message[112];
  const char *state = "FAIL";
  int length;

  if ((result == BMI2_OK) && (bmi270_device.chip_id == BMI270_CHIP_ID) &&
      (internal_status == BMI2_INIT_OK))
  {
    state = "PASS";
  }

  length = snprintf(message, sizeof(message),
                    "BMI270 API INIT: %s, result=%d, chip_id=0x%02X, "
                    "internal_status=0x%02X\r\n",
                    state, (int)result,
                    (unsigned int)bmi270_device.chip_id,
                    (unsigned int)internal_status);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            BMI270_APP_UART_TIMEOUT_MS);
  }
}

static void BMI270_App_PrintDataInitFailure(const char *stage, int8_t result)
{
  char message[80];
  int length;

  length = snprintf(message, sizeof(message),
                    "BMI270 DATA INIT: FAIL, stage=%s, result=%d\r\n",
                    stage, (int)result);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            BMI270_APP_UART_TIMEOUT_MS);
  }
}

static uint8_t BMI270_App_ConfigMatches(
    const struct bmi2_sens_config config[2])
{
  uint8_t accel_matches;
  uint8_t gyro_matches;

  accel_matches = (uint8_t)(
      (config[0].type == BMI2_ACCEL) &&
      (config[0].cfg.acc.odr == BMI2_ACC_ODR_200HZ) &&
      (config[0].cfg.acc.range == BMI2_ACC_RANGE_16G) &&
      (config[0].cfg.acc.bwp == BMI2_ACC_NORMAL_AVG4) &&
      (config[0].cfg.acc.filter_perf == BMI2_PERF_OPT_MODE));

  gyro_matches = (uint8_t)(
      (config[1].type == BMI2_GYRO) &&
      (config[1].cfg.gyr.odr == BMI2_GYR_ODR_200HZ) &&
      (config[1].cfg.gyr.range == BMI2_GYR_RANGE_2000) &&
      (config[1].cfg.gyr.bwp == BMI2_GYR_NORMAL_MODE) &&
      (config[1].cfg.gyr.filter_perf == BMI2_PERF_OPT_MODE) &&
      (config[1].cfg.gyr.noise_perf == BMI2_POWER_OPT_MODE));

  return (uint8_t)(accel_matches && gyro_matches);
}

static int32_t BMI270_App_AccelToMg(int16_t raw)
{
  return (int32_t)(((int64_t)raw * 16000LL) / 32768LL);
}

static int32_t BMI270_App_GyroToMdps(int16_t raw)
{
  return (int32_t)(((int64_t)raw * 2000000LL) / 32768LL);
}

static void BMI270_App_PrintSample(const BMI270_Sample_t *sample)
{
  char message[256];
  int length;

  length = snprintf(
      message, sizeof(message),
      "BMI270 DATA: t_us=%lu, acc_raw=[%d,%d,%d], acc_mg=[%ld,%ld,%ld], "
      "gyr_raw=[%d,%d,%d], gyr_mdps=[%ld,%ld,%ld], status=0x%02X\r\n",
      (unsigned long)sample->timestamp_us,
      (int)sample->acc_raw_x, (int)sample->acc_raw_y,
      (int)sample->acc_raw_z,
      (long)sample->acc_mg_x, (long)sample->acc_mg_y,
      (long)sample->acc_mg_z,
      (int)sample->gyr_raw_x, (int)sample->gyr_raw_y,
      (int)sample->gyr_raw_z,
      (long)sample->gyr_mdps_x, (long)sample->gyr_mdps_y,
      (long)sample->gyr_mdps_z,
      (unsigned int)sample->status);

  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            BMI270_APP_UART_TIMEOUT_MS);
  }
}
