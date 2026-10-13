"""Offline Phase 10E checks. No false Vivado claims or reliance on active device tools."""
import json
from pathlib import Path
import pytest
from experiments.phase10e_feasibility import (parse_top_ports, validate_phase10d, fit_screen,
  validate_out_dir, analyze, CAPACITY, PACKAGE_USER_IO, PART)

HEADER='''module ascon_aead_encrypt_temporal(
input logic clk,
input logic [127:0] key_i,
output logic [127:0] ciphertext_o,
output logic result_valid_o
);'''


def fixture_mapping():
    base={'lut_total':2000,'flip_flops':1500,'bram18':0,'bram36':0,'dsp48':0,
          'cell_types':{'LUT6':2000,'FDRE':1500}}
    return {'target_family':'xc7','historical_rtl_verified':True,
        'architectures': {d:dict(base) for d in ('baseline','instrumented','protected')}}


def test_port_bit_count_and_fail_closed_parser():
    got=parse_top_ports(HEADER)
    assert (got['input_bits'],got['output_bits']) == (129,129)
    with pytest.raises(ValueError): parse_top_ports(HEADER.replace('input logic [127:0]', 'input data [127:0]'))
    with pytest.raises(ValueError): parse_top_ports(HEADER.replace('output logic result_valid_o','output logic [3:0] ciphertext_o'))


def test_exact_architecture_and_source_provenance():
    data=fixture_mapping()
    assert len(validate_phase10d(data))==3
    bad=fixture_mapping();bad['historical_rtl_verified']=False
    with pytest.raises(ValueError): validate_phase10d(bad)
    bad=fixture_mapping();bad['architectures']['rogue']=bad['architectures']['baseline']
    with pytest.raises(ValueError): validate_phase10d(bad)


def test_unmapped_resources_or_bad_counts_rejected():
    bad=fixture_mapping();bad['architectures']['baseline']['lut_total']=2001
    with pytest.raises(ValueError,match='LUT count'):validate_phase10d(bad)
    bad=fixture_mapping();bad['architectures']['protected']['cell_types']['$_AND_']=1
    with pytest.raises(ValueError,match='Unmapped'):validate_phase10d(bad)
    bad=fixture_mapping();bad['architectures']['protected']['flip_flops']=-1
    with pytest.raises(ValueError,match='Invalid'):validate_phase10d(bad)


def test_capacity_math_and_exceeding_limits():
    x=validate_phase10d(fixture_mapping()); r=fit_screen(x)
    assert r['protected']['screen_pass'] is True
    assert r['protected']['resources']['lut_total']['percent']==round(100*2000/63400,3)
    x['protected']['lut_total']=63401
    assert fit_screen(x)['protected']['screen_pass'] is False
    assert PACKAGE_USER_IO==210 and CAPACITY['flip_flops']==126800


def test_36kb_bram_counts_twice():
    x=fixture_mapping()
    x['architectures']['protected']['bram18']=1
    x['architectures']['protected']['bram36']=2
    assert validate_phase10d(x)['protected']['bram18_equivalents']==5


def test_output_must_be_inside_build(tmp_path):
    (tmp_path/'build').mkdir()
    assert validate_out_dir(tmp_path/'build'/'phase10e',root=tmp_path).name=='phase10e'
    for value in [tmp_path/'reports'/'phase5',tmp_path/'rtl',tmp_path/'build']:
        with pytest.raises(ValueError): validate_out_dir(value,root=tmp_path)


def test_report_written_with_no_timing_claim(tmp_path, monkeypatch):
    import experiments.phase10e_feasibility as mod
    mapping=tmp_path/'fpga.json';mapping.write_text(json.dumps(fixture_mapping()))
    rtl=tmp_path/'top.sv';rtl.write_bytes(HEADER.encode('utf-8'))
    import hashlib
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    monkeypatch.setattr(mod,'PINNED_RTL_SHA256',hashlib.sha256(HEADER.encode()).hexdigest())
    data=fixture_mapping()
    data['source_sha256']={'ascon_aead_encrypt_temporal.sv':hashlib.sha256(HEADER.encode()).hexdigest()}
    mapping.write_text(json.dumps(data))
    report=analyze(mapping,rtl,tmp_path/'build'/'phase10e')
    assert report['device']==PART and report['io']['total_bits']==258
    txt=(tmp_path/'build'/'phase10e'/'REPORT.md').read_text()
    assert 'NOT a place-and-route' in txt
    assert 'No timing claims' in txt


def test_vivado_tcl_is_real_ooc_and_no_bitstream():
    tcl=(Path(__file__).parents[1]/'scripts/phase10e_vivado_ooc.tcl').read_text()
    for command in ('synth_design','-mode out_of_context','place_design','route_design','report_timing_summary','check_timing'):
        assert command in tcl
    assert '\nwrite_bitstream' not in tcl
