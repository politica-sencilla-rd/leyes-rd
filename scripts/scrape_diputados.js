// Lane A scraper: per-deputy committees, initiatives and plenary attendance
// for the 2024-2028 legislature, from the official SIL Ciudadano API of the
// Cámara de Diputados (www.diputadosrd.gob.do/sil/api/legislador/...).
//
// Data contract (verified live 2026-06-10 by driving the Angular SPA and
// reading its own network calls + render code):
//   - legisladores?page=&keyword=&periodoId=0  -> search; gives legisladorId,
//       nombreCompleto, provincia, funcion ("Diputado"), partido.siglas
//   - comisiones?page=&legisladorId=&periodoId=0 -> committees the deputy sits
//       on (field "comision" = name, "tipo" = Permanente/Coordinadora/etc, "cargo")
//   - Iniciativas?page=&legisladorId=&keyword=&periodoId=0 -> bills the deputy
//       authored/co-authored; "numero" ends in -CD (Cámara) / -CS (Senado).
//       We count ONLY -CD numbers so the credit is the deputy's own chamber.
//   - asistencias?page=&legisladorId=&keyword=&periodoId=0 -> per-session
//       attendance; field "tipoCiudadano" is the value the SPA shows citizens
//       ("Presente", "Presente Incorporado", "Excusa", "Ausente ..."). The
//       sibling "tipo" field is stale garbage ("Ausente sin excusa" on every
//       row) and is NOT rendered — we ignore it.
//
// periodoId=0 means "current period" on this API and consistently returns
// 2024-2028 data (verified: representacion.periodo === "2024-2028").
//
// Output: scripts/diputados_stats.json keyed by SIL nombreCompleto, plus an
// _unmatched list for any provincias.json deputy we could not resolve.

const path = require("path");
const fs = require("fs");
const CORE = path.join(
  process.env.HOME,
  ".nvm/versions/node/v24.11.1/lib/node_modules/@playwright/cli/node_modules/playwright-core"
);
const { chromium } = require(CORE);

const BASE = "https://www.diputadosrd.gob.do/sil/api/legislador/";
const ROSTER = JSON.parse(fs.readFileSync("/tmp/dips_roster.json", "utf8"));
const OUT = path.join(__dirname, "diputados_stats.json");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Normalize for fuzzy name comparison: strip accents, lowercase, collapse space.
function norm(s) {
  return (s || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
function tokens(s) { return new Set(norm(s).split(" ").filter((w) => w.length > 1)); }
function overlap(a, b) {
  const ta = tokens(a), tb = tokens(b);
  let hit = 0;
  for (const t of ta) if (tb.has(t)) hit++;
  return hit / Math.max(1, Math.min(ta.size, tb.size));
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  // Establish origin/referer so the API serves JSON, not the SPA shell.
  await page.goto("https://www.diputadosrd.gob.do/sil/legislador", { waitUntil: "load" });
  await sleep(2500);

  const get = async (url) => {
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const r = await page.request.get(url, { timeout: 30000 });
        const t = await r.text();
        if (t.trim().startsWith("<")) throw new Error("got HTML shell");
        return JSON.parse(t);
      } catch (e) {
        if (attempt === 2) throw e;
        await sleep(1500);
      }
    }
  };

  const pageAll = async (build) => {
    const out = [];
    for (let p = 1; p <= 60; p++) {
      const j = await get(build(p));
      const res = j.results || [];
      out.push(...res);
      if (out.length >= (j.total || 0) || res.length === 0) break;
    }
    return out;
  };

  const result = {};
  const unmatched = [];
  let i = 0;
  for (const dip of ROSTER) {
    i++;
    // Search by the last two surname-ish tokens to keep keyword tight but unique.
    const kw = dip.nombre.trim();
    let cands = [];
    try {
      const j = await get(BASE + "legisladores?page=1&keyword=" + encodeURIComponent(kw) + "&periodoId=0");
      cands = (j.results || []).filter((c) => (c.funcion || "").toLowerCase().startsWith("diputad"));
    } catch (e) {
      // fall through to retry with a shorter keyword below
    }
    if (cands.length === 0) {
      // Retry with just the surnames (last 2 words) — handles double first names.
      const parts = kw.split(/\s+/);
      const kw2 = parts.slice(-2).join(" ");
      try {
        const j = await get(BASE + "legisladores?page=1&keyword=" + encodeURIComponent(kw2) + "&periodoId=0");
        cands = (j.results || []).filter((c) => (c.funcion || "").toLowerCase().startsWith("diputad"));
      } catch (e) {}
    }
    if (cands.length === 0) {
      unmatched.push({ ...dip, reason: "no search hit" });
      console.error(`[${i}/178] UNMATCHED (no hit): ${dip.nombre}`);
      continue;
    }
    // Pick best by name overlap, breaking ties by matching province.
    cands.sort((a, b) => {
      const oa = overlap(dip.nombre, a.nombreCompleto), ob = overlap(dip.nombre, b.nombreCompleto);
      if (Math.abs(oa - ob) > 0.001) return ob - oa;
      const pa = norm(a.provincia) === norm(dip.provincia) ? 1 : 0;
      const pb = norm(b.provincia) === norm(dip.provincia) ? 1 : 0;
      return pb - pa;
    });
    const best = cands[0];
    const score = overlap(dip.nombre, best.nombreCompleto);
    if (score < 0.5) {
      unmatched.push({ ...dip, reason: `weak match (${score.toFixed(2)}) to ${best.nombreCompleto}` });
      console.error(`[${i}/178] UNMATCHED (weak ${score.toFixed(2)}): ${dip.nombre} ~ ${best.nombreCompleto}`);
      continue;
    }
    const id = best.legisladorId;

    // Committees.
    const comRows = await pageAll((p) => BASE + "comisiones?page=" + p + "&legisladorId=" + id + "&periodoId=0");
    const comisiones = [...new Set(comRows
      .map((c) => (c.comision || "").trim())
      .filter((c) => c.length))]
      .sort();

    // Initiatives — count only Cámara-origin (-CD) bills, this period.
    const iniRows = await pageAll((p) => BASE + "Iniciativas?page=" + p + "&legisladorId=" + id + "&keyword=&periodoId=0");
    const cdInis = iniRows.filter((x) => /-CD$/i.test((x.numero || "").trim()));

    // Attendance — tipoCiudadano is the citizen-facing status.
    const asisRows = await pageAll((p) => BASE + "asistencias?page=" + p + "&legisladorId=" + id + "&keyword=&periodoId=0");
    let presentes = 0, total = 0;
    const breakdown = {};
    for (const a of asisRows) {
      const t = (a.tipoCiudadano || "").trim();
      breakdown[t] = (breakdown[t] || 0) + 1;
      total++;
      if (/^presente/i.test(t)) presentes++;
    }

    result[dip.nombre] = {
      provincia: dip.provincia,
      legisladorId: id,
      sil_nombre: best.nombreCompleto.replace(/\s+/g, " ").trim(),
      sil_provincia: best.provincia,
      match_score: +score.toFixed(2),
      comisiones,
      iniciativas_cd: cdInis.length,
      iniciativas_total_sil: iniRows.length,
      asistencia: { presentes, total, breakdown },
    };
    console.error(`[${i}/178] ${dip.nombre} id=${id} | com=${comisiones.length} iniCD=${cdInis.length} asist=${presentes}/${total}`);
    await sleep(120);
  }

  fs.writeFileSync(OUT, JSON.stringify({ _generated: new Date().toISOString(), _unmatched: unmatched, diputados: result }, null, 1));
  console.error(`\nDONE. matched=${Object.keys(result).length} unmatched=${unmatched.length} -> ${OUT}`);
  await browser.close();
}
main().catch((e) => { console.error("FATAL", e); process.exit(1); });
