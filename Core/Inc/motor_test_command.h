#ifndef MOTOR_TEST_COMMAND_H
#define MOTOR_TEST_COMMAND_H

#include <stdint.h>

typedef enum
{
  MOTOR_TEST_COMMAND_INVALID = 0,
  MOTOR_TEST_COMMAND_STATUS,
  MOTOR_TEST_COMMAND_RUN,
  MOTOR_TEST_COMMAND_STOP,
  MOTOR_TEST_COMMAND_EMERGENCY_STOP,
  MOTOR_TEST_COMMAND_LOG_QUIET,
  MOTOR_TEST_COMMAND_LOG_FULL,
  MOTOR_TEST_COMMAND_LOG_STATUS
} Motor_Test_CommandType_t;

typedef enum
{
  MOTOR_TEST_PARSE_OK = 0,
  MOTOR_TEST_PARSE_EMPTY,
  MOTOR_TEST_PARSE_UNKNOWN,
  MOTOR_TEST_PARSE_FIELD_COUNT,
  MOTOR_TEST_PARSE_NUMBER_INVALID,
  MOTOR_TEST_PARSE_NUMBER_OVERFLOW,
  MOTOR_TEST_PARSE_MOTOR_RANGE,
  MOTOR_TEST_PARSE_PULSE_RANGE,
  MOTOR_TEST_PARSE_DURATION_RANGE
} Motor_Test_ParseResult_t;

typedef struct
{
  Motor_Test_CommandType_t type;
  uint8_t motor;
  uint16_t pulse_us;
  uint16_t duration_ms;
} Motor_Test_Command_t;

Motor_Test_ParseResult_t Motor_Test_Command_Parse(
    const char *line,
    Motor_Test_Command_t *command);

#endif /* MOTOR_TEST_COMMAND_H */
