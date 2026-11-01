import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Activity, AlertTriangle, ArrowUpRight, Cpu, Database, Fingerprint, Gauge, Layers3, RefreshCw, ShieldCheck, Zap, FlaskConical, GitCompareArrows, BookOpen } from 'lucide-react';
import AsconLab from './AsconLab';
import { ProjectIntro, ProjectArchitecture, ProtectionDemo, MetricMeaning } from './ProjectStory';

type Design = { design: string; generic_cells: number; ff_bits: number; combinational_cells: number };
type Phase = { phase: number; name: string; cases: number; applied: number; detected: number; false_alarms: number };
type Summary = {
  metrics: {
    cases: number; applied_faults: number; detected_faults: number; coverage_percent: number | null;
    false_alarms: number; unfaulted_cases: number; mean_baseline_cycles: number;
    mean_protected_cycles: number; relative_mean_latency_increase_percent: number;
    fail_closed_violations: number;
  };
  resources: Design[];
  phases: Phase[];
  provenance: { git_commit: string; reference_commit: string; yosys: string; sv2v: string; campaign_sha256: string };
  scope: { cipher: string; plaintext_ad_max_bytes: number; hardware: string; fault_model: string; disclaimer: string };
};
type CaseRow = {
  case: number; phase: number; round: number; bit: number; msg_len: number; ad_len: number;
  injected: number; detected: number; valid: number; baseline_cycles: number; protected_cycles: number;
  outcome: string;
};
type Page = { total: number; offset: number; limit: number; rows: CaseRow[] };
type ResearchKind = 'permutation' | 'aead';
type ResearchMetric = {
  cases: number; raw_mismatches: number; alarms: number; incorrect_releases: number;
  valid_releases: number; first_fault_events: number; replay_fault_events: number;
  checkpoint_fault_events: number;
};
type ResearchGroup = ResearchMetric & { scenario?: string; phase?: number };
type ResearchCampaign = {
  label: string; scope: string; output_label: string; fault_model: string;
  sha256: string; metrics: ResearchMetric; scenarios: ResearchGroup[]; phases: ResearchGroup[];
};
type ResearchSummary = {
  campaigns: { permutation: ResearchCampaign; aead: ResearchCampaign };
  limitations: string[];
};
type ResearchCase = {
  case: number; scenario: string; rounds?: number; phase?: number;
  ad_len?: number; msg_len?: number; first_round?: number; first_bit?: number;
  replay_round?: number; replay_bit?: number; checkpoint_mode?: number;
  first_fired: number; replay_fired: number; checkpoint_fired: number;
  raw_mismatch: number; alarm: number; valid: number; incorrect_release: number; cycles: number;
};
type ResearchPage = { kind: ResearchKind; total: number; offset: number; limit: number; rows: ResearchCase[] };
const scenarioNames: Record<string, string> = {
  clean: 'Both calculations unfaulted', first_only: 'Only the first calculation is disturbed',
  replay_only: 'Only the repeat calculation is disturbed', dual_identical: 'The same fault in both calculations',
  dual_different: 'Different faults in both calculations', checkpoint_shared: 'Both start from a corrupted checkpoint',
  checkpoint_replay: 'Only the replay checkpoint is corrupted', suppress_replay_alarm: 'Replay fault with the alarm forced off',
  suppress_first_alarm: 'First-pass fault with the alarm forced off', first_invalid_bit: 'First fault targets an invalid bit',
  replay_invalid_round: 'Replay fault targets an unused round', checkpoint_invalid_bit: 'Checkpoint fault targets an invalid bit',
};
const scenarioLabel = (name: string) => scenarioNames[name] ?? name.replaceAll('_', ' ');
const researchOutcomes = [
  ['all', 'All outcomes'], ['alarm', 'Alarm raised'],
  ['incorrect_release', 'Incorrect result released as valid'], ['raw_mismatch', 'The two calculations disagree'],
  ['valid_correct', 'Valid and correct'], ['no_alarm', 'No alarm'],
];


const fmt = (n: number) => n.toLocaleString('en-US');
const pct = (n: number | null) => n === null ? 'N/A' : `${n.toFixed(1)}%`;
const phaseText = (n: number) => (({ 0: 'Set up the key and nonce', 1: 'Add public context', 2: 'Finish public context', 3: 'Encrypt the message', 4: 'Create the authentication tag' } as Record<number, string>)[n] ?? `Phase ${n}`);

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) {
    let why = r.statusText;
    try { const body = await r.json(); why = body.detail ?? why; } catch { /* no JSON body */ }
    throw new Error(`${r.status}: ${why}`);
  }
  return await r.json() as T;
}

function MetricCard({ label, value, detail, icon, meaning }: { label: string; value: string; detail: string; icon: ReactNode; meaning: {measure:string;why:string;conclusion:string;limit:string} }) {
  return <div className="metric card">
    <div className="metric-label"><span>{label}</span>{icon}</div>
    <div className="metric-value">{value}</div>
    <div className="metric-detail">{detail}</div>
    <MetricMeaning {...meaning}/>
  </div>;
}

export default function App() {
  const [technical, setTechnical] = useState(false);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [status, setStatus] = useState('all');
  const [phase, setPhase] = useState('all');
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshCounter, setRefreshCounter] = useState(0);
  const [activeSection, setActiveSection] = useState<'overview' | 'comparison' | 'ledger' | 'research' | 'ascon-lab'>('overview');
  const [research, setResearch] = useState<ResearchSummary | null>(null);
  const [researchPage, setResearchPage] = useState<ResearchPage | null>(null);
  const [researchError, setResearchError] = useState('');
  const [researchKind, setResearchKind] = useState<ResearchKind>('aead');
  const [researchScenario, setResearchScenario] = useState('all');
  const [researchOutcome, setResearchOutcome] = useState('all');
  const [researchPhase, setResearchPhase] = useState('all');
  const [researchOffset, setResearchOffset] = useState(0);
  const researchLimit = 12;
  const resetResearchFilters = () => { setResearchScenario('all'); setResearchOutcome('all'); setResearchPhase('all'); setResearchOffset(0); };
  const jumpTo = (id: 'overview' | 'comparison' | 'ledger' | 'research' | 'ascon-lab') => {
    setActiveSection(id);
    const target=document.getElementById(id);
    const disclosure=target?.closest('details'); if(disclosure) disclosure.open=true;
    target?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth', block: 'start' });
  };
  const resourceMax = useMemo(() => Math.max(1, ...(summary?.resources.map(x => x.generic_cells) ?? [1])), [summary]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getJson<Summary>('/api/summary').then(data => {
      if (!cancelled) { setSummary(data); setError(''); }
    }).catch(e => {
      if (!cancelled) { setError(String(e)); setSummary(null); }
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshCounter]);

  useEffect(() => {
    if (!summary) return;
    let cancelled = false;
    const params = new URLSearchParams({ offset: String(offset), limit: '15', status });
    if (phase !== 'all') params.set('phase', phase);
    getJson<Page>(`/api/cases?${params}`).then(data => {
      if (!cancelled) setPage(data);
    }).catch(e => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [status, phase, offset, summary]);

  useEffect(() => {
    let cancelled = false;
    getJson<ResearchSummary>('/api/research/summary').then(data => {
      if (!cancelled) { setResearch(data); setResearchError(''); }
    }).catch(e => {
      if (!cancelled) { setResearchError(String(e)); setResearch(null); setResearchPage(null); }
    });
    return () => { cancelled = true; };
  }, [refreshCounter]);

  useEffect(() => {
    if (!research) return;
    let cancelled = false;
    setResearchPage(null);
    const params = new URLSearchParams({
      kind: researchKind, scenario: researchScenario, outcome: researchOutcome,
      offset: String(researchOffset), limit: String(researchLimit),
    });
    if (researchPhase !== 'all') params.set(researchKind === 'aead' ? 'phase' : 'rounds', researchPhase);
    getJson<ResearchPage>(`/api/research/cases?${params}`).then(data => {
      if (!cancelled) setResearchPage(data);
    }).catch(e => { if (!cancelled) { setResearchError(String(e)); setResearchPage(null); } });
    return () => { cancelled = true; };
  }, [research, researchKind, researchScenario, researchOutcome, researchPhase, researchOffset]);

  useEffect(() => {
    const followResults = () => { if (window.location.hash === '#/results' && summary) {
      setActiveSection('research'); requestAnimationFrame(() => document.getElementById('research')?.scrollIntoView({block:'start',behavior:'instant'}));
    }};
    followResults(); window.addEventListener('hashchange',followResults);
    return () => window.removeEventListener('hashchange',followResults);
  }, [summary]);

  return <div className={`shell project-dashboard ${technical?'is-technical':''}`}>
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Fingerprint size={24}/></div><div><strong>FAULTSCOPE</strong><small>ASCON RESEARCH LAB</small></div></div>
      <div className="side-label">WORKSPACE</div>
      <button type="button" className={`nav-link ${activeSection === 'overview' ? 'active' : ''}`} aria-current={activeSection === 'overview' ? 'location' : undefined} onClick={() => jumpTo('overview')}><Activity size={17}/> Evidence overview</button>
      <button type="button" disabled={!summary} className={`nav-link ${activeSection === 'comparison' ? 'active' : ''}`} aria-current={activeSection === 'comparison' ? 'location' : undefined} onClick={() => jumpTo('comparison')}><Layers3 size={17}/> Phase comparison</button>
      <button type="button" disabled={!summary} className={`nav-link ${activeSection === 'ledger' ? 'active' : ''}`} aria-current={activeSection === 'ledger' ? 'location' : undefined} onClick={() => jumpTo('ledger')}><Database size={17}/> Experiment ledger</button>
      <button type="button" disabled={!summary} className={`nav-link ${activeSection === 'research' ? 'active' : ''}`} aria-current={activeSection === 'research' ? 'location' : undefined} onClick={() => jumpTo('research')}><FlaskConical size={17}/> Adversarial research</button>
      <button type="button" className={`nav-link ${activeSection === 'ascon-lab' ? 'active' : ''}`} aria-current={activeSection === 'ascon-lab' ? 'location' : undefined} onClick={() => jumpTo('ascon-lab')}><BookOpen size={17}/> Ascon learning lab</button>
      <div className="sidebar-spacer"/>
      <div className="sidebar-note"><ShieldCheck size={18}/><div><strong>Evidence-driven</strong><p>Displays local, hash-verified Phase 4B, 7A, 7B and Phase 5 reports. No fabricated experiment results.</p></div></div>
      <div className="sidebar-footer">NIST SP 800-232<br/>Local research environment</div>
    </aside>

    <main>
      <header className="topbar">
        <div className="breadcrumbs">Our CNS project <span>/</span> <strong>{activeSection === 'overview' ? 'Experiment overview' : activeSection === 'comparison' ? 'Phase comparison' : activeSection === 'ledger' ? 'Experiment ledger' : activeSection === 'research' ? 'Adversarial research' : 'Ascon learning lab'}</strong></div>
        <div className="top-actions"><div className="project-view-switch" role="group" aria-label="Dashboard presentation"><button type="button" aria-pressed={!technical} onClick={()=>setTechnical(false)}>Simple View</button><button type="button" aria-pressed={technical} onClick={()=>setTechnical(true)}>Technical View</button></div><div className="status-chip"><span className={'dot ' + (summary ? 'ok' : 'off')}/>{summary ? 'Reports loaded' : 'Awaiting evidence'}</div>
        <button className="refresh" onClick={() => setRefreshCounter(x => x + 1)}><RefreshCw size={15}/> Refresh</button></div>
      </header>
      <section className="content">
        <ProjectIntro onResults={()=>jumpTo('research')}/>

        {loading && <div className="notice">Loading local verification reports…</div>}
        {error && <div className="notice error"><AlertTriangle size={18}/> <span>{error}<br/><small>Generate Phase 4B and Phase 5 evidence, then press Refresh.</small></span></div>}
        {summary && <>
          <div className="metrics-grid" aria-label="Recorded clean-replay findings">
            <MetricCard label="Hardware tests performed" value={fmt(summary.metrics.cases)} detail={`${summary.metrics.applied_faults} with applied faults; ${summary.metrics.unfaulted_cases} without injection`} icon={<Activity size={19}/>} meaning={{measure:'Configured RTL simulation cases, not physical board trials.',why:'Tests include both disturbed and undisturbed calculations.',conclusion:'We checked detection and unwanted alarms across these recorded cases.',limit:'This is a deterministic test set, not every possible input, fault, or real-world attack.'}}/>
            <MetricCard label="Faults detected in our clean-replay test" value={`${summary.metrics.detected_faults} / ${summary.metrics.applied_faults}`} detail={`${pct(summary.metrics.coverage_percent)} of applied faults; the repeat calculation was deliberately clean`} icon={<ShieldCheck size={19}/>} meaning={{measure:'Applied first-pass faults that raised the detection alarm.',why:'A disagreement must be caught before an incorrect result is released.',conclusion:'Every applied fault was detected in this deliberately narrow recorded model.',limit:'Clean replay, checkpoint and comparator are trusted here. This is not guaranteed fault security.'}}/>
            <MetricCard label="False alarms observed" value={fmt(summary.metrics.false_alarms)} detail={`Among ${summary.metrics.unfaulted_cases} cases without injection`} icon={<Zap size={19}/>} meaning={{measure:'Alarms in runs where no tested fault was injected.',why:'Useful protection should not reject correct calculations unnecessarily.',conclusion:'No false alarms were observed in these undisturbed cases.',limit:'Zero observed false alarms is a test result, not a proof for all operating conditions.'}}/>
            <MetricCard label="Extra processing time (simulation cycles)" value={`+${summary.metrics.relative_mean_latency_increase_percent.toFixed(2)}%`} detail="More mean clock cycles with protection; not elapsed milliseconds" icon={<Gauge size={19}/>} meaning={{measure:'Relative increase in mean protected versus baseline simulation cycles.',why:'Repeating a calculation has a performance cost.',conclusion:'The protected design uses about twice the mean cycles in this campaign.',limit:'Cycles are not measured board speed, physical latency or a clock-frequency result.'}}/>
          </div>
        </>}
        <ProjectArchitecture technical={technical}/>
        <ProtectionDemo technical={technical}/>
        {summary && <>

          <div className="panels">
            <section className="card panel">
              <div className="panel-head"><div><div className="panel-kicker">IMPLEMENTATION COST</div><h2>Estimated circuit complexity</h2></div><Cpu size={20}/></div>
              <p className="panel-explain">How much implementation structure does each design need? The bars use the same generic Yosys synthesis settings.</p>
              <div className="bars">
                {summary.resources.map(d => <div className="barrow" key={d.design}>
                  <div className="barlabel"><span>{({baseline:"Without protection",instrumented:"With fault-injection test controls",protected:"With recomputation protection"} as Record<string,string>)[d.design] ?? d.design}<small className="project-technical-inline"> · {d.design}</small></span><strong>{fmt(d.generic_cells)}</strong></div>
                  <div className="track"><div className={'fill ' + d.design} style={{ width: `${100 * d.generic_cells / resourceMax}%` }}/></div>
                  <div className="subbar">Generic Yosys cells<span className="project-technical-inline"> · {fmt(d.ff_bits)} FF output bits · {fmt(d.combinational_cells)} combinational cells</span></div>
                </div>)}
              </div>
              <MetricMeaning measure="Reported generic Yosys cell totals, including historical metadata entries." why="Checkpoints, result storage, comparison and control add implementation cost." conclusion="The protected design costs more generic cells while reusing a single permutation engine." limit="Generic cells are not physical gate area, FPGA LUTs, power, or board performance."/>
            </section>
            <section className="card panel">
              <div className="panel-head"><div><div className="panel-kicker">RUNTIME TRADE-OFF</div><h2>The cost of checking twice</h2></div><Gauge size={20}/></div>
              <p className="panel-explain">Average cycles needed for the same recorded messages and fault-test conditions. A cycle is one step of the simulated circuit clock.</p>
              <div className="cycle-grid">
                <div><div className="cycle-number">{summary.metrics.mean_baseline_cycles.toFixed(2)}</div><div className="cycle-label">Without protection</div></div>
                <ArrowUpRight size={22}/>
                <div><div className="cycle-number protected-number">{summary.metrics.mean_protected_cycles.toFixed(2)}</div><div className="cycle-label">With recomputation</div></div>
              </div>
              <div className="comparison"><div className="comparison-line"><div className="comparison-fill" style={{width: `${100 * summary.metrics.mean_baseline_cycles / Math.max(summary.metrics.mean_protected_cycles, 1)}%`}}/></div><small>Baseline cycles as a share of protected cycles</small></div>
              <MetricMeaning measure="Mean baseline and protected simulation cycle counts from the same campaign." why="Temporal recomputation spends time repeating the critical calculation." conclusion="These means show the cycle cost of adding the defense." limit="These are not milliseconds, physical latency, measured FPGA throughput, or an achieved clock frequency."/>
            </section>
          </div>

          <section className="card panel phases" id="comparison">
            <div className="panel-head"><div><div className="panel-kicker">FAULT LOCALIZATION</div><h2>Where in encryption did we test faults?</h2></div><Layers3 size={20}/></div>
            <p className="panel-explain">Encryption has several stages. We disturbed calculations during setup, public-context processing, message processing and tag creation to check the defense across these different jobs. All bars below still use the narrow clean-replay model.</p>
            <div className="phase-grid">
              {summary.phases.map(p => <div className="phase-card" key={p.phase}>
                <div className="phase-id">ENCRYPTION STAGE<span className="project-technical-inline"> · PHASE {p.phase}</span></div>
                <div className="phase-name">{technical?p.name:phaseText(p.phase)}</div>
                <div className="phase-value">{p.detected}<small> / {p.applied} detected</small></div>
                <div className="phase-track"><div style={{width: `${100 * p.detected / Math.max(p.applied, 1)}%`}}/></div>
                <div className="phase-foot">{p.cases} configured scenarios</div>
              </div>)}
            </div>
          </section>

          <section className="card panel ledger" id="ledger">
            <div className="panel-head"><div><div className="panel-kicker">AUDITABLE EXPERIMENTS</div><h2>Explore each recorded hardware test</h2></div><Database size={20}/></div>
            <div className="project-guide"><strong>What is a test case?</strong> One configured RTL simulation: choose inputs and a fault target, run the circuit, then check its output and alarm. An injection request may not fire if that target is never reached. Use the filters to inspect the recorded cases.</div>
            <details className="project-details"><summary>How to read a test result</summary><div className="project-guide"><dl><dt>Injection</dt><dd>A selected internal bit was actually changed during the run.</dd><dt>Detection</dt><dd>The two calculations disagreed and the alarm was raised.</dd><dt>Valid output</dt><dd>The hardware allowed the result to be released. It does not mean a receiver authenticated it.</dd><dt>Cycle count</dt><dd>Simulated clock steps until completion, not measured elapsed time.</dd></dl><p>Technical flags: injected / fault_applied_o; detected / fault_detected_o; valid / result_valid_o.</p></div></details>
            <div className="filters"><select aria-label="Filter by phase" value={phase} onChange={e => {setPhase(e.target.value);setOffset(0);}}>
              <option value="all">All phases</option>{Array.from(new Set(summary.phases.map(p=>p.phase))).map(p=><option value={p} key={p}>{phaseText(p)}{technical?` (phase ${p})`:''}</option>)}
            </select><select aria-label="Filter by outcome" value={status} onChange={e => {setStatus(e.target.value);setOffset(0);}}>
              <option value="all">All outcomes</option><option value="detected_fault">Detected fault</option><option value="undetected_fault">Undetected fault</option><option value="no_injection">No injection</option><option value="false_alarm">False alarm</option>
            </select><span>{page ? `${fmt(page.total)} matching rows` : 'Loading…'}</span></div>
            <div className="table-scroll"><table><thead><tr><th>TEST</th><th>ENCRYPTION STAGE</th><th className="project-technical-column">ROUND</th><th className="project-technical-column">BIT</th><th className="project-technical-column">AD/MESSAGE</th><th>RESULT</th><th className="project-technical-column">INJECTED / DETECTED / VALID</th><th>UNPROTECTED CYCLES</th><th>PROTECTED CYCLES</th></tr></thead>
              <tbody>{page?.rows.map(r=><tr key={r.case}><td>#{r.case}</td><td>{phaseText(r.phase)}</td><td className="project-technical-column">{r.round}</td><td className="project-technical-column">{r.bit}</td><td className="project-technical-column">{r.ad_len} / {r.msg_len} B</td><td><span className={`outcome ${r.outcome}`}>{({detected_fault:'Fault detected; output blocked',undetected_fault:'Applied fault was not detected',no_injection:'No fault applied',false_alarm:'Alarm without an applied fault'} as Record<string,string>)[r.outcome] ?? r.outcome.replaceAll('_',' ')}</span></td><td className="project-technical-column">{r.injected} / {r.detected} / {r.valid}</td><td>{r.baseline_cycles} cyc</td><td>{r.protected_cycles} cyc</td></tr>)}</tbody></table>
              {page?.rows.length === 0 && <div className="empty">No cases match this filter.</div>}
            </div>
            <div className="pagination"><button disabled={offset===0} onClick={()=>setOffset(x=>Math.max(0,x-15))}>Previous</button><span>{page?.total ? `${offset+1}–${Math.min(offset+15,page.total)} of ${page.total}` : '0 results'}</span><button disabled={!page || offset+15>=page.total} onClick={()=>setOffset(x=>x+15)}>Next</button></div>
          </section>

          <section className="card panel research" id="research">
            <div className="panel-head"><div><div className="panel-kicker">COMPARATIVE SECURITY EVALUATION</div><h2>What changes when the protection itself is challenged?</h2></div><GitCompareArrows size={20}/></div>
            <p className="panel-explain">First we trusted the replay. Then we deliberately challenged both calculations, their checkpoint and the comparison logic. These are different constructed test sets, not real-world attack probabilities.</p>
            {researchError && <div className="notice error"><AlertTriangle size={18}/><span>Advanced evidence unavailable: {researchError}<small>Original Phase 4B dashboard remains available; research figures are not substituted.</small></span></div>}
            {!research && !researchError && <div className="notice">Loading hash-verified Phase 7 evidence…</div>}
            {research && <>
              <div className="research-overview">
                <div className="research-tile">
                  <div className="project-investigation-title">Test 1: One faulty calculation</div><div className="project-technical-inline">Phase 4B · Single fault / clean replay</div>
                  <h3>{fmt(summary.metrics.cases)} tests</h3>
                  <strong>{summary.metrics.detected_faults} / {summary.metrics.applied_faults} applied faults detected</strong>
                  <p>{summary.metrics.unfaulted_cases} cases without injection; {summary.metrics.false_alarms} false alarms. The repeat calculation, checkpoint and comparator were deliberately trusted.</p><MetricMeaning measure="Detected applied faults under clean replay in bounded AEAD encryption." why="Establish a controlled baseline for detection." conclusion="All applied faults in this model were detected, with no observed false alarms." limit="It says nothing universal about faults that also affect replay, checkpoints, or comparison."/>
                </div>
                {(['permutation', 'aead'] as const).map(kind => {
                  const c = research.campaigns[kind];
                  return <div className="research-tile" key={kind}>
                    <div className="project-investigation-title">{kind === 'permutation' ? 'Test 2: What if the comparison can be fooled?' : 'Test 3: Can an incorrect encrypted output escape?'}</div><div className="project-technical-inline">{c.label} · {kind === 'permutation' ? 'Adversarial permutation' : 'Adversarial bounded AEAD'}</div>
                    <h3>{fmt(c.metrics.cases)} tests</h3>
                    <strong>{c.metrics.incorrect_releases} incorrect {kind === "permutation" ? "permutation states" : "ciphertext/tag results"} released as valid</strong>
                    <p>{kind === "permutation" ? "Some constructed cases make two executions agree on a wrong state, or suppress the alarm." : "These cases test whether wrong ciphertext or tags can leave the encryption controller, not whether a receiver accepts them."}</p><MetricMeaning measure={`${c.metrics.incorrect_releases} incorrect outputs allowed through among ${c.metrics.cases} deliberately configured ${kind === "permutation" ? "permutation" : "bounded AEAD"} simulations.`} why="Agreement alone can be undermined if the assumptions behind the comparison are broken." conclusion="The tested protection has limits under these more demanding fault models." limit="This ratio is not an attack probability. An incorrect output release does not establish a successful authentication forgery."/>
                  </div>;
                })}
              </div>
              <div className="research-divider"/>
              <div className="research-subhead">
                <div><div className="panel-kicker">SCENARIO ANALYSIS</div><h3>Fault outcomes by scenario</h3><p>Choose which part we tested, then select a fault scenario to inspect its recorded cases.</p></div>
                <div className="research-switch" role="group" aria-label="Select advanced experiment">
                  <button type="button" aria-pressed={researchKind === 'permutation'} className={researchKind === 'permutation' ? 'selected' : ''} onClick={() => {setResearchKind('permutation');resetResearchFilters();}}>Permutation tests<span className="project-technical-inline"> · Phase 7A</span></button>
                  <button type="button" aria-pressed={researchKind === 'aead'} className={researchKind === 'aead' ? 'selected' : ''} onClick={() => {setResearchKind('aead');resetResearchFilters();}}>Encrypted-output tests<span className="project-technical-inline"> · Phase 7B</span></button>
                </div>
              </div>
              <p className="panel-explain research-scope">{researchKind === "permutation" ? "A permutation transforms five state words. A wrong state being allowed through is the outcome measured here." : "Here we test the bounded encryption controller: a wrong ciphertext or tag being released is the measured outcome. Receiver acceptance is a different question."}</p><p className="project-research-note">“The two calculations disagree” means a raw mismatch; an alarm may still be suppressed in the configured model. Checkpoint means the saved starting state shared by the two runs. These counts are not a real-world success rate.</p>
              <div className="scenario-table-scroll"><table className="scenario-table">
                <thead><tr><th>FAULT SCENARIO</th><th>CASES</th><th>CALCULATIONS DISAGREE</th><th>ALARMS RAISED</th><th>INCORRECT RESULTS ALLOWED</th></tr></thead>
                <tbody>{research.campaigns[researchKind].scenarios.map(x => <tr key={x.scenario}>
                  <td><button className="scenario-link" onClick={() => {setResearchScenario(x.scenario ?? 'all');setResearchOffset(0);document.getElementById('research-explorer')?.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',block: 'start'});}}>{scenarioLabel(x.scenario ?? '')}<span className="project-technical-inline"> ({x.scenario})</span></button></td>
                  <td>{x.cases}</td><td>{x.raw_mismatches}</td><td>{x.alarms}</td>
                  <td><div className="scenario-result"><strong className={x.incorrect_releases ? 'research-critical' : ''}>{x.incorrect_releases}</strong><span className="scenario-track"><span style={{width: `${x.cases ? (100*x.incorrect_releases/x.cases) : 0}%`}}/></span></div></td>
                </tr>)}</tbody>
              </table></div>
              <div className="research-divider"/>
              {researchKind === 'aead' && <div className="research-phase-breakdown">
                <div className="panel-kicker">WHERE DID INCORRECT OUTPUTS GET THROUGH?</div>
                <div className="research-phase-grid">{research.campaigns.aead.phases.map(p => <div className="research-phase-tile" key={p.phase}>
                  <div className="phase-id">ENCRYPTION STAGE<span className="project-technical-inline"> · PHASE {p.phase}</span></div><strong>{phaseText(p.phase ?? -1)}</strong>
                  <small>{p.alarms} alarms · {p.incorrect_releases} incorrect releases / {p.cases} configured cases</small>
                </div>)}</div>
              </div>}
              <div className="research-subhead" id="research-explorer">
                <div><div className="panel-kicker">HASH-VERIFIED RECORDED CASES</div><h3>Inspect the harder test cases</h3></div>
                <span className="evidence-tag">SHA-256 pinned · local CSV</span>
              </div>
              <div className="filters research-filters">
                <select aria-label="Adversarial scenario" value={researchScenario} onChange={e => {setResearchScenario(e.target.value);setResearchOffset(0);}}>
                  <option value="all">All fault scenarios</option>{research.campaigns[researchKind].scenarios.map(x => <option key={x.scenario} value={x.scenario}>{scenarioLabel(x.scenario ?? '')}</option>)}
                </select>
                <select aria-label="Adversarial outcome" value={researchOutcome} onChange={e => {setResearchOutcome(e.target.value);setResearchOffset(0);}}>{researchOutcomes.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select>
                <select aria-label="Adversarial phase or permutation rounds" value={researchPhase} onChange={e => {setResearchPhase(e.target.value);setResearchOffset(0);}}>
                  <option value="all">{researchKind === 'aead' ? 'All AEAD phases' : 'Both permutations'}</option>
                  {researchKind === 'aead' ? [0,1,2,3,4].map(p => <option value={p} key={p}>{phaseText(p)}{technical?` (phase ${p})`:''}</option>) : [8,12].map(r => <option value={r} key={r}>p[{r}]</option>)}
                </select>
                <span>{researchPage ? `${fmt(researchPage.total)} matching rows` : 'Loading…'}</span>
              </div>
              <div className="table-scroll"><table className="research-cases-table"><thead><tr>
                <th>CASE</th><th>SCENARIO</th><th>{researchKind === 'aead' ? 'PHASE' : 'PERMUTATION'}</th>
                <th className="project-technical-column">FIRST / REPLAY / CHECKPOINT FAULT</th><th className="project-technical-column">RAW MISMATCH</th><th>ALARM</th><th>OUTPUT ALLOWED</th><th>WRONG OUTPUT</th><th>SIMULATION CYCLES</th>
              </tr></thead><tbody>{researchPage?.rows.map(r => <tr key={r.case}>
                <td>#{r.case}</td><td>{scenarioLabel(r.scenario)}<span className="project-technical-inline"> ({r.scenario})</span></td><td>{researchKind === 'aead' ? phaseText(r.phase ?? -1) : `p[${r.rounds}]`}</td>
                <td className="project-technical-column">{r.first_fired} / {r.replay_fired} / {r.checkpoint_fired}</td><td className="project-technical-column">{r.raw_mismatch}</td>
                <td><span className={`research-flag ${r.alarm ? 'warn' : 'neutral'}`}>{r.alarm ? 'Alarm' : 'None'}</span></td>
                <td>{r.valid ? 'Yes' : 'No'}</td><td><span className={`research-flag ${r.incorrect_release ? 'warn' : 'neutral'}`}>{r.incorrect_release ? 'Incorrect result released as valid' : 'No'}</span></td>
                <td>{r.cycles}</td>
              </tr>)}</tbody></table>{researchPage?.rows.length === 0 && <div className="empty">No recorded cases match these filters.</div>}</div>
              <div className="pagination"><button disabled={researchOffset === 0} onClick={()=>setResearchOffset(x=>Math.max(0,x-researchLimit))}>Previous</button><span>{researchPage?.total ? `${researchOffset+1}–${Math.min(researchOffset+researchLimit,researchPage.total)} of ${researchPage.total}` : '0 results'}</span><button disabled={!researchPage || researchOffset+researchLimit>=researchPage.total} onClick={()=>setResearchOffset(x=>x+researchLimit)}>Next</button></div>
              <div className="project-takeaway" data-testid="project-takeaway"><h3>What did we learn?</h3><p>Repeating a calculation detected every applied fault in our clean-replay tests, but deliberately more difficult fault scenarios revealed limitations in that protection. Stronger protection requires examining the trustworthiness of both executions, the checkpoint, and the comparison logic.</p><small>This is a conclusion about the tested models, not a universal security proof. The deliberately chosen case counts are not real-world attack probabilities, and incorrect ciphertext/tag release is not the same as receiver authentication success.</small></div>
            </>}
          </section>

          <section className="project-lab-guide" aria-labelledby="project-lab-title"><h2 id="project-lab-title">Want to look inside the mathematics?</h2><p>The original Ascon learning lab lets you explore permutation rounds, workflow phases and replay comparisons. It illustrates the calculation, not a complete live hardware run. For message-to-ciphertext and authenticated software decryption, use the <a href="#/walkthrough">Algorithm Walkthrough</a>.</p><details className="project-lab-disclosure" open={technical}><summary>Open the original Ascon learning lab</summary><AsconLab/></details></section>
          <details className="project-evidence" open={technical} aria-label="Technical evidence and reproducibility"><summary>Technical evidence and reproducibility</summary><p>Friendly labels describe the same data. Original phase identifiers, metric meanings and exported evidence are unchanged. All recorded results come from the existing read-only, hash-verifying APIs.</p><div className="project-proof-types"><div><strong>Measured RTL simulation</strong><small>Historical Verilator fault outcomes and completion cycles; not physical trials.</small></div><div><strong>Browser calculations</strong><small>Interactive mathematical illustrations. No live RTL experiment is launched.</small></div><div><strong>Formal and synthesis work</strong><small>Selected properties and implementation models; not universal fault security or measured silicon area.</small></div><div><strong>Not claimed</strong><small>Physical fault injection, board execution, production cryptography or forged-message acceptance.</small></div></div><div className="project-provenance-grid"><div><p><strong>Phase 4B — single fault, clean replay</strong></p><p>Campaign SHA-256: <code>{summary.provenance.campaign_sha256}</code></p><p>Source revision: <code>{summary.provenance.git_commit}</code></p><p>Ascon-C reference revision: <code>{summary.provenance.reference_commit}</code></p><p>Yosys: {summary.provenance.yosys}<br/>sv2v: {summary.provenance.sv2v}</p></div><div>{research&&<><p><strong>Phase 7A — adversarial permutation</strong></p><p>SHA-256: <code>{research.campaigns.permutation.sha256}</code></p><p>{research.campaigns.permutation.scope}. Model: {research.campaigns.permutation.fault_model}.</p><p><strong>Phase 7B — adversarial bounded AEAD</strong></p><p>SHA-256: <code>{research.campaigns.aead.sha256}</code></p><p>{research.campaigns.aead.scope}. Model: {research.campaigns.aead.fault_model}.</p></>}</div></div><p>Phase 4B signal mapping: applied injection / fault_applied_o; detection / fault_detected_o; output allowed / result_valid_o. “Valid” is permission to release, not receiver authentication.</p><p>Observed alarm-and-valid policy violations in Phase 4B: {summary.metrics.fail_closed_violations}. This is an observation for the recorded cases, not a proof for all reachable states.</p>{research&&<div className="table-scroll"><table aria-label="Exact aggregate research metrics"><thead><tr><th>Metric / original field</th><th>Phase 7A</th><th>Phase 7B</th></tr></thead><tbody>{([['Configured cases','cases'],['Raw mismatches','raw_mismatches'],['Alarms','alarms'],['Valid releases','valid_releases'],['Incorrect releases','incorrect_releases'],['First-pass fault events','first_fault_events'],['Replay fault events','replay_fault_events'],['Checkpoint fault events','checkpoint_fault_events']] as const).map(([label,key])=><tr key={key}><td>{label} <code>{key}</code></td><td>{research.campaigns.permutation.metrics[key]}</td><td>{research.campaigns.aead.metrics[key]}</td></tr>)}</tbody></table></div>}{research&&<ul>{research.limitations.map(text=><li key={text}>{text}</li>)}</ul>}<p><a href="https://github.com/pm2m1/faultscope-ascon/tree/main/reports/phase5" target="_blank" rel="noreferrer">Phase 5 synthesis reports and manifest</a> · <a href="https://github.com/pm2m1/faultscope-ascon/blob/main/docs/ascon_reference_commit.txt" target="_blank" rel="noreferrer">Pinned Ascon-C reference</a> · <a href="https://github.com/pm2m1/faultscope-ascon/blob/main/docs/phase10e_fpga_feasibility_and_timing.md" target="_blank" rel="noreferrer">FPGA feasibility scope</a></p><p>Source documentation: <a href="https://github.com/pm2m1/faultscope-ascon/blob/main/docs/phase4b_temporal_recomputation.md" target="_blank" rel="noreferrer">Phase 4B clean replay</a>; <a href="https://github.com/pm2m1/faultscope-ascon/blob/main/docs/phase7a_adversarial_temporal.md" target="_blank" rel="noreferrer">Phase 7A permutation scenarios</a>; <a href="https://github.com/pm2m1/faultscope-ascon/blob/main/docs/phase7b_bounded_aead_adversarial.md" target="_blank" rel="noreferrer">Phase 7B bounded AEAD scenarios</a>.</p><p>The RTL generates bounded ciphertext and tags; it does not implement synthesizable authenticated decryption. Phase 25 receiver-authentication research is separate and unaccepted. Browser authenticated decryption is not evidence of an RTL receiver or a successful fault-induced forgery.</p></details>

          <div className="footnote"><AlertTriangle size={18}/><div><strong>What this project can — and cannot — demonstrate</strong><p>{technical?`${summary.scope.disclaimer} Model: ${summary.scope.fault_model}. The RTL supports ${summary.scope.hardware}, with 0–${summary.scope.plaintext_ad_max_bytes} bytes each of plaintext and associated data.`:"The findings describe recorded RTL simulations and implementation models. Interactive browser calculations explain the idea; neither page proves physical hardware operation or guaranteed security."}</p></div></div>
          <footer className="project-technical-inline">Reference: {summary.provenance.reference_commit.slice(0,12)} · Analysis revision: {summary.provenance.git_commit.slice(0,12)} · Yosys: {summary.provenance.yosys.slice(0,35)}</footer>
        </>}
      </section>
    </main>
  </div>;
}
