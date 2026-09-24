// Runs the real docs/app.js against a fake DOM with every string in every data
// file poisoned with an HTML payload, then prints (as JSON) every innerHTML write
// that carries the payload unescaped, every href that is not http(s), and any
// error the page hit. Used by tests/test_app_escape.py.
//
//   node tests/js/render_hostil.js <repo-root> <modo>
//   modo: "todo"    = poison every string (dates, enums and states too)
//         "textos"  = keep the structural fields intact so every render path runs
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = process.argv[2];
const MODO = process.argv[3] || "todo";
const CARGA = "<i data-x=1>";
const JS_URL = "javascript:alert(1)";
// Fields that pick a render path. In "textos" mode they stay real so each path runs.
const ESTRUCTURA = new Set(["estado", "fecha", "tipo", "id", "numero", "acta", "iniciativa", "periodo_iso",
  "vigencia_fecha", "promulgada", "publicada", "cargo", "emoji", "voto", "vote", "datos_al", "revisado_el",
  "datos_al_manual", "fuente_sha256", "modelo_escritor", "modelo_revisor", "sil_id"]);

const html = [];
const hrefs = [];
const errores = [];

function envenenar(o, clave) {
  if (typeof o === "string") {
    if (/^https?:\/\//.test(o) || clave === "url" || /^url/.test(clave || "") || /url$/.test(clave || "")) return JS_URL;
    if (MODO === "textos" && ESTRUCTURA.has(clave)) return o;
    return o + CARGA;
  }
  if (Array.isArray(o)) return o.map((x) => envenenar(x, clave));
  if (o && typeof o === "object") {
    const out = {};
    for (const [k, v] of Object.entries(o)) out[k] = envenenar(v, k);
    return out;
  }
  return o;
}

function leer(rel) {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "docs", rel), "utf8"));
}

function datos(rel) {
  const d = leer(rel);
  if (rel === "data/resumenes.json") {
    // One verified summary per kind, for real items, so the AI-text paths render too.
    const ses = leer("data/sesiones.json");
    const vig = leer("data/vigencia.json");
    const autoLey = { id: "01234-2026" };  // the auto bill added below
    const ini = ses.sesiones[0].votaciones[0].iniciativa;  // its hand title is dropped below
    const num = "5-26";
    const r = (tipo, extra) => Object.assign({ tipo, estado: "verificado", fuente_url: "https://www.senadord.gob.do/x",
      fuente_nombre: "Fuente", fuente_sha256: "0".repeat(64), modelo_escritor: "a", modelo_revisor: "b",
      checks_pasados: 5, checks_total: 5, fecha: "2026-09-24" }, extra);
    d.resumenes["sil-" + autoLey.id] = r("proyecto", { titulo_facil: "T", que_es: "Q", por_que: "P", te_afecta: "A" });
    d.resumenes["senado-" + ini] = r("titulo_voto", { titulo_facil: "T" });
    d.resumenes["ley-" + num] = r("ley", { que_es: "Q" });
    d.sin_resumen["sil-x"] = { intentos: 3, fuente_url: "https://www.senadord.gob.do/x" };
  }
  if (rel === "data/leyes.json") {
    // Make sure an auto bill exists so its path renders.
    d.sectores[0].leyes.push({ id: "01234-2026", titulo: "Proyecto", titulo_oficial: "PROYECTO", estado: "votando",
      estado_sil: "En comisión", camara: true, auto: true, url_oficial: "https://www.diputadosrd.gob.do/sil",
      datos_al: "2026-09-24" });
  }
  if (rel === "data/sesiones.json") {
    for (const s of d.sesiones) { s.auto = true; }
    d.sesiones[0].votaciones[0].fuente = "Acta 0106, votación electrónica 003";
    delete d.sesiones[0].votaciones[0].titulo_facil;
    d.sesiones.push({ acta: "0999", fecha: "2026-01-01", estado: "no_procesada", url_acta: "https://www.senadord.gob.do/a",
      auto: true, motivo: "votaciones sin leer: 001" });
  }
  if (rel === "data/vigencia.json") {
    // A robot-added law (no hand-written que_es), as vigencia.py writes it.
    d.leyes.push({ numero: "5-26", titulo: "Ley nueva", titulo_oficial: "LEY NUEVA", promulgada: "2026-02-01",
      publicada: "2026-02-03", gaceta: "11230", estado: "vigencia", vigencia_fecha: "2026-02-04",
      vigencia_texto: "Rige desde el día siguiente a su publicación.", vigencia_cita: "Artículo 9. Entra en vigencia.",
      fuente: "Ley 5-26, art. 9 — Consultoría Jurídica del Poder Ejecutivo (consultoria.gov.do)",
      url_documento: "https://www.consultoria.gov.do/x.pdf", auto: true, datos_al: "2026-09-24" });
  }
  return envenenar(d, "");
}

// ---------------------------------------------------------------- fake DOM
function cualquiera() {
  const f = function () { return cualquiera(); };
  return new Proxy(f, {
    get(t, p) {
      if (p === Symbol.toPrimitive) return () => "";
      if (p === "then") return undefined;
      if (p === "length") return 0;
      return cualquiera();
    },
    set() { return true; },
    apply() { return cualquiera(); },
  });
}

const manejadores = [];
function nodo(tag) {
  const t = {
    tagName: String(tag || "div").toUpperCase(), children: [], dataset: {}, style: { setProperty() {} },
    classList: { add() {}, remove() {}, toggle() { return true; }, contains() { return false; } },
    append(...xs) { for (const x of xs) t.children.push(x); },
    prepend(...xs) { for (const x of xs) t.children.unshift(x); },
    appendChild(x) { t.children.push(x); return x; },
    insertBefore(x) { t.children.push(x); return x; },
    replaceWith() {}, remove() {}, focus() {}, scrollIntoView() {}, click() {},
    setAttribute(k, v) { if (k === "href") hrefs.push(String(v)); },
    getAttribute() { return null; }, removeAttribute() {}, hasAttribute() { return false; },
    addEventListener(tipo, fn) { manejadores.push([tipo, fn]); },
    querySelector() { return null; }, querySelectorAll() { return []; }, closest() { return null; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; },
    offsetHeight: 0, offsetWidth: 0, scrollTop: 0, open: false, value: "", disabled: false,
  };
  return new Proxy(t, {
    get(o, p) {
      if (p in o) return o[p];
      if (p === "innerHTML" || p === "textContent" || p === "outerHTML") return "";
      if (typeof p === "symbol") return undefined;
      return cualquiera();
    },
    set(o, p, v) {
      if (p === "innerHTML" || p === "outerHTML") html.push(String(v));
      else if (p === "href") hrefs.push(String(v));
      else o[p] = v;
      return true;
    },
  });
}

const documento = nodo("document");
Object.assign(documento, {
  createElement: (t) => nodo(t),
  createTextNode: (s) => ({ texto: s }),
  getElementById: (id) => nodo("div"),
  querySelector: () => nodo("div"),
  querySelectorAll: () => [],
  addEventListener() {},
  body: nodo("body"),
  documentElement: nodo("html"),
});

const ventana = {
  matchMedia: () => ({ matches: true, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, scrollTo() {}, scrollY: 0, innerWidth: 400, innerHeight: 800,
  location: { hash: "", href: "https://x/", pathname: "/", search: "" },
  history: { replaceState() {}, pushState() {} },
  localStorage: { getItem() { return null; }, setItem() {} },
  sessionStorage: { getItem() { return null; }, setItem() {} },
  navigator: { share: undefined, clipboard: undefined, userAgent: "node" },
  requestAnimationFrame: (f) => 0,
};

const ctx = {
  document: documento, window: ventana, console: {
    log() {}, warn() {},
    error: (...a) => errores.push(a.map((x) => (x && x.stack) || String(x)).join(" ")),
  },
  fetch: async (url) => {
    const rel = String(url).split("?")[0];
    try {
      const d = datos(rel);
      return { ok: true, json: async () => d };
    } catch (e) {
      return { ok: false, json: async () => ({}) };
    }
  },
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0,
  location: ventana.location, history: ventana.history, navigator: ventana.navigator,
  localStorage: ventana.localStorage, sessionStorage: ventana.sessionStorage,
  HTMLElement: function () {}, HTMLDetailsElement: function () {}, HTMLAnchorElement: function () {},
  HTMLButtonElement: function () {}, HTMLInputElement: function () {}, HTMLSelectElement: function () {},
  Element: function () {}, Node: function () {}, Event: function () {}, KeyboardEvent: function () {},
  IntersectionObserver: function () { return { observe() {}, disconnect() {} }; },
  MutationObserver: function () { return { observe() {}, disconnect() {} }; },
  URL, URLSearchParams, Intl, Promise, JSON, Math, Date, Array, Object, String, Number, Set, Map, RegExp, Error,
};
ctx.globalThis = ctx;
ctx.self = ctx;
vm.createContext(ctx);

(async () => {
  const codigo = fs.readFileSync(path.join(ROOT, "docs", "app.js"), "utf8");
  try {
    vm.runInContext(codigo, ctx, { filename: "app.js" });
  } catch (e) {
    errores.push("carga: " + (e && e.stack));
  }
  for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r));
  // Open every province profile and every fold: fire each click handler once.
  const evento = { preventDefault() {}, stopPropagation() {}, key: "Enter", target: nodo("div"), currentTarget: nodo("div") };
  const vistos = new Set();
  for (let ronda = 0; ronda < 3; ronda++) {
    for (const [tipo, fn] of manejadores.slice()) {
      if (tipo !== "click" || vistos.has(fn)) continue;
      vistos.add(fn);
      try { fn(evento); } catch (e) { /* a handler that needs a real DOM is not what we test */ }
    }
    for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r));
  }
  const crudos = html.filter((h) => h.includes(CARGA));
  const malos = hrefs.filter((h) => /^\s*javascript:/i.test(h));
  process.stdout.write(JSON.stringify({ escrituras: html.length, crudos, hrefs_js: malos, errores, html }));
})();
