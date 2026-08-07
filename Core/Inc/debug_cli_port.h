#ifndef DEBUG_CLI_PORT_H
#define DEBUG_CLI_PORT_H

#include "main.h"

typedef struct
{
  uint32_t bytes_received;
  uint32_t ring_overflows;
  uint32_t uart_errors;
  uint32_t restart_errors;
  uint32_t last_uart_error;
  uint8_t rx_armed;
} Debug_CLI_PortStats_t;

HAL_StatusTypeDef Debug_CLI_Port_Init(void);
void Debug_CLI_Process(void);
void Debug_CLI_Port_GetStats(Debug_CLI_PortStats_t *stats);
void Debug_CLI_Port_RxCpltCallback(UART_HandleTypeDef *huart);
void Debug_CLI_Port_ErrorCallback(UART_HandleTypeDef *huart);

#endif /* DEBUG_CLI_PORT_H */
