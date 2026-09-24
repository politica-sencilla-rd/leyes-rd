#!/usr/bin/env python3
"""At most ONE "Novedad" per workflow run, written from fixed templates filled
with counts and IDs by code (no AI), then docs/novedades.xml rebuilt from
docs/data/novedades.json so the two can never disagree.

Input: the run summary <tree>/.psrd-run/resumen.json written by the source
scripts. Nothing meaningful happened -> no Novedad (the XML is still rebuilt).

Usage: python3 scripts/auto/novedades.py [--dir <tree>] [--solo-xml]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import date
from email.utils import format_datetime
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import MESES, PERIODO, ROOT, Arbol, fecha_larga, hoy_et  # noqa: E402

SITIO = "https://politica-sencilla-rd.github.io/leyes-rd/"
APORTE = "🔄 Actualización automática"
MAX_XML = 30
NOMBRE_METRICA = {"inflacion": "inflación", "desempleo": "desempleo", "crecimiento": "crecimiento de la economía",
                  "deuda": "deuda del país", "salario": "sueldo promedio"}


def frases_de(fuentes: dict, antes: dict) -> tuple[str, list[str]]:
    """-> (family key, sentences). Pure; unit-tested."""
    out: list[str] = []
    fam = ""
    s = fuentes.get("senado_actas") or {}
    if s.get("nuevas"):
        fam = "senado"
        n = sorted(s["nuevas"])
        rango = f"acta {n[0]}" if len(n) == 1 else f"actas {n[0]} a {n[-1]}"
        out.append(f"Agregamos {len(n)} {'sesión' if len(n) == 1 else 'sesiones'} del Senado ({rango}), "
                   f"leídas de las actas oficiales.")
    if s.get("corregidas"):
        fam = fam or "senado"
        c = sorted(s["corregidas"])
        out.append(f"Corregimos los totales de {'el acta ' + c[0] if len(c) == 1 else 'las actas ' + ', '.join(c)} "
                   f"con el acta oficial.")
    c = fuentes.get("camara_diputados") or {}
    if c.get("datos_al") and c["datos_al"] != (antes.get("camara_diputados") or {}).get("datos_al"):
        fam = fam or "camara"
        out.append(f"Actualizamos la asistencia, las comisiones y las iniciativas de los diputados, "
                   f"con datos de la Cámara al {fecha_larga(c['datos_al'])}.")
    v = fuentes.get("vigencia_consultoria") or {}
    if v.get("nuevas"):
        fam = fam or "vigencia"
        n = v["nuevas"]
        out.append(("Nueva ley en «¿Ya está vigente?»: " + n[0] + ".") if len(n) == 1
                   else f"Agregamos {len(n)} leyes nuevas a «¿Ya está vigente?»: {', '.join(n)}.")
    l = fuentes.get("leyes_sil") or {}
    if l.get("nuevas"):
        fam = fam or "leyes"
        out.append(f"Agregamos {len(l['nuevas'])} proyectos de ley que pasaron una votación en el Congreso.")
    if l.get("actualizadas"):
        fam = fam or "leyes"
        out.append(f"Actualizamos en qué va {len(l['actualizadas'])} "
                   f"{'proyecto' if len(l['actualizadas']) == 1 else 'proyectos'} de ley.")
    d = fuentes.get("dinero") or {}
    if d.get("cambiados"):
        fam = fam or "dinero"
        partes = []
        for x in d["cambiados"]:
            m = re.match(r"(\w+) \((.*)\)", x)
            partes.append(f"{NOMBRE_METRICA.get(m.group(1), m.group(1))} ({m.group(2)})" if m else x)
        out.append("Actualizamos las cifras del país: " + ", ".join(partes) + ".")
    r = fuentes.get("resumenes_ia") or {}
    if r.get("verificados"):
        fam = fam or "resumenes"
        out.append(f"Publicamos {r['verificados']} "
                   f"{'resumen automático nuevo' if r['verificados'] == 1 else 'resúmenes automáticos nuevos'}, "
                   f"revisados contra el documento oficial.")
    return fam, out


# Every sentence frases_de() can write, as a pattern. Gate G8 blocks any new Novedad
# that is not made only of these (free prose, opinions or made-up numbers).
_PERIODO = rf"\((?:{PERIODO})\)"  # only a real period, no free words
_METRICA = rf"(?:{'|'.join(map(re.escape, NOMBRE_METRICA.values()))}|[a-z_]+) {_PERIODO}"
_LEY = r"\d+-\d+"
PLANTILLAS = [
    r"Agregamos \d+ (?:sesión|sesiones) del Senado \((?:acta \d+|actas \d+ a \d+)\), leídas de las actas oficiales\.",
    r"Corregimos los totales de (?:el acta \d+|las actas \d+(?:, \d+)*) con el acta oficial\.",
    r"Actualizamos la asistencia, las comisiones y las iniciativas de los diputados, con datos de la Cámara al "
    rf"\d{{1,2}} de (?:{'|'.join(MESES)}) de \d{{4}}\.",
    rf"Nueva ley en «¿Ya está vigente\?»: {_LEY}\.",
    rf"Agregamos \d+ leyes nuevas a «¿Ya está vigente\?»: {_LEY}(?:, {_LEY})*\.",
    r"Agregamos \d+ proyectos de ley que pasaron una votación en el Congreso\.",
    r"Actualizamos en qué va \d+ (?:proyecto|proyectos) de ley\.",
    rf"Actualizamos las cifras del país: {_METRICA}(?:, {_METRICA})*\.",
    r"Publicamos \d+ (?:resumen automático nuevo|resúmenes automáticos nuevos), revisados contra el documento oficial\.",
]
_UNA = "(?:" + "|".join(PLANTILLAS) + ")"
_NOVEDAD = re.compile(rf"{_UNA}(?: {_UNA})*")


def es_plantilla(texto: str) -> bool:
    """True when a Novedad is made only of frases_de() sentences."""
    return bool(_NOVEDAD.fullmatch(texto or ""))


def rfc822(iso: str) -> str:
    d = date.fromisoformat(iso)
    return format_datetime(datetime(d.year, d.month, d.day, tzinfo=timezone.utc)).replace("-0000", "+0000")


def descripcion(n: dict) -> str:
    aporte = re.sub(r"^[^\wÁÉÍÓÚÑáéíóúñ]+", "", n.get("aporte", "")).strip()
    return n["texto"] + (f" {aporte}." if aporte else "")


def construir_xml(nov: dict) -> str:
    items = nov["novedades"][:MAX_XML]
    ult = max((n["fecha"] for n in items), default=hoy_et().isoformat())
    lineas = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0">', "  <channel>",
              "    <title>Política Sencilla RD — Novedades</title>", f"    <link>{SITIO}</link>",
              "    <description>Las mejoras más recientes del sitio, escritas fácil. Sin redes sociales: tu app te "
              "avisa cuando hay algo nuevo.</description>",
              "    <language>es</language>", f"    <lastBuildDate>{rfc822(ult)}</lastBuildDate>"]
    for n in items:
        lineas += ["    <item>", f"      <title>{escape(n['texto'])}</title>", f"      <link>{SITIO}</link>",
                   f'      <guid isPermaLink="false">{escape(n["guid"])}</guid>',
                   f"      <pubDate>{rfc822(n['fecha'])}</pubDate>",
                   f"      <description>{escape(descripcion(n))}</description>", "    </item>"]
    lineas += ["  </channel>", "</rss>"]
    return "\n".join(lineas) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT))
    ap.add_argument("--solo-xml", action="store_true")
    a = ap.parse_args(argv)
    arbol = Arbol("novedades", base=Path(a.dir))
    nov = arbol.leer("docs/data/novedades.json")
    if not a.solo_xml:
        run = arbol.resumen_run().get("fuentes", {})
        # runs BEFORE datos_al.py, so estado-fuentes.json still holds last run's dates
        antes = arbol.leer("docs/data/estado-fuentes.json", {"fuentes": {}})
        fam, frases = frases_de(run, antes.get("fuentes", {}))
        if frases:
            hoy = hoy_et().isoformat()
            texto = " ".join(frases)
            h = hashlib.sha256(texto.encode()).hexdigest()[:8]
            item = {"fecha": hoy, "texto": texto, "aporte": APORTE, "guid": f"psrd-auto-{fam}-{hoy}-{h}", "auto": True}
            if not any(n.get("guid") == item["guid"] for n in nov["novedades"]):
                nov["novedades"].insert(0, item)
                arbol.escribir("docs/data/novedades.json", nov)
                print("novedad: " + texto)
        else:
            print("sin novedad (nada importante cambió)")
    arbol.escribir_texto("docs/novedades.xml", construir_xml(nov))
    return 0


if __name__ == "__main__":
    sys.exit(main())
