"""Static wrapper-mapping guards; live Yosys mapping runs only when enabled."""
from pathlib import Path
import json
import os
import shutil

import pytest

from experiments.phase11_fpga import PORTS, TOP, NAMES, validate_ports, synthesize

ROOT = Path(__file__).resolve().parents[1]


def test_physical_ports_are_six_bits():
    assert len(PORTS) == 6
    fake={"modules":{TOP:{"ports":{n:{"bits":[i+1],"direction":"input"} for i,n in enumerate(PORTS)}}}}
    validate_ports(fake)
    fake["modules"][TOP]["ports"]["extra"]={"bits":[9]}
    with pytest.raises(ValueError,match="port"):
        validate_ports(fake)


def test_unchanged_cryptographic_core_is_in_source_set():
    assert "ascon_aead_encrypt_temporal.sv" in NAMES
    assert "ascon_round.sv" in NAMES
    assert "faultscope_uart_top.sv" in NAMES
    assert "fs_reset_sync.sv" in NAMES
    assert all((ROOT/"rtl"/n).is_file() for n in NAMES)


def test_fpga_mapping_opt_in():
    if os.environ.get("FAULTSCOPE_RUN_PHASE11_FPGA")!="1":
        pytest.skip("Opt-in real xc7 UART wrapper synthesis")
    assert shutil.which("yosys") and shutil.which("sv2v")
    result=synthesize(ROOT/"build/reproduction/phase11")
    assert result["num_top_level_signal_bits"]==6
    assert result["metrics"]["lut_total"]>0
    assert result["metrics"]["flip_flops"]>0
