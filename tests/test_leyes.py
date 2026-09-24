"""Bills (SIL) and new laws (Consultoría), on saved real responses."""
import gzip
import json

import pytest

import dinero as D
import leyes as L
import senado_actas as S
import vigencia as V
from comun import texto_pdf
from conftest import FIX, cargar

CONF_SIL = json.loads((FIX.parents[1] / "config" / "sil.json").read_text())


def _data():
    return {"sectores": [{"id": "justicia", "nombre": "J", "leyes": [
        {"titulo": "Hecha a mano", "estado": "votando", "que_es": "x", "por_que": "y", "te_afecta": "z", "votos": []}]}]}


def test_sil_first_run_is_baseline_only():
    filas = cargar("leyes/getIniciativas_p1.json")["results"]
    data, snap, rep = L.aplicar(filas, None, _data(), CONF_SIL, "2026-09-24", 40)
    assert rep["linea_base"] and not rep["nuevas"] and len(snap) == len(filas)


def test_sil_change_detection_adds_passed_bills_and_updates_tracked():
    filas = [dict(r) for r in cargar("leyes/getIniciativas_p1.json")["results"]]
    snap = {str(r["id"]): [r["estado"], r["numPromulgacion"]] for r in filas}
    filas[0].update(tipo="Proyecto de Ley", estado="Aprobado en 2da. lectura", materia="JUSTICIA")
    filas[1].update(tipo="Proyecto de Ley", estado="Enviado a Comisión")  # changed but did not pass: not added
    data, nsnap, rep = L.aplicar(filas, snap, _data(), CONF_SIL, "2026-09-24", 40)
    assert [e["sil_id"] for e in rep["nuevas"]] == [filas[0]["id"]]
    nueva = data["sectores"][0]["leyes"][0]
    assert nueva["auto"] and nueva["estado"] == "votando" and "que_es" not in nueva
    assert data["sectores"][0]["leyes"][1]["titulo"] == "Hecha a mano"  # hand entry untouched
    # next week it is promulgated -> tracked entry updates
    snap2 = nsnap
    filas[0]["estado"] = "Promulgado"
    data2, _, rep2 = L.aplicar(filas, snap2, data, CONF_SIL, "2026-10-01", 40)
    assert rep2["actualizadas"] == [filas[0]["numero"]] and data2["sectores"][0]["leyes"][0]["estado"] == "aprobada"


def test_sil_cap_defers_the_rest():
    filas = [dict(r, tipo="Proyecto de Ley", estado="Promulgado") for r in cargar("leyes/getIniciativas_p1.json")["results"]]
    snap = {str(r["id"]): ["Depositado", None] for r in filas}
    data, nsnap, rep = L.aplicar(filas, snap, _data(), CONF_SIL, "2026-09-24", 3)
    assert len(rep["nuevas"]) == 3 and rep["diferidas"] == len(filas) - 3
    assert sum(1 for v in nsnap.values() if v[0] == "Depositado") == len(filas) - 3


def test_estado_mapping():
    assert L.mapear_estado("Perimido", CONF_SIL) == "vencida"
    assert L.mapear_estado("Retirado", CONF_SIL) == "retirada"
    assert L.mapear_estado("Promulgado", CONF_SIL) == "aprobada"
    assert L.mapear_estado("Con informe de comisión", CONF_SIL) == "votando"


GACETA = gzip.decompress((FIX / "vigencia" / "gaceta_11254.txt.gz").read_bytes()).decode()


def test_law_slice_and_concomitant_rule():
    t = V.cortar_ley(GACETA, "44-26")
    art, cl = V.clausula(t)
    assert art == "30" and "concomitantemente" in cl and "Dada en" not in cl
    f, regla, _ = V.calcular(cl, "2026-07-27", "2026-07-29", {"74-25": {"vigencia_fecha": "2026-08-03"}})
    assert (f, regla) == ("2026-08-03", "concomitante")
    # if we don't know law 74-25's date, the robot must not guess
    assert V.calcular(cl, "2026-07-27", "2026-07-29", {})[0] is None


def test_default_rule_and_plazos():
    assert V.calcular(None, "2026-07-27", "2026-07-29", {})[:2] == ("2026-07-30", "regla_por_defecto")
    std = ("Artículo 7.- Entrada en vigencia. Esta ley entrará en vigencia después de su promulgación y publicación, "
           "según lo establecido en la Constitución de la República.")
    assert V.calcular(std, "2026-07-22", "2026-07-25", {})[:2] == ("2026-07-26", "publicacion")
    assert V.calcular("Artículo 248.- Entrada en vigencia. Entrará en vigencia ciento ochenta días después de su promulgación.",
                      "2025-08-11", "2025-08-12", {})[0] == "2026-02-07"  # matches the hand-checked Ley 47-25
    assert V.calcular("Artículo 103.- Entrada en vigencia. Entrará en vigencia seis meses después de su promulgación.",
                      "2025-08-08", "2025-08-09", {})[0] == "2026-02-08"  # matches Ley 84-25
    raro = "Artículo 9.- Entrada en vigencia. Entrará en vigencia el 1 de enero de 2027, salvo el artículo 3."
    assert V.calcular(raro, "2026-07-22", "2026-07-25", {})[:2] == (None, "ver_articulo")


def test_consultoria_canonical_skips_reprints():
    filas = cargar("vigencia/consultas_search_2026.json")
    canon = V.canonicas(filas + [dict(filas[0], Gaceta="Edición especial", FechaPromulgacion="2000-01-01")])
    assert canon[filas[0]["Numero"]]["FechaPromulgacion"] != "2000-01-01"
    assert V.titulo_legible("QUE MODIFICA LA LEY NÚM.99-25").startswith("Ley que modifica")


