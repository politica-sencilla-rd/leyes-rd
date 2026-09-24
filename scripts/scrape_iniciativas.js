// Lane 3 scraper: count Senate initiatives proposed/co-proposed per senator
// for the 2024-2028 legislature, from the official SIL (senado.gov.do).
// Strategy: walk the unfiltered expediente list (20/page), collect every
// Ficha IdExpediente, then open each Ficha and read the "Proponentes" field
// (campos_nota_644). Count a senator when their name appears in that field.
// Honest count = authored OR co-authored. Output: scripts/iniciativas_raw.json
const path = require("path");
const fs = require("fs");
const CORE = path.join(
  process.env.HOME,
  ".nvm/versions/node/v24.11.1/lib/node_modules/@playwright/cli/node_modules/playwright-core"
);
const { chromium } = require(CORE);

const ENTRY = "http://www.senado.gov.do/wfilemaster/consultante.aspx?bd=C2024-2028&url=lista_expedientes.aspx?coleccion=53";
const OUT = path.join(__dirname, "iniciativas_raw.json");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);

  // ---- Phase 1: collect all ficha IDs by paging ----
  // Start at the entry URL so the SIL establishes the 2024-2028 session.
  await page.goto(ENTRY, { waitUntil: "load" });
  await sleep(4500);
  const total = await page.evaluate(() => {
    const t = document.body.innerText.replace(/\s+/g, " ");
    const m = t.match(/Expedientes:\s*\d+\s*-\s*\d+\s*de\s*(\d+)/i);
    return m ? +m[1] : null;
  });
  console.error("TOTAL expedientes:", total);

  const ids = new Set();
  let page1 = 0;
  let lastFirst = null;
  const maxPages = Math.ceil((total || 2500) / 20) + 5;
  for (let p = 0; p < maxPages; p++) {
    const pageIds = await page.evaluate(() =>
      [...new Set([...document.querySelectorAll("a")]
        .map((a) => a.href)
        .map((h) => { const m = h.match(/IdExpediente=(\d+)/); return m ? +m[1] : null; })
        .filter(Boolean))]
    );
    if (!pageIds.length) break;
    const firstId = pageIds[0];
    if (firstId === lastFirst) { console.error("no advance, stop at page", p); break; }
    lastFirst = firstId;
    pageIds.forEach((i) => ids.add(i));
    if (p % 10 === 0) console.error(`page ${p}: ${ids.size} ids so far`);
    if (ids.size >= (total || 0)) break;
    // advance: click the pagination "next" image (btSumaPaginacion)
    const advanced = await page.evaluate(() => {
      const b = document.getElementsByName("btSumaPaginacion")[0] || document.getElementsByName("btSumaPaginacion1")[0];
      if (b) { b.click(); return true; }
      return false;
    });
    if (!advanced) { console.error("no next button, stop"); break; }
    await sleep(2200);
  }
  console.error("collected ids:", ids.size);
  const idList = [...ids];

  // ---- Phase 2: read proponente per ficha ----
  const records = [];
  let n = 0;
  for (const id of idList) {
    const url = `http://www.senado.gov.do/wfilemaster/Ficha.aspx?IdExpediente=${id}&numeropagina=1&ContExpedientes=1&Coleccion=53`;
    try {
      await page.goto(url, { waitUntil: "load" });
      await sleep(900);
      const rec = await page.evaluate(() => {
        const prop = document.getElementsByName("campos_nota_644")[0];
        const num = document.getElementsByName("campos_text_628")[0];
        const tipo = document.getElementsByName("campos_auto_626")[0];
        return {
          proponente: prop ? prop.value.trim() : "",
          numero: num ? num.value.trim() : "",
        };
      });
      records.push({ id, ...rec });
    } catch (e) {
      records.push({ id, proponente: "", numero: "", error: String(e).slice(0, 80) });
    }
    n++;
    if (n % 50 === 0) {
      console.error(`ficha ${n}/${idList.length}`);
      fs.writeFileSync(OUT, JSON.stringify({ total, count: records.length, records }, null, 1));
    }
  }
  fs.writeFileSync(OUT, JSON.stringify({ total, count: records.length, records }, null, 1));
  console.error("DONE. wrote", records.length, "records to", OUT);
  await browser.close();
}

main().catch((e) => { console.error("FATAL", e); process.exit(1); });
