#!/usr/bin/env python3
"""Write Lane A report-card data into docs/data/provincias.json for the 178
deputies (2024-2028 legislature).

Source — fetched live by scripts/scrape_diputados.js from the official SIL
Ciudadano API of the Cámara de Diputados (www.diputadosrd.gob.do/sil/api):
  - comisiones[]            committees the deputy currently sits on
  - iniciativas_propuestas  count of Cámara-origin (-CD) bills the deputy
                            authored/co-authored this period
  - asistencia              plenary attendance (presentes / total) read from the
                            citizen-facing "tipoCiudadano" status per session

Reuses the same field names and shapes the Senate cards already use, so the
existing render in src/app.ts picks them up with no code change. A field is
written only when the source has a value; missing data leaves the card as-is.
Every deputy in diputados_stats.json matched by name with score >= 0.7, so no
roster entry is left unmatched (verified at scrape time, _unmatched == []).
"""
import json
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROV = ROOT / "docs" / "data" / "provincias.json"
STATS = HERE / "diputados_stats.json"

ASIST_FUENTE = (
    "registro oficial de asistencia al Pleno de la Cámara de Diputados "
    "(SIL Ciudadano, diputadosrd.gob.do)"
)
ASIST_PERIODO = "agosto 2024 a junio 2026"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def main() -> None:
    stats = json.loads(STATS.read_text())["diputados"]
    # Index the scraped stats by normalized name for a robust lookup.
    by_name = {norm(name): row for name, row in stats.items()}

    data = json.loads(PROV.read_text())
    n_com = n_ini = n_asist = 0
    missing: list[str] = []

    for prov in data["provincias"]:
        for lider in prov["lideres"]:
            if lider["cargo"] != "Diputado/a":
                continue
            row = by_name.get(norm(lider["nombre"]))
            if row is None:
                missing.append(lider["nombre"])
                continue

            comisiones = row.get("comisiones") or []
            if comisiones:
                lider["comisiones"] = comisiones
                n_com += 1

            n_cd = row.get("iniciativas_cd")
            if isinstance(n_cd, int) and n_cd > 0:
                lider["iniciativas_propuestas"] = n_cd
                n_ini += 1

            asist = row.get("asistencia") or {}
            presentes = asist.get("presentes")
            total = asist.get("total")
            if isinstance(total, int) and total > 0:
                lider["asistencia"] = {
                    "presentes": presentes,
                    "total": total,
                    "periodo": ASIST_PERIODO,
                    "fuente": ASIST_FUENTE,
                }
                n_asist += 1

    # indent=2 matches the file's actual committed style (verified against
    # the file on disk 2026-07-09) — indent=1 here previously reformatted
    # the WHOLE file on every run, turning a ~500-value update into a
    # 50k+ line diff that nobody could realistically review.
    PROV.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"comisiones written for {n_com}/178 deputies")
    print(f"iniciativas_propuestas written for {n_ini}/178 deputies")
    print(f"asistencia written for {n_asist}/178 deputies")
    if missing:
        print(f"UNMATCHED ({len(missing)}): {missing}")
    else:
        print("all 178 deputies matched")


if __name__ == "__main__":
    main()
