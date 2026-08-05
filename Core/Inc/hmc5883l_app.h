#ifndef HMC5883L_APP_H
#define HMC5883L_APP_H

#include "main.h"

typedef struct
{
  uint32_t timestamp_us;

  int16_t raw_x;
  int16_t raw_y;
  int16_t raw_z;

  int32_t magnetic_nt_x;
  int32_t magnetic_nt_y;
  int32_t magnetic_nt_z;

  uint32_t magnitude_nt;

  uint8_t status;
  uint8_t valid;
} HMC5883L_Sample_t;

HAL_StatusTypeDef HMC5883L_App_Init(void);
void HMC5883L_App_Process(void);

#endif /* HMC5883L_APP_H */
