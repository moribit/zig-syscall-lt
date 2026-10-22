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
const slideCount = (source.match(/^# /gm) || []).length;
assert.equal(slideCount, 20);
assert.equal([...source.matchAll(/```zig/g)].length, 4);
const report = { checkedAt: new Date().toISOString(), slides: [], animation: {}, presenter: false };
try {
  for (let i = 1; i <= slideCount; i++) {
    await page.goto(`${base}/${i}?clicks=99`);
    await page.locator('.slidev-layout:visible').first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    if (i===2) assert((await page.locator('.deck-footer:visible').innerText()).replace(/\s/g,'').endsWith('2/20'), 'Slidev must render exactly 20 pages');
    await page.waitForTimeout(200);
    const state = await page.evaluate(() => {
      const layouts = [...document.querySelectorAll('.slidev-layout')];
      const el = layouts.find(el => { const r=el.getBoundingClientRect(); return r.width>0 && r.left>=-1 && r.left<100; }) || layouts[0];
      const bounds = el.getBoundingClientRect();
      const take = el.querySelector('.takeaway')?.getBoundingClientRect();
      const overflow = [...el.querySelectorAll('h1, h3, pre, p, td, .io-lane, .io-completed, .code-key, .review-data, .live-terminal, .many-fds, .reason-list > div, .limits')].filter(x => {
        const r=x.getBoundingClientRect();
        return r.right > bounds.right+2 || r.bottom > bounds.bottom+2 || (x.tagName==='PRE' && x.scrollWidth>x.clientWidth+2) || (take && !x.classList.contains('fine') && r.top<take.top && r.bottom>take.top+2);
      }).map(x=>x.textContent.slice(0,80));
      return { title: el.querySelector('h1')?.textContent, overflow, background: getComputedStyle(el).backgroundColor, code: [...el.querySelectorAll('pre')].map(p=>({fontSize:parseFloat(getComputedStyle(p).fontSize), lines:p.innerText.trim().split('\n').length, overflow:p.scrollWidth>p.clientWidth+2})) };
    });
    report.slides.push({ number: i, ...state });
    await page.screenshot({ path: `${out}/slide-${String(i).padStart(2,'0')}.png` });
  }
  await page.goto(`${base}/9?clicks=99`); await page.waitForTimeout(200);
  report.semanticColors = {};
  for (const [concept,color] of [['fd','rgb(139, 185, 255)'], ['buffer','rgb(126, 224, 204)'], ['result','rgb(216, 180, 254)'], ['operation','rgb(255, 192, 120)']]) {
    const actual = await page.locator(`.slidev-layout:visible .ref-${concept}`).first().evaluate(el => getComputedStyle(el).color);
    assert.equal(actual,color); report.semanticColors[concept]=actual;
  }
  await page.goto(`${base}/14?clicks=0`); await page.waitForTimeout(300);
  const before = await page.locator('.slidev-vclick-hidden').count();
  const steps=[];
  for (let i=0;i<4;i++) {
    await page.keyboard.press('ArrowRight');await page.waitForTimeout(100);
    const state=await page.locator('.slidev-layout:visible .io-flow').evaluate(el=>({rows:[...el.querySelectorAll('.io-lane')].map(r=>r.classList.contains('slidev-vclick-hidden')),buffer:el.querySelector('.ref-buffer').classList.contains('slidev-vclick-hidden')}));
    assert.deepEqual(state.rows,[false,i<1,i<2]);assert.equal(state.buffer,i<3);steps.push({click:i+1,...state});
  }
  await page.waitForTimeout(300);
  const after = await page.locator('.slidev-vclick-hidden').count();
  report.animation = { before, after, steps, url: page.url() };
  assert(before>after && new URL(page.url()).pathname==='/14', 'Four click steps must reveal SQ/CQ on slide 14');
  await page.goto(`${base}/presenter/15`); await page.waitForTimeout(500);
  report.presenter = (await page.locator('body').innerText()).includes('目安180秒');
  assert(report.presenter, 'Presenter notes must be available');
  report.diagramGeometry=[];
  for (const number of [8,11,14]) {
    await page.goto(`${base}/${number}?clicks=99`);await page.waitForTimeout(200);
    const row=await page.locator('.slidev-layout:visible .io-lane').first().evaluate(el=>{const [left,,right]=el.children;return {left:left.getBoundingClientRect().left,right:right.getBoundingClientRect().left,width:left.getBoundingClientRect().width,font:getComputedStyle(left).fontSize};});
    report.diagramGeometry.push({number,...row});assert.equal(row.font,'20px');
  }
  assert(report.diagramGeometry.every(g=>Math.abs(g.left-report.diagramGeometry[0].left)<1&&Math.abs(g.right-report.diagramGeometry[0].right)<1&&Math.abs(g.width-report.diagramGeometry[0].width)<1));
  await page.goto(`${base}/2`); await page.waitForTimeout(200);
  report.introOpacity=await page.locator('.slidev-layout:visible .big-statement').evaluate(el=>getComputedStyle(el).opacity);
  assert.equal(report.introOpacity,'1');
  report.sections=[];
  for (const [number,name] of [[7,'poll'],[10,'epoll'],[13,'io_uring']]) {
    await page.goto(`${base}/${number}`); await page.waitForTimeout(200);
    const state=await page.locator('.api-section:visible').evaluate(el=>{
      const h=el.querySelector('h1'), r=h.getBoundingClientRect(), b=el.getBoundingClientRect();
      return {text:el.innerText.trim(),font:getComputedStyle(h).fontFamily,size:getComputedStyle(h).fontSize,background:getComputedStyle(el).backgroundColor,dx:(r.left+r.right-b.left-b.right)/2,dy:(r.top+r.bottom-b.top-b.bottom)/2,footer:!!document.querySelector('.deck-footer')};
    });
    assert.equal(state.text,name);assert(Math.abs(state.dx)<2&&Math.abs(state.dy)<2);assert(!state.footer);
    assert.equal(state.size,'112px');report.sections.push({number,...state});
  }
  assert(report.sections.every(s=>s.background===report.sections[0].background && s.font===report.sections[0].font));
  await page.goto(`${base}/4?clicks=99`); await page.waitForTimeout(200);
  report.codeColors=await page.locator('.slidev-layout:visible pre').first().evaluate(el=>({background:getComputedStyle(el).backgroundColor,tokens:[...el.querySelectorAll('span')].filter(x=>!x.children.length).map(x=>({text:x.textContent,color:getComputedStyle(x).color}))}));
  for (const [token,color] of [['1','rgb(139, 185, 255)'],['6','rgb(216, 180, 254)'],['write','rgb(255, 192, 120)']]) assert(report.codeColors.tokens.some(t=>t.text===token&&t.color===color));
  assert.equal(report.codeColors.background,'rgb(21, 30, 49)');
  assert(report.slides.flatMap(s=>s.code).every(c=>c.fontSize>=18&&c.lines<=3&&!c.overflow));
  await writeFile('docs/validation-visual.json', JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
  assert(report.slides.every(s=>s.overflow.length===0), 'Review overflow in validation-visual.json');
} finally { await browser.close(); await new Promise(r=>server.close(r)); }
