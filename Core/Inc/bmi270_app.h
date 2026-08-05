#ifndef BMI270_APP_H
#define BMI270_APP_H

#include <stdint.h>

typedef struct
{
  uint32_t timestamp_us;

  int16_t acc_raw_x;
  int16_t acc_raw_y;
  int16_t acc_raw_z;

  int16_t gyr_raw_x;
  int16_t gyr_raw_y;
  int16_t gyr_raw_z;

  int32_t acc_mg_x;
  int32_t acc_mg_y;
  int32_t acc_mg_z;

  int32_t gyr_mdps_x;
  int32_t gyr_mdps_y;
  int32_t gyr_mdps_z;

  uint8_t status;
} BMI270_Sample_t;

int8_t BMI270_App_Init(void);
void BMI270_App_Process(void);

#endif /* BMI270_APP_H */
