import json
import re
import subprocess
import sys
from datetime import date

import camara as C
from conftest import FIX, ROOT, cargar
from red import FalloFuente


class ClienteFixture:
    """Serves the saved real SIL responses; page 2+ of a list is empty."""

    def get(self, url, esperado="json"):
        class R:
            def __init__(self, d):
                self.d = d

            def json(self):
                return self.d
        ruta = url.split("/legislador/", 1)[1]
        if ruta.startswith("legislador/"):
            return R(cargar(f"camara/legislador_{ruta.split('/')[1]}.json"))
        page = int(re.search(r"page=(\d+)", ruta).group(1))
        tipo = ruta.split("?")[0].lower()
        if page > 1:
            return R({"total": 0, "results": []})
        f = {"comisiones": "comisiones_1466_p1.json", "iniciativas": "iniciativas_1466_p1.json",
             "asistencias": "asistencias_1466_p1.json", "legisladores": "busqueda_jorge_frias.json"}[tipo]
        d = cargar(f"camara/{f}")
        d = dict(d, total=len(d["results"]))  # pretend the saved first page is the whole list
        return R(d)


def test_periodo_label_comes_from_data():
    assert C.etiqueta_periodo("2024-08-16", "2026-07-24") == "agosto 2024 a julio 2026"
    assert C.etiqueta_periodo("2026-09-02", "2026-09-09") == "septiembre 2026"
    assert C.etiqueta_periodo(None, "2026-09-09") is None


def test_frias_by_pinned_id_and_term_end():
    cam = C.Camara(ClienteFixture(), date(2026, 9, 24))
    # name search finds nobody (the real bug)...
    assert cam.buscar_id("Jorge Frías", "Santo Domingo")[0] is None
    # ...but the pinned ID works and the SIL says his term ended 2026-08-07
    row = cam.diputado(1466)
    assert row["cargo_hasta"] == "2026-08-07"
    assert row["asistencia"]["total"] == 10 and row["asistencia"]["hasta"] == "2026-07-24"
    pins = json.loads((ROOT / "config" / "diputados_ids.json").read_text())["ids"]
    assert pins["Jorge Frías"] == 1466 and len(pins) >= 178  # the robot may add pins


def test_old_period_profile_is_not_a_term_end():
    cam = C.Camara(ClienteFixture(), date(2026, 9, 24))
    # 3486's profile still carries the 2020-2024 period marked "En Curso"
    assert cam.diputado(3486)["cargo_hasta"] is None


def test_unmatched_keeps_old_numbers_with_their_own_date():
    roster = [{"nombre": "A", "provincia": "P"}, {"nombre": "B", "provincia": "P"}]
    old = {"_generated": "2026-07-20T12:00:00", "diputados": {
        "B": {"comisiones": ["X"], "iniciativas_cd": 3, "asistencia": {"presentes": 5, "total": 6}}}}

    def fetch(i):
        if i == 2:
            raise FalloFuente("HTTP 500")
        return {"comisiones": ["Y"], "iniciativas_cd": 1,
                "asistencia": {"presentes": 9, "total": 10, "desde": "2024-08-16", "hasta": "2026-09-09"}}
    new, nuevos = C.run_pull(roster, {"A": 1, "B": 2}, old, fetch, lambda n, p: (None, "x"), hilos=1)
    assert new["diputados"]["A"]["asistencia"]["presentes"] == 9
    b = new["diputados"]["B"]
    assert b["_sin_actualizar"] and b["datos_al"] == "2026-07-20" and b["asistencia"]["presentes"] == 5
    assert new["_unmatched"][0]["nombre"] == "B"


def test_sanity_guard_rejects_empty_and_collapse():
    assert not C.sanity_check(None, {"diputados": {}})[0]
    old = {"diputados": {str(i): {"comisiones": ["a"], "iniciativas_cd": 1, "asistencia": {"total": 10}} for i in range(10)}}
    new = {"diputados": {str(i): {"comisiones": ["a"], "iniciativas_cd": 1, "asistencia": {"total": 10}} for i in range(7)}}
    assert not C.sanity_check(old, new)[0]
    assert C.sanity_check(old, old)[0]


def test_self_test_empty_exits_1_and_writes_nothing():
    antes = (ROOT / "docs" / "data" / "provincias.json").read_bytes()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "auto" / "camara.py"), "--self-test-empty", "--dry-run"],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert (ROOT / "docs" / "data" / "provincias.json").read_bytes() == antes


def test_merge_writes_computed_label_and_dates():
    prov = {"provincias": [{"nombre": "Santo Domingo", "lideres": [
        {"cargo": "Diputado/a", "nombre": "Jorge Frías", "asistencia": {"presentes": 1, "total": 2, "periodo": "agosto 2024 a junio 2026", "fuente": "x"}},
        {"cargo": "Senador/a", "nombre": "S"}]}]}
    stats = {"diputados": {"Jorge Frías": {"comisiones": ["Hacienda"], "iniciativas_cd": 15, "cargo_hasta": "2026-08-07",
                                           "asistencia": {"presentes": 178, "total": 191, "desde": "2024-08-16", "hasta": "2026-07-24"}}}}
    C.fusionar(prov, stats)
    l = prov["provincias"][0]["lideres"][0]
    assert l["asistencia"]["periodo"] == "agosto 2024 a julio 2026"
    assert l["asistencia"]["datos_al"] == "2026-07-24" and l["cargo_hasta"] == "2026-08-07"
    assert "asistencia" not in prov["provincias"][0]["lideres"][1]
