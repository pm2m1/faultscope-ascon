import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const output=path.join(process.env.FAULTSCOPE_UI_OUTPUT || path.resolve(import.meta.dirname,'../../build/reproduction/website_ui'),'screenshots');
async function ready(page:Page){await page.goto('/#/walkthrough');await expect(page.getByRole('heading',{name:'A small message. A real computation.'})).toBeVisible();}
async function encrypt(page:Page){await page.getByRole('button',{name:'Encrypt My Message'}).click();await expect(page.getByTestId('walk-current-step')).toContainText('Prepare the inputs');}
async function goStep(page:Page,index:number){await page.getByRole('button',{name:new RegExp(`^Step ${index}:`)}).click();}
async function noOverflow(page:Page){expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();}

test('dashboard introduces the project and preserves the real research controls',async({page})=>{
  await fs.mkdir(output,{recursive:true});await page.goto('/');
  await expect(page.getByRole('heading',{name:'Can hardware detect when encryption goes wrong?'})).toBeVisible();
  await expect(page.getByText('Reports loaded',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Simple View',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByLabel('Filter by phase')).toBeVisible();
  await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(output,'research-dashboard-desktop.png'),fullPage:true});
});

test('two top-level routes, back/forward and dashboard filters are preserved',async({page})=>{
  await page.goto('/');await expect(page.getByRole('link',{name:'Research Dashboard',exact:true})).toHaveAttribute('aria-current','page');
  await page.getByLabel('Filter by phase').selectOption('2');
  await page.getByRole('navigation',{name:'Main pages'}).getByRole('link',{name:'Algorithm Walkthrough',exact:true}).click();
  await expect(page).toHaveURL(/#\/walkthrough$/);
  await expect(page.getByRole('heading',{name:'Can hardware detect when encryption goes wrong?'})).not.toBeVisible();
  await page.goBack();await expect(page.getByLabel('Filter by phase')).toHaveValue('2');
  await page.goForward();await expect(page.getByRole('heading',{name:'A small message. A real computation.'})).toBeVisible();
  await page.getByRole('link',{name:'Research Dashboard',exact:true}).click();
  await page.getByRole('button',{name:'Ascon learning lab',exact:true}).click();
  await expect(page.getByRole('region',{name:'Interactive Ascon learning lab'})).toBeVisible();
  await page.getByRole('button',{name:'AEAD workflow',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Initialize the keyed state'})).toBeVisible();
});

test('HELLO: real ciphertext, successful decryption, both tamper cases and real copy',async({page,context})=>{
  await context.grantPermissions(['clipboard-read','clipboard-write']);
  const requests:string[]=[];page.on('request',r=>{if(r.method()!=='GET')requests.push(r.url());});
  await ready(page);await page.getByLabel('Advanced Technical View').check();
  for(const [label,value]of [['Message / Plaintext','HELLO'],['Associated Data','Course: CNS'],['Secret key hexadecimal','000102030405060708090a0b0c0d0e0f'],['Nonce hexadecimal','101112131415161718191a1b1c1d1e1f']])await page.getByRole('textbox',{name:label,exact:true}).fill(value);
  await page.getByLabel('Advanced Technical View').uncheck();
  await expect(page.locator('#walk-message-bytes')).toContainText('48 45 4c 4c 4f');await encrypt(page);
  await goStep(page,8);
  const ciphertext=await page.getByTestId('output-ciphertext').textContent();
  const tag=await page.getByTestId('output-authentication-tag').textContent();
  expect(ciphertext).toBe('a0b29b6679');expect(tag).toBe('38a5911ee12bb09077fdc926a45cae30');
  await page.getByRole('button',{name:'Copy Ciphertext',exact:true}).click();
  expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(ciphertext);
  await page.getByRole('button',{name:'Verify & decrypt',exact:true}).click();
  await expect(page.getByTestId('receiver-verdict')).toContainText('Authentication successful — Original message recovered: HELLO');
  await page.getByRole('button',{name:'Tamper With Message',exact:true}).click();await expect(page.getByTestId('receiver-verdict')).toContainText('Authentication failed — Message rejected');await expect(page.getByTestId('receiver-verdict')).not.toContainText('HELLO');
  await page.getByRole('button',{name:'Reset received data',exact:true}).click();await expect(page.getByTestId('receiver-verdict')).toContainText('HELLO');
  await page.getByRole('button',{name:'Tamper With Tag',exact:true}).click();await expect(page.getByTestId('receiver-verdict')).toContainText('Authentication failed');
  expect(requests).toEqual([]);expect(await page.evaluate(()=>({local:Object.keys(localStorage),session:Object.keys(sessionStorage)}))).toEqual({local:[],session:[]});
  expect(page.url()).not.toContain('HELLO');
});

test('UTF-8 byte limits and advanced key/nonce validation',async({page})=>{
  await ready(page);await page.getByRole('textbox',{name:'Message / Plaintext',exact:true}).fill('😀😀😀😀a');
  await expect(page.getByRole('alert')).toContainText('17 UTF-8 bytes');await expect(page.getByRole('button',{name:'Encrypt My Message'})).toBeDisabled();
  await page.getByRole('textbox',{name:'Message / Plaintext',exact:true}).fill('😀😀😀😀');await expect(page.getByRole('button',{name:'Encrypt My Message'})).toBeEnabled();
  await page.getByLabel('Advanced Technical View').check();await page.getByRole('textbox',{name:'Secret key hexadecimal',exact:true}).fill('abc');
  await expect(page.getByRole('alert')).toContainText('exactly 16 bytes');await page.getByRole('textbox',{name:'Secret key hexadecimal',exact:true}).fill('00'.repeat(16));
  await page.getByRole('textbox',{name:'Nonce hexadecimal',exact:true}).fill('zz'.repeat(16));await expect(page.getByRole('alert')).toContainText('Nonce');
});

test('play, pause, previous, restart and input changes cannot mix snapshots',async({page})=>{
  await page.clock.install();await ready(page);await encrypt(page);
  await page.getByRole('button',{name:'Play',exact:true}).click();await page.clock.fastForward(1300);await expect(page.getByTestId('walk-current-step')).toContainText('Initialize Ascon');
  await page.getByRole('button',{name:'Pause',exact:true}).click();await page.clock.fastForward(5000);await expect(page.getByTestId('walk-current-step')).toContainText('Initialize Ascon');
  await page.getByRole('button',{name:'Previous',exact:true}).click();await expect(page.getByTestId('walk-current-step')).toContainText('Prepare the inputs');
  await goStep(page,6);await expect(page.getByTestId('walk-current-step')).toContainText('Make the ciphertext, one byte at a time');
  await page.getByRole('button',{name:'Restart',exact:true}).click();await expect(page.getByTestId('walk-current-step')).toContainText('Prepare the inputs');
  await page.getByRole('button',{name:'Play',exact:true}).click();await page.getByRole('textbox',{name:'Message / Plaintext',exact:true}).fill('BYE');await page.clock.fastForward(10000);
  await expect(page.getByRole('region',{name:'Encryption trace',exact:true})).toHaveCount(0);await expect(page.getByTestId('receiver-verdict')).toHaveCount(0);
  await encrypt(page);await goStep(page,8);await expect(page.getByTestId('output-original-plaintext')).toHaveText('BYE');
});

test('actual permutation rounds and every fault scenario are interactive',async({page})=>{
  await ready(page);await encrypt(page);await page.getByLabel('Advanced Technical View').check();await goStep(page,3);
  await page.getByText('Explore all 12 real rounds',{exact:true}).click();
  await page.getByRole('combobox',{name:'Round for Permutation p[12]',exact:true}).selectOption('11');
  await page.getByRole('combobox',{name:'Layer for Permutation p[12]',exact:true}).selectOption('2');
  await expect(page.locator('.walk-round-explorer')).toContainText('Round 12 of 12');await expect(page.locator('.walk-round-explorer')).toContainText('0x4b');
  const fault=page.getByRole('region',{name:'What happens if a hardware calculation goes wrong?'});
  const expected:{[key:string]:string}={clean:'Correct output',first_only:'Output blocked',replay_only:'Output blocked',dual_identical:'Incorrect result released',checkpoint_shared:'Incorrect result released',suppress_replay_alarm:'Incorrect result released'};
  for(const [scenario,verdict] of Object.entries(expected)){await page.getByLabel('Walkthrough fault scenario',{exact:true}).selectOption(scenario);await expect(fault.getByRole('status')).toContainText(verdict);}
});

test('zero and full blocks remain truthful and link back to the project story',async({page})=>{
  await ready(page);await page.getByRole('textbox',{name:'Message / Plaintext',exact:true}).fill('');await page.getByRole('textbox',{name:'Associated Data',exact:true}).fill('');await encrypt(page);
  await goStep(page,4);await expect(page.getByTestId('walk-current-step')).toContainText('Empty AD: skip');await expect(page.getByTestId('walk-current-step').getByText('Explore all 8 real rounds',{exact:true})).toHaveCount(0);
  await goStep(page,8);await expect(page.getByTestId('output-ciphertext')).toHaveText('(empty)');await expect(page.getByRole('button',{name:'Tamper With Message',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Verify & decrypt',exact:true}).click();await expect(page.getByTestId('receiver-verdict')).toContainText('(empty message)');
  await page.getByRole('textbox',{name:'Message / Plaintext',exact:true}).fill('0123456789abcdef');await page.getByRole('textbox',{name:'Associated Data',exact:true}).fill('0123456789abcdef');await encrypt(page);
  await goStep(page,4);await expect(page.getByTestId('walk-current-step').getByText('Explore all 8 real rounds',{exact:true})).toHaveCount(2);
  await goStep(page,6);await expect(page.getByTestId('walk-current-step')).toContainText('empty tail after a full block');await expect(page.getByTestId('walk-current-step').getByText('Explore all 8 real rounds',{exact:true})).toHaveCount(1);
  await expect(page.getByRole('heading',{name:'So why did we build FaultScope?'})).toBeVisible();
  await expect(page.locator('.walkthrough').getByText(/SHA-256/)).toHaveCount(0);
  await page.getByRole('link',{name:'Explore our hardware experiments and results'}).click();
  await expect(page).toHaveURL(/#\/results$/);
  await expect(page.locator('#research')).toBeInViewport();

});

test('offline evidence never fabricates findings and crypto still works',async({page})=>{
  await page.route('**/api/**',r=>r.fulfill({status:503,body:'{"detail":"unavailable"}',contentType:'application/json'}));await ready(page);await encrypt(page);
  await page.getByRole('button',{name:'Verify & decrypt',exact:true}).click();await expect(page.getByTestId('receiver-verdict')).toContainText('HELLO');await expect(page.getByRole('heading',{name:'So why did we build FaultScope?'})).toBeVisible();await page.getByRole('link',{name:'Explore our hardware experiments and results'}).click();await expect(page.locator('.notice.error').first()).toContainText('503');await expect(page.locator('.research-tile')).toHaveCount(0);
});

test('desktop, tablet and mobile layouts, reduced motion and screenshots',async({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await fs.mkdir(output,{recursive:true});
  await ready(page);await expect(page.locator('.walkthrough')).toHaveCSS('animation-name','none');await noOverflow(page);
  await page.screenshot({path:path.join(output,'walkthrough-desktop-input.png'),fullPage:true});await encrypt(page);await expect(page.getByTestId('walk-current-step')).toHaveCSS('animation-name','none');await goStep(page,6);await page.screenshot({path:path.join(output,'walkthrough-desktop-xor.png'),fullPage:true});
  await page.setViewportSize({width:820,height:1180});await noOverflow(page);
  await page.setViewportSize({width:390,height:844});await noOverflow(page);await page.screenshot({path:path.join(output,'walkthrough-mobile.png'),fullPage:true});
  await page.setViewportSize({width:1920,height:1080});await goStep(page,8);await page.getByRole('button',{name:'Verify & decrypt',exact:true}).click();await page.screenshot({path:path.join(output,'walkthrough-desktop-result.png'),fullPage:true});
  expect(errors).toEqual([]);
});


test('keyboard navigation can open the page, submit and jump through the trace',async({page})=>{
  await page.goto('/');await page.keyboard.press('Tab');await page.keyboard.press('Tab');await page.keyboard.press('Tab');await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/walkthrough$/);
  await page.getByRole('button',{name:'Encrypt My Message'}).focus();await page.keyboard.press('Enter');
  await expect(page.getByTestId('walk-current-step')).toContainText('Prepare the inputs');
  await page.getByRole('button',{name:/^Step 5:/}).focus();await page.keyboard.press('Space');
  await expect(page.getByTestId('walk-current-step')).toContainText('Toggle the domain bit');
});
