#!/usr/bin/env python3
"""Weekly Senate refresh: official actas (minutes) -> docs/data/sesiones.json.

Source: the Senate's own actas list (WP File Download category 1387 on
senadord.gob.do). Each acta is a born-digital PDF with a real text layer, so no
OCR is needed. We read ONLY totals ("N votos a favor, de M senadores
presentes") and the roll-call counts. Named per-senator votes are never
collected: category 1438 (Votaciones Electrónicas) is never fetched.

Rules (design section 4.1), all enforced in code:
  - An acta publishes whole or not at all. Every "Votación electrónica NNN"
    heading in the text must be accounted for (bill vote, known non-bill step,
    or known source inconsistency). Otherwise the acta is published only as
    {"acta", "estado": "no_procesada", "url_acta"} and the issue is updated.
  - A vote with a_favor > presentes, or with missing totals, is left out and the
    session gets a public note ("notas_fuente").
  - Session "presentes" comes from the final roll call.
  - Every vote carries fuente "Acta NNNN, votación electrónica NNN" + url_acta.
  - Crawl-delay 120 s on senadord.gob.do (robots.txt), enforced by red.Cliente.
  - At most 30 actas per run (gate G5).

Usage:
  python3 scripts/auto/senado_actas.py [--dry-run] [--max 30]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import Arbol, encolar, guardar_texto_fuente, texto_pdf  # noqa: E402
from red import Cliente, FalloFuente  # noqa: E402

LISTADO = ("https://www.senadord.gob.do/wp-admin/admin-ajax.php?juwpfisadmin=false&action=wpfd"
           "&task=files.display&view=files&id=1387&rootcat=1387&page={page}")
URL_FUENTE = "https://www.senadord.gob.do/elaboracion-de-actas/actas-de-sesiones/"
SES = "docs/data/sesiones.json"
CONF = "config/senado.json"
MAX_ACTAS = 30
QUORUM = 17  # absolute majority of 32 (INFERRED floor, gate G3)

MES = {m: i + 1 for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())}
HDR = re.compile(
    r"^(S E N A D O|REPÚBLICA DOMINICANA|República Dominicana|Acta núm\..*pág\.\d+ de \d+|"
    r"Av\. Enrique Jiménez.*|Guzmán, Distrito Nacional, República Dominicana\.|"
    r"Departamento Elaboración de Actas\. Tel.*)\s*$", re.I)
TITULO_ACTA = re.compile(r"ACTA\s+N[ÚU]M\.?\s*(\d{4})", re.I)


def limpiar(raw: str) -> str:
    return "\n".join(ln for ln in raw.splitlines() if not HDR.match(ln.strip()))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _nombres(raw: str, bloque: str) -> list[str]:
    out, vistos = [], set()
    for ln in raw.splitlines():
        s = ln.strip()
        if s and s in bloque and not re.match(r"^\d", s) and len(s.split()) >= 2 and s not in vistos:
            vistos.add(s)
            out.append(s)
    return out


# ---------------------------------------------------------------- parser
def parse(raw_text: str) -> dict:
    raw = limpiar(raw_text)
    t = norm(raw)
    t = re.sub(r"Acta núm\. \d{4,5},? del? [^|]{0,60}?pág\. (?:núm\. )?\d+ de \d+ ?", "", t)
    m = re.search(r"Acta núm\. (\d{4,5}),? (?:del )?\w+ (\d{1,2}) de (\w+) (?:de|del) (\d{4})", t)
    if not m:
        raise ValueError("no se encontró el número y la fecha del acta")
    acta = m.group(1)[-4:]
    fecha = f"{m.group(4)}-{MES[m.group(3).lower()]:02d}-{int(m.group(2)):02d}"
    tipo = "extraordinaria" if re.search(r"Sesión Extraordinaria", t[:600], re.I) else "ordinaria"

    pres = re.search(r"1\.1 Senadores presentes \((\d+)\)", t)
    exc = re.search(r"1\.2 Senadores ausentes con excusa legítima \((\d+)\)(.*?)1\.3", t)
    sin = re.search(r"1\.3 Senadores ausentes sin excusa legítima \((\d+)\)(.*?)(?:1\.4|2\. Comprobación)", t)
    det = []
    if exc:
        det += [{"nombre": n, "estado": "excusado"} for n in _nombres(raw, exc.group(2)) if n.rstrip(".") != "No hay"]
    if sin:
        det += [{"nombre": n, "estado": "ausente"} for n in _nombres(raw, sin.group(2)) if n.rstrip(".") != "No hay"]
    allp = re.findall(r"Senadores presentes \((\d+)\)", t)
    asistencia = {
        "presentes_inicio": int(pres.group(1)) if pres else None,
        "presentes_final": int(allp[-1]) if allp else None,
        "excusados": int(exc.group(1)) if exc else 0,
        "sin_excusa": int(sin.group(1)) if sin else 0,
        "detalle": det,
    }

    votos = []
    heads = list(re.finditer(r"Votación electrónica (anulada )?(\d{3})\.? Sometid[ao] a votación ", t))
    for k, h in enumerate(heads):
        chunk = t[h.end(): heads[k + 1].start() if k + 1 < len(heads) else len(t)]
        num = h.group(2)
        if h.group(1):
            votos.append({"votacion": num, "anulada": True})  # annulled on the floor: not a result
            continue
        v = re.search(r"(.*?)(\d+) votos? a favor,? (?:de )?(\d+) senadores presentes para esta votación\.? "
                      r"(.*?)(?=Votación adjunta|Senador|\d+\.\d+(?:\.\d+)? |$)", chunk)
        if not v:
            votos.append({"votacion": num, "error": "totales_incompletos", "texto": chunk[:200]})
            continue
        obj, af, pr, res = v.groups()
        ini = re.search(r"(?:Iniciativa|Iniciativas) núm\.\s*(?:Iniciativa núm\.\s*)?(\d{5})-\s?(\d{4})", obj)
        procedural = (not re.search(r"(primera|segunda|única) (discusión|lectura)", res, re.I)) \
            or obj.lower().startswith("la propuesta")
        titulo = re.sub(r"^.*?\d{5}-\s?\d{4},?\s*", "", obj).strip().rstrip(".") if ini else obj.strip()
        flags = []
        if int(af) > int(pr):
            flags.append("a_favor_mayor_que_presentes")
        if int(pr) > 32:
            flags.append("presentes_mayor_que_32")
        votos.append({"votacion": num, "iniciativa": f"{ini.group(1)}-{ini.group(2)}" if ini else None,
                      "procedural": procedural, "a_favor": int(af), "presentes": int(pr),
                      "resultado": res.strip().rstrip("."), "titulo": titulo[:300], "flags": flags})

    # Every heading in the body (the table of contents ones are followed by dot leaders).
    encabezados = sorted(set(re.findall(r"Votación electrónica (?:anulada )?(\d{3})\b\.? ?(?!\.\.)", t)))
    return {"acta": acta, "fecha": fecha, "tipo": tipo, "asistencia": asistencia,
            "votaciones_todas": votos, "encabezados": encabezados}


def nota_publica(v: dict) -> str:
    n = v["votacion"]
    if v.get("error"):
        return f"Votación electrónica {n}: el acta no trae los totales completos; no la mostramos. Ver acta."
    if "a_favor_mayor_que_presentes" in v.get("flags", []):
        return (f"Votación electrónica {n}: el acta dice {v['a_favor']} a favor con {v['presentes']} "
                f"presentes; no la mostramos. Ver acta.")
    if "presentes_bajo_quorum" in v.get("flags", []):
        return (f"Votación electrónica {n}: el acta dice {v['presentes']} presentes, menos de la mitad "
                f"más uno de 32; no la mostramos. Ver acta.")
    return f"Votación electrónica {n}: el acta trae un dato imposible ({v['presentes']} presentes); no la mostramos. Ver acta."


def a_sesion(p: dict, url_acta: str) -> dict:
    """Parsed acta -> one sesiones.json entry, or the no_procesada stub."""
    parsed_nums = {v["votacion"] for v in p["votaciones_todas"]}
    faltan = sorted(set(p["encabezados"]) - parsed_nums)
    if faltan:
        return {"acta": p["acta"], "fecha": p["fecha"], "estado": "no_procesada", "url_acta": url_acta,
                "auto": True, "motivo": "votaciones sin leer: " + ", ".join(faltan)}
    votaciones, notas = [], []
    for v in p["votaciones_todas"]:
        if v.get("anulada"):
            continue
        if not v.get("error") and not v.get("flags") and v["presentes"] < QUORUM:
            v["flags"] = ["presentes_bajo_quorum"]
        if v.get("error") or v.get("flags"):
            notas.append(nota_publica(v))
            continue
        if not v.get("iniciativa") or v.get("procedural"):
            continue  # known non-bill step (acta approval, motion, amendment, inclusion in agenda)
        votaciones.append({"iniciativa": v["iniciativa"], "titulo": v["titulo"], "a_favor": v["a_favor"],
                           "presentes": v["presentes"], "resultado": v["resultado"],
                           "votacion_num": v["votacion"],
                           "fuente": f"Acta {p['acta']}, votación electrónica {v['votacion']}"})
    a = p["asistencia"]
    ausentes = a["excusados"] + a["sin_excusa"]
    detalle = a["detalle"] if len(a["detalle"]) == ausentes else []  # names only when the count matches
    ses = {"acta": p["acta"], "fecha": p["fecha"], "tipo": p["tipo"], "url_acta": url_acta,
           "votaciones": votaciones,
           "asistencia": {"presentes": a["presentes_final"], "ausentes": ausentes,
                          "detalle": detalle,
                          "nota": "Presentes según el último pase de lista del acta."},
           "auto": True}
    if notas:
        ses["notas_fuente"] = notas
    return ses


# Every 'motivo' a no_procesada acta can carry (a_sesion / sesion_valida). Gate G8 accepts no other.
_ERR_ACTA = r"(?:presentes fuera de 0\.\.32|presentes \+ ausentes > 32|votación \d{3}: totales imposibles)"
_MOTIVO = re.compile(rf"votaciones sin leer: \d{{3}}(?:, \d{{3}})*|{_ERR_ACTA}(?:; {_ERR_ACTA})*")


def es_motivo(texto: str) -> bool:
    return bool(_MOTIVO.fullmatch(texto or ""))


def sesion_valida(ses: dict) -> list[str]:
    """Item-level sanity (same numbers as gate G3) so one bad acta is dropped
    before the gate would block the whole batch."""
    err = []
    if ses.get("estado") == "no_procesada":
        return err
    a = ses["asistencia"]
    if a["presentes"] is not None and not (0 <= a["presentes"] <= 32):
        err.append("presentes fuera de 0..32")
    if a["presentes"] is not None and a["presentes"] + a["ausentes"] > 32:
        err.append("presentes + ausentes > 32")
    for v in ses["votaciones"]:
        if not (0 <= v["a_favor"] <= v["presentes"] <= 32) or v["presentes"] < QUORUM:
            err.append(f"votación {v['votacion_num']}: totales imposibles")
    return err


# ---------------------------------------------------------------- listing
def listar(cli: Cliente, desde_acta: int, max_paginas: int = 5) -> list[dict]:
    """Newest-first listing; stops at the first page that reaches actas we have."""
    out = []
    for page in range(1, max_paginas + 1):
        j = cli.get(LISTADO.format(page=page), "json").json()
        files = j.get("files") or []
        if not files:
            break
        for f in files:
            m = TITULO_ACTA.search(f.get("post_title") or "")
            if m and f.get("ext") == "pdf":
                out.append({"acta": m.group(1), "id": f["ID"], "url": f["linkdownload"],
                            "subido": f.get("created"), "titulo": f["post_title"]})
        nums = [int(x["acta"]) for x in out]
        if nums and min(nums) <= desde_acta:
            break
    return out


def fusionar(sesiones: list[dict], nuevas: list[dict], legado_titulos: dict) -> list[dict]:
    por_acta = {s["acta"]: s for s in sesiones}
    for s in nuevas:
        viejo = por_acta.get(s["acta"])
        if viejo and s.get("estado") != "no_procesada":
            # keep the legacy hand-written titulo_facil for the same bill (prose is never auto-edited)
            tf = {v["iniciativa"]: v.get("titulo_facil") for v in viejo.get("votaciones", []) if v.get("titulo_facil")}
            for v in s["votaciones"]:
                if v["iniciativa"] in tf:
                    v["titulo_facil"] = tf[v["iniciativa"]]
        por_acta[s["acta"]] = s
    return sorted(por_acta.values(), key=lambda s: s["acta"], reverse=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=MAX_ACTAS)
    ap.add_argument("--sin-reemplazos", action="store_true", help="no re-parsear las actas de config/senado.json")
    a = ap.parse_args(argv)

    arbol = Arbol("senado", dry_run=a.dry_run)
    data = arbol.leer(SES)
    conf = arbol.leer(CONF, {"reemplazar_una_vez": []})
    cli = Cliente(arbol.p(".psrd-run/recibos-senado.json"))
    hechas = {s["acta"] for s in data["sesiones"] if s.get("estado") != "no_procesada"}
    mayor = max(int(x) for x in hechas) if hechas else 0

    try:
        lista = listar(cli, mayor)
    except FalloFuente as e:
        cli.guardar()
        arbol.anotar_run("senado_actas", estado="sin_respuesta", error=str(e))
        print(f"LISTADO FALLÓ: {e}", file=sys.stderr)
        return 1
    ultimo_publicado = max((x for x in lista), key=lambda x: int(x["acta"]), default=None)

    pendientes = sorted([x for x in lista if int(x["acta"]) > mayor], key=lambda x: x["acta"])
    reemplazos = []
    if not a.sin_reemplazos:
        for s in data["sesiones"]:
            if s["acta"] in conf.get("reemplazar_una_vez", []) and not s.get("auto") and s.get("url_acta"):
                reemplazos.append({"acta": s["acta"], "url": s["url_acta"], "reemplazo": True})
    trabajo = (reemplazos + pendientes)[: a.max]
    print(f"actas nuevas en la fuente: {len(pendientes)}; reemplazos: {len(reemplazos)}; esta corrida: {len(trabajo)}")

    nuevas, fallos, cola = [], [], 0
    for x in trabajo:
        try:
            pdf = cli.get(x["url"], "pdf")
            p = parse(texto_pdf(pdf.cuerpo))
            if p["acta"] != x["acta"]:
                raise ValueError(f"el PDF dice acta {p['acta']}, la lista dice {x['acta']}")
            ses = a_sesion(p, x["url"])
            errs = sesion_valida(ses)
            if errs:
                ses = {"acta": x["acta"], "fecha": p["fecha"], "estado": "no_procesada", "url_acta": x["url"],
                       "auto": True, "motivo": "; ".join(errs)}
        except (FalloFuente, ValueError, KeyError) as e:
            fallos.append({"acta": x["acta"], "error": str(e)})
            print(f"acta {x['acta']}: FALLÓ ({e})", file=sys.stderr)
            continue
        if ses.get("estado") == "no_procesada":
            fallos.append({"acta": x["acta"], "error": ses["motivo"]})
        nuevas.append(ses)
        for v in ses.get("votaciones", []):
            if v.get("titulo_facil"):
                continue
            sha = guardar_texto_fuente(arbol, v["titulo"])
            if encolar(arbol, {"id": "senado-" + v["iniciativa"], "tipo": "titulo_voto",
                               "campos": ["titulo_facil"], "estado_ley": "votando",
                               "fuente_url": x["url"], "fuente_nombre": v["fuente"],
                               "fuente_sha256": sha}):
                cola += 1
        print(f"acta {x['acta']}: {len(ses.get('votaciones', []))} votaciones"
              f"{' (' + ses['estado'] + ')' if ses.get('estado') else ''}")
    cli.guardar()

    if trabajo and not nuevas:
        arbol.anotar_run("senado_actas", estado="roto", error="ninguna acta se pudo leer", fallos=fallos)
        return 1
    if nuevas:
        data["sesiones"] = fusionar(data["sesiones"], nuevas, {})
        arbol.escribir(SES, data)
    ok = [s for s in nuevas if s.get("estado") != "no_procesada"]
    arbol.anotar_run(
        "senado_actas", estado="ok" if not fallos else "parcial", fallos=fallos,
        ultimo_documento=f"Acta {ultimo_publicado['acta']}" if ultimo_publicado else None,
        subido_por_la_fuente=_iso(ultimo_publicado["subido"]) if ultimo_publicado else None,
        nuevas=[s["acta"] for s in ok if s["acta"] not in {r["acta"] for r in reemplazos}],
        corregidas=[s["acta"] for s in ok if s["acta"] in {r["acta"] for r in reemplazos}],
        votos_nuevos=sum(len(s["votaciones"]) for s in ok), encolados=cola,
        pendientes_en_fuente=max(0, len(pendientes) - max(0, a.max - len(reemplazos))))
    print(f"listo: {len(ok)} actas publicables, {len(fallos)} con problemas, {cola} títulos en cola para la IA")
    return 0


def _iso(dmy: str | None) -> str | None:
    if not dmy:
        return None
    d, m, y = dmy.split("-")
    return f"{y}-{m}-{d}"


if __name__ == "__main__":
    sys.exit(main())
