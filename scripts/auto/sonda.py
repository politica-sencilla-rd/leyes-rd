#!/usr/bin/env python3
"""Phase 0 probe (manual workflow sonda.yml): can a GitHub runner reach every
official source, and does one Gemini call work? One request per source (the
Senate one respects its 120 s crawl-delay). Writes .psrd-run/sonda.json and
prints a table. Never commits.

Usage: python3 scripts/auto/sonda.py [--sin-ia]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import ROOT  # noqa: E402
from red import Cliente, FalloFuente  # noqa: E402

FUENTES = [
    ("Cámara SIL (legisladores)", "https://www.diputadosrd.gob.do/sil/api/legislador/legislador/1466", "json", None),
    ("Cámara SIL (iniciativas)", "https://www.diputadosrd.gob.do/sil/api/iniciativa/getIniciativas?keyword=&page=1", "json", None),
    ("Senado actas (listado)", "https://www.senadord.gob.do/wp-admin/admin-ajax.php?juwpfisadmin=false&action=wpfd"
                               "&task=files.display&view=files&id=1387&rootcat=1387&page=1", "json", None),
    ("Consultoría (gacetas)", "https://www.consultoria.gov.do/api/documents?category=gacetas", "json", None),
    ("Consultoría (búsqueda)", "https://www.consultoria.gov.do/api/consultas/search", "json",
     {"DocumentTypeCode": 1, "DocumentNumber": "", "FullText": "", "Name": "", "LastName": "", "Identification": "",
      "Charge": "", "Institution": 0, "President": 0, "Consultor": 0, "Career": 0, "Guild": 0, "PensionType": 0,
      "PublicationYear": time.strftime("%Y")}),
    ("BCRD IPC", "https://cdn.bancentral.gov.do/documents/estadisticas/precios/documents/ipc_base_2019-2020.xls", "xls", None),
    ("Crédito Público", "https://www.creditopublico.gob.do/inicio/estadisticas", "html", None),
    ("TSS (WPFD)", "https://tss.gob.do/wp-admin/admin-ajax.php?juwpfisadmin=false&action=wpfd&task=categories.display"
                   "&view=categories&id=121&top=121", "json", None),
    ("Sitio publicado", "https://politica-sencilla-rd.github.io/leyes-rd/data/novedades.json", "json", None),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-ia", action="store_true")
    a = ap.parse_args(argv)
    out = ROOT / ".psrd-run"
    out.mkdir(exist_ok=True)
    cli = Cliente(out / "recibos-sonda.json", timeout=60, reintentos=1)
    filas = []
    for nombre, url, tipo, cuerpo in FUENTES:
        t = time.monotonic()
        try:
            data = json.dumps(cuerpo).encode() if cuerpo else None
            r = cli.get(url, tipo, data=data, cabeceras={"Content-Type": "application/json"} if cuerpo else None)
            filas.append({"fuente": nombre, "ok": True, "status": r.status, "bytes": len(r.cuerpo),
                          "segundos": round(time.monotonic() - t, 1)})
        except FalloFuente as e:
            filas.append({"fuente": nombre, "ok": False, "error": str(e)[:200], "segundos": round(time.monotonic() - t, 1)})
    if not a.sin_ia:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            filas.append({"fuente": "Gemini", "ok": False, "error": "falta GEMINI_API_KEY"})
        else:
            import escribir as E
            conf = json.loads((ROOT / "config" / "ia.json").read_text())
            g = E.Gemini(conf, key)
            for m in (conf["escritores"][0], conf["revisores"][0]):
                t = time.monotonic()
                try:
                    txt = g.generar(m, "¿Es Santo Domingo la capital de República Dominicana? Responde con UNA sola palabra: SI o NO.")
                    filas.append({"fuente": f"Gemini {m}", "ok": True, "respuesta": txt.strip()[:20],
                                  "segundos": round(time.monotonic() - t, 1)})
                except E.Rechazo as e:
                    filas.append({"fuente": f"Gemini {m}", "ok": False, "error": str(e)[:200]})
    cli.guardar()
    (out / "sonda.json").write_text(json.dumps(filas, ensure_ascii=False, indent=1))
    for f in filas:
        print(f"{'OK ' if f['ok'] else 'MAL'} {f['fuente']}: {f.get('status', '')} {f.get('bytes', '')} "
              f"{f.get('respuesta', '')}{f.get('error', '')} ({f.get('segundos', '')} s)")
    return 0 if all(f["ok"] for f in filas) else 1


if __name__ == "__main__":
    sys.exit(main())
