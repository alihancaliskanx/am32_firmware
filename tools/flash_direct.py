#!/usr/bin/env python3
"""Flash an AM32 hex to a 32 KB ESC over a direct single-wire bootloader link.

Follows the AM32 configurator's direct-connect flash sequence: clear the
EEPROM boot byte, write the image in 64-byte chunks from 0x1000, verify it,
restore the EEPROM, then start the application.
"""

import argparse
import sys
import time

import serial

FLASH_BASE = 0x08000000
FW_START = 0x1000
EEPROM = 0x7C00
NAME_ADDR = EEPROM - 32
LAYOUT_SIZE = 0xB8
WRITE_CHUNK = 64
READ_CHUNK = 128
RETRIES = 10
SIGNATURE = b"\x1f\x06"
INIT = bytes([0] * 12 + [0x0D]) + b"BLHeli" + bytes([0xF4, 0x7D])
GOOD_ACK = 0x30


class FlashError(Exception):
    pass


def crc16(data):
    crc = 0
    for xb in data:
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (xb ^ crc) & 1 else crc >> 1
            xb >>= 1
    return crc


def load_hex(path):
    chunks = {}
    base = 0
    for line in open(path):
        line = line.strip()
        if not line.startswith(":"):
            continue
        n, addr, typ = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
        if typ == 4:
            base = int(line[9:13], 16) << 16
        elif typ == 0:
            chunks[base + addr - FLASH_BASE] = bytes.fromhex(line[9:9 + 2 * n])
    start = min(chunks)
    end = max(a + len(d) for a, d in chunks.items())
    if start < FW_START or end > EEPROM:
        raise FlashError(f"hex spans 0x{start:04X}-0x{end:04X}, outside 0x{FW_START:04X}-0x{EEPROM:04X}")
    image = bytearray(b"\xff" * (end - FW_START))
    for a, d in chunks.items():
        image[a - FW_START:a - FW_START + len(d)] = d
    return bytes(image)


def cstr(data):
    return data.split(b"\0")[0].decode(errors="replace")


class Link:
    def __init__(self, port):
        self.ser = serial.Serial(port, 19200, timeout=0.05, exclusive=True)
        time.sleep(0.2)

    def close(self):
        self.ser.close()

    def exchange(self, pkt, reply_len, timeout=2.0):
        self.ser.reset_input_buffer()
        self.ser.write(pkt)
        self.ser.flush()
        want = len(pkt) + reply_len
        rx = b""
        end = time.time() + timeout
        while len(rx) < want and time.time() < end:
            rx += self.ser.read(want - len(rx))
        if rx[:len(pkt)] != pkt:
            return None
        return rx[len(pkt):]

    def command(self, body, reply_len):
        c = crc16(body)
        return self.exchange(bytes(body) + bytes([c & 0xFF, c >> 8]), reply_len)

    def init(self):
        return self.exchange(INIT, 9)

    def set_address(self, addr):
        return self.command([0xFF, 0x00, addr >> 8, addr & 0xFF], 1) == bytes([GOOD_ACK])

    def read(self, addr, size):
        out = b""
        for off in range(0, size, READ_CHUNK):
            n = min(READ_CHUNK, size - off)
            for _ in range(RETRIES):
                if not self.set_address(addr + off):
                    continue
                r = self.command([0x03, n], n + 3)
                if r and len(r) == n + 3 and r[-1] == GOOD_ACK and crc16(r[:n]) == (r[n] | r[n + 1] << 8):
                    out += r[:n]
                    break
            else:
                raise FlashError(f"read failed at 0x{addr + off:04X}")
        return out

    def write(self, addr, data):
        if len(data) % 8:
            data = data + b"\xff" * (8 - len(data) % 8)
        for _ in range(RETRIES):
            if self.set_address(addr):
                break
        else:
            raise FlashError(f"SetAddress 0x{addr:04X} failed")
        for _ in range(RETRIES):
            self.command([0xFE, 0x00, 0x00, len(data)], 0)
            if self.command(list(data), 1) == bytes([GOOD_ACK]):
                break
        else:
            raise FlashError(f"payload for 0x{addr:04X} not accepted")
        for _ in range(RETRIES):
            if self.command([0x01, 0x01], 1) == bytes([GOOD_ACK]):
                break
        else:
            raise FlashError(f"program at 0x{addr:04X} failed")

    def write_chunked(self, addr, data, progress=None):
        for off in range(0, len(data), WRITE_CHUNK):
            self.write(addr + off, data[off:off + WRITE_CHUNK])
            if progress:
                progress(off + min(WRITE_CHUNK, len(data) - off), len(data))

    def run_app(self):
        self.ser.write(bytes(4))
        self.ser.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("port")
    parser.add_argument("hex")
    parser.add_argument("--backup", required=True, help="file to save the pre-flash EEPROM to")
    parser.add_argument("--dry-run", action="store_true", help="check target and back up EEPROM only")
    args = parser.parse_args()

    image = load_hex(args.hex)
    hex_name = cstr(image[NAME_ADDR - FW_START:NAME_ADDR - FW_START + 32])
    print(f"hex: {len(image)} bytes from 0x{FW_START:04X}, target {hex_name!r}")

    link = Link(args.port)
    info = link.init()
    if not info or not info.startswith(b"471"):
        raise FlashError(f"no bootloader reply ({info.hex(' ') if info else 'nothing'})")
    if info[4:6] != SIGNATURE:
        raise FlashError(f"MCU signature {info[4:6].hex()} is not {SIGNATURE.hex()} (32 KB layout)")
    print(f"bootloader: {info.hex(' ')}")

    esc_name = cstr(link.read(NAME_ADDR, 32))
    print(f"esc target: {esc_name!r}")
    if esc_name != hex_name:
        raise FlashError(f"target mismatch: ESC {esc_name!r}, hex {hex_name!r}")

    eeprom = link.read(EEPROM, LAYOUT_SIZE)
    with open(args.backup, "wb") as f:
        f.write(eeprom)
    print(f"eeprom backed up to {args.backup}: {eeprom[:8].hex(' ')} ... version {eeprom[3]}.{eeprom[4]}")
    have_config = eeprom[0] <= 1 and 1 <= eeprom[1] <= 64

    if args.dry_run:
        print("dry run: nothing written")
        link.close()
        return

    if have_config:
        guard = bytes([0]) + eeprom[1:]
        link.write_chunked(EEPROM, guard)
        print("boot byte cleared")

    started = time.time()

    def progress(done, total):
        if done == total or done % 4096 == 0:
            print(f"  wrote {done}/{total} bytes ({time.time() - started:.0f}s)", flush=True)

    link.write_chunked(FW_START, image, progress)

    readback = link.read(FW_START, len(image))
    bad = sum(1 for a, b in zip(readback, image) if a != b)
    if bad:
        raise FlashError(f"verify failed: {bad} bytes differ; boot byte left cleared, re-run to retry")
    print(f"verify ok: {len(image)} bytes match")

    if have_config:
        restored = bytes([1]) + eeprom[1:]
        link.write_chunked(EEPROM, restored)
        check = link.read(EEPROM, LAYOUT_SIZE)
        if check[0] != 1 or check[3:] != restored[3:] or check[1] != restored[1]:
            raise FlashError("eeprom restore verify failed")
        print("eeprom restored, boot byte set")

    link.run_app()
    link.close()
    print("application started")


if __name__ == "__main__":
    try:
        main()
    except FlashError as e:
        sys.exit(f"ERROR: {e}")
