#!/usr/bin/env python3
"""Mechanical publish gates G1-G10 (design section 3).

Compares the NEW tree (the working tree, or a dry-run copy) against the BASE
(origin/main after the rebase, or a directory). Any failure exits 1: nothing is
committed and the job goes red. No human reads this before publishing; this
script is the reviewer.

  python3 scripts/gates/run_gates.py --base-ref origin/main
  python3 scripts/gates/run_gates.py --base-dir . --new-dir /tmp/psrd-dryrun/senado

G7 repairs as it checks: an emptied field gets its old value back in the new
tree (written in place). More than 5 repairs = broken source = fail.
"""
from __future__ import annotations

import argparse
import fnmatch
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
from comun import (PARECE_LEY, nombra_persona, numero_en_letras, numeros_ausentes,  # noqa: E402
                   patrones_nombres, problema_metrica, valor_previo)
PROSA = {"que_es", "por_que", "te_afecta", "titulo_facil", "en_30_segundos", "resumen", "resumen_corto"}
CLAVES_LISTA = ("acta", "numero", "id", "iniciativa", "nombre", "legisladorId", "fecha", "titulo")
VOTO_SENADO_OK = {"iniciativa", "titulo", "titulo_facil", "a_favor", "presentes", "resultado",
                  "votacion_num", "fuente", "nota"}
LIMITES = {"sesiones_actas": 30, "sesiones_votos": 250, "leyes_cambiadas": 60, "leyes_nuevas": 40,
           "vigencia_nuevas": 10, "finanzas_metricas": 9, "novedades_nuevas": 1}
MAX_REPARACIONES_G7 = 5


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
    def __init__(self, base: Lado, nuevo_dir: Path, conf_dir: Path, schemas_dir: Path, recibos: list[dict]):
        self.base = base
        self.nd = nuevo_dir
        self.nuevo = Lado(dir=nuevo_dir)
        self.conf = conf_dir
        self.schemas = schemas_dir
        self.recibos = recibos
        self.fallos: list[str] = []
        self.avisos: list[str] = []
        self.reparaciones: list[str] = []
        self.dominios = set(self._conf("dominios_oficiales.json", {"dominios": []})["dominios"])

    def _conf(self, name, defecto):
        f = self.conf / name
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else defecto

    def fallo(self, g: str, msg: str):
        self.fallos.append(f"{g}: {msg}")

    def datos(self) -> list[str]:
        return sorted({p for p in self.nuevo.archivos("docs/data") if p.endswith(".json")})

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
        for k, r in rn.items():
            if rb.get(k) == r:
                continue
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
            # Same source + different text = someone edited a checked summary without a new review.
            if k in rb and rb[k].get("fuente_sha256") == sha:
                self.fallo("G8", f"resumen {k}: el texto cambió sin un texto fuente nuevo (no pasó por la revisión)")
            # Re-run the code checks against the stored source (defence in depth; the writer ran them too).
            fuente = ftxt.read_text(encoding="utf-8")
            no_aprobado = r.get("estado_ley") not in ("aprobada", "promulgada")
            for campo in ia.get("campos_por_tipo", {}).get(r.get("tipo"), []):
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
        for _, s in self.cambiados("docs/data/sesiones.json", "sesiones", "acta")[0]:
            for nota in s.get("notas_fuente", []):
                out.append((f"acta {s['acta']} nota", nota, s))
        for _, m in self.cambiados("docs/data/finanzas.json", "metricas", "id")[0]:
            for campo in ("texto", "comparacion"):
                if (m.get("auto") or {}).get(campo):
                    out.append((f"finanzas {m['id']}.{campo}", m["auto"][campo], m))
        return out

    def g9_neutral(self):
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
            if donde.endswith(".te_afecta") and ctx.get("estado_ley") not in ("aprobada", "promulgada"):
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
        for g in (self.g7_no_vaciar, self.g1_esquemas, self.g2_sin_votos_por_senador, self.g3_totales,
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
