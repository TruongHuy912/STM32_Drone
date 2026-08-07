#include "motor_test_command.h"

#include <stdio.h>

static unsigned int failures;

static void ExpectResult(const char *line,
                         Motor_Test_ParseResult_t expected_result,
                         Motor_Test_CommandType_t expected_type)
{
  Motor_Test_Command_t command;
  Motor_Test_ParseResult_t result = Motor_Test_Command_Parse(line, &command);

  if ((result != expected_result) ||
      ((result == MOTOR_TEST_PARSE_OK) && (command.type != expected_type)))
  {
    (void)printf("FAIL: '%s' result=%u type=%u\n", line,
                 (unsigned int)result, (unsigned int)command.type);
    failures++;
  }
}

int main(void)
{
  Motor_Test_Command_t command;

  ExpectResult("MTEST STATUS", MOTOR_TEST_PARSE_OK,
               MOTOR_TEST_COMMAND_STATUS);
  ExpectResult("MTEST STOP", MOTOR_TEST_PARSE_OK,
               MOTOR_TEST_COMMAND_STOP);
  ExpectResult("!", MOTOR_TEST_PARSE_OK,
               MOTOR_TEST_COMMAND_EMERGENCY_STOP);
  ExpectResult("LOG QUIET", MOTOR_TEST_PARSE_OK,
               MOTOR_TEST_COMMAND_LOG_QUIET);
  ExpectResult("LOG FULL", MOTOR_TEST_PARSE_OK,
               MOTOR_TEST_COMMAND_LOG_FULL);
  ExpectResult("LOG STATUS", MOTOR_TEST_PARSE_OK,
               MOTOR_TEST_COMMAND_LOG_STATUS);
  ExpectResult("MTEST RUN 1 1050 1000", MOTOR_TEST_PARSE_OK,
               MOTOR_TEST_COMMAND_RUN);
  ExpectResult("MTEST RUN 4 1100 2000", MOTOR_TEST_PARSE_OK,
               MOTOR_TEST_COMMAND_RUN);

  ExpectResult("MTEST RUN 0 1050 1000", MOTOR_TEST_PARSE_MOTOR_RANGE,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 5 1050 1000", MOTOR_TEST_PARSE_MOTOR_RANGE,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 1 1019 1000", MOTOR_TEST_PARSE_PULSE_RANGE,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 1 1101 1000", MOTOR_TEST_PARSE_PULSE_RANGE,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 1 1050 99", MOTOR_TEST_PARSE_DURATION_RANGE,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 1 1050 2001", MOTOR_TEST_PARSE_DURATION_RANGE,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 1 1050", MOTOR_TEST_PARSE_NUMBER_INVALID,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 1 1050 1000 EXTRA", MOTOR_TEST_PARSE_FIELD_COUNT,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 1 -1050 1000", MOTOR_TEST_PARSE_NUMBER_INVALID,
               MOTOR_TEST_COMMAND_INVALID);
  ExpectResult("MTEST RUN 42949672960 1050 1000",
               MOTOR_TEST_PARSE_NUMBER_OVERFLOW,
               MOTOR_TEST_COMMAND_INVALID);

  if (Motor_Test_Command_Parse("MTEST RUN 2 1080 1500", &command) !=
      MOTOR_TEST_PARSE_OK)
  {
    failures++;
  }
  else if ((command.motor != 2U) || (command.pulse_us != 1080U) ||
           (command.duration_ms != 1500U))
  {
    (void)printf("FAIL: parsed RUN fields are incorrect\n");
    failures++;
  }

  if (failures != 0U)
  {
    (void)printf("motor_test_command_test: FAIL (%u)\n", failures);
    return 1;
  }

  (void)printf("motor_test_command_test: PASS\n");
  return 0;
}
