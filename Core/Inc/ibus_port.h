#ifndef IBUS_PORT_H
#define IBUS_PORT_H

#include "main.h"

typedef struct
{
  uint32_t bytes_received;
  uint32_t ring_overflows;
  uint32_t uart_errors;
  uint32_t rx_restart_errors;
  uint32_t last_uart_error;
  uint8_t rx_armed;
} IBus_PortStats_t;

HAL_StatusTypeDef IBus_Port_Init(void);
void IBus_Port_Service(void);
uint8_t IBus_Port_ReadByte(uint8_t *value);
void IBus_Port_GetStats(IBus_PortStats_t *stats);

#endif /* IBUS_PORT_H */
