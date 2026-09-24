#!/usr/bin/env python3
"""New laws -> docs/data/vigencia.json ("¿Ya está vigente?").

Source: Consultoría Jurídica del Poder Ejecutivo (consultoria.gov.do):
  - POST /api/consultas/search   the official law list (number, Gaceta, dates)
  - GET  /api/documents?category=gacetas   the Gaceta Oficial PDFs (real text)
  - GET  /api/document/{DocId}    the law's own PDF (the link we show)

When a law starts to apply is computed by CODE from a closed set of patterns
found word for word in the law's own text in the Gaceta:
  - "concomitantemente con la Ley núm. X"      -> same date as law X (if we have it)
  - "N días / meses / años después de/a partir de su promulgación|publicación"
  - "a partir de su promulgación y publicación" or no own article
                                                -> Código Civil art. 1: the day after
                                                   the Gaceta (Distrito Nacional)
  - anything else -> vigencia_fecha null, estado "ver_articulo", the quote is shown.
The site computes "ya rige / entra pronto" from vigencia_fecha in the browser,
so the label can never go stale.

Rules: at most 10 new laws per run (gate G5); a law never changes its
promulgation date once stored (gate G10: the 74-25 reprint trap); reprints
("edición especial", non-numeric Gaceta) are ignored; the earliest date wins.

Usage: python3 scripts/auto/vigencia.py [--dry-run] [--max 10]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import Arbol, encolar, guardar_texto_fuente, hoy_et, texto_pdf  # noqa: E402
from red import Cliente, FalloFuente  # noqa: E402

H = "https://www.consultoria.gov.do"
BUSCAR = H + "/api/consultas/search"
GACETAS = H + "/api/documents?category=gacetas"
URL_BUSQUEDA = H + "/consultas"
VIG = "docs/data/vigencia.json"
MAX_NUEVAS = 10
NUM = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
       "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "dieciocho": 18, "veinte": 20,
       "veinticuatro": 24, "treinta": 30, "sesenta": 60, "noventa": 90, "ciento veinte": 120,
       "ciento ochenta": 180, "trescientos sesenta y cinco": 365}
MOJIBAKE = {"â€œ": "“", "â€\x9d": "”", "â€": "”", "Ã“": "Ó", "Ã‘": "Ñ", "Ã‰": "É", "Ãš": "Ú", "Ã\x81": "Á",
            "Ã¡": "á", "Ã©": "é", "Ã­": "í", "Ã³": "ó", "Ãº": "ú", "Ã±": "ñ"}


def arreglar(s: str) -> str:
    for a, b in MOJIBAKE.items():
        s = s.replace(a, b)
    return " ".join(s.split())


def titulo_legible(oficial: str) -> str:
    """'QUE MODIFICA LA LEY ...' -> 'Ley que modifica la ley ...' (all-caps is hard to read)."""
    t = arreglar(oficial).strip().rstrip(".")
    if t.isupper():
        t = t.lower()
        t = re.sub(r"\b(rep[uú]blica dominicana)\b", "República Dominicana", t)
    if not t.lower().startswith("ley"):
        t = "Ley " + t
    return t[0].upper() + t[1:]


def canonicas(filas: list[dict]) -> dict:
    canon = {}
    for r in filas:
        if not str(r.get("Gaceta", "")).isdigit():
            continue  # special editions / reprints
        k = r["Numero"]
        if k not in canon or r["FechaPromulgacion"] < canon[k]["FechaPromulgacion"]:
            canon[k] = r
    return canon


def cortar_ley(gaceta: str, numero: str) -> str | None:
    a, b = numero.split("-")
    t = gaceta
    heads = [m.start() for m in re.finditer(r"Ley\s+n[úu]m\.\s*%s\s*-\s*%s\b" % (a, b), t)]
    if not heads:
        return None
    start = heads[-1]
    fin = re.search(r"PROMULGO la presente Ley.*?DADA en.*?\(\d{4}\)", t[start:], re.S)
    return t[start: start + (fin.end() if fin else 60000)]


def clausula(texto: str) -> tuple[str | None, str | None]:
    """(article number, clause text) of the law's own entry-into-force article."""
    m = re.search(r"Art[íi]culo\s+(\d+)\s*\.?\s*-?\s*(?:De la\s+)?(?:Entrada en vigencia|Vigencia|Entrada en vigor)"
                  r"[^\n]*(?:\n(?!\s*Art[íi]culo)[^\n]+){0,6}", texto, re.I)
    if not m:
        return None, None
    txt = " ".join(m.group(0).split())
    txt = re.split(r"\s(?:Dada en|DADA en|CAP[ÍI]TULO|T[ÍI]TULO\s+[IVX]+)\b", txt)[0]
    return m.group(1), txt.strip()


# Every vigencia_texto vigencia.py can write. Gate G8 accepts no other on a new law.
TXT_DEFECTO = ("No fija un plazo propio, así que manda el Código Civil: empieza a regir el día siguiente "
               "de salir en la Gaceta Oficial.")
TXT_PUBLICACION = ("Su propio texto dice que empieza a regir al promulgarse y publicarse; en la práctica, "
                   "el día siguiente de salir en la Gaceta Oficial.")
TXT_SIN_FECHA = "El robot no pudo calcular la fecha: lee el artículo de la ley (abajo)."
TXT_OJO = " Ojo: la ley dice que algunas partes empiezan más tarde; lee su texto."
_TEXTOS_VIG = re.compile(
    "(?:" + "|".join([re.escape(TXT_DEFECTO), re.escape(TXT_PUBLICACION), re.escape(TXT_SIN_FECHA),
                      r"Su propio texto dice que empieza a regir al mismo tiempo que la Ley \d+-\d+\.",
                      r"Su propio texto dice que empieza a regir \d+ (?:días|meses|años) después de su "
                      r"(?:promulgaci[óo]n|publicaci[óo]n)\."]) + ")(?:" + re.escape(TXT_OJO) + ")?")


def es_texto_vigencia(texto: str) -> bool:
    return bool(_TEXTOS_VIG.fullmatch(texto or ""))


def calcular(cl: str | None, promulgada: str, publicada: str, vigencia: dict) -> tuple[str | None, str, str]:
    """-> (vigencia_fecha, regla, texto para la gente)."""
    pub = date.fromisoformat(publicada)
    prom = date.fromisoformat(promulgada)
    dia_siguiente = (pub + timedelta(days=1)).isoformat()
    if cl is None:
        return dia_siguiente, "regla_por_defecto", TXT_DEFECTO
    c = cl.lower()
    m = re.search(r"concomitantemente con la (?:ley[^,]*?)n[úu]m\.\s*(\d+)\s*-\s*(\d+)", c)
    if m:
        otra = f"{m.group(1)}-{m.group(2)}"
        f = (vigencia.get(otra) or {}).get("vigencia_fecha")
        if f:
            return f, "concomitante", f"Su propio texto dice que empieza a regir al mismo tiempo que la Ley {otra}."
        return None, "ver_articulo", ""
    m = re.search(r"(\d+|" + "|".join(sorted(NUM, key=len, reverse=True)) + r")\s*(?:\(\d+\)\s*)?(d[íi]as|mes(?:es)?|años?)\s+"
                  r"(?:despu[ée]s de|a partir de)\s+(?:la fecha de\s+)?su\s+(promulgaci[óo]n|publicaci[óo]n)", c)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1)]
        base = prom if m.group(3).startswith("promulg") else pub
        unidad = m.group(2)
        if unidad.startswith("d"):
            f = base + timedelta(days=n)
        else:
            meses = n * (12 if unidad.startswith("a") else 1)
            y, mo = divmod(base.month - 1 + meses, 12)
            try:
                f = base.replace(year=base.year + y, month=mo + 1)
            except ValueError:
                return None, "ver_articulo", ""
        palabra = {"d": "días", "m": "meses", "a": "años"}[unidad[0]]
        return f.isoformat(), "plazo", f"Su propio texto dice que empieza a regir {n} {palabra} después de su {m.group(3)}."
    if re.search(r"(?:a partir|despu[ée]s) de (?:la fecha de )?su (?:promulgaci[óo]n y )?publicaci[óo]n", c) \
            and not re.search(r"\d{4}|excepto|salvo|diferid|\d+\s*(?:d[íi]as|mes)", c):
        return dia_siguiente, "publicacion", TXT_PUBLICACION
    return None, "ver_articulo", ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=MAX_NUEVAS)
    a = ap.parse_args(argv)
    arbol = Arbol("vigencia", dry_run=a.dry_run)
    data = arbol.leer(VIG)
    conf = arbol.leer("config/vigencia.json", {"excluir_titulos": []})
    cli = Cliente(arbol.p(".psrd-run/recibos-vigencia.json"))
    hoy = hoy_et()
    try:
        filas = []
        for y in sorted({hoy.year, hoy.year - 1 if hoy.month <= 2 else hoy.year}):
            cuerpo = {"DocumentTypeCode": 1, "DocumentNumber": "", "FullText": "", "Name": "", "LastName": "",
                      "Identification": "", "Charge": "", "Institution": 0, "President": 0, "Consultor": 0,
                      "Career": 0, "Guild": 0, "PensionType": 0, "PublicationYear": str(y)}
            r = cli.get(BUSCAR, "json", data=json.dumps(cuerpo).encode(), cabeceras={"Content-Type": "application/json"})
            filas += r.json()
        gacetas = {g["title"]: g for g in cli.get(GACETAS, "json").json() if g.get("category") == "gacetas"}
    except FalloFuente as e:
        cli.guardar()
        arbol.anotar_run("vigencia_consultoria", estado="sin_respuesta", error=str(e))
        print(f"FALLÓ la Consultoría: {e}", file=sys.stderr)
        return 1
    if not filas:
        cli.guardar()
        arbol.anotar_run("vigencia_consultoria", estado="roto", error="la búsqueda devolvió 0 leyes")
        print("La búsqueda devolvió 0 leyes: se trata como fuente rota.", file=sys.stderr)
        return 1

    canon = canonicas(filas)
    tenemos = {l["numero"]: l for l in data["leyes"]}
    excluir = [re.compile(x, re.I) for x in conf.get("excluir_titulos", [])]
    nuevas = [r for k, r in canon.items() if k not in tenemos and not any(x.search(arreglar(r["Titulo"])) for x in excluir)]
    nuevas.sort(key=lambda r: r["FechaPromulgacion"])
    print(f"leyes en la Consultoría: {len(canon)}; nuevas para el sitio: {len(nuevas)}; esta corrida: {min(len(nuevas), a.max)}")

    textos_gaceta: dict[str, str] = {}
    agregadas, fallos, cola = [], [], 0
    for r in nuevas[: a.max]:
        num = r["Numero"]
        g = gacetas.get(r["Gaceta"])
        if not g:
            fallos.append({"numero": num, "error": f"la Gaceta {r['Gaceta']} aún no está en el portal"})
            continue
        try:
            if r["Gaceta"] not in textos_gaceta:
                pdf = cli.get(H + g["fileUrl"].split("|")[0], "pdf")
                textos_gaceta[r["Gaceta"]] = texto_pdf(pdf.cuerpo)
            url_doc = f"{H}/api/document/{r['DocId']}"
            cli.get(url_doc, "pdf")  # the link we show must answer 200 with a PDF (gate G4)
        except FalloFuente as e:
            fallos.append({"numero": num, "error": str(e)})
            continue
        texto = cortar_ley(textos_gaceta[r["Gaceta"]], num)
        if not texto:
            fallos.append({"numero": num, "error": f"no se encontró la ley dentro de la Gaceta {r['Gaceta']}"})
            continue
        art, cl = clausula(texto)
        fecha, regla, explica = calcular(cl, r["FechaPromulgacion"], r["FechaPublicacion"], tenemos)
        ley = {"numero": num, "titulo": titulo_legible(r["Titulo"]), "titulo_oficial": arreglar(r["Titulo"]),
               "promulgada": r["FechaPromulgacion"], "publicada": r["FechaPublicacion"], "gaceta": r["Gaceta"],
               "estado": "ver_articulo" if fecha is None else ("vigencia" if date.fromisoformat(fecha) <= hoy else "pronto"),
               "vigencia_fecha": fecha,
               "vigencia_texto": explica or TXT_SIN_FECHA,
               "regla": regla,
               "fuente": f"Ley {num}{', art. ' + art if art else ''} — Consultoría Jurídica del Poder Ejecutivo (consultoria.gov.do)",
               "url_documento": url_doc, "url_busqueda": URL_BUSQUEDA, "auto": True, "datos_al": hoy.isoformat()}
        if cl:
            ley["vigencia_cita"] = cl[:400]
        if fecha and re.search(r"vigencia diferida|entrar[áa]n en vigencia en un plazo", texto, re.I):
            ley["vigencia_texto"] += TXT_OJO
        agregadas.append(ley)
        tenemos[num] = ley
        sha = guardar_texto_fuente(arbol, texto[:12000])
        if encolar(arbol, {"id": "ley-" + num, "tipo": "ley", "campos": ["que_es"], "estado_ley": "promulgada",
                           "fuente_url": url_doc, "fuente_nombre": f"Ley {num}, Gaceta Oficial {r['Gaceta']}",
                           "fuente_sha256": sha}):
            cola += 1
        print(f"{num}: promulgada {r['FechaPromulgacion']}, rige {fecha} ({regla})")
    cli.guardar()
    if agregadas:
        data["leyes"] = sorted(data["leyes"] + agregadas, key=lambda l: l["promulgada"], reverse=True)
        arbol.escribir(VIG, data)
    ultima = max(canon.values(), key=lambda r: r["FechaPublicacion"])
    arbol.anotar_run("vigencia_consultoria", estado="ok" if not fallos else "parcial", fallos=fallos,
                     nuevas=[l["numero"] for l in agregadas], encolados=cola,
                     ultimo_documento=f"Ley {ultima['Numero']}", subido_por_la_fuente=ultima["FechaPublicacion"],
                     pendientes_en_fuente=max(0, len(nuevas) - a.max))
    print(f"listo: {len(agregadas)} leyes nuevas, {len(fallos)} con problemas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
