// Local-first WCAG audit of the built frontend. No CDN/network assets.
// Start the backend, then: npm run axe
// Optional: PORTLY_AXE_URL=http://127.0.0.1:5533 PORTLY_AXE_COOKIE="session=..." npm run axe
import { chromium } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const baseUrl = process.env.PORTLY_AXE_URL || 'http://127.0.0.1:5533';
const cookieHeader = process.env.PORTLY_AXE_COOKIE || '';
const themes = ['dark', 'light'];

const targets = [
  { name: 'landing', open: async () => {} },
  { name: 'ports', open: async (p) => p.getByRole('button', { name: 'Ports', exact: true }).first().click() },
  { name: 'table', open: async (p) => p.getByRole('button', { name: 'Table', exact: true }).first().click() },
  { name: 'grid', open: async (p) => p.getByRole('button', { name: 'Grid', exact: true }).first().click() },
  { name: 'list', open: async (p) => p.getByRole('button', { name: 'List', exact: true }).first().click() },
  // exact: 'Board' otherwise substring-matches the "Portly Dashboard" brand
  // button, which opens a drawer whose backdrop blocks every later target.
  { name: 'board', open: async (p) => p.getByRole('button', { name: 'Board', exact: true }).first().click() },
  { name: 'add-app modal', open: async (p) => p.getByRole('button', { name: 'Add app' }).first().click() },
];

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  if (cookieHeader) {
    const cookies = cookieHeader.split(';').map((part) => {
      const [name, ...rest] = part.trim().split('=');
      return { name, value: rest.join('='), url: baseUrl };
    });
    await context.addCookies(cookies);
  }

  const page = await context.newPage();
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(1500);

  let totalSerious = 0;
  for (const target of targets) {
    try {
      await target.open(page);
      await page.waitForTimeout(400);
    } catch {
      console.log(`- skip ${target.name}: not present on this screen`);
      continue;
    }

    for (const theme of themes) {
      await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
      // Sidebar/toolbar color transitions run 150ms; measuring sooner reads
      // mid-transition colors and reports phantom contrast violations.
      await page.waitForTimeout(400);
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
      console.log(`${target.name} [${theme}]: ${bad.length} serious/critical violation(s)`);
      for (const v of bad) {
        console.log(`  ${v.impact.toUpperCase()} ${v.id}: ${v.help} (${v.nodes.length} node(s))`);
        for (const node of v.nodes.slice(0, 3)) {
          console.log(`    - ${node.target.join(' ')} :: ${(node.failureSummary || '').split('\n')[0]}`);
        }
        totalSerious += v.nodes.length;
      }
    }
  }

  if (totalSerious > 0) {
    console.error(`\n${totalSerious} serious/critical node(s) found.`);
    process.exitCode = 1;
  } else {
    console.log('\nNo serious/critical axe violations detected.');
  }
} finally {
  await browser.close();
}
