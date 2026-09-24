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
