#!/usr/bin/env python3
"""Writes docs/data/estado-fuentes.json: per source, how fresh the data really is.

  datos_al       computed FROM THE DATA (never from the run date):
                   Senate  = newest session date read from an acta
                   Cámara  = newest plenary session in the deputies' attendance
                   leyes   = the day the whole SIL was last read
                   vigencia= newest Gaceta publication date among our laws
                   dinero  = each card's own period (e.g. 2026-08 for August)
  revisado_el    the day a workflow last checked that source (only sources in
                 this run's .psrd-run/resumen.json move)
  estado         ok / parcial / sin_respuesta / roto (from the run)
  fallos_seguidos consecutive failed checks (frescura.py opens an issue at 2)

The site shows, per section: "Datos al 22 jul 2026 · revisado el 29 sep 2026".
This replaces the old single heartbeat date that made July data look fresh.

Usage: python3 scripts/auto/datos_al.py [--dir <tree>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import ROOT, Arbol, hoy_et  # noqa: E402

EF = "docs/data/estado-fuentes.json"


def desde_datos(arbol: Arbol) -> dict[str, dict]:
    out: dict[str, dict] = {}
    ses = arbol.leer("docs/data/sesiones.json")
    buenas = [s for s in ses["sesiones"] if s.get("estado") != "no_procesada"]
    if buenas:
        ult = max(buenas, key=lambda s: s["fecha"])
        out["senado_actas"] = {"datos_al": ult["fecha"], "ultimo_leido": f"Acta {ult['acta']}"}
    prov = arbol.leer("docs/data/provincias.json")
    fechas = [(l.get("asistencia") or {}).get("datos_al") for p in prov["provincias"] for l in p["lideres"]
              if l["cargo"] == "Diputado/a"]
    fechas = [f for f in fechas if f]
    if fechas:
        out["camara_diputados"] = {"datos_al": max(fechas)}
    if arbol.existe("pipeline-state/sil_snapshot.json"):
        out["leyes_sil"] = {"datos_al": arbol.leer("pipeline-state/sil_snapshot.json").get("fecha")}
    vig = arbol.leer("docs/data/vigencia.json")
    pubs = [l.get("publicada") or l.get("promulgada") for l in vig["leyes"]]
    pubs = [p for p in pubs if p]
    if pubs:
        out["vigencia_consultoria"] = {"datos_al": max(pubs)}
    fin = arbol.leer("docs/data/finanzas.json")
    for m in fin.get("metricas", []):
        if m.get("auto"):
            out[f"dinero_{m['id']}"] = {"datos_al": m["auto"]["periodo_iso"], "periodo": m["auto"]["periodo"]}
    return out


def actualizar(viejo: dict, calculado: dict, run: dict, conf: dict, hoy: str) -> dict:
    """Pure merge (unit-tested)."""
    fuentes = {}
    for k, c in conf["fuentes"].items():
        e = dict(viejo.get(k) or {})
        e.update({"nombre": c["nombre"], "seccion": c["seccion"], "url_fuente": c["url_fuente"], "retraso": c["retraso"]})
        e.update(calculado.get(k, {}))
        r = run.get(k) or (run.get("dinero") if k.startswith("dinero_") and run.get("dinero", {}).get("estado") == "roto" else None)
        if r:
            e["revisado_el"] = hoy
            e["estado"] = r.get("estado", "ok")
            if r.get("ultimo_documento"):
                e["ultimo_documento"] = r["ultimo_documento"]
            if r.get("subido_por_la_fuente"):
                e["subido_por_la_fuente"] = r["subido_por_la_fuente"]
            e["fallos_seguidos"] = (e.get("fallos_seguidos", 0) + 1) if e["estado"] in ("roto", "sin_respuesta") else 0
            if r.get("pendientes_en_fuente") is not None:
                e["pendientes_en_fuente"] = r["pendientes_en_fuente"]
        e.setdefault("estado", "sin_revisar")
        e.setdefault("fallos_seguidos", 0)
        fuentes[k] = e
    return fuentes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT))
    a = ap.parse_args(argv)
    arbol = Arbol("datos_al", base=Path(a.dir))
    conf = arbol.leer("config/fuentes.json")
    viejo = arbol.leer(EF, {"fuentes": {}}).get("fuentes", {})
    run = arbol.resumen_run().get("fuentes", {})
    fuentes = actualizar(viejo, desde_datos(arbol), run, conf, hoy_et().isoformat())
    arbol.escribir(EF, {"_nota": "Qué tan al día está cada fuente. 'datos_al' sale de los propios datos (la fecha "
                                 "más nueva que trae la fuente); 'revisado_el' es el último día que el robot la revisó. "
                                 "Lo escribe scripts/auto/datos_al.py en cada corrida.",
                        "fuentes": fuentes})
    if run:  # heartbeat kept for continuity; the honest dates are per section above
        u = arbol.leer("docs/data/ultima-revision.json", {"fuente": "", "detalle": ""})
        u["fecha"] = hoy_et().isoformat()
        u["fuente"] = "Robots automáticos del sitio (GitHub Actions) sobre las fuentes oficiales"
        arbol.escribir("docs/data/ultima-revision.json", u)
    for k, e in fuentes.items():
        print(f"{k}: datos al {e.get('datos_al')}, revisado {e.get('revisado_el')}, {e['estado']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
