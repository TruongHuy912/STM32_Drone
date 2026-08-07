#include "esc_pwm.h"

#include "debug_log.h"
#include "tim.h"
#include "usart.h"

#include <stdio.h>

#define ESC_PWM_EXPECTED_PRESCALER   199U
#define ESC_PWM_EXPECTED_PERIOD    19999U
#define ESC_PWM_FREQUENCY_HZ           50U
#define ESC_PWM_MACHINE_PERIOD_US  100000U
#define ESC_PWM_DIAG_PERIOD_US   1000000U
#define ESC_PWM_UART_TIMEOUT_MS       25U
#define ESC_PWM_ALL_STARTED_MASK      0x0FU

static const uint32_t esc_pwm_channels[ESC_PWM_MOTOR_COUNT] =
{
  TIM_CHANNEL_1,
  TIM_CHANNEL_2,
  TIM_CHANNEL_3,
  TIM_CHANNEL_4
};

static const char *const esc_pwm_stage_names[ESC_PWM_MOTOR_COUNT] =
{
  "CH1",
  "CH2",
  "CH3",
  "CH4"
};

static ESC_PWM_Status_t esc_pwm_status;
static uint32_t esc_pwm_last_machine_us;
static uint32_t esc_pwm_last_diag_us;

static uint8_t ESC_PWM_ConfigIsSafe(void);
static void ESC_PWM_WriteAllSafe(void);
static void ESC_PWM_PrintInitPass(void);
static void ESC_PWM_PrintInitFail(const char *stage,
                                  HAL_StatusTypeDef hal_status);
static void ESC_PWM_PrintMachine(uint32_t now_us);
static void ESC_PWM_PrintDiagnostic(void);
static void ESC_PWM_ReadCcr(uint32_t ccr[ESC_PWM_MOTOR_COUNT]);

uint8_t ESC_PWM_Init(void)
{
  esc_pwm_status = (ESC_PWM_Status_t){0};
  esc_pwm_status.state = ESC_PWM_STATE_UNINITIALIZED;
  esc_pwm_status.init_result = HAL_ERROR;
  esc_pwm_last_machine_us = micros();
  esc_pwm_last_diag_us = esc_pwm_last_machine_us;

  if (!ESC_PWM_ConfigIsSafe())
  {
    esc_pwm_status.state = ESC_PWM_STATE_ERROR;
    ESC_PWM_PrintInitFail("INIT", HAL_ERROR);
    return 0U;
  }

  ESC_PWM_WriteAllSafe();
  esc_pwm_status.init_result = HAL_OK;
  return 1U;
}

uint8_t ESC_PWM_StartSafe(void)
{
  HAL_StatusTypeDef result;
  uint8_t motor_index;
  uint8_t started_count = 0U;

  if ((esc_pwm_status.init_result != HAL_OK) ||
      (!ESC_PWM_ConfigIsSafe()))
  {
    esc_pwm_status.state = ESC_PWM_STATE_ERROR;
    esc_pwm_status.init_result = HAL_ERROR;
    ESC_PWM_PrintInitFail("INIT", HAL_ERROR);
    return 0U;
  }

  ESC_PWM_WriteAllSafe();
  esc_pwm_status.started_mask = 0U;

  for (motor_index = 0U; motor_index < ESC_PWM_MOTOR_COUNT; motor_index++)
  {
    result = HAL_TIM_PWM_Start(&htim4, esc_pwm_channels[motor_index]);
    if (result != HAL_OK)
    {
      uint8_t stop_index;

      esc_pwm_status.start_error_count++;
      ESC_PWM_WriteAllSafe();
      for (stop_index = 0U; stop_index < started_count; stop_index++)
      {
        (void)HAL_TIM_PWM_Stop(&htim4, esc_pwm_channels[stop_index]);
      }
      esc_pwm_status.started_mask = 0U;
      esc_pwm_status.state = ESC_PWM_STATE_ERROR;
      ESC_PWM_PrintInitFail(esc_pwm_stage_names[motor_index], result);
      return 0U;
    }

    esc_pwm_status.started_mask |= (uint8_t)(1U << motor_index);
    started_count++;
  }

  if (esc_pwm_status.started_mask != ESC_PWM_ALL_STARTED_MASK)
  {
    ESC_PWM_StopAll();
    esc_pwm_status.state = ESC_PWM_STATE_ERROR;
    esc_pwm_status.start_error_count++;
    ESC_PWM_PrintInitFail("INIT", HAL_ERROR);
    return 0U;
  }

  esc_pwm_status.state = ESC_PWM_STATE_SAFE;
  ESC_PWM_PrintInitPass();
  return 1U;
}

void ESC_PWM_SetAllSafe(void)
{
  if (htim4.Instance != TIM4)
  {
    esc_pwm_status.state = ESC_PWM_STATE_ERROR;
    return;
  }

  ESC_PWM_WriteAllSafe();
}

uint8_t ESC_PWM_SetPulseUs(uint8_t motor_index, uint16_t pulse_us)
{
  if ((motor_index >= ESC_PWM_MOTOR_COUNT) ||
      (pulse_us != ESC_PWM_SAFE_PULSE_US) ||
      (htim4.Instance != TIM4))
  {
    esc_pwm_status.rejected_command_count++;
    return 0U;
  }

  __HAL_TIM_SET_COMPARE(&htim4, esc_pwm_channels[motor_index],
                        ESC_PWM_SAFE_PULSE_US);
  esc_pwm_status.pulse_us[motor_index] = ESC_PWM_SAFE_PULSE_US;
  return 1U;
}

uint8_t ESC_PWM_SetSingleBenchPulseUs(uint8_t motor_index,
                                      uint16_t pulse_us)
{
  if ((htim4.Instance != TIM4) ||
      (esc_pwm_status.state != ESC_PWM_STATE_SAFE) ||
      (esc_pwm_status.started_mask != ESC_PWM_ALL_STARTED_MASK) ||
      (motor_index >= ESC_PWM_MOTOR_COUNT) ||
      (pulse_us < ESC_PWM_BENCH_MIN_PULSE_US) ||
      (pulse_us > ESC_PWM_BENCH_MAX_PULSE_US))
  {
    esc_pwm_status.rejected_command_count++;
    if (htim4.Instance == TIM4)
    {
      ESC_PWM_WriteAllSafe();
    }
    return 0U;
  }

  ESC_PWM_WriteAllSafe();
  __HAL_TIM_SET_COMPARE(&htim4, esc_pwm_channels[motor_index], pulse_us);
  esc_pwm_status.pulse_us[motor_index] = pulse_us;
  return 1U;
}

uint8_t ESC_PWM_AreAllOutputsSafe(void)
{
  uint8_t motor_index;

  if (htim4.Instance != TIM4)
  {
    return 0U;
  }

  for (motor_index = 0U; motor_index < ESC_PWM_MOTOR_COUNT; motor_index++)
  {
    if ((__HAL_TIM_GET_COMPARE(&htim4, esc_pwm_channels[motor_index]) !=
         ESC_PWM_SAFE_PULSE_US) ||
        (esc_pwm_status.pulse_us[motor_index] != ESC_PWM_SAFE_PULSE_US))
    {
      return 0U;
    }
  }

  return 1U;
}

uint8_t ESC_PWM_OutputsMatchSingleBench(uint8_t motor_index,
                                        uint16_t pulse_us)
{
  uint8_t index;

  if ((htim4.Instance != TIM4) ||
      (motor_index >= ESC_PWM_MOTOR_COUNT) ||
      (pulse_us < ESC_PWM_BENCH_MIN_PULSE_US) ||
      (pulse_us > ESC_PWM_BENCH_MAX_PULSE_US))
  {
    return 0U;
  }

  for (index = 0U; index < ESC_PWM_MOTOR_COUNT; index++)
  {
    uint16_t expected = (index == motor_index) ?
        pulse_us : ESC_PWM_SAFE_PULSE_US;

    if ((__HAL_TIM_GET_COMPARE(&htim4, esc_pwm_channels[index]) != expected) ||
        (esc_pwm_status.pulse_us[index] != expected))
    {
      return 0U;
    }
  }

  return 1U;
}

void ESC_PWM_StopAll(void)
{
  uint8_t motor_index;

  if (htim4.Instance != TIM4)
  {
    esc_pwm_status.state = ESC_PWM_STATE_ERROR;
    esc_pwm_status.started_mask = 0U;
    return;
  }

  ESC_PWM_WriteAllSafe();
  for (motor_index = 0U; motor_index < ESC_PWM_MOTOR_COUNT; motor_index++)
  {
    (void)HAL_TIM_PWM_Stop(&htim4, esc_pwm_channels[motor_index]);
  }
  esc_pwm_status.started_mask = 0U;
  if (esc_pwm_status.state != ESC_PWM_STATE_ERROR)
  {
    esc_pwm_status.state = ESC_PWM_STATE_UNINITIALIZED;
  }
}

const ESC_PWM_Status_t *ESC_PWM_GetStatus(void)
{
  return &esc_pwm_status;
}

void ESC_PWM_Process(void)
{
  uint32_t now_us = micros();

  if ((uint32_t)(now_us - esc_pwm_last_machine_us) >=
      ESC_PWM_MACHINE_PERIOD_US)
  {
    esc_pwm_last_machine_us = now_us;
    ESC_PWM_PrintMachine(now_us);
  }

  if ((Debug_Log_IsFull() != 0U) &&
      ((uint32_t)(now_us - esc_pwm_last_diag_us) >= ESC_PWM_DIAG_PERIOD_US))
  {
    esc_pwm_last_diag_us = now_us;
    ESC_PWM_PrintDiagnostic();
  }
}

static uint8_t ESC_PWM_ConfigIsSafe(void)
{
  return (uint8_t)(((htim4.Instance == TIM4) &&
                    (htim4.Init.Prescaler == ESC_PWM_EXPECTED_PRESCALER) &&
                    (htim4.Init.CounterMode == TIM_COUNTERMODE_UP) &&
                    (htim4.Init.Period == ESC_PWM_EXPECTED_PERIOD) &&
                    (htim4.Init.ClockDivision == TIM_CLOCKDIVISION_DIV1) &&
                    (htim4.Init.AutoReloadPreload ==
                     TIM_AUTORELOAD_PRELOAD_ENABLE)) ? 1U : 0U);
}

static void ESC_PWM_WriteAllSafe(void)
{
  uint8_t motor_index;

  for (motor_index = 0U; motor_index < ESC_PWM_MOTOR_COUNT; motor_index++)
  {
    __HAL_TIM_SET_COMPARE(&htim4, esc_pwm_channels[motor_index],
                          ESC_PWM_SAFE_PULSE_US);
    esc_pwm_status.pulse_us[motor_index] = ESC_PWM_SAFE_PULSE_US;
  }
}

static void ESC_PWM_PrintInitPass(void)
{
  static const char message[] =
      "ESC PWM INIT: PASS, timer=TIM4, frequency_hz=50, tick_us=1, "
      "pulse_us=[1000,1000,1000,1000], "
      "pins=[PD12,PD13,PD14,PD15], state=SAFE\r\n";

  (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                          (uint16_t)(sizeof(message) - 1U),
                          ESC_PWM_UART_TIMEOUT_MS);
}

static void ESC_PWM_PrintInitFail(const char *stage,
                                  HAL_StatusTypeDef hal_status)
{
  char message[128];
  int length;

  length = snprintf(message, sizeof(message),
                    "ESC PWM INIT: FAIL, stage=%s, hal_status=%u, "
                    "started_mask=0x%02X, state=ERROR\r\n",
                    stage,
                    (unsigned int)hal_status,
                    (unsigned int)esc_pwm_status.started_mask);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, ESC_PWM_UART_TIMEOUT_MS);
  }
}

static void ESC_PWM_PrintMachine(uint32_t now_us)
{
  uint32_t ccr[ESC_PWM_MOTOR_COUNT];
  char message[160];
  int length;

  ESC_PWM_ReadCcr(ccr);
  length = snprintf(message, sizeof(message),
                    "@ESC,%lu,%u,%u,%u,%lu,%lu,%lu,%lu,%lu,%lu\r\n",
                    (unsigned long)now_us,
                    (unsigned int)esc_pwm_status.state,
                    (unsigned int)esc_pwm_status.started_mask,
                    (unsigned int)ESC_PWM_FREQUENCY_HZ,
                    (unsigned long)ccr[0],
                    (unsigned long)ccr[1],
                    (unsigned long)ccr[2],
                    (unsigned long)ccr[3],
                    (unsigned long)esc_pwm_status.rejected_command_count,
                    (unsigned long)esc_pwm_status.start_error_count);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, ESC_PWM_UART_TIMEOUT_MS);
  }
}

static void ESC_PWM_PrintDiagnostic(void)
{
  uint32_t ccr[ESC_PWM_MOTOR_COUNT];
  char message[192];
  int length;

  ESC_PWM_ReadCcr(ccr);
  length = snprintf(message, sizeof(message),
                    "ESC PWM DIAG: state=%u, started_mask=0x%02X, "
                    "ccr=[%lu,%lu,%lu,%lu], rejected=%lu, "
                    "start_errors=%lu\r\n",
                    (unsigned int)esc_pwm_status.state,
                    (unsigned int)esc_pwm_status.started_mask,
                    (unsigned long)ccr[0],
                    (unsigned long)ccr[1],
                    (unsigned long)ccr[2],
                    (unsigned long)ccr[3],
                    (unsigned long)esc_pwm_status.rejected_command_count,
                    (unsigned long)esc_pwm_status.start_error_count);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, ESC_PWM_UART_TIMEOUT_MS);
  }
}

static void ESC_PWM_ReadCcr(uint32_t ccr[ESC_PWM_MOTOR_COUNT])
{
  uint8_t motor_index;

  if (htim4.Instance != TIM4)
  {
    for (motor_index = 0U; motor_index < ESC_PWM_MOTOR_COUNT; motor_index++)
    {
      ccr[motor_index] = 0U;
    }
    return;
  }

  for (motor_index = 0U; motor_index < ESC_PWM_MOTOR_COUNT; motor_index++)
  {
    ccr[motor_index] =
        __HAL_TIM_GET_COMPARE(&htim4, esc_pwm_channels[motor_index]);
  }
}
