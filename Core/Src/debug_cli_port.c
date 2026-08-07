#include "debug_cli_port.h"

#include "debug_log.h"
#include "motor_test.h"
#include "motor_test_command.h"
#include "usart.h"

#define DEBUG_CLI_RING_SIZE            128U
#define DEBUG_CLI_RING_MASK            (DEBUG_CLI_RING_SIZE - 1U)
#define DEBUG_CLI_LINE_SIZE             64U
#define DEBUG_CLI_PROCESS_BYTE_BUDGET  128U
#define DEBUG_CLI_RESTART_PERIOD_MS     10U
#define DEBUG_CLI_INTERBYTE_TIMEOUT_MS  250U

static uint8_t debug_cli_ring[DEBUG_CLI_RING_SIZE];
static uint8_t debug_cli_rx_byte;
static volatile uint16_t debug_cli_head;
static volatile uint16_t debug_cli_tail;
static volatile uint32_t debug_cli_bytes_received;
static volatile uint32_t debug_cli_ring_overflows;
static volatile uint32_t debug_cli_uart_errors;
static volatile uint32_t debug_cli_restart_errors;
static volatile uint32_t debug_cli_last_uart_error;
static volatile uint8_t debug_cli_rx_armed;
static volatile uint8_t debug_cli_safety_fault_pending;
static uint32_t debug_cli_last_restart_ms;
static char debug_cli_line[DEBUG_CLI_LINE_SIZE];
static uint8_t debug_cli_line_length;
static uint8_t debug_cli_discard_line;
static uint8_t debug_cli_previous_was_cr;
static uint32_t debug_cli_last_byte_ms;

static HAL_StatusTypeDef Debug_CLI_Port_ArmReceive(void);
static uint8_t Debug_CLI_Port_ReadByte(uint8_t *value);
static void Debug_CLI_ProcessByte(uint8_t value);
static void Debug_CLI_ProcessLine(void);

HAL_StatusTypeDef Debug_CLI_Port_Init(void)
{
  HAL_StatusTypeDef result;

  debug_cli_head = 0U;
  debug_cli_tail = 0U;
  debug_cli_bytes_received = 0U;
  debug_cli_ring_overflows = 0U;
  debug_cli_uart_errors = 0U;
  debug_cli_restart_errors = 0U;
  debug_cli_last_uart_error = HAL_UART_ERROR_NONE;
  debug_cli_rx_armed = 0U;
  debug_cli_safety_fault_pending = 0U;
  debug_cli_last_restart_ms = HAL_GetTick();
  debug_cli_line_length = 0U;
  debug_cli_discard_line = 0U;
  debug_cli_previous_was_cr = 0U;
  debug_cli_last_byte_ms = HAL_GetTick();

  HAL_NVIC_SetPriority(USART1_IRQn, 6U, 0U);
  HAL_NVIC_EnableIRQ(USART1_IRQn);

  result = Debug_CLI_Port_ArmReceive();
  if (result != HAL_OK)
  {
    debug_cli_restart_errors++;
    debug_cli_safety_fault_pending = 1U;
  }
  return result;
}

void Debug_CLI_Process(void)
{
  uint8_t value;
  uint8_t safety_fault_pending;
  uint16_t processed = 0U;
  uint32_t now_ms;
  uint32_t primask;

  primask = __get_PRIMASK();
  __disable_irq();
  safety_fault_pending = debug_cli_safety_fault_pending;
  debug_cli_safety_fault_pending = 0U;
  if (primask == 0U)
  {
    __enable_irq();
  }
  if (safety_fault_pending != 0U)
  {
    Motor_Test_LatchFault(MOTOR_TEST_ABORT_INTERNAL_ERROR);
  }

  if (debug_cli_rx_armed == 0U)
  {
    now_ms = HAL_GetTick();
    if ((uint32_t)(now_ms - debug_cli_last_restart_ms) >=
        DEBUG_CLI_RESTART_PERIOD_MS)
    {
      debug_cli_last_restart_ms = now_ms;
      if (Debug_CLI_Port_ArmReceive() != HAL_OK)
      {
        debug_cli_restart_errors++;
        Motor_Test_LatchFault(MOTOR_TEST_ABORT_INTERNAL_ERROR);
      }
    }
  }

  while ((processed < DEBUG_CLI_PROCESS_BYTE_BUDGET) &&
         (Debug_CLI_Port_ReadByte(&value) != 0U))
  {
    Debug_CLI_ProcessByte(value);
    processed++;
  }
}

void Debug_CLI_Port_GetStats(Debug_CLI_PortStats_t *stats)
{
  uint32_t primask;

  if (stats == NULL)
  {
    return;
  }

  primask = __get_PRIMASK();
  __disable_irq();
  stats->bytes_received = debug_cli_bytes_received;
  stats->ring_overflows = debug_cli_ring_overflows;
  stats->uart_errors = debug_cli_uart_errors;
  stats->restart_errors = debug_cli_restart_errors;
  stats->last_uart_error = debug_cli_last_uart_error;
  stats->rx_armed = debug_cli_rx_armed;
  if (primask == 0U)
  {
    __enable_irq();
  }
}

void Debug_CLI_Port_RxCpltCallback(UART_HandleTypeDef *huart)
{
  uint16_t head;
  uint16_t next_head;

  if (huart != &huart1)
  {
    return;
  }

  debug_cli_rx_armed = 0U;
  debug_cli_bytes_received++;
  head = debug_cli_head;
  next_head = (uint16_t)((head + 1U) & DEBUG_CLI_RING_MASK);
  if (next_head != debug_cli_tail)
  {
    debug_cli_ring[head] = debug_cli_rx_byte;
    __DMB();
    debug_cli_head = next_head;
  }
  else
  {
    debug_cli_ring_overflows++;
    debug_cli_safety_fault_pending = 1U;
  }

  if (Debug_CLI_Port_ArmReceive() != HAL_OK)
  {
    debug_cli_restart_errors++;
    debug_cli_safety_fault_pending = 1U;
  }
}

void Debug_CLI_Port_ErrorCallback(UART_HandleTypeDef *huart)
{
  HAL_StatusTypeDef abort_result;

  if (huart != &huart1)
  {
    return;
  }

  debug_cli_rx_armed = 0U;
  debug_cli_uart_errors++;
  debug_cli_last_uart_error = huart->ErrorCode;
  debug_cli_safety_fault_pending = 1U;

  abort_result = HAL_UART_AbortReceive(huart);
  if (abort_result != HAL_OK)
  {
    debug_cli_restart_errors++;
    return;
  }

  if (Debug_CLI_Port_ArmReceive() != HAL_OK)
  {
    debug_cli_restart_errors++;
  }
}

static HAL_StatusTypeDef Debug_CLI_Port_ArmReceive(void)
{
  HAL_StatusTypeDef result =
      HAL_UART_Receive_IT(&huart1, &debug_cli_rx_byte, 1U);

  if (result == HAL_OK)
  {
    debug_cli_rx_armed = 1U;
  }
  return result;
}

static uint8_t Debug_CLI_Port_ReadByte(uint8_t *value)
{
  uint16_t tail;

  if (value == NULL)
  {
    return 0U;
  }

  tail = debug_cli_tail;
  if (tail == debug_cli_head)
  {
    return 0U;
  }
  *value = debug_cli_ring[tail];
  __DMB();
  debug_cli_tail = (uint16_t)((tail + 1U) & DEBUG_CLI_RING_MASK);
  return 1U;
}

static void Debug_CLI_ProcessByte(uint8_t value)
{
  uint32_t now_ms = HAL_GetTick();

  if (((debug_cli_line_length != 0U) ||
       (debug_cli_discard_line != 0U)) &&
      ((uint32_t)(now_ms - debug_cli_last_byte_ms) >
       DEBUG_CLI_INTERBYTE_TIMEOUT_MS))
  {
    debug_cli_line_length = 0U;
    debug_cli_discard_line = 0U;
  }
  debug_cli_last_byte_ms = now_ms;

  if (value == (uint8_t)'!')
  {
    Motor_Test_Command_t command = {0};

    debug_cli_line_length = 0U;
    debug_cli_discard_line = 0U;
    debug_cli_previous_was_cr = 0U;
    command.type = MOTOR_TEST_COMMAND_EMERGENCY_STOP;
    Motor_Test_HandleCommand(&command);
    return;
  }

  if ((value == (uint8_t)'\r') || (value == (uint8_t)'\n'))
  {
    if ((value == (uint8_t)'\n') && (debug_cli_previous_was_cr != 0U))
    {
      debug_cli_previous_was_cr = 0U;
      return;
    }
    debug_cli_previous_was_cr =
        (value == (uint8_t)'\r') ? 1U : 0U;

    if (debug_cli_discard_line != 0U)
    {
      debug_cli_discard_line = 0U;
      debug_cli_line_length = 0U;
      Motor_Test_HandleParseError(MOTOR_TEST_PARSE_FIELD_COUNT);
    }
    else if (debug_cli_line_length != 0U)
    {
      Debug_CLI_ProcessLine();
    }
    return;
  }

  debug_cli_previous_was_cr = 0U;
  if ((value < 0x20U) || (value > 0x7EU))
  {
    if (debug_cli_discard_line == 0U)
    {
      Motor_Test_LatchFault(MOTOR_TEST_ABORT_INVALID_COMMAND);
    }
    debug_cli_discard_line = 1U;
    return;
  }
  if (debug_cli_discard_line != 0U)
  {
    return;
  }
  if (debug_cli_line_length >= (DEBUG_CLI_LINE_SIZE - 1U))
  {
    debug_cli_line_length = 0U;
    debug_cli_discard_line = 1U;
    Motor_Test_LatchFault(MOTOR_TEST_ABORT_INVALID_COMMAND);
    return;
  }

  debug_cli_line[debug_cli_line_length] = (char)value;
  debug_cli_line_length++;
}

static void Debug_CLI_ProcessLine(void)
{
  Motor_Test_Command_t command;
  Motor_Test_ParseResult_t result;

  debug_cli_line[debug_cli_line_length] = '\0';
  debug_cli_line_length = 0U;
  result = Motor_Test_Command_Parse(debug_cli_line, &command);
  if (result == MOTOR_TEST_PARSE_OK)
  {
    if ((command.type == MOTOR_TEST_COMMAND_LOG_QUIET) ||
        (command.type == MOTOR_TEST_COMMAND_LOG_FULL) ||
        (command.type == MOTOR_TEST_COMMAND_LOG_STATUS))
    {
      Debug_Log_HandleCommand(&command);
    }
    else
    {
      Motor_Test_HandleCommand(&command);
    }
  }
  else
  {
    Motor_Test_HandleParseError(result);
  }
}
