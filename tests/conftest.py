import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "auto"))
sys.path.insert(0, str(ROOT / "scripts" / "gates"))
FIX = ROOT / "tests" / "fixtures"


def cargar(rel):
    return json.loads((FIX / rel).read_text(encoding="utf-8"))


@pytest.fixture
def arbol_copia(tmp_path):
    """A throwaway copy of everything the pipeline reads/writes."""
    for rel in ["docs/data", "docs/novedades.xml", "pipeline-state", "config", "src/app.ts",
                "scripts/diputados_stats.json"]:
        src, dst = ROOT / rel, tmp_path / rel
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    # Tests build a "new" acta 0127. Once the live robot has published 0127 (or
    # later actas), drop them from the copy so the tests keep testing a NEW acta
    # instead of a replacement (first live run, 2026-09-24).
    import json
    ses = tmp_path / "docs/data/sesiones.json"
    d = json.loads(ses.read_text())
    d["sesiones"] = [x for x in d["sesiones"] if str(x.get("acta", "")) < "0127"]
    ses.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    (tmp_path / ".psrd-run").mkdir()
    return tmp_path
