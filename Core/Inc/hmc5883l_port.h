#ifndef HMC5883L_PORT_H
#define HMC5883L_PORT_H

#include "main.h"

typedef struct
{
  I2C_HandleTypeDef *hi2c;
  uint8_t address_7bit;
  uint32_t timeout_ms;
} HMC5883L_PortContext_t;

HAL_StatusTypeDef HMC5883L_Port_IsDeviceReady(
    const HMC5883L_PortContext_t *context,
    uint8_t address_7bit);
HAL_StatusTypeDef HMC5883L_Port_ReadRegisters(
    const HMC5883L_PortContext_t *context,
    uint8_t start_register,
    uint8_t *data,
    uint16_t length);
HAL_StatusTypeDef HMC5883L_Port_WriteRegister(
    const HMC5883L_PortContext_t *context,
    uint8_t register_address,
    uint8_t value);

#endif /* HMC5883L_PORT_H */
