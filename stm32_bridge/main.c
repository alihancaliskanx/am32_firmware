/*
 * USB-to-1-wire bridge for a NUCLEO-F446RE, for AM32/BLHeli ESC bootloaders.
 *
 * The ST-LINK virtual COM port is wired to PA2/PA3. Both are used as plain
 * GPIO: PA3 (host TX) is mirrored onto the ESC signal pin and the signal pin
 * is mirrored back onto PA2 (host RX), so the bridge is baud-rate agnostic.
 *
 * While the host is silent the signal pin is driven high push-pull. The AM32
 * bootloader samples the pin with its pull-down enabled at power-up and only
 * stays in the bootloader if it never reads low; a weak pull-up loses that
 * fight. Host activity switches the pin to input with pull-up so the ESC can
 * answer, and HOLD_AFTER_MS of silence on both sides drives it high again.
 *
 * Pins: PA10 (Arduino header D2) = ESC signal, PA5 = LD2 (on while holding).
 */

#include <stdint.h>

#define REG(addr) (*(volatile uint32_t *)(addr))

#define RCC_AHB1ENR REG(0x40023830)

#define GPIOA_MODER REG(0x40020000)
#define GPIOA_PUPDR REG(0x4002000C)
#define GPIOA_IDR REG(0x40020010)
#define GPIOA_BSRR REG(0x40020018)

#define SYST_CSR REG(0xE000E010)
#define SYST_RVR REG(0xE000E014)
#define SYST_CVR REG(0xE000E018)
#define SYST_COUNTFLAG (1u << 16)

#define TX_PIN 2
#define RX_PIN 3
#define LED_PIN 5
#define OW_PIN 10

#define SET(pin) (1u << (pin))
#define CLR(pin) (1u << ((pin) + 16))
#define MODE_MASK(pin) (3u << (2 * (pin)))
#define MODE_OUT(pin) (1u << (2 * (pin)))
#define PULL_UP(pin) (1u << (2 * (pin)))

#define HSI_HZ 16000000u
#define HOLD_AFTER_MS 500u

static inline uint32_t rx_high(void)
{
    return GPIOA_IDR & SET(RX_PIN);
}

static inline uint32_t ow_high(void)
{
    return GPIOA_IDR & SET(OW_PIN);
}

int main(void)
{
    RCC_AHB1ENR |= 1u;
    (void)RCC_AHB1ENR;

    GPIOA_BSRR = SET(TX_PIN) | SET(LED_PIN) | SET(OW_PIN);
    GPIOA_PUPDR = (GPIOA_PUPDR & ~(MODE_MASK(RX_PIN) | MODE_MASK(OW_PIN)))
                  | PULL_UP(RX_PIN) | PULL_UP(OW_PIN);

    /* PA13/PA14 stay in their SWD alternate function so the ST-LINK can reflash. */
    uint32_t moder_in = GPIOA_MODER
                        & ~(MODE_MASK(TX_PIN) | MODE_MASK(RX_PIN) | MODE_MASK(LED_PIN) | MODE_MASK(OW_PIN));
    moder_in |= MODE_OUT(TX_PIN) | MODE_OUT(LED_PIN);
    const uint32_t moder_out = moder_in | MODE_OUT(OW_PIN);

    SYST_RVR = HSI_HZ / 1000u - 1u;
    SYST_CVR = 0;
    SYST_CSR = 5u;

    for (;;) {
        GPIOA_BSRR = SET(OW_PIN) | SET(TX_PIN) | SET(LED_PIN);
        GPIOA_MODER = moder_out;
        while (rx_high())
            ;
        GPIOA_BSRR = CLR(LED_PIN);

        uint32_t idle_ms = 0;
        (void)SYST_CSR;
        while (idle_ms < HOLD_AFTER_MS) {
            if (!rx_high()) {
                GPIOA_BSRR = CLR(OW_PIN) | CLR(TX_PIN);
                GPIOA_MODER = moder_out;
                while (!rx_high())
                    ;
                /* Drive the rising edge, then let the pull-ups hold it. */
                GPIOA_BSRR = SET(OW_PIN) | SET(TX_PIN);
                GPIOA_MODER = moder_in;
                idle_ms = 0;
                (void)SYST_CSR;
            } else if (ow_high()) {
                GPIOA_BSRR = SET(TX_PIN);
                if (SYST_CSR & SYST_COUNTFLAG)
                    idle_ms++;
            } else {
                GPIOA_BSRR = CLR(TX_PIN);
                idle_ms = 0;
            }
        }
    }
}
