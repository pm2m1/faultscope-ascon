/** Educational browser-local NIST SP 800-232 AEAD. Not production cryptography.
 * UI bounds are separate from byte functions, which support official KAT lengths.
 * Pure functions: no storage, logging, network, or WebCrypto/key-management API.
 */
import { asconTrace, permute, type FiveWords, type TraceFrame } from './asconTrace.ts';
export const DEMO_KEY='000102030405060708090a0b0c0d0e0f';
export const DEMO_NONCE='101112131415161718191a1b1c1d1e1f';
export const IV=0x00001000808c0001n;
export type DemoForm={message:string;associatedData:string;keyHex:string;nonceHex:string};
export type ByteInputs={key:Uint8Array;nonce:Uint8Array;plaintext:Uint8Array;ad:Uint8Array};
export type Operation={label:string;detail:string;before:FiveWords;after:FiveWords;bytes?:Uint8Array;rounds?:8|12;frames?:TraceFrame[]};
export type AeadStep={title:string;simple:string;operations:Operation[]};
export type ByteXor={index:number;plaintext:number;rate:number;ciphertext:number};
export type AeadTrace={steps:AeadStep[];ciphertext:Uint8Array;tag:Uint8Array;combined:Uint8Array;byteXors:ByteXor[];initial:FiveWords;final:FiveWords};
export const hex=(b:Uint8Array)=>Array.from(b,v=>v.toString(16).padStart(2,'0')).join('');
export function utf8(text:string):Uint8Array {
  if (/[\uD800-\uDFFF]/u.test(text)) throw new Error('Please enter valid Unicode text (no unpaired surrogate).');
  return new TextEncoder().encode(text);
}
export function parse128(text:string,label='Key'):Uint8Array {
  const compact=text.replace(/\s/g,'');
  if(!/^[\da-f]{32}$/i.test(compact)) throw new Error(`${label} must contain exactly 16 bytes: 32 hexadecimal digits (spaces are allowed).`);
  return Uint8Array.from(compact.match(/../g)!,v=>parseInt(v,16));
}
export function validateForm(form:DemoForm):ByteInputs {
  const plaintext=utf8(form.message),ad=utf8(form.associatedData);
  if(plaintext.length>16) throw new Error(`Message is ${plaintext.length} UTF-8 bytes. The limit is 16 bytes, not 16 characters.`);
  if(ad.length>16) throw new Error(`Associated data is ${ad.length} UTF-8 bytes. The limit is 16 bytes, not 16 characters.`);
  return {plaintext,ad,key:parse128(form.keyHex),nonce:parse128(form.nonceHex,'Nonce')};
}
const join=(...blocks:Uint8Array[])=>{const out=new Uint8Array(blocks.reduce((n,b)=>n+b.length,0));let i=0;for(const b of blocks){out.set(b,i);i+=b.length;}return out;};
export const wordLE=(b:Uint8Array):bigint=>b.reduce((v,x,i)=>v|(BigInt(x)<<BigInt(i*8)),0n);
const bytesLE=(w:bigint)=>Uint8Array.from({length:8},(_,i)=>Number((w>>BigInt(i*8))&255n));
export const rateBytes=(s:FiveWords)=>join(bytesLE(s[0]),bytesLE(s[1]));
const setRate=(s:FiveWords,b:Uint8Array):FiveWords=>[wordLE(b.slice(0,8)),wordLE(b.slice(8,16)),s[2],s[3],s[4]];
const xor=(a:Uint8Array,b:Uint8Array)=>a.map((v,i)=>v^b[i]);
const pad=(tail:Uint8Array)=>{const b=new Uint8Array(16);b.set(tail);b[tail.length]=1;return b;};
function words(key:Uint8Array,nonce:Uint8Array){
  if(key.length!==16||nonce.length!==16)throw new Error('Key and nonce must each be exactly 16 bytes.');
  return [wordLE(key.slice(0,8)),wordLE(key.slice(8)),wordLE(nonce.slice(0,8)),wordLE(nonce.slice(8))] as const;
}
export function buildAeadTrace({key,nonce,plaintext,ad}:ByteInputs):AeadTrace {
  const [k0,k1,n0,n1]=words(key,nonce),initial:FiveWords=[IV,k0,k1,n0,n1];let state=initial;
  const steps:AeadStep[]=[];
  const step=(title:string,simple:string)=>{const s:AeadStep={title,simple,operations:[]};steps.push(s);return s;};
  const record=(s:AeadStep,label:string,detail:string,fn:(s:FiveWords)=>FiveWords,bytes?:Uint8Array)=>{const before=state;state=fn(state);s.operations.push({label,detail,before,after:state,bytes});};
  const p=(s:AeadStep,rounds:8|12)=>{const before=state,frames=asconTrace(state,rounds);state=frames.at(-1)!.lanes;s.operations.push({label:`Permutation p[${rounds}]`,detail:`${rounds} real rounds: round constant, substitution, diffusion.`,before,after:state,frames,rounds});};
  step('Prepare the inputs','The key is the shared secret. A unique nonce starts each encryption. The message is hidden; associated data is public context protected by the tag.');
  const setup=step('Initialize Ascon','Five 64-bit words make a 320-bit workspace. Load a constant, the key, and the nonce.');
  setup.operations.push({label:'Load x0–x4',detail:'x0 = 0x00001000808c0001; x1 = K0; x2 = K1; x3 = N0; x4 = N1. Words decode bytes little-endian.',before:[0n,0n,0n,0n,0n],after:initial});
  const init=step('Initialization permutation p[12]','Twelve rounds spread the input bits through the state. Mixing paint is an analogy: these are precise, deterministic bit operations.');p(init,12);
  record(init,'Mix the key again','After p[12]: x3 XOR K0; x4 XOR K1.',s=>[s[0],s[1],s[2],s[3]^k0,s[4]^k1]);
  const absorb=step('Authenticate associated data',ad.length===0?'Empty associated data skips AD absorption, AD padding, and its p[8] calls.':'Mix public context into the first two words. A 01 byte marks the end, with zeros filling the 16-byte block.');let offset=0;
  if(ad.length){
    while(offset+16<=ad.length){const block=ad.slice(offset,offset+16);record(absorb,`Absorb AD block ${offset/16+1}`,'Rate XOR full AD block. A full final block needs a separate padding-only block.',s=>setRate(s,xor(rateBytes(s),block)),block);p(absorb,8);offset+=16;}
    const block=pad(ad.slice(offset));record(absorb,'Absorb AD padding','Rate XOR (remaining AD || 01 || zeros). Exactly 16 bytes gets a separate 01 + 15 zeros block.',s=>setRate(s,xor(rateBytes(s),block)),block);p(absorb,8);
  }else record(absorb,'Empty AD: skip','No AD padding or AD permutation for zero-byte AD.',s=>s);
  const domain=step('Separate context from the message','A marker tells Ascon that public context has ended and secret message processing starts.');
  record(domain,'Toggle the domain bit','x4 XOR 0x8000000000000000: bit 63 of x4, using the NIST little-endian convention.',s=>[s[0],s[1],s[2],s[3],s[4]^(1n<<63n)]);
  const message=step('Encrypt the message','Each plaintext byte combines with its matching state rate byte using XOR. A 1 in one byte flips the matching bit in the other. Ciphertext also updates the state.');
  const parts:Uint8Array[]=[],byteXors:ByteXor[]=[];offset=0;
  const emit=(block:Uint8Array,at:number)=>{const rate=rateBytes(state),cipher=xor(block,rate);parts.push(cipher);block.forEach((v,i)=>byteXors.push({index:at+i,plaintext:v,rate:rate[i],ciphertext:cipher[i]}));return cipher;};
  while(offset+16<=plaintext.length){const cipher=emit(plaintext.slice(offset,offset+16),offset);record(message,`Encrypt full block ${offset/16+1}`,'C = plaintext XOR rate. Replace the rate with C, then apply p[8].',s=>setRate(s,cipher),cipher);p(message,8);offset+=16;}
  const tail=plaintext.slice(offset),cipherTail=emit(tail,offset);
  record(message,'Encrypt tail and pad','Replace used rate bytes with ciphertext; XOR 01 into the next byte. Padding is mandatory for an empty message and for the empty tail after a full block. No p[8] follows this tail.',s=>{const rate=rateBytes(s);rate.set(cipherTail);rate[tail.length]^=1;return setRate(s,rate);},pad(tail));
  const finalization=step('Create the authentication tag','Mix the key in, apply twelve more rounds, then mix the key again. The final two words become a 16-byte authentication tag.');
  record(finalization,'Key before final p[12]','x2 XOR K0; x3 XOR K1.',s=>[s[0],s[1],s[2]^k0,s[3]^k1,s[4]]);p(finalization,12);
  record(finalization,'Key after final p[12]','x3 XOR K0; x4 XOR K1. Tag = little-endian x3 || little-endian x4.',s=>[s[0],s[1],s[2],s[3]^k0,s[4]^k1]);
  const ciphertext=join(...parts),tag=join(bytesLE(state[3]),bytesLE(state[4]));
  step('Your sealed message','Send ciphertext and tag along with the public nonce and context. Keep the key secret. The receiver must verify the tag before releasing plaintext.');
  return {steps,initial,final:state,byteXors,ciphertext,tag,combined:join(ciphertext,tag)};
}
export const encryptBytes=(input:ByteInputs)=>buildAeadTrace(input).combined;
/** Reconstruct state from received ciphertext; verify a recomputed tag before
 * returning plaintext. No comparison with an expected plaintext or cached tag.
 * JS is not claimed constant-time or hardened against side channels. */
export function decryptBytes(key:Uint8Array,nonce:Uint8Array,combined:Uint8Array,ad:Uint8Array):{authenticated:true;plaintext:Uint8Array}|{authenticated:false;plaintext:null}{
  const[k0,k1,n0,n1]=words(key,nonce);if(combined.length<16)return {authenticated:false,plaintext:null};
  let s=permute([IV,k0,k1,n0,n1],12);s=[s[0],s[1],s[2],s[3]^k0,s[4]^k1];
  if(ad.length){let i=0;while(i+16<=ad.length){s=permute(setRate(s,xor(rateBytes(s),ad.slice(i,i+16))),8);i+=16;}s=permute(setRate(s,xor(rateBytes(s),pad(ad.slice(i)))),8);}
  s=[s[0],s[1],s[2],s[3],s[4]^(1n<<63n)];const ciphertext=combined.slice(0,-16),supplied=combined.slice(-16),plain:Uint8Array[]=[];let i=0;
  while(i+16<=ciphertext.length){const block=ciphertext.slice(i,i+16);plain.push(xor(block,rateBytes(s)));s=permute(setRate(s,block),8);i+=16;}
  const tail=ciphertext.slice(i),rate=rateBytes(s);plain.push(xor(tail,rate));rate.set(tail);rate[tail.length]^=1;s=setRate(s,rate);
  s=permute([s[0],s[1],s[2]^k0,s[3]^k1,s[4]],12);const tag=join(bytesLE(s[3]^k0),bytesLE(s[4]^k1));let difference=0;
  for(let j=0;j<16;j++)difference|=tag[j]^supplied[j];
  return difference===0?{authenticated:true,plaintext:join(...plain)}:{authenticated:false,plaintext:null};
}
