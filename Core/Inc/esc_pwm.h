#ifndef ESC_PWM_H
#define ESC_PWM_H

#include "main.h"

#define ESC_PWM_MOTOR_COUNT          4U
#define ESC_PWM_SAFE_PULSE_US     1000U
#define ESC_PWM_BENCH_MIN_PULSE_US 1020U
#define ESC_PWM_BENCH_MAX_PULSE_US 1100U

typedef enum
{
  ESC_PWM_STATE_UNINITIALIZED = 0,
  ESC_PWM_STATE_SAFE,
  ESC_PWM_STATE_ERROR
} ESC_PWM_State_t;

typedef enum
{
  ESC_PWM_MOTOR_1 = 0,
  ESC_PWM_MOTOR_2,
  ESC_PWM_MOTOR_3,
  ESC_PWM_MOTOR_4
} ESC_PWM_Motor_t;

typedef struct
{
  ESC_PWM_State_t state;
  uint8_t started_mask;
  uint16_t pulse_us[ESC_PWM_MOTOR_COUNT];
  HAL_StatusTypeDef init_result;
  uint32_t start_error_count;
  uint32_t rejected_command_count;
} ESC_PWM_Status_t;

uint8_t ESC_PWM_Init(void);
uint8_t ESC_PWM_StartSafe(void);
void ESC_PWM_SetAllSafe(void);
uint8_t ESC_PWM_SetPulseUs(uint8_t motor_index, uint16_t pulse_us);
uint8_t ESC_PWM_SetSingleBenchPulseUs(uint8_t motor_index,
                                      uint16_t pulse_us);
uint8_t ESC_PWM_AreAllOutputsSafe(void);
uint8_t ESC_PWM_OutputsMatchSingleBench(uint8_t motor_index,
                                        uint16_t pulse_us);
void ESC_PWM_StopAll(void);
const ESC_PWM_Status_t *ESC_PWM_GetStatus(void);
void ESC_PWM_Process(void);

#endif /* ESC_PWM_H */
