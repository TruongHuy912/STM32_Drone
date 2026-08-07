#include "bmp388_app.h"

#include "bmp388_port.h"
#include "debug_log.h"
#include "i2c.h"
#include "usart.h"

#include <stdio.h>

#define BMP388_APP_I2C_TIMEOUT_MS       50U
#define BMP388_APP_UART_TIMEOUT_MS      25U
#define BMP388_APP_POLL_PERIOD_US    20000U
#define BMP388_APP_PRINT_SAMPLE_COUNT    5U

static struct bmp3_dev bmp388_device;
static struct bmp3_settings bmp388_settings;
static struct bmp3_data bmp388_data;
static struct bmp3_status bmp388_status;
static BMP388_PortContext_t bmp388_context;
static BMP388_Sample_t bmp388_sample;
static uint32_t bmp388_last_poll_us;
static uint32_t bmp388_sample_count;
static uint32_t bmp388_read_error_count;
static uint32_t bmp388_not_ready_count;
static uint32_t bmp388_print_count;
static uint8_t bmp388_ready;

static void BMP388_App_PrintInitFailure(const char *stage, int8_t result);
static uint8_t BMP388_App_SettingsMatch(
    const struct bmp3_settings *settings);
static uint32_t BMP388_App_PressureToPa(double pressure);
static int32_t BMP388_App_TemperatureToCentiC(double temperature);
static void BMP388_App_PrintSample(const BMP388_Sample_t *sample);

int8_t BMP388_App_Init(void)
{
  struct bmp3_settings verify_settings = {0};
  uint32_t settings_sel;
  int8_t result;

  bmp388_device = (struct bmp3_dev){0};
  bmp388_settings = (struct bmp3_settings){0};
  bmp388_data = (struct bmp3_data){0};
  bmp388_status = (struct bmp3_status){0};
  bmp388_sample = (BMP388_Sample_t){0};
  bmp388_ready = 0U;
  bmp388_sample_count = 0U;
  bmp388_read_error_count = 0U;
  bmp388_not_ready_count = 0U;
  bmp388_print_count = 0U;

  bmp388_context.hi2c = &hi2c2;
  bmp388_context.address_7bit = 0U;
  bmp388_context.timeout_ms = BMP388_APP_I2C_TIMEOUT_MS;

  HAL_Delay(10U);
  result = BMP388_Port_SelectAddress(&bmp388_context);
  if (result != BMP3_OK)
  {
    BMP388_App_PrintInitFailure("NO_ACK", result);
    return result;
  }

  result = BMP388_Port_Configure(&bmp388_device, &bmp388_context);
  if (result == BMP3_OK)
  {
    result = bmp3_init(&bmp388_device);
  }
  if (result != BMP3_OK)
  {
    BMP388_App_PrintInitFailure("API_INIT", result);
    return result;
  }
  if (bmp388_device.chip_id != BMP3_CHIP_ID)
  {
    result = BMP3_E_DEV_NOT_FOUND;
    BMP388_App_PrintInitFailure("CHIP_ID", result);
    return result;
  }

  bmp388_settings.press_en = BMP3_ENABLE;
  bmp388_settings.temp_en = BMP3_ENABLE;
  bmp388_settings.odr_filter.press_os = BMP3_OVERSAMPLING_8X;
  bmp388_settings.odr_filter.temp_os = BMP3_NO_OVERSAMPLING;
  bmp388_settings.odr_filter.odr = BMP3_ODR_50_HZ;
  bmp388_settings.odr_filter.iir_filter = BMP3_IIR_FILTER_COEFF_3;
  bmp388_settings.int_settings.drdy_en = BMP3_ENABLE;

  settings_sel = BMP3_SEL_PRESS_EN | BMP3_SEL_TEMP_EN |
                 BMP3_SEL_PRESS_OS | BMP3_SEL_TEMP_OS |
                 BMP3_SEL_ODR | BMP3_SEL_IIR_FILTER |
                 BMP3_SEL_DRDY_EN;
  result = bmp3_set_sensor_settings(settings_sel, &bmp388_settings,
                                    &bmp388_device);
  if (result != BMP3_OK)
  {
    BMP388_App_PrintInitFailure("SET_SETTINGS", result);
    return result;
  }

  bmp388_settings.op_mode = BMP3_MODE_NORMAL;
  result = bmp3_set_op_mode(&bmp388_settings, &bmp388_device);
  if (result != BMP3_OK)
  {
    BMP388_App_PrintInitFailure("SET_MODE", result);
    return result;
  }

  result = bmp3_get_sensor_settings(&verify_settings, &bmp388_device);
  if (result != BMP3_OK)
  {
    BMP388_App_PrintInitFailure("VERIFY_SETTINGS", result);
    return result;
  }
  if (BMP388_App_SettingsMatch(&verify_settings) == 0U)
  {
    result = BMP3_E_CONFIGURATION_ERR;
    BMP388_App_PrintInitFailure("VERIFY_SETTINGS", result);
    return result;
  }

  {
    char message[96];
    int length;

    length = snprintf(message, sizeof(message),
                      "BMP388 API INIT: PASS, result=0, address=0x%02X, "
                      "chip_id=0x%02X\r\n",
                      (unsigned int)bmp388_context.address_7bit,
                      (unsigned int)bmp388_device.chip_id);
    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length,
                              BMP388_APP_UART_TIMEOUT_MS);
    }
  }

  {
    static const char message[] =
        "BMP388 DATA INIT: PASS, press_os=8x, temp_os=1x, odr=50Hz, "
        "iir_sel=2, mode=NORMAL\r\n";

    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)(sizeof(message) - 1U),
                            BMP388_APP_UART_TIMEOUT_MS);
  }

  bmp388_last_poll_us = micros();
  bmp388_ready = 1U;
  return BMP3_OK;
}

void BMP388_App_Process(void)
{
  uint32_t now_us;
  int8_t result;

  if (bmp388_ready == 0U)
  {
    return;
  }

  now_us = micros();
  if ((uint32_t)(now_us - bmp388_last_poll_us) < BMP388_APP_POLL_PERIOD_US)
  {
    return;
  }

  /* Resume from now rather than running an unbounded catch-up loop. */
  bmp388_last_poll_us = now_us;
  result = bmp3_get_status(&bmp388_status, &bmp388_device);
  if (result != BMP3_OK)
  {
    bmp388_read_error_count++;
    return;
  }
  if (bmp388_status.intr.drdy != BMP3_ENABLE)
  {
    bmp388_not_ready_count++;
    return;
  }

  result = bmp3_get_sensor_data(BMP3_PRESS_TEMP, &bmp388_data,
                                &bmp388_device);
  if (result != BMP3_OK)
  {
    bmp388_read_error_count++;
    return;
  }

  /* The official example reads status again to clear the DRDY indication. */
  result = bmp3_get_status(&bmp388_status, &bmp388_device);
  if (result != BMP3_OK)
  {
    bmp388_read_error_count++;
    return;
  }

  bmp388_sample.timestamp_us = now_us;
  bmp388_sample.pressure_pa =
      BMP388_App_PressureToPa(bmp388_data.pressure);
  bmp388_sample.temperature_centi_c =
      BMP388_App_TemperatureToCentiC(bmp388_data.temperature);
  bmp388_sample.drdy = BMP3_ENABLE;
  bmp388_sample.last_result = BMP3_OK;

  bmp388_sample_count++;
  bmp388_print_count++;
  if (bmp388_print_count >= BMP388_APP_PRINT_SAMPLE_COUNT)
  {
    bmp388_print_count = 0U;
    if (Debug_Log_IsFull() != 0U)
    {
      BMP388_App_PrintSample(&bmp388_sample);
    }
  }
}

static void BMP388_App_PrintInitFailure(const char *stage, int8_t result)
{
  char message[128];
  int length;

  length = snprintf(message, sizeof(message),
                    "BMP388 API INIT: FAIL, stage=%s, result=%d, "
                    "address=0x%02X, chip_id=0x%02X\r\n",
                    stage, (int)result,
                    (unsigned int)bmp388_context.address_7bit,
                    (unsigned int)bmp388_device.chip_id);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            BMP388_APP_UART_TIMEOUT_MS);
  }
}

static uint8_t BMP388_App_SettingsMatch(
    const struct bmp3_settings *settings)
{
  return (uint8_t)(
      (settings->press_en == BMP3_ENABLE) &&
      (settings->temp_en == BMP3_ENABLE) &&
      (settings->odr_filter.press_os == BMP3_OVERSAMPLING_8X) &&
      (settings->odr_filter.temp_os == BMP3_NO_OVERSAMPLING) &&
      (settings->odr_filter.odr == BMP3_ODR_50_HZ) &&
      (settings->odr_filter.iir_filter == BMP3_IIR_FILTER_COEFF_3) &&
      (settings->int_settings.drdy_en == BMP3_ENABLE) &&
      (settings->op_mode == BMP3_MODE_NORMAL));
}

static uint32_t BMP388_App_PressureToPa(double pressure)
{
  if (pressure <= 0.0)
  {
    return 0U;
  }
  if (pressure >= (double)UINT32_MAX)
  {
    return UINT32_MAX;
  }

  return (uint32_t)(pressure + 0.5);
}

static int32_t BMP388_App_TemperatureToCentiC(double temperature)
{
  double centi_c = temperature * 100.0;

  if (centi_c >= 0.0)
  {
    return (int32_t)(centi_c + 0.5);
  }

  return (int32_t)(centi_c - 0.5);
}

static void BMP388_App_PrintSample(const BMP388_Sample_t *sample)
{
  char message[144];
  int length;

  length = snprintf(message, sizeof(message),
                    "BMP388 DATA: t_us=%lu, pressure_pa=%lu, "
                    "temperature_centi_c=%ld, drdy=%u, result=%d\r\n",
                    (unsigned long)sample->timestamp_us,
                    (unsigned long)sample->pressure_pa,
                    (long)sample->temperature_centi_c,
                    (unsigned int)sample->drdy,
                    (int)sample->last_result);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            BMP388_APP_UART_TIMEOUT_MS);
  }
}
