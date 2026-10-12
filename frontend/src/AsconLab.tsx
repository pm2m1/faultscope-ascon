import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, Pause, Play, RotateCcw, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react';
import {
  type FiveWords, type ReplayScenario, allOnes, asconTrace, compareReplay,
  hex64, parseLaneHex, sequence, zeros,
} from './asconTrace';

const phaseSteps = [
  {
    label: 'Initialization', permutation: 'p[12]', headline: 'Initialize the keyed state',
    detail: 'Combine the Ascon-AEAD128 initialization constant, 128-bit key and 128-bit nonce. Apply p[12], then mix the secret key into the state again.',
    footnote: 'A unique nonce must be used with each encryption under the same key.',
  },
  {
    label: 'Associated data', permutation: 'p[8]', headline: 'Authenticate additional context',
    detail: 'Absorb associated-data blocks into the rate portion of the state and run p[8] for each processed full-rate block. A full final block receives a separate padding step.',
    footnote: 'Associated data is authenticated but not encrypted; empty AD follows a special path.',
  },
  {
    label: 'Domain separation', permutation: 'bit toggle', headline: 'Separate header processing from payload processing',
    detail: 'Flip the specified domain-separation bit before processing the plaintext so associated data and messages remain cryptographically distinct.',
    footnote: 'This is a protocol step, not an additional standalone permutation.',
  },
  {
    label: 'Plaintext processing', permutation: 'p[8]', headline: 'Produce ciphertext while updating state',
    detail: 'Mix plaintext into the state, emit ciphertext from the rate words, and advance p[8] between full message blocks. The final partial block is padded.',
    footnote: 'Exact padding and extra permutation calls depend on the block length.',
  },
  {
    label: 'Finalization and tag', permutation: 'p[12]', headline: 'Compute the authentication tag',
    detail: 'Inject the key into the final state, apply p[12], then derive the 128-bit authentication tag from the keyed state.',
    footnote: 'Tag generation here is an explanation of encryption; tag verification occurs during decryption.',
  },
] as const;

const scenarios: { value: ReplayScenario; label: string; meaning: string }[] = [
  { value: 'clean', label: 'No fault', meaning: 'Both executions use the same correct starting state.' },
  { value: 'first_only', label: 'First-pass bit flip', meaning: 'One transient fault affects only the first permutation execution.' },
  { value: 'replay_only', label: 'Replay-only bit flip', meaning: 'One transient fault affects only the replay execution.' },
  { value: 'dual_identical', label: 'Identical faults in both passes', meaning: 'The same bit is flipped before the same round in both executions.' },
  { value: 'checkpoint_shared', label: 'Shared checkpoint fault', meaning: 'Both executions receive the same wrong checkpoint input.' },
  { value: 'checkpoint_replay', label: 'Replay checkpoint fault', meaning: 'Only the replay receives a bit-flipped checkpoint input.' },
  { value: 'suppress_replay_alarm', label: 'Replay fault + alarm suppression', meaning: 'A replay mismatch is present, but the simulated comparator alarm is forcibly suppressed.' },
  { value: 'suppress_first_alarm', label: 'First fault + alarm suppression', meaning: 'The mismatch is suppressed, but the replay result remains correct in this model.' },
];

function stageText(stage: string) {
  return ({ input: 'Initial state', constant: 'Round constant', substitution: 'Nonlinear substitution', diffusion: 'Linear diffusion' } as Record<string, string>)[stage] ?? stage;
}

function StateWords({ title, lanes, isMuted = false }: { title: string; lanes: FiveWords; isMuted?: boolean }) {
  return <div className={`lab-lanes ${isMuted ? 'lab-muted' : ''}`}>
    <div className="lab-lanes-title">{title}</div>
    {lanes.map((word, i) => <div className="lab-lane" key={i}>
      <span>x{i}</span><code>{hex64(word)}</code>
    </div>)}
  </div>;
}

function Playback({ step, length, playing, setStep, setPlaying }: {
  step: number; length: number; playing: boolean;
  setStep: (update: (x: number) => number) => void; setPlaying: (v: boolean) => void;
}) {
  return <div className="lab-player">
    <button type="button" aria-label="Restart animation" onClick={() => {setPlaying(false);setStep(() => 0);}}><RotateCcw size={15}/></button>
    <button type="button" aria-label="Previous animation step" disabled={step === 0} onClick={() => {setPlaying(false);setStep(x => Math.max(0, x - 1));}}><ArrowLeft size={15}/></button>
    <button className="lab-play-primary" type="button" aria-label={playing ? 'Pause animation' : 'Play animation'} onClick={() => {if (step === length - 1) setStep(() => 0);setPlaying(!playing);}}>
      {playing ? <Pause size={15}/> : <Play size={15}/>} {playing ? 'Pause' : 'Play'}
    </button>
    <button type="button" aria-label="Next animation step" disabled={step >= length - 1} onClick={() => {setPlaying(false);setStep(x => Math.min(length - 1, x + 1));}}><ArrowRight size={15}/></button>
    <span className="lab-count">{step + 1} / {length}</span>
  </div>;
}

export default function AsconLab() {
  const [tab, setTab] = useState<'rounds' | 'aead' | 'replay'>('rounds');
  const [rounds, setRounds] = useState<8 | 12>(12);
  const [laneInputs, setLaneInputs] = useState<string[]>(zeros.map(hex64));
  const [state, setState] = useState<FiveWords>(zeros);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [workflowIndex, setWorkflowIndex] = useState(0);
  const [scenario, setScenario] = useState<ReplayScenario>('first_only');
  const [faultRound, setFaultRound] = useState(0);
  const [faultBit, setFaultBit] = useState(0);
  const [defenseStep, setDefenseStep] = useState(0);
  const [defensePlaying, setDefensePlaying] = useState(false);
  const frames = useMemo(() => asconTrace(state, rounds), [state, rounds]);
  const frame = frames[step] ?? frames[0];
  const result = useMemo(() => compareReplay(state, rounds, scenario, Math.min(faultRound, rounds - 1), faultBit), [state, rounds, scenario, faultRound, faultBit]);
  const laneValidity = laneInputs.map(s => parseLaneHex(s) !== null);
  const inputValid = laneValidity.every(Boolean);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setStep(prev => {
      if (prev >= frames.length - 1) {setPlaying(false);return prev;}
      return prev + 1;
    }), 900);
    return () => window.clearInterval(id);
  }, [playing, frames.length]);
  useEffect(() => {
    if (!defensePlaying) return;
    const id = window.setInterval(() => setDefenseStep(prev => {
      if (prev >= 4) {setDefensePlaying(false);return prev;}
      return prev + 1;
    }), 1150);
    return () => window.clearInterval(id);
  }, [defensePlaying]);

  const setPreset = (words: FiveWords) => {
    setLaneInputs(words.map(hex64));setState(words);setPlaying(false);setStep(0);setDefensePlaying(false);setDefenseStep(0);
  };
  const applyInputs = () => {
    if (!inputValid) return;
    setState(laneInputs.map(s => parseLaneHex(s)!) as unknown as FiveWords);
    setPlaying(false);setStep(0);setDefensePlaying(false);setDefenseStep(0);
  };
  const switchTab = (next: typeof tab) => {setTab(next);setPlaying(false);setDefensePlaying(false);};
  const wordStages = ['Checkpoint', 'First pass', 'Clean / faulted replay', 'Compare', 'Output policy'];

  return <section id="ascon-lab" className="card panel lab-panel" aria-label="Interactive Ascon learning lab">
    <div className="panel-head"><div><div className="panel-kicker">PHASE 8B · EDUCATIONAL SIMULATOR</div><h2>Interactive Ascon learning lab</h2></div><Sparkles size={20}/></div>
    <p className="panel-explain">Step through the real p[8]/p[12] permutation, explore the AEAD workflow, and replay modeled fault outcomes. The lab computes locally and never changes recorded experiment evidence.</p>
    <div className="lab-tabs" role="group" aria-label="Select learning lab module">
      <button type="button" className={tab === 'rounds' ? 'selected' : ''} aria-pressed={tab === 'rounds'} onClick={() => switchTab('rounds')}>Permutation rounds</button>
      <button type="button" className={tab === 'aead' ? 'selected' : ''} aria-pressed={tab === 'aead'} onClick={() => switchTab('aead')}>AEAD workflow</button>
      <button type="button" className={tab === 'replay' ? 'selected' : ''} aria-pressed={tab === 'replay'} onClick={() => switchTab('replay')}>Fault &amp; defense</button>
    </div>

    {tab !== 'aead' && <div className="lab-inputs">
      <div className="lab-input-heading"><strong>Starting state — five 64-bit words</strong><span>320 bits · hexadecimal · educational test inputs</span></div>
      <div className="lab-preset"><button type="button" onClick={() => setPreset(zeros)}>All zero</button><button type="button" onClick={() => setPreset(sequence)}>1–5 sequence</button><button type="button" onClick={() => setPreset(allOnes)}>All ones</button></div>
      <div className="lab-input-grid">{laneInputs.map((value, i) => <label key={i}>x{i}
        <input className={!laneValidity[i] ? 'lab-invalid' : ''} aria-label={`Input x${i} hexadecimal word`} value={value} spellCheck={false} maxLength={18} onChange={e => setLaneInputs(prev => prev.map((x, index) => index === i ? e.target.value : x))}/>
      </label>)}</div>
      <div className="lab-input-actions"><button type="button" disabled={!inputValid} onClick={applyInputs}>Apply state</button>{!inputValid && <span role="alert">Each lane needs 1–16 hexadecimal digits.</span>}
        <label className="lab-select-inline">Permutation <select aria-label="Permutation rounds" value={rounds} onChange={e => {setRounds(Number(e.target.value) as 8 | 12);setPlaying(false);setStep(0);setFaultRound(0);setDefenseStep(0);}}><option value={12}>p[12]</option><option value={8}>p[8]</option></select></label>
      </div>
    </div>}

    {tab === 'rounds' && <div className="lab-section">
      <div className="lab-stage-head"><div><div className="panel-kicker">{frame.roundIndex === -1 ? 'PERMUTATION INPUT' : `ROUND ${frame.roundIndex + 1} / ${rounds}`} · {stageText(frame.stage).toUpperCase()}</div><h3>{stageText(frame.stage)}</h3></div><span className="lab-stage-index">{frame.constant === null ? 'Before p' : `RC = 0x${frame.constant.toString(16).padStart(2, '0')}`}</span></div>
      <div className="lab-stage-track" aria-label="Animation position">{frames.map((f, i) => <button key={i} type="button" aria-label={`Jump to step ${i + 1}: ${stageText(f.stage)}`} className={`lab-tick ${i <= step ? 'passed' : ''} ${i === step ? 'here' : ''}`} onClick={() => {setPlaying(false);setStep(i);}}/>)}</div>
      <p className="lab-explain" aria-live="polite">{frame.explanation}</p>
      <StateWords title="Current 320-bit state" lanes={frame.lanes}/>
      <Playback step={step} length={frames.length} playing={playing} setStep={setStep} setPlaying={setPlaying}/>
      <div className="lab-formula">{frame.stage === 'constant' ? 'x2 ← x2 ⊕ RC' : frame.stage === 'substitution' ? '5-bit nonlinear substitution applied across 64 columns' : frame.stage === 'diffusion' ? 'xᵢ ← xᵢ ⊕ ROTR(xᵢ, aᵢ) ⊕ ROTR(xᵢ, bᵢ)' : '320-bit permutation state = (x0, x1, x2, x3, x4)'}</div>
      <p className="lab-disclaimer">The exact bit transformations are calculated locally using 64-bit BigInt operations; all 8 or 12 rounds are shown, not illustrative placeholders.</p>
    </div>}

    {tab === 'aead' && <div className="lab-section">
      <div className="lab-workflow" role="group" aria-label="Choose AEAD workflow phase">
        {phaseSteps.map((p, i) => <button key={p.label} type="button" className={workflowIndex === i ? 'selected' : ''} aria-pressed={workflowIndex === i} onClick={() => setWorkflowIndex(i)}><span>0{i + 1}</span>{p.label}</button>)}
      </div>
      <div className="lab-workflow-detail" aria-live="polite">
        <div className="panel-kicker">STEP {workflowIndex + 1} / 5 · {phaseSteps[workflowIndex].permutation}</div>
        <h3>{phaseSteps[workflowIndex].headline}</h3>
        <p>{phaseSteps[workflowIndex].detail}</p>
        <div className="lab-info">{phaseSteps[workflowIndex].footnote}</div>
      </div>
      <div className="lab-player"><button type="button" disabled={workflowIndex === 0} onClick={() => setWorkflowIndex(i => Math.max(0, i - 1))}><ArrowLeft size={15}/> Previous</button><button type="button" disabled={workflowIndex === 4} onClick={() => setWorkflowIndex(i => Math.min(4, i + 1))}>Next step <ArrowRight size={15}/></button><span className="lab-count">{workflowIndex + 1} / 5</span></div>
      <p className="lab-disclaimer">This workflow explains Ascon-AEAD128 encryption. It is not an encrypt/decrypt tool; padding and permutation calls depend on data length. Sender tag generation alone does not establish recipient authentication.</p>
    </div>}

    {tab === 'replay' && <div className="lab-section">
      <div className="lab-def-controls">
        <label>Fault scenario <select aria-label="Fault scenario" value={scenario} onChange={e => {setScenario(e.target.value as ReplayScenario);setDefenseStep(0);setDefensePlaying(false);}}>{scenarios.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
        <label>Pre-round index <input aria-label="Fault round index" type="number" min={0} max={rounds - 1} value={faultRound} onChange={e => {const n=Number(e.target.value);setFaultRound(Number.isFinite(n) ? Math.min(rounds - 1,Math.max(0,Math.floor(n))) : 0);setDefenseStep(0);setDefensePlaying(false);}}/></label>
        <label>State bit (0–319) <input aria-label="Fault bit index" type="number" min={0} max={319} value={faultBit} onChange={e => {const n=Number(e.target.value);setFaultBit(Number.isFinite(n) ? Math.min(319, Math.max(0,Math.floor(n))) : 0);setDefenseStep(0);setDefensePlaying(false);}}/></label>
      </div>
      <p className="lab-explain">{scenarios.find(s => s.value === scenario)?.meaning}</p>
      <div className="lab-replay-flow">{wordStages.map((name, index) => <div key={name} className={`lab-flow-block ${index === defenseStep ? 'selected' : ''} ${index <= defenseStep ? 'passed' : ''}`}><small>0{index + 1}</small>{name}</div>)}</div>
      <div className="lab-results" aria-live="polite">
        <div><strong>First pass</strong><span>{defenseStep >= 1 ? (result.firstFired ? 'Bit flip fired' : 'No pre-round bit flip') : 'Not executed'}</span></div>
        <div><strong>Replay pass</strong><span>{defenseStep >= 2 ? (result.replayFired ? 'Bit flip fired' : 'No pre-round bit flip') : 'Not executed'}</span></div>
        <div><strong>Raw mismatch</strong><span>{defenseStep >= 3 ? (result.rawMismatch ? 'Yes' : 'No') : 'Pending'}</span></div>
        <div><strong>Alarm</strong><span className={defenseStep >= 3 && result.alarm ? 'lab-attention' : ''}>{defenseStep >= 3 ? (result.alarm ? 'Raised' : 'Not raised') : 'Pending'}</span></div>
        <div><strong>Released state</strong><span className={defenseStep >= 4 && result.incorrectRelease ? 'lab-attention' : ''}>{defenseStep >= 4 ? (!result.valid ? 'Suppressed' : result.incorrectRelease ? 'Incorrect' : 'Correct') : 'Pending'}</span></div>
      </div>
      {defenseStep >= 2 && <div className="lab-three-states"><StateWords title="Golden (unfaulted)" lanes={result.golden}/><StateWords title="First execution" lanes={result.first}/><StateWords title="Replay execution" lanes={result.replay}/></div>}
      <Playback step={defenseStep} length={5} playing={defensePlaying} setStep={setDefenseStep} setPlaying={setDefensePlaying}/>
      {defenseStep === 4 && <div className={`lab-conclusion ${result.incorrectRelease ? 'risk' : ''}`}>
        {result.alarm ? <ShieldCheck size={20}/> : result.incorrectRelease ? <ShieldAlert size={20}/> : <ShieldCheck size={20}/>}
        <div><strong>{result.alarm ? 'Mismatch detected — result suppressed' : result.incorrectRelease ? 'Silent incorrect permutation state released' : 'Output matches the unfaulted permutation'}</strong><p>{result.alarm ? 'The comparator detects a mismatch and the output-valid flag stays low.' : result.incorrectRelease ? 'Two runs can agree on an incorrect state, or a simulated comparator fault can suppress the mismatch alarm.' : 'In this selected model, the replay state matches the fault-free result.'}</p></div>
      </div>}
      <p className="lab-disclaimer">Research-only permutation demonstration with selected pre-round faults. These are synthetic controls, not physical glitch instructions, key leakage, or AEAD tag-verification bypasses. The recorded Phase 7A/7B campaigns remain unchanged.</p>
    </div>}
  </section>;
}
