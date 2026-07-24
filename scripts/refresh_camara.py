#!/usr/bin/env python3
"""Mechanical weekly refresh: re-pull the 178 deputies' committees, initiatives
and plenary attendance from the official SIL Ciudadano API of the Cámara de
Diputados (www.diputadosrd.gob.do/sil/api/legislador/...).

This is the MECHANICAL layer only (see dr-laws-site-notes.md L7-8): numbers
and lists straight from the government API, no kid-Spanish summaries, no
judgment. It supersedes scripts/scrape_diputados.js for automated runs —
that script drove a real Chromium via Playwright to get a Referer/origin for
the API; live testing (2026-07-09) showed the API answers plain HTTP GETs
with no browser and no Referer needed, so this version uses only the Python
standard library (urllib) and needs no browser install in CI.

Pipeline:
  1. Read the current 178-deputy roster straight from docs/data/provincias.json
     (cargo == "Diputado/a") — no external roster file needed.
  2. For each deputy, search the SIL API by name, pick the best match, then
     pull comisiones / Iniciativas (count only -CD, this chamber's own bills)
     / asistencias (tipoCiudadano presente ratio). Same matching heuristic as
     the original scrape_diputados.js (token overlap, retry with surnames).
  3. SANITY GUARD (reviewer fix #2b): compare the new pull's aggregate counts
     against the last known-good scripts/diputados_stats.json. If matched
     deputies, total comisiones, total iniciativas_cd, or total attendance
     records collapse below 80% of the prior run — or the pull is empty —
     exit nonzero and write NOTHING. A GitHub Actions job failure fires
     GitHub's native failure email; that is the alerting.
  4. On a pass: write scripts/diputados_stats.json, merge it into
     docs/data/provincias.json via scripts/fill_diputados.py (reused as-is,
     not re-implemented), and stamp docs/data/ultima-revision.json with
     today's date so the schedule has proof of a live run every week.

Usage:
  python3 scripts/refresh_camara.py              # real run
  python3 scripts/refresh_camara.py --self-test-empty   # guard break-test,
      see VERIFY section in the build report — simulates an empty API pull
      and confirms the guard exits nonzero and writes nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROVINCIAS = ROOT / "docs" / "data" / "provincias.json"
STATS_OUT = HERE / "diputados_stats.json"
HEARTBEAT = ROOT / "docs" / "data" / "ultima-revision.json"

BASE = "https://www.diputadosrd.gob.do/sil/api/legislador/"
UA = "Mozilla/5.0 (compatible; PoliticaSencillaRD-refresh/1.0; +https://github.com/politica-sencilla-rd/leyes-rd)"
TIMEOUT = 30
RETRIES = 3
SLEEP_BETWEEN = 0.15  # be polite to the government server

# Sanity guard floor: a fresh pull must retain at least this fraction of the
# prior run's counts, or the pull is treated as broken/empty and rejected.
GUARD_FLOOR = 0.8


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def tokens(s: str) -> set[str]:
    return {t for t in norm(s).split(" ") if len(t) > 1}


def overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    hit = len(ta & tb)
    return hit / max(1, min(len(ta), len(tb)))


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last_err: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
            if body.lstrip().startswith("<"):
                raise ValueError("got HTML, not JSON (API likely serving the SPA shell)")
            return json.loads(body)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def page_all(build_url: Callable[[int], str]) -> list[dict]:
    out: list[dict] = []
    for p in range(1, 61):
        j = get_json(build_url(p))
        res = j.get("results") or []
        out.extend(res)
        if len(out) >= (j.get("total") or 0) or not res:
            break
    return out


def load_roster() -> list[dict]:
    data = json.loads(PROVINCIAS.read_text())
    roster = []
    for prov in data["provincias"]:
        for lider in prov["lideres"]:
            if lider["cargo"] == "Diputado/a":
                roster.append({"nombre": lider["nombre"], "provincia": prov.get("nombre") or prov.get("provincia") or ""})
    return roster


def fetch_deputy(dip: dict) -> dict | None:
    kw = dip["nombre"].strip()
    cands = []
    try:
        j = get_json(BASE + "legisladores?page=1&keyword=" + urllib.parse.quote(kw) + "&periodoId=0")
        cands = [c for c in (j.get("results") or []) if (c.get("funcion") or "").lower().startswith("diputad")]
    except RuntimeError:
        cands = []
    if not cands:
        parts = kw.split()
        kw2 = " ".join(parts[-2:]) if len(parts) >= 2 else kw
        try:
            j = get_json(BASE + "legisladores?page=1&keyword=" + urllib.parse.quote(kw2) + "&periodoId=0")
            cands = [c for c in (j.get("results") or []) if (c.get("funcion") or "").lower().startswith("diputad")]
        except RuntimeError:
            cands = []
    if not cands:
        return {"_unmatched": True, "nombre": dip["nombre"], "reason": "no search hit"}

    def sort_key(c):
        o = overlap(dip["nombre"], c.get("nombreCompleto") or "")
        prov_match = 1 if norm(c.get("provincia") or "") == norm(dip["provincia"]) else 0
        return (-o, -prov_match)

    cands.sort(key=sort_key)
    best = cands[0]
    score = overlap(dip["nombre"], best.get("nombreCompleto") or "")
    if score < 0.5:
        return {"_unmatched": True, "nombre": dip["nombre"], "reason": f"weak match ({score:.2f})"}

    dep_id = best["legisladorId"]
    comisiones_rows = page_all(lambda p: BASE + f"comisiones?page={p}&legisladorId={dep_id}&periodoId=0")
    comisiones = sorted({(c.get("comision") or "").strip() for c in comisiones_rows if (c.get("comision") or "").strip()})

    ini_rows = page_all(lambda p: BASE + f"Iniciativas?page={p}&legisladorId={dep_id}&keyword=&periodoId=0")
    cd_inis = [x for x in ini_rows if (x.get("numero") or "").strip().upper().endswith("-CD")]

    asis_rows = page_all(lambda p: BASE + f"asistencias?page={p}&legisladorId={dep_id}&keyword=&periodoId=0")
    presentes = 0
    breakdown: dict[str, int] = {}
    for a in asis_rows:
        t = (a.get("tipoCiudadano") or "").strip()
        breakdown[t] = breakdown.get(t, 0) + 1
        if t.lower().startswith("presente"):
            presentes += 1

    return {
        "provincia": dip["provincia"],
        "legisladorId": dep_id,
        "sil_nombre": " ".join((best.get("nombreCompleto") or "").split()),
        "sil_provincia": best.get("provincia"),
        "match_score": round(score, 2),
        "comisiones": comisiones,
        "iniciativas_cd": len(cd_inis),
        "iniciativas_total_sil": len(ini_rows),
        "asistencia": {"presentes": presentes, "total": len(asis_rows), "breakdown": breakdown},
    }


def run_pull(roster: list[dict]) -> dict:
    result: dict[str, dict] = {}
    unmatched: list[dict] = []
    for i, dip in enumerate(roster, 1):
        row = fetch_deputy(dip)
        if row is None:
            continue
        if row.get("_unmatched"):
            unmatched.append({"nombre": row["nombre"], "provincia": dip["provincia"], "reason": row["reason"]})
            print(f"[{i}/{len(roster)}] UNMATCHED: {dip['nombre']} ({row['reason']})", file=sys.stderr)
        else:
            result[dip["nombre"]] = row
            print(f"[{i}/{len(roster)}] {dip['nombre']} | com={len(row['comisiones'])} "
                  f"iniCD={row['iniciativas_cd']} asist={row['asistencia']['presentes']}/{row['asistencia']['total']}",
                  file=sys.stderr)
        time.sleep(SLEEP_BETWEEN)
    return {
        "_generated": datetime.now(timezone.utc).isoformat(),
        "_unmatched": unmatched,
        "diputados": result,
    }


def aggregate(stats: dict) -> dict:
    dips = stats.get("diputados") or {}
    return {
        "matched": len(dips),
        "comisiones_total": sum(len(d.get("comisiones") or []) for d in dips.values()),
        "iniciativas_total": sum(d.get("iniciativas_cd") or 0 for d in dips.values()),
        "asistencia_total": sum((d.get("asistencia") or {}).get("total") or 0 for d in dips.values()),
    }


def sanity_check(old_stats: dict | None, new_stats: dict) -> tuple[bool, str]:
    new_agg = aggregate(new_stats)
    if new_agg["matched"] == 0:
        return False, "REJECTED: fresh pull matched 0 deputies (empty/broken API response)."
    if old_stats is None:
        return True, f"OK: no prior run to compare against. New: {new_agg}"

    old_agg = aggregate(old_stats)
    lines = [f"prior: {old_agg}", f"new:   {new_agg}"]
    for key in ("matched", "comisiones_total", "iniciativas_total", "asistencia_total"):
        prior = old_agg[key]
        new = new_agg[key]
        floor = prior * GUARD_FLOOR
        lines.append(f"  {key}: prior={prior} new={new} floor(80%)={floor:.1f} -> {'OK' if new >= floor else 'FAIL'}")
        if prior > 0 and new < floor:
            return False, "REJECTED: " + "\n".join(lines)
    return True, "OK:\n" + "\n".join(lines)


def write_heartbeat() -> None:
    HEARTBEAT.write_text(json.dumps({
        "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "fuente": "Repull automático semanal del API SIL de la Cámara de Diputados (diputadosrd.gob.do)",
        "detalle": "Comisiones, iniciativas propuestas y asistencia al pleno de los 178 diputados. "
                   "No incluye resúmenes en español fácil de proyectos de ley nuevos: esa parte la revisa "
                   "una persona, nunca se genera sola.",
    }, ensure_ascii=False, indent=1) + "\n")


def main() -> int:
    self_test_empty = "--self-test-empty" in sys.argv

    roster = load_roster()
    print(f"roster loaded: {len(roster)} deputies", file=sys.stderr)

    old_stats = json.loads(STATS_OUT.read_text()) if STATS_OUT.exists() else None

    if self_test_empty:
        new_stats = {"_generated": datetime.now(timezone.utc).isoformat(), "_unmatched": [], "diputados": {}}
        print("SELF-TEST MODE: simulating an empty API pull (no network calls made).", file=sys.stderr)
    else:
        new_stats = run_pull(roster)

    ok, message = sanity_check(old_stats, new_stats)
    print(message)
    if not ok:
        print("Sanity guard failed. No files written.", file=sys.stderr)
        return 1

    STATS_OUT.write_text(json.dumps(new_stats, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {STATS_OUT}")

    merge = subprocess.run([sys.executable, str(HERE / "fill_diputados.py")], cwd=ROOT,
                            capture_output=True, text=True)
    print(merge.stdout)
    if merge.returncode != 0:
        print(merge.stderr, file=sys.stderr)
        print("fill_diputados.py failed to merge into provincias.json.", file=sys.stderr)
        return 1

    write_heartbeat()
    print(f"wrote {HEARTBEAT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
