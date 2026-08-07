#include "debug_log.h"

#include "usart.h"

#include <stdio.h>

#define DEBUG_LOG_UART_TIMEOUT_MS  25U

static Debug_Log_Mode_t debug_log_mode;

void Debug_Log_Init(void)
{
  debug_log_mode = DEBUG_LOG_MODE_FULL;
}

uint8_t Debug_Log_IsFull(void)
{
  return (debug_log_mode == DEBUG_LOG_MODE_FULL) ? 1U : 0U;
}

void Debug_Log_HandleCommand(const Motor_Test_Command_t *command)
{
  const char *command_name;
  const char *mode_name;
  char message[160];
  int length;

  if (command == NULL)
  {
    return;
  }

  switch (command->type)
  {
    case MOTOR_TEST_COMMAND_LOG_QUIET:
      debug_log_mode = DEBUG_LOG_MODE_QUIET;
      command_name = "LOG_QUIET";
      break;

    case MOTOR_TEST_COMMAND_LOG_FULL:
      debug_log_mode = DEBUG_LOG_MODE_FULL;
      command_name = "LOG_FULL";
      break;

    case MOTOR_TEST_COMMAND_LOG_STATUS:
      command_name = "LOG_STATUS";
      break;

    default:
      return;
  }

  mode_name = (debug_log_mode == DEBUG_LOG_MODE_FULL) ? "FULL" : "QUIET";
  length = snprintf(message, sizeof(message),
                    "LOG STATUS: mode=%s\r\n"
                    "@MACK,%lu,%s,1,NONE,0,1000,0\r\n",
                    mode_name,
                    (unsigned long)micros(),
                    command_name);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length, DEBUG_LOG_UART_TIMEOUT_MS);
  }
}
