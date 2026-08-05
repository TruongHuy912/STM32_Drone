#ifndef BMP388_PORT_H
#define BMP388_PORT_H

#include "main.h"
#include "bmp3.h"

typedef struct
{
  I2C_HandleTypeDef *hi2c;
  uint8_t address_7bit;
  uint32_t timeout_ms;
} BMP388_PortContext_t;

int8_t BMP388_Port_SelectAddress(BMP388_PortContext_t *context);
int8_t BMP388_Port_Configure(struct bmp3_dev *dev,
                             BMP388_PortContext_t *context);

#endif /* BMP388_PORT_H */
