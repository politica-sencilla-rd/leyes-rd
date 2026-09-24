#!/usr/bin/env python3
"""Weekly bills refresh (Cámara SIL) -> docs/data/leyes.json.

Source: the Cámara de Diputados' public SIL API
(www.diputadosrd.gob.do/sil/api/iniciativa/getIniciativas), every bill and
resolution, both chambers of origin. Data only; no prose.

What changes on the site, all decided by code:
  - A bill we already track automatically ("auto": true) gets its new status
    (votando / aprobada / vencida / retirada / rechazada) and its "datos_al".
  - A bill ("Proyecto de Ley") that newly PASSED at least one vote, or was
    promulgated, since last week enters the list with its official title, its
    SIL number and a link to the official search. Its plain-Spanish title is
    queued for the AI writer (never written here).
  - The 31 hand-written entries have no SIL number: they are never touched.
Change detection compares each bill's status with last week's copy
(pipeline-state/sil_snapshot.json), not "fechaUltimoCambioPrincipal", which the
Cámara bulk-reset on 2,290 rows on 2026-07-24.
The first run only saves that copy (baseline) and adds nothing.

Usage: python3 scripts/auto/leyes.py [--dry-run] [--max-nuevas 40]
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import Arbol, encolar, guardar_texto_fuente, hoy_et  # noqa: E402
from red import Cliente, FalloFuente  # noqa: E402

API = "https://www.diputadosrd.gob.do/sil/api/iniciativa/getIniciativas?keyword=&page={page}"
URL_OFICIAL = "https://www.diputadosrd.gob.do/sil"
LEYES = "docs/data/leyes.json"
SNAP = "pipeline-state/sil_snapshot.json"
MAX_NUEVAS = 40
MIN_FILAS = 5000  # the SIL had 6,357 rows on 2026-09-24; a much smaller pull is a broken source


def mapear_estado(estado_sil: str, conf: dict) -> str:
    for destino, lista in conf["estado"].items():
        if estado_sil in lista:
            return destino
    return "votando"


def sector_de(materia: str | None, conf: dict) -> str:
    return conf["materia_a_sector"].get((materia or "").strip().upper(), "otros")


def escanear(cli: Cliente, hilos: int = 4) -> list[dict]:
    first = cli.get(API.format(page=1), "json").json()
    paginas = (int(first["total"]) + 9) // 10
    filas = list(first["results"])

    def uno(p):
        return cli.get(API.format(page=p), "json").json()["results"]
    with ThreadPoolExecutor(hilos) as ex:
        for res in ex.map(uno, range(2, paginas + 1)):
            filas += res
    unicos = {r["id"]: r for r in filas}
    if len(unicos) < int(first["total"]) * 0.98:
        raise FalloFuente(f"el SIL dice {first['total']} filas y llegaron {len(unicos)}")
    return list(unicos.values())


def titulo_legible(desc: str) -> str:
    t = " ".join((desc or "").split()).rstrip(".")
    if t.isupper():
        t = t.lower()
    return t[:1].upper() + t[1:]


def aplicar(filas: list[dict], snap: dict | None, data: dict, conf: dict, hoy: str, max_nuevas: int):
    """Pure core (unit-tested). Returns (data, new_snapshot, report)."""
    nuevo_snap: dict[str, list] = {}
    rep = {"linea_base": snap is None, "actualizadas": [], "nuevas": [], "diferidas": 0}
    auto = {l["sil_id"]: l for s in data["sectores"] for l in s["leyes"] if l.get("auto") and l.get("sil_id")}
    califican = set(conf["entra_si"])
    candidatas = []
    for r in filas:
        k = str(r["id"])
        actual = [r.get("estado"), r.get("numPromulgacion")]
        antes = (snap or {}).get(k)
        nuevo_snap[k] = actual
        if snap is None or antes == actual:
            continue
        if r["id"] in auto:
            l = auto[r["id"]]
            l["estado"] = mapear_estado(r["estado"], conf)
            l["estado_sil"] = r["estado"]
            l["datos_al"] = hoy
            rep["actualizadas"].append(r["numero"])
        elif r.get("tipo") == "Proyecto de Ley" and r.get("estado") in califican:
            candidatas.append((r, antes))
    candidatas.sort(key=lambda x: x[0].get("fechaUltimoCambioPrincipal") or "", reverse=True)
    sectores = {s["id"]: s for s in data["sectores"]}
    for r, antes in candidatas[max_nuevas:]:
        # deferred to next run: keep last week's value so the change is seen again
        if antes is None:
            nuevo_snap.pop(str(r["id"]), None)
        else:
            nuevo_snap[str(r["id"])] = antes
        rep["diferidas"] += 1
    for r, _ in candidatas[:max_nuevas]:
        sid = sector_de(r.get("materia"), conf)
        if sid not in sectores:
            sectores[sid] = {"id": sid, **conf["sector_otros"], "leyes": []}
            data["sectores"].append(sectores[sid])
        entrada = {"id": r["numero"], "sil_id": r["id"], "titulo": titulo_legible(r["descripcion"]),
                   "titulo_oficial": " ".join(r["descripcion"].split()), "estado": mapear_estado(r["estado"], conf),
                   "estado_sil": r["estado"], "votos": [], "camara": r.get("camaraInicio") == "Cámara de Diputados",
                   "origen": r.get("camaraInicio"), "materia": r.get("materia"), "url_oficial": URL_OFICIAL,
                   "datos_al": hoy, "auto": True}
        sectores[sid]["leyes"].insert(0, entrada)
        rep["nuevas"].append(entrada)
    return data, nuevo_snap, rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-nuevas", type=int, default=MAX_NUEVAS)
    a = ap.parse_args(argv)
    arbol = Arbol("leyes", dry_run=a.dry_run)
    conf = arbol.leer("config/sil.json")
    data = arbol.leer(LEYES)
    snap = arbol.leer(SNAP) if arbol.existe(SNAP) else None
    cli = Cliente(arbol.p(".psrd-run/recibos-leyes.json"), espera={"www.diputadosrd.gob.do": 0.1})
    try:
        filas = escanear(cli)
    except FalloFuente as e:
        cli.guardar()
        arbol.anotar_run("leyes_sil", estado="sin_respuesta", error=str(e))
        print(f"EL SIL FALLÓ: {e}", file=sys.stderr)
        return 1
    cli.guardar()
    if len(filas) < MIN_FILAS:
        arbol.anotar_run("leyes_sil", estado="roto", error=f"solo {len(filas)} filas")
        print(f"Solo {len(filas)} filas: fuente rota, no se escribe nada.", file=sys.stderr)
        return 1
    hoy = hoy_et().isoformat()
    data, nuevo_snap, rep = aplicar(filas, snap.get("filas") if snap else None, data, conf, hoy, a.max_nuevas)
    cola = 0
    for e in rep["nuevas"]:
        sha = guardar_texto_fuente(arbol, e["titulo_oficial"])
        if encolar(arbol, {"id": "sil-" + e["id"], "tipo": "titulo_voto", "campos": ["titulo_facil"],
                           "estado_ley": e["estado"], "fuente_url": URL_OFICIAL,
                           "fuente_nombre": f"SIL de la Cámara, iniciativa {e['id']}", "fuente_sha256": sha}):
            cola += 1
    if rep["actualizadas"] or rep["nuevas"]:
        arbol.escribir(LEYES, data)
    arbol.escribir(SNAP, {"_nota": "Estado de cada iniciativa del SIL la semana pasada: {id: [estado, numPromulgacion]}. "
                                   "leyes.py compara contra esto para ver qué cambió.",
                          "fecha": hoy, "filas": nuevo_snap})
    ult = max((r.get("fechaDeposito") or "")[:10] for r in filas)
    arbol.anotar_run("leyes_sil", estado="ok", filas=len(filas), linea_base=rep["linea_base"],
                     actualizadas=rep["actualizadas"], nuevas=[e["id"] for e in rep["nuevas"]],
                     diferidas=rep["diferidas"], encolados=cola, subido_por_la_fuente=ult,
                     ultimo_documento=f"{len(filas)} iniciativas en el SIL")
    print(f"listo: {len(filas)} filas; línea base: {rep['linea_base']}; {len(rep['actualizadas'])} actualizadas; "
          f"{len(rep['nuevas'])} nuevas; {rep['diferidas']} para la próxima corrida")
    return 0


if __name__ == "__main__":
    sys.exit(main())
