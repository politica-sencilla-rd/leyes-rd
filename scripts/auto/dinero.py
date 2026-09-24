#!/usr/bin/env python3
"""Money numbers ("El bolsillo del país") -> docs/data/finanzas.json.

Every number comes from an official machine-readable file (Excel), parsed by
code. The card text comes from fixed Spanish templates filled by code. No AI.

  inflacion   BCRD, IPC base 2019-2020 (xls)                      monthly
  desempleo   BCRD, ENCFT 00_Indicadores.xlsx (tasa SU1)           quarterly
  crecimiento BCRD, pib_origen_2018.xlsx (PIB real, acumulado)     quarterly
  deuda       Crédito Público, saldo histórico 1970-YYYY (xlsx)    yearly (Dec)
  salario     TSS, boletín del régimen contributivo (xlsx, hoja 2) monthly

Rules: the year-ago comparison comes from the same file and the same series;
debt/GDP is never computed by us (taken from the Crédito Público file); a
metric changes value, comparison, period and link together or not at all; one
metric that fails keeps its last good value (the others still publish); a
period may never move backwards (gate G10); values outside sane ranges are
blocked by gate G3.

Usage: python3 scripts/auto/dinero.py [--dry-run]
"""
from __future__ import annotations

import argparse
import html as H
import io
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import Arbol, hoy_et  # noqa: E402
from red import Cliente, FalloFuente  # noqa: E402

FIN = "docs/data/finanzas.json"
MES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
       "Noviembre", "Diciembre"]
ACUM = {"E-M": "enero-marzo", "E-J": "enero-junio", "E-S": "enero-septiembre", "E-D": "enero-diciembre"}
TRIM = {"I": ("enero-marzo", 3), "II": ("abril-junio", 6), "III": ("julio-septiembre", 9), "IV": ("octubre-diciembre", 12)}
URL_IPC = "https://cdn.bancentral.gov.do/documents/estadisticas/precios/documents/ipc_base_2019-2020.xls"
URL_ENCFT = "https://cdn.bancentral.gov.do/documents/estadisticas/mercado-de-trabajo/documents/00_Indicadores.xlsx"
URL_PIB = "https://cdn.bancentral.gov.do/documents/estadisticas/sector-real/documents/pib_origen_2018.xlsx"
CP = "https://www.creditopublico.gob.do"
TSS_AJAX = "https://tss.gob.do/wp-admin/admin-ajax.php?juwpfisadmin=false&action=wpfd&task="
PAGINAS = {"inflacion": "https://www.bancentral.gov.do/a/d/2534-precios",
           "desempleo": "https://www.bancentral.gov.do/a/d/2541-encuesta-continua-encft",
           "crecimiento": "https://www.bancentral.gov.do/a/d/2533-sector-real",
           "deuda": "https://www.creditopublico.gob.do/inicio/estadisticas",
           "salario": "https://www.tss.gob.do/"}


def pd():
    import pandas  # noqa: PLC0415  (only this workflow installs pandas)
    return pandas


def fmt_pct(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".") + "%"


def fmt_rd(x: float) -> str:
    return f"RD${x:,.2f}"


def tendencia(nuevo: float, viejo: float, sube: str, baja: str, igual: str) -> str:
    if abs(nuevo - viejo) < 0.005:
        return igual
    return sube if nuevo > viejo else baja


# ---------------------------------------------------------------- parsers (pure: bytes -> dict)
def parse_ipc(contenido: bytes) -> dict:
    df = pd().read_excel(io.BytesIO(contenido), header=None)
    df[0] = df[0].ffill()
    d = df[df[1].isin(MES)].dropna(subset=[5])
    last = d.iloc[-1]
    prev = d[(d[0] == last[0] - 1) & (d[1] == last[1])].iloc[0]
    y, m = int(last[0]), MES.index(last[1]) + 1
    return {"valor_num": round(float(last[5]), 2), "anterior_num": round(float(prev[5]), 2),
            "periodo": f"{last[1].lower()} {y}", "periodo_iso": f"{y}-{m:02d}",
            "anterior_periodo": f"{last[1].lower()} {y - 1}"}


def parse_encft(contenido: bytes) -> dict:
    df = pd().read_excel(io.BytesIO(contenido), sheet_name=0, header=None)
    yrs = df.iloc[7].ffill()
    q = df.iloc[8].astype(str).str.strip()
    row = df[df[0].astype(str).str.startswith("SU1")].index[0]
    c = max(i for i in range(1, df.shape[1]) if pd().notna(df.iloc[row, i]))
    trim = q[c].split()[0]
    y = int(float(re.match(r"\d{4}", str(yrs[c])).group(0)))
    pc = [i for i in range(1, df.shape[1]) if str(yrs[i]).startswith(str(y - 1)) and q[i].split()[0] == trim][0]
    nombre, mes_fin = TRIM[trim]
    return {"valor_num": round(float(df.iloc[row, c]), 2), "anterior_num": round(float(df.iloc[row, pc]), 2),
            "periodo": f"{nombre} {y}", "periodo_iso": f"{y}-{mes_fin:02d}", "anterior_periodo": f"{nombre} {y - 1}"}


def parse_pib(contenido: bytes) -> dict:
    x = pd().ExcelFile(io.BytesIO(contenido))
    k = pd().read_excel(x, "PIBK_Trim_Acum", header=None)
    hdr_y, hdr_p = k.iloc[6].ffill(), k.iloc[7]
    grow = k[k[0].astype(str).str.strip() == "Producto Interno Bruto"].index[1]  # 2nd block = growth rates
    eds = [i for i in range(k.shape[1]) if str(hdr_p[i]).strip() == "E-D"]
    ed = eds[-1]
    ult = k.shape[1] - 1
    y = int(re.match(r"\d{4}", str(hdr_y[ed])).group(0))
    out = {"valor_num": round(float(k.iloc[grow, ed]), 2), "periodo": f"enero-diciembre {y}",
           "periodo_iso": f"{y}-12", "preliminar": "(p)" in str(hdr_y[ed])}
    if len(eds) > 1:
        out["anterior_num"] = round(float(k.iloc[grow, eds[-2]]), 2)
        out["anterior_periodo"] = f"enero-diciembre {y - 1}"
    if ult != ed:
        out["parcial_num"] = round(float(k.iloc[grow, ult]), 2)
        cod = str(hdr_p[ult]).strip()
        out["parcial_periodo"] = f"{ACUM.get(cod, cod)} {re.match(r'[0-9]{4}', str(hdr_y[ult])).group(0)}"
    return out


def enlace_deuda(pagina_html: str) -> str:
    hist = [l for l in re.findall(r'href="(/Content/estadisticas/historico/saldo/[^"]+)"', pagina_html) if "(1970" in l][0]
    return CP + urllib.parse.quote(H.unescape(hist))


def parse_deuda(contenido: bytes) -> dict:
    df = pd().read_excel(io.BytesIO(contenido), header=None)
    dic = df[df[10].astype(str).str.contains("Dic", na=False)]
    r0, r1 = dic.iloc[0], dic.iloc[1]
    y = int(re.search(r"(\d{4})", str(r0[10])).group(1))
    return {"valor_num": round(float(r0[14]), 2), "anterior_num": round(float(r1[14]), 2),
            "usd_millones": round(float(r0[13]), 1), "periodo": f"cierre de {y}", "periodo_iso": f"{y}-12",
            "anterior_periodo": f"cierre de {y - 1}"}


def parse_tss(contenido: bytes, anio: int) -> dict:
    df = pd().read_excel(io.BytesIO(contenido), sheet_name="2", header=None)
    yrow = df.iloc[5].tolist()
    mc = next(c for c in df.columns if df[c].isin(MES).any())
    mes_rows = df[df[mc].isin(MES)]
    cy = [i for i, v in enumerate(yrow) if str(v).startswith(str(anio))][1]  # salary column for the year
    m = mes_rows[mes_rows[cy].astype(float) > 0].iloc[-1]
    mi = MES.index(m[mc]) + 1
    return {"valor_num": round(float(m[cy]), 2), "anterior_num": round(float(m[cy - 1]), 2),
            "var_pct": round(float(m[cy + 2]) * 100, 2), "periodo": f"{m[mc].lower()} {anio}",
            "periodo_iso": f"{anio}-{mi:02d}", "anterior_periodo": f"{m[mc].lower()} {anio - 1}"}


# ---------------------------------------------------------------- templates (fixed Spanish)
def textos(mid: str, d: dict, poblacion: int | None) -> dict:
    v, a = d["valor_num"], d.get("anterior_num")
    if mid == "inflacion":
        t = {"valor_texto": fmt_pct(v), "unidad": "en un año",
             "texto": f"Lo que costaba RD$100 hace un año, hoy cuesta como RD${100 + v:.0f}.",
             "comparacion": f"Hace un año ({d['anterior_periodo']}) fue {fmt_pct(a)}; ahora ({d['periodo']}) es {fmt_pct(v)}. "
             + tendencia(v, a, "Los precios suben más rápido que hace un año.", "Los precios suben más despacio que hace un año.",
                         "Suben al mismo ritmo que hace un año."),
             "fuente": f"Banco Central RD, índice de precios (IPC), {d['periodo']}, comparado con {d['anterior_periodo']}."}
    elif mid == "desempleo":
        t = {"valor_texto": fmt_pct(v), "unidad": "",
             "texto": f"De cada 100 personas que buscan empleo, unas {round(v)} no lo consiguen.",
             "comparacion": f"Hace un año ({d['anterior_periodo']}) fue {fmt_pct(a)}; ahora ({d['periodo']}) es {fmt_pct(v)}. "
             + tendencia(v, a, "Subió.", "Bajó.", "Quedó igual."),
             "fuente": f"Banco Central RD, encuesta de empleo (ENCFT), tasa SU1, {d['periodo']}, comparado con {d['anterior_periodo']}."}
    elif mid == "crecimiento":
        prel = " (preliminar)" if d.get("preliminar") else ""
        comp = ""
        if a is not None:
            comp = f"El año anterior creció {fmt_pct(a)}; en {d['periodo']} creció {fmt_pct(v)}. " + \
                tendencia(v, a, "Creció más rápido.", "Creció más lento.", "Creció igual.")
        if d.get("parcial_num") is not None:
            comp += f" En lo que va del año ({d['parcial_periodo']}) va {fmt_pct(d['parcial_num'])}."
        t = {"valor_texto": fmt_pct(v), "unidad": "",
             "texto": f"De cada RD$100 que producía, el país pasó a producir como RD${100 + v:.0f}.",
             "comparacion": comp.strip(),
             "fuente": f"Banco Central RD, producto interno bruto real, {d['periodo']}{prel}."}
    elif mid == "deuda":
        extra = ""
        if poblacion:
            extra = f" Son como US${d['usd_millones'] * 1e6 / poblacion:,.0f} de deuda por cada dominicano."
        t = {"valor_texto": fmt_pct(v), "unidad": "del PIB",
             "texto": f"El país debe US${d['usd_millones']:,.1f} millones (sector público no financiero).{extra}",
             "comparacion": f"Al {d['anterior_periodo']} debía {fmt_pct(a)} del PIB; al {d['periodo']}, {fmt_pct(v)}. "
             + tendencia(v, a, "Subió.", "Bajó.", "Quedó igual."),
             "fuente": f"Dirección General de Crédito Público, saldo de la deuda, {d['periodo']}."}
    elif mid == "salario":
        t = {"valor_texto": fmt_rd(v), "unidad": "al mes",
             "texto": "Es el sueldo promedio de quien tiene trabajo \"con papeles\" y cotiza a la seguridad social. Muchos ganan menos.",
             "comparacion": f"En {d['anterior_periodo']} era {fmt_rd(a)}; en {d['periodo']}, {fmt_rd(v)} "
             f"({'+' if d['var_pct'] >= 0 else ''}{d['var_pct']:.2f}%). " + tendencia(v, a, "Subió.", "Bajó.", "Quedó igual."),
             "fuente": f"Tesorería de la Seguridad Social (TSS), salario promedio cotizable, {d['periodo']}."}
    else:
        raise KeyError(mid)
    return t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    arbol = Arbol("dinero", dry_run=a.dry_run)
    fin = arbol.leer(FIN)
    cli = Cliente(arbol.p(".psrd-run/recibos-dinero.json"), timeout=120)
    hoy = hoy_et()
    poblacion = (fin.get("poblacion") or {}).get("habitantes")

    def ipc():
        return URL_IPC, parse_ipc(cli.get(URL_IPC, "xls").cuerpo)

    def encft():
        return URL_ENCFT, parse_encft(cli.get(URL_ENCFT, "xlsx").cuerpo)

    def pib():
        return URL_PIB, parse_pib(cli.get(URL_PIB, "xlsx").cuerpo)

    def deuda():
        url = enlace_deuda(cli.get(CP + "/inicio/estadisticas", "html").texto())
        return url, parse_deuda(cli.get(url, "xlsx").cuerpo)

    def salario():
        cats = cli.get(TSS_AJAX + "categories.display&view=categories&id=121&top=121", "json").json()["categories"]
        ycat = max((c for c in cats if str(c["name"]).isdigit()), key=lambda c: int(c["name"]))
        files = cli.get(TSS_AJAX + f"files.display&view=files&id={ycat['term_id']}&rootcat=121&page=1", "json").json()["files"]
        f = [f for f in files if f["ext"] == "xlsx" and not f["post_title"].startswith("DATA")][0]
        url = f["linkdownload"].replace("http://", "https://")
        return url, parse_tss(cli.get(url, "xlsx").cuerpo, int(ycat["name"]))

    por_id = {m["id"]: m for m in fin["metricas"]}
    hechos, fallos, cambiados = [], [], []
    for mid, fn in [("inflacion", ipc), ("desempleo", encft), ("crecimiento", pib), ("deuda", deuda), ("salario", salario)]:
        try:
            url, d = fn()
            d.update(textos(mid, d, poblacion))
            cli.get(PAGINAS[mid], "html")  # the page we link people to must answer 200 (gate G4)
        except (FalloFuente, KeyError, IndexError, ValueError, TypeError, ImportError, AttributeError) as e:
            fallos.append({"metrica": mid, "error": f"{type(e).__name__}: {e}"[:300]})
            print(f"{mid}: FALLÓ ({e})", file=sys.stderr)
            continue
        d["url"] = url
        d["url_pagina"] = PAGINAS[mid]
        d["datos_al"] = d["periodo_iso"]
        m = por_id.get(mid)
        if m is None:
            continue
        viejo = m.get("auto") or {}
        if viejo.get("periodo_iso") and d["periodo_iso"] < viejo["periodo_iso"]:
            fallos.append({"metrica": mid, "error": f"el archivo trae un período más viejo ({d['periodo_iso']})"})
            continue
        comparar = {k: v for k, v in d.items() if k != "revisado_el"}
        if {k: v for k, v in viejo.items() if k != "revisado_el"} != comparar:
            cambiados.append(f"{mid} ({d['periodo']})")
        d["revisado_el"] = hoy.isoformat()
        m["auto"] = d
        hechos.append(mid)
        print(f"{mid}: {d['valor_texto']} — {d['periodo']}")
    cli.guardar()
    if not hechos:
        arbol.anotar_run("dinero", estado="roto", fallos=fallos)
        print("Ninguna métrica se pudo leer: no se escribe nada.", file=sys.stderr)
        return 1
    if poblacion and (por_id.get("deuda") or {}).get("auto"):
        fin.setdefault("comparaciones_derivadas", {})["deuda_por_persona_usd"] = \
            round(por_id["deuda"]["auto"]["usd_millones"] * 1e6 / poblacion)
    fin["actualizado_auto"] = hoy.isoformat()
    arbol.escribir(FIN, fin)
    por = {mid: por_id[mid]["auto"]["periodo_iso"] for mid in hechos}
    for mid in hechos:
        arbol.anotar_run(f"dinero_{mid}", estado="ok", datos_al=por[mid], url_fuente=por_id[mid]["auto"]["url"])
    arbol.anotar_run("dinero", estado="ok" if not fallos else "parcial", fallos=fallos, cambiados=cambiados)
    print(f"listo: {len(hechos)} métricas leídas, {len(cambiados)} con cambios, {len(fallos)} fallos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
