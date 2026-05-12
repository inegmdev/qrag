/**
 * sample.c — Toy ECC/SRAM driver fixture for QuickRAG-TI tests.
 */

#include <stdint.h>
#include <stdbool.h>

#define ECC_BASE_ADDR   0x40000000U
#define ECC_CTRL_REG    (ECC_BASE_ADDR + 0x00U)
#define ECC_STATUS_REG  (ECC_BASE_ADDR + 0x04U)
#define ECC_ERR_ADDR    (ECC_BASE_ADDR + 0x08U)

typedef struct {
    uint32_t ctrl;
    uint32_t status;
    uint32_t err_addr;
    uint32_t reserved;
} ECC_Regs;

typedef struct {
    uint32_t base_addr;
    uint32_t size_bytes;
    bool     ecc_enabled;
} SRAM_Config;

/**
 * enable_ecc - Enable error correction on SRAM.
 * Writes the ECC enable bit to the control register.
 */
int enable_ecc(uint32_t base_addr)
{
    volatile ECC_Regs *regs = (volatile ECC_Regs *)base_addr;
    regs->ctrl |= (1U << 0);  /* ECC_EN bit */
    return 0;
}

/**
 * disable_ecc - Disable error correction on SRAM.
 */
int disable_ecc(uint32_t base_addr)
{
    volatile ECC_Regs *regs = (volatile ECC_Regs *)base_addr;
    regs->ctrl &= ~(1U << 0);
    return 0;
}

/**
 * get_ecc_status - Read ECC status register.
 * Returns the raw status word; bit 0 = single-bit error, bit 1 = double-bit error.
 */
uint32_t get_ecc_status(uint32_t base_addr)
{
    volatile ECC_Regs *regs = (volatile ECC_Regs *)base_addr;
    return regs->status;
}

/**
 * clear_ecc_error - Clear latched ECC error flags.
 */
void clear_ecc_error(uint32_t base_addr)
{
    volatile ECC_Regs *regs = (volatile ECC_Regs *)base_addr;
    regs->status = 0U;
}

/**
 * sram_init - Initialize SRAM region with optional ECC.
 */
int sram_init(SRAM_Config *cfg)
{
    if (cfg == NULL)
        return -1;

    if (cfg->ecc_enabled)
        enable_ecc(cfg->base_addr);

    return 0;
}

/**
 * sram_read_word - Read a 32-bit word from SRAM at the given offset.
 */
uint32_t sram_read_word(uint32_t base_addr, uint32_t offset)
{
    volatile uint32_t *ptr = (volatile uint32_t *)(base_addr + offset);
    return *ptr;
}

/**
 * sram_write_word - Write a 32-bit word to SRAM at the given offset.
 */
void sram_write_word(uint32_t base_addr, uint32_t offset, uint32_t value)
{
    volatile uint32_t *ptr = (volatile uint32_t *)(base_addr + offset);
    *ptr = value;
}

/**
 * ecc_inject_error - Inject a single-bit ECC error for testing (test mode only).
 */
int ecc_inject_error(uint32_t base_addr, uint32_t target_addr)
{
    volatile ECC_Regs *regs = (volatile ECC_Regs *)base_addr;
    regs->err_addr = target_addr;
    regs->ctrl |= (1U << 4);  /* INJECT bit */
    return 0;
}
