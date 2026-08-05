#include "hmc5883l_port.h"

#define HMC5883L_PORT_READY_TRIALS  1U

HAL_StatusTypeDef HMC5883L_Port_IsDeviceReady(
    const HMC5883L_PortContext_t *context,
    uint8_t address_7bit)
{
  if ((context == NULL) || (context->hi2c == NULL))
  {
    return HAL_ERROR;
  }

  return HAL_I2C_IsDeviceReady(
      context->hi2c, (uint16_t)(address_7bit << 1U),
      HMC5883L_PORT_READY_TRIALS, context->timeout_ms);
}

HAL_StatusTypeDef HMC5883L_Port_ReadRegisters(
    const HMC5883L_PortContext_t *context,
    uint8_t start_register,
    uint8_t *data,
    uint16_t length)
{
  if ((context == NULL) || (context->hi2c == NULL) ||
      (data == NULL) || (length == 0U))
  {
    return HAL_ERROR;
  }

  return HAL_I2C_Mem_Read(
      context->hi2c, (uint16_t)(context->address_7bit << 1U),
      start_register, I2C_MEMADD_SIZE_8BIT, data, length,
      context->timeout_ms);
}

HAL_StatusTypeDef HMC5883L_Port_WriteRegister(
    const HMC5883L_PortContext_t *context,
    uint8_t register_address,
    uint8_t value)
{
  if ((context == NULL) || (context->hi2c == NULL))
  {
    return HAL_ERROR;
  }

  return HAL_I2C_Mem_Write(
      context->hi2c, (uint16_t)(context->address_7bit << 1U),
      register_address, I2C_MEMADD_SIZE_8BIT, &value, 1U,
      context->timeout_ms);
}
