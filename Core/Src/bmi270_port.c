#include "bmi270_port.h"

#define BMI270_PORT_MAX_TRANSFER_LENGTH  (BMI2_MAX_LEN + 1U)
#define BMI270_PORT_READ_WRITE_LENGTH      64U
#define BMI270_PORT_SPI_READ_MASK          0x80U
#define BMI270_PORT_SPI_WRITE_MASK         0x7FU
#define BMI270_PORT_INTF_ERROR  ((BMI2_INTF_RETURN_TYPE)-1)

static BMI2_INTF_RETURN_TYPE BMI270_Port_Read(uint8_t reg_addr,
                                               uint8_t *reg_data,
                                               uint32_t len,
                                               void *intf_ptr);
static BMI2_INTF_RETURN_TYPE BMI270_Port_Write(uint8_t reg_addr,
                                                const uint8_t *reg_data,
                                                uint32_t len,
                                                void *intf_ptr);
static void BMI270_Port_DelayUs(uint32_t period, void *intf_ptr);

int8_t BMI270_Port_Configure(struct bmi2_dev *dev,
                             struct bmi270_port_context *context)
{
  if ((dev == NULL) || (context == NULL) || (context->spi == NULL) ||
      (context->cs_port == NULL))
  {
    return BMI2_E_NULL_PTR;
  }

  *dev = (struct bmi2_dev){0};
  dev->intf = BMI2_SPI_INTF;
  dev->read = BMI270_Port_Read;
  dev->write = BMI270_Port_Write;
  dev->delay_us = BMI270_Port_DelayUs;
  dev->intf_ptr = context;
  dev->read_write_len = BMI270_PORT_READ_WRITE_LENGTH;
  dev->config_file_ptr = NULL;

  HAL_GPIO_WritePin(context->cs_port, context->cs_pin, GPIO_PIN_SET);
  return BMI2_OK;
}

static BMI2_INTF_RETURN_TYPE BMI270_Port_Read(uint8_t reg_addr,
                                               uint8_t *reg_data,
                                               uint32_t len,
                                               void *intf_ptr)
{
  struct bmi270_port_context *context =
      (struct bmi270_port_context *)intf_ptr;
  uint8_t tx[BMI270_PORT_MAX_TRANSFER_LENGTH + 1U] = {0U};
  uint8_t rx[BMI270_PORT_MAX_TRANSFER_LENGTH + 1U] = {0U};
  HAL_StatusTypeDef status;
  uint32_t index;

  if ((context != NULL) && (context->cs_port != NULL))
  {
    HAL_GPIO_WritePin(context->cs_port, context->cs_pin, GPIO_PIN_SET);
  }

  if ((context == NULL) || (context->spi == NULL) ||
      (context->cs_port == NULL) || (reg_data == NULL) || (len == 0U) ||
      (len > BMI270_PORT_MAX_TRANSFER_LENGTH))
  {
    return BMI270_PORT_INTF_ERROR;
  }

  tx[0] = (uint8_t)(reg_addr | BMI270_PORT_SPI_READ_MASK);

  HAL_GPIO_WritePin(context->cs_port, context->cs_pin, GPIO_PIN_RESET);
  status = HAL_SPI_TransmitReceive(context->spi, tx, rx,
                                   (uint16_t)(len + 1U),
                                   context->timeout_ms);
  HAL_GPIO_WritePin(context->cs_port, context->cs_pin, GPIO_PIN_SET);

  if (status != HAL_OK)
  {
    return BMI270_PORT_INTF_ERROR;
  }

  for (index = 0U; index < len; index++)
  {
    reg_data[index] = rx[index + 1U];
  }

  return BMI2_INTF_RET_SUCCESS;
}

static BMI2_INTF_RETURN_TYPE BMI270_Port_Write(uint8_t reg_addr,
                                                const uint8_t *reg_data,
                                                uint32_t len,
                                                void *intf_ptr)
{
  struct bmi270_port_context *context =
      (struct bmi270_port_context *)intf_ptr;
  uint8_t tx[BMI270_PORT_MAX_TRANSFER_LENGTH + 1U] = {0U};
  uint8_t rx[BMI270_PORT_MAX_TRANSFER_LENGTH + 1U] = {0U};
  HAL_StatusTypeDef status;
  uint32_t index;

  if ((context != NULL) && (context->cs_port != NULL))
  {
    HAL_GPIO_WritePin(context->cs_port, context->cs_pin, GPIO_PIN_SET);
  }

  if ((context == NULL) || (context->spi == NULL) ||
      (context->cs_port == NULL) || (reg_data == NULL) || (len == 0U) ||
      (len > BMI270_PORT_MAX_TRANSFER_LENGTH))
  {
    return BMI270_PORT_INTF_ERROR;
  }

  tx[0] = (uint8_t)(reg_addr & BMI270_PORT_SPI_WRITE_MASK);
  for (index = 0U; index < len; index++)
  {
    tx[index + 1U] = reg_data[index];
  }

  HAL_GPIO_WritePin(context->cs_port, context->cs_pin, GPIO_PIN_RESET);
  status = HAL_SPI_TransmitReceive(context->spi, tx, rx,
                                   (uint16_t)(len + 1U),
                                   context->timeout_ms);
  HAL_GPIO_WritePin(context->cs_port, context->cs_pin, GPIO_PIN_SET);

  return (status == HAL_OK) ? BMI2_INTF_RET_SUCCESS
                            : BMI270_PORT_INTF_ERROR;
}

static void BMI270_Port_DelayUs(uint32_t period, void *intf_ptr)
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
