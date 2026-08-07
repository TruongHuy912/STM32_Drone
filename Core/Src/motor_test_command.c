#include "motor_test_command.h"

#include <stddef.h>
#include <string.h>

#define MOTOR_TEST_MIN_MOTOR        1U
#define MOTOR_TEST_MAX_MOTOR        4U
#define MOTOR_TEST_MIN_PULSE_US  1020U
#define MOTOR_TEST_MAX_PULSE_US  1100U
#define MOTOR_TEST_MIN_DURATION_MS 100U
#define MOTOR_TEST_MAX_DURATION_MS 2000U

typedef enum
{
  PARSE_UINT_OK = 0,
  PARSE_UINT_INVALID,
  PARSE_UINT_OVERFLOW
} Parse_UintResult_t;

static const char *Motor_Test_SkipSpaces(const char *cursor);
static uint8_t Motor_Test_MatchWord(const char **cursor, const char *word);
static Parse_UintResult_t Motor_Test_ParseUint32(const char **cursor,
                                                 uint32_t *value);
static Motor_Test_ParseResult_t Motor_Test_MapUintResult(
    Parse_UintResult_t result);

Motor_Test_ParseResult_t Motor_Test_Command_Parse(
    const char *line,
    Motor_Test_Command_t *command)
{
  const char *cursor;
  uint32_t motor;
  uint32_t pulse_us;
  uint32_t duration_ms;
  Parse_UintResult_t uint_result;

  if ((line == NULL) || (command == NULL))
  {
    return MOTOR_TEST_PARSE_EMPTY;
  }

  *command = (Motor_Test_Command_t){0};
  cursor = Motor_Test_SkipSpaces(line);
  if (*cursor == '\0')
  {
    return MOTOR_TEST_PARSE_EMPTY;
  }

  if ((cursor[0] == '!') &&
      (*Motor_Test_SkipSpaces(&cursor[1]) == '\0'))
  {
    command->type = MOTOR_TEST_COMMAND_EMERGENCY_STOP;
    return MOTOR_TEST_PARSE_OK;
  }

  if (Motor_Test_MatchWord(&cursor, "MTEST") == 0U)
  {
    if (Motor_Test_MatchWord(&cursor, "LOG") == 0U)
    {
      return MOTOR_TEST_PARSE_UNKNOWN;
    }
    cursor = Motor_Test_SkipSpaces(cursor);
    if (Motor_Test_MatchWord(&cursor, "QUIET") != 0U)
    {
      command->type = MOTOR_TEST_COMMAND_LOG_QUIET;
    }
    else if (Motor_Test_MatchWord(&cursor, "FULL") != 0U)
    {
      command->type = MOTOR_TEST_COMMAND_LOG_FULL;
    }
    else if (Motor_Test_MatchWord(&cursor, "STATUS") != 0U)
    {
      command->type = MOTOR_TEST_COMMAND_LOG_STATUS;
    }
    else
    {
      return MOTOR_TEST_PARSE_UNKNOWN;
    }
    return (*Motor_Test_SkipSpaces(cursor) == '\0') ?
        MOTOR_TEST_PARSE_OK : MOTOR_TEST_PARSE_FIELD_COUNT;
  }
  cursor = Motor_Test_SkipSpaces(cursor);

  if (Motor_Test_MatchWord(&cursor, "STATUS") != 0U)
  {
    if (*Motor_Test_SkipSpaces(cursor) != '\0')
    {
      return MOTOR_TEST_PARSE_FIELD_COUNT;
    }
    command->type = MOTOR_TEST_COMMAND_STATUS;
    return MOTOR_TEST_PARSE_OK;
  }

  if (Motor_Test_MatchWord(&cursor, "STOP") != 0U)
  {
    if (*Motor_Test_SkipSpaces(cursor) != '\0')
    {
      return MOTOR_TEST_PARSE_FIELD_COUNT;
    }
    command->type = MOTOR_TEST_COMMAND_STOP;
    return MOTOR_TEST_PARSE_OK;
  }

  if (Motor_Test_MatchWord(&cursor, "RUN") == 0U)
  {
    return MOTOR_TEST_PARSE_UNKNOWN;
  }

  cursor = Motor_Test_SkipSpaces(cursor);
  uint_result = Motor_Test_ParseUint32(&cursor, &motor);
  if (uint_result != PARSE_UINT_OK)
  {
    return Motor_Test_MapUintResult(uint_result);
  }
  cursor = Motor_Test_SkipSpaces(cursor);
  uint_result = Motor_Test_ParseUint32(&cursor, &pulse_us);
  if (uint_result != PARSE_UINT_OK)
  {
    return Motor_Test_MapUintResult(uint_result);
  }
  cursor = Motor_Test_SkipSpaces(cursor);
  uint_result = Motor_Test_ParseUint32(&cursor, &duration_ms);
  if (uint_result != PARSE_UINT_OK)
  {
    return Motor_Test_MapUintResult(uint_result);
  }
  if (*Motor_Test_SkipSpaces(cursor) != '\0')
  {
    return MOTOR_TEST_PARSE_FIELD_COUNT;
  }

  if ((motor < MOTOR_TEST_MIN_MOTOR) || (motor > MOTOR_TEST_MAX_MOTOR))
  {
    return MOTOR_TEST_PARSE_MOTOR_RANGE;
  }
  if ((pulse_us < MOTOR_TEST_MIN_PULSE_US) ||
      (pulse_us > MOTOR_TEST_MAX_PULSE_US))
  {
    return MOTOR_TEST_PARSE_PULSE_RANGE;
  }
  if ((duration_ms < MOTOR_TEST_MIN_DURATION_MS) ||
      (duration_ms > MOTOR_TEST_MAX_DURATION_MS))
  {
    return MOTOR_TEST_PARSE_DURATION_RANGE;
  }

  command->type = MOTOR_TEST_COMMAND_RUN;
  command->motor = (uint8_t)motor;
  command->pulse_us = (uint16_t)pulse_us;
  command->duration_ms = (uint16_t)duration_ms;
  return MOTOR_TEST_PARSE_OK;
}

static const char *Motor_Test_SkipSpaces(const char *cursor)
{
  while (*cursor == ' ')
  {
    cursor++;
  }
  return cursor;
}

static uint8_t Motor_Test_MatchWord(const char **cursor, const char *word)
{
  size_t length = strlen(word);

  if ((strncmp(*cursor, word, length) != 0) ||
      (((*cursor)[length] != '\0') && ((*cursor)[length] != ' ')))
  {
    return 0U;
  }

  *cursor += length;
  return 1U;
}

static Parse_UintResult_t Motor_Test_ParseUint32(const char **cursor,
                                                 uint32_t *value)
{
  const char *position = *cursor;
  uint32_t parsed = 0U;

  if ((*position < '0') || (*position > '9'))
  {
    return PARSE_UINT_INVALID;
  }

  while ((*position >= '0') && (*position <= '9'))
  {
    uint32_t digit = (uint32_t)(*position - '0');

    if ((parsed > (UINT32_MAX / 10U)) ||
        ((parsed == (UINT32_MAX / 10U)) &&
         (digit > (UINT32_MAX % 10U))))
    {
      return PARSE_UINT_OVERFLOW;
    }
    parsed = (parsed * 10U) + digit;
    position++;
  }

  if ((*position != '\0') && (*position != ' '))
  {
    return PARSE_UINT_INVALID;
  }

  *cursor = position;
  *value = parsed;
  return PARSE_UINT_OK;
}

static Motor_Test_ParseResult_t Motor_Test_MapUintResult(
    Parse_UintResult_t result)
{
  return (result == PARSE_UINT_OVERFLOW) ?
      MOTOR_TEST_PARSE_NUMBER_OVERFLOW : MOTOR_TEST_PARSE_NUMBER_INVALID;
}
