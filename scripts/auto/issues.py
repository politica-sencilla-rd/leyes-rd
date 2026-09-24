#!/usr/bin/env python3
"""One GitHub issue per problem, never duplicated (uses the `gh` CLI that every
GitHub runner has).

  abrir(clave, titulo, cuerpo, etiqueta)  open, or update the body of the open one
  cerrar(clave, etiqueta, comentario)     close it when the problem is gone

The key is written as a hidden marker in the body (<!-- psrd:clave -->), so a
title edit never creates a duplicate.

CLI (used by the workflows):
  python3 scripts/auto/issues.py abrir  --clave K --titulo T --etiqueta L --cuerpo-archivo F
  python3 scripts/auto/issues.py cerrar --clave K --etiqueta L [--comentario C]
  python3 scripts/auto/issues.py ia --archivo .psrd-run/ia-fallos.json
  python3 scripts/auto/issues.py run --dir . --workflow camara   (items from the run summary)
Dry run (prints what it would do, touches no issue): no GITHUB_TOKEN/GH_TOKEN, or
the repo variable PSRD_AUTOPUBLICAR is not "si" (the same kill switch as publishing).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

COLORES = {"datos-viejos": "d93f0b", "auto-resumen": "5319e7", "publicacion-bloqueada": "b60205",
           "auto-fuente": "fbca04"}


def _gh(args: list[str], entrada: str | None = None) -> str:
    r = subprocess.run(["gh", *args], input=entrada, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {r.stderr.strip()[:300]}")
    return r.stdout


def en_seco() -> bool:
    return (not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
            or os.environ.get("PSRD_AUTOPUBLICAR") != "si" or os.environ.get("PSRD_ISSUES_SECO") == "1")


def buscar(clave: str, etiqueta: str) -> int | None:
    out = _gh(["issue", "list", "--label", etiqueta, "--state", "open", "--limit", "100", "--json", "number,body"])
    for it in json.loads(out or "[]"):
        if f"<!-- psrd:{clave} -->" in (it.get("body") or ""):
            return it["number"]
    return None


def asegurar_etiqueta(etiqueta: str) -> None:
    try:
        _gh(["label", "create", etiqueta, "--color", COLORES.get(etiqueta, "ededed"), "--force"])
    except RuntimeError:
        pass


def abrir(clave: str, titulo: str, cuerpo: str, etiqueta: str) -> str:
    cuerpo = f"<!-- psrd:{clave} -->\n{cuerpo}\n\n_Lo abrió y lo mantiene el robot; se cierra solo cuando el problema se va._"
    if en_seco():
        print(f"[seco] abriría/actualizaría issue '{titulo}' ({etiqueta}, clave {clave})")
        return "seco"
    asegurar_etiqueta(etiqueta)
    n = buscar(clave, etiqueta)
    if n:
        _gh(["issue", "edit", str(n), "--body-file", "-"], entrada=cuerpo)
        return f"actualizado #{n}"
    _gh(["issue", "create", "--title", titulo, "--label", etiqueta, "--body-file", "-"], entrada=cuerpo)
    return "creado"


def cerrar(clave: str, etiqueta: str, comentario: str = "Resuelto: la condición ya no se cumple.") -> str:
    if en_seco():
        print(f"[seco] cerraría el issue con clave {clave} si está abierto")
        return "seco"
    n = buscar(clave, etiqueta)
    if n:
        _gh(["issue", "close", str(n), "--comment", comentario])
        return f"cerrado #{n}"
    return "no había"


def tabla_ia(fallos: list[dict]) -> str:
    filas = ["| id | campo | revisión que falló | intentos | fuente |", "|---|---|---|---|---|"]
    for f in fallos:
        filas.append(f"| {f['id']} | {f.get('campo', '')} | {str(f.get('pregunta', '')).replace('|', '/')} | "
                     f"{f.get('intentos', '')} | {f.get('fuente_url', '')} |")
    return "\n".join(filas)


def issues_de_run(d: Path, workflow: str) -> list[str]:
    """Item-level problems from a run summary -> one issue per source, closed when clear."""
    res = json.loads((d / ".psrd-run" / "resumen.json").read_text()) if (d / ".psrd-run" / "resumen.json").exists() else {"fuentes": {}}
    hechos = []
    for fuente, r in res["fuentes"].items():
        problemas = r.get("fallos") or r.get("sin_actualizar") or []
        extra = r.get("cargo_terminado") or []
        clave = f"fuente-{fuente}"
        if r.get("estado") in ("sin_respuesta", "roto"):
            # the whole source failed (e.g. consultoria.gov.do answers 403 to GitHub runners):
            # nothing from it was published, the other sources still were
            cuerpo = (f"Corrida de `{workflow}`. La fuente `{fuente}` no respondió bien ({r.get('estado')}): "
                      f"{str(r.get('error', ''))[:300]}\n\nNo se publicó nada de esta fuente; el sitio conserva su "
                      "último dato bueno y las demás fuentes de la corrida se publicaron normalmente.")
            hechos.append(abrir(clave, f"[auto] Fuente sin respuesta: {fuente}", cuerpo, "auto-fuente"))
        elif problemas or extra:
            cuerpo = f"Corrida de `{workflow}`. Estos elementos no se pudieron actualizar y conservan su último dato bueno:\n\n"
            cuerpo += "\n".join(f"- `{json.dumps(p, ensure_ascii=False)}`" for p in problemas)
            if extra:
                cuerpo += ("\n\nSegún el SIL de la Cámara, estos diputados ya terminaron su cargo; el sitio lo dice en su "
                           "tarjeta, pero la lista de diputados (quién lo reemplaza) no la cambia el robot:\n\n")
                cuerpo += "\n".join(f"- {x['nombre']}: hasta {x['cargo_hasta']}" for x in extra)
            hechos.append(abrir(clave, f"[auto] Datos sin actualizar: {fuente}", cuerpo, "auto-fuente"))
        else:
            hechos.append(cerrar(clave, "auto-fuente"))
    return hechos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["abrir", "cerrar", "ia", "run"])
    ap.add_argument("--clave")
    ap.add_argument("--titulo")
    ap.add_argument("--etiqueta", default="auto-fuente")
    ap.add_argument("--cuerpo-archivo")
    ap.add_argument("--comentario", default="Resuelto: la condición ya no se cumple.")
    ap.add_argument("--archivo")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--workflow", default="")
    a = ap.parse_args(argv)
    if a.accion == "abrir":
        print(abrir(a.clave, a.titulo, Path(a.cuerpo_archivo).read_text(encoding="utf-8"), a.etiqueta))
    elif a.accion == "cerrar":
        print(cerrar(a.clave, a.etiqueta, a.comentario))
    elif a.accion == "ia":
        f = Path(a.archivo)
        fallos = json.loads(f.read_text()) if f.exists() else []
        if fallos:
            print(abrir("auto-resumen", "[auto] Resúmenes que no pasaron la revisión",
                        "Estos resúmenes automáticos NO se publicaron porque no pasaron todas las revisiones. "
                        "El sitio muestra el dato oficial y el enlace. Se reintentan solos (máximo 3 veces).\n\n"
                        + tabla_ia(fallos), "auto-resumen"))
        else:
            print(cerrar("auto-resumen", "auto-resumen", "Todos los resúmenes pendientes pasaron o se retiraron."))
    else:
        print("\n".join(issues_de_run(Path(a.dir), a.workflow)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
