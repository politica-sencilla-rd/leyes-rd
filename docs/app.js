"use strict";
function ico(nombre) {
    return '<span class="ico ico-' + nombre + '" aria-hidden="true"></span> ';
}
const SECTOR_ICO = {
    "⚖️": "scale", "💼": "briefcase", "🏥": "hospital", "💧": "droplet", "🚌": "bus",
    "📶": "antena", "🏠": "home", "🌱": "plant", "🎭": "masks", "🌍": "world",
    "📄": "leyes",
};
const estadoLabel = {
    aprobada: ico("check") + "Aprobada",
    votando: ico("hourglass") + "En votación",
    rechazada: ico("x") + "Rechazada",
    vencida: ico("reloj") + "Se venció sin votarse",
    retirada: ico("minus") + "Retirada",
};
const votoLabel = { si: ico("thumb-up") + "Sí", no: ico("thumb-down") + "No", ausente: ico("minus") + "Ausente" };
const votoClass = { si: "voto-si", no: "voto-no", ausente: "voto-aus" };
const MOSTRAR_VOTOS_POR_SENADOR = false;
const AVISO_VOTOS_SENADO = "El Senado no publica cómo votó cada senador. Estamos revisando nuestra lista contra las actas oficiales antes de mostrarla.";
const URL_SIL_CAMARA = "https://www.diputadosrd.gob.do/sil";
function avisoVotosCamara() {
    const p = el("p", "nota-fuente", "La Cámara de Diputados sí publica cómo votó cada diputado, con su nombre, en su sistema oficial. ");
    const a = enlaceDoc(URL_SIL_CAMARA, "Ver los votos en el SIL de la Cámara");
    if (a)
        p.append(a);
    return p;
}
function avisoVotosSenado() {
    return el("p", "nota-fuente", AVISO_VOTOS_SENADO + " Los totales de cada votación (cuántos votaron a favor) sí salen en el acta oficial: los ves en Sesiones.");
}
const DATA_VERSION = "20260924d";
async function cargar(path) {
    const sep = path.indexOf("?") >= 0 ? "&" : "?";
    const res = await fetch(path + sep + "v=" + DATA_VERSION);
    if (!res.ok)
        throw new Error("No se pudo cargar " + path);
    return (await res.json());
}
let RESUMENES = { resumenes: {}, sin_resumen: {} };
let ESTADO = { fuentes: {} };
function esc(t) {
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function urlSegura(u) {
    return typeof u === "string" && /^https?:\/\//i.test(u.trim()) ? u : "";
}
function resumenDe(id) {
    const r = RESUMENES.resumenes[id];
    return r && r.estado === "verificado" && r.checks_total > 0 && r.checks_pasados === r.checks_total ? r : null;
}
function fechaCorta(iso) {
    const p = iso.split("-");
    const mes = MESES[Number(p[1]) - 1] || p[1];
    return esc(p.length === 2 ? mes + " " + p[0] : Number(p[2]) + " " + mes.slice(0, 3) + " " + p[0]);
}
function etiquetaResumen(r) {
    const p = el("p", "resumen-auto");
    p.append(el("span", null, ico("info") + "Resumen automático, revisado contra el documento oficial"));
    const a = enlaceDoc(r.fuente_url, "Ver documento oficial ↗");
    if (a)
        p.append(document.createTextNode(" · "), a);
    const como = el("a", "como-link", "¿Cómo lo hacemos?");
    como.href = "#como-lo-hacemos";
    como.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        mostrarVista("proyecto");
        const d = document.getElementById("como-lo-hacemos");
        if (d) {
            d.open = true;
            d.scrollIntoView({ block: "start" });
        }
    });
    p.append(document.createTextNode(" · "), como);
    return p;
}
function resumenPendiente(id, url) {
    const falla = RESUMENES.sin_resumen && RESUMENES.sin_resumen[id];
    const p = el("p", "resumen-pendiente", falla ? "Resumen automático no disponible. Lee el documento oficial." : "Resumen en preparación.");
    const a = enlaceDoc((falla && falla.fuente_url) || url, "Documento oficial ↗");
    if (a)
        p.append(document.createTextNode(" "), a);
    return p;
}
function lineaDatosAl(clave, manual) {
    const f = ESTADO.fuentes[clave];
    const partes = [];
    if (f && f.datos_al)
        partes.push("Datos al <b>" + fechaCorta(f.datos_al) + "</b>");
    else if (manual)
        partes.push("Datos al <b>" + fechaCorta(manual) + "</b>");
    if (!partes.length)
        return null;
    if (f && f.revisado_el)
        partes.push("revisado el " + fechaCorta(f.revisado_el));
    if (f && (f.estado === "roto" || f.estado === "sin_respuesta"))
        partes.push("la fuente no respondió en la última revisión");
    const p = el("p", "datos-al", ico("reloj") + partes.join(" · ") + (f && f.retraso ? ". " + esc(f.retraso) : ""));
    if (f && f.url_fuente) {
        const a = enlaceDoc(f.url_fuente, "Fuente ↗");
        if (a)
            p.append(document.createTextNode(" "), a);
    }
    return p;
}
function estadoVigencia(l) {
    if (!l.vigencia_fecha)
        return "ver_articulo";
    const hoy = new Date();
    const iso = hoy.getFullYear() + "-" + String(hoy.getMonth() + 1).padStart(2, "0") + "-" + String(hoy.getDate()).padStart(2, "0");
    return l.vigencia_fecha <= iso ? "vigencia" : "pronto";
}
function renderFinanzasAuto(fin) {
    const hayAuto = (fin.metricas || []).some((m) => m.auto);
    (fin.metricas || []).forEach((m) => {
        const a = m.auto;
        if (!a)
            return;
        document.querySelectorAll('[data-metrica="' + m.id + '"]').forEach((card) => {
            const cifra = card.querySelector(".salud-cifra");
            if (cifra)
                cifra.innerHTML = esc(a.valor_texto) + (a.unidad ? ' <span class="salud-unidad">' + esc(a.unidad) + "</span>" : "");
            const nota = card.querySelector(".salud-nota");
            if (nota)
                nota.textContent = a.texto;
            const trend = card.querySelector(".salud-trend");
            if (trend) {
                trend.className = "salud-trend " + (a.anterior_num === undefined ? "" : a.valor_num > a.anterior_num ? "sube" : a.valor_num < a.anterior_num ? "baja" : "");
                trend.textContent = a.comparacion;
            }
            const fuente = card.querySelector(".nota-fuente");
            if (fuente)
                fuente.textContent = a.fuente + " Datos al " + a.periodo + ". Lo actualiza un robot desde el archivo oficial.";
            const link = card.querySelector("a.enlace-doc");
            if (link && urlSegura(a.url_pagina))
                link.href = a.url_pagina;
        });
        document.querySelectorAll('[data-auto="' + m.id + '"]').forEach((e) => { e.textContent = a.valor_texto; });
    });
    const host = document.getElementById("datosAlDinero");
    if (host && hayAuto) {
        const fechas = (fin.metricas || []).filter((m) => m.auto).map((m) => m.auto.periodo_iso).sort();
        host.innerHTML = ico("reloj") + "Cada tarjeta dice su propia fecha. La más vieja es de <b>" + fechaCorta(fechas[0]) +
            "</b> y la más nueva de <b>" + fechaCorta(fechas[fechas.length - 1]) + "</b>: cada oficina publica a su ritmo.";
        host.classList.remove("hidden");
    }
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
function enlaceDoc(url, texto) {
    if (!url || !urlSegura(url))
        return null;
    const a = el("a", "enlace-doc");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = texto;
    a.addEventListener("click", (e) => e.stopPropagation());
    return a;
}
function marcarBusqueda(a, numero, etiqueta) {
    a.dataset.busqueda = "1";
    if (numero)
        a.dataset.numero = numero;
    a.dataset.numeroEtiqueta = etiqueta;
}
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
        if ((_a = nav.clipboard) === null || _a === void 0 ? void 0 : _a.writeText)
            nav.clipboard.writeText(txt).then(ok, ok);
        else
            ok();
    });
    irBtn.addEventListener("click", () => { if (dlg.open)
        dlg.close(); });
    const quedarme = document.getElementById("avisoQuedarme");
    if (quedarme)
        quedarme.addEventListener("click", () => { if (dlg.open)
            dlg.close(); });
    dlg.addEventListener("click", (e) => {
        if (e.target === dlg)
            dlg.close();
    });
}
function partirFuenteUrl(fuente) {
    const m = fuente.match(/^(.*?)\s*\((https?:\/\/[^\s)]+)\)\s*$/);
    if (m)
        return { texto: m[1].trim(), url: m[2] };
    return { texto: fuente, url: null };
}
function renderLeyes(data) {
    const cont = byId("sectores");
    cont.innerHTML = "";
    const dAuto = lineaDatosAl("leyes_sil");
    if (dAuto)
        cont.append(dAuto);
    if (data.datos_al_manual && data.sectores.some((s) => s.leyes.some((l) => !l.auto))) {
        cont.append(el("p", "datos-al", ico("pencil") + "Las leyes explicadas a mano tienen datos al <b>" +
            fechaCorta(data.datos_al_manual) + "</b>. Las marcadas «automático» las revisa un robot cada semana."));
    }
    data.sectores.forEach((sec) => {
        const card = el("div", "sector");
        const head = el("div", "sector-head");
        const txt = el("div", "sector-txt");
        txt.append(el("h3", "sector-title", esc(sec.nombre)), el("span", "sector-count", sec.leyes.length + (sec.leyes.length === 1 ? " ley" : " leyes")));
        head.append(el("span", "sector-emoji", SECTOR_ICO[sec.emoji] ? ico(SECTOR_ICO[sec.emoji]) : esc(sec.emoji)), txt, el("span", "sector-chev", "▸"));
        const body = el("div", "sector-body");
        body.style.display = "none";
        sec.leyes.forEach((ley) => body.append(renderLey(ley, data.busqueda_oficial)));
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
function numeroIniciativa(titulo) {
    const m = titulo.match(/Iniciativa\s+([\w-]+)/i);
    return m ? m[1] : null;
}
function renderLey(ley, busqueda) {
    const wrap = el("div", "ley");
    const res = ley.auto && ley.id ? resumenDe("sil-" + ley.id) : null;
    wrap.append(el("p", "ley-titulo", esc(ley.auto && res && res.titulo_facil ? res.titulo_facil : ley.titulo)));
    wrap.append(el("span", "ley-estado estado-" + ley.estado, estadoLabel.hasOwnProperty(ley.estado) ? estadoLabel[ley.estado] : esc(ley.estado)));
    if (ley.auto)
        wrap.append(el("span", "ley-auto", "automático"));
    if (ley.camara) {
        wrap.append(el("span", "ley-camara", ico("banco") + "Cámara de Diputados"));
    }
    const det = el("div", "ley-detalle");
    if (ley.auto) {
        if (res)
            det.append(etiquetaResumen(res));
        else
            det.append(resumenPendiente("sil-" + ley.id, ley.url_oficial));
        det.append(el("h4", null, "Nombre oficial"), el("p", "ley-oficial", esc(ley.titulo_oficial || ley.titulo)));
        det.append(el("p", "nota-fuente", "En el SIL de la Cámara: <b>" + esc(ley.estado_sil || "") + "</b>" +
            (ley.datos_al ? " · datos al " + fechaCorta(ley.datos_al) : "") + "."));
    }
    else if (ley.que_es) {
        det.append(el("h4", null, "¿Qué es?"), el("p", null, esc(ley.que_es)));
    }
    if (ley.te_afecta) {
        det.append(el("h4", null, "¿Y a mí qué?"), el("p", "te-afecta leer-voz", esc(ley.te_afecta)));
    }
    const sinMotivo = !ley.por_que || /^razón no indicada/i.test(ley.por_que);
    if (ley.auto) {
    }
    else if (sinMotivo) {
        det.append(el("p", "nota-fuente", "El Senado no publicó el motivo. Cuando lo publique, te lo contamos aquí."));
    }
    else {
        det.append(el("h4", null, "¿Por qué se propuso?"), el("p", null, esc(ley.por_que || "")));
    }
    if (ley.votos && ley.votos.length && (ley.camara || MOSTRAR_VOTOS_POR_SENADOR)) {
        det.append(el("h4", null, "¿Quién votó?"));
        const votos = el("div", "votos");
        ley.votos.forEach((v) => {
            const fila = el("div", "voto-fila");
            fila.append(el("span", null, esc(v.nombre)));
            fila.append(el("span", votoClass[v.voto] || "", votoLabel.hasOwnProperty(v.voto) ? votoLabel[v.voto] : esc(v.voto)));
            votos.append(fila);
        });
        det.append(votos);
    }
    else if (ley.camara) {
        det.append(avisoVotosCamara());
    }
    else {
        det.append(el("p", "nota-fuente", "El Senado no publica cómo votó cada senador; solo publica los totales de cada votación."));
    }
    const url = ley.camara ? busqueda === null || busqueda === void 0 ? void 0 : busqueda.camara : busqueda === null || busqueda === void 0 ? void 0 : busqueda.senado;
    if (url) {
        const num = ley.id || numeroIniciativa(ley.titulo);
        const sistema = ley.camara ? "el SIL de la Cámara" : "el sistema del Senado";
        const texto = num
            ? "Búscala en el sistema oficial: iniciativa " + num
            : "Búscala en " + sistema + " (sistema oficial)";
        const a = enlaceDoc(url, texto);
        if (a)
            marcarBusqueda(a, num, "el número de la iniciativa");
        if (a)
            det.append(a);
    }
    wrap.append(det);
    wrap.setAttribute("role", "button");
    wrap.tabIndex = 0;
    wrap.setAttribute("aria-expanded", "false");
    wrap.addEventListener("click", (e) => {
        e.stopPropagation();
        if (e.target.closest(".ley-detalle"))
            return;
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
function conPunto(t) {
    return t.replace(/\.+$/, "") + ".";
}
function renderVigenciaLey(ley) {
    const card = el("details", "vig-ley");
    const cab = el("summary", "vig-ley-cab");
    const est = estadoVigencia(ley);
    cab.append(el("span", "vig-ley-num", "Ley " + esc(ley.numero)), el("span", "vig-ley-titulo", esc(ley.titulo)), el("span", "vig-ley-fecha", ley.vigencia_fecha
        ? (est === "pronto" ? ico("calendar") + "Entra: " : ico("check") + "Desde: ") + fechaLarga(ley.vigencia_fecha)
        : ico("info") + "Fecha: lee su artículo"), el("span", "vig-ley-chev", "▸"));
    card.append(cab);
    const det = el("div", "vig-ley-det");
    if (ley.que_es) {
        det.append(el("h4", null, "¿Qué es?"), el("p", null, esc(ley.que_es)));
    }
    else {
        const r = resumenDe("ley-" + ley.numero);
        if (r && r.que_es)
            det.append(el("h4", null, "¿Qué es?"), el("p", null, esc(r.que_es)), etiquetaResumen(r));
        else
            det.append(el("h4", null, "¿Qué es?"), resumenPendiente("ley-" + ley.numero, ley.url_documento));
    }
    det.append(el("h4", null, est === "pronto" ? "¿Cuándo empieza?" : est === "vigencia" ? "¿Desde cuándo rige?" : "¿Cuándo empieza?"), el("p", "vig-ley-cuando", esc(ley.vigencia_texto)));
    if (ley.vigencia_cita)
        det.append(el("p", "vig-ley-cita", "Lo que dice la ley: «" + esc(ley.vigencia_cita) + "»"));
    det.append(el("p", "vig-ley-meta", "El Presidente la firmó (la promulgó) el <b>" + fechaLarga(ley.promulgada) +
        "</b> y se publicó en la Gaceta Oficial " +
        (/^\d+$/.test(ley.gaceta) ? "núm. <b>" + ley.gaceta + "</b>" : "(" + esc(ley.gaceta) + ")") + "."));
    det.append(el("p", "nota-fuente", "Fuente: " + esc(conPunto(ley.fuente))));
    if (ley.url_documento) {
        const a = enlaceDoc(ley.url_documento, "Leer la ley completa (documento oficial)");
        if (a)
            det.append(a);
    }
    else if (ley.url_busqueda) {
        const a = enlaceDoc(ley.url_busqueda, "Búscala en el portal oficial: Ley " + ley.numero);
        if (a)
            marcarBusqueda(a, ley.numero, "el número de la ley");
        if (a)
            det.append(a);
    }
    card.append(det);
    return card;
}
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
    const intro = el("div", "como vig-intro");
    intro.innerHTML =
        "<b>" + ico("calendar") + "¿Cuáles leyes están por empezar?</b>" +
            "Que el Congreso apruebe una ley no quiere decir que ya te aplique. " +
            "Primero el Presidente la firma (la " +
            "<span class=\"palabra\" data-def=\"Promulgar es el acto en que el Presidente firma una ley ya aprobada por el Congreso para ordenar que se cumpla y se publique.\">promulga</span>) " +
            "y se publica en la " +
            "<span class=\"palabra\" data-def=\"La Gaceta Oficial es el periódico del Estado donde se publican las leyes para que sean válidas. Una ley no rige hasta que sale ahí.\">Gaceta Oficial</span>. " +
            "Recién entonces empieza su " +
            "<span class=\"palabra\" data-def=\"La vigencia es el momento desde el cual una ley ya manda y debes cumplirla. Algunas rigen de una vez; otras esperan unos meses.\">vigencia</span>: " +
            "la fecha desde la cual ya manda.";
    host.append(intro);
    const dv = lineaDatosAl("vigencia_consultoria");
    if (dv)
        host.append(dv);
    const vigentes = leyes.filter((l) => estadoVigencia(l) === "vigencia");
    const pronto = leyes.filter((l) => estadoVigencia(l) === "pronto");
    const verArticulo = leyes.filter((l) => estadoVigencia(l) === "ver_articulo");
    const grupo = (titulo, sub, arr, cls) => {
        if (!arr.length)
            return;
        const wrap = el("details", "grupo-cargo vig-grupo " + cls);
        const cab = el("summary", "grupo-cab vig-cab");
        cab.append(el("span", "grupo-nombre", titulo), el("span", "grupo-conteo", arr.length === 1 ? "1 ley" : arr.length + " leyes"), el("span", "grupo-chev", "▸"));
        wrap.append(cab);
        wrap.append(el("p", "vig-grupo-sub", sub));
        const ordenadas = [...arr].sort((a, b) => (b.vigencia_fecha || b.promulgada).localeCompare(a.vigencia_fecha || a.promulgada));
        ordenadas.forEach((l) => wrap.append(renderVigenciaLey(l)));
        host.append(wrap);
    };
    grupo(ico("reloj") + "Entran pronto", "Ya firmadas, pero su fecha de empezar todavía no llega. Apunta el día.", pronto, "vig-grupo-pronto");
    grupo(ico("check") + "Ya en vigencia (nuevas)", "Leyes recientes que ya mandan. Estas reglas ya te aplican.", vigentes, "vig-grupo-vigencia");
    grupo(ico("info") + "Firmadas: la fecha la dice su artículo", "El robot no pudo calcular la fecha con seguridad. Abre la ley para leer su propio artículo.", verArticulo, "vig-grupo-articulo");
    if (data.regla_por_defecto) {
        const r = data.regla_por_defecto;
        const det = el("details", "vig-regla");
        det.append(el("summary", "vig-regla-cab", ico("ayuda") + esc(r.titulo)));
        const body = el("div", "vig-regla-body");
        body.append(el("p", null, esc(r.texto)));
        body.append(el("p", "nota-fuente", "Fuente: " + esc(conPunto(r.fuente))));
        const aRegla = enlaceDoc(r.url, "Ver el documento oficial (PDF)");
        if (aRegla)
            body.append(aRegla);
        det.append(body);
        host.append(det);
    }
    setupGlosario();
}
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
        li.append(el("span", "novedad-fecha", fechaLarga(n.fecha)), el("span", "novedad-texto", esc(n.texto)));
        if (n.aporte)
            li.append(el("span", "novedad-aporte", aporteHtml(n.aporte)));
        host.append(li);
    });
}
function aporteHtml(a) {
    if (a.indexOf("💡") === 0)
        return ico("bulb") + esc(a.slice(2).trim());
    if (a.indexOf("🔧") === 0)
        return ico("tool") + esc(a.slice(2).trim());
    return esc(a);
}
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
function retratoSenador(provincia, l) {
    if (!l.cargo.toLowerCase().startsWith("senador"))
        return null;
    return RETRATOS_SENADORES[provincia + "||" + l.nombre] || null;
}
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
function suave() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}
function renderLider(l, provincia, conFuncion = true) {
    const block = el("div", "lider");
    const cab = el("div", "lider-cab");
    const retratoSen = retratoSenador(provincia, l);
    const retratoDip = retratoSen ? null : retratoDiputado(provincia, l);
    const retrato = retratoSen || retratoDip;
    const carpeta = retratoSen ? "img/senadores/" : "img/diputados/";
    if (retrato) {
        const img = el("img", "avatar avatar-foto");
        img.src = carpeta + retrato;
        img.alt = "Retrato oficial de " + l.nombre;
        img.width = 56;
        img.height = 56;
        img.loading = "lazy";
        img.decoding = "async";
        img.addEventListener("error", () => {
            const fb = el("span", "avatar", esc(iniciales(l.nombre)));
            img.replaceWith(fb);
        });
        cab.append(img);
    }
    else {
        cab.append(el("span", "avatar", esc(iniciales(l.nombre))));
    }
    const ident = el("div", "lider-ident");
    const tienePartido = Boolean(l.partido && l.partido.trim() !== "—");
    ident.append(el("p", "lider-nombre", "<b>" + esc(l.nombre) + "</b>" +
        (tienePartido ? "<span class='partido-chip'>" + esc(l.partido) + "</span>" : "")));
    ident.append(el("p", "lider-cargo", esc(l.cargo)));
    cab.append(ident);
    block.append(cab);
    if (esElecto(l.cargo)) {
        block.append(el("p", "lider-dato", ico("calendar") + "En el cargo: 2024–2028 (elegido por voto)"));
    }
    const fn = conFuncion ? funcionDeCargo(l.cargo) : "";
    if (fn)
        block.append(el("p", "lider-funcion", fn));
    if (l.resumen)
        block.append(el("p", null, esc(l.resumen)));
    const chips = el("div", "lider-chips");
    const datoChip = (icono, resumen, detalle) => {
        const d = el("details", "dato-chip");
        d.append(el("summary", "dato-chip-cab", ico(icono) + '<span class="dato-chip-txt">' + resumen + "</span>"), el("p", "dato-chip-det", detalle));
        return d;
    };
    if (l.asistencia && l.asistencia.total > 0) {
        const a = l.asistencia;
        chips.append(datoChip("calendar", "<b>" + esc(String(a.presentes)) + "/" + esc(String(a.total)) + "</b> sesiones", "Asistencia: estuvo en <b>" + esc(String(a.presentes)) + " de " + esc(String(a.total)) +
            "</b> sesiones del Pleno (" + esc(a.periodo) + ")." +
            (a.datos_al ? " Datos al " + fechaCorta(a.datos_al) + "." : "") + (a.nota ? " " + esc(a.nota) : "")));
    }
    if (l.cargo_hasta) {
        chips.append(el("p", "nota-fuente", ico("info") + "Según el SIL de la Cámara, estuvo en el cargo hasta el " + fechaLarga(l.cargo_hasta) + "."));
    }
    if (l.comisiones && l.comisiones.length) {
        chips.append(datoChip("folders", "<b>" + l.comisiones.length + "</b> comisiones", "Trabaja en " + l.comisiones.length + " comisiones: " + esc(l.comisiones.join(", ")) + "."));
    }
    if (typeof l.iniciativas_propuestas === "number") {
        const n = l.iniciativas_propuestas;
        chips.append(datoChip("pencil", "<b>" + n + "</b> " + (n === 1 ? "iniciativa" : "iniciativas"), "Ha propuesto o copropuesto <b>" + n + "</b> " +
            (n === 1 ? "iniciativa" : "iniciativas") + " en este período."));
    }
    if (l.votaciones_pleno && l.votaciones_pleno.total > 0) {
        const vp = l.votaciones_pleno;
        chips.append(datoChip("voto", "Votó en <b>" + vp.emitidas + "/" + vp.total + "</b>", "En las últimas <b>" + vp.total + "</b> votaciones del Pleno que registramos (sesiones " +
            "recientes), emitió su voto en <b>" + vp.emitidas + "</b>. En las demás se ausentó o no votó. " +
            "Algunas votaciones son de procedimiento interno; esto muestra si participa en las votaciones, " +
            "no cómo votó cada ley. Dato público de la Cámara de Diputados."));
    }
    const sueldo = sueldoDeCargo(l.cargo) || l.sueldo || null;
    if (sueldo) {
        chips.append(datoChip("coin", "Sueldo del cargo: <b>" + esc(sueldo.monto) + "/mes</b>", "Es el salario mensual oficial que paga el Estado por ocupar el cargo. " +
            "No es dinero de otras fuentes ni su patrimonio.<br>" +
            "Monto: <b>" + esc(sueldo.monto) + " al mes</b>, según la " + esc(sueldo.fuente) +
            " de " + esc(sueldo.mes) + ". Lo pagan los impuestos de todos."));
    }
    if (chips.children.length)
        block.append(chips);
    const cargoLower = l.cargo.toLowerCase();
    if (cargoLower.startsWith("gobernador")) {
        block.append(el("p", "nota-fuente", "El gobernador no hace leyes ni vota en el Congreso, por eso no tiene asistencia ni iniciativas. Lo nombra la Presidencia, y su sueldo sale en la nómina del Ministerio de Interior y Policía."));
    }
    else if (cargoLower.startsWith("alcalde")) {
        const nota = l.sueldo
            ? "El alcalde trabaja en el ayuntamiento, no en el Congreso, por eso no tiene asistencia ni iniciativas de leyes. Su sueldo sale en la nómina de su propio ayuntamiento."
            : "El alcalde trabaja en el ayuntamiento, no en el Congreso, por eso no tiene asistencia ni iniciativas de leyes. Su sueldo lo publica cada ayuntamiento; aún estamos reuniendo esas nóminas.";
        block.append(el("p", "nota-fuente", nota));
    }
    if (esLegislador(l.cargo)) {
        const esSenador = l.cargo.toLowerCase().startsWith("senador");
        if (esSenador && MOSTRAR_VOTOS_POR_SENADOR && l.votos && l.votos.length) {
            block.append(renderRegistroVotos(l));
        }
        else if (esSenador) {
            block.append(el("p", "lider-subtit", ico("voto") + "Cómo votó"), avisoVotosSenado());
        }
        else {
            block.append(el("p", "lider-subtit", ico("voto") + "Cómo votó"), avisoVotosCamara());
        }
    }
    return block;
}
function renderRegistroVotos(l) {
    const votos = l.votos;
    const totalLeyes = votos.reduce((n, s) => n + (s.leyes ? s.leyes.length : 0), 0);
    const card = el("details", "grupo-cargo votos-registro");
    const cab = el("summary", "grupo-cab");
    cab.append(el("span", "grupo-nombre", ico("voto") + "Registro de votos"), el("span", "grupo-conteo", totalLeyes + (totalLeyes === 1 ? " voto" : " votos")), el("span", "grupo-chev", "▸"));
    card.append(cab);
    const body = el("div", "votos-registro-body");
    const nota = l.votos_nota ||
        "Estas son las sesiones recientes del Senado que ya leímos, no todo su período.";
    body.append(el("p", "nota-fuente", esc(nota)));
    votos.forEach((ses) => {
        if (!ses.leyes || !ses.leyes.length)
            return;
        const sDet = el("details", "votos-sesion");
        const sCab = el("summary", "votos-sesion-cab");
        sCab.append(el("span", "votos-sesion-nom", "Sesión " + esc(String(ses.sesion))), el("span", "votos-sesion-conteo", ses.leyes.length + (ses.leyes.length === 1 ? " ley" : " leyes")), el("span", "grupo-chev", "▸"));
        sDet.append(sCab);
        ses.leyes.forEach((ley) => {
            const wrap = el("div", "voto-ley");
            const top = el("div", "voto-ley-top");
            top.append(el("span", "voto-ley-titulo", esc(ley.titulo)));
            top.append(el("span", "voto-ley-voto " + (votoClass[ley.voto] || ""), votoLabel.hasOwnProperty(ley.voto) ? votoLabel[ley.voto] : esc(ley.voto)));
            wrap.append(top);
            if (ley.que_es) {
                wrap.append(el("h4", "voto-ley-h", "¿Qué es?"), el("p", "voto-ley-p", esc(ley.que_es)));
            }
            if (ley.como_afecta) {
                wrap.append(el("h4", "voto-ley-h", "¿Y a mí qué?"), el("p", "voto-ley-p", esc(ley.como_afecta)));
            }
            sDet.append(wrap);
        });
        body.append(sDet);
    });
    card.append(body);
    return card;
}
function renderRegidoresCard(prov) {
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
    let html = "<b>" + ico("silla") + "¿Y los regidores?</b> En cada ayuntamiento, además del alcalde, hay un grupo de " +
        "<span class=\"palabra\" data-def=\"Los regidores son el grupo de personas, elegidas por voto, que forman el concejo del ayuntamiento. Aprueban el presupuesto del pueblo, dictan las normas locales y vigilan al alcalde. Son como los concejales del pueblo.\">regidores</span>: " +
        "son los concejales del pueblo. Aprueban el presupuesto del municipio, dictan las normas locales y vigilan al alcalde. " +
        "Cada municipio elige varios por voto, según cuánta gente vive en él.";
    const r = prov.regidores;
    let fuenteTotalLink = null;
    if (r && typeof r.total === "number") {
        let textoFuente = r.fuente_total || "";
        if (r.fuente_total) {
            const partida = partirFuenteUrl(r.fuente_total);
            textoFuente = partida.texto;
            fuenteTotalLink = enlaceDoc(partida.url || undefined, "Ver la lista oficial (JCE)");
        }
        html += "<br><br>En esta provincia hay <b>" + r.total + " regidores</b> en total" +
            (textoFuente ? ", según " + esc(textoFuente) : "") + ".";
    }
    else {
        html += "<br><br><span class=\"nota-fuente\">Cuántos hay en total en esta provincia: aún estamos confirmando la cifra con datos oficiales de la JCE.</span>";
    }
    card.innerHTML = html;
    if (fuenteTotalLink)
        card.append(fuenteTotalLink);
    const wrap = el("div", "regidores-body");
    wrap.append(card);
    if (r && r.municipios && r.municipios.length) {
        r.municipios.forEach((m) => {
            if (!m.lista || !m.lista.length)
                return;
            const det = el("details", "regidores-lista");
            det.append(el("summary", "regidores-municipio", "<span>" + ico("silla") + "Regidores de " + esc(m.municipio) + "</span><span class=\"grupo-conteo\">" + m.lista.length + "</span>"));
            m.lista.forEach((rg) => {
                const fila = el("p", "regidor-fila");
                fila.innerHTML = esc(rg.nombre) + " <span class='partido-chip'>" + esc(rg.partido) + "</span>";
                det.append(fila);
            });
            if (m.fuente_lista) {
                const partida = partirFuenteUrl(m.fuente_lista);
                det.append(el("p", "nota-fuente", "Fuente: " + esc(partida.texto) + "."));
                const a = enlaceDoc(partida.url || undefined, "Ver la lista oficial (JCE)");
                if (a)
                    det.append(a);
            }
            wrap.append(det);
        });
    }
    return wrap;
}
function cerrarPerfil(desplazar = true) {
    const perfil = byId("perfilProvincia");
    perfil.classList.add("hidden");
    perfil.innerHTML = "";
    const vista = byId("view-mapa");
    if (!vista.classList.contains("con-perfil"))
        return;
    vista.classList.remove("con-perfil");
    if (desplazar)
        byId("provincias").scrollIntoView({ block: "start", behavior: suave() });
}
function renderProvincias(data) {
    const grid = el("div", "prov-grid");
    const perfil = byId("perfilProvincia");
    const ordenadas = [...data.provincias].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
    ordenadas.forEach((prov) => {
        const c = el("div", "prov-card");
        c.append(el("span", "prov-nombre", esc(prov.nombre)));
        const n = prov.lideres.length;
        c.append(el("span", "prov-count", n + (n === 1 ? " cargo" : " cargos")));
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
            byId("view-mapa").classList.add("con-perfil");
            const cerrar = el("button", "perfil-cerrar", ico("arriba") + "Todas las provincias");
            cerrar.type = "button";
            cerrar.addEventListener("click", () => cerrarPerfil());
            const perfilTitulo = el("h3", null, esc(prov.nombre));
            perfilTitulo.tabIndex = -1;
            const perfilCab = el("div", "perfil-cab");
            perfilCab.append(perfilTitulo, cerrar);
            perfil.append(perfilCab);
            const grupos = {};
            prov.lideres.forEach((l) => {
                const k = grupoDeCargo(l.cargo);
                (grupos[k] = grupos[k] || []).push(l);
            });
            ORDEN_GRUPOS.forEach((k) => {
                const arr = grupos[k];
                if (!arr || !arr.length)
                    return;
                const etq = ETIQUETA_GRUPO[k] || "Otros";
                const grupoCard = el("details", "grupo-cargo");
                const cab = el("summary", "grupo-cab");
                cab.append(el("span", "grupo-nombre", etq), el("span", "grupo-conteo", arr.length === 1 ? "1 persona" : arr.length + " personas"), el("span", "grupo-chev", "▸"));
                grupoCard.append(cab);
                const funciones = Array.from(new Set(arr.map((l) => funcionDeCargo(l.cargo))));
                const unaFuncion = funciones.length === 1 && funciones[0] !== "";
                if (unaFuncion)
                    grupoCard.append(el("p", "lider-funcion grupo-funcion", funciones[0]));
                arr.forEach((l) => {
                    const block = renderLider(l, prov.nombre, !unaFuncion);
                    const cabLider = block.querySelector(".lider-cab");
                    if (arr.length > 3 && cabLider) {
                        const fold = el("details", "lider-fold");
                        const sumLider = el("summary");
                        sumLider.append(cabLider);
                        fold.append(sumLider, block);
                        grupoCard.append(fold);
                    }
                    else {
                        grupoCard.append(block);
                    }
                });
                perfil.append(grupoCard);
            });
            if (!grupos["alcalde"]) {
                perfil.append(el("p", "nota-fuente", "Alcaldes: aún por añadir. Estamos completando esta provincia con datos oficiales. " +
                    "¿Conoces a tu alcalde? <a href=\"https://github.com/politica-sencilla-rd/leyes-rd/issues/new/choose\" target=\"_blank\" rel=\"noopener\">Ayúdanos a completarlo</a>."));
            }
            perfil.append(renderRegidoresCard(prov));
            setupGlosario();
            perfil.style.setProperty("--cab-h", perfilCab.offsetHeight + "px");
            perfil.scrollIntoView({ behavior: suave(), block: "start" });
            perfilTitulo.focus({ preventScroll: true });
        });
        grid.append(c);
    });
    const host = byId("provincias");
    host.innerHTML = "";
    const comoLeer = el("details", "transp como-leer");
    comoLeer.innerHTML =
        "<summary>" + ico("info") + "¿Cómo leer la ficha de un senador?</summary><div class=\"transp-body\">Al abrir una provincia y tocar a su senador verás cuatro datos nuevos:<br>" +
            ico("calendar") + "<b>Asistencia</b>: a cuántas reuniones del " +
            "<span class=\"palabra\" data-def=\"La reunión grande donde todos los senadores se juntan a votar las leyes.\">Pleno</span> " +
            "fue, de las que pudimos contar. Ir es su trabajo.<br>" +
            ico("folders") + "<b>Comisiones</b>: una " +
            "<span class=\"palabra\" data-def=\"Un grupo pequeño de senadores que estudia un tema (salud, educación, dinero) antes de que todos voten.\">comisión</span> " +
            "es un equipo que estudia un tema a fondo. Trabajar en varias es normal.<br>" +
            ico("pencil") + "<b>Iniciativas</b>: cuántas " +
            "<span class=\"palabra\" data-def=\"Una idea de ley o resolución que el senador presenta, solo o junto a otros, para que el Senado la estudie.\">propuestas de ley</span> " +
            "ha presentado, solo o con otros.<br>" +
            ico("coin") + "<b>Sueldo del cargo</b>: el salario mensual oficial que paga el Estado por ocupar el puesto. " +
            "No es dinero de otras fuentes ni su patrimonio. Sale de la " +
            "<span class=\"palabra\" data-def=\"La lista pública de lo que cobra cada empleado del Estado. La ley obliga a publicarla cada mes.\">nómina</span> " +
            "pública. Lo pagan los impuestos de todos nosotros.</div>";
    host.append(grid, comoLeer);
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
        .sort((a, b) => b.asientos - a.asientos || a.partido.localeCompare(b.partido));
}
const COLOR_PARTIDO = {
    PRM: "#1a4ed8",
    FP: "#7b2ff7",
    PLD: "#1f9d57",
    PRSC: "#e0651a",
    DXC: "#0fb5c4",
    PPG: "#d8261a",
    PLR: "#c01b8a",
};
const COLOR_OTROS = "#565e6e";
function colorDePartido(partido) {
    return COLOR_PARTIDO[partido] || COLOR_OTROS;
}
function renderCamara(nombre, total, conteo) {
    const wrap = el("div", "camara-comp");
    wrap.append(el("p", "camara-titulo", "<b>" + nombre + "</b> <span class=\"camara-total\">" + total + " asientos</span>"));
    const grandes = conteo.filter((c) => c.asientos > 2);
    const pequenos = conteo.filter((c) => c.asientos <= 2);
    const otrosTotal = pequenos.reduce((n, c) => n + c.asientos, 0);
    const segmentos = [...grandes];
    if (otrosTotal > 0)
        segmentos.push({ partido: "Otros", asientos: otrosTotal });
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
    const leyenda = el("div", "comp-leyenda");
    segmentos.forEach((s) => {
        const chip = el("span", "comp-chip");
        let punto;
        if (s.partido === "Otros") {
            punto = el("span", "comp-punto-multi");
            pequenos.forEach((p) => {
                const d = el("span", "comp-punto");
                d.style.background = colorDePartido(p.partido);
                punto.append(d);
            });
        }
        else {
            punto = el("span", "comp-punto");
            punto.style.background = colorDePartido(s.partido);
        }
        chip.append(punto, el("span", "comp-chip-txt", esc(s.partido) + " " + s.asientos));
        leyenda.append(chip);
    });
    wrap.append(leyenda);
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
        wrap.append(el("p", "comp-clave", "El <b>" + esc(lider.partido) + "</b> tiene <b>" + lider.asientos + " de " + total + "</b> " + sustantivo + cola));
    }
    const det = el("details", "comp-detalle");
    det.append(el("summary", "comp-detalle-cab", "Ver el detalle por partido"));
    conteo.forEach((c) => {
        const fila = el("p", "comp-detalle-fila");
        const punto = el("span", "comp-punto");
        punto.style.background = colorDePartido(c.partido);
        fila.append(punto, el("span", null, esc(c.partido) + ": " + c.asientos +
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
const MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
function fechaLarga(iso) {
    const parts = iso.split("-");
    if (parts.length !== 3)
        return esc(iso);
    const y = parts[0];
    const m = Number(parts[1]) - 1;
    const d = Number(parts[2]);
    const mes = MESES[m] || parts[1];
    return esc(d + " de " + mes + " de " + y);
}
function esFechaIso(s) {
    return /^\d{4}-\d{2}-\d{2}$/.test(s);
}
const estadoAsist = {
    presente: ico("check") + "Presente",
    ausente: ico("minus") + "Ausente",
    excusado: ico("pencil") + "Excusado",
};
function renderSesiones(data, votosPorSesion) {
    const cont = byId("sesiones");
    cont.innerHTML = "";
    const leyenda = el("details", "transp ses-leyenda");
    leyenda.innerHTML =
        "<summary>" + ico("leyes") + "¿Qué es primera y segunda discusión?</summary><div class=\"transp-body\"><p>" +
            "Una ley se vota <b>dos veces</b> en el Senado: la primera discusión y la segunda. " +
            "Si gana las dos, sigue su camino para ser ley. Las resoluciones (homenajes, peticiones) se deciden en una sola votación: <b>única discusión</b>. " +
            "<b>Unanimidad</b> = todos los presentes dijeron que sí.</p></div>";
    cont.append(leyenda);
    if (data.sesiones.length) {
        const fechas = data.sesiones.map((s) => s.fecha).sort();
        const ultima = fechas[fechas.length - 1];
        const cab = el("div", "ses-lista-cab");
        cab.append(el("h3", "ses-lista-titulo", "Sesiones del Senado"), el("p", "ses-lista-meta", data.sesiones.length + " sesiones · de la más reciente a la más antigua · última: " + fechaLarga(ultima)));
        const dal = lineaDatosAl("senado_actas");
        if (dal)
            cab.append(dal);
        cont.append(cab);
    }
    if (MOSTRAR_VOTOS_POR_SENADOR && votosPorSesion) {
        const detalle = renderSesionesVotos(votosPorSesion);
        if (detalle)
            cont.append(detalle);
    }
    else {
        const aviso = el("div", "aviso-pausa");
        aviso.append(el("b", null, ico("pausa") + "¿Cómo votó cada senador?"));
        aviso.append(el("p", null, AVISO_VOTOS_SENADO +
            " Abajo ves los totales de cada votación, sacados del acta oficial del Senado."));
        aviso.append(avisoVotosCamara());
        cont.append(aviso);
    }
    data.sesiones.forEach((ses) => {
        if (ses.estado === "no_procesada") {
            const c = el("div", "sesion sesion-no-leida");
            c.append(el("p", "sesion-head", '<span class="sesion-fecha">' + fechaLarga(ses.fecha) + '</span><span class="sesion-acta">Acta ' + esc(ses.acta) + "</span>"));
            c.append(el("p", "nota-fuente", "El robot no pudo leer esta acta completa, así que no mostramos sus números. Léela en el documento oficial."));
            const a = enlaceDoc(ses.url_acta, "Ver el acta oficial (PDF)");
            if (a)
                c.append(a);
            cont.append(c);
            return;
        }
        const card = el("details", "sesion");
        const head = el("summary", "sesion-head");
        head.append(el("span", "sesion-fecha", fechaLarga(ses.fecha)), el("span", "sesion-conteo", ses.votaciones.length + " votaciones"), el("span", "sesion-acta", "Acta " + esc(ses.acta)), el("span", "sesion-chev", "▸"));
        card.append(head);
        const vlist = el("div", "votaciones");
        ses.votaciones.forEach((v) => {
            const row = el("div", "votacion");
            const auto = v.titulo_facil ? null : resumenDe("senado-" + v.iniciativa);
            const facil = esc(v.titulo_facil || (auto && auto.titulo_facil ? auto.titulo_facil : ""));
            if (facil) {
                row.append(el("p", "votacion-titulo", facil));
                if (auto)
                    row.append(etiquetaResumen(auto));
                const oficial = el("details", "oficial");
                oficial.append(el("summary", null, ico("leyes") + "Ver nombre oficial"), el("p", "votacion-titulo-oficial", esc(v.titulo)));
                row.append(oficial);
            }
            else {
                row.append(el("p", "votacion-titulo", esc(v.titulo)));
                if (ses.auto)
                    row.append(el("p", "resumen-pendiente", "Título fácil en preparación: arriba va el nombre oficial."));
            }
            const meta = el("div", "votacion-meta");
            const aprob = /^aprob/i.test(v.resultado);
            const icono = aprob ? ico("check") : "•&nbsp;";
            const conteo = el("span", "v-conteo", "<b>" + esc(String(v.a_favor)) + " de " + esc(String(v.presentes)) + "</b> presentes votaron a favor");
            const pct = v.presentes > 0 ? Math.round((v.a_favor / v.presentes) * 100) : 0;
            const barra = el("div", "voto-barra");
            barra.setAttribute("role", "img");
            barra.setAttribute("aria-label", v.a_favor + " de " + v.presentes + " presentes votaron a favor");
            barra.setAttribute("title", "Gris: no votaron a favor");
            const fill = el("span", "voto-barra-fill");
            fill.style.width = pct + "%";
            barra.append(fill);
            meta.append(conteo, barra, el("span", aprob ? "v-resultado" : "v-resultado v-resultado-neutral", icono + esc(v.resultado)), el("span", "v-iniciativa", "Iniciativa " + esc(v.iniciativa) + (v.fuente ? " · " + esc(v.fuente) : "")));
            row.append(meta);
            vlist.append(row);
        });
        card.append(vlist);
        if (ses.notas_fuente && ses.notas_fuente.length) {
            const notas = el("div", "notas-fuente");
            notas.append(el("p", null, ico("alerta") + "<b>Lo que dejamos fuera y por qué</b>"));
            ses.notas_fuente.forEach((n) => notas.append(el("p", "nota-fuente", esc(n))));
            card.append(notas);
        }
        const det = ses.asistencia.detalle;
        if (!det.length && ses.asistencia.ausentes === 0) {
            card.append(el("p", "asistencia-nula", ico("users") + "Según el acta, ningún senador presentó excusa ese día."));
        }
        else {
            const asistWrap = el("details", "asistencia");
            const sum = el("summary", "asistencia-sum");
            if (det.length) {
                sum.innerHTML = ico("users") + "Quién faltó (con excusa): " + det.length;
            }
            else {
                sum.innerHTML = ico("users") + "Asistencia";
            }
            asistWrap.append(sum);
            const body = el("div", "asistencia-body");
            if (det.length) {
                const ul = el("div", "asist-lista");
                det.forEach((p) => {
                    const fila = el("div", "asist-fila");
                    fila.append(el("span", null, esc(p.nombre)));
                    fila.append(el("span", "asist-estado-" + p.estado, estadoAsist.hasOwnProperty(p.estado) ? estadoAsist[p.estado] : esc(p.estado)));
                    ul.append(fila);
                });
                body.append(ul);
                body.append(el("p", "nota-fuente", ses.asistencia.presentes !== null && ses.asistencia.presentes !== undefined
                    ? "Lista de senadores ausentes, según el acta oficial. Presentes en el último pase de lista: <b>" + esc(String(ses.asistencia.presentes)) + "</b>."
                    : "Lista de senadores que presentaron excusa, según el acta oficial. El acta no publica una cifra total de presentes."));
            }
            else {
                body.append(el("p", "nota-fuente", "La lista por nombre no está disponible de forma legible para esta sesión."));
            }
            asistWrap.append(body);
            card.append(asistWrap);
        }
        const aActa = enlaceDoc(ses.url_acta, "Ver el acta oficial (PDF)");
        if (aActa)
            card.append(aActa);
        const cerrar = el("button", "ses-cerrar", "Cerrar esta sesión");
        cerrar.type = "button";
        cerrar.addEventListener("click", () => { card.open = false; head.scrollIntoView({ block: "nearest" }); });
        card.append(cerrar);
        cont.append(card);
    });
}
function renderSesionesVotos(data) {
    const senado = data.Senado || [];
    const tieneSenado = senado.some((s) => s.bills && s.bills.length);
    if (!tieneSenado)
        return null;
    const host = el("div", "ses-votos");
    host.append(el("h3", "ses-votos-titulo", ico("voto") + "Cómo votó cada quién, sesión por sesión"));
    host.append(el("p", "como", "<b>Otra puerta a lo mismo:</b> aquí entras por la sesión, no por la persona. " +
        "Eliges la cámara, abres una sesión y ves cada proyecto que se votó ese día, " +
        "con el resultado (Sí / No / Ausente) y cómo votó cada senador por su nombre."));
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
    host.append(el("p", "ses-votos-camaras-nota", "El <b>Senado</b> son los 32 senadores, uno por provincia (y uno por el Distrito Nacional). " +
        "La <b>Cámara de Diputados</b> es el otro grupo del Congreso, más grande; sus votos los " +
        "leeremos próximamente."));
    host.append(el("p", "nota-fuente", "Estas son las sesiones recientes que ya leímos, no todo el período. " +
        "Solo aparecen los proyectos con su explicación verificada."));
    const panelSen = el("div", "ses-votos-panel");
    senado.forEach((ses) => {
        if (!ses.bills || !ses.bills.length)
            return;
        const sCard = el("details", "grupo-cargo ses-votos-sesion");
        const sCab = el("summary", "grupo-cab");
        const tieneFecha = esFechaIso(ses.fecha);
        const nombreSesion = tieneFecha
            ? "Sesión del " + fechaLarga(ses.fecha)
            : "Sesión " + esc(String(ses.numero));
        const cabNombre = el("span", "grupo-nombre", nombreSesion);
        if (tieneFecha) {
            cabNombre.append(el("span", "ses-votos-num", "N.º " + esc(String(ses.numero))));
        }
        sCab.append(cabNombre, el("span", "grupo-conteo", ses.bills.length + (ses.bills.length === 1 ? " proyecto" : " proyectos")), el("span", "grupo-chev", "▸"));
        sCard.append(sCab);
        sCard.append(el("p", "ses-votos-sesion-linea", "Una reunión donde votaron leyes — ábrela para ver qué decidieron ese día."));
        ses.bills.forEach((b) => {
            const bDet = el("details", "ses-voto-bill");
            const bCab = el("summary", "ses-voto-bill-cab");
            const tituloWrap = el("span", "ses-voto-bill-titulo");
            tituloWrap.append(el("span", "ses-voto-bill-kicker", "La ley"));
            tituloWrap.append(el("span", "ses-voto-bill-nombre", esc(b.titulo)));
            bCab.append(tituloWrap);
            const totales = el("span", "ses-voto-totales");
            totales.append(el("span", "ses-total voto-si", ico("thumb-up") + b.si), el("span", "ses-total voto-no", ico("thumb-down") + b.no), el("span", "ses-total voto-aus", ico("minus") + b.ausente));
            bCab.append(totales);
            bCab.append(el("span", "grupo-chev", "▸"));
            bDet.append(bCab);
            if (b.que_es) {
                bDet.append(el("h4", "voto-ley-h", "¿Qué es?"), el("p", "voto-ley-p", esc(b.que_es)));
            }
            if (b.como_afecta) {
                bDet.append(el("h4", "voto-ley-h", "¿Y a mí qué?"), el("p", "voto-ley-p", esc(b.como_afecta)));
            }
            const rollDet = el("details", "ses-voto-roll");
            rollDet.append(el("summary", "ses-voto-roll-cab", ico("users") + "Cómo votó cada senador (" + b.roll.length + ")"));
            const lista = el("div", "asist-lista");
            b.roll.forEach((r) => {
                const fila = el("div", "asist-fila");
                fila.append(el("span", null, esc(r.senator)));
                fila.append(el("span", "ses-voto-roll-voto " + (votoClass[r.vote] || ""), votoLabel.hasOwnProperty(r.vote) ? votoLabel[r.vote] : esc(r.vote)));
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
function pesosRD(monto) {
    return "RD$" + monto.toLocaleString("en-US");
}
function setupDineroFolds() {
    document.querySelectorAll("#view-dinero > .grupo-pagina").forEach((d) => {
        d.addEventListener("toggle", () => {
            const sum = d.querySelector("summary");
            if (!d.open && sum && sum.getBoundingClientRect().top < 0) {
                sum.scrollIntoView({ block: "start", behavior: suave() });
            }
        });
    });
}
function renderFondos(data) {
    const cont = byId("fondos-publicos");
    cont.innerHTML = "";
    const fondos = data.fondos || [];
    if (!fondos.length)
        return;
    const leyenda = data.leyenda_estado;
    cont.append(el("p", "fondos-intro", "Esto es dinero público: <b>tuyo y de todos</b>. Debería llegar a la gente. " +
        "Aquí seguimos su rastro paso a paso y marcamos cada paso con un semáforo, " +
        "para que veas <b>hasta dónde se puede mirar</b> y dónde se pierde de vista."));
    const leyDiv = el("div", "rastro-leyenda");
    ["publico", "dificil", "oculto"].forEach((k) => {
        const li = leyenda[k];
        if (!li)
            return;
        const item = el("span", "rastro-leyenda-item rastro-" + k);
        item.append(el("span", "rastro-leyenda-emoji", '<span class="rastro-punto" aria-hidden="true"></span>'), el("span", "rastro-leyenda-txt", "<b>" + esc(li.etiqueta) + "</b> — " + esc(li.explica)));
        leyDiv.append(item);
    });
    cont.append(leyDiv);
    fondos.forEach((f) => {
        const g = renderFondoGrupo(f, leyenda);
        if (fondos.length === 1)
            g.open = true;
        cont.append(g);
    });
}
function renderFondoGrupo(f, leyenda) {
    const grupo = el("details", "grupo-cargo grupo-pagina fondo-grupo");
    const cab = el("summary", "grupo-cab");
    const txt = el("span", "grupo-cab-txt");
    txt.append(el("span", "grupo-nombre", ico("coin") + esc(f.nombre_popular)), el("span", "grupo-sub", "Nombre oficial: " + esc(f.nombre_oficial) + ". Sigue su rastro y mira el veredicto."));
    cab.append(txt, el("span", "grupo-chev", "▸"));
    grupo.append(cab);
    const body = el("div", "grupo-pagina-body");
    body.append(renderFondo(f, leyenda));
    grupo.append(body);
    return grupo;
}
function renderFondo(f, leyenda) {
    const card = el("div", "fondo");
    card.append(el("p", "fondo-quees leer-voz", esc(f.que_es)));
    if (f.para_quien) {
        const pq = el("p", "fondo-quees fondo-paraquien");
        pq.innerHTML = "<b>¿Para quién?</b> " + esc(f.para_quien);
        card.append(pq);
    }
    if (f.monto_total) {
        const montos = el("div", "fondo-montos");
        if (f.monto_total.anual)
            montos.append(el("span", "fondo-monto-pill", esc(f.monto_total.anual)));
        if (f.monto_total.mensual)
            montos.append(el("span", "fondo-monto-pill", esc(f.monto_total.mensual)));
        card.append(montos);
        if (f.monto_total.nota)
            card.append(el("p", "nota-fuente", esc(f.monto_total.nota)));
    }
    const ver = el("div", "fondo-veredicto leer-voz");
    ver.append(el("span", "fondo-veredicto-kicker", "Veredicto"), " ", el("strong", "fondo-veredicto-etiqueta", esc(f.veredicto.etiqueta)));
    ver.append(el("p", "fondo-veredicto-txt", esc(f.veredicto.explica)));
    card.append(ver);
    card.append(el("h5", "fondo-cadena-titulo", ico("buscar") + "El rastro, paso a paso"));
    const flujo = el("div", "flujo-graf fondo-cadena");
    f.cadena.forEach((p, i) => {
        if (i > 0)
            flujo.append(el("div", "flecha", "↓"));
        flujo.append(renderFondoPaso(p, i + 1, leyenda));
    });
    card.append(flujo);
    if (f.mal_uso_documentado) {
        const mu = el("div", "fondo-maluso");
        mu.innerHTML = "<b>" + ico("alerta") + "Lo que encontró la prensa:</b> " + esc(f.mal_uso_documentado);
        card.append(mu);
    }
    if (f.formula) {
        const fDet = el("details", "fondo-fold");
        fDet.append(el("summary", "fondo-fold-cab", ico("calc") + "<span>¿Cómo se calcula cuánto recibe cada uno?</span>"));
        const body = el("div", "fondo-fold-body");
        body.append(el("p", "fondo-formula-regla", esc(f.formula.regla)));
        if (f.formula.minimo) {
            const mn = el("p", null);
            mn.innerHTML = "<b>Mínimo:</b> " + esc(f.formula.minimo);
            body.append(mn);
        }
        if (f.formula.tope) {
            const tp = el("p", null);
            tp.innerHTML = "<b>Tope:</b> " + esc(f.formula.tope);
            body.append(tp);
        }
        if (f.formula.nota)
            body.append(el("p", "nota-fuente", esc(f.formula.nota)));
        fDet.append(body);
        card.append(fDet);
    }
    if (f.tabla_por_provincia && f.tabla_por_provincia.filas.length) {
        const t = f.tabla_por_provincia;
        const tDet = el("details", "fondo-fold");
        const cab = ico("mapa") + "<span>" + esc(t.titulo || "Cuánto recibe cada provincia") +
            " <span class=\"fondo-fold-conteo\">" + t.filas.length + " provincias</span></span>";
        tDet.append(el("summary", "fondo-fold-cab", cab));
        const body = el("div", "fondo-fold-body");
        if (t.mes_referencia) {
            const mr = el("p", "fondo-tabla-mes");
            mr.innerHTML = "Montos de <b>" + esc(t.mes_referencia) + "</b>" +
                (t.moneda ? " (" + esc(t.moneda) + ")" : "") + ".";
            body.append(mr);
        }
        const tabla = el("div", "fondo-tabla");
        t.filas.forEach((row) => {
            const fila = el("div", "fondo-tabla-fila");
            fila.append(el("span", "fondo-tabla-prov", esc(row.provincia)), el("span", "fondo-tabla-monto", esc(pesosRD(row.monto))));
            tabla.append(fila);
        });
        body.append(tabla);
        if (t.nota)
            body.append(el("p", "nota-fuente", esc(t.nota)));
        tDet.append(body);
        card.append(tDet);
    }
    if (f.quien_lo_rechaza && (f.quien_lo_rechaza.nombres.length || f.quien_lo_rechaza.nota)) {
        const r = f.quien_lo_rechaza;
        const box = el("div", "fondo-rechaza");
        const t = el("b", null, ico("x") + esc(r.titulo || "No todos lo aceptan"));
        box.append(t);
        if (r.nombres.length)
            box.append(el("p", "fondo-rechaza-nombres", esc(r.nombres.join(" · "))));
        if (r.nota)
            box.append(el("p", "nota-fuente", esc(r.nota)));
        card.append(box);
    }
    if (f.base_legal) {
        const bl = el("div", "fondo-legal");
        bl.innerHTML = "<b>" + ico("scale") + "¿Qué ley lo crea?</b> " + esc(f.base_legal);
        card.append(bl);
    }
    if (f.legal && f.legal.items.length) {
        card.append(renderFondoLegal(f.legal));
    }
    if (f.fuentes && f.fuentes.length) {
        const sDet = el("details", "fuente-fold");
        sDet.append(el("summary", null, ico("libros") + "Ver fuentes"));
        const ul = el("ul", "fondo-fuentes");
        f.fuentes.forEach((src) => {
            const li = el("li", null);
            const a = el("a", "enlace-doc");
            a.href = urlSegura(src.url);
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
function fondoFuenteLink(src) {
    const a = el("a", "enlace-doc fondo-legal-fuente");
    a.href = urlSegura(src.url);
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = src.titulo;
    a.addEventListener("click", (e) => e.stopPropagation());
    return a;
}
function renderFondoLegal(legal) {
    const det = el("details", "fondo-fold fondo-legal-fold");
    det.append(el("summary", "fondo-fold-cab", ico("scale") + "<span>" + esc(legal.titulo || "Las preguntas legales, en sencillo") +
        " <span class=\"fondo-fold-conteo\">" + legal.items.length + " preguntas</span></span>"));
    const body = el("div", "fondo-fold-body");
    if (legal.intro)
        body.append(el("p", "fondo-legal-intro", esc(legal.intro)));
    legal.items.forEach((it) => {
        const qa = el("div", "fondo-legal-qa");
        qa.append(el("p", "fondo-legal-q", esc(it.q)));
        qa.append(el("p", "fondo-legal-a", esc(it.a)));
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
function renderFondoPaso(p, num, leyenda) {
    const li = leyenda[p.estado];
    const paso = el("div", "paso fondo-paso rastro-borde-" + p.estado);
    paso.append(el("span", "paso-num", String(num)));
    const txt = el("div", "paso-txt");
    const titulo = p.subtitulo ? p.paso + " — " + p.subtitulo : p.paso;
    txt.append(el("b", null, esc(titulo)));
    txt.append(el("span", null, esc(p.que_pasa)));
    if (li) {
        const badge = el("span", "rastro-badge rastro-" + p.estado, '<span class="rastro-punto" aria-hidden="true"></span> ' + esc(li.etiqueta));
        txt.append(badge);
    }
    paso.append(txt);
    return paso;
}
function normaliza(s) {
    return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}
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
function setupBuscadorLeyes() {
    const inp = document.getElementById("buscarLey");
    if (!inp)
        return;
    const aviso = document.getElementById("leyNoResultado");
    inp.addEventListener("input", () => {
        var _a;
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
        (_a = document.getElementById("sectores")) === null || _a === void 0 ? void 0 : _a.classList.toggle("hidden", Boolean(q) && visibles === 0);
    });
}
const VISTAS = {
    home: "view-home",
    pais: "view-pais",
    leyes: "view-leyes",
    mapa: "view-mapa",
    sesiones: "view-sesiones",
    dinero: "view-dinero",
    proyecto: "view-proyecto",
};
function mostrarVista(view) {
    Object.keys(VISTAS).forEach((k) => {
        byId(VISTAS[k]).classList.toggle("hidden", k !== view);
    });
    document.querySelectorAll(".tab").forEach((t) => {
        const activo = t.dataset.view === view;
        t.classList.toggle("active", activo);
        if (activo)
            t.setAttribute("aria-current", "page");
        else
            t.removeAttribute("aria-current");
    });
    window.scrollTo({ top: 0, behavior: "auto" });
}
function setupTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            const view = tab.dataset.view;
            if (view === "mapa")
                cerrarPerfil(false);
            if (view)
                mostrarVista(view);
        });
    });
    document.querySelectorAll("[data-goto]").forEach((card) => {
        card.addEventListener("click", () => {
            const dest = card.dataset.goto;
            if (dest === "mapa")
                cerrarPerfil(false);
            if (dest)
                mostrarVista(dest);
        });
    });
    const homeLink = document.getElementById("homeLink");
    if (homeLink)
        homeLink.addEventListener("click", () => mostrarVista("home"));
}
function copiarEnlace(url, btn) {
    var _a;
    const prev = btn.textContent;
    const ok = () => {
        btn.textContent = "¡Copiado!";
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
function construirSabias(leyes, ses, fin) {
    const datos = [];
    const sal = fin && (fin.metricas || []).find((m) => m.id === "salario" && m.auto);
    const deudaPP = fin && fin.comparaciones_derivadas && fin.comparaciones_derivadas.deuda_por_persona_usd;
    datos.push({
        texto: sal && sal.auto
            ? "El sueldo promedio del trabajador formal en RD es <b>" + esc(sal.auto.valor_texto) + " al mes</b>, según la seguridad social (" + esc(sal.auto.periodo) + ")."
            : "El sueldo promedio del trabajador formal en RD es <b>RD$37,572.82 al mes</b>, según la seguridad social (junio 2025).",
        cta: "Ver el bolsillo del país", destino: "dinero", acento: "acc-dinero",
    });
    datos.push({
        texto: "Cada dominicano carga <b>US$" + (typeof deudaPP === "number" ? deudaPP.toLocaleString("en-US") : "5,713") + "</b> de la deuda del país, sin haberlo pedido.",
        cta: "Ver el dinero", destino: "dinero", acento: "acc-dinero",
    });
    datos.push({
        texto: "Por cada <b>RD$100</b> que el Estado gana, gasta como <b>RD$121</b>. Ese hueco se tapa con préstamos.",
        cta: "Ver el dinero", destino: "dinero", acento: "acc-dinero",
    });
    datos.push({
        texto: "El Senado son solo <b>32 personas</b> que hacen las leyes de todo el país: una por provincia.",
        cta: "Ver las sesiones", destino: "sesiones", acento: "acc-sesiones",
    });
    if (ses.sesiones.length) {
        const ult = ses.sesiones.map((s) => s.fecha).sort().slice(-1)[0];
        datos.push({
            texto: "La última sesión del Senado que pudimos leer fue el <b>" + fechaLarga(ult) + "</b>.",
            cta: "Ver las sesiones", destino: "sesiones", acento: "acc-sesiones",
        });
    }
    const totalLeyes = leyes.sectores.reduce((n, s) => n + s.leyes.length, 0);
    datos.push({
        texto: "Aquí tienes <b>" + totalLeyes + " leyes</b> explicadas fácil, ordenadas en <b>" +
            leyes.sectores.length + " temas</b>.",
        cta: "Ver las leyes", destino: "leyes", acento: "acc-leyes",
    });
    return datos;
}
function setupSabias(leyes, ses, fin) {
    const seccion = document.getElementById("sabias");
    const viva = document.getElementById("sabiasViva");
    const puntosCont = document.getElementById("sabiasPuntos");
    const pausaBtn = document.getElementById("sabiasPausa");
    if (!seccion || !viva || !puntosCont || !pausaBtn)
        return;
    const datos = construirSabias(leyes, ses, fin);
    if (!datos.length) {
        seccion.classList.add("hidden");
        return;
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let idx = 0;
    let timer = 0;
    let pausado = reduce;
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
        btn.innerHTML = d.cta + ' <span aria-hidden="true">→</span>';
        btn.addEventListener("click", () => mostrarVista(d.destino));
        tarjeta.append(btn);
        viva.append(tarjeta);
        seccion.classList.remove("acc-dinero", "acc-leyes", "acc-sesiones");
        seccion.classList.add(d.acento);
        puntos.forEach((p, j) => p.setAttribute("aria-selected", j === idx ? "true" : "false"));
    }
    function avanzar() { mostrar(idx + 1); }
    function arrancar() {
        if (pausado)
            return;
        detener();
        timer = window.setInterval(avanzar, 12000);
    }
    function detener() { if (timer) {
        window.clearInterval(timer);
        timer = 0;
    } }
    function reiniciar() { detener(); arrancar(); }
    pausaBtn.addEventListener("click", () => {
        pausado = !pausado;
        pausaBtn.setAttribute("aria-pressed", String(pausado));
        pausaBtn.setAttribute("aria-label", pausado ? "Reanudar el cambio automático" : "Pausar el cambio automático");
        if (pausado)
            detener();
        else
            arrancar();
    });
    seccion.addEventListener("focusin", detener);
    seccion.addEventListener("focusout", () => { if (!pausado)
        arrancar(); });
    seccion.addEventListener("pointerenter", detener);
    seccion.addEventListener("pointerdown", detener);
    seccion.addEventListener("pointerleave", () => { if (!pausado)
        arrancar(); });
    let x0 = 0;
    seccion.addEventListener("pointerdown", (e) => { x0 = e.clientX; });
    seccion.addEventListener("pointerup", (e) => {
        const dx = e.clientX - x0;
        if (Math.abs(dx) > 40) {
            mostrar(idx + (dx < 0 ? 1 : -1));
            reiniciar();
        }
    });
    if (reduce) {
        pausaBtn.setAttribute("aria-pressed", "true");
        pausaBtn.setAttribute("aria-label", "Reanudar el cambio automático");
    }
    mostrar(0);
    arrancar();
}
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
function setupGlosario() {
    document.querySelectorAll(".palabra").forEach((p) => {
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
        if (p && !p.classList.contains("hidden"))
            cerrarPerfil();
    });
}
function setupEscuchar() {
    const synth = window.speechSynthesis;
    if (!synth || typeof SpeechSynthesisUtterance === "undefined")
        return;
    const hayVozEs = () => synth.getVoices().some((v) => (v.lang || "").toLowerCase().startsWith("es"));
    const resetBotones = () => {
        document.querySelectorAll(".btn-escuchar").forEach((b) => {
            b.innerHTML = ico("altavoz") + "Escuchar";
            b.setAttribute("aria-pressed", "false");
        });
    };
    const wire = (host, texto) => {
        if (host.dataset.escucharWired === "1" || !texto.trim())
            return;
        host.dataset.escucharWired = "1";
        const btn = el("button", "btn-escuchar");
        btn.type = "button";
        btn.innerHTML = ico("altavoz") + "Escuchar";
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
            btn.innerHTML = ico("pausa") + "Detener";
            btn.setAttribute("aria-pressed", "true");
            synth.speak(u);
        });
        host.appendChild(btn);
    };
    const montar = () => {
        if (!hayVozEs())
            return;
        document.querySelectorAll(".en30").forEach((card) => {
            const p = card.querySelector("p");
            if (p)
                wire(card, p.textContent || "");
        });
        document.querySelectorAll(".leer-voz").forEach((blk) => {
            wire(blk, blk.textContent || "");
        });
    };
    montar();
    if (!hayVozEs())
        synth.addEventListener("voiceschanged", montar, { once: true });
}
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
                perfil.scrollIntoView({ behavior: suave(), block: "start" });
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
            MOSTRAR_VOTOS_POR_SENADOR
                ? cargar("data/votos_por_sesion.json").catch(() => ({}))
                : Promise.resolve(undefined),
            cargar("data/fondos_publicos.json").catch(() => ({ leyenda_estado: {}, fondos: [] })),
        ]);
        const [resumenes, estado, finanzas] = await Promise.all([
            cargar("data/resumenes.json").catch(() => ({ resumenes: {}, sin_resumen: {} })),
            cargar("data/estado-fuentes.json").catch(() => ({ fuentes: {} })),
            cargar("data/finanzas.json").catch(() => ({ metricas: [] })),
        ]);
        RESUMENES = resumenes;
        ESTADO = estado;
        sesiones.sesiones.forEach((x) => {
            if (!x.votaciones)
                x.votaciones = [];
            if (!x.asistencia)
                x.asistencia = { presentes: null, ausentes: null, detalle: [] };
        });
        renderVigencia(vigencia);
        renderNovedades(novedades);
        renderLeyes(leyes);
        renderProvincias(provincias);
        renderComposicion(provincias);
        setupFinder(provincias);
        renderSesiones(sesiones, votosPorSesion);
        if (fondos && fondos.leyenda_estado)
            renderFondos(fondos);
        renderFinanzasAuto(finanzas);
        const dMapa = document.getElementById("datosAlMapa");
        const lMapa = lineaDatosAl("camara_diputados");
        if (dMapa && lMapa)
            dMapa.replaceWith(lMapa);
        setupEscuchar();
        llenarCifrasHome(leyes, provincias, sesiones);
        setupSabias(leyes, sesiones, finanzas);
        setupCasoAccordion();
        setupDineroFolds();
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
