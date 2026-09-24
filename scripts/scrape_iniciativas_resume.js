// Resume scraper: re-fetch only the fichas that errored in the first pass
// (the browser crashed partway through). Reads scripts/iniciativas_missing.json,
// re-reads each Ficha's proponente, and writes scripts/iniciativas_resume.json.
const path = require("path");
const fs = require("fs");
const CORE = path.join(
  process.env.HOME,
  ".nvm/versions/node/v24.11.1/lib/node_modules/@playwright/cli/node_modules/playwright-core"
);
const { chromium } = require(CORE);
const ENTRY =
  "http://www.senado.gov.do/wfilemaster/consultante.aspx?bd=C2024-2028&url=lista_expedientes.aspx?coleccion=53";
const OUT = path.join(__dirname, "iniciativas_resume.json");
const MISSING = path.join(__dirname, "iniciativas_missing.json");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const ids = JSON.parse(fs.readFileSync(MISSING, "utf8"));
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);
  // establish session
  await page.goto(ENTRY, { waitUntil: "load" });
  await sleep(4500);

  const records = [];
  let n = 0;
  for (const id of ids) {
    const url = `http://www.senado.gov.do/wfilemaster/Ficha.aspx?IdExpediente=${id}&numeropagina=1&ContExpedientes=1&Coleccion=53`;
    try {
      await page.goto(url, { waitUntil: "load" });
      await sleep(900);
      const rec = await page.evaluate(() => {
        const prop = document.getElementsByName("campos_nota_644")[0];
        const num = document.getElementsByName("campos_text_628")[0];
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
      console.error(`resume ${n}/${ids.length}`);
      fs.writeFileSync(OUT, JSON.stringify({ count: records.length, records }, null, 1));
    }
  }
  fs.writeFileSync(OUT, JSON.stringify({ count: records.length, records }, null, 1));
  console.error("RESUME DONE", records.length);
  await browser.close();
}

main().catch((e) => { console.error("FATAL", e); process.exit(1); });
