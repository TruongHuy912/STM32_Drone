#include "motor_test.h"

#include "debug_log.h"
#include "esc_pwm.h"
#include "ibus_app.h"
#include "usart.h"

#include <stdio.h>

#define MOTOR_TEST_IBUS_ACCEPT_MAX_AGE_US  50000U
#define MOTOR_TEST_IBUS_ABORT_MAX_AGE_US  100000U
#define MOTOR_TEST_THROTTLE_MAX              1050U
#define MOTOR_TEST_ENABLE_HIGH               1900U
#define MOTOR_TEST_ENABLE_ABORT_LOW          1700U
#define MOTOR_TEST_CHANNEL_MIN                800U
#define MOTOR_TEST_CHANNEL_MAX               2200U
#define MOTOR_TEST_MIN_DURATION_MS            100U
#define MOTOR_TEST_MAX_DURATION_MS           2000U
#define MOTOR_TEST_MACHINE_PERIOD_US       100000U
#define MOTOR_TEST_DIAG_PERIOD_US         1000000U
#define MOTOR_TEST_UART_TIMEOUT_MS              25U
#define MOTOR_TEST_ALL_STARTED_MASK             0x0FU

#define MOTOR_TEST_GATE_ESC_SAFE       (1UL << 0U)
#define MOTOR_TEST_GATE_ALL_STARTED    (1UL << 1U)
#define MOTOR_TEST_GATE_IBUS_VALID     (1UL << 2U)
#define MOTOR_TEST_GATE_IBUS_FRESH     (1UL << 3U)
#define MOTOR_TEST_GATE_THROTTLE_LOW   (1UL << 4U)
#define MOTOR_TEST_GATE_CH5_ENABLED    (1UL << 5U)
#define MOTOR_TEST_GATE_CH6_ENABLED    (1UL << 6U)
#define MOTOR_TEST_GATE_CHANNEL_RANGE  (1UL << 7U)
#define MOTOR_TEST_GATE_ALL            0xFFUL

#define MOTOR_TEST_THROTTLE_INDEX  2U
#define MOTOR_TEST_CH5_INDEX       4U
#define MOTOR_TEST_CH6_INDEX       5U

static Motor_Test_Status_t motor_test_status;
static uint32_t motor_test_start_us;
static uint32_t motor_test_last_machine_us;
static uint32_t motor_test_last_diag_us;

static uint32_t Motor_Test_EvaluateGates(const IBus_State_t *ibus,
                                         const ESC_PWM_Status_t *esc);
static void Motor_Test_RefreshFrameAge(IBus_State_t *ibus, uint32_t now_us);
static Motor_Test_AbortReason_t Motor_Test_FirstGateFailure(uint32_t gates);
static uint8_t Motor_Test_WriteSafeAndVerify(void);
static void Motor_Test_Start(const Motor_Test_Command_t *command);
static void Motor_Test_Finish(Motor_Test_AbortReason_t reason,
                              uint8_t completed,
                              uint8_t latch_fault);
static void Motor_Test_PrintCommandAccept(const Motor_Test_Command_t *command);
static void Motor_Test_PrintCommandReject(Motor_Test_AbortReason_t reason,
                                          Motor_Test_ParseResult_t parse_result,
                                          const Motor_Test_Command_t *command);
static void Motor_Test_PrintStatus(void);
static void Motor_Test_PrintMachine(uint32_t now_us);
static void Motor_Test_PrintDiagnostic(void);
static const char *Motor_Test_AbortReasonName(Motor_Test_AbortReason_t reason);

void Motor_Test_Init(void)
{
  const ESC_PWM_Status_t *esc = ESC_PWM_GetStatus();
  uint32_t now_us = micros();

  motor_test_status = (Motor_Test_Status_t){0};
  motor_test_status.state = MOTOR_TEST_DISABLED;
  motor_test_status.active_pulse_us = ESC_PWM_SAFE_PULSE_US;
  motor_test_start_us = now_us;
  motor_test_last_machine_us = now_us;
  motor_test_last_diag_us = now_us;

  if ((esc->state == ESC_PWM_STATE_SAFE) &&
      (esc->started_mask == MOTOR_TEST_ALL_STARTED_MASK) &&
      (Motor_Test_WriteSafeAndVerify() != 0U))
  {
    static const char message[] =
        "MTEST INIT: PASS, state=READY, auto_run=DISABLED\r\n";

    motor_test_status.state = MOTOR_TEST_READY;
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)(sizeof(message) - 1U),
                            MOTOR_TEST_UART_TIMEOUT_MS);
  }
  else
  {
    static const char message[] =
        "MTEST INIT: FAIL, state=FAULT, outputs_us=1000\r\n";

    motor_test_status.state = MOTOR_TEST_FAULT;
    motor_test_status.last_abort_reason = MOTOR_TEST_ABORT_ESC_NOT_SAFE;
    (void)Motor_Test_WriteSafeAndVerify();
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)(sizeof(message) - 1U),
                            MOTOR_TEST_UART_TIMEOUT_MS);
  }
}

void Motor_Test_Process(void)
{
  IBus_State_t ibus;
  const ESC_PWM_Status_t *esc = ESC_PWM_GetStatus();
  uint32_t now_us = micros();

  IBus_App_GetState(&ibus);
  Motor_Test_RefreshFrameAge(&ibus, now_us);
  motor_test_status.safety_gate_mask = Motor_Test_EvaluateGates(&ibus, esc);

  if (motor_test_status.state == MOTOR_TEST_RUNNING)
  {
    uint32_t elapsed_us = (uint32_t)(now_us - motor_test_start_us);
    uint32_t duration_us = (uint32_t)motor_test_status.duration_ms * 1000U;

    motor_test_status.elapsed_ms = (uint16_t)(elapsed_us / 1000U);
    motor_test_status.remaining_ms = (elapsed_us >= duration_us) ? 0U :
        (uint16_t)((duration_us - elapsed_us + 999U) / 1000U);

    if ((esc->state != ESC_PWM_STATE_SAFE) ||
        (esc->started_mask != MOTOR_TEST_ALL_STARTED_MASK))
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_ESC_NOT_SAFE, 0U, 1U);
    }
    else if ((ibus.valid_frames == 0U) || (ibus.frame_valid == 0U))
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_IBUS_INVALID, 0U, 0U);
    }
    else if (ibus.frame_age_us >= MOTOR_TEST_IBUS_ABORT_MAX_AGE_US)
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_IBUS_TIMEOUT, 0U, 0U);
    }
    else if (ibus.stream_alive == 0U)
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_IBUS_INVALID, 0U, 0U);
    }
    else if ((ibus.channels[MOTOR_TEST_THROTTLE_INDEX] <
              MOTOR_TEST_CHANNEL_MIN) ||
             (ibus.channels[MOTOR_TEST_THROTTLE_INDEX] >
              MOTOR_TEST_CHANNEL_MAX) ||
             (ibus.channels[MOTOR_TEST_CH5_INDEX] < MOTOR_TEST_CHANNEL_MIN) ||
             (ibus.channels[MOTOR_TEST_CH5_INDEX] > MOTOR_TEST_CHANNEL_MAX) ||
             (ibus.channels[MOTOR_TEST_CH6_INDEX] < MOTOR_TEST_CHANNEL_MIN) ||
             (ibus.channels[MOTOR_TEST_CH6_INDEX] > MOTOR_TEST_CHANNEL_MAX))
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_IBUS_INVALID, 0U, 0U);
    }
    else if (ibus.channels[MOTOR_TEST_THROTTLE_INDEX] >
             MOTOR_TEST_THROTTLE_MAX)
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_THROTTLE_NOT_LOW, 0U, 0U);
    }
    else if (ibus.channels[MOTOR_TEST_CH5_INDEX] <
             MOTOR_TEST_ENABLE_ABORT_LOW)
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_CH5_NOT_ENABLED, 0U, 0U);
    }
    else if (ibus.channels[MOTOR_TEST_CH6_INDEX] <
             MOTOR_TEST_ENABLE_ABORT_LOW)
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_CH6_NOT_ENABLED, 0U, 0U);
    }
    else if (elapsed_us >= duration_us)
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_TIME_EXPIRED, 1U, 0U);
    }
    else if (ESC_PWM_OutputsMatchSingleBench(
                 (uint8_t)(motor_test_status.selected_motor - 1U),
                 motor_test_status.commanded_pulse_us) == 0U)
    {
      Motor_Test_Finish(MOTOR_TEST_ABORT_INTERNAL_ERROR, 0U, 1U);
    }
  }
  else
  {
    uint8_t safe_ok = Motor_Test_WriteSafeAndVerify();

    if ((esc->state != ESC_PWM_STATE_SAFE) ||
        (esc->started_mask != MOTOR_TEST_ALL_STARTED_MASK) ||
        (safe_ok == 0U))
    {
      motor_test_status.state = MOTOR_TEST_FAULT;
      motor_test_status.last_abort_reason = MOTOR_TEST_ABORT_ESC_NOT_SAFE;
    }
  }

  now_us = micros();
  if ((uint32_t)(now_us - motor_test_last_machine_us) >=
      MOTOR_TEST_MACHINE_PERIOD_US)
  {
    motor_test_last_machine_us = now_us;
    Motor_Test_PrintMachine(now_us);
  }
  if ((Debug_Log_IsFull() != 0U) &&
      ((uint32_t)(now_us - motor_test_last_diag_us) >=
       MOTOR_TEST_DIAG_PERIOD_US))
  {
    motor_test_last_diag_us = now_us;
    Motor_Test_PrintDiagnostic();
  }
}

void Motor_Test_HandleCommand(const Motor_Test_Command_t *command)
{
  if (command == NULL)
  {
    Motor_Test_HandleParseError(MOTOR_TEST_PARSE_EMPTY);
    return;
  }

  switch (command->type)
  {
    case MOTOR_TEST_COMMAND_STATUS:
      Motor_Test_PrintStatus();
      Motor_Test_PrintCommandAccept(command);
      break;

    case MOTOR_TEST_COMMAND_RUN:
      Motor_Test_Start(command);
      break;

    case MOTOR_TEST_COMMAND_STOP:
      if (motor_test_status.state == MOTOR_TEST_RUNNING)
      {
        Motor_Test_Finish(MOTOR_TEST_ABORT_USER_STOP, 0U, 0U);
      }
      else
      {
        (void)Motor_Test_WriteSafeAndVerify();
      }
      Motor_Test_PrintCommandAccept(command);
      break;

    case MOTOR_TEST_COMMAND_EMERGENCY_STOP:
      if (motor_test_status.state == MOTOR_TEST_RUNNING)
      {
        Motor_Test_Finish(MOTOR_TEST_ABORT_EMERGENCY_STOP, 0U, 0U);
      }
      else
      {
        (void)Motor_Test_WriteSafeAndVerify();
        motor_test_status.last_abort_reason =
            MOTOR_TEST_ABORT_EMERGENCY_STOP;
      }
      Motor_Test_PrintCommandAccept(command);
      break;

    default:
      Motor_Test_HandleParseError(MOTOR_TEST_PARSE_UNKNOWN);
      break;
  }
}

void Motor_Test_HandleParseError(Motor_Test_ParseResult_t parse_result)
{
  motor_test_status.rejected_count++;
  if (motor_test_status.state == MOTOR_TEST_RUNNING)
  {
    Motor_Test_Finish(MOTOR_TEST_ABORT_INVALID_COMMAND, 0U, 0U);
  }
  else
  {
    (void)Motor_Test_WriteSafeAndVerify();
    motor_test_status.last_abort_reason = MOTOR_TEST_ABORT_INVALID_COMMAND;
  }
  Motor_Test_PrintCommandReject(MOTOR_TEST_ABORT_INVALID_COMMAND,
                                parse_result, NULL);
}

void Motor_Test_LatchFault(Motor_Test_AbortReason_t reason)
{
  if (reason == MOTOR_TEST_ABORT_NONE)
  {
    reason = MOTOR_TEST_ABORT_INTERNAL_ERROR;
  }
  Motor_Test_Finish(reason, 0U, 1U);
}

const Motor_Test_Status_t *Motor_Test_GetStatus(void)
{
  return &motor_test_status;
}

static uint32_t Motor_Test_EvaluateGates(const IBus_State_t *ibus,
                                         const ESC_PWM_Status_t *esc)
{
  uint32_t gates = 0U;
  uint16_t throttle = ibus->channels[MOTOR_TEST_THROTTLE_INDEX];
  uint16_t ch5 = ibus->channels[MOTOR_TEST_CH5_INDEX];
  uint16_t ch6 = ibus->channels[MOTOR_TEST_CH6_INDEX];

  if (esc->state == ESC_PWM_STATE_SAFE)
  {
    gates |= MOTOR_TEST_GATE_ESC_SAFE;
  }
  if (esc->started_mask == MOTOR_TEST_ALL_STARTED_MASK)
  {
    gates |= MOTOR_TEST_GATE_ALL_STARTED;
  }
  if ((ibus->valid_frames != 0U) && (ibus->frame_valid != 0U) &&
      (ibus->stream_alive != 0U))
  {
    gates |= MOTOR_TEST_GATE_IBUS_VALID;
  }
  if ((ibus->valid_frames != 0U) &&
      (ibus->frame_age_us <= MOTOR_TEST_IBUS_ACCEPT_MAX_AGE_US))
  {
    gates |= MOTOR_TEST_GATE_IBUS_FRESH;
  }
  if (throttle <= MOTOR_TEST_THROTTLE_MAX)
  {
    gates |= MOTOR_TEST_GATE_THROTTLE_LOW;
  }
  if (ch5 >= MOTOR_TEST_ENABLE_HIGH)
  {
    gates |= MOTOR_TEST_GATE_CH5_ENABLED;
  }
  if (ch6 >= MOTOR_TEST_ENABLE_HIGH)
  {
    gates |= MOTOR_TEST_GATE_CH6_ENABLED;
  }
  if ((throttle >= MOTOR_TEST_CHANNEL_MIN) &&
      (throttle <= MOTOR_TEST_CHANNEL_MAX) &&
      (ch5 >= MOTOR_TEST_CHANNEL_MIN) && (ch5 <= MOTOR_TEST_CHANNEL_MAX) &&
      (ch6 >= MOTOR_TEST_CHANNEL_MIN) && (ch6 <= MOTOR_TEST_CHANNEL_MAX))
  {
    gates |= MOTOR_TEST_GATE_CHANNEL_RANGE;
  }

  return gates;
}

static void Motor_Test_RefreshFrameAge(IBus_State_t *ibus, uint32_t now_us)
{
  if (ibus->valid_frames == 0U)
  {
    ibus->frame_age_us = 0U;
  }
  else
  {
    ibus->frame_age_us = (uint32_t)(now_us - ibus->last_valid_frame_us);
  }
}

static Motor_Test_AbortReason_t Motor_Test_FirstGateFailure(uint32_t gates)
{
  if ((gates & MOTOR_TEST_GATE_ESC_SAFE) == 0U ||
      (gates & MOTOR_TEST_GATE_ALL_STARTED) == 0U)
  {
    return MOTOR_TEST_ABORT_ESC_NOT_SAFE;
  }
  if ((gates & MOTOR_TEST_GATE_IBUS_VALID) == 0U ||
      (gates & MOTOR_TEST_GATE_CHANNEL_RANGE) == 0U)
  {
    return MOTOR_TEST_ABORT_IBUS_INVALID;
  }
  if ((gates & MOTOR_TEST_GATE_IBUS_FRESH) == 0U)
  {
    return MOTOR_TEST_ABORT_IBUS_TIMEOUT;
  }
  if ((gates & MOTOR_TEST_GATE_THROTTLE_LOW) == 0U)
  {
    return MOTOR_TEST_ABORT_THROTTLE_NOT_LOW;
  }
  if ((gates & MOTOR_TEST_GATE_CH5_ENABLED) == 0U)
  {
    return MOTOR_TEST_ABORT_CH5_NOT_ENABLED;
  }
  if ((gates & MOTOR_TEST_GATE_CH6_ENABLED) == 0U)
  {
    return MOTOR_TEST_ABORT_CH6_NOT_ENABLED;
  }
  return MOTOR_TEST_ABORT_NONE;
}

static uint8_t Motor_Test_WriteSafeAndVerify(void)
{
  ESC_PWM_SetAllSafe();
  motor_test_status.active_pulse_us = ESC_PWM_SAFE_PULSE_US;
  motor_test_status.remaining_ms = 0U;
  return ESC_PWM_AreAllOutputsSafe();
}

static void Motor_Test_Start(const Motor_Test_Command_t *command)
{
  IBus_State_t ibus;
  const ESC_PWM_Status_t *esc = ESC_PWM_GetStatus();
  Motor_Test_AbortReason_t reject_reason;

  if ((command->motor < 1U) || (command->motor > ESC_PWM_MOTOR_COUNT) ||
      (command->pulse_us < ESC_PWM_BENCH_MIN_PULSE_US) ||
      (command->pulse_us > ESC_PWM_BENCH_MAX_PULSE_US) ||
      (command->duration_ms < MOTOR_TEST_MIN_DURATION_MS) ||
      (command->duration_ms > MOTOR_TEST_MAX_DURATION_MS))
  {
    motor_test_status.rejected_count++;
    Motor_Test_Finish(MOTOR_TEST_ABORT_INVALID_COMMAND, 0U, 1U);
    Motor_Test_PrintCommandReject(MOTOR_TEST_ABORT_INVALID_COMMAND,
                                  MOTOR_TEST_PARSE_OK, command);
    return;
  }

  IBus_App_GetState(&ibus);
  Motor_Test_RefreshFrameAge(&ibus, micros());
  motor_test_status.safety_gate_mask = Motor_Test_EvaluateGates(&ibus, esc);

  if (motor_test_status.state == MOTOR_TEST_FAULT)
  {
    reject_reason = MOTOR_TEST_ABORT_INTERNAL_ERROR;
  }
  else if (motor_test_status.state != MOTOR_TEST_READY)
  {
    reject_reason = MOTOR_TEST_ABORT_INVALID_COMMAND;
  }
  else
  {
    reject_reason =
        Motor_Test_FirstGateFailure(motor_test_status.safety_gate_mask);
  }

  if ((reject_reason != MOTOR_TEST_ABORT_NONE) ||
      (motor_test_status.safety_gate_mask != MOTOR_TEST_GATE_ALL))
  {
    motor_test_status.rejected_count++;
    if (reject_reason == MOTOR_TEST_ABORT_NONE)
    {
      reject_reason = MOTOR_TEST_ABORT_INTERNAL_ERROR;
    }
    if (motor_test_status.state == MOTOR_TEST_RUNNING)
    {
      Motor_Test_Finish(reject_reason, 0U, 0U);
    }
    else
    {
      (void)Motor_Test_WriteSafeAndVerify();
      motor_test_status.last_abort_reason = reject_reason;
    }
    Motor_Test_PrintCommandReject(reject_reason, MOTOR_TEST_PARSE_OK, command);
    return;
  }

  if ((Motor_Test_WriteSafeAndVerify() == 0U) ||
      (ESC_PWM_SetSingleBenchPulseUs((uint8_t)(command->motor - 1U),
                                     command->pulse_us) == 0U) ||
      (ESC_PWM_OutputsMatchSingleBench((uint8_t)(command->motor - 1U),
                                       command->pulse_us) == 0U))
  {
    motor_test_status.rejected_count++;
    Motor_Test_Finish(MOTOR_TEST_ABORT_INTERNAL_ERROR, 0U, 1U);
    Motor_Test_PrintCommandReject(MOTOR_TEST_ABORT_INTERNAL_ERROR,
                                  MOTOR_TEST_PARSE_OK, command);
    return;
  }

  motor_test_status.selected_motor = command->motor;
  motor_test_status.commanded_pulse_us = command->pulse_us;
  motor_test_status.active_pulse_us = command->pulse_us;
  motor_test_status.duration_ms = command->duration_ms;
  motor_test_status.elapsed_ms = 0U;
  motor_test_status.remaining_ms = command->duration_ms;
  motor_test_status.last_abort_reason = MOTOR_TEST_ABORT_NONE;
  motor_test_start_us = micros();
  motor_test_status.run_count++;
  motor_test_status.state = MOTOR_TEST_RUNNING;
  Motor_Test_PrintCommandAccept(command);
}

static void Motor_Test_Finish(Motor_Test_AbortReason_t reason,
                              uint8_t completed,
                              uint8_t latch_fault)
{
  uint8_t was_running =
      (motor_test_status.state == MOTOR_TEST_RUNNING) ? 1U : 0U;
  uint8_t safe_ok = Motor_Test_WriteSafeAndVerify();

  motor_test_status.last_abort_reason = reason;
  if (completed != 0U)
  {
    motor_test_status.completed_count++;
  }
  else if (was_running != 0U)
  {
    motor_test_status.abort_count++;
  }

  if ((latch_fault != 0U) || (safe_ok == 0U))
  {
    motor_test_status.state = MOTOR_TEST_FAULT;
    if (safe_ok == 0U)
    {
      motor_test_status.last_abort_reason = MOTOR_TEST_ABORT_INTERNAL_ERROR;
    }
  }
  else if (motor_test_status.state != MOTOR_TEST_DISABLED)
  {
    motor_test_status.state = MOTOR_TEST_READY;
  }
}

static void Motor_Test_PrintCommandAccept(const Motor_Test_Command_t *command)
{
  const char *command_name;
  const char *reason_name;
  uint8_t motor = 0U;
  uint16_t pulse_us = ESC_PWM_SAFE_PULSE_US;
  uint16_t duration_ms = 0U;
  char message[240];
  int length;

  if (command->type == MOTOR_TEST_COMMAND_RUN)
  {
    command_name = "RUN";
    reason_name = "NONE";
    motor = command->motor;
    pulse_us = command->pulse_us;
    duration_ms = command->duration_ms;
  }
  else if (command->type == MOTOR_TEST_COMMAND_STOP)
  {
    command_name = "STOP";
    reason_name = "USER_STOP";
  }
  else if (command->type == MOTOR_TEST_COMMAND_EMERGENCY_STOP)
  {
    command_name = "ESTOP";
    reason_name = "EMERGENCY_STOP";
  }
  else
  {
    command_name = "STATUS";
    reason_name = "NONE";
  }

  length = snprintf(message, sizeof(message),
                    "MTEST CMD: ACCEPT, command=%s, motor=%u, pulse_us=%u, "
                    "duration_ms=%u\r\n"
                    "@MACK,%lu,%s,1,%s,%u,%u,%u\r\n",
                    command_name,
                    (unsigned int)motor,
                    (unsigned int)pulse_us,
                    (unsigned int)duration_ms,
                    (unsigned long)micros(),
                    command_name,
                    reason_name,
                    (unsigned int)motor,
                    (unsigned int)pulse_us,
                    (unsigned int)duration_ms);

  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, MOTOR_TEST_UART_TIMEOUT_MS);
  }
}

static void Motor_Test_PrintCommandReject(Motor_Test_AbortReason_t reason,
                                          Motor_Test_ParseResult_t parse_result,
                                          const Motor_Test_Command_t *command)
{
  const char *command_name = "INVALID";
  uint8_t motor = 0U;
  uint16_t pulse_us = ESC_PWM_SAFE_PULSE_US;
  uint16_t duration_ms = 0U;
  char message[240];

  if ((command != NULL) && (command->type == MOTOR_TEST_COMMAND_RUN))
  {
    command_name = "RUN";
    motor = command->motor;
    pulse_us = command->pulse_us;
    duration_ms = command->duration_ms;
  }

  int length = snprintf(message, sizeof(message),
                        "MTEST CMD: REJECT, command=%s, reason=%s, "
                        "parse=%u\r\n"
                        "@MACK,%lu,%s,0,%s,%u,%u,%u\r\n",
                        command_name,
                        Motor_Test_AbortReasonName(reason),
                        (unsigned int)parse_result,
                        (unsigned long)micros(),
                        command_name,
                        Motor_Test_AbortReasonName(reason),
                        (unsigned int)motor,
                        (unsigned int)pulse_us,
                        (unsigned int)duration_ms);

  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, MOTOR_TEST_UART_TIMEOUT_MS);
  }
}

static void Motor_Test_PrintStatus(void)
{
  char message[224];
  int length = snprintf(
      message, sizeof(message),
      "MTEST STATUS: state=%u, motor=%u, commanded_us=%u, active_us=%u, "
      "remaining_ms=%u, gates=0x%02lX, abort=%s, runs=%lu, "
      "completed=%lu, aborted=%lu, rejected=%lu\r\n",
      (unsigned int)motor_test_status.state,
      (unsigned int)motor_test_status.selected_motor,
      (unsigned int)motor_test_status.commanded_pulse_us,
      (unsigned int)motor_test_status.active_pulse_us,
      (unsigned int)motor_test_status.remaining_ms,
      (unsigned long)motor_test_status.safety_gate_mask,
      Motor_Test_AbortReasonName(motor_test_status.last_abort_reason),
      (unsigned long)motor_test_status.run_count,
      (unsigned long)motor_test_status.completed_count,
      (unsigned long)motor_test_status.abort_count,
      (unsigned long)motor_test_status.rejected_count);

  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, MOTOR_TEST_UART_TIMEOUT_MS);
  }
}

static void Motor_Test_PrintMachine(uint32_t now_us)
{
  char message[192];
  int length = snprintf(
      message, sizeof(message),
      "@MTEST,%lu,%u,%u,%u,%u,%u,%lu,%u,%lu,%lu,%lu,%lu\r\n",
      (unsigned long)now_us,
      (unsigned int)motor_test_status.state,
      (unsigned int)motor_test_status.selected_motor,
      (unsigned int)motor_test_status.commanded_pulse_us,
      (unsigned int)motor_test_status.active_pulse_us,
      (unsigned int)motor_test_status.remaining_ms,
      (unsigned long)motor_test_status.safety_gate_mask,
      (unsigned int)motor_test_status.last_abort_reason,
      (unsigned long)motor_test_status.run_count,
      (unsigned long)motor_test_status.completed_count,
      (unsigned long)motor_test_status.abort_count,
      (unsigned long)motor_test_status.rejected_count);

  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, MOTOR_TEST_UART_TIMEOUT_MS);
  }
}

static void Motor_Test_PrintDiagnostic(void)
{
  char message[256];
  int length = snprintf(
      message, sizeof(message),
      "MTEST DIAG: state=%u, motor=%u, active_us=%u, remaining_ms=%u, "
      "gates=0x%02lX, abort=%s, runs=%lu, completed=%lu, aborted=%lu, "
      "rejected=%lu\r\n",
      (unsigned int)motor_test_status.state,
      (unsigned int)motor_test_status.selected_motor,
      (unsigned int)motor_test_status.active_pulse_us,
      (unsigned int)motor_test_status.remaining_ms,
      (unsigned long)motor_test_status.safety_gate_mask,
      Motor_Test_AbortReasonName(motor_test_status.last_abort_reason),
      (unsigned long)motor_test_status.run_count,
      (unsigned long)motor_test_status.completed_count,
      (unsigned long)motor_test_status.abort_count,
      (unsigned long)motor_test_status.rejected_count);

  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, MOTOR_TEST_UART_TIMEOUT_MS);
  }
}

static const char *Motor_Test_AbortReasonName(Motor_Test_AbortReason_t reason)
{
  static const char *const names[] =
  {
    "NONE",
    "USER_STOP",
    "EMERGENCY_STOP",
    "TIME_EXPIRED",
    "THROTTLE_NOT_LOW",
    "CH5_NOT_ENABLED",
    "CH6_NOT_ENABLED",
    "IBUS_TIMEOUT",
    "IBUS_INVALID",
    "ESC_NOT_SAFE",
    "INVALID_COMMAND",
    "INTERNAL_ERROR"
  };

  if ((uint32_t)reason >= (uint32_t)(sizeof(names) / sizeof(names[0])))
  {
    return "INTERNAL_ERROR";
  }
  return names[reason];
}
