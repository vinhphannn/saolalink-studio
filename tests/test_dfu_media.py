"""Execute the actual bootloader media callbacks with a fake flash driver."""
from pathlib import Path
import shutil
import re
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'edgetx/radio/src/targets/taranis/saolalink_v1/devebox_dfu.cpp'

class DfuMediaTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'requires host g++')
    def test_complete_memory_map_survives_usb_string_encoding(self):
        source_root = SOURCE.parents[3]
        config = (source_root / 'targets/common/arm/stm32/usbd_conf.h').read_text()
        dev_config = config.split('#if defined(SAOLALINK_DEVEBOX)', 1)[1].split('#else', 1)[0]
        capacity = int(re.search(r'USBD_MAX_STR_DESC_SIZ\s+(\d+)U', dev_config)[1])
        descriptor = re.search(r'\.pStrDesc = .*?"([^"]+)"', SOURCE.read_text())[1]
        self.assertLessEqual(len(descriptor) * 2 + 2, capacity)
        sectors = re.findall(r'(\d+)\*(\d+)Kg', descriptor)
        self.assertEqual(sum(int(count) * int(size) * 1024 for count, size in sectors), 480 * 1024)
        # Run the upstream encoder too: it previously clamped bLength while
        # writing the full string beyond the allocated descriptor buffer.
        ctl = (source_root / 'thirdparty/STM32_USB_Device_Library/Core/Src/usbd_ctlreq.c').read_text()
        encoder = ctl.split('void USBD_GetString(', 1)[1].split('/**', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / 'string.cpp'
            harness.write_text('#include <stdint.h>\n#include <cstring>\n#include <cassert>\n'
                '#define MIN(a,b) ((a)<(b)?(a):(b))\n#define USB_DESC_TYPE_STRING 3\n'
                f'#define USBD_MAX_STR_DESC_SIZ {capacity}\n'
                'static uint8_t USBD_GetLen(uint8_t* p) { return strlen((char*)p); }\n'
                'void USBD_GetString(' + encoder + '\nint main() {\n'
                f'uint8_t input[]="{descriptor}"; uint8_t output[{capacity+16}];\n'
                'memset(output,0xA5,sizeof(output)); uint16_t len=0; USBD_GetString(input,output,&len);\n'
                f'assert(len=={2*len(descriptor)+2} && output[0]==len);\n'
                'for(unsigned i=0;i<strlen((char*)input);++i) assert(output[2+2*i]==input[i]);\n'
                f'for(unsigned i={capacity};i<sizeof(output);++i) assert(output[i]==0xA5);\n' + '}\n')
            result = subprocess.run(['g++', str(harness), '-o', str(root / 'string')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(root / 'string')], check=True)

    @unittest.skipUnless(shutil.which('g++'), 'requires host g++')
    def test_boot_sector_bounds_errors_and_partial_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            headers = {
                'board.h': '#include <stdint.h>\n#define APP_START_ADDRESS 0x08008000U\n',
                'stm32_cmsis.h': 'inline void __WFI() {}\n',
                'flash_driver.h': 'struct Driver { int (*erase_sector)(uint32_t); int (*program)(uint32_t,void*,uint32_t); };\nextern const Driver stm32_flash_driver;\n',
                'hal/usb_driver.h': '''
#define USBD_OK 0
#define USBD_FAIL 1
#define DFU_MEDIA_ERASE 0
#define USB_DFU_MODE 4
struct USBD_DFU_MediaTypeDef {
 const uint8_t* pStrDesc; uint16_t (*Init)(); uint16_t (*DeInit)();
 uint16_t (*Erase)(uint32_t); uint16_t (*Write)(uint8_t*,uint8_t*,uint32_t);
 uint8_t* (*Read)(uint8_t*,uint8_t*,uint32_t);
 uint16_t (*GetStatus)(uint32_t,uint8_t,uint8_t*);
};
inline void usbRegisterDFUMedia(const USBD_DFU_MediaTypeDef*) {}
inline void setSelectedUsbMode(int) {}
inline void usbStart() {}
''',
                'thirdparty/STM32_USB_Device_Library/Class/DFU/Inc/usbd_dfu.h': '',
            }
            for name, text in headers.items():
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(text)
            test = root / 'media.cpp'
            test.write_text(f'#include "{SOURCE}"\n' + r'''
#include <cassert>
static int calls = 0, failure = 0;
static uint32_t last_address, last_length, last_word;
static int fake_erase(uint32_t a) { ++calls; last_address=a; return failure; }
static int fake_write(uint32_t a, void* data, uint32_t len) {
 ++calls; last_address=a; last_length=len; memcpy(&last_word,data,4); return failure;
}
const Driver stm32_flash_driver = {fake_erase,fake_write};
int main() {
 uint8_t buffer[6] = {};
 assert(media.Erase(0x08000000)==USBD_FAIL);
 assert(media.Erase(0x08007FFF)==USBD_FAIL);
 assert(media.Erase(0x08080000)==USBD_FAIL);
 assert(calls==0);
 assert(media.Erase(0x08008000)==USBD_OK && calls==1);
 assert(media.Erase(0x0807FFFF)==USBD_OK && calls==2);
 alignas(4) uint8_t data[] = {1,2,3,4,5,6,7,8};
 calls=0;
 assert(media.Write(data,(uint8_t*)0x08007FFC,8)==USBD_FAIL);
 assert(media.Write(data,(uint8_t*)0x0807FFFC,8)==USBD_FAIL);
 assert(media.Write(data,(uint8_t*)0x08008001,4)==USBD_FAIL);
 assert(media.Write(data,(uint8_t*)0x08008000,0xFFFFFFFF)==USBD_FAIL);
 assert(calls==0);
 assert(media.Write(data,(uint8_t*)0x08008000,5)==USBD_OK);
 assert(calls==2 && last_address==0x08008004 && last_length==4);
 assert(last_word==0xFFFFFF05);
 assert(media.Write(data,(uint8_t*)0x0807FFFC,3)==USBD_OK);
 assert(last_word==0xFF030201);
 failure=-1;
 assert(media.Erase(0x08008000)==USBD_FAIL);
 assert(media.Write(data,(uint8_t*)0x08008000,4)==USBD_FAIL);
 assert(media.Read((uint8_t*)0x08000000,data,4)==nullptr);
 assert(media.Read((uint8_t*)0x0807FFFF,data,2)==nullptr);
 assert(media.GetStatus(0x08000000,DFU_MEDIA_ERASE,buffer)==USBD_FAIL);
 assert(media.GetStatus(0x08008000,DFU_MEDIA_ERASE,buffer)==USBD_OK);
 assert((buffer[1] | (buffer[2]<<8) | (buffer[3]<<16))==2000);
}
''')
            result = subprocess.run(['g++', '-std=c++20', '-fpermissive', '-I', str(root), str(test), '-o', str(root / 'media')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(root / 'media')], check=True)
