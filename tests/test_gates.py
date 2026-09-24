"""Every gate must block the thing it exists to block (and pass clean data)."""
import json
import shutil
from pathlib import Path

import pytest

import run_gates as G
from conftest import ROOT

SES = "docs/data/sesiones.json"


def correr(base: Path, nuevo: Path, recibos=None):
    g = G.Gates(G.Lado(dir=base), nuevo, nuevo / "config", ROOT / "schemas", recibos or [])
    ok = g.correr()
    return ok, g


def leer(d, rel):
    return json.loads((d / rel).read_text(encoding="utf-8"))


def escribir(d, rel, data):
    (d / rel).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


@pytest.fixture
def par(arbol_copia, tmp_path_factory):
    base = tmp_path_factory.mktemp("base")
    shutil.copytree(arbol_copia / "docs", base / "docs")
    return base, arbol_copia


def test_clean_tree_passes(par):
    ok, g = correr(*par)
    assert ok, g.fallos


def test_g2_named_senator_vote_is_blocked(par):
    base, n = par
    d = leer(n, SES)
    d["sesiones"][0]["votaciones"][0]["votos"] = [{"senador": "X", "voto": "si"}]
    escribir(n, SES, d)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G2") for f in g.fallos)


def test_g2_flag_flip_and_file_are_blocked(par):
    base, n = par
    app = n / "src" / "app.ts"
    app.write_text(app.read_text().replace("const MOSTRAR_VOTOS_POR_SENADOR = false;", "const MOSTRAR_VOTOS_POR_SENADOR = true;"))
    (n / "docs" / "data" / "votos_por_sesion.json").write_text("{}")
    ok, g = correr(base, n)
    msgs = " ".join(g.fallos)
    assert not ok and "MOSTRAR_VOTOS_POR_SENADOR" in msgs and "votos_por_sesion" in msgs


def test_g2_senator_with_votes_in_provincias(par):
    base, n = par
    p = leer(n, "docs/data/provincias.json")
    sen = next(l for pr in p["provincias"] for l in pr["lideres"] if l["cargo"].startswith("Senador"))
    sen["votos"] = [{"sesion": "1", "leyes": []}]
    escribir(n, "docs/data/provincias.json", p)
    assert not correr(base, n)[0]


def test_g3_impossible_totals(par):
    base, n = par
    d = leer(n, SES)
    d["sesiones"][0]["votaciones"][0]["a_favor"] = 30
    d["sesiones"][0]["votaciones"][0]["presentes"] = 20
    escribir(n, SES, d)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G3") for f in g.fallos)


def _acta_nueva(url="https://www.senadord.gob.do/Descargas/1387/actas-de-sesiones/62268/acta-num-0127"):
    return {"acta": "0127", "fecha": "2026-07-22", "tipo": "extraordinaria", "url_acta": url, "auto": True,
            "votaciones": [{"iniciativa": "01710-2026", "titulo": "Proyecto de ley X", "a_favor": 20, "presentes": 22,
                            "resultado": "Aprobado en primera discusión", "votacion_num": "003",
                            "fuente": "Acta 0127, votación electrónica 003"}],
            "asistencia": {"presentes": 22, "ausentes": 0, "detalle": []}}


def test_g4_new_acta_needs_official_host_and_receipt(par):
    base, n = par
    d = leer(n, SES)
    d["sesiones"].insert(0, _acta_nueva())
    escribir(n, SES, d)
    ok, g = correr(base, n)
    assert not ok and any("recibo" in f for f in g.fallos)
    ok, g = correr(base, n, [{"url": _acta_nueva()["url_acta"], "status": 200, "error": None}])
    assert ok, g.fallos
    d["sesiones"][0] = _acta_nueva("https://periodico.com.do/acta.pdf")
    escribir(n, SES, d)
    ok, g = correr(base, n, [{"url": "https://periodico.com.do/acta.pdf", "status": 200, "error": None}])
    assert not ok and any("dominio oficial" in f for f in g.fallos)


def test_g5_too_many_new_items(par):
    base, n = par
    d = leer(n, "docs/data/novedades.json")
    for i in range(2):
        d["novedades"].insert(0, {"fecha": "2026-09-30", "texto": f"Actualizamos algo número {i}.", "aporte": "a", "guid": f"g{i}"})
    escribir(n, "docs/data/novedades.json", d)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G5") for f in g.fallos)


def test_g6_deleting_an_acta_is_blocked(par):
    base, n = par
    d = leer(n, SES)
    d["sesiones"].pop()
    escribir(n, SES, d)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G6") for f in g.fallos)


def test_g7_empty_over_good_is_repaired_then_blocked_when_many(par):
    base, n = par
    d = leer(n, SES)
    d["sesiones"][0]["url_acta"] = ""
    escribir(n, SES, d)
    ok, g = correr(base, n)
    assert ok, g.fallos
    assert leer(n, SES)["sesiones"][0]["url_acta"].startswith("https://")  # old value restored in place
    p = leer(n, "docs/data/provincias.json")
    for pr in p["provincias"][:6]:
        pr["lideres"][0]["resumen"] = ""
    escribir(n, "docs/data/provincias.json", p)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G7") for f in g.fallos)


def test_g8_prose_outside_resumenes_is_blocked(par):
    base, n = par
    d = leer(n, "docs/data/leyes.json")
    d["sectores"][0]["leyes"][0]["que_es"] = "Texto nuevo que nadie verificó."
    escribir(n, "docs/data/leyes.json", d)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") for f in g.fallos)


def _resumen(sha, **k):
    r = {"tipo": "titulo_voto", "estado": "verificado", "estado_ley": "votando", "fuente_url": "https://www.senadord.gob.do/x.pdf",
         "fuente_nombre": "Acta", "fuente_sha256": sha, "modelo_escritor": "gemini-3.5-flash-lite",
         "modelo_revisor": "gemma-4-31b-it", "checks_pasados": 7, "checks_total": 7, "fecha": "2026-09-30",
         "titulo_facil": "Crear un sistema para cuidar a niños y personas mayores."}
    r.update(k)
    return r


def test_g8_resumen_must_be_fully_checked_and_sourced(par):
    base, n = par
    sha = "a" * 64
    (n / "pipeline-state" / "textos" / f"{sha}.txt").write_text("fuente")
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"]["senado-00636-2025"] = _resumen(sha)
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert ok, g.fallos
    res["resumenes"]["senado-00636-2025"] = _resumen(sha, checks_pasados=6)
    escribir(n, "docs/data/resumenes.json", res)
    assert not correr(base, n)[0]
    res["resumenes"]["senado-00636-2025"] = _resumen("b" * 64)
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any("texto fuente" in f for f in g.fallos)
    res["resumenes"]["senado-00636-2025"] = _resumen(sha, modelo_revisor="gemini-3.5-flash-lite")
    escribir(n, "docs/data/resumenes.json", res)
    assert not correr(base, n)[0]
    res["resumenes"]["senado-00636-2025"] = _resumen(sha, modelo_escritor="stub-escritor", modelo_revisor="stub-revisor")
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any("config/ia.json" in f for f in g.fallos)


@pytest.mark.parametrize("texto", ["Fue una ley excelente para el país.", "El PRM la aprobó.",
                                   "Lo propuso Jorge Frías en la Cámara."])
def test_g9_partisan_opinion_or_names_are_blocked(par, texto):
    base, n = par
    sha = "a" * 64
    (n / "pipeline-state" / "textos" / f"{sha}.txt").write_text("fuente")
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"]["x"] = _resumen(sha, titulo_facil=texto)
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G9") for f in g.fallos)


def test_g9_unpassed_bill_must_be_worded_as_proposal(par):
    base, n = par
    sha = "a" * 64
    (n / "pipeline-state" / "textos" / f"{sha}.txt").write_text("fuente")
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"]["p"] = _resumen(sha, tipo="proyecto", titulo_facil=None, te_afecta="Tendrás más agua en tu casa.")
    del res["resumenes"]["p"]["titulo_facil"]
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any("La propuesta busca" in f for f in g.fallos)


def test_g10_promulgation_date_never_changes(par):
    base, n = par
    v = leer(n, "docs/data/vigencia.json")
    v["leyes"][0]["promulgada"] = "2026-08-14"  # the 74-25 reprint trap
    escribir(n, "docs/data/vigencia.json", v)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G10") for f in g.fallos)


def test_g10_money_period_never_goes_back(par):
    base, n = par
    f = leer(n, "docs/data/finanzas.json")
    auto = {"valor_num": 5.13, "valor_texto": "5.13%", "periodo": "agosto 2026", "periodo_iso": "2026-08",
            "url": "https://cdn.bancentral.gov.do/x.xls", "fuente": "BCRD", "texto": "t", "comparacion": "c"}
    next(m for m in f["metricas"] if m["id"] == "inflacion")["auto"] = auto
    escribir(base, "docs/data/finanzas.json", f)
    f2 = json.loads(json.dumps(f))
    next(m for m in f2["metricas"] if m["id"] == "inflacion")["auto"] = dict(auto, periodo_iso="2026-07", valor_num=5.0)
    escribir(n, "docs/data/finanzas.json", f2)
    ok, g = correr(base, n, [{"url": auto["url"], "status": 200, "error": None}])
    assert not ok and any(f.startswith("G10") for f in g.fallos)


def test_g1_schema_rejects_unknown_estado(par):
    base, n = par
    v = leer(n, "docs/data/vigencia.json")
    v["leyes"][0]["estado"] = "quizas"
    escribir(n, "docs/data/vigencia.json", v)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G1") for f in g.fallos)
