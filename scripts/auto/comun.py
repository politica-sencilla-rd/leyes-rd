"""Shared helpers for the automatic pipeline (scripts/auto/*).

One idea runs through every script: a script READS and WRITES through an
`Arbol` (tree). In a real run the tree is the repo itself. With --dry-run the
tree is a fresh copy under /tmp/psrd-dryrun/<nombre>/, so nothing in docs/ is
touched and the gates can compare the copy against the real repo.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DRY_BASE = Path("/tmp/psrd-dryrun")

# Everything a pipeline script may read or write. The dry-run copy holds only these.
COPIAR = ["docs/data", "docs/novedades.xml", "pipeline-state", "config", "src/app.ts",
          "scripts/diputados_stats.json"]

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def hoy_et() -> date:
    """Today's date in New York (UTC-4 in summer, UTC-5 in winter)."""
    ahora = datetime.now(timezone.utc)
    # US DST: second Sunday of March .. first Sunday of November.
    y = ahora.year
    mar = date(y, 3, 8) + timedelta(days=(6 - date(y, 3, 8).weekday()) % 7)
    nov = date(y, 11, 1) + timedelta(days=(6 - date(y, 11, 1).weekday()) % 7)
    dst = mar <= ahora.date() < nov
    return (ahora - timedelta(hours=4 if dst else 5)).date()


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", norm(s)) if len(t) > 1}


def similitud(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def sha256_texto(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def fecha_larga(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _formato(texto: str) -> tuple[int, bool]:
    """Detect indent and trailing newline of an existing JSON file so rewrites
    keep the same style (a style change would turn a 3-value update into a
    50k-line diff)."""
    lineas = texto.split("\n", 2)
    indent = 2
    if len(lineas) > 1:
        m = re.match(r"^( +)", lineas[1])
        if m:
            indent = len(m.group(1))
    return indent, texto.endswith("\n")


def dump_json(data: Any, indent: int = 2, nl: bool = True) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent) + ("\n" if nl else "")


class Arbol:
    """Where a script reads and writes. dry_run -> a copy in /tmp."""

    def __init__(self, nombre: str, dry_run: bool = False, base: Path | None = None):
        self.nombre = nombre
        self.dry_run = dry_run
        self.origen = base or ROOT
        if dry_run:
            self.raiz = DRY_BASE / nombre
            if self.raiz.exists():
                shutil.rmtree(self.raiz)
            for rel in COPIAR:
                src = self.origen / rel
                dst = self.raiz / rel
                if src.is_dir():
                    shutil.copytree(src, dst)
                elif src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
        else:
            self.raiz = self.origen
        (self.raiz / ".psrd-run").mkdir(parents=True, exist_ok=True)

    def p(self, rel: str) -> Path:
        return self.raiz / rel

    def existe(self, rel: str) -> bool:
        return self.p(rel).exists()

    def leer(self, rel: str, defecto: Any = None) -> Any:
        f = self.p(rel)
        if not f.exists():
            if defecto is not None:
                return defecto
            raise FileNotFoundError(f)
        return json.loads(f.read_text(encoding="utf-8"))

    def escribir(self, rel: str, data: Any) -> None:
        f = self.p(rel)
        indent, nl = (2, True)
        if f.exists():
            indent, nl = _formato(f.read_text(encoding="utf-8"))
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(dump_json(data, indent, nl), encoding="utf-8")

    def escribir_texto(self, rel: str, texto: str) -> None:
        f = self.p(rel)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(texto, encoding="utf-8")

    # --- run log shared by the scripts of one workflow run (never served) ---
    def resumen_run(self) -> dict:
        return self.leer(".psrd-run/resumen.json", {"fuentes": {}})

    def anotar_run(self, fuente: str, **datos: Any) -> None:
        r = self.resumen_run()
        r["fuentes"].setdefault(fuente, {}).update(datos)
        self.escribir(".psrd-run/resumen.json", r)


def guardar_texto_fuente(arbol: Arbol, texto: str) -> str:
    """Store the exact official text a summary is checked against, keyed by its
    sha256 (audit trail). Returns the sha."""
    sha = sha256_texto(texto)
    arbol.escribir_texto(f"pipeline-state/textos/{sha}.txt", texto)
    return sha


def encolar(arbol: Arbol, item: dict) -> bool:
    """Add or refresh one item in the AI writing queue. If the source text
    changed, attempts reset (the old summary is withdrawn by escribir.py)."""
    cola = arbol.leer("pipeline-state/cola_resumenes.json", {"items": []})
    # A published summary whose source text changed is withdrawn in this same
    # data commit (the site then shows "Resumen en preparación").
    if arbol.existe("docs/data/resumenes.json"):
        res = arbol.leer("docs/data/resumenes.json")
        viejo = res.get("resumenes", {}).get(item["id"])
        if viejo and viejo.get("fuente_sha256") != item.get("fuente_sha256"):
            del res["resumenes"][item["id"]]
            res.get("sin_resumen", {}).pop(item["id"], None)
            arbol.escribir("docs/data/resumenes.json", res)
        elif viejo:
            return False  # already written from this exact text
    for it in cola["items"]:
        if it["id"] == item["id"]:
            if it.get("fuente_sha256") != item.get("fuente_sha256"):
                it.update(item)
                it["intentos"] = 0
                arbol.escribir("pipeline-state/cola_resumenes.json", cola)
                return True
            return False
    item.setdefault("intentos", 0)
    cola["items"].append(item)
    arbol.escribir("pipeline-state/cola_resumenes.json", cola)
    return True


def texto_pdf(pdf: bytes) -> str:
    """PDF -> text. pdftotext (poppler; apt-get on the runner, a separate GPL
    program) is the primary tool. Local fallbacks: PyMuPDF (AGPL, only if
    installed), then pypdf (BSD)."""
    if shutil.which("pdftotext"):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(pdf)
            f.flush()
            out = subprocess.run(["pdftotext", "-enc", "UTF-8", f.name, "-"], capture_output=True, check=True)
            return out.stdout.decode("utf-8", errors="replace")
    try:
        import fitz  # type: ignore
        return "\n".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))
    except ImportError:
        import io
        import pypdf  # type: ignore
        return "\n".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
