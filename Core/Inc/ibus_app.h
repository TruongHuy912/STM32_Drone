#ifndef IBUS_APP_H
#define IBUS_APP_H

#include "main.h"

#define IBUS_CHANNEL_COUNT  14U

typedef struct
{
  uint16_t channels[IBUS_CHANNEL_COUNT];

  uint32_t last_valid_frame_us;
  uint32_t valid_frames;
  uint32_t checksum_errors;
  uint32_t frame_age_us;

  uint8_t channel_count;
  uint8_t frame_valid;
  uint8_t stream_alive;
} IBus_State_t;

HAL_StatusTypeDef IBus_App_Init(void);
void IBus_App_Process(void);

#endif /* IBUS_APP_H */
