import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const output=path.join(process.env.FAULTSCOPE_UI_OUTPUT || path.resolve(import.meta.dirname,'../../build/reproduction/website_ui'),'screenshots');

test('friendly findings match the verified API exactly, with correct interpretation',async({page})=>{
  const base=await (await page.request.get('/api/summary')).json();
  const research=await (await page.request.get('/api/research/summary')).json();
  await page.goto('/');await expect(page.getByText('Reports loaded',{exact:true})).toBeVisible();
  const cards=page.getByLabel('Recorded clean-replay findings').locator('.metric');
  await expect(cards.nth(0)).toContainText(base.metrics.cases.toLocaleString('en-US'));
  await expect(cards.nth(1)).toContainText(`${base.metrics.detected_faults} / ${base.metrics.applied_faults}`);
  await expect(cards.nth(1)).toContainText('repeat calculation was deliberately clean');
  await expect(cards.nth(2)).toContainText(`${base.metrics.unfaulted_cases} cases without injection`);
  await expect(cards.nth(3)).toContainText(`+${base.metrics.relative_mean_latency_increase_percent.toFixed(2)}%`);
  for(const resource of base.resources)await expect(page.locator('.bars')).toContainText(resource.generic_cells.toLocaleString('en-US'));
  await expect(page.locator('.cycle-grid')).toContainText(base.metrics.mean_baseline_cycles.toFixed(2));
  await expect(page.locator('.cycle-grid')).toContainText(base.metrics.mean_protected_cycles.toFixed(2));
  const tiles=page.locator('.research-tile');await expect(tiles).toHaveCount(3);
  await expect(tiles.nth(0)).toContainText(`${base.metrics.cases} tests`);
  await expect(tiles.nth(1)).toContainText(`${research.campaigns.permutation.metrics.cases} tests`);
  await expect(tiles.nth(1)).toContainText(`${research.campaigns.permutation.metrics.incorrect_releases} incorrect permutation states`);
  await expect(tiles.nth(2)).toContainText(`${research.campaigns.aead.metrics.cases} tests`);
  await expect(tiles.nth(2)).toContainText(`${research.campaigns.aead.metrics.incorrect_releases} incorrect ciphertext/tag results`);
  await expect(page.getByTestId('project-takeaway')).toContainText('not a universal security proof');
  await expect(page.getByTestId('project-takeaway')).toContainText('not real-world attack probabilities');
  await expect(tiles.nth(2)).toContainText('not whether a receiver accepts them');
});

test('simple and technical views share data and preserve provenance and filters',async({page})=>{
  const base=await (await page.request.get('/api/summary')).json();
  const research=await (await page.request.get('/api/research/summary')).json();
  await page.goto('/');await expect(page.getByText('Reports loaded',{exact:true})).toBeVisible();
  const disclosure=page.locator('details.project-evidence');
  await expect(disclosure).not.toHaveAttribute('open','');
  await expect(page.locator('.project-technical-column').first()).not.toBeVisible();
  await page.getByLabel('Filter by phase').selectOption('2');
  await page.getByRole('button',{name:'Technical View',exact:true}).click();
  await expect(disclosure).toHaveAttribute('open','');
  await expect(disclosure).toContainText(base.provenance.campaign_sha256);
  await expect(disclosure).toContainText(research.campaigns.permutation.sha256);
  await expect(disclosure).toContainText(research.campaigns.aead.sha256);
  await expect(disclosure).toContainText('fault_detected_o');
  await expect(disclosure).toContainText('Phase 25 receiver-authentication research is separate and unaccepted');
  await expect(page.getByRole('table',{name:'Exact aggregate research metrics'})).toBeVisible();
  await expect(page.getByLabel('Filter by phase')).toHaveValue('2');
  await page.getByRole('button',{name:'Simple View',exact:true}).click();
  await expect(page.getByLabel('Filter by phase')).toHaveValue('2');
  await expect(disclosure).not.toHaveAttribute('open','');
  await disclosure.locator('summary').click();await expect(disclosure).toContainText(base.provenance.campaign_sha256);
});

test('protection stepper uses genuine permutation states for all three modes',async({page})=>{
  await page.clock.install();await page.goto('/');
  const demo=page.getByRole('region',{name:'How does repeating a calculation help?'});
  await expect(demo).toContainText('not live Verilator execution');
  await demo.getByRole('button',{name:'Run the check',exact:true}).click();await page.clock.fastForward(1100);
  await expect(demo.getByRole('button',{name:'Protection step 2: First calculation'})).toHaveAttribute('aria-current','step');
  await demo.getByRole('button',{name:'Pause check',exact:true}).click();await page.clock.fastForward(5000);
  await expect(demo.getByRole('button',{name:'Protection step 2: First calculation'})).toHaveAttribute('aria-current','step');
  for(const [name,expected] of [['No fault','correct output allowed'],['One faulty calculation','output blocked'],['The same fault twice','incorrect result is allowed']]){
    await demo.getByRole('button',{name,exact:true}).click();await demo.getByRole('button',{name:'Protection step 5: Release or block'}).click();await expect(demo.getByRole('status')).toContainText(expected);
  }
  await demo.getByText('Advanced view: the real calculated states',{exact:true}).click();
  const calculated=await page.evaluate(async()=>{
    const {compareReplay,sequence,hex64}=await import('/src/asconTrace.ts');
    const r=compareReplay(sequence,12,'dual_identical',0,0);return {golden:r.golden.map(hex64),first:r.first.map(hex64),replay:r.replay.map(hex64)};
  });
  for(const value of calculated.golden)await expect(demo.locator('.project-state-table')).toContainText(value);
  for(const value of calculated.first)await expect(demo.locator('.project-state-table')).toContainText(value);
  await demo.getByRole('button',{name:'Reset',exact:true}).click();await expect(demo.getByRole('button',{name:'Protection step 1: Receive input'})).toHaveAttribute('aria-current','step');
});

test('ledger and adversarial controls still filter and paginate real recorded cases',async({page})=>{
  await page.goto('/');const ledger=page.locator('#ledger');await expect(ledger.locator('tbody tr')).toHaveCount(15);
  const first=await ledger.locator('tbody tr').first().locator('td').first().textContent();await ledger.getByRole('button',{name:'Next',exact:true}).click();await expect(ledger.locator('tbody tr').first().locator('td').first()).not.toHaveText(first!);
  await ledger.getByRole('button',{name:'Previous',exact:true}).click();await expect(ledger.locator('tbody tr').first().locator('td').first()).toHaveText(first!);
  await page.getByLabel('Filter by outcome').selectOption('no_injection');await expect(ledger.locator('tbody tr').first()).toContainText('No fault applied');
  const harder=page.locator('#research');await harder.getByRole('button',{name:'Permutation tests',exact:true}).click();
  await page.getByLabel('Adversarial scenario',{exact:true}).selectOption('dual_identical');
  await page.getByLabel('Adversarial outcome',{exact:true}).selectOption('incorrect_release');
  const source=await (await page.request.get('/api/research/cases?kind=permutation&scenario=dual_identical&outcome=incorrect_release&offset=0&limit=12')).json();
  await expect(harder.locator('.research-cases-table tbody tr')).toHaveCount(source.rows.length);
  await expect(harder.locator('.research-filters')).toContainText(`${source.total} matching rows`);
  for(const row of await harder.locator('.research-cases-table tbody tr').all())await expect(row).toContainText('The same fault in both calculations');
  await harder.getByRole('button',{name:'Encrypted-output tests',exact:true}).click();await expect(page.getByLabel('Adversarial scenario',{exact:true})).toHaveValue('all');
});

test('walkthrough bridge is concise, contains no research hashes and reaches results',async({page})=>{
  await page.goto('/#/walkthrough');const walk=page.locator('.walkthrough');
  await expect(walk.getByRole('heading',{name:'So why did we build FaultScope?'})).toBeVisible();
  await expect(walk.getByText(/SHA-256/)).toHaveCount(0);
  await expect(walk.getByText('What did the project actually find?',{exact:true})).toHaveCount(0);
  await page.getByRole('link',{name:'Explore our hardware experiments and results'}).click();
  await expect(page).toHaveURL(/#\/results$/);await expect(page.locator('#research')).toBeInViewport();
});

test('professor-demo visual inspection: desktop/mobile, simple/technical and keyboard',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await fs.mkdir(output,{recursive:true});
  await page.setViewportSize({width:1920,height:1080});await page.goto('/');await expect(page.getByText('Reports loaded',{exact:true})).toBeVisible();await page.evaluate(()=>document.fonts.ready);
  const heading=page.getByRole('heading',{name:'Can hardware detect when encryption goes wrong?'});await expect(heading).toBeInViewport();
  await page.screenshot({path:path.join(output,'dashboard-1920-introduction.png')});
  await page.getByRole('region',{name:'An encryption circuit, and a way to question its answers'}).screenshot({path:path.join(output,'dashboard-architecture.png')});
  const demo=page.getByRole('region',{name:'How does repeating a calculation help?'});await demo.getByRole('button',{name:'One faulty calculation',exact:true}).click();await demo.getByRole('button',{name:'Protection step 5: Release or block'}).click();await demo.screenshot({path:path.join(output,'dashboard-protection.png')});
  await page.locator('#research').screenshot({path:path.join(output,'dashboard-results.png')});
  await page.getByRole('button',{name:'Technical View',exact:true}).click();await page.locator('details.project-evidence').screenshot({path:path.join(output,'dashboard-technical-evidence.png')});
  for(const width of [320,390,820,1920]){await page.setViewportSize({width,height:1080});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();}
  await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Simple View',exact:true}).click();await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(output,'dashboard-mobile.png')});
  await page.setViewportSize({width:1920,height:1080});await page.getByRole('navigation',{name:'Main pages'}).getByRole('link',{name:'Algorithm Walkthrough',exact:true}).focus();await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/walkthrough$/);await page.screenshot({path:path.join(output,'walkthrough-1920-introduction.png')});
  await page.getByRole('heading',{name:'So why did we build FaultScope?'}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'walkthrough-project-bridge.png')});
  expect(errors).toEqual([]);
});

// The selected release retains the original dark navy presentation on both routes.
test('both pages retain the selected dark visual identity',async({page})=>{
  for(const route of ['/#/','/#/walkthrough']){
    await page.goto(route);
    await expect(page.locator('html')).toHaveCSS('background-color','rgb(9, 15, 29)');
    await expect(page.getByRole('navigation',{name:'Main pages'})).toBeVisible();
  }
});
