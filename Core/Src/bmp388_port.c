#include "bmp388_port.h"

#define BMP388_PORT_READY_TRIALS  1U
#define BMP388_PORT_INTF_ERROR    ((BMP3_INTF_RET_TYPE)-1)

static BMP3_INTF_RET_TYPE BMP388_Port_Read(uint8_t reg_addr,
                                            uint8_t *reg_data,
                                            uint32_t len,
                                            void *intf_ptr);
static BMP3_INTF_RET_TYPE BMP388_Port_Write(uint8_t reg_addr,
                                             const uint8_t *reg_data,
                                             uint32_t len,
                                             void *intf_ptr);
static void BMP388_Port_DelayUs(uint32_t period, void *intf_ptr);

int8_t BMP388_Port_SelectAddress(BMP388_PortContext_t *context)
{
  HAL_StatusTypeDef status;

  if ((context == NULL) || (context->hi2c == NULL))
  {
    return BMP3_E_NULL_PTR;
  }

  context->address_7bit = 0U;
  status = HAL_I2C_IsDeviceReady(
      context->hi2c, (uint16_t)(BMP3_ADDR_I2C_PRIM << 1U),
      BMP388_PORT_READY_TRIALS, context->timeout_ms);
  if (status == HAL_OK)
  {
    context->address_7bit = BMP3_ADDR_I2C_PRIM;
    return BMP3_OK;
  }

  status = HAL_I2C_IsDeviceReady(
      context->hi2c, (uint16_t)(BMP3_ADDR_I2C_SEC << 1U),
      BMP388_PORT_READY_TRIALS, context->timeout_ms);
  if (status == HAL_OK)
  {
    context->address_7bit = BMP3_ADDR_I2C_SEC;
    return BMP3_OK;
  }

  return BMP3_E_DEV_NOT_FOUND;
}

int8_t BMP388_Port_Configure(struct bmp3_dev *dev,
                             BMP388_PortContext_t *context)
{
  if ((dev == NULL) || (context == NULL) || (context->hi2c == NULL) ||
      (context->address_7bit == 0U))
  {
    return BMP3_E_NULL_PTR;
  }

  *dev = (struct bmp3_dev){0};
  dev->intf = BMP3_I2C_INTF;
  dev->read = BMP388_Port_Read;
  dev->write = BMP388_Port_Write;
  dev->delay_us = BMP388_Port_DelayUs;
  dev->intf_ptr = context;
  dev->dummy_byte = 0U;

  return BMP3_OK;
}

static BMP3_INTF_RET_TYPE BMP388_Port_Read(uint8_t reg_addr,
                                            uint8_t *reg_data,
                                            uint32_t len,
                                            void *intf_ptr)
{
  BMP388_PortContext_t *context = (BMP388_PortContext_t *)intf_ptr;
  HAL_StatusTypeDef status;

  if ((context == NULL) || (context->hi2c == NULL) ||
      ((len > 0U) && (reg_data == NULL)) || (len > UINT16_MAX))
  {
    return BMP388_PORT_INTF_ERROR;
  }
  if (len == 0U)
  {
    return BMP3_INTF_RET_SUCCESS;
  }

  status = HAL_I2C_Mem_Read(
      context->hi2c, (uint16_t)(context->address_7bit << 1U),
      reg_addr, I2C_MEMADD_SIZE_8BIT, reg_data, (uint16_t)len,
      context->timeout_ms);

  return (status == HAL_OK) ? BMP3_INTF_RET_SUCCESS
                            : BMP388_PORT_INTF_ERROR;
}

static BMP3_INTF_RET_TYPE BMP388_Port_Write(uint8_t reg_addr,
                                             const uint8_t *reg_data,
                                             uint32_t len,
                                             void *intf_ptr)
{
  BMP388_PortContext_t *context = (BMP388_PortContext_t *)intf_ptr;
  HAL_StatusTypeDef status;

  if ((context == NULL) || (context->hi2c == NULL) ||
      ((len > 0U) && (reg_data == NULL)) || (len > UINT16_MAX))
  {
    return BMP388_PORT_INTF_ERROR;
  }
  if (len == 0U)
  {
    return BMP3_INTF_RET_SUCCESS;
  }

  status = HAL_I2C_Mem_Write(
      context->hi2c, (uint16_t)(context->address_7bit << 1U),
      reg_addr, I2C_MEMADD_SIZE_8BIT, (uint8_t *)reg_data,
      (uint16_t)len, context->timeout_ms);

  return (status == HAL_OK) ? BMP3_INTF_RET_SUCCESS
                            : BMP388_PORT_INTF_ERROR;
}

static void BMP388_Port_DelayUs(uint32_t period, void *intf_ptr)
{
  uint32_t milliseconds = period / 1000U;
  uint32_t microseconds = period % 1000U;
  uint32_t start;

  (void)intf_ptr;

  if (milliseconds > 0U)
  {
    HAL_Delay(milliseconds);
  }

  start = micros();
  while ((uint32_t)(micros() - start) < microseconds)
  {
    __NOP();
  }
}
