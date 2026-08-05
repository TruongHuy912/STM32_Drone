#ifndef BMP388_APP_H
#define BMP388_APP_H

#include <stdint.h>

typedef struct
{
  uint32_t timestamp_us;
  uint32_t pressure_pa;
  int32_t temperature_centi_c;
  uint8_t drdy;
  int8_t last_result;
} BMP388_Sample_t;

int8_t BMP388_App_Init(void);
void BMP388_App_Process(void);

#endif /* BMP388_APP_H */
