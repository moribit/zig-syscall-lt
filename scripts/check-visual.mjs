import { chromium } from 'playwright-chromium';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import assert from 'node:assert/strict';
const root = resolve('dist');
const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' };
const server = createServer(async (req, res) => {
  const path = new URL(req.url, 'http://localhost').pathname;
  try { const file = resolve(root, '.' + path); assert(file.startsWith(root + '/')); const body = await readFile(file); res.setHeader('Content-Type', mime[extname(file)] ?? 'application/octet-stream'); res.end(body); }
  catch { res.setHeader('Content-Type', 'text/html'); res.end(await readFile(resolve(root, 'index.html'))); }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1100, height: 619 } });
const out = process.env.VISUAL_OUTPUT || '/tmp/zig-lt-visual';
await mkdir(out, { recursive: true });
const source = await readFile('slides.md', 'utf8');
const slideCount = (source.match(/^---\s*$/gm) || []).length - 1;
assert.equal(slideCount, 15);
assert(!source.includes('```'), 'Live deck must not contain code blocks');
const report = { checkedAt: new Date().toISOString(), slides: [], animation: {}, presenter: false };
try {
  for (let i = 1; i <= slideCount; i++) {
    await page.goto(`${base}/${i}?clicks=99`);
    await page.locator('.slidev-layout:visible').first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(200);
    const state = await page.evaluate(() => {
      const layouts = [...document.querySelectorAll('.slidev-layout')];
      const el = layouts.find(el => { const r=el.getBoundingClientRect(); return r.width>0 && r.left>=-1 && r.left<100; }) || layouts[0];
      const bounds = el.getBoundingClientRect();
      const take = el.querySelector('.takeaway')?.getBoundingClientRect();
      const overflow = [...el.querySelectorAll('h1, h3, pre, p, td, .reason-list > div, .limits')].filter(x => {
        const r=x.getBoundingClientRect();
        return r.right > bounds.right+2 || r.bottom > bounds.bottom+2 || (x.tagName==='PRE' && x.scrollWidth>x.clientWidth+2) || (take && !x.classList.contains('fine') && r.top<take.top && r.bottom>take.top+2);
      }).map(x=>x.textContent.slice(0,80));
      return { title: el.querySelector('h1')?.textContent, overflow };
    });
    report.slides.push({ number: i, ...state });
    await page.screenshot({ path: `${out}/slide-${String(i).padStart(2,'0')}.png` });
  }
  await page.goto(`${base}/7?clicks=99`); await page.waitForTimeout(200);
  report.semanticColors = {};
  for (const [concept,color] of [['fd','rgb(29, 78, 216)'], ['buffer','rgb(15, 118, 110)'], ['result','rgb(126, 34, 206)'], ['operation','rgb(180, 83, 9)']]) {
    const actual = await page.locator(`.slidev-layout:visible .ref-${concept}`).first().evaluate(el => getComputedStyle(el).color);
    assert.equal(actual,color); report.semanticColors[concept]=actual;
  }
  await page.goto(`${base}/10?clicks=0`); await page.waitForTimeout(300);
  const before = await page.locator('.slidev-vclick-hidden').count();
  for (let i=0;i<4;i++) await page.keyboard.press('ArrowRight');
  await page.waitForTimeout(300);
  const after = await page.locator('.slidev-vclick-hidden').count();
  report.animation = { before, after, url: page.url() };
  assert(before>after && new URL(page.url()).pathname==='/10', 'Four click steps must reveal SQ/CQ on slide 10');
  await page.goto(`${base}/presenter/11`); await page.waitForTimeout(500);
  report.presenter = (await page.locator('body').innerText()).includes('目安180秒');
  assert(report.presenter, 'Presenter notes must be available');
  await writeFile('docs/validation-visual.json', JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
  assert(report.slides.every(s=>s.overflow.length===0), 'Review overflow in validation-visual.json');
} finally { await browser.close(); await new Promise(r=>server.close(r)); }
