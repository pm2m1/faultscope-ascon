"""UART protocol and real RTL end-to-end bench for the phase 11 board wrapper."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest

from scripts.phase11_uart_host import (
    BAD_CRC, OK, SET_CONTROL, SET_KEY, TX_SOF, control_payload,
    crc8, decode_result, request, response_parse,
)

ROOT = Path(__file__).resolve().parents[1]


def test_reference_crc_vectors():
    assert crc8(b"123456789") == 0xF4  # CRC-8/ATM standard check
    assert crc8(bytes([0x22, 0x00])) == 0x84
    assert request(0x22) == bytes((0xA5, 0x22, 0x00, 0x84))


def test_frame_parser_rejects_corruption():
    frame = bytes((TX_SOF, OK, 2, 0x11, 0x00))
    frame += bytes((crc8(frame[1:]),))
    assert response_parse(frame) == (OK, b"\x11\x00")
    with pytest.raises(ValueError, match="CRC"):
        response_parse(frame[:-1] + bytes((frame[-1] ^ 1,)))
    with pytest.raises(ValueError, match="length"):
        response_parse(frame[:-2])
    assert len(request(SET_KEY, bytes(range(16)))) == 20
    with pytest.raises(ValueError):
        request(SET_KEY, bytes(17))


def test_control_and_invalid_result_fail_closed():
    assert control_payload(0, 16, fault_enable=True, fault_phase=4,
                           fault_round=11, fault_bit=319) == bytes([0, 16, 1, 4, 11, 63, 1])
    for kw in (dict(ad_length=17, msg_length=0),
               dict(ad_length=0, msg_length=17),
               dict(ad_length=0, msg_length=0, fault_bit=320),
               dict(ad_length=0, msg_length=0, fault_phase=6)):
        with pytest.raises(ValueError):
            control_payload(**kw)
    result = decode_result(bytes([0, 0]) + bytes(32))
    assert not result.valid and not result.alarm and result.ciphertext == b""
    with pytest.raises(ValueError, match="Fail-closed"):
        decode_result(bytes([0, 0, 1]) + bytes(31))
    with pytest.raises(ValueError, match="Alarm"):
        decode_result(bytes([0, 3]) + bytes(32))


def test_uart_wrapper_has_no_extra_wide_io_ports():
    source = (ROOT / "rtl/faultscope_uart_top.sv").read_text()
    assert "module faultscope_uart_top" in source
    assert "ascon_aead_encrypt_temporal core" in source
    assert "clk" in source and "uart_rx_i" in source and "uart_tx_o" in source
    assert "crc8_byte" in source
    assert "assign led_alarm_o = core_alarm" in source
    # A port-level wrapper, not an alteration of the cryptographic core.
    assert "output logic [127:0] tag_o" not in source


def test_uart_end_to_end_verilator(tmp_path):
    if os.environ.get("FAULTSCOPE_RUN_PHASE11_UART") != "1":
        pytest.skip("Opt-in UART RTL simulation; run Phase 11 pilot")
    verilator = shutil.which("verilator")
    assert verilator, "Verilator required for UART wrapper test (brew install verilator)"
    sources = ["rtl/ascon_round.sv", "rtl/ascon_permutation_faultable.sv",
               "rtl/ascon_permutation_temporal.sv", "rtl/ascon_aead_encrypt_temporal.sv",
               "rtl/fs_reset_sync.sv", "rtl/fs_uart_rx.sv", "rtl/fs_uart_tx.sv",
               "rtl/faultscope_uart_top.sv",
               "tb/tb_faultscope_uart_top.sv"]
    obj = tmp_path / "obj_dir"
    proc = subprocess.run([verilator, "--binary", "--timing", "--assert",
                           "-j", "2", "-Wno-fatal", "--top-module", "tb_faultscope_uart_top",
                           "--Mdir", str(obj),
                           *[str(ROOT / s) for s in sources]], cwd=ROOT,
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-6000:]
    proc = subprocess.run([str(obj / "Vtb_faultscope_uart_top")], cwd=ROOT,
                          capture_output=True, text=True, timeout=90)
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-5000:]
    assert "PASS: UART protected AEAD clean tag, fault alarm, invalid CRC" in proc.stdout


def test_host_transport_command_sequence_without_serial_device():
    from scripts.phase11_uart_host import (
        Transport, READ_RESULT, START, TX_SOF, crc8,
    )

    class SyntheticSerial:
        def __init__(self):
            self.buffer = bytearray()
            self.received = []
            self.reads = 0

        def write(self, data):
            command = data[1]
            self.received.append(command)
            if command == READ_RESULT:
                self.reads += 1
                status = 3 if self.reads == 1 else OK
                payload = (bytes((0, 1)) + bytes(16) +
                           bytes.fromhex('4f9c278211bec9316bf68f46ee8b2ec6')) if status == OK else b''
            elif command == 0x22:
                status, payload = OK, bytes((0x11, 0x00))
            else:
                status, payload = OK, b''
            body = bytes((status, len(payload))) + payload
            self.buffer.extend(bytes((TX_SOF,)) + body + bytes((crc8(body),)))
            return len(data)

        def flush(self):
            pass

        def read(self, count):
            chunk = bytes(self.buffer[:count])
            del self.buffer[:count]
            return chunk

    port = SyntheticSerial()
    result = Transport(port).run(bytes(range(16)), bytes(range(16, 32)), b'', b'', timeout=2)
    assert result.valid and not result.alarm
    assert result.tag.hex() == '4f9c278211bec9316bf68f46ee8b2ec6'
    assert port.received == [0x10, 0x11, 0x12, 0x13, 0x14, START, READ_RESULT, READ_RESULT]
