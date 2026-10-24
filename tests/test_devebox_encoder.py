"""Exercise actual rotary decoding and DevEBox PE9/PE14 extraction on host."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
SRC = Path(__file__).resolve().parents[2] / 'edgetx/radio/src'

class EncoderTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'requires host g++')
    def test_pin_override_direction_bounce_and_enter_suppression(self):
        driver = (SRC / 'targets/common/arm/stm32/rotary_encoder_driver.cpp').read_text()
        decoder = driver.split('volatile rotenc_t rotencValue = 0;', 1)[1].split('void rotaryEncoderStartDelay()', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test = root / 'encoder.cpp'
            test.write_text(r'''
#include <stdint.h>
#include <cassert>
#define SAOLALINK_DEVEBOX
#define ROTARY_ENCODER_INVERTED
#define ROTARY_ENCODER_GPIO (&port)
#define LL_GPIO_PIN_14 (1U<<14)
#define LL_EXTI_LINE_14 (1U<<14)
#define LL_SYSCFG_EXTI_LINE14 14
struct Port { uint32_t IDR; } port;
''' + f'#include "{SRC / "targets/taranis/saolalink_v1/hal_overrides.h"}"\n' + r'''
using rotenc_t = int16_t;
#define ROTARY_ENCODER_GRANULARITY 2
#define ON_DETENT(p) ((p)==0 || (p)==3)
#define ROTARY_ENCODER_MODE_INVERT_BOTH 2
#define KEY_ENTER 2
struct { int rotEncMode; } g_eeGeneral = {ROTARY_ENCODER_MODE_INVERT_BOTH};
uint32_t keys;
uint32_t readKeys() {return keys;}
volatile rotenc_t rotencValue = 0;
''' + decoder + r'''
static void sample(unsigned pins) {
 port.IDR=((pins&1U)<<9) | ((pins&2U)<<13);
 rotaryEncoderCheck();
}
int main() {
 static_assert(ROTARY_ENCODER_GPIO_PIN_B==(1U<<14));
 static_assert(ROTARY_ENCODER_EXTI_LINE2==(1U<<14));
 static_assert(ROTARY_ENCODER_EXTI_SYS_LINE2==14);
 port.IDR=1U<<10; assert(ROTARY_ENCODER_POSITION==0); // SYS must not be encoder B
 port.IDR=1U<<9; assert(ROTARY_ENCODER_POSITION==1);
 port.IDR=1U<<14; assert(ROTARY_ENCODER_POSITION==2);
 port.IDR=(1U<<9)|(1U<<14); assert(ROTARY_ENCODER_POSITION==3);
 sample(0); sample(1); sample(3); sample(2); sample(0);
 assert(rotaryEncoderGetValue()==2);
 sample(2); sample(3); sample(1); sample(0);
 assert(rotaryEncoderGetValue()==0); // reverse cycle
 sample(1); sample(0); sample(1); sample(0);
 assert(rotaryEncoderGetValue()==0); // alternating contact bounce cancels
 keys=1U<<KEY_ENTER;
 sample(1); sample(3); sample(2); sample(0);
 assert(rotaryEncoderGetValue()==0); // retain upstream Enter+rotation suppression
 keys=0;
 sample(1); sample(3); sample(2); sample(0);
 assert(rotaryEncoderGetValue()==2);
}
''')
            r = subprocess.run(['g++', '-std=c++17', str(test), '-o', str(root / 'encoder')], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            subprocess.run([str(root / 'encoder')], check=True)
