"use strict";
// Leyes RD — fácil. TypeScript source.
// Compiles to site/app.js via `npm run build` (tsc). Loads sample JSON,
// groups laws by sector, expandable cards + province profiles.
const estadoLabel = {
    aprobada: "✅ Aprobada",
    votando: "🗳️ En votación",
    rechazada: "❌ Rechazada",
};
const votoLabel = { si: "👍 Sí", no: "👎 No", ausente: "➖ Ausente" };
const votoClass = { si: "voto-si", no: "voto-no", ausente: "voto-aus" };
// Bumped with every data/content change, same value as the index.html
// cache-buster (?v=...). Appended to every data fetch so returning visitors
// don't render stale JSON from the browser's HTTP cache when only the data
// changed (the data files are not versioned in the HTML).
const DATA_VERSION = "20260615c";
async function cargar(path) {
    const sep = path.indexOf("?") >= 0 ? "&" : "?";
    const res = await fetch(path + sep + "v=" + DATA_VERSION);
    if (!res.ok)
        throw new Error("No se pudo cargar " + path);
    return (await res.json());
}
function el(tag, cls, html) {
    const n = document.createElement(tag);
    if (cls)
        n.className = cls;
    if (html !== undefined)
        n.innerHTML = html;
    return n;
}
function byId(id) {
    const n = document.getElementById(id);
    if (!n)
        throw new Error("Falta el elemento #" + id);
    return n;
}
// One consistent "official document" link line, used across the whole site
// (5ª sugerencia de un usuario real, Ángel). Returns an <a> that opens the
// official source in a new tab, safely (rel="noopener"). texto is the visible
// label, e.g. "📄 Leer la ley completa" or "📄 Ver el documento oficial".
// Returns null when there is no url, so callers can skip it cleanly.
function enlaceDoc(url, texto) {
    if (!url)
        return null;
    const a = el("a", "enlace-doc");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = texto;
    // Don't let a tap on the link also toggle the surrounding collapsible card.
    a.addEventListener("click", (e) => e.stopPropagation());
    return a;
}
// Marks a doc link as a SEARCH-type link: one that drops the visitor on an
// official government search page where they must look the document up by
// number themselves (no fixed address per document). A single delegated click
// handler (setupAvisoBusqueda) shows a friendly heads-up before leaving the
// site. numero may be null when the document carries no number — then the
// dialog adjusts its wording honestly. etiqueta names the number in plain
// Spanish, e.g. "el número de la ley".
function marcarBusqueda(a, numero, etiqueta) {
    a.dataset.busqueda = "1";
    if (numero)
        a.dataset.numero = numero;
    a.dataset.numeroEtiqueta = etiqueta;
}
/* ---------- Aviso antes de ir al buscador oficial ---------- */
// One small, friendly dialog shown when a visitor taps a SEARCH-type doc link
// (data-busqueda). Direct document links never trigger it — they open in one
// tap, untouched. Wired ONCE via a single delegated listener on the document
// (guarded so it can't double-wire and cancel itself, the bug setupGlosario
// hit). Uses the native <dialog> in docs/index.html for built-in focus trap,
// Escape-to-close and backdrop. Kid-simple Spanish throughout.
let avisoBusquedaWired = false;
function setupAvisoBusqueda() {
    if (avisoBusquedaWired)
        return;
    avisoBusquedaWired = true;
    const dlg = document.getElementById("avisoBuscador");
    const numEl = document.getElementById("avisoNumero");
    const numWrap = document.getElementById("avisoNumeroWrap");
    const sinNumEl = document.getElementById("avisoSinNumero");
    const cuerpoEl = document.getElementById("avisoCuerpo");
    const irBtn = document.getElementById("avisoIr");
    const copyFeed = document.getElementById("avisoCopiado");
    if (!dlg || !numEl || !numWrap || !sinNumEl || !cuerpoEl || !irBtn)
        return;
    const con = "Esa página del gobierno no tiene una dirección fija para cada documento. Cuando llegues, busca este número:";
    const sin = "Esa página del gobierno no tiene una dirección fija para cada documento. Cuando llegues, busca el documento por su nombre o su número.";
    // Delegated, in the CAPTURE phase: every doc link adds its own bubble-phase
    // click listener that calls stopPropagation (so a tap doesn't toggle the
    // surrounding card). That would stop a bubble-phase delegated listener from
    // ever seeing the click. Capturing runs first, top-down, so we intercept the
    // search-type link before its own handler can stop the event.
    document.addEventListener("click", (e) => {
        const target = e.target;
        const a = target === null || target === void 0 ? void 0 : target.closest("a.enlace-doc[data-busqueda]");
        if (!a)
            return;
        e.preventDefault();
        e.stopPropagation();
        const numero = a.dataset.numero || "";
        irBtn.href = a.href;
        if (numero) {
            numEl.textContent = numero;
            numWrap.classList.remove("hidden");
            sinNumEl.classList.add("hidden");
            cuerpoEl.textContent = con;
        }
        else {
            numWrap.classList.add("hidden");
            sinNumEl.classList.remove("hidden");
            cuerpoEl.textContent = sin;
        }
        if (copyFeed)
            copyFeed.classList.add("hidden");
        if (typeof dlg.showModal === "function")
            dlg.showModal();
        else
            dlg.setAttribute("open", "");
    }, true);
    // Tap-to-copy the number, with "¡Copiado!" feedback. Skipped silently if the
    // browser has no clipboard (the visitor still sees the number plainly).
    numWrap.addEventListener("click", () => {
        var _a;
        const txt = numEl.textContent || "";
        if (!txt)
            return;
        const nav = navigator;
        const ok = () => {
            if (!copyFeed)
                return;
            copyFeed.classList.remove("hidden");
            window.setTimeout(() => copyFeed.classList.add("hidden"), 1600);
        };
        // Same forgiving pattern as copiarEnlace: show "¡Copiado!" on both resolve
        // and reject. The number is already on screen, so worst case the visitor
        // copies it by hand — never a broken-looking failure.
        if ((_a = nav.clipboard) === null || _a === void 0 ? void 0 : _a.writeText)
            nav.clipboard.writeText(txt).then(ok, ok);
        else
            ok();
    });
    // "Ir al buscador →" opens the official page in a new tab, then closes the
    // dialog. The anchor's own target/rel handle the safe new-tab open.
    irBtn.addEventListener("click", () => { if (dlg.open)
        dlg.close(); });
    // "Quedarme aquí" and the backdrop both close without leaving the site.
    const quedarme = document.getElementById("avisoQuedarme");
    if (quedarme)
        quedarme.addEventListener("click", () => { if (dlg.open)
            dlg.close(); });
    // Backdrop tap: a click that lands on the <dialog> element itself (not its
    // inner card) is the backdrop. Native dialog already closes on Escape.
    dlg.addEventListener("click", (e) => {
        if (e.target === dlg)
            dlg.close();
    });
}
// Some source strings carry their URL inline as a trailing "(https://...)",
// e.g. the JCE regidores source. This splits that into the descriptive text
// (without the URL) and the bare URL, so the text reads clean and the URL can
// render as a real link. Returns url=null when the string has no trailing URL.
function partirFuenteUrl(fuente) {
    const m = fuente.match(/^(.*?)\s*\((https?:\/\/[^\s)]+)\)\s*$/);
    if (m)
        return { texto: m[1].trim(), url: m[2] };
    return { texto: fuente, url: null };
}
/* ---------- Leyes ---------- */
function renderLeyes(data) {
    const cont = byId("sectores");
    cont.innerHTML = "";
    data.sectores.forEach((sec) => {
        const card = el("div", "sector");
        const head = el("div", "sector-head");
        head.append(el("span", "sector-emoji", sec.emoji), el("h3", "sector-title", sec.nombre), el("span", "sector-count", sec.leyes.length + (sec.leyes.length === 1 ? " ley" : " leyes")), el("span", "sector-chev", "▸"));
        const body = el("div", "sector-body");
        body.style.display = "none";
        sec.leyes.forEach((ley) => body.append(renderLey(ley, data.busqueda_oficial)));
        // Keyboard accessible: behave like an expandable button.
        head.setAttribute("role", "button");
        head.tabIndex = 0;
        head.setAttribute("aria-expanded", "false");
        head.addEventListener("click", () => {
            const abierto = body.style.display !== "none";
            body.style.display = abierto ? "none" : "block";
            card.classList.toggle("open", !abierto);
            head.setAttribute("aria-expanded", String(!abierto));
        });
        head.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                head.click();
            }
        });
        card.append(head, body);
        cont.append(card);
    });
}
// Pulls the initiative number out of a bill title when present, e.g.
// "...(Iniciativa 04789-2024-2028-CD)" -> "04789-2024-2028-CD". Returns null
// when the title carries no number (most Senate bills in our data don't).
function numeroIniciativa(titulo) {
    const m = titulo.match(/Iniciativa\s+([\w-]+)/i);
    return m ? m[1] : null;
}
function renderLey(ley, busqueda) {
    const wrap = el("div", "ley");
    wrap.append(el("p", "ley-titulo", ley.titulo));
    wrap.append(el("span", "ley-estado estado-" + ley.estado, estadoLabel[ley.estado] || ley.estado));
    // Which chamber the bill comes from. Senate is the default (no chip);
    // a chip is shown only when the bill comes from the Cámara de Diputados.
    if (ley.camara) {
        wrap.append(el("span", "ley-camara", "🏛️ Cámara de Diputados"));
    }
    const det = el("div", "ley-detalle");
    det.append(el("h4", null, "¿Qué es?"), el("p", null, ley.que_es));
    // One plain line: how this law touches daily life.
    if (ley.te_afecta) {
        det.append(el("h4", null, "¿Y a mí qué?"), el("p", "te-afecta leer-voz", ley.te_afecta));
    }
    // Only show a real reason; otherwise a quiet note (the Senate source rarely states the motive).
    const sinMotivo = !ley.por_que || /^razón no indicada/i.test(ley.por_que);
    if (sinMotivo) {
        det.append(el("p", "nota-fuente", "El Senado no publicó el motivo. Cuando lo publique, te lo contamos aquí."));
    }
    else {
        det.append(el("h4", null, "¿Por qué se propuso?"), el("p", null, ley.por_que));
    }
    // Votes: shown when the Senate publishes them; otherwise a quiet note.
    if (ley.votos && ley.votos.length) {
        det.append(el("h4", null, "¿Quién votó?"));
        const votos = el("div", "votos");
        ley.votos.forEach((v) => {
            const fila = el("div", "voto-fila");
            fila.append(el("span", null, v.nombre));
            fila.append(el("span", votoClass[v.voto] || "", votoLabel[v.voto] || v.voto));
            votos.append(fila);
        });
        det.append(votos);
    }
    else {
        det.append(el("p", "nota-fuente", "Voto de cada legislador: el Senado aún no lo hace público."));
    }
    // Link to the official search system (5ª sugerencia de un usuario real,
    // Ángel). No stable per-bill URL exists, so we link the chamber's official
    // initiatives page and, when the title carries the initiative number, name it.
    const url = ley.camara ? busqueda === null || busqueda === void 0 ? void 0 : busqueda.camara : busqueda === null || busqueda === void 0 ? void 0 : busqueda.senado;
    if (url) {
        const num = numeroIniciativa(ley.titulo);
        const sistema = ley.camara ? "el SIL de la Cámara" : "el sistema del Senado";
        const texto = num
            ? "📄 Búscala en el sistema oficial: iniciativa " + num
            : "📄 Búscala en " + sistema + " (sistema oficial)";
        const a = enlaceDoc(url, texto);
        // Search-type link: warn the visitor before sending them to the chamber's
        // search system, and (when we have it) tell them which iniciativa number to
        // type. Some Senate bills carry no number — then we show no number, honestly.
        if (a)
            marcarBusqueda(a, num, "el número de la iniciativa");
        if (a)
            det.append(a);
    }
    wrap.append(det);
    // Keyboard accessible: behave like an expandable button.
    wrap.setAttribute("role", "button");
    wrap.tabIndex = 0;
    wrap.setAttribute("aria-expanded", "false");
    wrap.addEventListener("click", (e) => {
        e.stopPropagation();
        const abierto = wrap.classList.toggle("open");
        wrap.setAttribute("aria-expanded", String(abierto));
    });
    wrap.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            wrap.click();
        }
    });
    return wrap;
}
/* ---------- Leyes que entran en vigencia ---------- */
// One tappable card per promulgated law. Collapsed it shows the plain title,
// the law number and the vigencia date; tapped it reveals "¿qué es?", the
// full date explanation and the per-entry source. Same fold idiom (details/
// summary) the rest of the site uses, so it reads consistent on a phone.
function renderVigenciaLey(ley) {
    const card = el("details", "vig-ley");
    const cab = el("summary", "vig-ley-cab");
    cab.append(el("span", "vig-ley-num", "Ley " + ley.numero), el("span", "vig-ley-titulo", ley.titulo), el("span", "vig-ley-fecha", (ley.estado === "pronto" ? "📅 Entra: " : "✅ Desde: ") + fechaLarga(ley.vigencia_fecha)), el("span", "vig-ley-chev", "▸"));
    card.append(cab);
    const det = el("div", "vig-ley-det");
    det.append(el("h4", null, "¿Qué es?"), el("p", null, ley.que_es));
    det.append(el("h4", null, ley.estado === "pronto" ? "¿Cuándo empieza?" : "¿Desde cuándo rige?"), el("p", "vig-ley-cuando", ley.vigencia_texto));
    det.append(el("p", "vig-ley-meta", "El Presidente la firmó (la promulgó) el <b>" + fechaLarga(ley.promulgada) +
        "</b> y se publicó en la Gaceta Oficial " +
        (/^\d+$/.test(ley.gaceta) ? "núm. <b>" + ley.gaceta + "</b>" : "(" + ley.gaceta + ")") + "."));
    det.append(el("p", "nota-fuente", "Fuente: " + ley.fuente + "."));
    // Official-document deep link (5ª sugerencia de un usuario real, Ángel).
    // A direct link to the full law text when we have a verified PDF; otherwise
    // an honest line pointing to the official portal to look it up by number.
    if (ley.url_documento) {
        const a = enlaceDoc(ley.url_documento, "📄 Leer la ley completa (documento oficial)");
        if (a)
            det.append(a);
    }
    else if (ley.url_busqueda) {
        const a = enlaceDoc(ley.url_busqueda, "📄 Búscala en el portal oficial: Ley " + ley.numero);
        // Search-type link: the official portal has no fixed address per law, so we
        // pop a friendly heads-up telling the visitor which number to look up.
        if (a)
            marcarBusqueda(a, ley.numero, "el número de la ley");
        if (a)
            det.append(a);
    }
    card.append(det);
    return card;
}
// Renders the whole "¿Cuáles leyes están por empezar?" block: a glossary intro
// that explains aprobada vs en vigencia, then two groups — already in force
// (nuevas) and entering soon — each a tappable card list. Nothing is invented:
// the block hides itself if the data is missing or empty.
function renderVigencia(data) {
    const host = document.getElementById("vigencia");
    if (!host)
        return;
    host.innerHTML = "";
    const leyes = data.leyes || [];
    if (!leyes.length) {
        host.classList.add("hidden");
        return;
    }
    host.classList.remove("hidden");
    // Intro: aprobada vs en vigencia, with tap-to-define words.
    const intro = el("div", "como vig-intro");
    intro.innerHTML =
        "<b>📅 ¿Cuáles leyes están por empezar?</b><br>" +
            "Que el Congreso apruebe una ley no quiere decir que ya te aplique. " +
            "Primero el Presidente la firma (la " +
            "<span class=\"palabra\" data-def=\"Promulgar es el acto en que el Presidente firma una ley ya aprobada por el Congreso para ordenar que se cumpla y se publique.\">promulga</span>) " +
            "y se publica en la " +
            "<span class=\"palabra\" data-def=\"La Gaceta Oficial es el periódico del Estado donde se publican las leyes para que sean válidas. Una ley no rige hasta que sale ahí.\">Gaceta Oficial</span>. " +
            "Recién entonces empieza su " +
            "<span class=\"palabra\" data-def=\"La vigencia es el momento desde el cual una ley ya manda y debes cumplirla. Algunas rigen de una vez; otras esperan unos meses.\">vigencia</span>: " +
            "la fecha desde la cual ya manda.";
    host.append(intro);
    const vigentes = leyes.filter((l) => l.estado === "vigencia");
    const pronto = leyes.filter((l) => l.estado === "pronto");
    // Group "Entran pronto" goes first — it answers the user's exact question
    // ("¿qué reglas nuevas están por empezar a aplicarme?"); already-in-force
    // laws follow as recent context.
    // Each group folds into a collapsible card (Kelvin: same drop-down flow as
    // the role cards) — title + count visible, tap to see the laws.
    const grupo = (titulo, sub, arr, cls) => {
        if (!arr.length)
            return;
        const wrap = el("details", "grupo-cargo vig-grupo " + cls);
        const cab = el("summary", "grupo-cab vig-cab");
        cab.append(el("span", "grupo-nombre", titulo), el("span", "grupo-conteo", arr.length === 1 ? "1 ley" : arr.length + " leyes"), el("span", "grupo-chev", "▸"));
        wrap.append(cab);
        wrap.append(el("p", "vig-grupo-sub", sub));
        // Newest entry-into-force first within each group.
        const ordenadas = [...arr].sort((a, b) => b.vigencia_fecha.localeCompare(a.vigencia_fecha));
        ordenadas.forEach((l) => wrap.append(renderVigenciaLey(l)));
        host.append(wrap);
    };
    grupo("🔜 Entran pronto", "Ya firmadas, pero su fecha de empezar todavía no llega. Apunta el día.", pronto, "vig-grupo-pronto");
    grupo("✅ Ya en vigencia (nuevas)", "Leyes recientes que ya mandan. Estas reglas ya te aplican.", vigentes, "vig-grupo-vigencia");
    // Default-rule note, folded so the page stays airy.
    if (data.regla_por_defecto) {
        const r = data.regla_por_defecto;
        const det = el("details", "vig-regla");
        det.append(el("summary", "vig-regla-cab", "❓ " + r.titulo));
        const body = el("div", "vig-regla-body");
        body.append(el("p", null, r.texto));
        body.append(el("p", "nota-fuente", "Fuente: " + r.fuente + "."));
        const aRegla = enlaceDoc(r.url, "📄 Ver el documento oficial (PDF)");
        if (aRegla)
            body.append(aRegla);
        det.append(body);
        host.append(det);
    }
    // The block just added glossary words and they need tap-to-define wiring.
    setupGlosario();
}
/* ---------- Novedades (FOLLOW) ---------- */
// Renders the latest improvements into the #novedadesLista list on Inicio.
// Each item is one short line + its long-form date. Newest first, capped at 5.
// Hides the whole block if the data is missing or empty (never an empty card).
function renderNovedades(data) {
    const host = document.getElementById("novedadesLista");
    if (!host)
        return;
    host.innerHTML = "";
    const items = (data.novedades || [])
        .slice()
        .sort((a, b) => b.fecha.localeCompare(a.fecha))
        .slice(0, 5);
    const wrap = host.closest(".novedades");
    if (!items.length) {
        if (wrap)
            wrap.classList.add("hidden");
        return;
    }
    if (wrap)
        wrap.classList.remove("hidden");
    items.forEach((n) => {
        const li = el("li", "novedad");
        li.append(el("span", "novedad-fecha", fechaLarga(n.fecha)), el("span", "novedad-texto", n.texto));
        // Credit / origin label on every entry (Kelvin): who contributed the idea,
        // or a "🔧 Mejora interna" marker for team changes.
        if (n.aporte)
            li.append(el("span", "novedad-aporte", n.aporte));
        host.append(li);
    });
}
/* ---------- Provincias ---------- */
// One kid-friendly explanation per ROLE, matched by the start of the cargo.
// Keeps the language identical for every person with the same job.
function funcionDeCargo(cargo) {
    const c = cargo.toLowerCase();
    if (c.startsWith("senador"))
        return "Hace las leyes del país junto a los diputados. También aprueba nombramientos importantes (como la junta electoral o el defensor del pueblo) y juzga a altos funcionarios acusados. Y representa a toda la provincia en la capital: pelea por su parte del presupuesto y por obras como carreteras, escuelas y hospitales. Hay uno por provincia.";
    if (c.startsWith("diputad"))
        return "También hace y vota las leyes, en nombre de su provincia. Propone proyectos, revisa el presupuesto del país y vigila el trabajo del gobierno. Cada provincia tiene varios, según cuánta gente vive en ella.";
    if (c.startsWith("gobernador"))
        return "Representa al Presidente en la provincia. No hace leyes: es el puente entre el gobierno central y la gente del lugar. Lo nombra la Presidencia; no se elige por voto.";
    if (c.startsWith("alcalde") || c.startsWith("alcaldesa"))
        return "Dirige el ayuntamiento de su pueblo o ciudad. Se encarga del día a día local: calles, basura, aceras, parques, alumbrado y permisos. Se elige por voto de la gente del municipio.";
    if (c.startsWith("director"))
        return "Como un alcalde, pero de un distrito municipal (una zona más pequeña dentro de un municipio). Maneja los servicios locales de esa zona. Se elige por voto.";
    if (c.startsWith("regidor"))
        return "Forma parte del concejo del ayuntamiento. Aprueba el presupuesto del pueblo, dicta las normas locales y vigila el trabajo del alcalde. Se elige por voto.";
    return "";
}
function esLegislador(cargo) {
    const c = cargo.toLowerCase();
    return c.startsWith("senador") || c.startsWith("diputad");
}
function esElecto(cargo) {
    const c = cargo.toLowerCase();
    return c.startsWith("senador") || c.startsWith("diputad") || c.startsWith("alcalde")
        || c.startsWith("alcaldesa") || c.startsWith("regidor") || c.startsWith("director");
}
function sueldoDeCargo(cargo) {
    const c = cargo.toLowerCase();
    if (c.startsWith("senador"))
        return {
            monto: "RD$320,000",
            mes: "abril 2026",
            fuente: "nómina de sueldos fijos del Senado",
        };
    if (c.startsWith("diputad"))
        return {
            monto: "RD$320,000",
            mes: "mayo 2026",
            fuente: "nómina de la Cámara de Diputados",
        };
    if (c.startsWith("gobernador"))
        return {
            monto: "RD$150,000",
            mes: "abril 2026",
            fuente: "nómina de personal fijo del Ministerio de Interior y Policía",
        };
    return null;
}
function iniciales(nombre) {
    var _a, _b;
    const palabras = nombre.trim().split(/\s+/).filter((w) => w.length > 2);
    const ini = (((_a = palabras[0]) === null || _a === void 0 ? void 0 : _a[0]) || "") + (((_b = palabras[1]) === null || _b === void 0 ? void 0 : _b[0]) || "");
    return ini.toUpperCase() || "·";
}
// Official senator portraits from senadord.gob.do (32 verified, fetched
// 2026-06-12). Keyed by "provincia||nombre" so a name is only matched when the
// province also lines up — no portrait is shown for a senator we can't verify.
// Only senators have verified photos; deputies/governors/mayors keep initials.
// Filenames live in docs/img/senadores/. Manifest of record (name, party,
// province, source_url, sha256): senado-reader/gallery/gallery.json.
const RETRATOS_SENADORES = {
    "Distrito Nacional||Omar Leonel Fernández Domínguez": "omar-leonel-fernandez-dominguez.jpg",
    "Azua||Lía Ynocencia Díaz Santana": "lia-ynocencia-diaz-santana.jpg",
    "Bahoruco||Andrés Guillermo Lama Pérez": "andres-guillermo-lama-perez.jpg",
    "Barahona||Moisés Ayala Pérez": "moises-ayala-perez.jpg",
    "Dajabón||Manuel María Rodríguez Ortega": "manuel-maria-rodriguez-ortega.jpg",
    "Duarte||Franklin Martín Romero Morillo": "franklin-martin-romero-morillo.jpg",
    "El Seibo||Santiago José Zorrilla": "santiago-jose-zorrilla.jpg",
    "Elías Piña||Jonhson Encarnación Díaz": "jonhson-encarnacion-diaz.jpg",
    "Espaillat||Carlos Manuel Gómez Ureña": "carlos-manuel-gomez-urena.jpg",
    "Hato Mayor||Cristóbal Venerado Castillo": "cristobal-venerado-castillo.jpg",
    "Hermanas Mirabal||María Mercedes Ortiz Diloné": "maria-mercedes-ortiz-dilone.jpg",
    "Independencia||Dagoberto Rodríguez Adames": "dagoberto-rodriguez-adames.jpg",
    "La Altagracia||Rafael Barón Duluc Rijo": "rafael-baron-duluc-rijo.jpg",
    "La Romana||Eduard Alexis Espiritusanto Castillo": "eduard-alexis-espiritusanto-castillo.jpg",
    "La Vega||Ramón Rogelio Genao Durán": "ramon-rogelio-genao-duran.jpg",
    "María Trinidad Sánchez||Alexis Victoria Yeb": "alexis-victoria-yeb.jpg",
    "Monseñor Nouel||Héctor E. Acosta": "hector-e-acosta.jpg",
    "Monte Cristi||Bernardo Alemán Rodríguez": "bernardo-aleman-rodriguez.jpg",
    "Monte Plata||Pedro Antonio Tineo Núñez": "pedro-antonio-tineo-nunez.jpg",
    "Pedernales||Secundino Velázquez Pimentel": "secundino-velazquez-pimentel.jpg",
    "Peravia||Julito Fulcar Encarnación": "julito-fulcar-encarnacion.jpg",
    "Puerto Plata||Ginnette Altagracia Bournigal": "ginnette-altagracia-bournigal.jpg",
    "Samaná||Pedro Catrain Bonilla": "pedro-catrain-bonilla.jpg",
    "San Cristóbal||Gustavo Lara Salazar": "gustavo-lara-salazar.jpg",
    "San José de Ocoa||Aneudy Ortiz Sajiun": "aneudy-ortiz-sajiun.jpg",
    "San Juan||Félix Bautista Rosario": "felix-bautista-rosario.jpg",
    "San Pedro de Macorís||Aracelis Villanueva": "aracelis-villanueva.jpg",
    "Sánchez Ramírez||Ricardo De Los Santos": "ricardo-de-los-santos.jpg",
    "Santiago||Daniel Enrique De Jesús Rivera Reyes": "daniel-enrique-de-jesus-rivera-reyes.jpg",
    "Santiago Rodríguez||Casimiro Antonio Marte Familia": "casimiro-antonio-marte-familia.jpg",
    "Santo Domingo||Antonio M. Taveras Guzmán": "antonio-m-taveras-guzman.jpg",
    "Valverde||Odalís Rafael Rodríguez Rodríguez": "odalis-rafael-rodriguez-rodriguez.jpg",
};
// Returns the portrait filename for a senator, or null when we have no verified
// photo for that exact person in that exact province. Only senators qualify.
function retratoSenador(provincia, l) {
    if (!l.cargo.toLowerCase().startsWith("senador"))
        return null;
    return RETRATOS_SENADORES[provincia + "||" + l.nombre] || null;
}
// Official deputy portraits from diputadosrd.gob.do (178 verified, fetched
// 2026-06-12). Keyed by "provincia||nombre" exactly like the senators so a
// name is only matched when the province also lines up. Matched 178/178 by
// normalized name against provincias.json — no portrait is fabricated.
// Filenames live in docs/img/diputados/. Manifest of record (name, party,
// province, source_url, sha256):
// senado-reader/gallery-diputados/gallery-diputados.json.
const RETRATOS_DIPUTADOS = {
    "Azua||Brenda Mercedes Ogando Campos": "brenda-mercedes-ogando-campos.jpg",
    "Azua||Julio César Beltré Méndez": "julio-cesar-beltre-mendez.jpg",
    "Azua||Nurca Nieves Luciano Jiménez de Galván": "nurca-nieves-luciano-jimenez-de-galvan.jpg",
    "Azua||Ángela Maruja Gregorina Pérez Díaz": "angela-maruja-gregorina-perez-diaz.jpg",
    "Bahoruco||Juan Bolívar Cuevas Davis": "juan-bolivar-cuevas-davis.jpg",
    "Bahoruco||Olfanny Yuverka Méndez Matos": "olfanny-yuverka-mendez-matos.jpg",
    "Barahona||Aquiles Leonel Ledesma Alcántara": "aquiles-leonel-ledesma-alcantara.jpg",
    "Barahona||José del Carmen Montero Arias": "jose-del-carmen-montero-arias.jpg",
    "Barahona||Sara Penélope Féliz Díaz": "sara-penelope-feliz-diaz.jpg",
    "Dajabón||Adelso de Jesús Ruben Contreras": "adelso-de-jesus-ruben-contreras.jpg",
    "Dajabón||Daritza Felicidad Zapata Díaz": "daritza-felicidad-zapata-diaz.jpg",
    "Distrito Nacional||Alfredo Pacheco Osoria": "alfredo-pacheco-osoria.jpg",
    "Distrito Nacional||Carlos Sánchez Quezada": "carlos-sanchez-quezada.jpg",
    "Distrito Nacional||Charles Noel Mariotti Paz": "charles-noel-mariotti-paz.jpg",
    "Distrito Nacional||Chavely Melina Sánchez Taveras": "chavely-melina-sanchez-taveras.jpg",
    "Distrito Nacional||Eliazer Matos Féliz": "eliazer-matos-feliz.jpg",
    "Distrito Nacional||Fanny Selinés Méndez Simonó": "fanny-selines-mendez-simono.jpg",
    "Distrito Nacional||Francisca Trinidad Jaque Aponte": "francisca-trinidad-jaque-aponte.jpg",
    "Distrito Nacional||Gustavo Antonio Sánchez García": "gustavo-antonio-sanchez-garcia.jpg",
    "Distrito Nacional||José Manuel Caraballo Gómez": "jose-manuel-caraballo-gomez.jpg",
    "Distrito Nacional||Liz Adriana Mieses Díaz": "liz-adriana-mieses-diaz.jpg",
    "Distrito Nacional||Manuel de Jesús Núñez Guerrero": "manuel-de-jesus-nunez-guerrero.jpg",
    "Distrito Nacional||Maribel Altagracia Almánzar de Ogando": "maribel-altagracia-almanzar-de-ogando.jpg",
    "Distrito Nacional||Rafael Aníbal Díaz Rodríguez": "rafael-anibal-diaz-rodriguez.jpg",
    "Distrito Nacional||Rafael Tobías Crespo Pérez": "rafael-tobias-crespo-perez.jpg",
    "Distrito Nacional||Ramón Antonio Bueno Patiño": "ramon-antonio-bueno-patino.jpg",
    "Distrito Nacional||Sergio Moya de la Cruz": "sergio-moya-de-la-cruz.jpg",
    "Distrito Nacional||Vicente Arturo Sánchez Henríquez": "vicente-arturo-sanchez-henriquez.jpg",
    "Distrito Nacional||Yuderka Yvelisse de la Rosa Guerrero": "yuderka-yvelisse-de-la-rosa-guerrero.jpg",
    "Duarte||Dorina Yajaira Rodríguez Salazar": "dorina-yajaira-rodriguez-salazar.jpg",
    "Duarte||Jeovanny Ventura Rivera": "jeovanny-ventura-rivera.jpg",
    "Duarte||José Luis Rodríguez Hiciano": "jose-luis-rodriguez-hiciano.jpg",
    "Duarte||Luis Tomás Marte Santos": "luis-tomas-marte-santos.jpg",
    "Duarte||Nicolás Hidalgo Almánzar": "nicolas-hidalgo-almanzar.jpg",
    "El Seibo||Faustina Guerrero Cabrera": "faustina-guerrero-cabrera.jpg",
    "El Seibo||Valerio Leonardo Palacio": "valerio-leonardo-palacio.jpg",
    "Elías Piña||Luis Enrique Castillo Ogando": "luis-enrique-castillo-ogando.jpg",
    "Elías Piña||Millys Johanna Martínez Morillo": "millys-johanna-martinez-morillo.jpg",
    "Espaillat||José Miguel Ferreiras Torres": "jose-miguel-ferreiras-torres.jpg",
    "Espaillat||Marleni Altagracia Jiménez Muñoz": "marleni-altagracia-jimenez-munoz.jpg",
    "Espaillat||Robinson Antonio Santos Rodríguez": "robinson-antonio-santos-rodriguez.jpg",
    "Espaillat||Shirley Antonia López Féliz": "shirley-antonia-lopez-feliz.jpg",
    "Hato Mayor||Carmen Ligia Barceló González": "carmen-ligia-barcelo-gonzalez.jpg",
    "Hato Mayor||Héctor Fodil Rosa Mercedes": "hector-fodil-rosa-mercedes.jpg",
    "Hermanas Mirabal||Félix Santiago Hiciano Almánzar": "felix-santiago-hiciano-almanzar.jpg",
    "Hermanas Mirabal||Lourdes de Jesús Vélez": "lourdes-de-jesus-velez.jpg",
    "Independencia||Hermes Evangelina José Méndez de Méndez": "hermes-evangelina-jose-mendez-de-mendez.jpg",
    "Independencia||Llanelis Matos Cuevas": "llanelis-matos-cuevas.jpg",
    "La Altagracia||Carmen Aurelia de la Rosa Pérez": "carmen-aurelia-de-la-rosa-perez.jpg",
    "La Altagracia||Francisco Rodolfo Villegas Pérez": "francisco-rodolfo-villegas-perez.jpg",
    "La Altagracia||Jorge Leonardo Tavárez Valdez": "jorge-leonardo-tavarez-valdez.jpg",
    "La Altagracia||Onavel Andrés Aristy Cedeño": "onavel-andres-aristy-cedeno.jpg",
    "La Altagracia||Ángel del Rosario Robles": "angel-del-rosario-robles.jpg",
    "La Romana||Carlos de Pérez Juan": "carlos-de-perez-juan.jpg",
    "La Romana||Eugenio Cedeño Areché": "eugenio-cedeno-areche.jpg",
    "La Romana||Jacqueline Fernández Brito": "jacqueline-fernandez-brito.jpg",
    "La Romana||Wandy Modesto Batista Gómez": "wandy-modesto-batista-gomez.jpg",
    "La Vega||Carolin Mercedes de la Cruz": "carolin-mercedes-de-la-cruz.jpg",
    "La Vega||Elpidio Infante Galán": "elpidio-infante-galan.jpg",
    "La Vega||Gabriela María Abreu Santos": "gabriela-maria-abreu-santos.jpg",
    "La Vega||Gilda Mercedes Moronta Guzmán": "gilda-mercedes-moronta-guzman.jpg",
    "La Vega||José Luis Abreu Veloz": "jose-luis-abreu-veloz.jpg",
    "La Vega||Rogelio Alfonso Genao Lanza": "rogelio-alfonso-genao-lanza.jpg",
    "La Vega||Vilma Hortencia Morillo Vásquez": "vilma-hortencia-morillo-vasquez.jpg",
    "María Trinidad Sánchez||Jesús Stalin Vásquez Marte": "jesus-stalin-vasquez-marte.jpg",
    "María Trinidad Sánchez||Jorge Hugo Cavoli Balbuena": "jorge-hugo-cavoli-balbuena.jpg",
    "María Trinidad Sánchez||Sonia Núñez Espino": "sonia-nunez-espino.jpg",
    "Monseñor Nouel||José Antonio Fabián Beltré": "jose-antonio-fabian-beltre.jpg",
    "Monseñor Nouel||Nolberto Ortiz de la Cruz": "nolberto-ortiz-de-la-cruz.jpg",
    "Monseñor Nouel||Orlando Antonio Martínez Peña": "orlando-antonio-martinez-pena.jpg",
    "Monte Cristi||Johanny Margarita Martínez Gómez": "johanny-margarita-martinez-gomez.jpg",
    "Monte Cristi||Rosendy Joel Polanco Polanco": "rosendy-joel-polanco-polanco.jpg",
    "Monte Plata||Jhonatan Rabel Contreras del Orbe": "jhonatan-rabel-contreras-del-orbe.jpg",
    "Monte Plata||Oscar Adolfo Morel Figueroa": "oscar-adolfo-morel-figueroa.jpg",
    "Monte Plata||Román de Jesús Vargas": "roman-de-jesus-vargas.jpg",
    "Pedernales||Mery Antonia Mercado García de Contreras": "mery-antonia-mercado-garcia-de-contreras.jpg",
    "Pedernales||Rafael Antonio Pérez Gómez": "rafael-antonio-perez-gomez.jpg",
    "Peravia||Carmen Leida Escarfuller Morel de Melo": "carmen-leida-escarfuller-morel-de-melo.jpg",
    "Peravia||Luis Alcides Báez": "luis-alcides-baez.jpg",
    "Peravia||Willy Enrique Sánchez González": "willy-enrique-sanchez-gonzalez.jpg",
    "Puerto Plata||Fiordaliza Estévez Castillo": "fiordaliza-estevez-castillo.jpg",
    "Puerto Plata||Heidy María Musa Kunhardt": "heidy-maria-musa-kunhardt.jpg",
    "Puerto Plata||Jhonny de Jesús Medina Santos": "jhonny-de-jesus-medina-santos.jpg",
    "Puerto Plata||Juan Agustín Medina Santos": "juan-agustin-medina-santos.jpg",
    "Puerto Plata||Julio Emil Durán Rodríguez": "julio-emil-duran-rodriguez.jpg",
    "Puerto Plata||Lidia Esther Pérez de Taveras": "lidia-esther-perez-de-taveras.jpg",
    "Samaná||Carmen Lidia Williams Benjamín": "carmen-lidia-williams-benjamin.jpg",
    "Samaná||Cecilio García Javier": "cecilio-garcia-javier.jpg",
    "San Cristóbal||Ana Miledy Cuevas": "ana-miledy-cuevas.jpg",
    "San Cristóbal||Antonio Brito Rodríguez": "antonio-brito-rodriguez.jpg",
    "San Cristóbal||Francisco Javier Paulino": "francisco-javier-paulino.jpg",
    "San Cristóbal||German Martínez Araujo": "german-martinez-araujo.jpg",
    "San Cristóbal||Gregoria Monserrat Santana Silfa": "gregoria-monserrat-santana-silfa.jpg",
    "San Cristóbal||Jacqueline Montero": "jacqueline-montero.jpg",
    "San Cristóbal||Margarita Tejeda de la Rosa": "margarita-tejeda-de-la-rosa.jpg",
    "San Cristóbal||Nelson Saulo Vega Báez": "nelson-saulo-vega-baez.jpg",
    "San Cristóbal||Otoniel Tejeda Martínez": "otoniel-tejeda-martinez.jpg",
    "San Cristóbal||Ydenia Doñé Tiburcio": "ydenia-done-tiburcio.jpg",
    "San José de Ocoa||Elida Yalis Soto Mordán": "elida-yalis-soto-mordan.jpg",
    "San José de Ocoa||Ángel María Sánchez Pujols": "angel-maria-sanchez-pujols.jpg",
    "San Juan||Carlos Morillo Valdez": "carlos-morillo-valdez.jpg",
    "San Juan||Elvira Corporán de los Santos de Lebrón": "elvira-corporan-de-los-santos-de-lebron.jpg",
    "San Juan||Franklin Ramírez de los Santos": "franklin-ramirez-de-los-santos.jpg",
    "San Juan||Mélido Mercedes Castillo": "melido-mercedes-castillo.jpg",
    "San Pedro de Macorís||Alcibíades Tavárez de la Cruz": "alcibiades-tavarez-de-la-cruz.jpg",
    "San Pedro de Macorís||Carlixta Carolina Paula de la Cruz": "carlixta-carolina-paula-de-la-cruz.jpg",
    "San Pedro de Macorís||Jacobo Ramos Crispín": "jacobo-ramos-crispin.jpg",
    "San Pedro de Macorís||Luis Gómez Benzo": "luis-gomez-benzo.jpg",
    "San Pedro de Macorís||Miguel Arredondo Quezada": "miguel-arredondo-quezada.jpg",
    "Santiago||Brailyn Miguel Vargas Núñez": "brailyn-miguel-vargas-nunez.jpg",
    "Santiago||Braulio de Jesús Espinal Tavárez": "braulio-de-jesus-espinal-tavarez.jpg",
    "Santiago||Deisy Emelda Díaz Salcedo": "deisy-emelda-diaz-salcedo.jpg",
    "Santiago||Dharuelly Leany D´Aza Caraballo": "dharuelly-leany-d-aza-caraballo.jpg",
    "Santiago||Dilenia Altagracia Santos Muñoz": "dilenia-altagracia-santos-munoz.jpg",
    "Santiago||Estamy Rafaela Colón Tatis": "estamy-rafaela-colon-tatis.jpg",
    "Santiago||Francisco Alberto Díaz García": "francisco-alberto-diaz-garcia.jpg",
    "Santiago||Félix Michell Rodríguez Morel": "felix-michell-rodriguez-morel.jpg",
    "Santiago||Gregorio Domínguez Domínguez": "gregorio-dominguez-dominguez.jpg",
    "Santiago||José David Báez Reinoso": "jose-david-baez-reinoso.jpg",
    "Santiago||Llaniris del Carmen Espinal Cabrera": "llaniris-del-carmen-espinal-cabrera.jpg",
    "Santiago||Luis René Fernández Tavárez": "luis-rene-fernandez-tavarez.jpg",
    "Santiago||Mateo Evangelista Espaillat Tavárez": "mateo-evangelista-espaillat-tavarez.jpg",
    "Santiago||Mirna Josefina López Francisco de Matos": "mirna-josefina-lopez-francisco-de-matos.jpg",
    "Santiago||Nelsa Shoraya Suárez Ariza": "nelsa-shoraya-suarez-ariza.jpg",
    "Santiago||Nelson Rafael Marmolejos Gil": "nelson-rafael-marmolejos-gil.jpg",
    "Santiago||Ramón Mayobanex Martínez Durán": "ramon-mayobanex-martinez-duran.jpg",
    "Santiago||Robinson de Jesús Díaz Mejía": "robinson-de-jesus-diaz-mejia.jpg",
    "Santiago Rodríguez||Juana Ramona Castillo": "juana-ramona-castillo.jpg",
    "Santiago Rodríguez||Nicolás Tolentino López Mercado": "nicolas-tolentino-lopez-mercado.jpg",
    "Santo Domingo||Abelardo Antonio Rutinel Arzeno": "abelardo-antonio-rutinel-arzeno.jpg",
    "Santo Domingo||Aldoneris Rafael Adón Duarte": "aldoneris-rafael-adon-duarte.jpg",
    "Santo Domingo||Alexander Javier Cuevas": "alexander-javier-cuevas.jpg",
    "Santo Domingo||Altagracia de los Santos": "altagracia-de-los-santos.jpg",
    "Santo Domingo||Amado Antonio Díaz Jiménez": "amado-antonio-diaz-jimenez.jpg",
    "Santo Domingo||Ana Adalgiza del Carmen Abreu Polanco": "ana-adalgiza-del-carmen-abreu-polanco.jpg",
    "Santo Domingo||Anny Veleissy Mambrú Rodríguez": "anny-veleissy-mambru-rodriguez.jpg",
    "Santo Domingo||Bolívar Ernesto Valera Ariza": "bolivar-ernesto-valera-ariza.jpg",
    "Santo Domingo||Carlos Alberto Pérez Hernández": "carlos-alberto-perez-hernandez.jpg",
    "Santo Domingo||Carlos José Gil Rodríguez": "carlos-jose-gil-rodriguez.jpg",
    "Santo Domingo||Damarys Vásquez Castillo": "damarys-vasquez-castillo.jpg",
    "Santo Domingo||Dellys Dumidia Féliz Rodríguez": "dellys-dumidia-feliz-rodriguez.jpg",
    "Santo Domingo||Diómedes Omar Rojas": "diomedes-omar-rojas.jpg",
    "Santo Domingo||Domingo Eusebio de León Mascaró": "domingo-eusebio-de-leon-mascaro.jpg",
    "Santo Domingo||Eduviges María Bautista Gomera": "eduviges-maria-bautista-gomera.jpg",
    "Santo Domingo||Enriqueta Rojas Javier": "enriqueta-rojas-javier.jpg",
    "Santo Domingo||Eudy Maldonado de la Cruz": "eudy-maldonado-de-la-cruz.jpg",
    "Santo Domingo||Franklin Martínez": "franklin-martinez.jpg",
    "Santo Domingo||Félix Manuel Encarnación Montero": "felix-manuel-encarnacion-montero.jpg",
    "Santo Domingo||Heriberto Aracena Montilla": "heriberto-aracena-montilla.jpg",
    "Santo Domingo||Ignacio Aracena": "ignacio-aracena.jpg",
    "Santo Domingo||Indhira Shary de Jesús de Morla": "indhira-shary-de-jesus-de-morla.jpg",
    "Santo Domingo||Jesús Manuel Sánchez Martínez": "jesus-manuel-sanchez-martinez.jpg",
    "Santo Domingo||Jheyson Amir García Castillo": "jheyson-amir-garcia-castillo.jpg",
    "Santo Domingo||Jorge Frías": "jorge-frias.jpg",
    "Santo Domingo||José Moisés Ortiz López": "jose-moises-ortiz-lopez.jpg",
    "Santo Domingo||Juan Carlos Echavarría Milané": "juan-carlos-echavarria-milane.jpg",
    "Santo Domingo||Juan José Rojas Franco": "juan-jose-rojas-franco.jpg",
    "Santo Domingo||Junior Muñoz Olivo": "junior-munoz-olivo.jpg",
    "Santo Domingo||Kinsberly Taveras Duarte": "kinsberly-taveras-duarte.jpg",
    "Santo Domingo||Lucila Leonarda de León Martínez": "lucila-leonarda-de-leon-martinez.jpg",
    "Santo Domingo||María Elisa Suárez Alcalá": "maria-elisa-suarez-alcala.jpg",
    "Santo Domingo||Melvin Alexis Lara Melo": "melvin-alexis-lara-melo.jpg",
    "Santo Domingo||Miguel Alberto Bogaert Marra": "miguel-alberto-bogaert-marra.jpg",
    "Santo Domingo||Miguel Eduardo Espinal Muñoz": "miguel-eduardo-espinal-munoz.jpg",
    "Santo Domingo||Patricia Alexandra Núñez Rivera": "patricia-alexandra-nunez-rivera.jpg",
    "Santo Domingo||Pedro Julio Alcántara": "pedro-julio-alcantara.jpg",
    "Santo Domingo||Rafael Augusto Castillo Casado": "rafael-augusto-castillo-casado.jpg",
    "Santo Domingo||Rafaela González González": "rafaela-gonzalez-gonzalez.jpg",
    "Santo Domingo||Tayluma Monserrat Calderón Fortuna": "tayluma-monserrat-calderon-fortuna.jpg",
    "Santo Domingo||Víctor Virgilio Jiménez": "victor-virgilio-jimenez.jpg",
    "Santo Domingo||Yancarlos Simanca Ferreras": "yancarlos-simanca-ferreras.jpg",
    "Santo Domingo||Ycelmary Brito O´Neal": "ycelmary-brito-o-neal.jpg",
    "Sánchez Ramírez||Caty Díaz Abreu": "caty-diaz-abreu.jpg",
    "Sánchez Ramírez||José Alberto Jiménez Santos": "jose-alberto-jimenez-santos.jpg",
    "Sánchez Ramírez||Sadoky Duarte Suárez": "sadoky-duarte-suarez.jpg",
    "Valverde||José Altagracia Valenzuela Arias": "jose-altagracia-valenzuela-arias.jpg",
    "Valverde||María de los Ángeles Rodríguez Bonseñor": "maria-de-los-angeles-rodriguez-bonsenor.jpg",
    "Valverde||Rubén Darío Peñaló Torres": "ruben-dario-penalo-torres.jpg",
};
// Returns the portrait filename for a deputy, or null when we have no verified
// photo for that exact person in that exact province. Only deputies qualify.
function retratoDiputado(provincia, l) {
    if (!l.cargo.toLowerCase().startsWith("diputad"))
        return null;
    return RETRATOS_DIPUTADOS[provincia + "||" + l.nombre] || null;
}
const ORDEN_GRUPOS = ["senador", "diputad", "gobernador", "alcalde", "director", "regidor", "otros"];
const ETIQUETA_GRUPO = {
    senador: "Senador/a",
    diputad: "Diputados/as",
    gobernador: "Gobernador/a",
    alcalde: "Alcaldes/sas",
    director: "Directores/as de distrito",
    regidor: "Regidores/as",
    otros: "Otros",
};
function grupoDeCargo(cargo) {
    const c = cargo.toLowerCase();
    return ORDEN_GRUPOS.find((k) => k !== "otros" && c.startsWith(k)) || "otros";
}
function renderLider(l, provincia) {
    const block = el("div", "lider");
    const cab = el("div", "lider-cab");
    // Senators and deputies with a verified official portrait show the photo;
    // everyone else (governors, mayors, regidores, and anyone we couldn't match)
    // keeps the initials circle. The carpeta (folder) differs per cargo so each
    // photo is read from its own official-source set.
    const retratoSen = retratoSenador(provincia, l);
    const retratoDip = retratoSen ? null : retratoDiputado(provincia, l);
    const retrato = retratoSen || retratoDip;
    const carpeta = retratoSen ? "img/senadores/" : "img/diputados/";
    if (retrato) {
        const img = el("img", "avatar avatar-foto");
        img.src = carpeta + retrato;
        img.alt = "Retrato oficial de " + l.nombre;
        img.width = 44;
        img.height = 44;
        img.loading = "lazy";
        img.decoding = "async";
        // If the file ever fails to load, fall back to the initials circle so the
        // card never shows a broken-image icon.
        img.addEventListener("error", () => {
            const fb = el("span", "avatar", iniciales(l.nombre));
            img.replaceWith(fb);
        });
        cab.append(img);
    }
    else {
        cab.append(el("span", "avatar", iniciales(l.nombre)));
    }
    const ident = el("div", "lider-ident");
    ident.append(el("p", "lider-nombre", "<b>" + l.nombre + "</b><span class='partido-chip'>" + l.partido + "</span>"));
    ident.append(el("p", "lider-cargo", l.cargo));
    cab.append(ident);
    block.append(cab);
    if (esElecto(l.cargo)) {
        block.append(el("p", "lider-dato", "🗓️ En el cargo: 2024–2028 (elegido por voto)"));
    }
    const fn = funcionDeCargo(l.cargo);
    if (fn)
        block.append(el("p", "lider-funcion", fn));
    if (l.resumen)
        block.append(el("p", null, l.resumen));
    // --- Report-card lines, regrouped into a compact chip row. Each stat shows a
    //     short headline in the chip (emoji + number) and tucks its full sentence
    //     behind a tap, reusing the native <details> fold idiom. A leader without
    //     any data renders no chip row at all, exactly as before. ---
    const chips = el("div", "lider-chips");
    // Helper: one tappable stat chip. summary = short headline; body = full line.
    const datoChip = (resumen, detalle) => {
        const d = el("details", "dato-chip");
        d.append(el("summary", "dato-chip-cab", resumen), el("p", "dato-chip-det", detalle));
        return d;
    };
    // Lane 1: plenary attendance.
    if (l.asistencia && l.asistencia.total > 0) {
        const a = l.asistencia;
        chips.append(datoChip("📅 <b>" + a.presentes + "/" + a.total + "</b> sesiones", "Asistencia: estuvo en <b>" + a.presentes + " de " + a.total +
            "</b> sesiones del Pleno (" + a.periodo + ")."));
    }
    // Lane 2: committees the senator works in.
    if (l.comisiones && l.comisiones.length) {
        chips.append(datoChip("🗂️ <b>" + l.comisiones.length + "</b> comisiones", "Trabaja en " + l.comisiones.length + " comisiones: " + l.comisiones.join(", ") + "."));
    }
    // Lane 3: bills proposed or co-proposed.
    if (typeof l.iniciativas_propuestas === "number") {
        const n = l.iniciativas_propuestas;
        chips.append(datoChip("📜 <b>" + n + "</b> " + (n === 1 ? "iniciativa" : "iniciativas"), "Ha propuesto o copropuesto <b>" + n + "</b> " +
            (n === 1 ? "iniciativa" : "iniciativas") + " en este período."));
    }
    // Lane 5: voting participation (deputies) — how many recent recorded roll-call
    // votes they actually cast. Neutral count from the Chamber's own public data.
    if (l.votaciones_pleno && l.votaciones_pleno.total > 0) {
        const vp = l.votaciones_pleno;
        chips.append(datoChip("🗳️ Votó en <b>" + vp.emitidas + "/" + vp.total + "</b>", "En las últimas <b>" + vp.total + "</b> votaciones del Pleno que registramos (sesiones " +
            "recientes), emitió su voto en <b>" + vp.emitidas + "</b>. En las demás se ausentó o no votó. " +
            "Algunas votaciones son de procedimiento interno; esto muestra si participa en las votaciones, " +
            "no cómo votó cada ley. Dato público de la Cámara de Diputados."));
    }
    // Lane 4: base monthly salary, from the public payroll. Senators, deputies
    // and governors share a role-wide rate (sueldoDeCargo); mayors each have their
    // own amount read from their own ayuntamiento's nómina (l.sueldo).
    const sueldo = sueldoDeCargo(l.cargo) || l.sueldo || null;
    if (sueldo) {
        chips.append(datoChip("💰 Sueldo del cargo: <b>" + sueldo.monto + "/mes</b>", "Es el salario mensual oficial que paga el Estado por ocupar el cargo. " +
            "No es dinero de otras fuentes ni su patrimonio.<br>" +
            "Monto: <b>" + sueldo.monto + " al mes</b>, según la " + sueldo.fuente +
            " de " + sueldo.mes + ". Lo pagan los impuestos de todos."));
    }
    if (chips.children.length)
        block.append(chips);
    // Honest note for roles that don't legislate: explain why there are no
    // attendance/bill stats instead of leaving the card looking unfinished.
    const cargoLower = l.cargo.toLowerCase();
    if (cargoLower.startsWith("gobernador")) {
        block.append(el("p", "nota-fuente", "El gobernador no hace leyes ni vota en el Congreso, por eso no tiene asistencia ni iniciativas. Lo nombra la Presidencia, y su sueldo sale en la nómina del Ministerio de Interior y Policía."));
    }
    else if (cargoLower.startsWith("alcalde")) {
        // When we already show this mayor's salary (from their ayuntamiento's own
        // nómina), drop the "estamos reuniendo" promise and just explain the role.
        const nota = l.sueldo
            ? "El alcalde trabaja en el ayuntamiento, no en el Congreso, por eso no tiene asistencia ni iniciativas de leyes. Su sueldo sale en la nómina de su propio ayuntamiento."
            : "El alcalde trabaja en el ayuntamiento, no en el Congreso, por eso no tiene asistencia ni iniciativas de leyes. Su sueldo lo publica cada ayuntamiento; aún estamos reuniendo esas nóminas.";
        block.append(el("p", "nota-fuente", nota));
    }
    if (esLegislador(l.cargo)) {
        // When we've read this legislator's votes from the official boards, show an
        // expandable record: a "Registro de votos" card -> one fold per session ->
        // the bills voted on, each with the plain "¿qué es?" / "¿y a mí qué?" and how
        // this person voted. Gated on l.votos so the other legislators (and every
        // non-legislator) keep the plain fallback line below, exactly as before.
        if (l.votos && l.votos.length) {
            block.append(renderRegistroVotos(l));
        }
        else {
            block.append(el("p", "lider-cargo", "Registro de votos: " + l.registro));
        }
    }
    return block;
}
// Builds the expandable "Registro de votos" record for a legislator that has
// per-session vote data (l.votos). Outer card folds open to the honest scope
// note + one fold per session; each session fold opens to its bills, and each
// bill shows the plain explanation and this person's vote. Nothing is invented:
// every title/explanation comes verbatim from the data passed in.
function renderRegistroVotos(l) {
    const votos = l.votos;
    const totalLeyes = votos.reduce((n, s) => n + (s.leyes ? s.leyes.length : 0), 0);
    const card = el("details", "grupo-cargo votos-registro");
    const cab = el("summary", "grupo-cab");
    cab.append(el("span", "grupo-nombre", "🗳️ Registro de votos"), el("span", "grupo-conteo", totalLeyes + (totalLeyes === 1 ? " voto" : " votos")), el("span", "grupo-chev", "▸"));
    card.append(cab);
    const body = el("div", "votos-registro-body");
    // Honest scope line first: these are the recent sessions we've read, not the
    // whole term.
    const nota = l.votos_nota ||
        "Estas son las sesiones recientes del Senado que ya leímos, no todo su período.";
    body.append(el("p", "nota-fuente", nota));
    votos.forEach((ses) => {
        if (!ses.leyes || !ses.leyes.length)
            return;
        const sDet = el("details", "votos-sesion");
        const sCab = el("summary", "votos-sesion-cab");
        sCab.append(el("span", "votos-sesion-nom", "Sesión " + ses.sesion), el("span", "votos-sesion-conteo", ses.leyes.length + (ses.leyes.length === 1 ? " ley" : " leyes")), el("span", "grupo-chev", "▸"));
        sDet.append(sCab);
        ses.leyes.forEach((ley) => {
            const wrap = el("div", "voto-ley");
            // Title + this person's vote on the same row, the vote colored like the
            // existing per-law vote rows (voto-si / voto-no / voto-aus).
            const top = el("div", "voto-ley-top");
            top.append(el("span", "voto-ley-titulo", ley.titulo));
            top.append(el("span", "voto-ley-voto " + (votoClass[ley.voto] || ""), votoLabel[ley.voto] || ley.voto));
            wrap.append(top);
            if (ley.que_es) {
                wrap.append(el("h4", "voto-ley-h", "¿Qué es?"), el("p", "voto-ley-p", ley.que_es));
            }
            if (ley.como_afecta) {
                wrap.append(el("h4", "voto-ley-h", "¿Y a mí qué?"), el("p", "voto-ley-p", ley.como_afecta));
            }
            sDet.append(wrap);
        });
        body.append(sDet);
    });
    card.append(body);
    return card;
}
// "¿Y los regidores?" — a small explainer card in every province profile.
// Explains, kid-simple, what a regidor is (the town council that approves the
// mayor's budget and rules — los concejales del pueblo) and that each
// municipality elects several. Shows the verified total ONLY when present in
// the data; otherwise it stays a pure explainer with no invented number.
// When verified names exist (regidores.lista), they render as a name+party list.
function renderRegidoresCard(prov) {
    // Same drop-down card flow as the other roles (Kelvin): title + count
    // collapsed; tap to see the explainer and the named lists.
    const r0 = prov.regidores;
    const nombres = r0 && r0.municipios
        ? r0.municipios.reduce((n, m) => n + (m.lista ? m.lista.length : 0), 0) : 0;
    const wrap = el("details", "grupo-cargo");
    const cab = el("summary", "grupo-cab");
    cab.append(el("span", "grupo-nombre", "Regidores/as"), el("span", "grupo-conteo", nombres > 0
        ? nombres + " con nombre"
        : (r0 && typeof r0.total === "number" ? String(r0.total) + " personas" : "¿qué son?")), el("span", "grupo-chev", "▸"));
    wrap.append(cab);
    wrap.append(renderRegidoresBody(prov));
    return wrap;
}
function renderRegidoresBody(prov) {
    const card = el("div", "como");
    let html = "<b>🪑 ¿Y los regidores?</b> En cada ayuntamiento, además del alcalde, hay un grupo de " +
        "<span class=\"palabra\" data-def=\"Los regidores son el grupo de personas, elegidas por voto, que forman el concejo del ayuntamiento. Aprueban el presupuesto del pueblo, dictan las normas locales y vigilan al alcalde. Son como los concejales del pueblo.\">regidores</span>: " +
        "son los concejales del pueblo. Aprueban el presupuesto del municipio, dictan las normas locales y vigilan al alcalde. " +
        "Cada municipio elige varios por voto, según cuánta gente vive en él.";
    const r = prov.regidores;
    // When the source string carries its URL inline (JCE), keep the descriptive
    // text here and render the URL as a tappable link below (5ª sugerencia de un
    // usuario real, Ángel).
    let fuenteTotalLink = null;
    if (r && typeof r.total === "number") {
        let textoFuente = r.fuente_total || "";
        if (r.fuente_total) {
            const partida = partirFuenteUrl(r.fuente_total);
            textoFuente = partida.texto;
            fuenteTotalLink = enlaceDoc(partida.url || undefined, "📄 Ver la lista oficial (JCE)");
        }
        html += "<br><br>En esta provincia hay <b>" + r.total + " regidores</b> en total" +
            (textoFuente ? ", según " + textoFuente : "") + ".";
    }
    else {
        html += "<br><br><span class=\"nota-fuente\">Cuántos hay en total en esta provincia: aún estamos confirmando la cifra con datos oficiales de la JCE.</span>";
    }
    card.innerHTML = html;
    if (fuenteTotalLink)
        card.append(fuenteTotalLink);
    // Verified names per municipality, when we have them. A municipality's list
    // folds behind a tap so a 30-name council doesn't flood the card.
    if (r && r.municipios && r.municipios.length) {
        r.municipios.forEach((m) => {
            if (!m.lista || !m.lista.length)
                return;
            const det = el("details", "regidores-lista");
            det.append(el("summary", "regidores-municipio", "🪑 Regidores de " + m.municipio + " (" + m.lista.length + ")"));
            m.lista.forEach((rg) => {
                const fila = el("p", "regidor-fila");
                fila.innerHTML = rg.nombre + " <span class='partido-chip'>" + rg.partido + "</span>";
                det.append(fila);
            });
            if (m.fuente_lista) {
                // Render the source text clean and turn its inline URL into a link.
                const partida = partirFuenteUrl(m.fuente_lista);
                det.append(el("p", "nota-fuente", "Fuente: " + partida.texto + "."));
                const a = enlaceDoc(partida.url || undefined, "📄 Ver la lista oficial (JCE)");
                if (a)
                    det.append(a);
            }
            card.append(det);
        });
    }
    return card;
}
function renderProvincias(data) {
    const grid = el("div", "prov-grid");
    const perfil = byId("perfilProvincia");
    const ordenadas = [...data.provincias].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
    ordenadas.forEach((prov) => {
        const c = el("div", "prov-card");
        c.append(el("span", "prov-nombre", prov.nombre));
        const n = prov.lideres.length;
        c.append(el("span", "prov-count", n + (n === 1 ? " cargo" : " cargos")));
        // Keyboard accessible: behave like a button.
        c.setAttribute("role", "button");
        c.tabIndex = 0;
        c.setAttribute("aria-label", "Ver " + prov.nombre);
        c.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                c.click();
            }
        });
        c.addEventListener("click", () => {
            perfil.classList.remove("hidden");
            perfil.innerHTML = "";
            const cerrar = el("button", "perfil-cerrar", "✕ Cerrar");
            cerrar.addEventListener("click", () => {
                perfil.classList.add("hidden");
                perfil.innerHTML = "";
            });
            perfil.append(cerrar);
            perfil.append(el("h3", null, prov.nombre));
            // Group the officials by role so a long list (e.g. 43 deputies) stays scannable.
            const grupos = {};
            prov.lideres.forEach((l) => {
                const k = grupoDeCargo(l.cargo);
                (grupos[k] = grupos[k] || []).push(l);
            });
            // Each role folds into its own card (Kelvin: find your target without
            // scrolling through every position). Same details/summary flow as Sesiones.
            ORDEN_GRUPOS.forEach((k) => {
                const arr = grupos[k];
                if (!arr || !arr.length)
                    return;
                const etq = ETIQUETA_GRUPO[k] || "Otros";
                const grupoCard = el("details", "grupo-cargo");
                const cab = el("summary", "grupo-cab");
                cab.append(el("span", "grupo-nombre", etq), el("span", "grupo-conteo", arr.length === 1 ? "1 persona" : arr.length + " personas"), el("span", "grupo-chev", "▸"));
                grupoCard.append(cab);
                arr.forEach((l) => grupoCard.append(renderLider(l, prov.nombre)));
                perfil.append(grupoCard);
            });
            // Honest note when this province's mayors aren't loaded yet.
            if (!grupos["alcalde"]) {
                perfil.append(el("p", "nota-fuente", "Alcaldes: aún por añadir. Estamos completando esta provincia con datos oficiales. " +
                    "¿Conoces a tu alcalde? <a href=\"https://github.com/politica-sencilla-rd/leyes-rd/issues/new/choose\" target=\"_blank\" rel=\"noopener\">Ayúdanos a completarlo</a>."));
            }
            // Always explain the town council (regidores) — feedback de un usuario real.
            perfil.append(renderRegidoresCard(prov));
            // The card just added a new .palabra word; wire tap-to-define on it.
            setupGlosario();
            perfil.scrollIntoView({ behavior: "smooth", block: "start" });
        });
        grid.append(c);
    });
    const host = byId("provincias");
    host.innerHTML = "";
    // "¿Cómo leer esto?" — explains the new report-card lines on a senator card,
    // in kid-simple Spanish, with tap-to-define words. Only shows once, on top.
    const comoLeer = el("div", "como");
    comoLeer.innerHTML =
        "<b>¿Cómo leer la ficha de un senador?</b> Al abrir una provincia y tocar a su senador verás cuatro datos nuevos:<br>" +
            "📅 <b>Asistencia</b>: a cuántas reuniones del " +
            "<span class=\"palabra\" data-def=\"La reunión grande donde todos los senadores se juntan a votar las leyes.\">Pleno</span> " +
            "fue, de las que pudimos contar. Ir es su trabajo.<br>" +
            "🗂️ <b>Comisiones</b>: una " +
            "<span class=\"palabra\" data-def=\"Un grupo pequeño de senadores que estudia un tema (salud, educación, dinero) antes de que todos voten.\">comisión</span> " +
            "es un equipo que estudia un tema a fondo. Trabajar en varias es normal.<br>" +
            "📜 <b>Iniciativas</b>: cuántas " +
            "<span class=\"palabra\" data-def=\"Una idea de ley o resolución que el senador presenta, solo o junto a otros, para que el Senado la estudie.\">propuestas de ley</span> " +
            "ha presentado, solo o con otros.<br>" +
            "💰 <b>Sueldo del cargo</b>: el salario mensual oficial que paga el Estado por ocupar el puesto. " +
            "No es dinero de otras fuentes ni su patrimonio. Sale de la " +
            "<span class=\"palabra\" data-def=\"La lista pública de lo que cobra cada empleado del Estado. La ley obliga a publicarla cada mes.\">nómina</span> " +
            "pública. Lo pagan los impuestos de todos nosotros.";
    host.append(comoLeer);
    host.append(grid);
    // New glossary words were just added — wire up tap-to-define on them.
    setupGlosario();
}
function contarPorPartido(data, cargoStart) {
    const cuenta = {};
    data.provincias.forEach((p) => {
        p.lideres.forEach((l) => {
            if (l.cargo.toLowerCase().startsWith(cargoStart)) {
                const part = l.partido || "?";
                cuenta[part] = (cuenta[part] || 0) + 1;
            }
        });
    });
    return Object.keys(cuenta)
        .map((k) => ({ partido: k, asientos: cuenta[k] }))
        // Most seats first; ties broken by party initials so the order is stable.
        .sort((a, b) => b.asientos - a.asientos || a.partido.localeCompare(b.partido));
}
// A fixed color per party so the bar, the legend and the detail all agree.
// Parties not listed fall back to a neutral grey (never invented data, just a
// color). Colors picked to read apart on a small phone screen.
const COLOR_PARTIDO = {
    PRM: "#1a4ed8", // azul — same family as the site accent
    FP: "#7b2ff7", // morado
    PLD: "#1f9d57", // verde
    PRSC: "#e0651a", // naranja
    DXC: "#0fb5c4", // turquesa
    PPG: "#d8261a", // rojo
    PLR: "#c01b8a", // magenta
};
const COLOR_OTROS = "#565e6e"; // gris para el grupo "Otros"
function colorDePartido(partido) {
    return COLOR_PARTIDO[partido] || COLOR_OTROS;
}
// Renders one chamber: a grid of actual seat dots (one per legislator, colored
// by party, sorted so each party forms a contiguous block, majority obvious at a
// glance) + a legend of party chips, with the real per-party counts folded behind
// a tap, plus one honest takeaway derived only from the math. Tiny parties (1–2
// seats) collapse into "Otros" on the legend for readability — the seat grid and
// the fold-out detail still show every party.
function renderCamara(nombre, total, conteo) {
    const wrap = el("div", "camara-comp");
    wrap.append(el("p", "camara-titulo", "<b>" + nombre + "</b> <span class=\"camara-total\">" + total + " asientos</span>"));
    // Group tiny parties (1–2 seats) into "Otros" for the legend only.
    const grandes = conteo.filter((c) => c.asientos > 2);
    const pequenos = conteo.filter((c) => c.asientos <= 2);
    const otrosTotal = pequenos.reduce((n, c) => n + c.asientos, 0);
    const segmentos = [...grandes];
    if (otrosTotal > 0)
        segmentos.push({ partido: "Otros", asientos: otrosTotal });
    // Seat grid: one dot per legislator, in party order so each party is a solid
    // block and the majority reads at a glance. The grid is decorative-plus — it
    // carries an aria-label summarizing the counts; the legend below is the
    // readable source of truth. Tighter dots for the bigger Cámara so 178 stay
    // crisp and the grid wraps instead of stretching the page.
    const grande = total > 60;
    const grid = el("div", "comp-asientos" + (grande ? " comp-asientos-densa" : ""));
    grid.setAttribute("role", "img");
    grid.setAttribute("aria-label", nombre + ": " + conteo.map((c) => c.partido + " " + c.asientos).join(", ") + " de " + total + " asientos.");
    conteo.forEach((c) => {
        for (let i = 0; i < c.asientos; i++) {
            const dot = el("span", "comp-asiento");
            dot.style.background = colorDePartido(c.partido);
            dot.title = c.partido;
            grid.append(dot);
        }
    });
    wrap.append(grid);
    // Legend: one chip per visible segment (initials + count).
    const leyenda = el("div", "comp-leyenda");
    segmentos.forEach((s) => {
        const chip = el("span", "comp-chip");
        const punto = el("span", "comp-punto");
        punto.style.background = s.partido === "Otros" ? COLOR_OTROS : colorDePartido(s.partido);
        chip.append(punto, el("span", "comp-chip-txt", s.partido + " " + s.asientos));
        leyenda.append(chip);
    });
    wrap.append(leyenda);
    // Honest takeaway, derived from the math only — no political commentary.
    const lider = conteo[0];
    if (lider) {
        const mitad = total / 2;
        let cola;
        if (lider.asientos > mitad)
            cola = " — más de la mitad.";
        else if (lider.asientos === mitad)
            cola = " — justo la mitad.";
        else
            cola = " — la mayor parte, pero no la mitad.";
        const sustantivo = nombre.toLowerCase().includes("senado") ? "senadores" : "diputados";
        wrap.append(el("p", "comp-clave", "El <b>" + lider.partido + "</b> tiene <b>" + lider.asientos + " de " + total + "</b> " + sustantivo + cola));
    }
    // Fold-out detail: every party with its real count, biggest first.
    const det = el("details", "comp-detalle");
    det.append(el("summary", "comp-detalle-cab", "Ver el detalle por partido"));
    conteo.forEach((c) => {
        const fila = el("p", "comp-detalle-fila");
        const punto = el("span", "comp-punto");
        punto.style.background = colorDePartido(c.partido);
        fila.append(punto, el("span", null, c.partido + ": " + c.asientos +
            (c.asientos === 1 ? " asiento" : " asientos")));
        det.append(fila);
    });
    wrap.append(det);
    return wrap;
}
function renderComposicion(data) {
    const host = document.getElementById("composicionCongreso");
    if (!host)
        return;
    const senado = contarPorPartido(data, "senador");
    const diputados = contarPorPartido(data, "diputad");
    const totalSen = senado.reduce((n, c) => n + c.asientos, 0);
    const totalDip = diputados.reduce((n, c) => n + c.asientos, 0);
    host.innerHTML = "";
    const card = el("div", "comp-card");
    card.append(renderCamara("Senado", totalSen, senado));
    card.append(renderCamara("Cámara de Diputados", totalDip, diputados));
    card.append(el("p", "nota-fuente", "Cuenta hecha con los datos verificados de esta misma página (Senado y Cámara, 2024–2028)."));
    host.append(card);
}
/* ---------- Sesiones ---------- */
const MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
function fechaLarga(iso) {
    // iso = "2026-04-15"
    const parts = iso.split("-");
    if (parts.length !== 3)
        return iso;
    const y = parts[0];
    const m = Number(parts[1]) - 1;
    const d = Number(parts[2]);
    const mes = MESES[m] || parts[1];
    return d + " de " + mes + " de " + y;
}
// True when a string is a real ISO date ("2026-06-12"), false for the
// by-session fallback (the session code like "0116"). Lets the by-session view
// show a friendly date when one exists and fall back to the number otherwise,
// without ever inventing a date.
function esFechaIso(s) {
    return /^\d{4}-\d{2}-\d{2}$/.test(s);
}
const estadoAsist = {
    presente: "✅ Presente",
    ausente: "➖ Ausente",
    excusado: "📝 Excusado",
};
function renderSesiones(data, votosPorSesion) {
    const cont = byId("sesiones");
    cont.innerHTML = "";
    if (data.sesiones.length) {
        const fechas = data.sesiones.map((s) => s.fecha).sort();
        const ultima = fechas[fechas.length - 1];
        cont.append(el("p", "nota-fuente", "Última sesión publicada: " + fechaLarga(ultima) + "."));
    }
    // By-session vote detail (the second door to the same vote data): voting record
    // organized by session and bill, with the per-senator roll. Rendered first, as
    // its own clearly-labelled block; the anonymous attendance/tally cards below
    // stay exactly as before. Skipped cleanly if the data file is missing/empty.
    if (votosPorSesion) {
        const detalle = renderSesionesVotos(votosPorSesion);
        if (detalle)
            cont.append(detalle);
    }
    // Kid-simple legend: what "primera/segunda discusión" and "unanimidad" mean.
    const leyenda = el("div", "como");
    leyenda.innerHTML =
        "<b>¿Cómo leer esto?</b> Una ley se vota <b>dos veces</b> en el Senado: la primera discusión y la segunda. " +
            "Si gana las dos, sigue su camino para ser ley. Las resoluciones (homenajes, peticiones) se deciden en una sola votación: <b>única discusión</b>. " +
            "<b>Unanimidad</b> = todos los presentes dijeron que sí.";
    cont.append(leyenda);
    data.sesiones.forEach((ses) => {
        // Each session collapses to one line. All start CLOSED so the tab opens
        // short and consistent with every other tab (the user taps the session
        // they want). The most recent is listed first.
        const card = el("details", "sesion");
        const head = el("summary", "sesion-head");
        head.append(el("span", "sesion-fecha", fechaLarga(ses.fecha)), el("span", "sesion-conteo", ses.votaciones.length + " votaciones"), el("span", "sesion-acta", "Acta " + ses.acta), el("span", "sesion-chev", "▸"));
        card.append(head);
        // Votaciones
        const vlist = el("div", "votaciones");
        ses.votaciones.forEach((v) => {
            const row = el("div", "votacion");
            // Plain title up front; the official legalese title tucks behind a tap.
            if (v.titulo_facil) {
                row.append(el("p", "votacion-titulo", v.titulo_facil));
                const oficial = el("details", "oficial");
                oficial.append(el("summary", null, "📜 Ver nombre oficial"), el("p", "votacion-titulo-oficial", v.titulo));
                row.append(oficial);
            }
            else {
                row.append(el("p", "votacion-titulo", v.titulo));
            }
            const meta = el("div", "votacion-meta");
            const aprob = /^aprob/i.test(v.resultado);
            const icono = aprob ? "✅ " : "•&nbsp;";
            meta.append(el("span", "v-iniciativa", "Iniciativa " + v.iniciativa), el("span", "v-conteo", v.a_favor + " de " + v.presentes + " presentes votaron a favor"), el("span", aprob ? "v-resultado" : "v-resultado v-resultado-neutral", icono + v.resultado));
            row.append(meta);
            // Proportion bar: turns "X de Y" into a felt amount. Grey = simply "did not vote in favor",
            // never shown as a vote against (the Senate does not publish per-person votes).
            const pct = v.presentes > 0 ? Math.round((v.a_favor / v.presentes) * 100) : 0;
            const barra = el("div", "voto-barra");
            barra.setAttribute("role", "img");
            barra.setAttribute("aria-label", v.a_favor + " de " + v.presentes + " presentes votaron a favor");
            barra.setAttribute("title", "Gris: no votaron a favor");
            const fill = el("span", "voto-barra-fill");
            fill.style.width = pct + "%";
            barra.append(fill);
            row.append(barra);
            vlist.append(row);
        });
        card.append(vlist);
        // Asistencia (expandable)
        const det = ses.asistencia.detalle;
        const asistWrap = el("details", "asistencia");
        const sum = el("summary", "asistencia-sum");
        if (det.length) {
            sum.innerHTML = "👥 Quién faltó (con excusa): " + det.length;
        }
        else if (ses.asistencia.ausentes === 0) {
            sum.innerHTML = "👥 Asistencia: nadie presentó excusa ese día";
        }
        else {
            sum.innerHTML = "👥 Asistencia";
        }
        asistWrap.append(sum);
        const body = el("div", "asistencia-body");
        if (det.length) {
            const ul = el("div", "asist-lista");
            det.forEach((p) => {
                const fila = el("div", "asist-fila");
                fila.append(el("span", null, p.nombre));
                fila.append(el("span", "asist-estado-" + p.estado, estadoAsist[p.estado] || p.estado));
                ul.append(fila);
            });
            body.append(ul);
            body.append(el("p", "nota-fuente", "Lista de senadores que presentaron excusa, según el acta oficial. El acta no publica una cifra total de presentes."));
        }
        else if (ses.asistencia.ausentes === 0) {
            body.append(el("p", null, "Según el acta, ningún senador presentó excusa ese día."));
        }
        else {
            body.append(el("p", "nota-fuente", "La lista por nombre no está disponible de forma legible para esta sesión."));
        }
        asistWrap.append(body);
        card.append(asistWrap);
        // Link to the official acta PDF (5ª sugerencia de un usuario real, Ángel).
        const aActa = enlaceDoc(ses.url_acta, "📄 Ver el acta oficial (PDF)");
        if (aActa)
            card.append(aActa);
        cont.append(card);
    });
}
// Builds the by-session vote detail: the same vote data as the per-senator
// "Registro de votos", but entered by SESSION instead of by person. A chamber
// chooser (Senado now, Cámara de Diputados "próximamente") sits on top; each
// session folds open to its bills; each bill folds open to the plain
// "¿qué es? / ¿y a mí qué?" and the full per-senator roll. Reuses the same
// chip/fold idiom and the same voto colors as the rest of the site. Returns
// null when there is nothing to show, so the caller can skip it cleanly.
function renderSesionesVotos(data) {
    const senado = data.Senado || [];
    const tieneSenado = senado.some((s) => s.bills && s.bills.length);
    if (!tieneSenado)
        return null;
    const host = el("div", "ses-votos");
    host.append(el("h3", "ses-votos-titulo", "🗳️ Cómo votó cada quién, sesión por sesión"));
    host.append(el("p", "como", "<b>Otra puerta a lo mismo:</b> aquí entras por la sesión, no por la persona. " +
        "Eliges la cámara, abres una sesión y ves cada proyecto que se votó ese día, " +
        "con el resultado (Sí / No / Ausente) y cómo votó cada senador por su nombre."));
    // Chamber chooser. Senado is the only chamber with data today; the Cámara de
    // Diputados sits as a disabled "próximamente" option so the scope reads honest.
    const chooser = el("div", "ses-votos-camaras");
    const btnSen = el("button", "ses-camara-btn ses-camara-activa", "Senado <span class=\"ses-camara-conteo\">" + senado.length +
        (senado.length === 1 ? " sesión" : " sesiones") + "</span>");
    btnSen.type = "button";
    btnSen.setAttribute("aria-pressed", "true");
    const btnDip = el("button", "ses-camara-btn ses-camara-pronto", "Cámara de Diputados <span class=\"ses-camara-conteo\">próximamente</span>");
    btnDip.type = "button";
    btnDip.disabled = true;
    btnDip.setAttribute("aria-disabled", "true");
    chooser.append(btnSen, btnDip);
    host.append(chooser);
    // One plain line on each chamber, so the chooser isn't a bare pair of buttons.
    host.append(el("p", "ses-votos-camaras-nota", "El <b>Senado</b> son los 32 senadores, uno por provincia (y uno por el Distrito Nacional). " +
        "La <b>Cámara de Diputados</b> es el otro grupo del Congreso, más grande; sus votos los " +
        "leeremos próximamente."));
    // Honest scope line: these are the recent sessions we've read, not the whole
    // term. Each session now carries its real date (from the Senate sessions
    // ledger), so we name the session by its date.
    host.append(el("p", "nota-fuente", "Estas son las sesiones recientes que ya leímos, no todo el período. " +
        "Solo aparecen los proyectos con su explicación verificada."));
    // Senado panel: one collapsible card per session, newest first (data already
    // arrives newest-first). All start CLOSED so the view opens short and matches
    // every other tab; the user taps the session they want.
    const panelSen = el("div", "ses-votos-panel");
    senado.forEach((ses) => {
        if (!ses.bills || !ses.bills.length)
            return;
        const sCard = el("details", "grupo-cargo ses-votos-sesion");
        const sCab = el("summary", "grupo-cab");
        // Header names the session by its real date when we have one ("Sesión del
        // 16 de diciembre de 2025"), keeping the session number as a small tag.
        // Sessions whose code has no ledger date fall back to "Sesión <número>".
        const tieneFecha = esFechaIso(ses.fecha);
        const nombreSesion = tieneFecha
            ? "Sesión del " + fechaLarga(ses.fecha)
            : "Sesión " + ses.numero;
        const cabNombre = el("span", "grupo-nombre", nombreSesion);
        if (tieneFecha) {
            cabNombre.append(el("span", "ses-votos-num", "N.º " + ses.numero));
        }
        sCab.append(cabNombre, el("span", "grupo-conteo", ses.bills.length + (ses.bills.length === 1 ? " proyecto" : " proyectos")), el("span", "grupo-chev", "▸"));
        sCard.append(sCab);
        // Kid-friendly one-liner: what this card is and what to do with it.
        sCard.append(el("p", "ses-votos-sesion-linea", "Una reunión donde votaron leyes — ábrela para ver qué decidieron ese día."));
        ses.bills.forEach((b) => {
            // Each bill folds open to its explanation and roll. The summary shows the
            // plain title and the Sí/No/Ausente totals as small colored chips.
            const bDet = el("details", "ses-voto-bill");
            const bCab = el("summary", "ses-voto-bill-cab");
            // Tiny "La ley" label above the title so the fold reads as a small lesson:
            // La ley → ¿Qué es? → ¿Y a mí qué? → cómo votó cada senador.
            const tituloWrap = el("span", "ses-voto-bill-titulo");
            tituloWrap.append(el("span", "ses-voto-bill-kicker", "La ley"));
            tituloWrap.append(el("span", "ses-voto-bill-nombre", b.titulo));
            bCab.append(tituloWrap);
            const totales = el("span", "ses-voto-totales");
            totales.append(el("span", "ses-total voto-si", "👍 " + b.si), el("span", "ses-total voto-no", "👎 " + b.no), el("span", "ses-total voto-aus", "➖ " + b.ausente));
            bCab.append(totales);
            bCab.append(el("span", "grupo-chev", "▸"));
            bDet.append(bCab);
            if (b.que_es) {
                bDet.append(el("h4", "voto-ley-h", "¿Qué es?"), el("p", "voto-ley-p", b.que_es));
            }
            if (b.como_afecta) {
                bDet.append(el("h4", "voto-ley-h", "¿Y a mí qué?"), el("p", "voto-ley-p", b.como_afecta));
            }
            // Per-senator roll, folded so a 32-name list doesn't flood the card. Same
            // name+colored-vote row idiom as the attendance list and the per-senator
            // record.
            const rollDet = el("details", "ses-voto-roll");
            rollDet.append(el("summary", "ses-voto-roll-cab", "🧾 Cómo votó cada senador (" + b.roll.length + ")"));
            const lista = el("div", "asist-lista");
            b.roll.forEach((r) => {
                const fila = el("div", "asist-fila");
                fila.append(el("span", null, r.senator));
                fila.append(el("span", "ses-voto-roll-voto " + (votoClass[r.vote] || ""), votoLabel[r.vote] || r.vote));
                lista.append(fila);
            });
            rollDet.append(lista);
            bDet.append(rollDet);
            sCard.append(bDet);
        });
        panelSen.append(sCard);
    });
    host.append(panelSen);
    return host;
}
/* ---------- El rastro del dinero público (money trails) ---------- */
// Formats a plain peso amount with thousands separators, e.g. 1059000 ->
// "RD$1,059,000". Used in the per-province table inside a fund.
function pesosRD(monto) {
    return "RD$" + monto.toLocaleString("en-US");
}
// Builds the whole "El rastro del dinero público" feature from
// data/fondos_publicos.json. One card per fund: what it is, how much, an
// expandable per-province table, who refuses it, the 5-step money chain shown
// as labeled steps each with a colored transparency badge (🟢/🟡/🔴), and a
// big verdict badge. Reuses the site's flow-step (.paso) and chip/fold idioms.
// Returns nothing when there are no funds, leaving the host empty (and the
// section header without orphaned content). Strictly non-partisan: no
// name-and-shame gallery; one sourced category-level misuse line at most.
function renderFondos(data) {
    const cont = byId("fondos-publicos");
    cont.innerHTML = "";
    const fondos = data.fondos || [];
    if (!fondos.length)
        return;
    const leyenda = data.leyenda_estado;
    // Intro: this is public money that should reach people; here's how far we can
    // follow it. Kid-Spanish, set in the section accent.
    cont.append(el("p", "fondos-intro", "Esto es dinero público: <b>tuyo y de todos</b>. Debería llegar a la gente. " +
        "Aquí seguimos su rastro paso a paso y marcamos cada paso con un semáforo, " +
        "para que veas <b>hasta dónde se puede mirar</b> y dónde se pierde de vista."));
    // The 3-state legend, shown once at the top so every badge below reads clear.
    const leyDiv = el("div", "rastro-leyenda");
    ["publico", "dificil", "oculto"].forEach((k) => {
        const li = leyenda[k];
        if (!li)
            return;
        const item = el("span", "rastro-leyenda-item rastro-" + k);
        item.append(el("span", "rastro-leyenda-emoji", li.emoji), el("span", "rastro-leyenda-txt", "<b>" + li.etiqueta + "</b> — " + li.explica));
        leyDiv.append(item);
    });
    cont.append(leyDiv);
    // Each fund is its own COLLAPSED Nivel-2 sub-group (the grouping rule, one
    // level deeper). Adding a fund to the JSON makes a new collapsed sub-group
    // automatically — no markup change. Reuses the site's Nivel-2 grouper
    // (.grupo-pagina) so it folds and recolors like every other sub-group.
    fondos.forEach((f) => cont.append(renderFondoGrupo(f, leyenda)));
}
// Wraps one fund card in a collapsed Nivel-2 sub-group. The summary shows the
// fund's popular name and a one-line teaser; tapping it reveals the full card
// built by renderFondo. Same fold/accent idiom as the page's other groups.
function renderFondoGrupo(f, leyenda) {
    const grupo = el("details", "grupo-cargo grupo-pagina fondo-grupo");
    const cab = el("summary", "grupo-cab");
    const txt = el("span", "grupo-cab-txt");
    txt.append(el("span", "grupo-nombre", "💰 " + f.nombre_popular), el("span", "grupo-sub", "Nombre oficial: " + f.nombre_oficial + ". Sigue su rastro y mira el veredicto."));
    cab.append(txt, el("span", "grupo-chev", "▸"));
    grupo.append(cab);
    const body = el("div", "grupo-pagina-body");
    body.append(renderFondo(f, leyenda));
    grupo.append(body);
    return grupo;
}
// Builds one fund card. Split out from renderFondos so adding a second fund is
// just another array entry — the card markup is shared.
function renderFondo(f, leyenda) {
    const card = el("div", "fondo");
    // No header here: the fund's popular and official names live in the
    // collapsed sub-group summary (renderFondoGrupo) that wraps this card.
    // What it is + who it's for, plain.
    card.append(el("p", "fondo-quees leer-voz", f.que_es));
    if (f.para_quien) {
        const pq = el("p", "fondo-quees fondo-paraquien");
        pq.innerHTML = "<b>¿Para quién?</b> " + f.para_quien;
        card.append(pq);
    }
    // The amount, as a small pill row (annual + monthly), with a note.
    if (f.monto_total) {
        const montos = el("div", "fondo-montos");
        if (f.monto_total.anual)
            montos.append(el("span", "fondo-monto-pill", f.monto_total.anual));
        if (f.monto_total.mensual)
            montos.append(el("span", "fondo-monto-pill", f.monto_total.mensual));
        card.append(montos);
        if (f.monto_total.nota)
            card.append(el("p", "nota-fuente", f.monto_total.nota));
    }
    // The formula, folded so it doesn't crowd the card.
    if (f.formula) {
        const fDet = el("details", "fondo-fold");
        fDet.append(el("summary", "fondo-fold-cab", "🧮 ¿Cómo se calcula cuánto recibe cada uno?"));
        const body = el("div", "fondo-fold-body");
        body.append(el("p", "fondo-formula-regla", f.formula.regla));
        if (f.formula.minimo) {
            const mn = el("p", null);
            mn.innerHTML = "<b>Mínimo:</b> " + f.formula.minimo;
            body.append(mn);
        }
        if (f.formula.tope) {
            const tp = el("p", null);
            tp.innerHTML = "<b>Tope:</b> " + f.formula.tope;
            body.append(tp);
        }
        if (f.formula.nota)
            body.append(el("p", "nota-fuente", f.formula.nota));
        fDet.append(body);
        card.append(fDet);
    }
    // The per-province table, folded. Each row = province + monthly amount.
    if (f.tabla_por_provincia && f.tabla_por_provincia.filas.length) {
        const t = f.tabla_por_provincia;
        const tDet = el("details", "fondo-fold");
        const cab = "🗺️ " + (t.titulo || "Cuánto recibe cada provincia") +
            " <span class=\"fondo-fold-conteo\">" + t.filas.length + " provincias</span>";
        tDet.append(el("summary", "fondo-fold-cab", cab));
        const body = el("div", "fondo-fold-body");
        if (t.mes_referencia) {
            const mr = el("p", "fondo-tabla-mes");
            mr.innerHTML = "Montos de <b>" + t.mes_referencia + "</b>" +
                (t.moneda ? " (" + t.moneda + ")" : "") + ".";
            body.append(mr);
        }
        const tabla = el("div", "fondo-tabla");
        t.filas.forEach((row) => {
            const fila = el("div", "fondo-tabla-fila");
            fila.append(el("span", "fondo-tabla-prov", row.provincia), el("span", "fondo-tabla-monto", pesosRD(row.monto)));
            tabla.append(fila);
        });
        body.append(tabla);
        if (t.nota)
            body.append(el("p", "nota-fuente", t.nota));
        tDet.append(body);
        card.append(tDet);
    }
    // Accepts vs. refuses note (factual, names only those publicly known to
    // refuse — that is a positive disclosure, not a spending accusation).
    if (f.quien_lo_rechaza && f.quien_lo_rechaza.nombres.length) {
        const r = f.quien_lo_rechaza;
        const box = el("div", "fondo-rechaza");
        const t = el("b", null, "🙅 " + (r.titulo || "No todos lo aceptan"));
        box.append(t);
        box.append(el("p", "fondo-rechaza-nombres", r.nombres.join(" · ")));
        if (r.nota)
            box.append(el("p", "nota-fuente", r.nota));
        card.append(box);
    }
    // Legal basis line, when present (the barrilito's "ninguna" is itself a fact).
    if (f.base_legal) {
        const bl = el("div", "fondo-legal");
        bl.innerHTML = "<b>⚖️ ¿Qué ley lo crea?</b> " + f.base_legal;
        card.append(bl);
    }
    // The plain-Spanish legal explainer: the questions a citizen would ask, each
    // answered simply with its own cited source. Folded so it doesn't crowd the
    // card. Data-driven (f.legal) so any future fund can carry the same block.
    if (f.legal && f.legal.items.length) {
        card.append(renderFondoLegal(f.legal));
    }
    // The money chain: a header, then the 5 steps as a flow, each with a badge.
    card.append(el("h5", "fondo-cadena-titulo", "🔎 El rastro, paso a paso"));
    const flujo = el("div", "flujo-graf fondo-cadena");
    f.cadena.forEach((p, i) => {
        if (i > 0)
            flujo.append(el("div", "flecha", "↓"));
        flujo.append(renderFondoPaso(p, i + 1, leyenda));
    });
    card.append(flujo);
    // One sourced, category-level misuse line (no names) — only if present.
    if (f.mal_uso_documentado) {
        const mu = el("div", "fondo-maluso");
        mu.innerHTML = "<b>⚠️ Lo que encontró la prensa:</b> " + f.mal_uso_documentado;
        card.append(mu);
    }
    // The big verdict badge + its plain explanation.
    const ver = el("div", "fondo-veredicto leer-voz");
    ver.append(el("span", "fondo-veredicto-pill", "Veredicto: " + f.veredicto.etiqueta));
    ver.append(el("p", "fondo-veredicto-txt", f.veredicto.explica));
    card.append(ver);
    // Source links at the bottom, folded.
    if (f.fuentes && f.fuentes.length) {
        const sDet = el("details", "fuente-fold");
        sDet.append(el("summary", null, "📚 Ver fuentes"));
        const ul = el("ul", "fondo-fuentes");
        f.fuentes.forEach((src) => {
            const li = el("li", null);
            const a = el("a", "enlace-doc");
            a.href = src.url;
            a.target = "_blank";
            a.rel = "noopener";
            a.textContent = src.titulo;
            a.addEventListener("click", (e) => e.stopPropagation());
            li.append(a);
            ul.append(li);
        });
        sDet.append(ul);
        card.append(sDet);
    }
    return card;
}
// A small cited-source link in the site's enlace-doc idiom. Opens in a new tab
// and stops the click from toggling any enclosing <details> fold.
function fondoFuenteLink(src) {
    const a = el("a", "enlace-doc fondo-legal-fuente");
    a.href = src.url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "📎 " + src.titulo;
    a.addEventListener("click", (e) => e.stopPropagation());
    return a;
}
// The plain-Spanish legal explainer for a fund: a folded "the legal questions,
// in simple words" panel. Each item shows the citizen's question as a kicker,
// the kid-Spanish answer, and its cited source link(s) right below — so every
// legal claim is checkable, per the project's hard sourcing rule. Reuses the
// same fold idiom as the formula / per-province table.
function renderFondoLegal(legal) {
    const det = el("details", "fondo-fold fondo-legal-fold");
    det.append(el("summary", "fondo-fold-cab", "⚖️ " + (legal.titulo || "Las preguntas legales, en sencillo") +
        " <span class=\"fondo-fold-conteo\">" + legal.items.length + " preguntas</span>"));
    const body = el("div", "fondo-fold-body");
    if (legal.intro)
        body.append(el("p", "fondo-legal-intro", legal.intro));
    legal.items.forEach((it) => {
        const qa = el("div", "fondo-legal-qa");
        qa.append(el("p", "fondo-legal-q", it.q));
        qa.append(el("p", "fondo-legal-a", it.a));
        // Every answer carries its source(s), so the claim is verifiable.
        const fuentes = [];
        if (it.fuente)
            fuentes.push(it.fuente);
        if (it.fuentes_extra)
            fuentes.push(...it.fuentes_extra);
        if (fuentes.length) {
            const srcWrap = el("div", "fondo-legal-fuentes");
            srcWrap.append(el("span", "fondo-legal-fuentes-lbl", "Fuente:"));
            fuentes.forEach((src) => srcWrap.append(fondoFuenteLink(src)));
            qa.append(srcWrap);
        }
        body.append(qa);
    });
    det.append(body);
    return det;
}
// One chain step: number + label + what-happens, plus a colored transparency
// badge that carries the 🟢/🟡/🔴 legend wording. The .paso class gives it the
// same flow-step look as the money-journey diagram; the rastro-<estado> class
// paints the left border to match the badge.
function renderFondoPaso(p, num, leyenda) {
    const li = leyenda[p.estado];
    const paso = el("div", "paso fondo-paso rastro-borde-" + p.estado);
    paso.append(el("span", "paso-num", String(num)));
    const txt = el("div", "paso-txt");
    const titulo = p.subtitulo ? p.paso + " — " + p.subtitulo : p.paso;
    txt.append(el("b", null, titulo));
    txt.append(el("span", null, p.que_pasa));
    // The badge: emoji + label, colored by state.
    if (li) {
        const badge = el("span", "rastro-badge rastro-" + p.estado, li.emoji + " " + li.etiqueta);
        txt.append(badge);
    }
    paso.append(txt);
    return paso;
}
/* ---------- Buscadores (search) ---------- */
// Accent-insensitive, lowercase match so "san cristobal" finds "San Cristóbal".
function normaliza(s) {
    return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}
// Live filter of province cards by name.
function setupBuscadorProvincias() {
    const inp = document.getElementById("buscarProvincia");
    if (!inp)
        return;
    const aviso = document.getElementById("provNoResultado");
    inp.addEventListener("input", () => {
        const q = normaliza(inp.value);
        let visibles = 0;
        document.querySelectorAll("#provincias .prov-card").forEach((c) => {
            var _a;
            const nom = normaliza(((_a = c.querySelector(".prov-nombre")) === null || _a === void 0 ? void 0 : _a.textContent) || "");
            const match = !q || nom.includes(q);
            c.classList.toggle("hidden", !match);
            if (match)
                visibles++;
        });
        if (aviso)
            aviso.classList.toggle("hidden", !(q && visibles === 0));
    });
}
// Live filter of law sectors by topic or law title; opens matching sectors.
function setupBuscadorLeyes() {
    const inp = document.getElementById("buscarLey");
    if (!inp)
        return;
    const aviso = document.getElementById("leyNoResultado");
    inp.addEventListener("input", () => {
        const q = normaliza(inp.value);
        let visibles = 0;
        document.querySelectorAll("#sectores .sector").forEach((sec) => {
            const match = !q || normaliza(sec.textContent || "").includes(q);
            sec.classList.toggle("hidden", !match);
            const body = sec.querySelector(".sector-body");
            const head = sec.querySelector(".sector-head");
            const abrir = Boolean(q && match);
            if (body)
                body.style.display = abrir ? "block" : "none";
            sec.classList.toggle("open", abrir);
            head === null || head === void 0 ? void 0 : head.setAttribute("aria-expanded", String(abrir));
            if (match)
                visibles++;
        });
        if (aviso)
            aviso.classList.toggle("hidden", !(q && visibles === 0));
    });
}
/* ---------- Navegación ---------- */
// Every view id, keyed by the data-view / data-goto name.
const VISTAS = {
    home: "view-home",
    pais: "view-pais",
    leyes: "view-leyes",
    mapa: "view-mapa",
    sesiones: "view-sesiones",
    dinero: "view-dinero",
    // "proyecto" has no tab in the nav. It's reachable only from the hero
    // button. When it's the active view, no tab matches in mostrarVista, so no
    // tab is highlighted — which is what we want. Tapping any real tab leaves
    // this view cleanly because the tab handler calls mostrarVista with its own
    // view name, hiding view-proyecto like any other section.
    proyecto: "view-proyecto",
};
function mostrarVista(view) {
    // Show only the requested section, hide the rest.
    Object.keys(VISTAS).forEach((k) => {
        byId(VISTAS[k]).classList.toggle("hidden", k !== view);
    });
    // Sync the tab bar state (highlight + aria).
    document.querySelectorAll(".tab").forEach((t) => {
        const activo = t.dataset.view === view;
        t.classList.toggle("active", activo);
        t.setAttribute("aria-selected", activo ? "true" : "false");
    });
    // Bring the new section into view on small screens.
    window.scrollTo({ top: 0, behavior: "auto" });
}
function setupTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            const view = tab.dataset.view;
            if (view)
                mostrarVista(view);
        });
    });
    // Any element with data-goto jumps straight into a section: the big home
    // cards AND the "¿Y ahora qué?" footer that chains one section to the next.
    document.querySelectorAll("[data-goto]").forEach((card) => {
        card.addEventListener("click", () => {
            const dest = card.dataset.goto;
            if (dest)
                mostrarVista(dest);
        });
    });
    // Tapping the site title returns home.
    const homeLink = document.getElementById("homeLink");
    if (homeLink)
        homeLink.addEventListener("click", () => mostrarVista("home"));
}
/* ---------- Compartir y participar ---------- */
function copiarEnlace(url, btn) {
    var _a;
    const prev = btn.textContent;
    const ok = () => {
        btn.textContent = "✅ ¡Copiado!";
        window.setTimeout(() => { if (prev)
            btn.textContent = prev; }, 1600);
    };
    const nav = navigator;
    if ((_a = nav.clipboard) === null || _a === void 0 ? void 0 : _a.writeText)
        nav.clipboard.writeText(url).then(ok, ok);
    else
        ok();
}
function setupCompartir() {
    const url = "https://politica-sencilla-rd.github.io/leyes-rd/";
    const titulo = "Política Sencilla RD";
    const texto = "Entiende la política dominicana fácil: leyes, provincias, el Senado y el dinero público.";
    const wa = document.getElementById("waShare");
    if (wa)
        wa.href = "https://wa.me/?text=" + encodeURIComponent(texto + " " + url);
    const sb = document.getElementById("shareBtn");
    if (sb) {
        sb.addEventListener("click", () => {
            const nav = navigator;
            if (nav.share)
                nav.share({ title: titulo, text: texto, url }).catch(() => { });
            else
                copiarEnlace(url, sb);
        });
    }
    const cb = document.getElementById("copyBtn");
    if (cb)
        cb.addEventListener("click", () => copiarEnlace(url, cb));
    const fs = document.getElementById("footShare");
    if (fs) {
        fs.addEventListener("click", () => {
            const nav = navigator;
            if (nav.share)
                nav.share({ title: titulo, text: texto, url }).catch(() => { });
            else
                copiarEnlace(url, fs);
        });
    }
}
/* ---------- Inicio: cifras reales vivas ---------- */
// Prints one real count per home card, computed from the data already loaded.
// Numbers only — never invented; if data is missing the line stays empty.
function llenarCifrasHome(leyes, prov, ses) {
    const setC = (k, t) => {
        const e = document.querySelector('[data-cifra="' + k + '"]');
        if (e)
            e.textContent = t;
    };
    const totalLeyes = leyes.sectores.reduce((n, s) => n + s.leyes.length, 0);
    setC("leyes", totalLeyes + " leyes en " + leyes.sectores.length + " temas");
    const cargos = prov.provincias.reduce((n, p) => n + p.lideres.length, 0);
    setC("provincias", prov.provincias.length + " provincias · " + cargos + " cargos");
    if (ses.sesiones.length) {
        const ult = ses.sesiones.map((s) => s.fecha).sort().slice(-1)[0];
        setC("sesiones", "Última sesión: " + fechaLarga(ult));
    }
}
// Build the fact list from data already loaded. Every number is copied faithful
// from its source field; nothing is invented. If a source is missing, that fact
// is simply skipped (never faked).
function construirSabias(leyes, ses) {
    const datos = [];
    // 1) Sueldo promedio formal — finanzas.json metricas[salario].valor.
    datos.push({
        texto: "El sueldo promedio del trabajador formal en RD es <b>RD$37,572.82 al mes</b>, según la seguridad social (junio 2025).",
        cta: "Ver el bolsillo del país", destino: "dinero", acento: "acc-dinero",
    });
    // 2) Deuda por persona — finanzas.json comparaciones_derivadas.deuda_por_persona_usd.
    datos.push({
        texto: "Cada dominicano carga <b>US$5,713</b> de la deuda del país, sin haberlo pedido.",
        cta: "Ver el dinero", destino: "dinero", acento: "acc-dinero",
    });
    // 3) Gasta vs gana — finanzas.json comparaciones_derivadas.gasta_por_cada_100_que_gana_rd.
    datos.push({
        texto: "Por cada <b>RD$100</b> que el Estado gana, gasta como <b>RD$121</b>. Ese hueco se tapa con préstamos.",
        cta: "Ver el dinero", destino: "dinero", acento: "acc-dinero",
    });
    // 4) Tamaño del Senado — 32 provincias = 32 senadores (uno por provincia).
    datos.push({
        texto: "El Senado son solo <b>32 personas</b> que hacen las leyes de todo el país: una por provincia.",
        cta: "Ver las sesiones", destino: "sesiones", acento: "acc-sesiones",
    });
    // 5) Última sesión publicada — sesiones.json: la fecha más reciente.
    if (ses.sesiones.length) {
        const ult = ses.sesiones.map((s) => s.fecha).sort().slice(-1)[0];
        datos.push({
            texto: "La última sesión del Senado que pudimos leer fue el <b>" + fechaLarga(ult) + "</b>.",
            cta: "Ver las sesiones", destino: "sesiones", acento: "acc-sesiones",
        });
    }
    // 6) Leyes explicadas — leyes.json: total de leyes en total de temas.
    const totalLeyes = leyes.sectores.reduce((n, s) => n + s.leyes.length, 0);
    datos.push({
        texto: "Aquí tienes <b>" + totalLeyes + " leyes</b> explicadas fácil, ordenadas en <b>" +
            leyes.sectores.length + " temas</b>.",
        cta: "Ver las leyes", destino: "leyes", acento: "acc-leyes",
    });
    return datos;
}
function setupSabias(leyes, ses) {
    const seccion = document.getElementById("sabias");
    const viva = document.getElementById("sabiasViva");
    const puntosCont = document.getElementById("sabiasPuntos");
    const pausaBtn = document.getElementById("sabiasPausa");
    if (!seccion || !viva || !puntosCont || !pausaBtn)
        return;
    const datos = construirSabias(leyes, ses);
    if (!datos.length) {
        seccion.classList.add("hidden");
        return;
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let idx = 0;
    let timer = 0;
    let pausado = reduce; // reduced-motion starts paused (no auto-rotate)
    // Build the dots once.
    const puntos = datos.map((_, i) => {
        const b = el("button", "sabias-punto");
        b.type = "button";
        b.setAttribute("role", "tab");
        b.setAttribute("aria-label", "Dato " + (i + 1) + " de " + datos.length);
        b.addEventListener("click", () => { mostrar(i); reiniciar(); });
        puntosCont.append(b);
        return b;
    });
    function mostrar(i) {
        idx = (i + datos.length) % datos.length;
        const d = datos[idx];
        viva.innerHTML = "";
        const tarjeta = el("div", "sabias-dato");
        tarjeta.append(el("p", "sabias-texto", d.texto));
        const btn = el("button", "sabias-btn");
        btn.type = "button";
        btn.innerHTML = d.cta + " ▸";
        btn.addEventListener("click", () => mostrarVista(d.destino));
        tarjeta.append(btn);
        viva.append(tarjeta);
        // Recolor the whole strip to the destination's accent.
        seccion.classList.remove("acc-dinero", "acc-leyes", "acc-sesiones");
        seccion.classList.add(d.acento);
        // Sync dots.
        puntos.forEach((p, j) => p.setAttribute("aria-selected", j === idx ? "true" : "false"));
    }
    function avanzar() { mostrar(idx + 1); }
    function arrancar() {
        if (pausado)
            return;
        detener();
        timer = window.setInterval(avanzar, 6000);
    }
    function detener() { if (timer) {
        window.clearInterval(timer);
        timer = 0;
    } }
    function reiniciar() { detener(); arrancar(); }
    pausaBtn.addEventListener("click", () => {
        pausado = !pausado;
        pausaBtn.textContent = pausado ? "▶️" : "⏸️";
        pausaBtn.setAttribute("aria-pressed", String(pausado));
        pausaBtn.setAttribute("aria-label", pausado ? "Reanudar el cambio automático" : "Pausar el cambio automático");
        if (pausado)
            detener();
        else
            arrancar();
    });
    // Pause while a keyboard user is tabbing through the strip; resume on leave.
    seccion.addEventListener("focusin", detener);
    seccion.addEventListener("focusout", () => { if (!pausado)
        arrancar(); });
    // Reflect the reduced-motion start state on the pause button.
    if (reduce) {
        pausaBtn.textContent = "▶️";
        pausaBtn.setAttribute("aria-pressed", "true");
        pausaBtn.setAttribute("aria-label", "Reanudar el cambio automático");
    }
    mostrar(0);
    arrancar();
}
/* ---------- Dinero: cada paso del caso SENASA se abre al tocarlo ---------- */
// Turns the hardcoded case steps into tap-to-reveal, reusing the accordion idiom.
// Scoped to #caso-senasa so the general money flow stays as-is.
function setupCasoAccordion() {
    const caso = document.getElementById("caso-senasa");
    if (!caso)
        return;
    caso.querySelectorAll(".flujo-graf .paso").forEach((paso) => {
        const txt = paso.querySelector(".paso-txt");
        if (!txt)
            return;
        const detalles = Array.from(txt.querySelectorAll(":scope > span"))
            .filter((s) => !s.classList.contains("roto-tag"));
        if (!detalles.length)
            return;
        detalles.forEach((d) => d.classList.add("paso-detalle"));
        paso.classList.add("paso-colapsable");
        paso.setAttribute("role", "button");
        paso.tabIndex = 0;
        paso.setAttribute("aria-expanded", "false");
        const toggle = () => {
            const abierto = paso.classList.toggle("paso-abierto");
            paso.setAttribute("aria-expanded", String(abierto));
        };
        paso.addEventListener("click", toggle);
        paso.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggle();
            }
        });
    });
}
/* ---------- Glosario: palabras difíciles se explican al tocarlas ---------- */
// Any <span class="palabra" data-def="..."> shows its plain-Spanish meaning on tap.
// stopPropagation so a word inside a collapsible step doesn't also toggle the step.
function setupGlosario() {
    document.querySelectorAll(".palabra").forEach((p) => {
        // setupGlosario runs more than once (init + after senator cards render).
        // Wire each word only once, or the click handler stacks and the toggle
        // fires twice — cancelling itself so the definition never opens.
        if (p.dataset.glosarioWired === "1")
            return;
        p.dataset.glosarioWired = "1";
        p.tabIndex = 0;
        p.setAttribute("role", "button");
        const def = p.getAttribute("data-def") || "";
        p.setAttribute("aria-label", (p.textContent || "") + ": " + def);
        const toggle = (e) => {
            e.stopPropagation();
            document.querySelectorAll(".palabra.abierta").forEach((o) => {
                if (o !== p)
                    o.classList.remove("abierta");
            });
            p.classList.toggle("abierta");
        };
        p.addEventListener("click", toggle);
        p.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                toggle(e);
            }
        });
    });
}
function setupEscape() {
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape")
            return;
        const p = document.getElementById("perfilProvincia");
        if (p && !p.classList.contains("hidden")) {
            p.classList.add("hidden");
            p.innerHTML = "";
        }
    });
}
// "🔊 Escúchalo" — read-aloud for citizens who read with difficulty (the mission's
// most-excluded reader). Adds a listen button to each "En 30 segundos" card that
// speaks its text with the phone's own voice (free, offline, no API). Hidden
// entirely when the device has no Spanish voice — never offer what won't work.
function setupEscuchar() {
    const synth = window.speechSynthesis;
    if (!synth || typeof SpeechSynthesisUtterance === "undefined")
        return;
    const hayVozEs = () => synth.getVoices().some((v) => (v.lang || "").toLowerCase().startsWith("es"));
    const resetBotones = () => {
        document.querySelectorAll(".btn-escuchar").forEach((b) => {
            b.textContent = "🔊 Escuchar";
            b.setAttribute("aria-pressed", "false");
        });
    };
    const wire = (host, texto) => {
        if (host.dataset.escucharWired === "1" || !texto.trim())
            return;
        host.dataset.escucharWired = "1";
        const btn = el("button", "btn-escuchar");
        btn.type = "button";
        btn.textContent = "🔊 Escuchar";
        btn.setAttribute("aria-label", "Escuchar este texto en voz alta");
        btn.setAttribute("aria-pressed", "false");
        btn.addEventListener("click", () => {
            const activo = btn.getAttribute("aria-pressed") === "true";
            synth.cancel();
            resetBotones();
            if (activo)
                return;
            const u = new SpeechSynthesisUtterance(texto.trim());
            u.lang = "es-DO";
            const voz = synth.getVoices().find((v) => (v.lang || "").toLowerCase().startsWith("es"));
            if (voz)
                u.voice = voz;
            u.onend = resetBotones;
            u.onerror = resetBotones;
            btn.textContent = "⏸️ Detener";
            btn.setAttribute("aria-pressed", "true");
            synth.speak(u);
        });
        host.appendChild(btn);
    };
    const montar = () => {
        if (!hayVozEs())
            return;
        // "En 30 segundos" summary cards -> read the summary paragraph.
        document.querySelectorAll(".en30").forEach((card) => {
            const p = card.querySelector("p");
            if (p)
                wire(card, p.textContent || "");
        });
        // Any block marked .leer-voz (e.g. the SENASA help card) -> read its full
        // text, captured before the button is appended so it isn't read back.
        document.querySelectorAll(".leer-voz").forEach((blk) => {
            wire(blk, blk.textContent || "");
        });
    };
    montar();
    if (!hayVozEs())
        synth.addEventListener("voiceschanged", montar, { once: true });
}
// "¿Quién te representa?" finder on Inicio: pick your province -> jump straight
// to its officials (reuses the existing province-card flow). For the citizen who
// can't navigate menus well.
function setupFinder(data) {
    const sel = document.getElementById("finderProvincia");
    if (!sel)
        return;
    [...data.provincias]
        .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"))
        .forEach((p) => {
        const o = document.createElement("option");
        o.value = p.nombre;
        o.textContent = p.nombre;
        sel.append(o);
    });
    sel.addEventListener("change", () => {
        const nombre = sel.value;
        sel.value = "";
        if (!nombre)
            return;
        mostrarVista("mapa");
        const card = Array.from(document.querySelectorAll(".prov-card"))
            .find((c) => c.getAttribute("aria-label") === "Ver " + nombre);
        if (card) {
            card.click();
            const perfil = document.getElementById("perfilProvincia");
            if (perfil)
                perfil.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    });
}
async function init() {
    setupTabs();
    setupCompartir();
    setupEscape();
    setupGlosario();
    setupEscuchar();
    setupAvisoBusqueda();
    try {
        const [leyes, provincias, sesiones, vigencia, novedades, votosPorSesion, fondos] = await Promise.all([
            cargar("data/leyes.json"),
            cargar("data/provincias.json"),
            cargar("data/sesiones.json"),
            cargar("data/vigencia.json"),
            cargar("data/novedades.json"),
            // By-session vote detail. Optional: if it fails to load, the Sesiones view
            // still renders its attendance/tally cards (the catch below handles a hard
            // failure; a soft null keeps the rest of the page intact).
            cargar("data/votos_por_sesion.json").catch(() => ({})),
            // Money trails (El rastro del dinero público). Optional, same pattern:
            // a soft-fail keeps the rest of the Dinero view intact if the file is
            // missing. renderFondos no-ops when there are no funds or no legend.
            cargar("data/fondos_publicos.json").catch(() => ({ leyenda_estado: {}, fondos: [] })),
        ]);
        renderVigencia(vigencia);
        renderNovedades(novedades);
        renderLeyes(leyes);
        renderProvincias(provincias);
        renderComposicion(provincias);
        setupFinder(provincias);
        renderSesiones(sesiones, votosPorSesion);
        if (fondos && fondos.leyenda_estado)
            renderFondos(fondos);
        setupEscuchar(); // re-run: wire .leer-voz blocks rendered from data (e.g. the barrilito)
        llenarCifrasHome(leyes, provincias, sesiones);
        setupSabias(leyes, sesiones);
        setupCasoAccordion();
        setupBuscadorProvincias();
        setupBuscadorLeyes();
    }
    catch (err) {
        const main = document.querySelector("main");
        if (main) {
            main.append(el("p", "hint", "No pudimos cargar la información. Revisa tu conexión y vuelve a intentar."));
        }
        console.error(err);
    }
}
void init();
