#ifndef BMI270_PORT_H
#define BMI270_PORT_H

#include "main.h"
#include "bmi270.h"

struct bmi270_port_context
{
  SPI_HandleTypeDef *spi;
  GPIO_TypeDef *cs_port;
  uint16_t cs_pin;
  uint32_t timeout_ms;
};

int8_t BMI270_Port_Configure(struct bmi2_dev *dev,
                             struct bmi270_port_context *context);

#endif /* BMI270_PORT_H */
