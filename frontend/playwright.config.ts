import { defineConfig } from '@playwright/test';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');
// Keep every run separate from archived screenshots and prior validation evidence.
const artifacts=path.resolve(process.env.FAULTSCOPE_UI_OUTPUT || path.join(root,'build/reproduction/website_ui',`${new Date().toISOString().replace(/[:.]/g,'-')}-${process.pid}`));
process.env.FAULTSCOPE_UI_OUTPUT=artifacts;
const python=process.env.FAULTSCOPE_TEST_PYTHON || (process.platform==='win32'?'python':'python3');
export default defineConfig({
  testDir:'./e2e',fullyParallel:false,workers:1,timeout:45000,
  expect:{timeout:8000},
  outputDir:path.join(artifacts,'browser-artifacts'),
  reporter:[['line'],['json',{outputFile:path.join(artifacts,'browser-results.json')}]],
  use:{baseURL:'http://127.0.0.1:5173',browserName:'chromium',channel:process.env.FAULTSCOPE_BROWSER_CHANNEL||(process.platform==='win32'?'msedge':undefined),headless:true,viewport:{width:1920,height:1080},reducedMotion:'reduce',screenshot:'only-on-failure'},
  webServer:[
    {command:`"${python}" -m uvicorn backend.api:app --host 127.0.0.1 --port 8000`,cwd:root,url:'http://127.0.0.1:8000/api/health',reuseExistingServer:!process.env.CI,timeout:30000},
    {command:'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173',url:'http://127.0.0.1:5173',reuseExistingServer:!process.env.CI,timeout:30000},
  ],
});
