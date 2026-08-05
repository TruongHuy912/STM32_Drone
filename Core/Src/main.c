/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "i2c.h"
#include "spi.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define BMI270_CHIP_ID_REG       0x00U
#define BMI270_CHIP_ID_EXPECTED  0x24U
#define BMI270_SPI_READ_MASK     0x80U
#define BMI270_SPI_TIMEOUT_MS    50U
#define BMI270_I2C_ADDRESS_0     0x68U
#define BMI270_I2C_ADDRESS_1     0x69U
#define BMI270_I2C_READY_TRIALS  1U
#define BMI270_I2C_TIMEOUT_MS    50U
#define BMI270_UART_TIMEOUT_MS   100U
#define BMI270_SPI_BOOT_TEST_ENABLED  1U
#define BMI270_I2C_BOOT_TEST_ENABLED  0U
#define SPI2_LOOPBACK_BOOT_TEST_ENABLED  0U
#define SPI2_LOOPBACK_TIMEOUT_MS  50U
#define SPI2_PIN_BOOT_TEST_ENABLED  0U
#define SPI2_PIN_TEST_HOLD_MS      3000U
#define SPI2_PIN_TEST_UART_TIMEOUT_MS  100U
#define BMI270_BB_SPI_BOOT_TEST_ENABLED  0U
#define BMI270_BB_HALF_PERIOD_US    10U
#define BMI270_BB_CS_PIN            GPIO_PIN_12
#define BMI270_BB_SCK_PIN           GPIO_PIN_13
#define BMI270_BB_MISO_PIN          GPIO_PIN_14
#define BMI270_BB_MOSI_PIN          GPIO_PIN_15

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */
static uint32_t led_timestamp;
static uint32_t uart_timestamp;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
void PeriphCommonClock_Config(void);
/* USER CODE BEGIN PFP */
static HAL_StatusTypeDef BMI270_SPI_ReadRegister(uint8_t reg_addr,
                                                 uint8_t *value,
                                                 uint8_t raw_rx[3]);
static HAL_StatusTypeDef BMI270_I2C_ReadRegister(uint16_t device_address,
                                                 uint8_t register_address,
                                                 uint8_t *value);
static void BMI270_BB_DelayUs(uint32_t delay_us);
static uint8_t BMI270_BB_TransferByte(uint8_t tx_byte);
static void BMI270_BB_ReadRegister(uint8_t reg_addr,
                                   uint8_t *rx_address_phase,
                                   uint8_t *value);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
static HAL_StatusTypeDef BMI270_SPI_ReadRegister(uint8_t reg_addr,
                                                 uint8_t *value,
                                                 uint8_t raw_rx[3])
{
  uint8_t tx[3] = {(uint8_t)(reg_addr | BMI270_SPI_READ_MASK),
                   0x00U, 0x00U};
  uint8_t rx[3] = {0x00U, 0x00U, 0x00U};
  HAL_StatusTypeDef status;

  if ((value == NULL) || (raw_rx == NULL))
  {
    HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);
    return HAL_ERROR;
  }

  HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_RESET);
  status = HAL_SPI_TransmitReceive(&hspi2, tx, rx, 3U,
                                   BMI270_SPI_TIMEOUT_MS);
  HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);

  raw_rx[0] = rx[0];
  raw_rx[1] = rx[1];
  raw_rx[2] = rx[2];

  if (status == HAL_OK)
  {
    *value = rx[2];
  }

  return status;
}

static HAL_StatusTypeDef BMI270_I2C_ReadRegister(uint16_t device_address,
                                                 uint8_t register_address,
                                                 uint8_t *value)
{
  uint8_t register_value = 0x00U;
  HAL_StatusTypeDef status;

  if (value == NULL)
  {
    return HAL_ERROR;
  }

  status = HAL_I2C_Mem_Read(&hi2c2, device_address, register_address,
                            I2C_MEMADD_SIZE_8BIT, &register_value, 1U,
                            BMI270_I2C_TIMEOUT_MS);

  if (status == HAL_OK)
  {
    *value = register_value;
  }

  return status;
}

static void BMI270_BB_DelayUs(uint32_t delay_us)
{
  uint32_t start = micros();

  while ((uint32_t)(micros() - start) < delay_us)
  {
    __NOP();
  }
}

static uint8_t BMI270_BB_TransferByte(uint8_t tx_byte)
{
  uint8_t rx_byte = 0x00U;
  uint8_t bit_mask;

  for (bit_mask = 0x80U; bit_mask != 0x00U; bit_mask >>= 1U)
  {
    HAL_GPIO_WritePin(GPIOB, BMI270_BB_MOSI_PIN,
                      ((tx_byte & bit_mask) != 0U) ? GPIO_PIN_SET
                                                  : GPIO_PIN_RESET);
    BMI270_BB_DelayUs(BMI270_BB_HALF_PERIOD_US);

    HAL_GPIO_WritePin(GPIOB, BMI270_BB_SCK_PIN, GPIO_PIN_SET);
    BMI270_BB_DelayUs(BMI270_BB_HALF_PERIOD_US);

    rx_byte <<= 1U;
    if (HAL_GPIO_ReadPin(GPIOB, BMI270_BB_MISO_PIN) == GPIO_PIN_SET)
    {
      rx_byte |= 0x01U;
    }

    HAL_GPIO_WritePin(GPIOB, BMI270_BB_SCK_PIN, GPIO_PIN_RESET);
    BMI270_BB_DelayUs(BMI270_BB_HALF_PERIOD_US);
  }

  HAL_GPIO_WritePin(GPIOB, BMI270_BB_SCK_PIN, GPIO_PIN_RESET);
  return rx_byte;
}

static void BMI270_BB_ReadRegister(uint8_t reg_addr,
                                   uint8_t *rx_address_phase,
                                   uint8_t *value)
{
  uint8_t address_rx;
  uint8_t data_rx;

  HAL_GPIO_WritePin(GPIOB, BMI270_BB_CS_PIN, GPIO_PIN_RESET);
  BMI270_BB_DelayUs(10U);

  address_rx = BMI270_BB_TransferByte((uint8_t)(reg_addr | 0x80U));
  data_rx = BMI270_BB_TransferByte(0x00U);

  BMI270_BB_DelayUs(10U);
  HAL_GPIO_WritePin(GPIOB, BMI270_BB_CS_PIN, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOB, BMI270_BB_SCK_PIN, GPIO_PIN_RESET);
  BMI270_BB_DelayUs(100U);

  if (rx_address_phase != NULL)
  {
    *rx_address_phase = address_rx;
  }
  if (value != NULL)
  {
    *value = data_rx;
  }
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* Configure the peripherals common clocks */
  PeriphCommonClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM2_Init();
  MX_USART1_UART_Init();
  MX_I2C2_Init();
  MX_SPI2_Init();
  /* USER CODE BEGIN 2 */
  if (HAL_TIM_Base_Start(&htim2) != HAL_OK)
  {
    Error_Handler();
  }

  led_timestamp = micros();
  uart_timestamp = led_timestamp;

  if (BMI270_SPI_BOOT_TEST_ENABLED != 0U)
  {
    uint8_t first_chip_id = 0x00U;
    uint8_t second_chip_id = 0x00U;
    uint8_t third_chip_id = 0x00U;
    uint8_t first_rx[3] = {0x00U, 0x00U, 0x00U};
    uint8_t second_rx[3] = {0x00U, 0x00U, 0x00U};
    uint8_t third_rx[3] = {0x00U, 0x00U, 0x00U};
    uint8_t chip_id;
    HAL_StatusTypeDef first_status;
    HAL_StatusTypeDef second_status;
    HAL_StatusTypeDef third_status;
    char message[224];
    int length;

    HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);
    HAL_Delay(10U);
    first_status = BMI270_SPI_ReadRegister(BMI270_CHIP_ID_REG,
                                           &first_chip_id, first_rx);
    HAL_Delay(1U);
    second_status = BMI270_SPI_ReadRegister(BMI270_CHIP_ID_REG,
                                            &second_chip_id, second_rx);
    HAL_Delay(2U);
    third_status = BMI270_SPI_ReadRegister(BMI270_CHIP_ID_REG,
                                           &third_chip_id, third_rx);

    length = snprintf(message, sizeof(message),
                      "BMI270 SPI3B: first_status=%u, "
                      "first_rx=[0x%02X,0x%02X,0x%02X], "
                      "second_status=%u, "
                      "second_rx=[0x%02X,0x%02X,0x%02X], "
                      "third_status=%u, "
                      "third_rx=[0x%02X,0x%02X,0x%02X]\r\n",
                      (unsigned int)first_status,
                      (unsigned int)first_rx[0],
                      (unsigned int)first_rx[1],
                      (unsigned int)first_rx[2],
                      (unsigned int)second_status,
                      (unsigned int)second_rx[0],
                      (unsigned int)second_rx[1],
                      (unsigned int)second_rx[2],
                      (unsigned int)third_status,
                      (unsigned int)third_rx[0],
                      (unsigned int)third_rx[1],
                      (unsigned int)third_rx[2]);
    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length, BMI270_UART_TIMEOUT_MS);
    }

    if ((second_rx[2] == BMI270_CHIP_ID_EXPECTED) ||
        (third_rx[2] == BMI270_CHIP_ID_EXPECTED))
    {
      chip_id = BMI270_CHIP_ID_EXPECTED;
      length = snprintf(message, sizeof(message),
                        "BMI270 SPI: PASS, chip_id=0x%02X\r\n",
                        (unsigned int)chip_id);
    }
    else
    {
      chip_id = second_rx[2];
      length = snprintf(message, sizeof(message),
                        "BMI270 SPI: FAIL, chip_id=0x%02X\r\n",
                        (unsigned int)chip_id);
    }

    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length, BMI270_UART_TIMEOUT_MS);
    }

    led_timestamp = micros();
    uart_timestamp = led_timestamp;
  }

  if (BMI270_I2C_BOOT_TEST_ENABLED != 0U)
  {
    uint8_t selected_address = 0x00U;
    uint8_t chip_id = 0x00U;
    HAL_StatusTypeDef ready_status_68;
    HAL_StatusTypeDef ready_status_69 = HAL_ERROR;
    HAL_StatusTypeDef ready_status;
    HAL_StatusTypeDef read_status;
    char message[112];
    int length;

    HAL_Delay(10U);
    ready_status_68 = HAL_I2C_IsDeviceReady(
        &hi2c2, (uint16_t)(BMI270_I2C_ADDRESS_0 << 1U),
        BMI270_I2C_READY_TRIALS, BMI270_I2C_TIMEOUT_MS);
    ready_status = ready_status_68;

    if (ready_status_68 == HAL_OK)
    {
      selected_address = BMI270_I2C_ADDRESS_0;
    }
    else
    {
      ready_status_69 = HAL_I2C_IsDeviceReady(
          &hi2c2, (uint16_t)(BMI270_I2C_ADDRESS_1 << 1U),
          BMI270_I2C_READY_TRIALS, BMI270_I2C_TIMEOUT_MS);
      ready_status = ready_status_69;
      if (ready_status_69 == HAL_OK)
      {
        selected_address = BMI270_I2C_ADDRESS_1;
      }
    }

    if (selected_address == 0x00U)
    {
      length = snprintf(message, sizeof(message),
                        "BMI270 I2C: FAIL, no_ack_0x68=%u, "
                        "no_ack_0x69=%u\r\n",
                        (unsigned int)ready_status_68,
                        (unsigned int)ready_status_69);
    }
    else
    {
      read_status = BMI270_I2C_ReadRegister(
          (uint16_t)(selected_address << 1U), BMI270_CHIP_ID_REG, &chip_id);

      if ((read_status == HAL_OK) &&
          (chip_id == BMI270_CHIP_ID_EXPECTED))
      {
        length = snprintf(message, sizeof(message),
                          "BMI270 I2C: PASS, address=0x%02X, "
                          "chip_id=0x%02X\r\n",
                          (unsigned int)selected_address,
                          (unsigned int)chip_id);
      }
      else
      {
        length = snprintf(message, sizeof(message),
                          "BMI270 I2C: FAIL, address=0x%02X, "
                          "chip_id=0x%02X, ready_status=%u, "
                          "read_status=%u\r\n",
                          (unsigned int)selected_address,
                          (unsigned int)chip_id,
                          (unsigned int)ready_status,
                          (unsigned int)read_status);
      }
    }

    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length, BMI270_UART_TIMEOUT_MS);
    }
  }

  if (SPI2_LOOPBACK_BOOT_TEST_ENABLED != 0U)
  {
    uint8_t tx[3] = {0xA5U, 0x5AU, 0xC3U};
    uint8_t rx[3] = {0x00U, 0x00U, 0x00U};
    HAL_StatusTypeDef status;
    char message[112];
    int length;

    HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);
    status = HAL_SPI_TransmitReceive(&hspi2, tx, rx, 3U,
                                     SPI2_LOOPBACK_TIMEOUT_MS);

    length = snprintf(message, sizeof(message),
                      "SPI2 LOOPBACK: status=%u, "
                      "tx=[0x%02X,0x%02X,0x%02X], "
                      "rx=[0x%02X,0x%02X,0x%02X]\r\n",
                      (unsigned int)status,
                      (unsigned int)tx[0], (unsigned int)tx[1],
                      (unsigned int)tx[2], (unsigned int)rx[0],
                      (unsigned int)rx[1], (unsigned int)rx[2]);
    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length, BMI270_UART_TIMEOUT_MS);
    }

    if ((status == HAL_OK) && (rx[0] == tx[0]) &&
        (rx[1] == tx[1]) && (rx[2] == tx[2]))
    {
      length = snprintf(message, sizeof(message), "SPI2 LOOPBACK: PASS\r\n");
    }
    else
    {
      length = snprintf(message, sizeof(message), "SPI2 LOOPBACK: FAIL\r\n");
    }

    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length, BMI270_UART_TIMEOUT_MS);
    }
  }

  if (SPI2_PIN_BOOT_TEST_ENABLED != 0U)
  {
    static const uint8_t cs_low_message[] = "PIN TEST: CS LOW\r\n";
    static const uint8_t cs_high_message[] = "PIN TEST: CS HIGH\r\n";
    static const uint8_t sck_low_message[] = "PIN TEST: SCK LOW\r\n";
    static const uint8_t sck_high_message[] = "PIN TEST: SCK HIGH\r\n";
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    (void)HAL_SPI_DeInit(&hspi2);

    __HAL_RCC_GPIOB_CLK_ENABLE();
    HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, GPIO_PIN_RESET);

    GPIO_InitStruct.Pin = BMI270_CS_Pin | GPIO_PIN_13;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_RESET);
    (void)HAL_UART_Transmit(&huart1, cs_low_message,
                            (uint16_t)(sizeof(cs_low_message) - 1U),
                            SPI2_PIN_TEST_UART_TIMEOUT_MS);
    HAL_Delay(SPI2_PIN_TEST_HOLD_MS);

    HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);
    (void)HAL_UART_Transmit(&huart1, cs_high_message,
                            (uint16_t)(sizeof(cs_high_message) - 1U),
                            SPI2_PIN_TEST_UART_TIMEOUT_MS);
    HAL_Delay(SPI2_PIN_TEST_HOLD_MS);

    HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, GPIO_PIN_RESET);
    (void)HAL_UART_Transmit(&huart1, sck_low_message,
                            (uint16_t)(sizeof(sck_low_message) - 1U),
                            SPI2_PIN_TEST_UART_TIMEOUT_MS);
    HAL_Delay(SPI2_PIN_TEST_HOLD_MS);

    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, GPIO_PIN_SET);
    (void)HAL_UART_Transmit(&huart1, sck_high_message,
                            (uint16_t)(sizeof(sck_high_message) - 1U),
                            SPI2_PIN_TEST_UART_TIMEOUT_MS);
    HAL_Delay(SPI2_PIN_TEST_HOLD_MS);

    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, GPIO_PIN_RESET);
    (void)HAL_UART_Transmit(&huart1, sck_low_message,
                            (uint16_t)(sizeof(sck_low_message) - 1U),
                            SPI2_PIN_TEST_UART_TIMEOUT_MS);
    HAL_Delay(SPI2_PIN_TEST_HOLD_MS);

    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_13, GPIO_PIN_SET);
    (void)HAL_UART_Transmit(&huart1, sck_high_message,
                            (uint16_t)(sizeof(sck_high_message) - 1U),
                            SPI2_PIN_TEST_UART_TIMEOUT_MS);
    HAL_Delay(SPI2_PIN_TEST_HOLD_MS);

    HAL_GPIO_WritePin(BMI270_CS_GPIO_Port, BMI270_CS_Pin, GPIO_PIN_SET);
    MX_SPI2_Init();
    led_timestamp = micros();
    uart_timestamp = led_timestamp;
  }

  if (BMI270_BB_SPI_BOOT_TEST_ENABLED != 0U)
  {
    uint8_t first_rx_address = 0x00U;
    uint8_t first_rx_data = 0x00U;
    uint8_t second_rx_address = 0x00U;
    uint8_t second_rx_data = 0x00U;
    uint8_t third_rx_address = 0x00U;
    uint8_t third_rx_data = 0x00U;
    uint8_t chip_id;
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    char message[128];
    int length;

    (void)HAL_SPI_DeInit(&hspi2);

    __HAL_RCC_GPIOB_CLK_ENABLE();
    HAL_GPIO_WritePin(GPIOB, BMI270_BB_CS_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOB, BMI270_BB_SCK_PIN | BMI270_BB_MOSI_PIN,
                      GPIO_PIN_RESET);

    GPIO_InitStruct.Pin = BMI270_BB_CS_PIN | BMI270_BB_SCK_PIN |
                          BMI270_BB_MOSI_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = BMI270_BB_MISO_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

    HAL_GPIO_WritePin(GPIOB, BMI270_BB_CS_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOB, BMI270_BB_SCK_PIN | BMI270_BB_MOSI_PIN,
                      GPIO_PIN_RESET);
    HAL_Delay(10U);

    BMI270_BB_ReadRegister(BMI270_CHIP_ID_REG,
                           &first_rx_address, &first_rx_data);
    HAL_Delay(10U);
    BMI270_BB_ReadRegister(BMI270_CHIP_ID_REG,
                           &second_rx_address, &second_rx_data);
    HAL_Delay(2U);
    BMI270_BB_ReadRegister(BMI270_CHIP_ID_REG,
                           &third_rx_address, &third_rx_data);

    HAL_GPIO_WritePin(GPIOB, BMI270_BB_CS_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOB, BMI270_BB_SCK_PIN | BMI270_BB_MOSI_PIN,
                      GPIO_PIN_RESET);

    length = snprintf(message, sizeof(message),
                      "BMI270 BB SPI: first=[0x%02X,0x%02X], "
                      "second=[0x%02X,0x%02X], "
                      "third=[0x%02X,0x%02X]\r\n",
                      (unsigned int)first_rx_address,
                      (unsigned int)first_rx_data,
                      (unsigned int)second_rx_address,
                      (unsigned int)second_rx_data,
                      (unsigned int)third_rx_address,
                      (unsigned int)third_rx_data);
    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length, BMI270_UART_TIMEOUT_MS);
    }

    if ((second_rx_data == BMI270_CHIP_ID_EXPECTED) ||
        (third_rx_data == BMI270_CHIP_ID_EXPECTED))
    {
      chip_id = BMI270_CHIP_ID_EXPECTED;
      length = snprintf(message, sizeof(message),
                        "BMI270 BB SPI: PASS, chip_id=0x%02X\r\n",
                        (unsigned int)chip_id);
    }
    else
    {
      chip_id = second_rx_data;
      length = snprintf(message, sizeof(message),
                        "BMI270 BB SPI: FAIL, chip_id=0x%02X\r\n",
                        (unsigned int)chip_id);
    }

    if ((length > 0) && ((size_t)length < sizeof(message)))
    {
      (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                              (uint16_t)length, BMI270_UART_TIMEOUT_MS);
    }

    led_timestamp = micros();
    uart_timestamp = led_timestamp;
  }

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    uint32_t now = micros();

    if ((uint32_t)(now - led_timestamp) >= 500000U)
    {
      led_timestamp += 500000U;
      HAL_GPIO_TogglePin(GPIOE, GPIO_PIN_3);
    }

    if ((uint32_t)(now - uart_timestamp) >= 1000000U)
    {
      char message[48];
      int length;

      uart_timestamp += 1000000U;
      length = snprintf(message, sizeof(message),
                        "H1 boot OK, micros=%lu\r\n", (unsigned long)now);
      if ((length > 0) && ((size_t)length < sizeof(message)))
      {
        (void)HAL_UART_Transmit(&huart1, (uint8_t *)message,
                                (uint16_t)length, HAL_MAX_DELAY);
      }
    }
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Supply configuration update enable
  */
  HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY);

  /** Configure the main internal regulator output voltage
  */
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  while(!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {}

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI|RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSIState = RCC_HSI_DIV1;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 5;
  RCC_OscInitStruct.PLL.PLLN = 160;
  RCC_OscInitStruct.PLL.PLLP = 2;
  RCC_OscInitStruct.PLL.PLLQ = 2;
  RCC_OscInitStruct.PLL.PLLR = 2;
  RCC_OscInitStruct.PLL.PLLRGE = RCC_PLL1VCIRANGE_2;
  RCC_OscInitStruct.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
  RCC_OscInitStruct.PLL.PLLFRACN = 0;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2
                              |RCC_CLOCKTYPE_D3PCLK1|RCC_CLOCKTYPE_D1PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.SYSCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB3CLKDivider = RCC_APB3_DIV2;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_APB2_DIV2;
  RCC_ClkInitStruct.APB4CLKDivider = RCC_APB4_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief Peripherals Common Clock Configuration
  * @retval None
  */
void PeriphCommonClock_Config(void)
{
  RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

  /** Initializes the peripherals clock
  */
  PeriphClkInitStruct.PeriphClockSelection = RCC_PERIPHCLK_CKPER;
  PeriphClkInitStruct.CkperClockSelection = RCC_CLKPSOURCE_HSI;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */
uint32_t micros(void)
{
  return __HAL_TIM_GET_COUNTER(&htim2);
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
