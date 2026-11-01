"""Browser AEAD vs Python and pinned official Ascon-C KATs; no external crypto API."""
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess

import pytest
from reference.ascon_aead import encrypt, decrypt, IV
from reference.ascon_permutation import ascon_round, ascon_permutation, ROUND_CONSTANTS, MASK64

ROOT=Path(__file__).resolve().parents[1]
IMPORT="""import {buildAeadTrace,encryptBytes,decryptBytes,validateForm,parse128,hex,DEMO_KEY,DEMO_NONCE} from './frontend/src/asconAeadTrace.ts';
let text='';for await(const chunk of process.stdin)text+=chunk;const cases=JSON.parse(text);
const bytes=s=>Uint8Array.from(s.match(/../g)??[],b=>parseInt(b,16));
"""
def node(body,data):
    executable=shutil.which('node')
    assert executable,'Node >=22 is required for browser algorithm verification'
    proc=subprocess.run([executable,'--experimental-strip-types','--input-type=module','-e',IMPORT+body],input=json.dumps(data),cwd=ROOT,capture_output=True,text=True,timeout=180)
    assert proc.returncode==0,proc.stderr
    return json.loads(proc.stdout)


def test_all_1089_pinned_official_vectors_encrypt_decrypt_and_reject_tampering():
    pin=(ROOT/'docs/ascon_reference_commit.txt').read_text(encoding='utf-8').strip()
    repo=ROOT/'references/ascon-c'
    relative='crypto_aead/asconaead128/LWC_AEAD_KAT_128_128.txt'
    path=repo/relative
    assert path.is_file(),'Restore the pinned Ascon-C reference as documented by existing CI'
    assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==pin
    committed=subprocess.check_output(['git','-C',str(repo),'show',f'{pin}:{relative}'])
    assert path.read_bytes().replace(b'\r\n',b'\n')==committed
    vectors=[]
    for block in path.read_text(encoding='utf-8').strip().split('\n\n'):
        f=dict(line.split(' = ',1) for line in block.splitlines() if ' = ' in line)
        vectors.append({'key':f['Key'],'nonce':f['Nonce'],'msg':f['PT'],'ad':f['AD'],'expected':f['CT']})
    assert len(vectors)==1089
    actual=node("""console.log(JSON.stringify(cases.map(v=>{
      const k=bytes(v.key),n=bytes(v.nonce),m=bytes(v.msg),a=bytes(v.ad),sealed=encryptBytes({key:k,nonce:n,plaintext:m,ad:a});
      const valid=decryptBytes(k,n,sealed,a),tagFault=sealed.slice();tagFault[tagFault.length-1]^=1;
      const badTag=decryptBytes(k,n,tagFault,a);let badCipher=null;
      if(m.length){const b=sealed.slice();b[0]^=1;badCipher=decryptBytes(k,n,b,a);}
      return {sealed:hex(sealed),plain:valid.authenticated?hex(valid.plaintext):null,
        tagBlocked:!badTag.authenticated&&badTag.plaintext===null,
        cipherBlocked:badCipher===null||(!badCipher.authenticated&&badCipher.plaintext===null)};
    })));""",vectors)
    for case,result in zip(vectors,actual):
        k,n,m,a=(bytes.fromhex(case[x]) for x in ('key','nonce','msg','ad'))
        expected=bytes.fromhex(case['expected'])
        assert encrypt(k,n,m,a)==expected
        assert decrypt(k,n,expected,a)==m
        assert result=={'sealed':expected.hex(),'plain':m.hex(),'tagBlocked':True,'cipherBlocked':True}


def _substitution(s):
    x0,x1,x2,x3,x4=s
    x0^=x4;x4^=x3;x2^=x1
    t0=x0^(~x1&x2);t1=x1^(~x2&x3);t2=x2^(~x3&x4);t3=x3^(~x4&x0);t4=x4^(~x0&x1)
    t1^=t0;t0^=t4;t3^=t2;t2=~t2
    return tuple(v&MASK64 for v in (t0,t1,t2,t3,t4))


def oracle_operations(k,n,m,a):
    key=[int.from_bytes(k[i:i+8],'little') for i in (0,8)]
    s=(IV,*key,*[int.from_bytes(n[i:i+8],'little') for i in (0,8)])
    operations=[(1,(0,)*5,s)]
    def op(phase,after):
        nonlocal s
        operations.append((phase,s,after));s=after
    def perm(phase,r):op(phase,ascon_permutation(s,r))
    def rate():return s[0].to_bytes(8,'little')+s[1].to_bytes(8,'little')
    def replace(b):return (int.from_bytes(b[:8],'little'),int.from_bytes(b[8:],'little'),*s[2:])
    perm(2,12);op(2,(*s[:3],s[3]^key[0],s[4]^key[1]))
    if a:
        i=0
        while i+16<=len(a):op(3,replace(bytes(x^y for x,y in zip(rate(),a[i:i+16]))));perm(3,8);i+=16
        padded=a[i:]+b'\x01'+bytes(15-len(a[i:]))
        op(3,replace(bytes(x^y for x,y in zip(rate(),padded))));perm(3,8)
    else:op(3,s)
    op(4,(*s[:4],s[4]^(1<<63)))
    i=0
    while i+16<=len(m):op(5,replace(bytes(x^y for x,y in zip(rate(),m[i:i+16]))));perm(5,8);i+=16
    b=bytearray(rate())
    for j,v in enumerate(m[i:]):b[j]^=v
    b[len(m[i:])]^=1;op(5,replace(b))
    op(6,(*s[:2],s[2]^key[0],s[3]^key[1],s[4]));perm(6,12)
    op(6,(*s[:3],s[3]^key[0],s[4]^key[1]))
    return operations


@pytest.mark.parametrize('message_length',[0,1,15,16])
@pytest.mark.parametrize('ad_length',[0,1,15,16])
def test_bounded_macro_and_every_round_stage_match_python(message_length,ad_length):
    rng=random.Random(8128+message_length*33+ad_length)
    k,n,m,a=[rng.randbytes(length) for length in (16,16,message_length,ad_length)]
    result=node("""const v=cases;const t=buildAeadTrace({key:bytes(v.k),nonce:bytes(v.n),plaintext:bytes(v.m),ad:bytes(v.a)});
      const w=s=>s.map(x=>x.toString(16).padStart(16,'0'));
      console.log(JSON.stringify({sealed:hex(t.combined),ops:t.steps.flatMap((step,phase)=>step.operations.map(op=>({phase,before:w(op.before),after:w(op.after),rounds:op.rounds??null,frames:op.frames?.map(f=>({stage:f.stage,constant:f.constant,lanes:w(f.lanes)}))??null}))),xor:t.byteXors}));""",dict(k=k.hex(),n=n.hex(),m=m.hex(),a=a.hex()))
    assert result['sealed']==encrypt(k,n,m,a).hex()
    expected=oracle_operations(k,n,m,a)
    assert len(result['ops'])==len(expected)
    for js,(phase,before,after) in zip(result['ops'],expected):
        assert js['phase']==phase
        assert js['before']==[f'{x:016x}' for x in before]
        assert js['after']==[f'{x:016x}' for x in after]
        if js['rounds']:
            state=before;frames=js['frames'];rounds=js['rounds']
            assert len(frames)==3*rounds+1
            assert frames[0]['lanes']==[f'{x:016x}' for x in before]
            for i,constant in enumerate(ROUND_CONSTANTS[12-rounds:]):
                c=(state[0],state[1],state[2]^constant,state[3],state[4])
                expected_stages=(c,_substitution(c),ascon_round(state,constant))
                for j,stage in enumerate(('constant','substitution','diffusion')):
                    f=frames[i*3+1+j]
                    assert f['stage']==stage and f['constant']==constant
                    assert f['lanes']==[f'{x:016x}' for x in expected_stages[j]]
                state=expected_stages[2]
            assert state==after
    assert len(result['xor'])==message_length
    assert bytes(row['ciphertext'] for row in result['xor'])==encrypt(k,n,m,a)[:-16]
    assert all(row['plaintext']^row['rate']==row['ciphertext'] for row in result['xor'])


def test_utf8_bounds_hex_validation_and_text_edge_cases():
    cases=[{'message':s,'associatedData':a,'keyHex':k,'nonceHex':n} for s,a,k,n in [
        ('HELLO','', '00'*16,'11'*16),('é'*8,'','00'*16,'11'*16),('😀'*4,'','00'*16,'11'*16),
        ('é'*9,'','00'*16,'11'*16),('😀'*4+'a','','00'*16,'11'*16),('','界'*6,'00'*16,'11'*16),
        ('','', '00'*15,'11'*16),('','', 'gg'*16,'11'*16),('','', '00'*16,'11'*17),
        ('','', '00 '*16,'11 '*16),('\ud800','','00'*16,'11'*16)]]
    out=node("""console.log(JSON.stringify(cases.map(v=>{try{const i=validateForm(v);return {ok:true,bytes:hex(i.plaintext),ad:i.ad.length};}catch(e){return {ok:false,error:e.message};}})));""",cases)
    assert [r['ok'] for r in out]==[True,True,True,False,False,False,False,False,False,True,False]
    assert out[0]['bytes']=='48454c4c4f'
    assert '18 UTF-8 bytes' in out[3]['error'] and '17 UTF-8 bytes' in out[4]['error']


def test_receiver_uses_received_ciphertext_and_authenticates_context_and_inputs():
    result=node("""const v=validateForm({message:'HELLO',associatedData:'Course: CNS',keyHex:DEMO_KEY,nonceHex:DEMO_NONCE}),b=encryptBytes(v);
      const k=v.key.slice(),n=v.nonce.slice(),a=v.ad.slice();k[0]^=1;n[0]^=1;a[0]^=1;
      console.log(JSON.stringify([decryptBytes(k,v.nonce,b,v.ad),decryptBytes(v.key,n,b,v.ad),decryptBytes(v.key,v.nonce,b,a),decryptBytes(v.key,v.nonce,b.slice(0,15),v.ad)].map(r=>!r.authenticated&&r.plaintext===null)));""",{})
    assert result==[True]*4

def test_default_hello_demo_matches_python_reference():
    result=node("""const i=validateForm({message:'HELLO',associatedData:'Course: CNS',keyHex:DEMO_KEY,nonceHex:DEMO_NONCE});
      console.log(JSON.stringify({sealed:hex(encryptBytes(i)),message:hex(i.plaintext),ad:hex(i.ad)}));""",{})
    assert result=={'sealed':encrypt(bytes(range(16)),bytes(range(16,32)),b'HELLO',b'Course: CNS').hex(),
                    'message':b'HELLO'.hex(),'ad':b'Course: CNS'.hex()}
