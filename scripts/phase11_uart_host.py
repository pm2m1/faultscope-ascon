"""Phase 11 laboratory UART host; raw keys traverse the link in plaintext.

Transport: 8N1, half duplex (one request and its complete response).
Requires optional ``pyserial`` ONLY when actually connecting to a board.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import time

RX_SOF, TX_SOF = 0xA5, 0x5A
SET_KEY, SET_NONCE, SET_AD, SET_MSG = 0x10, 0x11, 0x12, 0x13
SET_CONTROL, START, READ_RESULT, PING = 0x14, 0x20, 0x21, 0x22
OK, BAD_LENGTH, BAD_CRC, BUSY, NOT_READY, BAD_COMMAND, BAD_CONTROL = range(7)
STATUS = {
    OK: "OK", BAD_LENGTH: "BAD_LENGTH", BAD_CRC: "BAD_CRC",
    BUSY: "BUSY", NOT_READY: "NOT_READY", BAD_COMMAND: "BAD_COMMAND",
    BAD_CONTROL: "BAD_CONTROL",
}


def crc8(data: bytes) -> int:
    """CRC-8 with polynomial x^8+x^2+x+1 (0x07), init 0, no reflection."""
    c = 0
    for byte in data:
        c ^= byte
        for _ in range(8):
            c = ((c << 1) ^ (0x07 if c & 0x80 else 0)) & 0xFF
    return c


def request(command: int, payload: bytes = b"") -> bytes:
    if not 0 <= command <= 255 or len(payload) > 16:
        raise ValueError("Command must be a byte; request payload limit 16")
    body = bytes((command, len(payload))) + payload
    return bytes((RX_SOF,)) + body + bytes((crc8(body),))


def response_parse(frame: bytes) -> tuple[int, bytes]:
    if len(frame) < 4 or frame[0] != TX_SOF:
        raise ValueError("Invalid response sync/length")
    status, length = frame[1], frame[2]
    if length > 34 or len(frame) != 4 + length:
        raise ValueError("Malformed response length")
    if crc8(frame[1:-1]) != frame[-1]:
        raise ValueError("Response CRC8 mismatch")
    if status not in STATUS:
        raise ValueError("Unknown response status")
    return status, frame[3:-1]


@dataclass(frozen=True)
class Result:
    message_length: int
    valid: bool
    alarm: bool
    applied: bool
    ciphertext: bytes
    tag: bytes


def decode_result(payload: bytes) -> Result:
    if len(payload) != 34 or payload[0] > 16 or payload[1] & 0xF8:
        raise ValueError("Malformed result payload")
    flags = payload[1]
    ciphertext = payload[2:18]
    tag = payload[18:34]
    if not (flags & 1) and (any(ciphertext) or any(tag)):
        raise ValueError("Fail-closed response released nonzero invalid output")
    if bool(flags & 1) and bool(flags & 2):
        raise ValueError("Alarm and valid output asserted simultaneously")
    return Result(payload[0], bool(flags & 1), bool(flags & 2),
                  bool(flags & 4), ciphertext[:payload[0]], tag)


def control_payload(ad_length: int, msg_length: int, *, fault_enable: bool = False,
                    fault_phase: int = 0, fault_round: int = 0, fault_bit: int = 0) -> bytes:
    if not (0 <= ad_length <= 16 and 0 <= msg_length <= 16 and
            0 <= fault_phase <= 4 and 0 <= fault_round <= 11 and
            0 <= fault_bit < 320):
        raise ValueError("Invalid bounded AEAD/fault controls")
    return bytes((ad_length, msg_length, int(fault_enable), fault_phase,
                  fault_round, fault_bit & 0xFF, fault_bit >> 8))


class Transport:
    def __init__(self, serial_obj):
        self.port = serial_obj

    def exchange(self, command: int, payload: bytes = b"") -> tuple[int, bytes]:
        self.port.write(request(command, payload))
        self.port.flush()
        def exact(count: int) -> bytes:
            result = bytearray()
            while len(result) < count:
                block = self.port.read(count - len(result))
                if not block:
                    raise TimeoutError("UART response timed out")
                result.extend(block)
            return bytes(result)
        header = exact(3)
        if header[0] != TX_SOF or header[2] > 34:
            raise ValueError("UART response framing/length error")
        status, data = response_parse(header + exact(header[2] + 1))
        return status, data

    def require_ok(self, command: int, data: bytes = b"") -> bytes:
        status, payload = self.exchange(command, data)
        if status != OK:
            raise RuntimeError(f"Board rejected {command:#x}: {STATUS[status]}")
        return payload

    def run(self, key: bytes, nonce: bytes, ad: bytes, plaintext: bytes,
            *, fault_enable: bool = False, fault_phase: int = 0,
            fault_round: int = 0, fault_bit: int = 0,
            timeout: float = 10) -> Result:
        if len(key) != 16 or len(nonce) != 16 or len(ad) > 16 or len(plaintext) > 16:
            raise ValueError("Key/nonce must be 16 bytes, AD/message at most 16")
        for command, data in ((SET_KEY, key), (SET_NONCE, nonce),
                              (SET_AD, ad.ljust(16, b"\0")),
                              (SET_MSG, plaintext.ljust(16, b"\0")),
                              (SET_CONTROL, control_payload(
                                  len(ad), len(plaintext), fault_enable=fault_enable,
                                  fault_phase=fault_phase, fault_round=fault_round,
                                  fault_bit=fault_bit))):
            self.require_ok(command, data)
        self.require_ok(START)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, data = self.exchange(READ_RESULT)
            if status == OK:
                return decode_result(data)
            if status not in (BUSY, NOT_READY):
                raise RuntimeError(f"Read failed: {STATUS[status]}")
            time.sleep(0.005)
        raise TimeoutError("Ascon transaction did not complete before timeout")


def main() -> None:
    p = argparse.ArgumentParser(description="FaultScope-Ascon unencrypted UART laboratory client")
    p.add_argument("--port", required=True, help="Serial device path, e.g. /dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--key", required=True, help="32 hex digits; NEVER use a production key")
    p.add_argument("--nonce", required=True, help="32 hex digits; MUST be unique per key")
    p.add_argument("--ad", default="", help="Associated data hex, max 32 digits")
    p.add_argument("--msg", default="", help="Plaintext hex, max 32 digits")
    p.add_argument("--fault", action="store_true")
    p.add_argument("--phase", type=int, default=0)
    p.add_argument("--round", type=int, default=0)
    p.add_argument("--bit", type=int, default=0)
    args = p.parse_args()
    try:
        import serial  # optional dependency
    except ImportError as e:
        raise SystemExit("Install optional UART host dependency: uv pip install pyserial") from e
    try:
        key, nonce = bytes.fromhex(args.key), bytes.fromhex(args.nonce)
        ad, msg = bytes.fromhex(args.ad), bytes.fromhex(args.msg)
    except ValueError as e:
        p.error(f"Invalid hex input: {e}")
    with serial.Serial(args.port, args.baud, timeout=2, write_timeout=2) as port:
        result = Transport(port).run(key, nonce, ad, msg,
                                      fault_enable=args.fault, fault_phase=args.phase,
                                      fault_round=args.round, fault_bit=args.bit)
    print(f"valid={result.valid} alarm={result.alarm} applied={result.applied}")
    print(f"ciphertext={result.ciphertext.hex()} tag={result.tag.hex()}")
    print("LAB ONLY: transport is plaintext, unauthenticated, and not production-safe")


if __name__ == "__main__":
    main()
