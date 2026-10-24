"""Host checks for actual DevEBox GPIO mapping and button transition filter."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[2] / 'edgetx/radio/src'

class DeveboxButtonTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'requires host g++')
    def test_gpio_mapping_active_low_and_debounce(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'stm32_hal_ll.h').write_text('''
#define GPIO_IN_PU 1
#define GPIO_PIN_SPEED_LOW 0
#define GPIOA 0x40020000U
#define GPIOB 0x40020400U
#define GPIOC 0x40020800U
#define GPIOD 0x40020C00U
#define GPIOE 0x40021000U
''')
            (root / 'stm32_gpio_driver.h').write_text('')
            (root / 'stm32_gpio.h').write_text('#define GPIO_PIN(port,pin) ((port)|(pin))\n')
            (root / 'stm32_keys.inc').write_text('''
static void _init_keys() { __builtin_trap(); }
static void _init_trims() { __builtin_trap(); }
static unsigned _read_keys() { __builtin_trap(); }
static unsigned _read_trims() { __builtin_trap(); }
''')
            harness = root / 'buttons.cpp'
            harness.write_text('#define SAOLALINK_DEVEBOX\n'
                f'#include "{SRC / "boards/generic_stm32/inputs.cpp"}"\n'
                f'#include "{SRC / "targets/taranis/saolalink_v1/button_monitor.h"}"\n' + r'''
#include <cassert>
#include <map>
static std::map<gpio_t,int> levels;
void gpio_init(gpio_t pin, gpio_mode_t mode, gpio_speed_t) {
 assert(mode==GPIO_IN_PU);
 assert(pin!=(GPIOA|13) && pin!=(GPIOB|4));
 levels[pin]=1;
}
int gpio_read(gpio_t pin) { assert(levels.count(pin)); return levels[pin]; }
int main() {
 keysInit(); assert(levels.size()==7 && readKeys()==0 && readTrims()==0);
 const gpio_t pins[]={GPIOC|5,GPIOD|3,GPIOD|7,GPIOD|2,GPIOE|10,GPIOE|11,GPIOD|14};
 const EnumKeys keys[]={KEY_EXIT,KEY_PAGEUP,KEY_PAGEDN,KEY_TELE,KEY_SYS,KEY_MODEL,KEY_ENTER};
 unsigned all=0;
 for(unsigned i=0;i<7;++i) {
  levels[pins[i]]=0; assert(readKeys()==(1U<<keys[i]));
  assert(deveboxReadButtons()==(1U<<i));
  levels[pins[i]]=1; all|=1U<<keys[i];
 }
 for(auto& item:levels) item.second=0;
 assert(readKeys()==all && (readKeys()&(1U<<KEY_ENTER)));
 DeveboxButtonMonitor m;
 m.reset(0,0);
 assert(m.update(1,10)==0);
 assert(m.update(0,20)==0); // contact bounce
 assert(m.update(1,25)==0);
 assert(m.update(1,54)==0);
 assert(m.update(1,55)==1 && m.value()==1);
 assert(m.update(1,100)==0); // no periodic/repeat spam while held
 assert(m.update(2,110)==0);
 assert(m.update(2,140)==3 && m.value()==2); // release + another press
 m.reset(0,0xFFFFFFE0U);
 assert(m.update(63,0xFFFFFFF0U)==0);
 assert(m.update(63,0xEU)==63 && m.value()==63); // timer wrap
 assert(m.update(0,20)==0);
 assert(m.update(0,50)==63 && m.value()==0);
 m.reset(4,100); assert(m.value()==4 && m.update(4,200)==0);
 m.reset(0,0); assert(m.update(64,1)==0); assert(m.update(64,31)==64 && m.value()==64); // stuck-at-boot snapshot
}
''')
            result = subprocess.run(['g++', '-std=c++17', '-I', str(root), '-I', str(SRC), str(harness), '-o', str(root / 'buttons')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(root / 'buttons')], check=True)
