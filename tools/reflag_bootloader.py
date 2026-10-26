#!/usr/bin/env python3
"""Re-flag an ESP32-family bootloader image for a different flash size.

Python port of patchBootloaderFlashSize() from the WLED web installer's app.js
(wled/WLED-WebInstaller @ 5fa2889): patch the flash-size nibble in header
byte 3, then recompute the appended SHA-256 digest if the image has one.
The checksum byte covers segment data only, so it is left alone.

Usage: reflag_bootloader.py IN.bin OUT.bin 4MB|8MB|16MB|32MB
"""
import hashlib
import struct
import sys

FLASH_SIZE_NIBBLE = {"4MB": 2, "8MB": 3, "16MB": 4, "32MB": 5}


def reflag(data: bytes, size: str) -> bytes:
    data = bytearray(data)
    if data[0] != 0xE9:
        raise ValueError("not an ESP image (bad magic byte)")
    num_segments = data[1]
    append_digest = data[23]
    pos = 24
    for _ in range(num_segments):
        (seg_len,) = struct.unpack_from("<I", data, pos + 4)
        pos += 8 + seg_len
    pad = (16 - ((pos + 1) % 16)) % 16
    hash_start = pos + pad + 1

    data[3] = (data[3] & 0x0F) | (FLASH_SIZE_NIBBLE[size] << 4)
    if append_digest:
        data[hash_start:hash_start + 32] = hashlib.sha256(data[:hash_start]).digest()
    return bytes(data)


if __name__ == "__main__":
    src, dst, size = sys.argv[1:4]
    with open(src, "rb") as f:
        out = reflag(f.read(), size)
    with open(dst, "wb") as f:
        f.write(out)
    print(f"{dst}: {size}, sha256 {hashlib.sha256(out).hexdigest()}")
