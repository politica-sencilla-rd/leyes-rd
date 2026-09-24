"""AI writer + checker: fail closed, code checks, canary, atomic questions."""
import json

import pytest

import escribir as E
from comun import Arbol, sha256_texto
from conftest import FIX

CONF = json.loads((FIX.parents[1] / "config" / "ia.json").read_text())


@pytest.fixture
def listas(arbol_copia):
    return E.cargar_listas(Arbol("t", base=arbol_copia))


# ---------------------------------------------------------------- fail-closed parsing
def test_real_gemma_answer_skips_thoughts():
    raw = (FIX / "ia" / "gemma_respuesta_con_pensamiento.json").read_text()
    assert E.interpretar_respuesta("gemma-4-26b-a4b-it", "application/json; charset=UTF-8", raw) == "SI"


def test_github_models_200_ok_is_rejected():
    with pytest.raises(E.Rechazo):
        E.interpretar_respuesta("x", "text/plain", (FIX / "ia" / "github_models_200_ok.txt").read_text())


@pytest.mark.parametrize("cuerpo", [
    {"candidates": [{"finishReason": "SAFETY", "content": {"parts": [{"text": "x"}]}}]},
    {"candidates": [], "promptFeedback": {"blockReason": "OTHER"}},
    {"candidates": [{"finishReason": "STOP", "content": {"parts": []}}]},
    {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "SI"}]}}]},
])
def test_blocked_or_truncated_answers_are_rejected(cuerpo):
    with pytest.raises(E.Rechazo):
        E.interpretar_respuesta("m", "application/json", json.dumps(cuerpo))


def test_checker_must_say_exactly_si_or_no():
    class Charlatan:
        def generar(self, *a, **k):
            return "Creo que sí, más o menos"
    with pytest.raises(E.Rechazo):
        E.pregunta(Charlatan(), "r", "¿?", "frase", "fuente")


# ---------------------------------------------------------------- code checks
FUENTE = json.loads((FIX / "ia_canario.json").read_text())["fuente"]
ITEM = {"tipo": "ley", "estado_ley": "votando"}


def f(texto, cita="para que fuese apoderada la Comisión Permanente de Cultura", campo="que_es"):
    return [{"campo": campo, "texto": texto, "cita": cita}]


def test_code_checks_catch_each_rule(listas):
    ok = f("La Cámara pasó la iniciativa 03737-2024-2028-CD a la Comisión Permanente de Cultura.")
    assert E.chequeos_codigo(ok, FUENTE, ITEM, CONF, *listas) == []
    casos = {
        "(1)": f("La Cámara votó.", cita="una cita inventada"),
        "(2) el número": f("La Cámara votó 99 veces."),
        "(2) número escrito": f("La Cámara movió dos iniciativas."),
        "(3) palabra": f("Fue una decisión excelente de la Cámara."),
        "(3) nombra": f("Jorge Frías votó en la Cámara."),
        "(4) presenta": f("Ya es ley la iniciativa de cultura."),
        "(5) frase": f(" ".join(["palabra"] * 21)),
    }
    for regla, frases in casos.items():
        errs = E.chequeos_codigo(frases, FUENTE, ITEM, CONF, *listas)
        assert any(e.startswith(regla) for e in errs), (regla, errs)


def test_te_afecta_must_be_a_proposal_when_not_passed(listas):
    item = {"tipo": "proyecto", "estado_ley": "votando"}
    frases = [{"campo": c, "texto": "La Cámara pasó la iniciativa a la Comisión Permanente de Cultura.",
               "cita": "para que fuese apoderada la Comisión Permanente de Cultura"}
              for c in ("que_es", "por_que", "te_afecta", "en_30_segundos")]
    errs = E.chequeos_codigo(frases, FUENTE, item, CONF, *listas)
    assert any(e.startswith("(4)") for e in errs)
    frases[2]["texto"] = "La propuesta busca pasar la iniciativa a la Comisión Permanente de Cultura."
    assert E.chequeos_codigo(frases, FUENTE, item, CONF, *listas) == []


# ---------------------------------------------------------------- canary + independence
def test_canary_passes_with_stub(listas):
    ok, log = E.canario(E.Stub(), CONF, listas, ["w"], ["c"])
    assert ok, log


def test_degraded_checker_fails_the_canary(listas):
    class SiempreSi:
        def generar(self, *a, **k):
            return "SI"
    ok, log = E.canario(SiempreSi(), CONF, listas, ["w"], ["c"])
    assert not ok


def test_checker_cannot_be_the_writer(listas):
    r = E.procesar({"tipo": "ley", "estado_ley": "votando", "fuente_url": "u", "fuente_sha256": "s"}, FUENTE,
                   E.Stub(), CONF, listas, ["same"], ["same"])
    assert r["estado"] == "rechazado"


def test_rewrite_then_publish(listas):
    """First draft invents a fact (checker says NO), the rewrite passes."""
    class Escritor(E.Stub):
        n = 0

        def generar(self, modelo, prompt, system=None, schema=None):
            if schema:
                Escritor.n += 1
                texto = ("La Cámara aprobó una ley nueva para los bomberos." if Escritor.n == 1 else
                         "La Cámara pasó la iniciativa 03737-2024-2028-CD a la Comisión Permanente de Cultura.")
                return json.dumps({"frases": [{"campo": "que_es", "texto": texto,
                                               "cita": "para que fuese apoderada la Comisión Permanente de Cultura"}]})
            return super().generar(modelo, prompt, system, schema)
    item = {"tipo": "ley", "estado_ley": "votando", "fuente_url": "u", "fuente_sha256": "s", "id": "x"}
    r = E.procesar(item, FUENTE, Escritor(), CONF, listas, ["w"], ["c"])
    assert r["estado"] == "verificado" and Escritor.n == 2 and r["checks_pasados"] == r["checks_total"]


def test_any_exception_is_a_rejection(listas):
    class Roto:
        def generar(self, *a, **k):
            raise ConnectionResetError("boom")
    r = E.procesar({"tipo": "ley", "estado_ley": "votando", "fuente_url": "u", "fuente_sha256": "s"}, FUENTE,
                   Roto(), CONF, listas, ["w"], ["c"])
    assert r["estado"] == "rechazado"


def test_no_key_means_nothing_published(arbol_copia, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(E, "Arbol", lambda nombre, dry_run=False: Arbol(nombre, base=arbol_copia))
    antes = (arbol_copia / "docs/data/resumenes.json").read_text()
    assert E.main([]) == 1
    assert (arbol_copia / "docs/data/resumenes.json").read_text() == antes


def test_stub_run_writes_verified_records_only(arbol_copia, monkeypatch):
    monkeypatch.setattr(E, "Arbol", lambda nombre, dry_run=False: Arbol(nombre, base=arbol_copia))
    textos = {"senado-01531-2026": "Proyecto de ley que autoriza el pago a contratistas del Estado y crea una comisión "
                                    "para la revisión de reclamaciones derivadas de obras ejecutadas con o sin contrato formal"}
    items = []
    for k, t in textos.items():
        sha = sha256_texto(t)
        (arbol_copia / "pipeline-state" / "textos" / f"{sha}.txt").write_text(t)
        items.append({"id": k, "tipo": "titulo_voto", "estado_ley": "votando", "fuente_url": "https://www.senadord.gob.do/x",
                      "fuente_sha256": sha, "intentos": 0})
    (arbol_copia / "pipeline-state" / "cola_resumenes.json").write_text(json.dumps({"items": items}))
    assert E.main(["--stub"]) == 0
    res = json.loads((arbol_copia / "docs/data/resumenes.json").read_text())["resumenes"]
    assert res["senado-01531-2026"]["estado"] == "verificado"
    assert res["senado-01531-2026"]["checks_pasados"] == res["senado-01531-2026"]["checks_total"]


def test_model_chain_falls_back_then_fails_closed():
    class Medio:
        llamados = []

        def generar(self, modelo, *a, **k):
            Medio.llamados.append(modelo)
            if modelo == "a":
                raise E.Rechazo("429")
            return "SI"
    c = E.Cadena(Medio(), ["a", "b"])
    assert c.generar("", "p") == "SI" and c.usado == "b"
    assert c.generar("", "p") == "SI" and Medio.llamados == ["a", "b", "b"]

    class Nada:
        def generar(self, *a, **k):
            raise E.Rechazo("caido")
    with pytest.raises(E.Rechazo):
        E.Cadena(Nada(), ["a", "b"]).generar("", "p")
