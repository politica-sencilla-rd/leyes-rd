"""The page never renders data as raw HTML (X1: a new acta's 'resultado' was one).

Runs the real docs/app.js in Node against a fake DOM, with every string in every
data file poisoned with an HTML tag and every link turned into javascript:.
Any innerHTML write that still carries the tag, or any javascript: link, fails.
"""
import json
import shutil
import subprocess

import pytest

from conftest import ROOT

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node no está instalado")

# Each of these must show up in some innerHTML write, so the run really drew those parts.
COBERTURA = ["Aprobad", "Quién faltó", "votación electrónica", "Regidores de", "comisiones:", "Sueldo del cargo",
             "Lo que dice la ley", "En el SIL de la Cámara", "Resumen automático", "Mínimo:", "Datos al",
             "Gaceta Oficial"]


def _correr(modo):
    r = subprocess.run([NODE, str(ROOT / "tests" / "js" / "render_hostil.js"), str(ROOT), modo],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.parametrize("modo", ["todo", "textos"])
def test_x1_no_data_string_reaches_the_page_as_html(modo):
    d = _correr(modo)
    assert d["errores"] == [], d["errores"][:3]
    assert d["escrituras"] > 1000
    assert d["crudos"] == [], [h[:160] for h in d["crudos"][:10]]
    assert d["hrefs_js"] == [], d["hrefs_js"][:5]
    if modo == "textos":
        todo = "\n".join(d["html"])
        faltan = [c for c in COBERTURA if c not in todo]
        assert not faltan, f"el recorrido no dibujó: {faltan}"


def test_x1_app_js_is_the_build_of_app_ts(tmp_path):
    tsc = ROOT / "node_modules" / ".bin" / "tsc"
    if not tsc.exists():
        pytest.skip("typescript no está instalado (npm ci)")
    r = subprocess.run([str(tsc), "-p", str(ROOT / "tsconfig.json"), "--outDir", str(tmp_path)],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "app.js").read_bytes() == (ROOT / "docs" / "app.js").read_bytes(), \
        "docs/app.js no es el build de src/app.ts: corre npm run build"
