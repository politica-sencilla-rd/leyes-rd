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
def _con_resumen(n, fuente=FUENTE, **k):
    sha = _texto(n, fuente)
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"]["x"] = _resumen(sha, **k)
    escribir(n, "docs/data/resumenes.json", res)


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
    m["auto"] = {"valor_num": 5.13, "anterior_num": 3.71, "valor_texto": "5.13%", "periodo": "agosto 2026",
                 "periodo_iso": "2026-08", "url": rec[0]["url"], "fuente": "BCRD", "texto": "t", "comparacion": "c"}
    escribir(n, "docs/data/finanzas.json", f)
    ok, g = correr(base, n, rec)
    assert ok, g.fallos                                   # the real August number publishes
    m["auto"]["valor_num"] = 28.0                          # in range, absurd jump
    escribir(n, "docs/data/finanzas.json", f)
    ok, g = correr(base, n, rec)
    assert not ok and any("G3" in x and "inflacion" in x for x in g.fallos)
    m["auto"]["valor_num"] = 5.13
    s = next(m for m in f["metricas"] if m["id"] == "salario")
    s["auto"] = {"valor_num": 3.0, "anterior_num": 2.9, "var_pct": 3.45, "valor_texto": "RD$3.00", "periodo": "junio 2026",
                 "periodo_iso": "2026-06", "url": rec[0]["url"], "fuente": "TSS", "texto": "t", "comparacion": "c"}
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
    res["resumenes"]["x"] = {k: v for k, v in res["resumenes"]["x"].items() if v is not None}
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
        res["resumenes"]["x"] = {k: v for k, v in res["resumenes"]["x"].items() if v is not None}
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
    res["resumenes"]["x"] = {k: v for k, v in res["resumenes"]["x"].items() if v is not None}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok
    assert any("te_afecta no se pide" in f for f in g.fallos), g.fallos
    assert any("x.te_afecta: el número 999" in f for f in g.fallos)
    # 4 prose fields but 1/1 checks
    _con_resumen(n, tipo="proyecto", checks_pasados=1, checks_total=1, titulo_facil=None,
                 que_es="Crea un sistema de cuidados.", por_que="Para cuidar a niños.",
                 te_afecta="La propuesta busca cuidar a niños.", en_30_segundos="Un sistema de cuidados.")
    res = leer(n, "docs/data/resumenes.json")
    res["resumenes"]["x"] = {k: v for k, v in res["resumenes"]["x"].items() if v is not None}
    escribir(n, "docs/data/resumenes.json", res)
    ok, g = correr(base, n)
    assert not ok and any("1 revisiones para 4 campos" in f for f in g.fallos), g.fallos
    res["resumenes"]["x"].update(checks_pasados=25, checks_total=25)
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
    actas = sorted(s["acta"] for s in leer(n, SES)["sesiones"])[-2:]
    ley = leer(n, "docs/data/vigencia.json")["leyes"][0]["numero"]
    _, fr = N.frases_de({"senado_actas": {"nuevas": actas}, "vigencia_consultoria": {"nuevas": [ley]},
                         "leyes_sil": {"actualizadas": ["1"]}, "dinero": {"cambiados": ["inflacion (agosto 2026)"]},
                         "resumenes_ia": {"verificados": 2}}, {})
    _novedad(n, " ".join(fr))
    ok, g = correr(base, n)
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
