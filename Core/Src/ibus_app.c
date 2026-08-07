#include "ibus_app.h"

#include "debug_log.h"
#include "ibus_port.h"
#include "usart.h"

#include <stdio.h>

/*
 * Protocol facts independently implemented after auditing Betaflight at
 * dda912c8686039f4679b9f1fff31aa476d5f48f6. No driver code was copied.
 */
#define IBUS_FRAME_LENGTH             32U
#define IBUS_LENGTH_BYTE              0x20U
#define IBUS_COMMAND_BYTE             0x40U
#define IBUS_CHANNEL_DATA_OFFSET       2U
#define IBUS_CHECKSUM_DATA_LENGTH     30U
#define IBUS_CHANNEL_HIGH_MASK        0x0FU
#define IBUS_CHANNEL_MIN             750U
#define IBUS_CHANNEL_MAX            2250U
#define IBUS_STREAM_TIMEOUT_US    100000U
#define IBUS_MACHINE_PERIOD_US      50000U
#define IBUS_DATA_PERIOD_US       100000U
#define IBUS_DIAG_PERIOD_US      1000000U
#define IBUS_PROCESS_BYTE_BUDGET      256U
#define IBUS_UART_TIMEOUT_MS           25U

typedef enum
{
  IBUS_PARSER_WAIT_LENGTH = 0,
  IBUS_PARSER_WAIT_COMMAND,
  IBUS_PARSER_COLLECT_FRAME
} IBus_ParserState_t;

static IBus_State_t ibus_state;
static IBus_ParserState_t ibus_parser_state;
static uint8_t ibus_frame[IBUS_FRAME_LENGTH];
static uint8_t ibus_frame_index;
static uint8_t ibus_link_seen;
static uint32_t ibus_header_errors;
static uint32_t ibus_length_errors;
static uint32_t ibus_range_errors;
static uint32_t ibus_resync_count;
static uint32_t ibus_last_machine_print_us;
static uint32_t ibus_last_data_print_us;
static uint32_t ibus_last_diag_print_us;

static void IBus_App_ParseByte(uint8_t value, uint32_t now_us);
static void IBus_App_ValidateFrame(uint32_t now_us);
static void IBus_App_UpdateLink(uint32_t now_us);
static void IBus_App_PrintLinkLost(uint32_t age_us);
static void IBus_App_PrintLinkRecovered(void);
static void IBus_App_PrintMachine(uint32_t now_us);
static void IBus_App_PrintData(uint32_t now_us);
static void IBus_App_PrintDiagnostic(uint32_t now_us);

HAL_StatusTypeDef IBus_App_Init(void)
{
  HAL_StatusTypeDef result;

  ibus_state = (IBus_State_t){0};
  ibus_state.channel_count = IBUS_CHANNEL_COUNT;
  ibus_parser_state = IBUS_PARSER_WAIT_LENGTH;
  ibus_frame_index = 0U;
  ibus_link_seen = 0U;
  ibus_header_errors = 0U;
  ibus_length_errors = 0U;
  ibus_range_errors = 0U;
  ibus_resync_count = 0U;
  ibus_last_machine_print_us = micros();
  ibus_last_data_print_us = ibus_last_machine_print_us;
  ibus_last_diag_print_us = ibus_last_data_print_us;

  result = IBus_Port_Init();
  if (result == HAL_OK)
  {
    static const char message[] =
        "IBUS INIT: PASS, uart=USART2, baud=115200, rx_pin=PA3, "
        "mode=INTERRUPT\r\n";

    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)(sizeof(message) - 1U),
                            IBUS_UART_TIMEOUT_MS);
  }
  else
  {
    char message[80];
    int length;

    length = snprintf(message, sizeof(message),
                      "IBUS INIT: FAIL, stage=START_RX, hal_status=%u\r\n",
                      (unsigned int)result);
    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length,
                              IBUS_UART_TIMEOUT_MS);
    }
  }

  return result;
}

void IBus_App_Process(void)
{
  uint8_t value;
  uint16_t byte_count = 0U;
  uint32_t now_us;

  IBus_Port_Service();
  now_us = micros();
  while ((byte_count < IBUS_PROCESS_BYTE_BUDGET) &&
         (IBus_Port_ReadByte(&value) != 0U))
  {
    IBus_App_ParseByte(value, now_us);
    byte_count++;
  }

  now_us = micros();
  IBus_App_UpdateLink(now_us);

  if ((uint32_t)(now_us - ibus_last_machine_print_us) >=
      IBUS_MACHINE_PERIOD_US)
  {
    ibus_last_machine_print_us = now_us;
    IBus_App_PrintMachine(now_us);
  }

  if ((Debug_Log_IsFull() != 0U) &&
      (ibus_state.stream_alive != 0U) &&
      ((uint32_t)(now_us - ibus_last_data_print_us) >=
       IBUS_DATA_PERIOD_US))
  {
    ibus_last_data_print_us = now_us;
    IBus_App_PrintData(now_us);
  }

  if ((Debug_Log_IsFull() != 0U) &&
      ((uint32_t)(now_us - ibus_last_diag_print_us) >=
       IBUS_DIAG_PERIOD_US))
  {
    ibus_last_diag_print_us = now_us;
    IBus_App_PrintDiagnostic(now_us);
  }
}

void IBus_App_GetState(IBus_State_t *state)
{
  if (state != NULL)
  {
    *state = ibus_state;
  }
}

static void IBus_App_ParseByte(uint8_t value, uint32_t now_us)
{
  switch (ibus_parser_state)
  {
    case IBUS_PARSER_WAIT_LENGTH:
      if (value == IBUS_LENGTH_BYTE)
      {
        ibus_frame[0] = value;
        ibus_frame_index = 1U;
        ibus_parser_state = IBUS_PARSER_WAIT_COMMAND;
      }
      else
      {
        ibus_length_errors++;
        ibus_resync_count++;
      }
      break;

    case IBUS_PARSER_WAIT_COMMAND:
      if (value == IBUS_COMMAND_BYTE)
      {
        ibus_frame[1] = value;
        ibus_frame_index = 2U;
        ibus_parser_state = IBUS_PARSER_COLLECT_FRAME;
      }
      else
      {
        ibus_header_errors++;
        ibus_resync_count++;
        if (value == IBUS_LENGTH_BYTE)
        {
          ibus_frame[0] = value;
          ibus_frame_index = 1U;
        }
        else
        {
          ibus_frame_index = 0U;
          ibus_parser_state = IBUS_PARSER_WAIT_LENGTH;
        }
      }
      break;

    case IBUS_PARSER_COLLECT_FRAME:
      if (ibus_frame_index < IBUS_FRAME_LENGTH)
      {
        ibus_frame[ibus_frame_index] = value;
        ibus_frame_index++;
      }

      if (ibus_frame_index == IBUS_FRAME_LENGTH)
      {
        IBus_App_ValidateFrame(now_us);
        ibus_frame_index = 0U;
        ibus_parser_state = IBUS_PARSER_WAIT_LENGTH;
      }
      break;

    default:
      ibus_frame_index = 0U;
      ibus_parser_state = IBUS_PARSER_WAIT_LENGTH;
      ibus_resync_count++;
      break;
  }
}

static void IBus_App_ValidateFrame(uint32_t now_us)
{
  uint16_t channels[IBUS_CHANNEL_COUNT];
  uint16_t calculated_checksum = 0xFFFFU;
  uint16_t received_checksum;
  uint8_t index;

  if (ibus_frame[0] != IBUS_LENGTH_BYTE)
  {
    ibus_length_errors++;
    ibus_state.frame_valid = 0U;
    ibus_resync_count++;
    return;
  }
  if (ibus_frame[1] != IBUS_COMMAND_BYTE)
  {
    ibus_header_errors++;
    ibus_state.frame_valid = 0U;
    ibus_resync_count++;
    return;
  }

  for (index = 0U; index < IBUS_CHECKSUM_DATA_LENGTH; index++)
  {
    calculated_checksum =
        (uint16_t)(calculated_checksum - ibus_frame[index]);
  }
  received_checksum =
      (uint16_t)((uint16_t)ibus_frame[30] |
                 ((uint16_t)ibus_frame[31] << 8U));
  if (calculated_checksum != received_checksum)
  {
    ibus_state.checksum_errors++;
    ibus_state.frame_valid = 0U;
    ibus_resync_count++;
    return;
  }

  for (index = 0U; index < IBUS_CHANNEL_COUNT; index++)
  {
    uint8_t offset =
        (uint8_t)(IBUS_CHANNEL_DATA_OFFSET + (2U * index));

    channels[index] =
        (uint16_t)((uint16_t)ibus_frame[offset] |
                   (((uint16_t)ibus_frame[offset + 1U] &
                     IBUS_CHANNEL_HIGH_MASK) << 8U));
    if ((channels[index] < IBUS_CHANNEL_MIN) ||
        (channels[index] > IBUS_CHANNEL_MAX))
    {
      ibus_range_errors++;
      ibus_state.frame_valid = 0U;
      ibus_resync_count++;
      return;
    }
  }

  for (index = 0U; index < IBUS_CHANNEL_COUNT; index++)
  {
    ibus_state.channels[index] = channels[index];
  }
  ibus_state.last_valid_frame_us = now_us;
  ibus_state.valid_frames++;
  ibus_state.frame_age_us = 0U;
  ibus_state.frame_valid = 1U;

  if ((ibus_link_seen != 0U) && (ibus_state.stream_alive == 0U))
  {
    IBus_App_PrintLinkRecovered();
  }
  ibus_link_seen = 1U;
  ibus_state.stream_alive = 1U;
}

static void IBus_App_UpdateLink(uint32_t now_us)
{
  if (ibus_state.valid_frames == 0U)
  {
    ibus_state.frame_age_us = 0U;
    return;
  }

  ibus_state.frame_age_us =
      (uint32_t)(now_us - ibus_state.last_valid_frame_us);
  if ((ibus_state.stream_alive != 0U) &&
      (ibus_state.frame_age_us >= IBUS_STREAM_TIMEOUT_US))
  {
    ibus_state.stream_alive = 0U;
    IBus_App_PrintLinkLost(ibus_state.frame_age_us);
  }
}

static void IBus_App_PrintLinkLost(uint32_t age_us)
{
  char message[64];
  int length;

  length = snprintf(message, sizeof(message),
                    "IBUS LINK: LOST, age_ms=%lu\r\n",
                    (unsigned long)(age_us / 1000U));
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            IBUS_UART_TIMEOUT_MS);
  }
}

static void IBus_App_PrintLinkRecovered(void)
{
  static const char message[] = "IBUS LINK: RECOVERED\r\n";

  (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                          (uint16_t)(sizeof(message) - 1U),
                          IBUS_UART_TIMEOUT_MS);
}

static void IBus_App_PrintMachine(uint32_t now_us)
{
  IBus_PortStats_t port_stats;
  char message[224];
  int length;

  IBus_Port_GetStats(&port_stats);
  length = snprintf(
      message, sizeof(message),
      "@IBUS,%lu,%u,%lu,%u,%u,%u,%u,%u,%u,%u,%u,%lu,%lu,%lu,%lu\r\n",
      (unsigned long)now_us,
      (unsigned int)ibus_state.stream_alive,
      (unsigned long)(ibus_state.frame_age_us / 1000U),
      (unsigned int)ibus_state.channels[0],
      (unsigned int)ibus_state.channels[1],
      (unsigned int)ibus_state.channels[2],
      (unsigned int)ibus_state.channels[3],
      (unsigned int)ibus_state.channels[4],
      (unsigned int)ibus_state.channels[5],
      (unsigned int)ibus_state.channels[6],
      (unsigned int)ibus_state.channels[7],
      (unsigned long)ibus_state.valid_frames,
      (unsigned long)ibus_state.checksum_errors,
      (unsigned long)port_stats.uart_errors,
      (unsigned long)port_stats.ring_overflows);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            IBUS_UART_TIMEOUT_MS);
  }
}

static void IBus_App_PrintData(uint32_t now_us)
{
  IBus_PortStats_t port_stats;
  char message[320];
  int length;

  IBus_Port_GetStats(&port_stats);
  length = snprintf(
      message, sizeof(message),
      "IBUS DATA: t_us=%lu, age_ms=%lu, "
      "ch=[%u,%u,%u,%u,%u,%u,%u,%u], valid_frames=%lu, "
      "checksum_errors=%lu, uart_errors=%lu, ring_overflows=%lu, "
      "stream=OK\r\n",
      (unsigned long)now_us,
      (unsigned long)(ibus_state.frame_age_us / 1000U),
      (unsigned int)ibus_state.channels[0],
      (unsigned int)ibus_state.channels[1],
      (unsigned int)ibus_state.channels[2],
      (unsigned int)ibus_state.channels[3],
      (unsigned int)ibus_state.channels[4],
      (unsigned int)ibus_state.channels[5],
      (unsigned int)ibus_state.channels[6],
      (unsigned int)ibus_state.channels[7],
      (unsigned long)ibus_state.valid_frames,
      (unsigned long)ibus_state.checksum_errors,
      (unsigned long)port_stats.uart_errors,
      (unsigned long)port_stats.ring_overflows);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            IBUS_UART_TIMEOUT_MS);
  }
}

static void IBus_App_PrintDiagnostic(uint32_t now_us)
{
  IBus_PortStats_t port_stats;
  char message[320];
  int length;

  (void)now_us;
  IBus_Port_GetStats(&port_stats);
  length = snprintf(
      message, sizeof(message),
      "IBUS DIAG: bytes=%lu, valid=%lu, crc_err=%lu, "
      "header_err=%lu, length_err=%lu, range_err=%lu, resync=%lu, "
      "uart_err=%lu, restart_err=%lu, last_uart_error=0x%08lX, "
      "overflow=%lu, rx_armed=%u\r\n",
      (unsigned long)port_stats.bytes_received,
      (unsigned long)ibus_state.valid_frames,
      (unsigned long)ibus_state.checksum_errors,
      (unsigned long)ibus_header_errors,
      (unsigned long)ibus_length_errors,
      (unsigned long)ibus_range_errors,
      (unsigned long)ibus_resync_count,
      (unsigned long)port_stats.uart_errors,
      (unsigned long)port_stats.rx_restart_errors,
      (unsigned long)port_stats.last_uart_error,
      (unsigned long)port_stats.ring_overflows,
      (unsigned int)port_stats.rx_armed);
  if ((length > 0) && ((size_t)length < sizeof(message)))
  {
    (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                            (uint16_t)length,
                            IBUS_UART_TIMEOUT_MS);
  }
}
