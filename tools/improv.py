#!/usr/bin/env python3
"""Minimal Improv Serial client for WLED (protocol v1).

  improv.py PORT info             query state + device info
  improv.py PORT provision        prompt for SSID, getpass for password, send to device

The password is read with getpass, sent only to the serial port, and never printed or stored.
WLED v16.0.1 is built with WLED_DISABLE_IMPROV_WIFISCAN, so there is no scan command here.
"""
import argparse
import getpass
import sys
import time

import serial

HEADER = b"IMPROV"
VERSION = 1
T_STATE, T_ERROR, T_RPC, T_RESULT = 0x01, 0x02, 0x03, 0x04
RPC_WIFI, RPC_STATE, RPC_INFO = 0x01, 0x02, 0x03
STATES = {0x02: "ready (authorised)", 0x03: "provisioning", 0x04: "provisioned"}
ERRORS = {0x00: "no error", 0x01: "invalid RPC packet", 0x02: "unknown RPC command",
          0x03: "unable to connect", 0x04: "not authorised", 0xFF: "unknown error"}


def packet(ptype: int, data: bytes) -> bytes:
    body = HEADER + bytes([VERSION, ptype, len(data)]) + data
    return body + bytes([sum(body) & 0xFF])


def rpc(cmd: int, payload: bytes = b"") -> bytes:
    return packet(T_RPC, bytes([cmd, len(payload)]) + payload)


def open_port(port: str, attempts: int = 20) -> serial.Serial:
    # Open with pyserial's default line states and never touch DTR/RTS afterwards.
    # On this C3's USB-Serial/JTAG (macOS), any DTR/RTS-driven reset -- including
    # esptool's --after hard-reset -- lands in ROM download mode until a power cycle.
    for _ in range(attempts):
        try:
            return serial.Serial(port, 115200, timeout=0.1)
        except serial.SerialException:
            time.sleep(0.5)
    sys.exit(f"could not open {port}")


class Reader:
    """Splits the serial stream into Improv packets and ordinary log text."""

    def __init__(self, ser: serial.Serial):
        self.ser, self.buf = ser, bytearray()

    def poll(self, seconds: float, show_log: bool = True):
        end = time.time() + seconds
        while time.time() < end:
            try:
                self.buf += self.ser.read(256)
            except serial.SerialException:
                time.sleep(0.2)
                continue
            while True:
                i = self.buf.find(HEADER)
                if i < 0:
                    # keep a tail in case a header is split across reads
                    cut = max(0, len(self.buf) - len(HEADER))
                    self._log(self.buf[:cut], show_log)
                    del self.buf[:cut]
                    break
                self._log(self.buf[:i], show_log)
                del self.buf[:i]
                if len(self.buf) < 9 or len(self.buf) < 10 + self.buf[8]:
                    break
                n = 10 + self.buf[8]
                pkt, self.buf = bytes(self.buf[:n]), self.buf[n:]
                if sum(pkt[:-1]) & 0xFF != pkt[-1]:
                    print("  [improv] bad checksum, ignored")
                    continue
                yield pkt[7], pkt[9:-1]

    @staticmethod
    def _log(chunk: bytes, show: bool):
        if show and chunk:
            sys.stdout.write(chunk.decode("utf-8", "replace"))
            sys.stdout.flush()


def strings(data: bytes) -> list:
    out, pos = [], 2  # skip command byte + total length
    while pos < len(data):
        n = data[pos]
        out.append(data[pos + 1:pos + 1 + n].decode("utf-8", "replace"))
        pos += 1 + n
    return out


def describe(ptype: int, data: bytes) -> str:
    if ptype == T_STATE:
        return f"state: {STATES.get(data[0], hex(data[0]))}"
    if ptype == T_ERROR:
        return f"error: {ERRORS.get(data[0], hex(data[0]))}"
    if ptype == T_RESULT:
        return f"rpc 0x{data[0]:02x} result: {strings(data)}"
    return f"type 0x{ptype:02x}: {data.hex()}"


def cmd_info(ser):
    r = Reader(ser)
    print("--- improv queries ---")
    for cmd in (RPC_INFO, RPC_STATE):
        ser.write(rpc(cmd))
        for p in r.poll(1.5, show_log=False):
            print(f"  [improv] {describe(*p)}")


def cmd_provision(ser):
    ssid = input("Wi-Fi SSID: ").strip()
    pw = getpass.getpass("Wi-Fi password (not echoed): ")
    s, p = ssid.encode(), pw.encode()
    if len(s) > 32 or len(p) > 64:
        sys.exit("SSID max 32 bytes, password max 64 bytes")
    payload = bytes([len(s)]) + s + bytes([len(p)]) + p
    del pw, p
    r = Reader(ser)
    ser.write(rpc(RPC_WIFI, payload))
    del payload
    print("Sent. Waiting up to 40 s for the device to join...")
    for ptype, data in r.poll(40, show_log=False):
        print(f"  [improv] {describe(ptype, data)}")
        if ptype == T_RESULT and data[0] == RPC_WIFI:
            urls = strings(data)
            print(f"\nConnected: {urls[0]}" if urls else "\nResult with no URL (not connected?)")
            return
        if ptype == T_ERROR and data[0] not in (0x00,):
            print("\nDevice reported an error.")
            return
    # WLED only sends the URL result once connected; ask for state as a fallback
    ser.write(rpc(RPC_STATE))
    for p in r.poll(2, show_log=False):
        print(f"  [improv] {describe(*p)}")
    print("\nNo connection confirmed within 40 s.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("action", choices=["info", "provision"])
    a = ap.parse_args()
    s = open_port(a.port)
    try:
        if a.action == "info":
            cmd_info(s)
        else:
            cmd_provision(s)
    finally:
        s.close()
