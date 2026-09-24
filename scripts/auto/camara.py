#!/usr/bin/env python3
"""Weekly Cámara de Diputados refresh (replaces scripts/refresh_camara.py).

Numbers only, straight from the official SIL Ciudadano API
(www.diputadosrd.gob.do/sil/api/legislador/...): committees, bills proposed
(-CD) and plenary attendance for the deputies in docs/data/provincias.json.
No AI and no prose.

Fixes over the old refresh (critique 2026-09-23, Part 3 #2):
  1. The attendance period label is computed from each deputy's own first and
     last session dates. The fixed string "agosto 2024 a junio 2026" is gone.
  2. Deputies are fetched by their pinned SIL legisladorId
     (config/diputados_ids.json). Name search is used only for a new name.
     Jorge Frías (ID 1466) stopped matching by name; by ID he works.
  3. A deputy that still cannot be fetched keeps his previous numbers, marked
     with their own "datos_al" date, and is listed for an issue. The other
     deputies still publish.
  4. If the SIL profile says the term ended ("representacion.fin" in the past),
     the card gets "cargo_hasta" so the site can say so.

Sanity guard (kept from the old script): an empty pull, or totals below 80% of
the previous run, exits 1 and writes nothing.

Usage:
  python3 scripts/auto/camara.py                  # real run (writes docs/data)
  python3 scripts/auto/camara.py --dry-run        # writes to /tmp/psrd-dryrun/camara
  python3 scripts/auto/camara.py --self-test-empty
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import MESES, Arbol, hoy_et, norm, tokens  # noqa: E402
from red import Cliente, FalloFuente  # noqa: E402

BASE = "https://www.diputadosrd.gob.do/sil/api/legislador/"
URL_FUENTE = "https://www.diputadosrd.gob.do/sil"
PROV = "docs/data/provincias.json"
STATS = "scripts/diputados_stats.json"
PINS = "config/diputados_ids.json"
GUARD_FLOOR = 0.8
PERIODO_ACTUAL = "2024-2028"
ASIST_FUENTE = ("registro oficial de asistencia al Pleno de la Cámara de Diputados "
                "(SIL Ciudadano, diputadosrd.gob.do)")


def overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, min(len(ta), len(tb)))


def etiqueta_periodo(desde: str | None, hasta: str | None) -> str | None:
    """'2024-08-16', '2026-07-24' -> 'agosto 2024 a julio 2026' (from the data)."""
    if not desde or not hasta:
        return None
    d, h = date.fromisoformat(desde[:10]), date.fromisoformat(hasta[:10])
    a = f"{MESES[d.month - 1]} {d.year}"
    b = f"{MESES[h.month - 1]} {h.year}"
    return a if a == b else f"{a} a {b}"


def load_roster(prov: dict) -> list[dict]:
    out = []
    for p in prov["provincias"]:
        for l in p["lideres"]:
            if l["cargo"] == "Diputado/a":
                out.append({"nombre": l["nombre"], "provincia": p.get("nombre") or ""})
    return out


class Camara:
    def __init__(self, cliente: Cliente, hoy: date):
        self.c = cliente
        self.hoy = hoy

    def get(self, ruta: str) -> dict:
        return self.c.get(BASE + ruta, "json").json()

    def paginas(self, ruta: str) -> list[dict]:
        out: list[dict] = []
        for p in range(1, 101):
            j = self.get(ruta.format(page=p))
            res = j.get("results") or []
            out.extend(res)
            if len(out) >= (j.get("total") or 0) or not res:
                break
        return out

    def buscar_id(self, nombre: str, provincia: str) -> tuple[int | None, str]:
        cands: list[dict] = []
        for kw in (nombre, " ".join(nombre.split()[-2:])):
            try:
                j = self.get("legisladores?page=1&keyword=" + urllib.parse.quote(kw) + "&periodoId=0")
            except FalloFuente:
                continue
            cands = [c for c in (j.get("results") or []) if (c.get("funcion") or "").lower().startswith("diputad")]
            if cands:
                break
        if not cands:
            return None, "la búsqueda por nombre no encontró a nadie"
        cands.sort(key=lambda c: (-overlap(nombre, c.get("nombreCompleto") or ""),
                                  -(norm(c.get("provincia")) == norm(provincia))))
        best = cands[0]
        sc = overlap(nombre, best.get("nombreCompleto") or "")
        if sc < 0.5:
            return None, f"parecido muy bajo ({sc:.2f})"
        return best["legisladorId"], "búsqueda por nombre"

    def diputado(self, dep_id: int) -> dict:
        perfil = self.get(f"legislador/{dep_id}")
        rep = perfil.get("representacion") or {}
        comis = self.paginas(f"comisiones?page={{page}}&legisladorId={dep_id}&periodoId=0")
        inis = self.paginas(f"Iniciativas?page={{page}}&legisladorId={dep_id}&keyword=&periodoId=0")
        asis = self.paginas(f"asistencias?page={{page}}&legisladorId={dep_id}&keyword=&periodoId=0")
        presentes = 0
        breakdown: dict[str, int] = {}
        fechas = []
        for a in asis:
            t = (a.get("tipoCiudadano") or "").strip()
            breakdown[t] = breakdown.get(t, 0) + 1
            if t.lower().startswith("presente"):
                presentes += 1
            f = ((a.get("sesion") or {}).get("fecha") or "")[:10]
            if f:
                fechas.append(f)
        fin = (rep.get("fin") or "")[:10] or None
        # Only trust "fin" for the current period and a finished term; some
        # profiles still carry an older period (seen: 2020-2024 "En Curso").
        termino = (fin and rep.get("periodo") == PERIODO_ACTUAL and rep.get("ejercicio") != "En Curso"
                   and date.fromisoformat(fin) < self.hoy)
        return {
            "legisladorId": dep_id,
            "sil_nombre": " ".join((perfil.get("nombreCompleto") or "").split()),
            "cargo_hasta": fin if termino else None,
            "comisiones": sorted({(c.get("comision") or "").strip() for c in comis if (c.get("comision") or "").strip()}),
            "iniciativas_cd": sum(1 for x in inis if (x.get("numero") or "").strip().upper().endswith("-CD")),
            "iniciativas_total_sil": len(inis),
            "asistencia": {"presentes": presentes, "total": len(asis), "breakdown": breakdown,
                           "desde": min(fechas) if fechas else None, "hasta": max(fechas) if fechas else None},
        }


def aggregate(stats: dict) -> dict:
    dips = {k: v for k, v in (stats.get("diputados") or {}).items() if not v.get("_sin_actualizar")}
    return {
        "matched": len(dips),
        "comisiones_total": sum(len(d.get("comisiones") or []) for d in dips.values()),
        "iniciativas_total": sum(d.get("iniciativas_cd") or 0 for d in dips.values()),
        "asistencia_total": sum((d.get("asistencia") or {}).get("total") or 0 for d in dips.values()),
    }


def sanity_check(old: dict | None, new: dict) -> tuple[bool, str]:
    n = aggregate(new)
    if n["matched"] == 0:
        return False, "RECHAZADO: el repull no trajo a ningún diputado (API vacía o rota)."
    if not old:
        return True, f"OK (sin corrida anterior): {n}"
    o = aggregate(old)
    lineas = [f"antes: {o}", f"ahora: {n}"]
    for k in n:
        if o[k] > 0 and n[k] < o[k] * GUARD_FLOOR:
            return False, "RECHAZADO (menos del 80% de la corrida anterior en " + k + "):\n" + "\n".join(lineas)
    return True, "OK:\n" + "\n".join(lineas)


def run_pull(roster: list[dict], pins: dict, old: dict | None, fetch_id, buscar, hilos: int = 4):
    """fetch_id(id)->row, buscar(nombre, provincia)->(id|None, motivo). Pure orchestration (tested)."""
    old_rows = (old or {}).get("diputados") or {}
    old_fecha = ((old or {}).get("_generated") or "")[:10] or None
    resultado: dict[str, dict] = {}
    sin: list[dict] = []
    nuevos_pins: dict[str, int] = {}

    def uno(dip):
        nombre = dip["nombre"]
        dep_id = pins.get(nombre)
        motivo = "ID fijo"
        if dep_id is None:
            dep_id, motivo = buscar(nombre, dip["provincia"])
        if dep_id is None:
            return nombre, None, motivo, None
        try:
            return nombre, fetch_id(dep_id), motivo, dep_id
        except FalloFuente as e:
            return nombre, None, f"la API falló: {e}", dep_id

    with ThreadPoolExecutor(hilos) as ex:
        for (nombre, row, motivo, dep_id), dip in zip(ex.map(uno, roster), roster):
            if row is not None:
                row["provincia"] = dip["provincia"]
                resultado[nombre] = row
                if nombre not in pins:
                    nuevos_pins[nombre] = dep_id
                continue
            viejo = old_rows.get(nombre)
            datos_al = ((viejo or {}).get("asistencia") or {}).get("hasta") or (viejo or {}).get("datos_al") or old_fecha
            sin.append({"nombre": nombre, "provincia": dip["provincia"], "motivo": motivo, "datos_al": datos_al})
            if viejo:
                v = dict(viejo)
                v["_sin_actualizar"] = True
                v["datos_al"] = datos_al
                resultado[nombre] = v
    return {"_generated": datetime.now(timezone.utc).isoformat(), "_unmatched": sin,
            "diputados": resultado}, nuevos_pins


def fusionar(prov: dict, stats: dict) -> dict:
    """Write the pulled numbers onto the deputy cards. Only fields with a value
    are written (never blank over good data)."""
    by = {norm(n): r for n, r in stats["diputados"].items()}
    cuenta = {"comisiones": 0, "iniciativas": 0, "asistencia": 0, "sin_actualizar": 0}
    for p in prov["provincias"]:
        for l in p["lideres"]:
            if l["cargo"] != "Diputado/a":
                continue
            row = by.get(norm(l["nombre"]))
            if row is None:
                continue
            if row.get("_sin_actualizar"):
                cuenta["sin_actualizar"] += 1
                if isinstance(l.get("asistencia"), dict) and row.get("datos_al"):
                    l["asistencia"]["datos_al"] = row["datos_al"]
                    l["asistencia"]["nota"] = "No pudimos actualizar este dato esta semana; es el último que obtuvimos."
                continue
            if row.get("comisiones"):
                l["comisiones"] = row["comisiones"]
                cuenta["comisiones"] += 1
            if isinstance(row.get("iniciativas_cd"), int) and row["iniciativas_cd"] > 0:
                l["iniciativas_propuestas"] = row["iniciativas_cd"]
                cuenta["iniciativas"] += 1
            a = row.get("asistencia") or {}
            if isinstance(a.get("total"), int) and a["total"] > 0:
                periodo = etiqueta_periodo(a.get("desde"), a.get("hasta"))
                nueva = {"presentes": a["presentes"], "total": a["total"],
                         "periodo": periodo or (l.get("asistencia") or {}).get("periodo") or "",
                         "fuente": ASIST_FUENTE}
                if a.get("hasta"):
                    nueva["datos_al"] = a["hasta"]
                l["asistencia"] = nueva
                cuenta["asistencia"] += 1
            if row.get("cargo_hasta"):
                l["cargo_hasta"] = row["cargo_hasta"]
            else:
                l.pop("cargo_hasta", None)
    return cuenta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--self-test-empty", action="store_true")
    ap.add_argument("--limite", type=int, default=0, help="solo los primeros N diputados (pruebas)")
    a = ap.parse_args(argv)

    arbol = Arbol("camara", dry_run=a.dry_run)
    prov = arbol.leer(PROV)
    roster = load_roster(prov)
    if a.limite:
        roster = roster[: a.limite]
    old = arbol.leer(STATS) if arbol.existe(STATS) else None
    pins_doc = arbol.leer(PINS, {"ids": {}})
    cli = Cliente(arbol.p(".psrd-run/recibos-camara.json"), espera={"www.diputadosrd.gob.do": 0.15})
    cam = Camara(cli, hoy_et())

    if a.self_test_empty:
        new, nuevos = {"_generated": "", "_unmatched": [], "diputados": {}}, {}
    else:
        new, nuevos = run_pull(roster, pins_doc["ids"], old, cam.diputado, cam.buscar_id)
    cli.guardar()

    if a.limite and old:
        # partial pull (test mode): compare only against the same deputies
        old = {"_generated": old.get("_generated"), "diputados": {k: v for k, v in old["diputados"].items()
                                                                if k in {d["nombre"] for d in roster}}}
    ok, msg = sanity_check(old, new)
    print(msg)
    if not ok:
        arbol.anotar_run("camara_diputados", estado="roto", error=msg)
        print("Guardia de cordura: no se escribe nada.", file=sys.stderr)
        return 1

    if a.limite:
        full = arbol.leer(STATS)
        full["diputados"].update(new["diputados"])
        full["_unmatched"] = new["_unmatched"]
        full["_generated"] = new["_generated"]
        new = full
    arbol.escribir(STATS, new)
    cuenta = fusionar(prov, new)
    arbol.escribir(PROV, prov)
    if nuevos:
        pins_doc["ids"].update(nuevos)
        arbol.escribir(PINS, pins_doc)

    hastas = [((r.get("asistencia") or {}).get("hasta")) for r in new["diputados"].values() if not r.get("_sin_actualizar")]
    hastas = [h for h in hastas if h]
    arbol.anotar_run("camara_diputados", estado="ok" if not new["_unmatched"] else "parcial",
                     datos_al=max(hastas) if hastas else None,
                     sin_actualizar=new["_unmatched"], cuenta=cuenta,
                     cargo_terminado=[{"nombre": n, "cargo_hasta": r["cargo_hasta"]}
                                      for n, r in new["diputados"].items() if r.get("cargo_hasta")],
                     resumen=f"{cuenta['asistencia']} diputados actualizados")
    print(f"escrito en {arbol.raiz}: {cuenta}")
    for u in new["_unmatched"]:
        print(f"SIN ACTUALIZAR: {u['nombre']} ({u['motivo']}), datos al {u['datos_al']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
