#include "ibus_port.h"

#include "debug_cli_port.h"
#include "usart.h"

#define IBUS_PORT_RING_SIZE          256U
#define IBUS_PORT_RING_MASK          (IBUS_PORT_RING_SIZE - 1U)
#define IBUS_PORT_RESTART_PERIOD_MS  10U

static uint8_t ibus_port_ring[IBUS_PORT_RING_SIZE];
static uint8_t ibus_port_rx_byte;
static volatile uint16_t ibus_port_head;
static volatile uint16_t ibus_port_tail;
static volatile uint32_t ibus_port_bytes_received;
static volatile uint32_t ibus_port_ring_overflows;
static volatile uint32_t ibus_port_uart_errors;
static volatile uint32_t ibus_port_rx_restart_errors;
static volatile uint32_t ibus_port_last_uart_error;
static volatile uint8_t ibus_port_rx_armed;
static uint32_t ibus_port_last_restart_ms;

static HAL_StatusTypeDef IBus_Port_ArmReceive(void);

HAL_StatusTypeDef IBus_Port_Init(void)
{
  HAL_StatusTypeDef result;

  ibus_port_head = 0U;
  ibus_port_tail = 0U;
  ibus_port_bytes_received = 0U;
  ibus_port_ring_overflows = 0U;
  ibus_port_uart_errors = 0U;
  ibus_port_rx_restart_errors = 0U;
  ibus_port_last_uart_error = HAL_UART_ERROR_NONE;
  ibus_port_rx_armed = 0U;
  ibus_port_last_restart_ms = HAL_GetTick();

  result = IBus_Port_ArmReceive();
  if (result != HAL_OK)
  {
    ibus_port_rx_restart_errors++;
  }

  return result;
}

void IBus_Port_Service(void)
{
  uint32_t now_ms;

  if (ibus_port_rx_armed != 0U)
  {
    return;
  }

  now_ms = HAL_GetTick();
  if ((uint32_t)(now_ms - ibus_port_last_restart_ms) <
      IBUS_PORT_RESTART_PERIOD_MS)
  {
    return;
  }

  ibus_port_last_restart_ms = now_ms;
  if (IBus_Port_ArmReceive() != HAL_OK)
  {
    ibus_port_rx_restart_errors++;
  }
}

uint8_t IBus_Port_ReadByte(uint8_t *value)
{
  uint16_t tail;

  if (value == NULL)
  {
    return 0U;
  }

  tail = ibus_port_tail;
  if (tail == ibus_port_head)
  {
    return 0U;
  }

  *value = ibus_port_ring[tail];
  __DMB();
  ibus_port_tail = (uint16_t)((tail + 1U) & IBUS_PORT_RING_MASK);
  return 1U;
}

void IBus_Port_GetStats(IBus_PortStats_t *stats)
{
  uint32_t primask;

  if (stats == NULL)
  {
    return;
  }

  primask = __get_PRIMASK();
  __disable_irq();
  stats->bytes_received = ibus_port_bytes_received;
  stats->ring_overflows = ibus_port_ring_overflows;
  stats->uart_errors = ibus_port_uart_errors;
  stats->rx_restart_errors = ibus_port_rx_restart_errors;
  stats->last_uart_error = ibus_port_last_uart_error;
  stats->rx_armed = ibus_port_rx_armed;
  if (primask == 0U)
  {
    __enable_irq();
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  uint16_t head;
  uint16_t next_head;

  if (huart == &huart1)
  {
    Debug_CLI_Port_RxCpltCallback(huart);
    return;
  }
  if (huart != &huart2)
  {
    return;
  }

  ibus_port_rx_armed = 0U;
  ibus_port_bytes_received++;
  head = ibus_port_head;
  next_head = (uint16_t)((head + 1U) & IBUS_PORT_RING_MASK);
  if (next_head != ibus_port_tail)
  {
    ibus_port_ring[head] = ibus_port_rx_byte;
    __DMB();
    ibus_port_head = next_head;
  }
  else
  {
    /* Drop the new byte; unread buffered data is preserved. */
    ibus_port_ring_overflows++;
  }

  if (IBus_Port_ArmReceive() != HAL_OK)
  {
    ibus_port_rx_restart_errors++;
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
  HAL_StatusTypeDef abort_result;

  if (huart == &huart1)
  {
    Debug_CLI_Port_ErrorCallback(huart);
    return;
  }
  if (huart != &huart2)
  {
    return;
  }

  ibus_port_rx_armed = 0U;
  ibus_port_uart_errors++;
  ibus_port_last_uart_error = huart->ErrorCode;

  abort_result = HAL_UART_AbortReceive(huart);
  if (abort_result != HAL_OK)
  {
    ibus_port_rx_restart_errors++;
    return;
  }

  if (IBus_Port_ArmReceive() != HAL_OK)
  {
    ibus_port_rx_restart_errors++;
  }
}

static HAL_StatusTypeDef IBus_Port_ArmReceive(void)
{
  HAL_StatusTypeDef result;

  result = HAL_UART_Receive_IT(&huart2, &ibus_port_rx_byte, 1U);
  if (result == HAL_OK)
  {
    ibus_port_rx_armed = 1U;
  }

  return result;
}
