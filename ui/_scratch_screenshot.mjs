import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const routes = [
  { path: '/', name: 'overview' },
  { path: '/graph', name: 'graph' },
  { path: '/guarantees', name: 'guarantees' },
  { path: '/scenarios', name: 'scenarios' },
];

const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (msg) => { if (msg.type() === 'error') errors.push(msg.text()); });

for (const route of routes) {
  await page.goto(`http://localhost:5173${route.path}`, { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(800);
  await page.screenshot({ path: `/tmp/shot-${route.name}.png` });
  console.log('captured', route.path);
}

console.log('console/page errors:', JSON.stringify(errors));
await browser.close();
