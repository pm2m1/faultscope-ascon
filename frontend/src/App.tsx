import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Activity, AlertTriangle, ArrowUpRight, Cpu, Database, Fingerprint, Gauge, Layers3, RefreshCw, ShieldCheck, Zap, FlaskConical, GitCompareArrows } from 'lucide-react';

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
const scenarioLabel = (name: string) => name.replaceAll('_', ' ');
const researchOutcomes = [
  ['all', 'All outcomes'], ['alarm', 'Alarm raised'],
  ['incorrect_release', 'Incorrect release'], ['raw_mismatch', 'Raw mismatch'],
  ['valid_correct', 'Valid and correct'], ['no_alarm', 'No alarm'],
];


const fmt = (n: number) => n.toLocaleString('en-US');
const pct = (n: number | null) => n === null ? 'N/A' : `${n.toFixed(1)}%`;
const phaseText = (n: number) => (({ 0: 'Initialization', 1: 'AD absorption', 2: 'AD padding', 3: 'Message', 4: 'Finalization' } as Record<number, string>)[n] ?? `Phase ${n}`);

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) {
    let why = r.statusText;
    try { const body = await r.json(); why = body.detail ?? why; } catch { /* no JSON body */ }
    throw new Error(`${r.status}: ${why}`);
  }
  return await r.json() as T;
}

function MetricCard({ label, value, detail, icon }: { label: string; value: string; detail: string; icon: ReactNode }) {
  return <div className="metric card">
    <div className="metric-label"><span>{label}</span>{icon}</div>
    <div className="metric-value">{value}</div>
    <div className="metric-detail">{detail}</div>
  </div>;
}

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [page, setPage] = useState<Page | null>(null);
  const [status, setStatus] = useState('all');
  const [phase, setPhase] = useState('all');
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshCounter, setRefreshCounter] = useState(0);
  const [activeSection, setActiveSection] = useState<'overview' | 'comparison' | 'ledger' | 'research'>('overview');
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
  const jumpTo = (id: 'overview' | 'comparison' | 'ledger' | 'research') => {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Fingerprint size={24}/></div><div><strong>FAULTSCOPE</strong><small>ASCON RESEARCH LAB</small></div></div>
      <div className="side-label">WORKSPACE</div>
      <button type="button" className={`nav-link ${activeSection === 'overview' ? 'active' : ''}`} aria-current={activeSection === 'overview' ? 'location' : undefined} onClick={() => jumpTo('overview')}><Activity size={17}/> Evidence overview</button>
      <button type="button" disabled={!summary} className={`nav-link ${activeSection === 'comparison' ? 'active' : ''}`} aria-current={activeSection === 'comparison' ? 'location' : undefined} onClick={() => jumpTo('comparison')}><Layers3 size={17}/> Phase comparison</button>
      <button type="button" disabled={!summary} className={`nav-link ${activeSection === 'ledger' ? 'active' : ''}`} aria-current={activeSection === 'ledger' ? 'location' : undefined} onClick={() => jumpTo('ledger')}><Database size={17}/> Experiment ledger</button>
      <button type="button" disabled={!summary} className={`nav-link ${activeSection === 'research' ? 'active' : ''}`} aria-current={activeSection === 'research' ? 'location' : undefined} onClick={() => jumpTo('research')}><FlaskConical size={17}/> Adversarial research</button>
      <div className="sidebar-spacer"/>
      <div className="sidebar-note"><ShieldCheck size={18}/><div><strong>Evidence-driven</strong><p>Displays local, hash-verified Phase 4B, 7A, 7B and Phase 5 reports. No fabricated experiment results.</p></div></div>
      <div className="sidebar-footer">NIST SP 800-232<br/>Local research environment</div>
    </aside>

    <main>
      <header className="topbar">
        <div className="breadcrumbs">Cryptographic hardware <span>/</span> <strong>{activeSection === 'overview' ? 'Experiment overview' : activeSection === 'comparison' ? 'Phase comparison' : activeSection === 'ledger' ? 'Experiment ledger' : 'Adversarial research'}</strong></div>
        <div className="top-actions"><div className="status-chip"><span className={'dot ' + (summary ? 'ok' : 'off')}/>{summary ? 'Reports loaded' : 'Awaiting evidence'}</div>
        <button className="refresh" onClick={() => setRefreshCounter(x => x + 1)}><RefreshCw size={15}/> Refresh</button></div>
      </header>
      <section className="content">
        <div className="hero-kicker">PRE-SILICON FAULT INJECTION & DEFENSE</div>
        <div className="hero-head" id="overview"><div><h1>Ascon hardware security</h1><p>Fault occurrence, protection coverage and synthesis overhead — grounded in recorded RTL experiments.</p></div><span className="scope-pill">SINGLE-FAULT · CLEAN REPLAY</span></div>

        {loading && <div className="notice">Loading local verification reports…</div>}
        {error && <div className="notice error"><AlertTriangle size={18}/> <span>{error}<br/><small>Generate Phase 4B and Phase 5 evidence, then press Refresh.</small></span></div>}
        {summary && <>
          <div className="metrics-grid">
            <MetricCard label="CAMPAIGN SCENARIOS" value={fmt(summary.metrics.cases)} detail="Deterministic HDL experiments" icon={<Activity size={19}/>}/>
            <MetricCard label="FAULT COVERAGE" value={pct(summary.metrics.coverage_percent)} detail={`${summary.metrics.detected_faults} of ${summary.metrics.applied_faults} applied faults detected`} icon={<ShieldCheck size={19}/>}/>
            <MetricCard label="FALSE ALARMS" value={fmt(summary.metrics.false_alarms)} detail={`Among ${summary.metrics.unfaulted_cases} non-injection cases`} icon={<Zap size={19}/>}/>
            <MetricCard label="MEAN CYCLE OVERHEAD" value={`+${summary.metrics.relative_mean_latency_increase_percent.toFixed(2)}%`} detail="Protected versus baseline" icon={<Gauge size={19}/>}/>
          </div>

          <div className="panels">
            <section className="card panel">
              <div className="panel-head"><div><div className="panel-kicker">IMPLEMENTATION COST</div><h2>Generic synthesis cells</h2></div><Cpu size={20}/></div>
              <p className="panel-explain">Technology-independent resource proxy from identical Yosys synthesis settings.</p>
              <div className="bars">
                {summary.resources.map(d => <div className="barrow" key={d.design}>
                  <div className="barlabel"><span>{d.design}</span><strong>{fmt(d.generic_cells)}</strong></div>
                  <div className="track"><div className={'fill ' + d.design} style={{ width: `${100 * d.generic_cells / resourceMax}%` }}/></div>
                  <div className="subbar">{fmt(d.ff_bits)} FF output bits · {fmt(d.combinational_cells)} combinational cells</div>
                </div>)}
              </div>
              <div className="panel-foot">Counts are not ASIC area, FPGA LUT utilization or timing.</div>
            </section>
            <section className="card panel">
              <div className="panel-head"><div><div className="panel-kicker">RUNTIME TRADE-OFF</div><h2>Mean execution cycles</h2></div><Gauge size={20}/></div>
              <p className="panel-explain">Average simulation cycle counts for the same experiment set.</p>
              <div className="cycle-grid">
                <div><div className="cycle-number">{summary.metrics.mean_baseline_cycles.toFixed(2)}</div><div className="cycle-label">Baseline</div></div>
                <ArrowUpRight size={22}/>
                <div><div className="cycle-number protected-number">{summary.metrics.mean_protected_cycles.toFixed(2)}</div><div className="cycle-label">Protected</div></div>
              </div>
              <div className="comparison"><div className="comparison-line"><div className="comparison-fill" style={{width: `${100 * summary.metrics.mean_baseline_cycles / Math.max(summary.metrics.mean_protected_cycles, 1)}%`}}/></div><small>Baseline share of protected runtime</small></div>
              <div className="panel-foot">Mean cycle overhead does not imply lower clock frequency.</div>
            </section>
          </div>

          <section className="card panel phases" id="comparison">
            <div className="panel-head"><div><div className="panel-kicker">FAULT LOCALIZATION</div><h2>Results by Ascon phase</h2></div><Layers3 size={20}/></div>
            <div className="phase-grid">
              {summary.phases.map(p => <div className="phase-card" key={p.phase}>
                <div className="phase-id">PHASE {p.phase}</div>
                <div className="phase-name">{p.name}</div>
                <div className="phase-value">{p.detected}<small> / {p.applied} detected</small></div>
                <div className="phase-track"><div style={{width: `${100 * p.detected / Math.max(p.applied, 1)}%`}}/></div>
                <div className="phase-foot">{p.cases} configured scenarios</div>
              </div>)}
            </div>
          </section>

          <section className="card panel ledger" id="ledger">
            <div className="panel-head"><div><div className="panel-kicker">AUDITABLE EXPERIMENTS</div><h2>Fault campaign ledger</h2></div><Database size={20}/></div>
            <div className="filters"><select aria-label="Filter by phase" value={phase} onChange={e => {setPhase(e.target.value);setOffset(0);}}>
              <option value="all">All phases</option>{Array.from(new Set(summary.phases.map(p=>p.phase))).map(p=><option value={p} key={p}>{phaseText(p)}</option>)}
            </select><select aria-label="Filter by outcome" value={status} onChange={e => {setStatus(e.target.value);setOffset(0);}}>
              <option value="all">All outcomes</option><option value="detected_fault">Detected fault</option><option value="undetected_fault">Undetected fault</option><option value="no_injection">No injection</option><option value="false_alarm">False alarm</option>
            </select><span>{page ? `${fmt(page.total)} matching rows` : 'Loading…'}</span></div>
            <div className="table-scroll"><table><thead><tr><th>CASE</th><th>PHASE</th><th>ROUND</th><th>BIT</th><th>AD/MESSAGE</th><th>OUTCOME</th><th>BASELINE</th><th>PROTECTED</th></tr></thead>
              <tbody>{page?.rows.map(r=><tr key={r.case}><td>#{r.case}</td><td>{phaseText(r.phase)}</td><td>{r.round}</td><td>{r.bit}</td><td>{r.ad_len} / {r.msg_len} B</td><td><span className={`outcome ${r.outcome}`}>{r.outcome.replaceAll('_',' ')}</span></td><td>{r.baseline_cycles} cyc</td><td>{r.protected_cycles} cyc</td></tr>)}</tbody></table>
              {page?.rows.length === 0 && <div className="empty">No cases match this filter.</div>}
            </div>
            <div className="pagination"><button disabled={offset===0} onClick={()=>setOffset(x=>Math.max(0,x-15))}>Previous</button><span>{page?.total ? `${offset+1}–${Math.min(offset+15,page.total)} of ${page.total}` : '0 results'}</span><button disabled={!page || offset+15>=page.total} onClick={()=>setOffset(x=>x+15)}>Next</button></div>
          </section>

          <section className="card panel research" id="research">
            <div className="panel-head"><div><div className="panel-kicker">COMPARATIVE SECURITY EVALUATION</div><h2>Adversarial research</h2></div><GitCompareArrows size={20}/></div>
            <p className="panel-explain">Three distinct simulation models. Counts describe deliberately configured cases, not physical attack probabilities or a shared detection rate.</p>
            {researchError && <div className="notice error"><AlertTriangle size={18}/><span>Advanced evidence unavailable: {researchError}<small>Original Phase 4B dashboard remains available; research figures are not substituted.</small></span></div>}
            {!research && !researchError && <div className="notice">Loading hash-verified Phase 7 evidence…</div>}
            {research && <>
              <div className="research-overview">
                <div className="research-tile">
                  <div className="panel-kicker">PHASE 4B · SINGLE FAULT</div>
                  <h3>{fmt(summary.metrics.cases)} scenarios</h3>
                  <strong>{summary.metrics.detected_faults} / {summary.metrics.applied_faults} applied faults detected</strong>
                  <p>Clean replay, bounded AEAD encryption. Zero observed alarm-and-valid policy violations.</p>
                </div>
                {(['permutation', 'aead'] as const).map(kind => {
                  const c = research.campaigns[kind];
                  return <div className="research-tile" key={kind}>
                    <div className="panel-kicker">{c.label} · {kind === 'permutation' ? 'PERMUTATION' : 'BOUNDED AEAD'}</div>
                    <h3>{fmt(c.metrics.cases)} scenarios</h3>
                    <strong>{c.metrics.incorrect_releases} incorrect releases</strong>
                    <p>{c.metrics.alarms} alarms · {c.metrics.raw_mismatches} raw mismatches. {c.scope}.</p>
                  </div>;
                })}
              </div>
              <div className="research-divider"/>
              <div className="research-subhead">
                <div><div className="panel-kicker">SCENARIO ANALYSIS</div><h3>Fault outcomes by scenario</h3><p>Select a campaign to examine the distinct fault mechanisms.</p></div>
                <div className="research-switch" role="group" aria-label="Select advanced experiment">
                  <button type="button" aria-pressed={researchKind === 'permutation'} className={researchKind === 'permutation' ? 'selected' : ''} onClick={() => {setResearchKind('permutation');resetResearchFilters();}}>Phase 7A</button>
                  <button type="button" aria-pressed={researchKind === 'aead'} className={researchKind === 'aead' ? 'selected' : ''} onClick={() => {setResearchKind('aead');resetResearchFilters();}}>Phase 7B</button>
                </div>
              </div>
              <p className="panel-explain research-scope">{research.campaigns[researchKind].output_label}. {research.campaigns[researchKind].scope}.</p>
              <div className="scenario-table-scroll"><table className="scenario-table">
                <thead><tr><th>FAULT SCENARIO</th><th>CASES</th><th>RAW MISMATCH</th><th>ALARMS</th><th>INCORRECT RELEASES</th></tr></thead>
                <tbody>{research.campaigns[researchKind].scenarios.map(x => <tr key={x.scenario}>
                  <td><button className="scenario-link" onClick={() => {setResearchScenario(x.scenario ?? 'all');setResearchOffset(0);document.getElementById('research-explorer')?.scrollIntoView({behavior: 'smooth',block: 'start'});}}>{scenarioLabel(x.scenario ?? '')}</button></td>
                  <td>{x.cases}</td><td>{x.raw_mismatches}</td><td>{x.alarms}</td>
                  <td><div className="scenario-result"><strong className={x.incorrect_releases ? 'research-critical' : ''}>{x.incorrect_releases}</strong><span className="scenario-track"><span style={{width: `${x.cases ? (100*x.incorrect_releases/x.cases) : 0}%`}}/></span></div></td>
                </tr>)}</tbody>
              </table></div>
              <div className="research-divider"/>
              {researchKind === 'aead' && <div className="research-phase-breakdown">
                <div className="panel-kicker">BOUNDED AEAD · PER-PHASE OUTCOMES</div>
                <div className="research-phase-grid">{research.campaigns.aead.phases.map(p => <div className="research-phase-tile" key={p.phase}>
                  <div className="phase-id">PHASE {p.phase}</div><strong>{phaseText(p.phase ?? -1)}</strong>
                  <small>{p.alarms} alarms · {p.incorrect_releases} incorrect releases / {p.cases} configured cases</small>
                </div>)}</div>
              </div>}
              <div className="research-subhead" id="research-explorer">
                <div><div className="panel-kicker">HASH-VERIFIED RECORDED CASES</div><h3>Adversarial experiment explorer</h3></div>
                <span className="evidence-tag">SHA-256 pinned · local CSV</span>
              </div>
              <div className="filters research-filters">
                <select aria-label="Adversarial scenario" value={researchScenario} onChange={e => {setResearchScenario(e.target.value);setResearchOffset(0);}}>
                  <option value="all">All fault scenarios</option>{research.campaigns[researchKind].scenarios.map(x => <option key={x.scenario} value={x.scenario}>{scenarioLabel(x.scenario ?? '')}</option>)}
                </select>
                <select aria-label="Adversarial outcome" value={researchOutcome} onChange={e => {setResearchOutcome(e.target.value);setResearchOffset(0);}}>{researchOutcomes.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select>
                <select aria-label="Adversarial phase or permutation rounds" value={researchPhase} onChange={e => {setResearchPhase(e.target.value);setResearchOffset(0);}}>
                  <option value="all">{researchKind === 'aead' ? 'All AEAD phases' : 'Both permutations'}</option>
                  {researchKind === 'aead' ? [0,1,2,3,4].map(p => <option value={p} key={p}>{phaseText(p)}</option>) : [8,12].map(r => <option value={r} key={r}>p[{r}]</option>)}
                </select>
                <span>{researchPage ? `${fmt(researchPage.total)} matching rows` : 'Loading…'}</span>
              </div>
              <div className="table-scroll"><table className="research-cases-table"><thead><tr>
                <th>CASE</th><th>SCENARIO</th><th>{researchKind === 'aead' ? 'PHASE' : 'PERMUTATION'}</th>
                <th>FIRST / REPLAY / CP</th><th>RAW DIFF</th><th>ALARM</th><th>VALID</th><th>INCORRECT</th><th>CYCLES</th>
              </tr></thead><tbody>{researchPage?.rows.map(r => <tr key={r.case}>
                <td>#{r.case}</td><td>{scenarioLabel(r.scenario)}</td><td>{researchKind === 'aead' ? phaseText(r.phase ?? -1) : `p[${r.rounds}]`}</td>
                <td>{r.first_fired} / {r.replay_fired} / {r.checkpoint_fired}</td><td>{r.raw_mismatch}</td>
                <td><span className={`research-flag ${r.alarm ? 'warn' : 'neutral'}`}>{r.alarm ? 'Alarm' : 'None'}</span></td>
                <td>{r.valid ? 'Yes' : 'No'}</td><td><span className={`research-flag ${r.incorrect_release ? 'warn' : 'neutral'}`}>{r.incorrect_release ? 'Incorrect' : 'No'}</span></td>
                <td>{r.cycles}</td>
              </tr>)}</tbody></table>{researchPage?.rows.length === 0 && <div className="empty">No recorded cases match these filters.</div>}</div>
              <div className="pagination"><button disabled={researchOffset === 0} onClick={()=>setResearchOffset(x=>Math.max(0,x-researchLimit))}>Previous</button><span>{researchPage?.total ? `${researchOffset+1}–${Math.min(researchOffset+researchLimit,researchPage.total)} of ${researchPage.total}` : '0 results'}</span><button disabled={!researchPage || researchOffset+researchLimit>=researchPage.total} onClick={()=>setResearchOffset(x=>x+researchLimit)}>Next</button></div>
              <details className="provenance-detail"><summary>Verified evidence fingerprints</summary><p>Phase 7A SHA-256: <code>{research.campaigns.permutation.sha256}</code></p><p>Phase 7B SHA-256: <code>{research.campaigns.aead.sha256}</code></p><p>Hashes identify specific committed CSV snapshots, not the security of a deployed implementation.</p></details>
              <div className="research-limitations"><strong>Interpretation boundaries</strong><ul>{research.limitations.map(text => <li key={text}>{text}</li>)}</ul></div>
            </>}
          </section>

          <div className="footnote"><AlertTriangle size={18}/><div><strong>Interpretation boundary</strong><p>{summary.scope.disclaimer} Model: {summary.scope.fault_model}. The RTL currently supports {summary.scope.hardware}, with 0–{summary.scope.plaintext_ad_max_bytes} bytes of plaintext and associated data.</p></div></div>
          <footer>Reference: {summary.provenance.reference_commit.slice(0,12)} · Analysis revision: {summary.provenance.git_commit.slice(0,12)} · Yosys: {summary.provenance.yosys.slice(0,35)}</footer>
        </>}
      </section>
    </main>
  </div>;
}
