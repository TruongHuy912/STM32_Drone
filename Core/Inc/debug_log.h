#ifndef DEBUG_LOG_H
#define DEBUG_LOG_H

#include "main.h"
#include "motor_test_command.h"

typedef enum
{
  DEBUG_LOG_MODE_QUIET = 0,
  DEBUG_LOG_MODE_FULL = 1
} Debug_Log_Mode_t;

void Debug_Log_Init(void);
uint8_t Debug_Log_IsFull(void);
void Debug_Log_HandleCommand(const Motor_Test_Command_t *command);

#endif /* DEBUG_LOG_H */
