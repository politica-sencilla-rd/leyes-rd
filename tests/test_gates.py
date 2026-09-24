"""Every gate must block the thing it exists to block (and pass clean data)."""
import hashlib
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
    shutil.copytree(arbol_copia / "config", base / "config")  # the rulebook comes from the base
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


FUENTE = ("Proyecto de ley que crea el sistema nacional de cuidados. Presupuesto de 1500 millones. "
          "Aprobado en primera lectura por el Senado de la República.")


def _texto(n, fuente=FUENTE):
    """Store a source text the way escribir.py does (named by its sha256) -> sha."""
    sha = hashlib.sha256(fuente.encode("utf-8")).hexdigest()
    (n / "pipeline-state" / "textos").mkdir(parents=True, exist_ok=True)
    (n / "pipeline-state" / "textos" / f"{sha}.txt").write_text(fuente, encoding="utf-8")
    return sha


def _resumen(sha, **k):
    r = {"tipo": "titulo_voto", "estado": "verificado", "estado_ley": "votando", "fuente_url": "https://www.senadord.gob.do/x.pdf",
         "fuente_nombre": "Acta", "fuente_sha256": sha, "modelo_escritor": "gemini-3.5-flash-lite",
         "modelo_revisor": "gemma-4-31b-it", "checks_pasados": 7, "checks_total": 7, "fecha": "2026-09-30",
         "titulo_facil": "Crear un sistema para cuidar a niños y personas mayores."}
    r.update(k)
    return r


def test_g8_resumen_must_be_fully_checked_and_sourced(par):
    base, n = par
    sha = _texto(n)
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
    sha = _texto(n)
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"]["x"] = _resumen(sha, titulo_facil=texto)
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G9") for f in g.fallos)


def test_g9_unpassed_bill_must_be_worded_as_proposal(par):
    base, n = par
    sha = _texto(n)
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


# ---------------------------------------------------------------- review round 1 regressions
K = "senado-00636-2025"   # a Senate vote title: never law yet
K_LEY = "ley-74-25"       # a law in vigencia.json: promulgated


def _con_resumen(n, fuente=FUENTE, clave=None, **k):
    clave = clave or (K_LEY if k.get("estado_ley") == "promulgada" else K)
    sha = _texto(n, fuente)
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"] = {clave: _resumen(sha, **k)}
    escribir(n, "docs/data/resumenes.json", res)
    return clave


def _auto_dinero(mid="inflacion", **k):
    import dinero
    d = {"valor_num": 5.13, "anterior_num": 3.71, "periodo": "agosto 2026", "periodo_iso": "2026-08",
         "anterior_periodo": "agosto 2025", "url": "https://cdn.bancentral.gov.do/x.xls",
         "url_pagina": "https://www.bancentral.gov.do/a/d/2534-precios", "datos_al": "2026-08"}
    d.update(k)
    d.update(dinero.textos(mid, d, None))
    return d


def test_b1_g9_partial_roster_and_title_plus_name(par):
    base, n = par
    prov = leer(n, "docs/data/provincias.json")
    completo = next(l["nombre"] for p in prov["provincias"] for l in p["lideres"]
                    if l["cargo"].startswith("Senador") and len(l["nombre"].split()) >= 4)
    t = completo.split()
    for texto in (f"{t[0]} {t[-2]} propuso cuidar a los niños.", f"{t[0]} {t[1]} {t[-2]} propuso cuidar a los niños.",
                  "Lo propuso el ministro Juan Pérez Gómez."):
        _con_resumen(n, titulo_facil=texto)
        ok, g = correr(base, n)
        assert not ok and any(f.startswith("G9") and "persona" in f for f in g.fallos), (texto, g.fallos)


def test_b2_g3_money_jump_and_salary_range(par):
    base, n = par
    rec = [{"url": "https://cdn.bancentral.gov.do/x.xls", "status": 200, "error": None}]
    f = leer(n, "docs/data/finanzas.json")
    m = next(m for m in f["metricas"] if m["id"] == "inflacion")  # card on main says 5.35%
    m["auto"] = _auto_dinero()
    escribir(n, "docs/data/finanzas.json", f)
    ok, g = correr(base, n, rec)
    assert ok, g.fallos                                   # the real August number publishes
    m["auto"] = _auto_dinero(valor_num=28.0)               # in range, absurd jump
    escribir(n, "docs/data/finanzas.json", f)
    ok, g = correr(base, n, rec)
    assert not ok and any("G3" in x and "inflacion" in x for x in g.fallos)
    m["auto"] = _auto_dinero()
    s = next(m for m in f["metricas"] if m["id"] == "salario")
    s["auto"] = _auto_dinero("salario", valor_num=3.0, anterior_num=2.9, var_pct=3.45, periodo="junio 2026",
                             periodo_iso="2026-06", anterior_periodo="junio 2025")
    escribir(n, "docs/data/finanzas.json", f)
    ok, g = correr(base, n, rec)
    assert not ok and any("G3" in x and "salario" in x for x in g.fallos)


@pytest.mark.parametrize("campos,pista", [
    ({"titulo_facil": "Crear un sistema de cuidados con 9999 millones de pesos."}, "9999"),
    ({"titulo_facil": ""}, "vacío"),
    ({"tipo": "proyecto", "titulo_facil": None, "que_es": "Ya es ley el sistema de cuidados.",
      "por_que": "Para cuidar.", "te_afecta": "La propuesta busca cuidar a los niños.", "en_30_segundos": "Cuida."},
     "no aprobado"),
])
def test_n1_g8_rechecks_the_record_against_the_stored_source(par, campos, pista):
    base, n = par
    _con_resumen(n, **campos)
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"] = {c: {k: v for k, v in r.items() if v is not None} for c, r in res["resumenes"].items()}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any(pista in x for x in g.fallos), g.fallos


def test_n1_g8_money_amount_from_source_passes(par):
    base, n = par
    _con_resumen(n, titulo_facil="Crear un sistema de cuidados con 1500 millones.")
    ok, g = correr(base, n)
    assert ok, g.fallos


def test_n1_g8_old_summary_edited_without_new_source_is_blocked(par):
    base, n = par
    _con_resumen(base)
    _con_resumen(n, titulo_facil="Texto cambiado sin revisar por nadie.")
    ok, g = correr(base, n)
    assert not ok and any("sin un texto fuente nuevo" in x for x in g.fallos)


def test_n9_g7_emptied_top_level_list_fails_instead_of_repair(par):
    base, n = par
    escribir(n, SES, {"sesiones": []})
    ok, g = correr(base, n)
    assert not ok and any(x.startswith("G7") and "sesiones" in x for x in g.fallos)
    assert leer(n, SES)["sesiones"] == []  # not silently put back


def test_n9_g7_withdrawn_summary_is_not_restored(par):
    base, n = par
    _con_resumen(base)
    _texto(n)
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"] = {}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert ok, g.fallos
    assert leer(n, "docs/data/resumenes.json")["resumenes"] == {}


# ---------------------------------------------------------------- review round 3 (2026-09-24)
def test_r3_g8_source_must_hash_to_its_name_and_not_be_empty(par):
    base, n = par
    sha = _texto(n)
    falso = "b" * 64
    (n / "pipeline-state" / "textos" / f"{falso}.txt").write_text(FUENTE, encoding="utf-8")
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"]["x"] = _resumen(falso)
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any("no corresponde a su sha256" in f for f in g.fallos), g.fallos
    # empty source (its sha is the sha of "") and a too-short one for a bill
    for fuente, tipo in (("", "titulo_voto"), ("Crea el sistema.", "titulo_voto"), ("Proyecto de ley de cuidados.", "ley")):
        campos = {"tipo": tipo, "titulo_facil": None, "que_es": "Crea un sistema de cuidados."} if tipo == "ley" else {}
        _con_resumen(n, fuente, **campos)
        res = leer(n, "docs/data/resumenes.json")
        res["resumenes"] = {c: {k: v for k, v in r.items() if v is not None} for c, r in res["resumenes"].items()}
        escribir(n, "docs/data/resumenes.json", res)
        ok, g = correr(base, n)
        assert not ok and any("caracteres" in f for f in g.fallos), (fuente, g.fallos)
    # a real one-line Senate title (40 characters) still publishes
    _con_resumen(n, "Proyecto de ley de eficiencia energética", titulo_facil="Ahorrar energía.")
    ok, g = correr(base, n)
    assert ok, g.fallos
    assert sha


def test_r3_rulebook_is_read_from_the_base_not_the_new_tree(par):
    base, n = par
    ia = leer(n, "config/ia.json")
    ia["escritores"].append("stub-escritor")
    ia["revisores"].append("stub-revisor")
    escribir(n, "config/ia.json", ia)
    neu = leer(n, "config/neutralidad.json")
    neu["prohibidas"] = []
    escribir(n, "config/neutralidad.json", neu)
    _con_resumen(n, modelo_escritor="stub-escritor", modelo_revisor="stub-revisor",
                 titulo_facil="Un sistema de cuidados excelente.")
    ok, g = correr(base, n)
    assert not ok
    assert any(f.startswith("G0") and "config/ia.json" in f for f in g.fallos), g.fallos
    assert any(f.startswith("G0") and "config/neutralidad.json" in f for f in g.fallos)
    assert any(f.startswith("G8") and "no están en config/ia.json" in f for f in g.fallos)   # base models
    assert any(f.startswith("G9") and "excelente" in f for f in g.fallos)                    # base word list


def test_r3_g0_only_diputados_ids_may_change_and_base_must_have_rules(par):
    base, n = par
    ids = leer(n, "config/diputados_ids.json")
    escribir(n, "config/diputados_ids.json", ids)  # re-written (different formatting) = changed
    ok, g = correr(base, n)
    assert ok, g.fallos
    (n / "config" / "nuevo.json").write_text("{}")
    ok, g = correr(base, n)
    assert not ok and any("config/nuevo.json" in f for f in g.fallos)
    (n / "config" / "nuevo.json").unlink()
    shutil.rmtree(base / "config")
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G0") and "no existe en la base" in f for f in g.fallos)


def test_r3_g8_checks_every_prose_field_and_enough_checks(par):
    base, n = par
    # a 'ley' record carrying an extra field the writer never asked for
    _con_resumen(n, tipo="ley", estado_ley="promulgada", titulo_facil=None, que_es="Crea un sistema de cuidados.",
                 te_afecta="Pagarás 999 pesos más.")
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"] = {c: {k: v for k, v in r.items() if v is not None} for c, r in res["resumenes"].items()}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok
    assert any("te_afecta no se pide" in f for f in g.fallos), g.fallos
    assert any(f"{K_LEY}.te_afecta: el número 999" in f for f in g.fallos)
    # 4 prose fields but 1/1 checks
    _con_resumen(n, tipo="proyecto", checks_pasados=1, checks_total=1, titulo_facil=None,
                 que_es="Crea un sistema de cuidados.", por_que="Para cuidar a niños.",
                 te_afecta="La propuesta busca cuidar a niños.", en_30_segundos="Un sistema de cuidados.")
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"] = {c: {k: v for k, v in r.items() if v is not None} for c, r in res["resumenes"].items()}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any("1 revisiones para 4 campos" in f for f in g.fallos), g.fallos
    res["resumenes"][K].update(checks_pasados=25, checks_total=25)
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert ok, g.fallos


def _nota_voto(n, nota):
    ses = leer(n, SES)
    ses["sesiones"][0]["votaciones"][0]["nota"] = nota
    escribir(n, SES, ses)
    return ses["sesiones"][0]["votaciones"][0]


def test_r3_vote_note_is_scanned_for_names_opinions_and_numbers(par):
    base, n = par
    prov = leer(n, "docs/data/provincias.json")
    sen = next(l["nombre"].split() for p in prov["provincias"] for l in p["lideres"]
               if l["cargo"].startswith("Senador") and len(l["nombre"].split()) >= 4)
    _nota_voto(n, f"Aquí votó {sen[0]} {sen[-2]} en contra.")
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G9") and "nota" in f and "persona" in f for f in g.fallos), g.fallos
    _nota_voto(n, "Una votación lamentable.")
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G9") and "lamentable" in f for f in g.fallos)
    v = _nota_voto(n, "El acta dice 99 a favor.")
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") and "99" in f for f in g.fallos), g.fallos
    _nota_voto(n, f"El acta dice {v['a_favor']} a favor con {v['presentes']} presentes.")
    rec = [{"url": leer(n, SES)["sesiones"][0]["url_acta"], "status": 200, "error": None}]  # changed acta: G4 receipt
    ok, g = correr(base, n, rec)
    assert ok, g.fallos


def _novedad(n, texto):
    nov = leer(n, "docs/data/novedades.json")
    nov["novedades"].insert(0, {"fecha": "2026-09-30", "texto": texto, "aporte": "🔄 Actualización automática",
                                "guid": "psrd-auto-x", "auto": True})
    escribir(n, "docs/data/novedades.json", nov)


@pytest.mark.parametrize("texto", ["El gobierno hizo un trabajo lamentable.",
                                   "Los impuestos subirán 40% el mes que viene.",
                                   "Agregamos 3 sesiones del Senado (actas 0107 a 0127), leídas de las actas oficiales. "
                                   "Los impuestos subirán 40%."])
def test_r3_novedad_must_come_from_the_templates(par, texto):
    base, n = par
    _novedad(n, texto)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") and "plantillas" in f for f in g.fallos), g.fallos


def test_r3_novedad_from_templates_passes_and_ids_must_exist(par):
    import novedades as N
    base, n = par
    # this commit really adds the 2 newest actas, 1 summary and the August inflation number
    ses = leer(base, SES)
    ses["sesiones"] = sorted(ses["sesiones"], key=lambda s: s["acta"])[:-2]
    escribir(base, SES, ses)
    actas = sorted(s["acta"] for s in leer(n, SES)["sesiones"])[-2:]
    ses = leer(n, SES)
    for s in ses["sesiones"]:
        if s["acta"] in actas:   # a robot-read acta has no hand-written plain titles
            for v in s.get("votaciones", []):
                v.pop("titulo_facil", None)
    escribir(n, SES, ses)
    rec = [{"url": s["url_acta"], "status": 200, "error": None} for s in leer(n, SES)["sesiones"] if s["acta"] in actas]
    rec.append({"url": _auto_dinero()["url"], "status": 200, "error": None})
    _con_resumen(n)
    f = leer(n, "docs/data/finanzas.json")
    next(m for m in f["metricas"] if m["id"] == "inflacion")["auto"] = _auto_dinero()
    escribir(n, "docs/data/finanzas.json", f)
    _, fr = N.frases_de({"senado_actas": {"nuevas": actas}, "dinero": {"cambiados": ["inflacion (agosto 2026)"]},
                         "resumenes_ia": {"verificados": 1}}, {})
    _novedad(n, " ".join(fr))
    ok, g = correr(base, n, rec)
    assert ok, g.fallos
    _novedad(n, "Nueva ley en «¿Ya está vigente?»: 999-26.")
    ok, g = correr(base, n)
    assert not ok and any("la ley 999-26 no está" in f for f in g.fallos), g.fallos


def test_r3_g5_too_many_new_summaries(par):
    base, n = par
    sha = _texto(n)
    res = leer(n, "docs/data/resumenes.json")
    for i in range(21):
        res["resumenes"][f"s{i}"] = _resumen(sha)
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G5") and "21 resúmenes" in f for f in g.fallos), g.fallos


@pytest.mark.parametrize("texto,bloquea", [
    ("Evangelina Rodríguez propone cuidar a niños.", True),
    ("Lo propone Evangelina Rodríguez para cuidar a niños.", True),
    ("La Cámara de Diputados aprobó cuidar a niños.", False),
    ("Crea un sistema de cuidados en Santo Domingo.", False),
    ("Lo pide el Banco Central para cuidar a niños.", False),
])
def test_r3_bare_names_are_blocked_institutions_and_places_are_not(par, texto, bloquea):
    from comun import nombre_suelto
    assert (nombre_suelto(texto) is not None) is bloquea
    base, n = par
    _con_resumen(n, fuente=FUENTE + " Cámara de Diputados, Santo Domingo, Banco Central.", titulo_facil=texto)
    ok, g = correr(base, n)
    assert (any(f.startswith("G9") and "persona" in f for f in g.fallos)) is bloquea, g.fallos


def test_r3_bill_presented_as_law_is_blocked_by_code(par):
    base, n = par
    _con_resumen(n, titulo_facil="El Congreso aprobó el sistema de cuidados y ahora rige.")
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") and "presenta como ley" in f for f in g.fallos), g.fallos
    # the same words on a law that is already promulgated are fine
    _con_resumen(n, estado_ley="promulgada", titulo_facil="El Congreso aprobó el sistema de cuidados y ahora rige.")
    ok, g = correr(base, n)
    assert ok, g.fallos


def test_r3_hand_written_money_card_cannot_change(par):
    base, n = par
    fin = leer(n, "docs/data/finanzas.json")
    next(m for m in fin["metricas"] if m["id"] == "inflacion")["valor"] = "99% en un año"
    escribir(n, "docs/data/finanzas.json", fin)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") and "inflacion" in f for f in g.fallos), g.fallos


# ---------------------------------------------------------------- review round 4 (2026-09-24)
@pytest.mark.parametrize("texto,bloquea", [
    ("EVANGELINA RODRÍGUEZ propone cuidar a niños.", True),
    ("Evangelina RODRÍGUEZ propone cuidar a niños.", True),
    ("Lo aprobó la CÁMARA DE DIPUTADOS para cuidar a niños.", False),
    ("Crea un sistema de cuidados en SANTO DOMINGO.", False),
])
def test_r4_bare_names_in_capitals_are_blocked(par, texto, bloquea):
    from comun import nombre_suelto
    assert (nombre_suelto(texto) is not None) is bloquea
    base, n = par
    _con_resumen(n, fuente=FUENTE + " CÁMARA DE DIPUTADOS, SANTO DOMINGO.", titulo_facil=texto)
    ok, g = correr(base, n)
    assert (any(f.startswith("G9") and "persona" in f for f in g.fallos)) is bloquea, g.fallos


def test_r4_bare_ya_is_not_law_but_ya_es_ley_is():
    from comun import PARECE_LEY
    assert not PARECE_LEY.search("Crear un sistema para que los niños ya no queden solos.")
    assert PARECE_LEY.search("Ya es ley: crear un sistema de cuidados.")


def _bill_auto(estado="votando"):
    return {"id": "01234-2026", "sil_id": 91234, "titulo": "Proyecto de ley de cuidados",
            "titulo_oficial": "PROYECTO DE LEY DE CUIDADOS", "estado": estado, "estado_sil": "Aprobado en 1ra. lectura",
            "votos": [], "camara": True, "origen": "Cámara de Diputados", "materia": "SALUD",
            "url_oficial": "https://www.diputadosrd.gob.do/sil", "datos_al": "2026-09-24", "auto": True}


def test_r4_law_or_not_comes_from_the_data_not_the_record(par):
    from comun import estado_ley_de
    base, n = par
    # a Senate vote title that calls itself 'promulgada' to skip the "not law yet" checks (craft4 H7b)
    _con_resumen(n, clave=K, estado_ley="promulgada", titulo_facil="Ya es ley: crear un sistema para cuidar a niños.")
    ok, g = correr(base, n)
    assert not ok and any("los datos dicen 'votando'" in f for f in g.fallos), g.fallos
    assert any("presenta como ley" in f for f in g.fallos)
    # a key that points at nothing on the site
    for clave in ("x", "ley-999-99", "sil-01234-2026"):
        _con_resumen(n, clave=clave)
        ok, g = correr(base, n)
        assert not ok and any("no corresponde a ningún" in f for f in g.fallos), (clave, g.fallos)
    # a SIL bill: the record must carry the bill's own estado from leyes.json
    for d in (base, n):
        ly = leer(d, "docs/data/leyes.json")
        ly["sectores"][0]["leyes"].insert(0, _bill_auto())
        escribir(d, "docs/data/leyes.json", ly)
    _con_resumen(n, clave="sil-01234-2026", estado_ley="aprobada", titulo_facil="Ahora rige un sistema de cuidados.")
    ok, g = correr(base, n)
    assert not ok and any("los datos dicen 'votando'" in f for f in g.fallos), g.fallos
    _con_resumen(n, clave="sil-01234-2026", titulo_facil="Crear un sistema para cuidar a niños.")
    ok, g = correr(base, n)
    assert ok, g.fallos
    assert estado_ley_de("sil-01234-2026", leer(n, "docs/data/leyes.json"), None) == "votando"
    assert estado_ley_de("ley-74-25", None, leer(n, "docs/data/vigencia.json")) == "promulgada"


def test_r4_escribir_takes_law_state_from_the_data(arbol_copia, monkeypatch):
    import escribir as E
    from comun import Arbol, sha256_texto
    monkeypatch.setattr(E, "Arbol", lambda nombre, dry_run=False: Arbol(nombre, base=arbol_copia))
    t = ("Proyecto de ley que autoriza el pago a contratistas del Estado y crea una comisión para la revisión "
         "de reclamaciones derivadas de obras ejecutadas con o sin contrato formal")
    sha = sha256_texto(t)
    (arbol_copia / "pipeline-state" / "textos" / f"{sha}.txt").write_text(t)
    items = [{"id": k, "tipo": "titulo_voto", "estado_ley": "promulgada", "fuente_url": "https://www.senadord.gob.do/x",
              "fuente_sha256": sha, "intentos": 0} for k in ("senado-01531-2026", "raro-1")]
    (arbol_copia / "pipeline-state" / "cola_resumenes.json").write_text(json.dumps({"items": items}))
    assert E.main(["--stub"]) == 0
    res = json.loads((arbol_copia / "docs/data/resumenes.json").read_text())["resumenes"]
    assert res["senado-01531-2026"]["estado_ley"] == "votando"
    assert "raro-1" not in res


def test_r4_money_card_text_must_be_what_the_numbers_say(par):
    base, n = par
    rec = [{"url": "https://cdn.bancentral.gov.do/x.xls", "status": 200, "error": None}]
    f = leer(n, "docs/data/finanzas.json")
    m = next(m for m in f["metricas"] if m["id"] == "inflacion")
    # craft4 N6: valor_num is fine, the headline and sentences the page shows are not
    m["auto"] = dict(_auto_dinero(), valor_texto="99%", texto="Lo que costaba RD$100 hace un año, hoy cuesta como RD$199.",
                     comparacion="Hace un año (agosto 2025) fue 3.71%; ahora (agosto 2026) es 99%. Los precios suben más rápido que hace un año.")
    escribir(n, "docs/data/finanzas.json", f)
    ok, g = correr(base, n, rec)
    assert not ok
    for campo in ("valor_texto", "texto", "comparacion"):
        assert any(x.startswith("G3") and f"inflacion.{campo}" in x for x in g.fallos), (campo, g.fallos)
    # free words hidden in a period are not a period
    m["auto"] = _auto_dinero(periodo="agosto 2026 (el gobierno mintió)")
    escribir(n, "docs/data/finanzas.json", f)
    ok, g = correr(base, n, rec)
    assert not ok and any("no es un período" in x for x in g.fallos), g.fallos
    m["auto"] = _auto_dinero()
    escribir(n, "docs/data/finanzas.json", f)
    ok, g = correr(base, n, rec)
    assert ok, g.fallos


def _diputado(d):
    return next(l for p in d["provincias"] for l in p["lideres"] if l["cargo"] == "Diputado/a" and l.get("asistencia"))


def _mut_vig(campo, valor, extra=None):
    def f(n):
        v = leer(n, "docs/data/vigencia.json")
        v["leyes"][0][campo] = valor
        v["leyes"][0].update(extra or {})
        escribir(n, "docs/data/vigencia.json", v)
    return f


def _mut_ley(campo, valor):
    def f(n):
        ly = leer(n, "docs/data/leyes.json")
        ly["sectores"][0]["leyes"][0][campo] = valor
        escribir(n, "docs/data/leyes.json", ly)
    return f


def _mut_lider(fn):
    def f(n):
        p = leer(n, "docs/data/provincias.json")
        fn(_diputado(p))
        escribir(n, "docs/data/provincias.json", p)
    return f


@pytest.mark.parametrize("mutar", [
    _mut_vig("titulo", "Código Penal del corrupto Luis Abinader"),                       # N3a
    _mut_vig("url_documento", "https://evil.example/ley.pdf"),                           # N3b
    _mut_vig("vigencia_texto", "<img src=x onerror=alert(1)> Rige desde 2099."),        # N3c (innerHTML)
    _mut_vig("estado", "vigencia", {"vigencia_fecha": "2025-01-01"}),                   # estado-only flip
    _mut_vig("auto", True),                                                              # re-labelled as robot's
    _mut_ley("estado", "aprobada"),                                                      # N4 estado only
    _mut_ley("url_oficial", "https://evil.example/x"),                                   # N4b
    _mut_lider(lambda l: l.update(partido="PLD")),                                       # N5a
    _mut_lider(lambda l: l.update(registro="otro")),
    _mut_lider(lambda l: l["asistencia"].update(nota="Este diputado nunca va.", presentes=1)),  # N5b
    _mut_lider(lambda l: l["asistencia"].update(fuente="me lo dijeron")),
    _mut_lider(lambda l: l["asistencia"].update(periodo="siempre falta")),
    _mut_lider(lambda l: l.update(comisiones=["<img src=x onerror=alert(1)>"])),
    lambda n: escribir(n, "docs/data/finanzas.json", dict(leer(n, "docs/data/finanzas.json"), metricas=leer(
        n, "docs/data/finanzas.json")["metricas"] + [{"id": "nueva", "valor": "99%"}])),
], ids=["vig-titulo", "vig-url", "vig-texto", "vig-estado", "vig-auto", "ley-estado", "ley-url", "partido",
        "registro", "asis-nota", "asis-fuente", "asis-periodo", "comisiones-html", "tarjeta-nueva"])
def test_r4_hand_written_records_are_frozen(par, mutar):
    base, n = par
    mutar(n)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") for f in g.fallos), g.fallos


def test_r4_normal_camara_update_still_passes(par):
    import camara
    base, n = par
    p = leer(n, "docs/data/provincias.json")
    dips = [l for pr in p["provincias"] for l in pr["lideres"] if l["cargo"] == "Diputado/a" and l.get("asistencia")]
    uno, dos = dips[0], dips[1]
    stats = {"diputados": {
        uno["nombre"]: {"comisiones": ["Comisión Permanente de Justicia"], "iniciativas_cd": 7, "cargo_hasta": None,
                        "asistencia": {"presentes": 90, "total": 100, "desde": "2024-08-16", "hasta": "2026-07-24"}},
        dos["nombre"]: {"_sin_actualizar": True, "datos_al": "2026-06-30"}}}
    camara.fusionar(p, stats)
    escribir(n, "docs/data/provincias.json", p)
    assert _diputado(leer(n, "docs/data/provincias.json"))["asistencia"]["periodo"] == "agosto 2024 a julio 2026"
    ok, g = correr(base, n)
    assert ok, g.fallos


def test_real_long_committee_names_pass(par):
    """2026-09-24 first live run: real Cámara special-committee names reach 223
    characters and a 200-char cap false-blocked the whole deputy update."""
    import camara
    base, n = par
    p = leer(n, "docs/data/provincias.json")
    uno = [l for pr in p["provincias"] for l in pr["lideres"] if l["cargo"] == "Diputado/a" and l.get("asistencia")][0]
    largo = ("05199-2024-2028-CD Comisión Especial designada para el estudio del proyecto de ley que autoriza "
             "el pago de deuda por obras ejecutadas sin contrato formal y otras disposiciones relacionadas con "
             "la deuda pública y los contratos del Estado.")
    assert 200 < len(largo) <= 400
    camara.fusionar(p, {"diputados": {uno["nombre"]: {"comisiones": [largo], "iniciativas_cd": 7, "cargo_hasta": None,
        "asistencia": {"presentes": 90, "total": 100, "desde": "2024-08-16", "hasta": "2026-07-24"}}}})
    escribir(n, "docs/data/provincias.json", p)
    ok, g = correr(base, n)
    assert ok, g.fallos


def test_r4_novedad_aporte_is_fixed_and_old_ones_never_change(par):
    base, n = par
    for aporte in ("El PRM es corrupto y Luis Abinader también", "<img src=x onerror=alert(1)>"):
        nov = leer(base, "docs/data/novedades.json")
        nov["novedades"].insert(0, {"fecha": "2026-09-30", "texto": "Actualizamos en qué va 1 proyecto de ley.",
                                    "aporte": aporte, "guid": "psrd-auto-c", "auto": True})
        escribir(n, "docs/data/novedades.json", nov)
        ok, g = correr(base, n)
        assert not ok and any(f.startswith("G8") and "aporte" in f for f in g.fallos), g.fallos
    nov = leer(base, "docs/data/novedades.json")
    nov["novedades"][0]["aporte"] = "Texto nuevo sin revisar."
    escribir(n, "docs/data/novedades.json", nov)
    ok, g = correr(base, n)
    assert not ok and any("ya publicada cambió" in f for f in g.fallos), g.fallos


def test_r4_sin_resumen_link_must_be_official(par):
    base, n = par
    res = leer(n, "docs/data/resumenes.json")
    res["sin_resumen"]["senado-00636-2025"] = {"intentos": 3, "fuente_url": "https://evil.example/phish.pdf"}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G4") and "sin_resumen" in f for f in g.fallos), g.fallos
    res["sin_resumen"]["senado-00636-2025"]["fuente_url"] = "https://www.senadord.gob.do/x.pdf"
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert ok, g.fallos


def test_r4_stray_file_in_docs_data_and_edited_feed_are_blocked(par):
    base, n = par
    (n / "docs" / "data" / "aviso.html").write_text("<h1>aviso</h1>")
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G1") and "aviso.html" in f for f in g.fallos), g.fallos
    (n / "docs" / "data" / "aviso.html").unlink()
    xml = (n / "docs" / "novedades.xml").read_text(encoding="utf-8")
    (n / "docs" / "novedades.xml").write_text(xml.replace("</channel>", "<item><title>x</title></item></channel>"),
                                              encoding="utf-8")
    ok, g = correr(base, n)
    assert not ok and any("novedades.xml" in f for f in g.fallos), g.fallos


def test_r4_no_procesada_motivo_is_a_fixed_form(par):
    base, n = par
    url = "https://www.senadord.gob.do/Descargas/1387/actas-de-sesiones/99999/acta-num-0199"
    rec = [{"url": url, "status": 200, "error": None}]
    for motivo, pasa in (("El senador Omar Fernández es corrupto, dice el PRM.", False),
                         ("votaciones sin leer: 004, 007", True)):
        ses = leer(base, SES)
        ses["sesiones"].insert(0, {"acta": "0199", "fecha": "2026-09-01", "estado": "no_procesada", "url_acta": url,
                                   "auto": True, "motivo": motivo})
        escribir(n, SES, ses)
        ok, g = correr(base, n, rec)
        assert ok is pasa, (motivo, g.fallos)


@pytest.mark.parametrize("texto,pista", [
    ("Agregamos 999 proyectos de ley que pasaron una votación en el Congreso.", "999 proyectos"),       # craft4 H4d
    ("Actualizamos las cifras del país: inflación (subio a 40 en agosto 2026).", "plantillas"),          # craft4 H4e
    ("Actualizamos las cifras del país: inflación (agosto 2026).", "no es una cifra que cambió"),
])
def test_r4_novedad_counts_and_periods_must_match_the_commit(par, texto, pista):
    base, n = par
    _novedad(n, texto)
    ok, g = correr(base, n)
    assert not ok and any(pista in f for f in g.fallos), g.fallos


def test_r4_new_law_vigencia_texto_is_a_fixed_form(par):
    import vigencia as V
    base, n = par
    url = "https://www.consultoria.gov.do/api/document/1"
    ley = {"numero": "9-26", "titulo": "Ley de cuidados", "titulo_oficial": "LEY DE CUIDADOS", "promulgada": "2026-09-01",
           "publicada": "2026-09-02", "gaceta": "11200", "estado": "vigencia", "vigencia_fecha": "2026-09-03",
           "vigencia_texto": V.TXT_DEFECTO, "regla": "regla_por_defecto", "fuente": "Ley 9-26",
           "url_documento": url, "url_busqueda": "https://www.consultoria.gov.do/consultas", "auto": True,
           "datos_al": "2026-09-24"}
    rec = [{"url": url, "status": 200, "error": None}]
    for texto, pasa in (("Rige desde hoy gracias al senador Omar Fernández.", False), (V.TXT_DEFECTO, True)):
        v = leer(base, "docs/data/vigencia.json")
        v["leyes"].insert(0, dict(ley, vigencia_texto=texto))
        escribir(n, "docs/data/vigencia.json", v)
        ok, g = correr(base, n, rec)
        assert ok is pasa, (texto, g.fallos)


def test_r4_normal_leyes_update_still_passes(par):
    import leyes as L
    base, n = par
    conf = leer(n, "config/sil.json")
    for d in (base, n):
        ly = leer(d, "docs/data/leyes.json")
        ly["sectores"][0]["leyes"].insert(0, _bill_auto())
        escribir(d, "docs/data/leyes.json", ly)
    fila = lambda i, num, estado, tipo="Proyecto de Ley": {  # noqa: E731
        "id": i, "numero": num, "estado": estado, "numPromulgacion": None, "tipo": tipo, "descripcion": "PROYECTO DE LEY X",
        "materia": "SALUD PÚBLICA Y ASISTENCIA SOCIAL", "camaraInicio": "Cámara de Diputados",
        "fechaUltimoCambioPrincipal": "2026-09-20"}
    snap = {"91234": ["Aprobado en 1ra. lectura", None], "95555": ["Depositado", None]}
    filas = [fila(91234, "01234-2026", "Promulgado"), fila(95555, "05555-2026", "Aprobado en 1ra. lectura")]
    data, _, rep = L.aplicar(filas, snap, leer(n, "docs/data/leyes.json"), conf, "2026-09-30", 40)
    assert rep["actualizadas"] == ["01234-2026"] and len(rep["nuevas"]) == 1
    escribir(n, "docs/data/leyes.json", data)
    ok, g = correr(base, n)
    assert ok, g.fallos


# ------------------------------------------------------------------ review round 5
RECIBO_0127 = [{"url": _acta_nueva()["url_acta"], "status": 200, "error": None}]


def _con_acta(n, **cambios):
    d = leer(n, SES)
    a = _acta_nueva()
    a["votaciones"][0].update(cambios.pop("voto", {}))
    a.update(cambios)
    d["sesiones"].insert(0, a)
    escribir(n, SES, d)


@pytest.mark.parametrize("resultado", ["Aprobado <img src=x onerror=alert(1)>", "<b>Aprobado</b>",
                                       "Aprobado en primera discusión<script>"])
def test_x1_vote_result_with_html_is_blocked(par, resultado):
    base, n = par
    _con_acta(n, voto={"resultado": resultado})
    ok, g = correr(base, n, RECIBO_0127)
    assert not ok, g.fallos
    assert any(f.startswith("G1") and "resultado" in f for f in g.fallos), g.fallos
    assert any(f.startswith("G9") and "resultado" in f and "'<'" in f for f in g.fallos), g.fallos


def test_x1_every_real_vote_result_passes_the_schema_and_g9(par):
    base, n = par
    reales = sorted({v["resultado"] for s in leer(n, SES)["sesiones"] for v in s.get("votaciones", [])})
    d = leer(n, SES)
    a = _acta_nueva()
    a["votaciones"] = [dict(a["votaciones"][0], iniciativa=f"{i:05d}-2026", votacion_num=f"{i:03d}", resultado=r,
                            fuente=f"Acta 0127, votación electrónica {i:03d}") for i, r in enumerate(reales, 1)]
    d["sesiones"].insert(0, a)
    escribir(n, SES, d)
    ok, g = correr(base, n, RECIBO_0127)
    assert ok, g.fallos


@pytest.mark.parametrize("fuente", ["Acta 0127, votación electrónica 003 <i>", "Según el periódico",
                                    "Acta 127, votación electrónica 3"])
def test_b_vote_fuente_is_the_fixed_acta_form(par, fuente):
    base, n = par
    _con_acta(n, voto={"fuente": fuente})
    ok, g = correr(base, n, RECIBO_0127)
    assert not ok and any(f.startswith("G1") and "fuente" in f for f in g.fallos), g.fallos


@pytest.mark.parametrize("nombre,bloquea", [
    ("Félix Ramón Bautista Rosario", False),              # acta form of "Félix Bautista Rosario"
    ("Héctor Elpidio Acosta Restituyo", False),           # acta form of "Héctor E. Acosta"
    ("Ginnette Altagracia Bournigal Socías de Jiménez", False),
    ("Juan Pérez", True),                                 # not a senator
    ("Félix Bautista Rosario es corrupto", True),         # free text after a real name
    ("Félix Bautista Rosario <img src=x>", True),
    ("Omar Fernández", False),                            # short form of "Omar Leonel Fernández Domínguez"
    ("Luis Rodolfo Abinader Corona", True),               # a public person who is not a senator
])
def test_c_absence_names_must_be_senators_on_main(par, nombre, bloquea):
    base, n = par
    _con_acta(n, asistencia={"presentes": 22, "ausentes": 1, "detalle": [{"nombre": nombre, "estado": "excusado"}]})
    ok, g = correr(base, n, RECIBO_0127)
    assert (not ok) is bloquea, g.fallos
    if bloquea:
        assert any("asistencia.detalle" in f or "nombre" in f for f in g.fallos), g.fallos


def test_d_resumenes_nota_is_frozen_and_sin_resumen_takes_no_extra_fields(par):
    base, n = par
    res = leer(n, "docs/data/resumenes.json")
    res["_nota"] = "Resúmenes escritos por un robot <b>confiable</b>."
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") and "resumenes.json" in f for f in g.fallos), g.fallos
    res = leer(base, "docs/data/resumenes.json")
    res["sin_resumen"]["senado-00636-2025"] = {"intentos": 3, "motivo": "<b>x</b>"}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G1") and "sin_resumen" in f for f in g.fallos), g.fallos


@pytest.mark.parametrize("fuente_nombre", ["Acta de Evangelina Rodríguez", "Acta <i>0127</i>"])
def test_d_resumen_fuente_nombre_is_scanned(par, fuente_nombre):
    base, n = par
    _con_resumen(n, fuente_nombre=fuente_nombre)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G9") and "fuente_nombre" in f for f in g.fallos), g.fallos


def test_d_real_fuente_nombre_forms_pass(par):
    base, n = par
    for fn in ("Acta 0106, votación electrónica 003", "SIL de la Cámara, iniciativa 01234-2026",
               "Ley 5-26, Gaceta Oficial 11230"):
        _con_resumen(n, fuente_nombre=fn)
        ok, g = correr(base, n)
        assert ok, (fn, g.fallos)


@pytest.mark.parametrize("mutar", [
    lambda e: e["fuentes"]["senado_actas"].update(retraso="El Senado esconde sus actas <b>a propósito</b>."),
    lambda e: e["fuentes"]["senado_actas"].update(nombre="Actas secretas"),
    lambda e: e["fuentes"]["senado_actas"].update(url_fuente="https://www.senadord.gob.do/otra"),
    lambda e: e["fuentes"]["dinero_deuda"].update(seccion="leyes"),
    lambda e: e["fuentes"].update(nueva={"nombre": "Fuente nueva", "estado": "ok", "fallos_seguidos": 0}),
])
def test_e_estado_fuentes_copies_config_fuentes_from_main(par, mutar):
    base, n = par
    e = leer(n, "docs/data/estado-fuentes.json")
    mutar(e)
    escribir(n, "docs/data/estado-fuentes.json", e)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") and "estado-fuentes" in f for f in g.fallos), g.fallos


def test_e_estado_fuentes_normal_update_passes(par):
    base, n = par
    e = leer(n, "docs/data/estado-fuentes.json")
    e["fuentes"]["senado_actas"].update(estado="ok", revisado_el="2026-09-30", datos_al="2026-07-22")
    escribir(n, "docs/data/estado-fuentes.json", e)
    ok, g = correr(base, n)
    assert ok, g.fallos


def test_x1_link_must_be_http_even_on_an_official_host(par):
    base, n = par
    res = leer(n, "docs/data/resumenes.json")
    res["sin_resumen"]["senado-00636-2025"] = {"intentos": 3, "fuente_url": "javascript://www.senadord.gob.do/%0aalert(1)"}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G4") and "http" in f for f in g.fallos), g.fallos


@pytest.mark.parametrize("texto", ["La ley está en vigencia desde enero.", "El casco es obligatorio en la moto.",
                                   "El Congreso convirtió el proyecto de cuidados en ley.",
                                   "La regla ya se aplica en todo el país.", "El sistema ya funciona.",
                                   "El fondo ya opera en tres provincias."])
def test_a_more_ways_of_calling_a_bill_law_are_blocked(par, texto):
    from comun import PARECE_LEY
    assert PARECE_LEY.search(texto)
    base, n = par
    _con_resumen(n, titulo_facil=texto)
    ok, g = correr(base, n)
    assert not ok and any(f.startswith("G8") and "presenta como ley" in f for f in g.fallos), g.fallos
