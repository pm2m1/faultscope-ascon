"""Checkout portability never accepts mutations or replaces raw provenance."""
import hashlib
import json
from pathlib import Path

import pytest

from experiments.source_provenance import verify_rtl_source
from experiments.phase10b_analysis import build_comparison
from experiments.phase10d_fpga import verify_historical_rtl_hashes
from experiments.run_phase5 import source_hashes

ROOT = Path(__file__).resolve().parents[1]
SOURCE = b'module example;\nwire valid;\nendmodule\n'
PIN = hashlib.sha256(SOURCE).hexdigest()


@pytest.mark.parametrize('content,mode', [(SOURCE,'raw'), (SOURCE.replace(b'\n',b'\r\n'),'CRLF-to-LF')])
def test_exact_and_crlf_matches_record_raw_bytes(tmp_path,content,mode):
    path=tmp_path/'example.sv'; path.write_bytes(content)
    before=path.read_bytes()
    result=verify_rtl_source(path,PIN)
    assert result['match_mode']==mode
    assert result['raw_sha256']==hashlib.sha256(content).hexdigest()
    assert result['pinned_sha256']==result['lf_sha256']==PIN
    assert path.read_bytes()==before


@pytest.mark.parametrize('content', [SOURCE.replace(b'valid',b'alarm'), SOURCE+b'// comment\n',
    SOURCE.replace(b'wire',b' wire'), SOURCE.replace(b'\n',b'\r'), b'\xef\xbb\xbf'+SOURCE,
    SOURCE.replace(b'\n',b'\r\n')+b'\r\n'])
def test_no_other_byte_change_is_accepted(tmp_path,content):
    path=tmp_path/'example.sv'; path.write_bytes(content)
    with pytest.raises(ValueError,match='source hash differs'): verify_rtl_source(path,PIN)


def test_hash_dictionary_conversion_requires_actual_bytes(tmp_path):
    path=tmp_path/'example.sv'; path.write_bytes(SOURCE.replace(b'\n',b'\r\n'))
    actual={'example.sv':hashlib.sha256(path.read_bytes()).hexdigest()}
    pinned={'sources_sha256':{'example.sv':PIN}}
    with pytest.raises(ValueError): verify_historical_rtl_hashes(actual,pinned)
    result=verify_historical_rtl_hashes(actual,pinned,source_dir=tmp_path)
    assert result['example.sv']['match_mode']=='CRLF-to-LF'
    with pytest.raises(ValueError,match='raw RTL source digest'):
        verify_historical_rtl_hashes({'example.sv':PIN},pinned,source_dir=tmp_path)
    path.write_bytes(path.read_bytes()+b'// mutation\r\n')
    with pytest.raises(ValueError): verify_historical_rtl_hashes(actual,pinned,source_dir=tmp_path)


def test_comparison_distinguishes_raw_manifest_equality_from_source_match(tmp_path):
    rtl=tmp_path/'rtl'; rtl.mkdir()
    historical=json.loads((ROOT/'reports/phase5/manifest.json').read_text())
    measurements=json.loads((ROOT/'reports/phase5/synthesis_summary.json').read_text())
    raw={}
    for name,pin in historical['sources_sha256'].items():
        content=(ROOT/'rtl'/name).read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
        (rtl/name).write_bytes(content)
        raw[name]=hashlib.sha256(content).hexdigest()
    current={**historical,'sources_sha256':raw}
    result=build_comparison(measurements,measurements,current,historical,root=tmp_path)
    assert not result['same_synthesis_flow_and_RTL_hashes']
    assert result['RTL_matches_historical_bytes_or_CRLF_conversion']
    assert all(r['match_mode']=='CRLF-to-LF' for r in result['rtl_source_provenance'].values())
    current['sources_sha256']['ascon_round.sv']='0'*64
    with pytest.raises(ValueError): build_comparison(measurements,measurements,current,historical,root=tmp_path)


def test_phase5_hashes_remain_raw():
    for name,digest in source_hashes().items():
        assert digest==hashlib.sha256((ROOT/'rtl'/name).read_bytes()).hexdigest()
