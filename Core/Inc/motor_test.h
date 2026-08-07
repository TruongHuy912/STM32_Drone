#ifndef MOTOR_TEST_H
#define MOTOR_TEST_H

#include "main.h"
#include "motor_test_command.h"

typedef enum
{
  MOTOR_TEST_DISABLED = 0,
  MOTOR_TEST_READY,
  MOTOR_TEST_RUNNING,
  MOTOR_TEST_FAULT
} Motor_Test_State_t;

typedef enum
{
  MOTOR_TEST_ABORT_NONE = 0,
  MOTOR_TEST_ABORT_USER_STOP,
  MOTOR_TEST_ABORT_EMERGENCY_STOP,
  MOTOR_TEST_ABORT_TIME_EXPIRED,
  MOTOR_TEST_ABORT_THROTTLE_NOT_LOW,
  MOTOR_TEST_ABORT_CH5_NOT_ENABLED,
  MOTOR_TEST_ABORT_CH6_NOT_ENABLED,
  MOTOR_TEST_ABORT_IBUS_TIMEOUT,
  MOTOR_TEST_ABORT_IBUS_INVALID,
  MOTOR_TEST_ABORT_ESC_NOT_SAFE,
  MOTOR_TEST_ABORT_INVALID_COMMAND,
  MOTOR_TEST_ABORT_INTERNAL_ERROR
} Motor_Test_AbortReason_t;

typedef struct
{
  Motor_Test_State_t state;
  uint8_t selected_motor;
  uint16_t commanded_pulse_us;
  uint16_t active_pulse_us;
  uint16_t duration_ms;
  uint16_t elapsed_ms;
  uint16_t remaining_ms;
  uint32_t run_count;
  uint32_t completed_count;
  uint32_t abort_count;
  uint32_t rejected_count;
  Motor_Test_AbortReason_t last_abort_reason;
  uint32_t safety_gate_mask;
} Motor_Test_Status_t;

void Motor_Test_Init(void);
void Motor_Test_Process(void);
void Motor_Test_HandleCommand(const Motor_Test_Command_t *command);
void Motor_Test_HandleParseError(Motor_Test_ParseResult_t parse_result);
void Motor_Test_LatchFault(Motor_Test_AbortReason_t reason);
const Motor_Test_Status_t *Motor_Test_GetStatus(void);

#endif /* MOTOR_TEST_H */
