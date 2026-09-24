#!/usr/bin/env python3
"""Mechanical publish gates G0-G10 (design section 3). G8 also freezes hand-written records.

Compares the NEW tree (the working tree, or a dry-run copy) against the BASE
(origin/main after the rebase, or a directory). Any failure exits 1: nothing is
committed and the job goes red. No human reads this before publishing; this
script is the reviewer.

  python3 scripts/gates/run_gates.py --base-ref origin/main
  python3 scripts/gates/run_gates.py --base-dir . --new-dir /tmp/psrd-dryrun/senado

G7 repairs as it checks: an emptied field gets its old value back in the new
tree (written in place). More than 5 repairs = broken source = fail.

The rulebook (config/ia.json, neutralidad.json, personas_publicas.json,
dominios_oficiales.json, senado.json) is read from the BASE, never from the
tree being checked, and G0 blocks any change to config/ other than
config/diputados_ids.json: a commit can't loosen the rules it is judged by.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "auto"))
# Shared with escribir.py / dinero.py so the writer and the gate never disagree.
from comun import (MESES, PARECE_LEY, PERIODO, estado_ley_de, nombra_persona, numero_en_letras,  # noqa: E402
                   numeros_ausentes, patrones_nombres, problema_metrica, valor_previo)
from camara import ASIST_FUENTE, CAMPOS_ROBOT, NOTA_SIN_ACTUALIZAR  # noqa: E402
from dinero import textos as textos_dinero  # noqa: E402
from novedades import APORTE, NOMBRE_METRICA, construir_xml, es_plantilla  # noqa: E402
from senado_actas import es_motivo  # noqa: E402
from vigencia import es_texto_vigencia  # noqa: E402
PROSA = {"que_es", "por_que", "te_afecta", "titulo_facil", "en_30_segundos", "resumen", "resumen_corto"}
CLAVES_LISTA = ("acta", "numero", "id", "iniciativa", "nombre", "legisladorId", "fecha", "titulo")
VOTO_SENADO_OK = {"iniciativa", "titulo", "titulo_facil", "a_favor", "presentes", "resultado",
                  "votacion_num", "fuente", "nota"}
LIMITES = {"sesiones_actas": 30, "sesiones_votos": 250, "leyes_cambiadas": 60, "leyes_nuevas": 40,
           "vigencia_nuevas": 10, "finanzas_metricas": 9, "novedades_nuevas": 1, "resumenes_nuevos": 20}
MAX_REPARACIONES_G7 = 5
# The only config file a robot may change (camara.py adds SIL IDs of new deputies).
CONFIG_ROBOT = {"config/diputados_ids.json"}
# A summary's stored source text must be at least this long. A Senate/SIL vote
# title is one official line (the shortest real one is 40 characters); a bill or
# law text is much longer.
MIN_FUENTE = {"titulo_voto": 30}
MIN_FUENTE_DEFECTO = 100
CHECKS_POR_CAMPO = 5  # escribir.py asks Q1-Q5 (Q6 too when not law) about every sentence
APROBADO = ("aprobada", "promulgada")
# Fields leyes.py writes on an auto bill: all of them on a new one, only these on an existing one.
LEY_AUTO_CAMPOS = {"id", "sil_id", "titulo", "titulo_oficial", "estado", "estado_sil", "votos", "camara", "origen",
                   "materia", "url_oficial", "datos_al", "auto"}
LEY_AUTO_CAMBIAN = {"estado", "estado_sil", "datos_al"}
FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")
_MES_ANIO = rf"(?:{'|'.join(MESES)}) \d{{4}}"
PERIODO_ASIS = re.compile(rf"{_MES_ANIO}(?: a {_MES_ANIO})?")  # camara.etiqueta_periodo()


# ------------------------------------------------------------------ trees
class Lado:
    """One side of the comparison: a directory or a git ref."""

    def __init__(self, dir: Path | None = None, ref: str | None = None, repo: Path = ROOT):
        self.dir, self.ref, self.repo = dir, ref, repo

    def texto(self, rel: str) -> str | None:
        if self.dir is not None:
            f = self.dir / rel
            return f.read_text(encoding="utf-8") if f.exists() else None
        r = subprocess.run(["git", "show", f"{self.ref}:{rel}"], cwd=self.repo, capture_output=True)
        return r.stdout.decode("utf-8") if r.returncode == 0 else None

    def json(self, rel: str):
        t = self.texto(rel)
        return json.loads(t) if t is not None else None

    def archivos(self, prefijo: str) -> list[str]:
        if self.dir is not None:
            base = self.dir / prefijo
            if not base.exists():
                return []
            return sorted(str(p.relative_to(self.dir)) for p in base.rglob("*") if p.is_file())
        r = subprocess.run(["git", "ls-tree", "-r", "--name-only", self.ref, prefijo], cwd=self.repo,
                           capture_output=True, text=True)
        return sorted(r.stdout.split())


def _vacio(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _clave(items: list) -> str | None:
    if not items or not all(isinstance(x, dict) for x in items):
        return None
    for k in CLAVES_LISTA:
        vals = [x.get(k) for x in items]
        if all(v is not None for v in vals) and len(set(map(str, vals))) == len(vals):
            return k
    return None


def recorrer(base, nuevo, ruta="$", visitar=None):
    """Walk base/new in parallel; lists of dicts matched by a stable key."""
    visitar(ruta, base, nuevo)
    if isinstance(base, dict) and isinstance(nuevo, dict):
        for k in base:
            if k in nuevo:
                recorrer(base[k], nuevo[k], f"{ruta}.{k}", visitar)
    elif isinstance(base, list) and isinstance(nuevo, list):
        k = _clave(base) if _clave(base) and _clave(base) == _clave(nuevo) else None
        if k:
            idx = {str(x[k]): x for x in nuevo}
            for x in base:
                if str(x[k]) in idx:
                    recorrer(x, idx[str(x[k])], f"{ruta}[{k}={x[k]}]", visitar)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


# ------------------------------------------------------------------ gates
class Gates:
    def __init__(self, base: Lado, nuevo_dir: Path, conf_dir: Path | None, schemas_dir: Path, recibos: list[dict]):
        # conf_dir is ignored (kept so old callers still work): the rulebook comes from the BASE.
        self.base = base
        self.nd = nuevo_dir
        self.nuevo = Lado(dir=nuevo_dir)
        self.schemas = schemas_dir
        self.recibos = recibos
        self.fallos: list[str] = []
        self.avisos: list[str] = []
        self.reparaciones: list[str] = []
        self.dominios = set(self._conf("dominios_oficiales.json", {"dominios": []})["dominios"])

    def _conf(self, name, defecto):
        """Rulebook from the BASE (main), never from the tree under review. Missing = fail closed."""
        t = self.base.texto(f"config/{name}")
        if t is None:
            self.fallo("G0", f"config/{name} no existe en la base: sin reglas no se publica")
            return defecto
        return json.loads(t)

    def fallo(self, g: str, msg: str):
        self.fallos.append(f"{g}: {msg}")

    def datos(self) -> list[str]:
        return sorted({p for p in self.nuevo.archivos("docs/data") if p.endswith(".json")})

    # G0 ---------------------------------------------------------------
    def g0_config(self):
        """No config file may change in a robot commit, except config/diputados_ids.json."""
        for rel in sorted(set(self.base.archivos("config")) | set(self.nuevo.archivos("config"))):
            if rel in CONFIG_ROBOT:
                continue
            if self.base.texto(rel) != self.nuevo.texto(rel):
                self.fallo("G0", f"{rel} es distinto de la base: las reglas solo se cambian a mano, en un PR")

    # G1 ---------------------------------------------------------------
    def g1_esquemas(self):
        import jsonschema  # installed in every workflow
        for rel in self.datos():
            nombre = Path(rel).name.replace(".json", "")
            sch = self.schemas / f"{nombre}.schema.json"
            if not sch.exists():
                self.fallo("G1", f"{rel} no tiene esquema en schemas/")
                continue
            try:
                data = self.nuevo.json(rel)
            except json.JSONDecodeError as e:
                self.fallo("G1", f"{rel} no es JSON válido: {e}")
                continue
            v = jsonschema.Draft202012Validator(json.loads(sch.read_text(encoding="utf-8")))
            errs = sorted(v.iter_errors(data), key=lambda e: list(e.path))
            for e in errs[:5]:
                self.fallo("G1", f"{rel} {'/'.join(map(str, e.path))}: {e.message[:200]}")
        # Only the known JSON files may appear or change under docs/data (publicar.sh adds the whole
        # folder and Pages serves it): a stray .html/.js would pass every other gate.
        for rel in sorted(set(self.nuevo.archivos("docs/data")) | set(self.base.archivos("docs/data"))):
            if not rel.endswith(".json") and self.nuevo.texto(rel) != self.base.texto(rel):
                self.fallo("G1", f"{rel}: en docs/data solo pueden cambiar archivos .json con esquema")
        xml = self.nuevo.texto("docs/novedades.xml")
        if xml is not None:
            try:
                ET.fromstring(xml.encode("utf-8"))
            except ET.ParseError as e:
                self.fallo("G1", f"docs/novedades.xml no es XML válido: {e}")

    # G2 ---------------------------------------------------------------
    def g2_sin_votos_por_senador(self):
        ses = self.nuevo.json("docs/data/sesiones.json") or {"sesiones": []}
        for s in ses["sesiones"]:
            for v in s.get("votaciones", []):
                extra = set(v) - VOTO_SENADO_OK
                if extra:
                    self.fallo("G2", f"sesiones acta {s['acta']}: campos no permitidos en una votación: {sorted(extra)}")
        leyes = self.nuevo.json("docs/data/leyes.json") or {"sectores": []}
        for sec in leyes["sectores"]:
            for l in sec["leyes"]:
                if l.get("votos") and not l.get("camara"):
                    self.fallo("G2", f"leyes '{l.get('titulo', '')[:50]}': trae votos con nombre y no es de la Cámara")
        prov = self.nuevo.json("docs/data/provincias.json") or {"provincias": []}
        for p in prov["provincias"]:
            for l in p["lideres"]:
                if str(l.get("cargo", "")).startswith("Senador") and (l.get("votos") or l.get("votaciones_pleno")):
                    self.fallo("G2", f"provincias {p['nombre']}: el senador {l['nombre']} trae votos por nombre")
        app = (self.nd / "src" / "app.ts")
        app_txt = app.read_text(encoding="utf-8") if app.exists() else (ROOT / "src" / "app.ts").read_text(encoding="utf-8")
        if "const MOSTRAR_VOTOS_POR_SENADOR = false;" not in app_txt:
            self.fallo("G2", "src/app.ts ya no dice 'const MOSTRAR_VOTOS_POR_SENADOR = false;'")
        for rel in self.nuevo.archivos("docs"):
            if fnmatch.fnmatch(rel.lower(), "*votos-senado*") or fnmatch.fnmatch(rel.lower(), "*votos_por_sesion*"):
                self.fallo("G2", f"{rel}: archivo de votos por senador dentro de docs/")
        for rel in self.datos():
            self._buscar_rollos(self.nuevo.json(rel), rel)

    def _buscar_rollos(self, o, rel, ruta="$"):
        if isinstance(o, dict):
            ks = {k.lower() for k in o}
            if ({"senator", "senador"} & ks) and ({"vote", "voto"} & ks):
                self.fallo("G2", f"{rel} {ruta}: parece un voto con nombre de senador")
                return
            for k, v in o.items():
                self._buscar_rollos(v, rel, f"{ruta}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                self._buscar_rollos(v, rel, f"{ruta}[{i}]")

    # G3 ---------------------------------------------------------------
    def g3_totales(self):
        ses = self.nuevo.json("docs/data/sesiones.json") or {"sesiones": []}
        for s in ses["sesiones"]:
            if s.get("estado") == "no_procesada":
                continue
            for v in s.get("votaciones", []):
                if not (0 <= v["a_favor"] <= v["presentes"] <= 32):
                    self.fallo("G3", f"acta {s['acta']} {v['iniciativa']}: {v['a_favor']} a favor / {v['presentes']} presentes")
                elif v["presentes"] < 17:
                    self.fallo("G3", f"acta {s['acta']} {v['iniciativa']}: {v['presentes']} presentes (< 17)")
            a = s.get("asistencia") or {}
            if a.get("presentes") is not None and a["presentes"] + (a.get("ausentes") or 0) > 32:
                self.fallo("G3", f"acta {s['acta']}: presentes + ausentes > 32")
            if a.get("detalle") and a.get("ausentes") is not None and len(a["detalle"]) != a["ausentes"]:
                self.fallo("G3", f"acta {s['acta']}: {len(a['detalle'])} nombres pero {a['ausentes']} ausentes")
        prov = self.nuevo.json("docs/data/provincias.json") or {"provincias": []}
        for p in prov["provincias"]:
            for l in p["lideres"]:
                a = l.get("asistencia")
                if isinstance(a, dict) and a.get("total") is not None:
                    if not (0 <= (a.get("presentes") or 0) <= a["total"]):
                        self.fallo("G3", f"{l['nombre']}: asistencia {a.get('presentes')}/{a['total']}")
                vp = l.get("votaciones_pleno")
                if isinstance(vp, dict) and not (0 <= vp.get("emitidas", 0) <= vp.get("total", 0) <= 190 * 100):
                    self.fallo("G3", f"{l['nombre']}: votaciones_pleno imposible")
        fin = self.nuevo.json("docs/data/finanzas.json") or {}
        fin_b = {m.get("id"): m for m in (self.base.json("docs/data/finanzas.json") or {}).get("metricas", [])}
        for m in fin.get("metricas", []):
            auto = m.get("auto")
            if not auto:
                continue
            # range + max jump vs the value on main (robot's last number, else the hand-written card)
            previo = valor_previo(fin_b[m["id"]]) if m.get("id") in fin_b else None
            prob = problema_metrica(m.get("id"), auto, previo)
            if prob:
                self.fallo("G3", f"finanzas {prob}")
        # The site shows valor_texto and the sentences, not valor_num: they must be exactly what
        # dinero.textos() writes from the numbers, and every period must be a real period.
        pob = ((self.base.json("docs/data/finanzas.json") or {}).get("poblacion") or {}).get("habitantes")
        for _, m in self.cambiados("docs/data/finanzas.json", "metricas", "id")[0]:
            auto = m.get("auto")
            if not auto:
                continue
            for k in ("periodo", "anterior_periodo", "parcial_periodo"):
                if k in auto and not re.fullmatch(PERIODO, str(auto[k])):
                    self.fallo("G3", f"finanzas {m.get('id')}.{k}: {str(auto[k])[:60]!r} no es un período")
            try:
                esperado = textos_dinero(m.get("id"), auto, pob)
            except (KeyError, TypeError, ValueError) as e:
                self.fallo("G3", f"finanzas {m.get('id')}: no se puede rehacer el texto de la tarjeta ({type(e).__name__}: {e})")
                continue
            for k, v in esperado.items():
                if auto.get(k) != v:
                    self.fallo("G3", f"finanzas {m.get('id')}.{k}: dice {str(auto.get(k))[:60]!r} y los números dan {v[:60]!r}")
        pre = fin.get("presupuesto_auto")
        if isinstance(pre, dict) and all(isinstance(pre.get(k), (int, float)) for k in ("ingresos", "gastos", "resultado")):
            calc = pre["ingresos"] - pre["gastos"]
            if abs(calc - pre["resultado"]) > abs(pre["resultado"]) * 0.01 + 1:
                self.fallo("G3", f"presupuesto: ingresos - gastos = {calc:.1f} y el archivo dice {pre['resultado']}")

    # G4 ---------------------------------------------------------------
    def _url_ok(self, url: str, donde: str, exigir_recibo=True):
        host = (urlsplit(url).hostname or "").lower()
        if host not in self.dominios:
            self.fallo("G4", f"{donde}: {host} no es un dominio oficial de config/dominios_oficiales.json")
            return
        if exigir_recibo and not any(r.get("url") == url and r.get("status") == 200 and not r.get("error")
                                     for r in self.recibos):
            self.fallo("G4", f"{donde}: {url} no tiene un recibo HTTP 200 de esta corrida")

    def cambiados(self, rel: str, lista: str, clave: str, sub=None):
        b = self.base.json(rel) or {}
        n = self.nuevo.json(rel) or {}
        get = sub or (lambda d: d.get(lista, []))
        bi = {str(x.get(clave)): x for x in get(b) if isinstance(x, dict)}
        out = []
        for x in get(n):
            if not isinstance(x, dict):
                continue
            k = str(x.get(clave))
            if k not in bi:
                out.append(("nuevo", x))
            elif bi[k] != x:
                out.append(("cambiado", x))
        return out, bi

    def g4_fuentes(self):
        for tipo, s in self.cambiados("docs/data/sesiones.json", "sesiones", "acta")[0]:
            if not s.get("url_acta"):
                self.fallo("G4", f"acta {s['acta']}: sin url_acta")
            else:
                self._url_ok(s["url_acta"], f"acta {s['acta']}")
        for tipo, l in self.cambiados("docs/data/vigencia.json", "leyes", "numero")[0]:
            url = l.get("url_documento") or l.get("url_oficial") or l.get("url_busqueda")
            if not url:
                self.fallo("G4", f"ley {l.get('numero')}: sin enlace oficial")
            elif l.get("auto"):
                self._url_ok(url, f"ley {l.get('numero')}")
        todas = lambda d: [x for s in d.get("sectores", []) for x in s.get("leyes", []) if x.get("id")]  # noqa: E731
        for tipo, l in self.cambiados("docs/data/leyes.json", None, "id", sub=todas)[0]:
            if not l.get("auto"):
                continue
            if not l.get("url_oficial"):
                self.fallo("G4", f"proyecto {l.get('id')}: sin url_oficial")
            else:
                self._url_ok(l["url_oficial"], f"proyecto {l.get('id')}", exigir_recibo=False)
        for tipo, m in self.cambiados("docs/data/finanzas.json", "metricas", "id")[0]:
            auto = m.get("auto")
            if auto:
                self._url_ok(auto.get("url", ""), f"finanzas {m['id']}")
        res_b = (self.base.json("docs/data/resumenes.json") or {}).get("resumenes", {})
        for k, r in ((self.nuevo.json("docs/data/resumenes.json") or {}).get("resumenes", {})).items():
            if res_b.get(k) != r:
                self._url_ok(r.get("fuente_url", ""), f"resumen {k}", exigir_recibo=False)
        # "Resumen automático no disponible" shows sin_resumen[*].fuente_url as "Documento oficial".
        sin_b = (self.base.json("docs/data/resumenes.json") or {}).get("sin_resumen", {})
        for k, x in ((self.nuevo.json("docs/data/resumenes.json") or {}).get("sin_resumen", {})).items():
            if sin_b.get(k) != x and isinstance(x, dict) and "fuente_url" in x:
                self._url_ok(str(x["fuente_url"]), f"sin_resumen {k}", exigir_recibo=False)

    # G5 ---------------------------------------------------------------
    def g5_tamano(self):
        cam, _ = self.cambiados("docs/data/sesiones.json", "sesiones", "acta")
        if len(cam) > LIMITES["sesiones_actas"]:
            self.fallo("G5", f"{len(cam)} actas nuevas o cambiadas (máximo {LIMITES['sesiones_actas']})")
        votos = sum(len(s.get("votaciones", [])) for _, s in cam)
        if votos > LIMITES["sesiones_votos"]:
            self.fallo("G5", f"{votos} votaciones nuevas (máximo {LIMITES['sesiones_votos']})")
        todas = lambda d: [x for s in d.get("sectores", []) for x in s.get("leyes", []) if x.get("id")]  # noqa: E731
        cl, _ = self.cambiados("docs/data/leyes.json", None, "id", sub=todas)
        if sum(1 for t, _ in cl if t == "nuevo") > LIMITES["leyes_nuevas"]:
            self.fallo("G5", "demasiados proyectos nuevos en leyes.json")
        if sum(1 for t, _ in cl if t == "cambiado") > LIMITES["leyes_cambiadas"]:
            self.fallo("G5", "demasiados proyectos cambiados en leyes.json")
        cv, _ = self.cambiados("docs/data/vigencia.json", "leyes", "numero")
        if sum(1 for t, _ in cv if t == "nuevo") > LIMITES["vigencia_nuevas"]:
            self.fallo("G5", "demasiadas leyes nuevas en vigencia.json")
        cf, _ = self.cambiados("docs/data/finanzas.json", "metricas", "id")
        if len(cf) > LIMITES["finanzas_metricas"]:
            self.fallo("G5", "demasiadas métricas cambiadas en finanzas.json")
        cn, _ = self.cambiados("docs/data/novedades.json", "novedades", "texto")
        if sum(1 for t, _ in cn if t == "nuevo") > LIMITES["novedades_nuevas"]:
            self.fallo("G5", "más de 1 novedad nueva en una corrida")
        rb = (self.base.json("docs/data/resumenes.json") or {}).get("resumenes", {})
        rn = (self.nuevo.json("docs/data/resumenes.json") or {}).get("resumenes", {})
        nr = sum(1 for k, r in rn.items() if rb.get(k) != r)
        if nr > LIMITES["resumenes_nuevos"]:
            self.fallo("G5", f"{nr} resúmenes nuevos o cambiados (máximo {LIMITES['resumenes_nuevos']})")
        for rel in self.datos():
            bt, nt = self.base.texto(rel), self.nuevo.texto(rel)
            if bt is None or nt is None:
                continue
            lim = max(1.5 * len(bt), len(bt) + 400_000)
            if len(nt) > lim:
                self.fallo("G5", f"{rel} creció de {len(bt)} a {len(nt)} bytes (límite {int(lim)})")

    # G6 ---------------------------------------------------------------
    def g6_borrados(self):
        def ids(side, rel, f):
            d = side.json(rel)
            return set(f(d)) if d is not None else None
        chk = [
            ("docs/data/sesiones.json", lambda d: [s["acta"] for s in d["sesiones"]], "actas"),
            ("docs/data/vigencia.json", lambda d: [l["numero"] for l in d["leyes"]], "leyes en vigencia"),
            ("docs/data/finanzas.json", lambda d: [m["id"] for m in d["metricas"]], "métricas"),
            ("docs/data/provincias.json",
             lambda d: [f"{p['nombre']}|{l['cargo']}|{l['nombre']}" for p in d["provincias"] for l in p["lideres"]],
             "líderes"),
            ("docs/data/novedades.json", lambda d: [n["texto"] for n in d["novedades"]], "novedades"),
        ]
        for rel, f, que in chk:
            b, n = ids(self.base, rel, f), ids(self.nuevo, rel, f)
            if b is None:
                continue
            if n is None:
                self.fallo("G6", f"{rel} desapareció")
                continue
            if b - n:
                self.fallo("G6", f"{rel}: se borraron {len(b - n)} {que}: {sorted(b - n)[:5]}")
        lb = self.base.json("docs/data/leyes.json")
        ln = self.nuevo.json("docs/data/leyes.json")
        if lb and ln:
            key = lambda l: l.get("id") or l["titulo"]  # noqa: E731
            b = {key(l): l for s in lb["sectores"] for l in s["leyes"]}
            n = {key(l) for s in ln["sectores"] for l in s["leyes"]}
            gone = [k for k in b if k not in n]
            if any(not b[k].get("auto") for k in gone):
                self.fallo("G6", "leyes.json: se borró una entrada escrita a mano")
            if len(gone) > 0.02 * len(b):
                self.fallo("G6", f"leyes.json: se borraron {len(gone)} de {len(b)} entradas (máximo 2%)")

    # G7 ---------------------------------------------------------------
    def g7_no_vaciar(self):
        for rel in self.datos():
            # resumenes.json: withdrawing a summary is legitimate (G8 checks every record instead)
            if rel.endswith("resumenes.json"):
                continue
            b = self.base.json(rel)
            if b is None:
                continue
            n = self.nuevo.json(rel)
            reparados = []

            def visitar(ruta, bv, nv, _rel=rel):
                if isinstance(bv, dict) and isinstance(nv, dict):
                    for k, v in bv.items():
                        if k in nv and not _vacio(v) and _vacio(nv[k]) and not isinstance(v, bool):
                            if ruta == "$" and isinstance(v, (list, dict)):
                                # a whole top-level list/object emptied = the source broke; never "repair" it
                                self.fallo("G7", f"{_rel}: '{k}' quedó vacío (fuente rota?)")
                                continue
                            nv[k] = v
                            reparados.append(f"{_rel} {ruta}.{k}")
            recorrer(b, n, "$", visitar)
            if reparados:
                self.reparaciones += reparados
                txt = self.nuevo.texto(rel)
                indent = len(re.match(r"^( *)", txt.split("\n", 2)[1]).group(1)) if "\n" in txt else 2
                (self.nd / rel).write_text(json.dumps(n, ensure_ascii=False, indent=indent or 2)
                                           + ("\n" if txt.endswith("\n") else ""), encoding="utf-8")
        if len(self.reparaciones) > MAX_REPARACIONES_G7:
            self.fallo("G7", f"{len(self.reparaciones)} campos con datos buenos quedaron vacíos (fuente rota?): "
                             f"{self.reparaciones[:5]}")
        elif self.reparaciones:
            self.avisos.append(f"G7: se devolvió el valor anterior a {self.reparaciones}")

    # G8 ---------------------------------------------------------------
    def g8_prosa(self):
        # Every plain-Spanish string in a data file (outside resumenes.json) must
        # already exist on main. Removing prose is allowed; adding or editing is not.
        for rel in self.datos():
            if rel.endswith("resumenes.json"):
                continue
            b = self.base.json(rel)
            n = self.nuevo.json(rel)
            if b is None:
                b = {}
            nuevos = self._prosa(n) - self._prosa(b)
            for campo, texto in sorted(nuevos)[:5]:
                self.fallo("G8", f"{rel} {campo}: texto en español fácil nuevo o cambiado fuera de resumenes.json: "
                                 f"{texto[:60]!r}")
        rb = (self.base.json("docs/data/resumenes.json") or {}).get("resumenes", {})
        rn = (self.nuevo.json("docs/data/resumenes.json") or {}).get("resumenes", {})
        ia = self._conf("ia.json", {"escritores": [], "revisores": []})
        leyes_n, vig_n = self.nuevo.json("docs/data/leyes.json"), self.nuevo.json("docs/data/vigencia.json")
        for k, r in rn.items():
            if rb.get(k) == r:
                continue
            # Law or not comes from the data (leyes.json / vigencia.json / a Senate vote), never from the record.
            real = estado_ley_de(k, leyes_n, vig_n)
            if real is None:
                self.fallo("G8", f"resumen {k}: no corresponde a ningún proyecto, ley o votación del sitio")
            elif r.get("estado_ley") != real:
                self.fallo("G8", f"resumen {k}: dice estado_ley {r.get('estado_ley')!r} y los datos dicen {real!r}")
            # only real configured models publish (a --stub run can never reach the site)
            if r.get("modelo_escritor") not in ia["escritores"] or r.get("modelo_revisor") not in ia["revisores"]:
                self.fallo("G8", f"resumen {k}: modelos {r.get('modelo_escritor')}/{r.get('modelo_revisor')} "
                                 "no están en config/ia.json (¿corrida de prueba?)")
            if r.get("estado") != "verificado":
                self.fallo("G8", f"resumen {k}: estado {r.get('estado')} (solo 'verificado' se publica)")
            if not r.get("checks_total") or r.get("checks_pasados") != r.get("checks_total"):
                self.fallo("G8", f"resumen {k}: pasó {r.get('checks_pasados')} de {r.get('checks_total')} revisiones")
            if r.get("modelo_escritor") and r.get("modelo_escritor") == r.get("modelo_revisor"):
                self.fallo("G8", f"resumen {k}: el revisor es el mismo modelo que el escritor")
            sha = r.get("fuente_sha256", "")
            ftxt = self.nd / "pipeline-state" / "textos" / f"{sha}.txt"
            if not re.fullmatch(r"[0-9a-f]{64}", sha) or not ftxt.exists():
                self.fallo("G8", f"resumen {k}: falta el texto fuente pipeline-state/textos/{sha}.txt")
                continue
            # The stored text must BE the text that was checked: its sha256 must match its name.
            crudo = ftxt.read_bytes()
            if hashlib.sha256(crudo).hexdigest() != sha:
                self.fallo("G8", f"resumen {k}: pipeline-state/textos/{sha}.txt no corresponde a su sha256")
                continue
            fuente = crudo.decode("utf-8")
            minimo = MIN_FUENTE.get(r.get("tipo"), MIN_FUENTE_DEFECTO)
            if len(fuente.strip()) < minimo:
                self.fallo("G8", f"resumen {k}: el texto fuente tiene {len(fuente.strip())} caracteres "
                                 f"(mínimo {minimo}): no hay contra qué revisar")
                continue
            # Same source + different text = someone edited a checked summary without a new review.
            if k in rb and rb[k].get("fuente_sha256") == sha:
                self.fallo("G8", f"resumen {k}: el texto cambió sin un texto fuente nuevo (no pasó por la revisión)")
            # Re-run the code checks against the stored source on EVERY prose field present
            # (defence in depth; the writer ran them too).
            pedidos = ia.get("campos_por_tipo", {}).get(r.get("tipo"))
            if pedidos is None:
                self.fallo("G8", f"resumen {k}: tipo {r.get('tipo')!r} desconocido")
                continue
            presentes = sorted(c for c in PROSA if c in r)
            for campo in pedidos:
                if campo not in presentes:
                    self.fallo("G8", f"resumen {k}: falta el campo {campo}")
            for campo in presentes:
                if campo not in pedidos:
                    self.fallo("G8", f"resumen {k}: el campo {campo} no se pide para el tipo {r.get('tipo')}")
            if (r.get("checks_total") or 0) < CHECKS_POR_CAMPO * len(presentes):
                self.fallo("G8", f"resumen {k}: {r.get('checks_total')} revisiones para {len(presentes)} campos "
                                 f"(mínimo {CHECKS_POR_CAMPO} por campo)")
            no_aprobado = real not in APROBADO
            for campo in presentes:
                t = r.get(campo)
                if not isinstance(t, str) or not t.strip():
                    self.fallo("G8", f"resumen {k}: el campo {campo} está vacío")
                    continue
                for num in numeros_ausentes(t, fuente):
                    self.fallo("G8", f"resumen {k}.{campo}: el número {num} no está en el texto fuente")
                if numero_en_letras(t):
                    self.fallo("G8", f"resumen {k}.{campo}: número escrito en letras ({numero_en_letras(t)})")
                if no_aprobado and PARECE_LEY.search(t):
                    self.fallo("G8", f"resumen {k}.{campo}: presenta como ley algo no aprobado "
                                     f"({PARECE_LEY.search(t).group(0)!r})")
        self._g8_notas_y_novedades()

    def _g8_notas_y_novedades(self):
        # A money card's hand-written part never changes in a robot commit (dinero.py writes only 'auto').
        fin_b = {m.get("id"): m for m in (self.base.json("docs/data/finanzas.json") or {}).get("metricas", [])}
        for m in (self.nuevo.json("docs/data/finanzas.json") or {}).get("metricas", []):
            b = fin_b.get(m.get("id"))
            if b is not None and {k: v for k, v in m.items() if k != "auto"} != {k: v for k, v in b.items() if k != "auto"}:
                self.fallo("G8", f"finanzas {m.get('id')}: cambió la parte escrita a mano de la tarjeta (solo 'auto' puede cambiar)")

        # A vote note may only repeat numbers the vote itself carries.
        for donde, nota, v, s in self.notas_nuevas():
            propio = " ".join(str(x) for kk, x in v.items() if kk != "nota") + f" {s.get('acta')} {s.get('fecha')}"
            for num in numeros_ausentes(nota, propio):
                self.fallo("G8", f"{donde}: el número {num} no está en los datos de esa votación")
        # A no_procesada acta's 'motivo' is one of senado_actas.py's fixed forms.
        for _, s in self.cambiados("docs/data/sesiones.json", "sesiones", "acta")[0]:
            if "motivo" in s and not es_motivo(str(s["motivo"])):
                self.fallo("G8", f"acta {s.get('acta')}: 'motivo' no es uno de los de senado_actas.py: {str(s['motivo'])[:60]!r}")
        self._g8_novedades()
        self._g8_escrito_a_mano()

    def _g8_novedades(self):
        # A robot Novedad is built from fixed templates (novedades.py); anything else is free prose.
        ses = {str(s.get("acta")) for s in (self.nuevo.json("docs/data/sesiones.json") or {}).get("sesiones", [])}
        vig = {str(l.get("numero")) for l in (self.nuevo.json("docs/data/vigencia.json") or {}).get("leyes", [])}
        # What this commit really did, to check the counts a Novedad claims.
        todas = lambda d: [x for s in d.get("sectores", []) for x in s.get("leyes", []) if x.get("id")]  # noqa: E731
        cl = self.cambiados("docs/data/leyes.json", None, "id", sub=todas)[0]
        hecho = {
            # an acta stored as no_procesada and now read is "new" to the robot but "changed" here
            "sesiones": len(self.cambiados("docs/data/sesiones.json", "sesiones", "acta")[0]),
            "proyectos": sum(1 for t, x in cl if t == "nuevo" and x.get("auto")),
            "actualizados": sum(1 for t, x in cl if t == "cambiado" and x.get("auto")),
            "leyes": sum(1 for t, _ in self.cambiados("docs/data/vigencia.json", "leyes", "numero")[0] if t == "nuevo"),
        }
        rb = (self.base.json("docs/data/resumenes.json") or {}).get("resumenes", {})
        hecho["resumenes"] = sum(1 for k, r in ((self.nuevo.json("docs/data/resumenes.json") or {}).get("resumenes", {})).items()
                                 if rb.get(k) != r)
        metricas = {m.get("id"): m.get("auto") or {} for _, m in self.cambiados("docs/data/finanzas.json", "metricas", "id")[0]}
        por_nombre = {v: k for k, v in NOMBRE_METRICA.items()}
        for t, n in self.cambiados("docs/data/novedades.json", "novedades", "texto")[0]:
            texto = n.get("texto", "")
            if t == "cambiado":
                self.fallo("G8", f"novedad ya publicada cambió: {texto[:60]!r} (un robot solo agrega novedades)")
                continue
            # aporte is rendered as HTML: it may only be the fixed robot label.
            if n.get("auto") is not True or n.get("aporte") != APORTE:
                self.fallo("G8", f"novedad: una novedad del robot lleva auto: true y aporte {APORTE!r}, "
                                 f"no {str(n.get('aporte'))[:60]!r}")
            if not es_plantilla(texto):
                self.fallo("G8", f"novedad: no sale de las plantillas de novedades.py: {texto[:80]!r}")
                continue
            for rx, que in ((r"Agregamos (\d+) (?:sesión|sesiones) del Senado", "sesiones"),
                            (r"Agregamos (\d+) proyectos de ley", "proyectos"),
                            (r"Actualizamos en qué va (\d+)", "actualizados"),
                            (r"Agregamos (\d+) leyes nuevas", "leyes"),
                            (r"Publicamos (\d+) resúmen", "resumenes")):
                for num in re.findall(rx, texto):
                    if int(num) > hecho[que]:
                        self.fallo("G8", f"novedad: dice {num} {que} y este cambio trae {hecho[que]}")
            for lista in re.findall(r"Agregamos (\d+) leyes nuevas a «¿Ya está vigente\?»: ([\d\-, ]+)", texto):
                if int(lista[0]) != len(re.findall(r"\d+-\d+", lista[1])):
                    self.fallo("G8", f"novedad: dice {lista[0]} leyes y nombra {len(re.findall(r'[0-9]+-[0-9]+', lista[1]))}")
            for cifras in re.findall(r"Actualizamos las cifras del país: (.*)\.", texto):
                for nombre, periodo in re.findall(r"([^,()]+?) \(([^)]*)\)", cifras):
                    mid = por_nombre.get(nombre.strip(), nombre.strip())
                    if mid not in metricas or metricas[mid].get("periodo") != periodo:
                        self.fallo("G8", f"novedad: '{nombre.strip()} ({periodo})' no es una cifra que cambió en este commit")
            for acta in re.findall(r"\bactas? ((?:\d+(?:, | a )?)+)", texto):
                for a in re.findall(r"\d+", acta):
                    if a not in ses:
                        self.fallo("G8", f"novedad: el acta {a} no está en sesiones.json")
            for lista in re.findall(r"vigente\?»: ([\d\-, ]+)", texto):
                for num in re.findall(r"\d+-\d+", lista):
                    if num not in vig:
                        self.fallo("G8", f"novedad: la ley {num} no está en vigencia.json")
        # The feed is rebuilt from novedades.json by code: it can't carry anything else.
        xml = self.nuevo.texto("docs/novedades.xml")
        nov = self.nuevo.json("docs/data/novedades.json")
        if xml is not None and nov is not None and xml != self.base.texto("docs/novedades.xml") and xml != construir_xml(nov):
            self.fallo("G8", "docs/novedades.xml no es el que novedades.py arma desde docs/data/novedades.json")

    def _g8_escrito_a_mano(self):
        """Hand-written records never change in a robot commit: only the exact fields each robot writes."""
        def sin(d, quitar):
            return {k: v for k, v in (d or {}).items() if k not in quitar}

        # leyes.json: hand-written bills identical (same sector, same order); auto bills only change
        # estado/estado_sil/datos_al; new ones carry only the fields leyes.py writes.
        lb, ln = self.base.json("docs/data/leyes.json"), self.nuevo.json("docs/data/leyes.json")
        if lb is not None and ln is not None:
            if sin(lb, {"sectores"}) != sin(ln, {"sectores"}):
                self.fallo("G8", "leyes.json: cambió una parte escrita a mano (fuera de 'sectores')")
            mano = lambda d: [(s.get("id"), l) for s in d.get("sectores", []) for l in s.get("leyes", [])  # noqa: E731
                              if not l.get("auto")]
            if mano(lb) != mano(ln):
                self.fallo("G8", "leyes.json: cambió, se agregó o se movió un proyecto escrito a mano")
            sec_b = {s.get("id"): sin(s, {"leyes"}) for s in lb.get("sectores", [])}
            otros = self._conf("sil.json", {}).get("sector_otros", {})
            for s in ln.get("sectores", []):
                if sec_b.get(s.get("id"), {"id": s.get("id"), **otros}) != sin(s, {"leyes"}):
                    self.fallo("G8", f"leyes.json: el sector {s.get('id')} cambió o no es el que leyes.py crea")
            auto_b = {str(l.get("id")): l for s in lb.get("sectores", []) for l in s.get("leyes", []) if l.get("auto")}
            for s in ln.get("sectores", []):
                for l in s.get("leyes", []):
                    if not l.get("auto"):
                        continue
                    viejo = auto_b.get(str(l.get("id")))
                    if viejo is None:
                        if set(l) - LEY_AUTO_CAMPOS or not l.get("id") or not l.get("sil_id") or l.get("votos"):
                            self.fallo("G8", f"leyes.json: el proyecto nuevo {l.get('id')} trae campos que leyes.py no escribe: "
                                             f"{sorted(set(l) - LEY_AUTO_CAMPOS)}")
                    elif sin(viejo, LEY_AUTO_CAMBIAN) != sin(l, LEY_AUTO_CAMBIAN):
                        self.fallo("G8", f"leyes.json: en el proyecto {l.get('id')} solo pueden cambiar {sorted(LEY_AUTO_CAMBIAN)}")

        # vigencia.json: a law already on main never changes; a new one is the robot's, with a fixed text.
        vb, vn = self.base.json("docs/data/vigencia.json"), self.nuevo.json("docs/data/vigencia.json")
        if vb is not None and vn is not None:
            if sin(vb, {"leyes"}) != sin(vn, {"leyes"}):
                self.fallo("G8", "vigencia.json: cambió una parte escrita a mano (fuera de 'leyes')")
            por_num = {str(l.get("numero")): l for l in vb.get("leyes", [])}
            for l in vn.get("leyes", []):
                viejo = por_num.get(str(l.get("numero")))
                if viejo is not None:
                    if viejo != l:
                        self.fallo("G8", f"vigencia.json: la ley {l.get('numero')} ya publicada cambió")
                elif l.get("auto") is not True:
                    self.fallo("G8", f"vigencia.json: ley nueva {l.get('numero')} sin auto: true (a mano solo por PR)")
                elif not es_texto_vigencia(str(l.get("vigencia_texto", ""))):
                    self.fallo("G8", f"vigencia.json: ley {l.get('numero')}: vigencia_texto no es uno de los de vigencia.py")

        # provincias.json: everything identical except the fields camara.py writes on a leader.
        pb, pn = self.base.json("docs/data/provincias.json"), self.nuevo.json("docs/data/provincias.json")
        if pb is not None and pn is not None:
            def mascara(d):
                d = json.loads(json.dumps(d))
                for p in d.get("provincias", []):
                    for l in p.get("lideres", []):
                        for k in CAMPOS_ROBOT:
                            l.pop(k, None)
                return d
            if mascara(pb) != mascara(pn):
                self.fallo("G8", "provincias.json: cambió algo escrito a mano (solo cambian asistencia, comisiones, "
                                 "iniciativas_propuestas y cargo_hasta)")
            else:
                viejos = [l for p in pb.get("provincias", []) for l in p.get("lideres", [])]
                nuevos = [l for p in pn.get("provincias", []) for l in p.get("lideres", [])]
                for b, l in zip(viejos, nuevos):
                    self._lider_robot(b, l)

        # finanzas.json: only each card's 'auto', actualizado_auto and the derived debt per person.
        fb, fn = self.base.json("docs/data/finanzas.json"), self.nuevo.json("docs/data/finanzas.json")
        if fb is not None and fn is not None:
            def mascara_f(d):
                d = json.loads(json.dumps(d))
                d.pop("actualizado_auto", None)
                (d.get("comparaciones_derivadas") or {}).pop("deuda_por_persona_usd", None)
                d.pop("metricas", None)
                return d
            if mascara_f(fb) != mascara_f(fn):
                self.fallo("G8", "finanzas.json: cambió una parte escrita a mano (fuera de las tarjetas 'auto')")
            extra = {m.get("id") for m in fn.get("metricas", [])} - {m.get("id") for m in fb.get("metricas", [])}
            if extra:
                self.fallo("G8", f"finanzas.json: tarjetas nuevas {sorted(map(str, extra))} (solo a mano, por PR)")
            dpp = (fn.get("comparaciones_derivadas") or {}).get("deuda_por_persona_usd")
            if dpp != (fb.get("comparaciones_derivadas") or {}).get("deuda_por_persona_usd"):
                deuda = next((m.get("auto") or {} for m in fn.get("metricas", []) if m.get("id") == "deuda"), {})
                pob = (fb.get("poblacion") or {}).get("habitantes")
                try:
                    ok = dpp == round(deuda["usd_millones"] * 1e6 / pob)
                except (KeyError, TypeError, ZeroDivisionError):
                    ok = False
                if not ok:
                    self.fallo("G8", f"finanzas.json: deuda_por_persona_usd {dpp} no sale de la deuda y la población")

    def _lider_robot(self, b: dict, l: dict):
        quien = l.get("nombre")
        c = l.get("comisiones")
        if c != b.get("comisiones") and (not isinstance(c, list) or
                                         not all(isinstance(x, str) and x and len(x) <= 200 and not re.search(r"[<>]", x)
                                                 for x in c)):
            self.fallo("G8", f"{quien}: comisiones no es una lista de nombres")
        i = l.get("iniciativas_propuestas")
        if i != b.get("iniciativas_propuestas") and not (isinstance(i, int) and not isinstance(i, bool) and i >= 0):
            self.fallo("G8", f"{quien}: iniciativas_propuestas {i!r} no es un número")
        h = l.get("cargo_hasta")
        if h != b.get("cargo_hasta") and h is not None and not (isinstance(h, str) and FECHA.fullmatch(h)):
            self.fallo("G8", f"{quien}: cargo_hasta {h!r} no es una fecha")
        a, ab = l.get("asistencia"), b.get("asistencia")
        if a == ab:
            return
        if not isinstance(a, dict):
            self.fallo("G8", f"{quien}: asistencia no es un objeto")
            return
        ab = ab if isinstance(ab, dict) else {}
        for k, v in a.items():
            if v == ab.get(k):
                continue
            if k in ("presentes", "total"):
                bien = isinstance(v, int) and not isinstance(v, bool) and v >= 0
            elif k == "datos_al":
                bien = isinstance(v, str) and bool(FECHA.fullmatch(v))
            elif k == "nota":
                bien = v == NOTA_SIN_ACTUALIZAR
            elif k == "fuente":
                bien = v == ASIST_FUENTE
            elif k == "periodo":
                bien = isinstance(v, str) and bool(PERIODO_ASIS.fullmatch(v))
            else:
                bien = False
            if not bien:
                self.fallo("G8", f"{quien}: asistencia.{k} = {str(v)[:60]!r} no es algo que escribe camara.py")

    def notas_nuevas(self) -> list[tuple[str, str, dict, dict]]:
        """(where, note, vote, session) for every vote 'nota' not already on main."""
        def todas(d):
            return [(f"acta {s.get('acta')} votación {v.get('votacion_num') or v.get('iniciativa')} nota", v["nota"], v, s)
                    for s in (d or {}).get("sesiones", []) for v in s.get("votaciones", [])
                    if isinstance(v.get("nota"), str) and v["nota"]]
        viejas = {(x[0], x[1]) for x in todas(self.base.json("docs/data/sesiones.json"))}
        return [x for x in todas(self.nuevo.json("docs/data/sesiones.json")) if (x[0], x[1]) not in viejas]

    def _prosa(self, o) -> set:
        out = set()
        if isinstance(o, dict):
            for k, v in o.items():
                if k in PROSA and isinstance(v, str) and v:
                    out.add((k, v))
                else:
                    out |= self._prosa(v)
        elif isinstance(o, list):
            for v in o:
                out |= self._prosa(v)
        return out

    # G9 ---------------------------------------------------------------
    def textos_nuevos(self) -> list[tuple[str, str, dict]]:
        """(where, text, context) for every new machine-written text."""
        out = []
        rb = (self.base.json("docs/data/resumenes.json") or {}).get("resumenes", {})
        for k, r in ((self.nuevo.json("docs/data/resumenes.json") or {}).get("resumenes", {})).items():
            if rb.get(k) == r:
                continue
            for campo in PROSA:
                if r.get(campo):
                    out.append((f"resumen {k}.{campo}", r[campo], r))
        for _, n in self.cambiados("docs/data/novedades.json", "novedades", "texto")[0]:
            out.append(("novedad", n["texto"], n))
            if isinstance(n.get("aporte"), str) and n["aporte"]:
                out.append(("novedad aporte", n["aporte"], n))
        for _, s in self.cambiados("docs/data/sesiones.json", "sesiones", "acta")[0]:
            for nota in s.get("notas_fuente", []):
                out.append((f"acta {s['acta']} nota", nota, s))
            if isinstance(s.get("motivo"), str) and s["motivo"]:
                out.append((f"acta {s['acta']} motivo", s["motivo"], s))
            nota_asis = (s.get("asistencia") or {}).get("nota")
            if isinstance(nota_asis, str) and nota_asis:
                out.append((f"acta {s['acta']} asistencia.nota", nota_asis, s))
        for donde, nota, v, _s in self.notas_nuevas():
            out.append((donde, nota, v))
        for _, m in self.cambiados("docs/data/finanzas.json", "metricas", "id")[0]:
            for campo in ("texto", "comparacion"):
                if (m.get("auto") or {}).get(campo):
                    out.append((f"finanzas {m['id']}.{campo}", m["auto"][campo], m))
        return out

    def g9_neutral(self):
        leyes_n, vig_n = self.nuevo.json("docs/data/leyes.json"), self.nuevo.json("docs/data/vigencia.json")
        neu = self._conf("neutralidad.json", {"prohibidas_exactas": [], "prohibidas": []})
        exact = re.compile(r"\b(" + "|".join(map(re.escape, neu["prohibidas_exactas"])) + r")\b") \
            if neu["prohibidas_exactas"] else None
        suaves = re.compile(r"\b(" + "|".join(neu["prohibidas"]) + r")\b", re.I) if neu["prohibidas"] else None
        nombres = list(self._conf("personas_publicas.json", {"nombres": []})["nombres"])
        for side in (self.base, self.nuevo):
            prov = side.json("docs/data/provincias.json") or {"provincias": []}
            for p in prov["provincias"]:
                for l in p["lideres"]:
                    if l.get("nombre") and len(l["nombre"].split()) >= 2:
                        nombres.append(l["nombre"])
        patrones = patrones_nombres(nombres)
        for donde, txt, ctx in self.textos_nuevos():
            if exact and exact.search(txt):
                self.fallo("G9", f"{donde}: palabra partidista '{exact.search(txt).group(0)}'")
            if suaves and suaves.search(txt):
                self.fallo("G9", f"{donde}: palabra de juicio u opinión '{suaves.search(txt).group(0)}'")
            persona = nombra_persona(txt, patrones)
            if persona:
                self.fallo("G9", f"{donde}: nombra a una persona ({persona})")
            clave = donde[len("resumen "):].rsplit(".", 1)[0] if donde.startswith("resumen ") else ""
            if donde.endswith(".te_afecta") and estado_ley_de(clave, leyes_n, vig_n) not in APROBADO:
                for frase in re.split(r"(?<=[.!?])\s+", txt.strip()):
                    if frase and not (frase.startswith("La propuesta busca") or frase.startswith("Si se aprueba,")):
                        self.fallo("G9", f"{donde}: en un proyecto no aprobado cada frase debe empezar con "
                                         f"'La propuesta busca' o 'Si se aprueba,': {frase[:60]!r}")

    # G10 --------------------------------------------------------------
    def g10_avanzar(self):
        known = set(self._conf("senado.json", {"reemplazar_una_vez": []})["reemplazar_una_vez"])
        cam, bi = self.cambiados("docs/data/sesiones.json", "sesiones", "acta")
        for t, s in cam:
            if t != "cambiado":
                continue
            old = bi[s["acta"]]
            if len(s.get("votaciones", [])) < len(old.get("votaciones", [])) and s["acta"] not in known:
                self.fallo("G10", f"acta {s['acta']}: la nueva lectura trae menos votaciones "
                                  f"({len(s.get('votaciones', []))} < {len(old.get('votaciones', []))})")
            if s.get("estado") == "no_procesada" and old.get("estado") != "no_procesada":
                self.fallo("G10", f"acta {s['acta']}: se cambiaría un acta buena por 'no procesada'")
        cv, bv = self.cambiados("docs/data/vigencia.json", "leyes", "numero")
        for t, l in cv:
            if t == "cambiado" and bv[l["numero"]].get("promulgada") and l.get("promulgada") != bv[l["numero"]]["promulgada"]:
                self.fallo("G10", f"ley {l['numero']}: la fecha de promulgación no puede cambiar")
        cf, bf = self.cambiados("docs/data/finanzas.json", "metricas", "id")
        for t, m in cf:
            if t != "cambiado":
                continue
            po = ((bf[m["id"]].get("auto") or {}).get("periodo_iso"))
            pn = ((m.get("auto") or {}).get("periodo_iso"))
            if po and pn and pn < po:
                self.fallo("G10", f"finanzas {m['id']}: el período retrocede ({po} -> {pn})")

    def correr(self) -> bool:
        # G7 first: it repairs emptied fields in place, then every other gate sees the repaired tree.
        for g in (self.g0_config, self.g7_no_vaciar, self.g1_esquemas, self.g2_sin_votos_por_senador, self.g3_totales,
                  self.g4_fuentes, self.g5_tamano, self.g6_borrados, self.g8_prosa, self.g9_neutral,
                  self.g10_avanzar):
            try:
                g()
            except Exception as e:  # noqa: BLE001  a crashing gate is a failed gate
                self.fallo(g.__name__, f"el control falló con {type(e).__name__}: {e}")
        return not self.fallos


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-ref")
    ap.add_argument("--base-dir")
    ap.add_argument("--new-dir", default=str(ROOT))
    ap.add_argument("--recibos", nargs="*", default=None,
                    help="archivos de recibos; por defecto <new-dir>/.psrd-run/recibos-*.json")
    a = ap.parse_args(argv)
    if not (a.base_ref or a.base_dir):
        ap.error("falta --base-ref o --base-dir")
    base = Lado(ref=a.base_ref) if a.base_ref else Lado(dir=Path(a.base_dir))
    nd = Path(a.new_dir)
    recibos = []
    files = [Path(f) for f in a.recibos] if a.recibos is not None else sorted((nd / ".psrd-run").glob("recibos-*.json"))
    for f in files:
        if f.exists():
            recibos += json.loads(f.read_text())
    conf = nd / "config" if (nd / "config").exists() else ROOT / "config"
    schemas = ROOT / "schemas"
    g = Gates(base, nd, conf, schemas, recibos)
    ok = g.correr()
    log = ["RESULTADO: " + ("PASA" if ok else "BLOQUEADO")] + g.fallos + g.avisos
    print("\n".join(log))
    (nd / ".psrd-run").mkdir(exist_ok=True)
    (nd / ".psrd-run" / "gates.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
