"""Money parsers, on the real official Excel files."""
import gzip
import json

import pytest

import dinero as D
import leyes as L
import senado_actas as S
import vigencia as V
from comun import texto_pdf
from conftest import FIX, cargar

def test_money_parsers_on_real_files():
    ipc = D.parse_ipc((FIX / "dinero" / "ipc_base_2019-2020.xls").read_bytes())
    assert (ipc["valor_num"], ipc["anterior_num"], ipc["periodo_iso"]) == (5.13, 3.71, "2026-08")
    enc = D.parse_encft((FIX / "dinero" / "00_Indicadores.xlsx").read_bytes())
    assert (enc["valor_num"], enc["anterior_num"], enc["periodo"]) == (5.31, 4.95, "abril-junio 2026")
    pib = D.parse_pib((FIX / "dinero" / "pib_origen_2018.xlsx").read_bytes())
    assert pib["valor_num"] == 2.12 and pib["periodo_iso"] == "2025-12" and pib["parcial_periodo"] == "enero-marzo 2026"
    deu = D.parse_deuda((FIX / "dinero" / "deuda_historico.xlsx").read_bytes())
    assert (deu["valor_num"], deu["anterior_num"], deu["usd_millones"]) == (48.14, 46.35, 61549.9)
    tss = D.parse_tss((FIX / "dinero" / "tss_boletin_jun2026.xlsx").read_bytes(), 2026)
    assert (tss["valor_num"], tss["anterior_num"], tss["periodo_iso"]) == (39844.66, 37524.07, "2026-06")


def test_money_templates_have_no_opinion_and_compute_per_person():
    t = D.textos("deuda", {"valor_num": 48.14, "anterior_num": 46.35, "usd_millones": 61549.9, "periodo": "cierre de 2025",
                           "anterior_periodo": "cierre de 2024"}, 10773983)
    assert "US$5,713" in t["texto"] and t["comparacion"].endswith("Subió.")
    t2 = D.textos("inflacion", {"valor_num": 5.13, "anterior_num": 3.71, "periodo": "agosto 2026",
                                "anterior_periodo": "agosto 2025"}, None)
    assert t2["valor_texto"] == "5.13%" and "RD$105" in t2["texto"]


# ---------------------------------------------------------------- review round 1 regressions (B2)
from comun import problema_metrica, valor_previo  # noqa: E402


def _tarjetas():
    return {m["id"]: m for m in json.loads((FIX.parents[1] / "docs/data/finanzas.json").read_text())["metricas"]}


# Hand-written card values before the robot's first update (commit 4f6a9a3).
# Frozen here because the live cards change with every robot run.
PREVIOS = {"inflacion": 5.35, "desempleo": 5.0, "crecimiento": 2.1, "deuda": 47.9, "salario": 37572.82}


def test_b2_real_numbers_pass_against_the_cards_on_main():
    t = _tarjetas()
    assert all(valor_previo(t[m]) for m in PREVIOS)
    reales = {"inflacion": D.parse_ipc((FIX / "dinero" / "ipc_base_2019-2020.xls").read_bytes()),
              "desempleo": D.parse_encft((FIX / "dinero" / "00_Indicadores.xlsx").read_bytes()),
              "crecimiento": D.parse_pib((FIX / "dinero" / "pib_origen_2018.xlsx").read_bytes()),
              "deuda": D.parse_deuda((FIX / "dinero" / "deuda_historico.xlsx").read_bytes()),
              "salario": D.parse_tss((FIX / "dinero" / "tss_boletin_jun2026.xlsx").read_bytes(), 2026)}
    for mid, d in reales.items():
        assert problema_metrica(mid, d, PREVIOS[mid]) is None, mid


@pytest.mark.parametrize("mid,d,previo", [
    ("inflacion", {"valor_num": 28.0, "anterior_num": 3.7}, 5.13),     # in range, absurd jump
    ("desempleo", {"valor_num": 9.5, "anterior_num": 5.0}, 5.31),
    ("crecimiento", {"valor_num": -9.0}, 2.12),
    ("deuda", {"valor_num": 70.0, "anterior_num": 46.3}, 48.14),
    ("salario", {"valor_num": 3.0, "anterior_num": 2.9, "var_pct": 3.4}, None),   # RD$3 salary, no history
    ("salario", {"valor_num": 52000.0, "anterior_num": 37524.07, "var_pct": 6.18}, 39844.66),  # +30%
    ("salario", {"valor_num": 39844.66, "anterior_num": 37524.07, "var_pct": 0.06}, 39844.66),  # shifted % column
])
def test_b2_implausible_money_is_refused(mid, d, previo):
    assert problema_metrica(mid, d, previo)


def test_b2_shifted_ipc_column_is_refused():
    """One inserted column in the BCRD IPC sheet used to give 2.6% (year-to-date) as the 12-month rate."""
    import io
    pd = pytest.importorskip("pandas")
    df = pd.read_excel(FIX / "dinero" / "ipc_base_2019-2020.xls", header=None)
    df.insert(3, "nueva", None)
    df.columns = range(df.shape[1])
    b = io.BytesIO()
    df.to_excel(b, header=False, index=False)
    with pytest.raises(ValueError):
        D.parse_ipc(b.getvalue())
