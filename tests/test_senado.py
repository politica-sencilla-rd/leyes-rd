"""Senate actas parser, on saved real actas (PDF and text)."""
import gzip
import json

import pytest

import dinero as D
import leyes as L
import senado_actas as S
import vigencia as V
from comun import texto_pdf
from conftest import FIX, cargar

ESPERADO = cargar("senado/esperado.json")

@pytest.mark.parametrize("acta", ["0104", "0105", "0112", "0113", "0123"])
def test_acta_golden(acta):
    txt = gzip.decompress((FIX / "senado" / f"acta_{acta}.pymupdf.txt.gz").read_bytes()).decode()
    ses = S.a_sesion(S.parse(txt), f"https://example/{acta}")
    assert ses == ESPERADO[acta]


@pytest.mark.parametrize("acta", ["0122", "0127"])
def test_acta_pdf_end_to_end(acta):
    """Real PDF -> text (PyMuPDF, pinned, on every machine) -> parse. Must equal the golden
    output, so a text-tool change can't silently change published numbers."""
    ses = S.a_sesion(S.parse(texto_pdf((FIX / "senado" / f"acta_{acta}.pdf").read_bytes())), f"https://example/{acta}")
    assert ses == ESPERADO[acta]


def test_known_source_errors_become_public_notes():
    assert "22 a favor con 19 presentes" in ESPERADO["0112"]["notas_fuente"][0]
    assert len(ESPERADO["0123"]["notas_fuente"]) == 2
    # annulled vote 015 in acta 0105 and headings without a period are accounted for
    assert len(ESPERADO["0105"]["votaciones"]) == 23


def test_unaccounted_heading_blocks_the_whole_acta():
    base = gzip.decompress((FIX / "senado" / "acta_0112.pymupdf.txt.gz").read_bytes()).decode()
    roto = base + "\nVotación electrónica 099 texto que el lector no entiende.\n"
    ses = S.a_sesion(S.parse(roto), "u")
    assert ses["estado"] == "no_procesada" and "099" in ses["motivo"]


def test_no_named_votes_in_parser_output():
    for ses in ESPERADO.values():
        for v in ses.get("votaciones", []):
            assert set(v) <= {"iniciativa", "titulo", "a_favor", "presentes", "resultado", "votacion_num", "fuente"}


def test_listing_parse_and_merge_keeps_legacy_titles():
    j = cargar("senado/listado_p1.json")
    actas = [f["post_title"] for f in j["files"]]
    assert "ACTA NÚM. 0127 DE FECHA 22 DE JULIO 2026" in actas
    viejas = [{"acta": "0104", "votaciones": [{"iniciativa": "00636-2025", "titulo_facil": "Legado"}]}]
    nueva = {"acta": "0104", "votaciones": [{"iniciativa": "00636-2025"}, {"iniciativa": "01111-2026"}]}
    out = S.fusionar(viejas, [nueva], {})
    assert out[0]["votaciones"][0]["titulo_facil"] == "Legado" and "titulo_facil" not in out[0]["votaciones"][1]


def test_item_level_sanity():
    ses = {"asistencia": {"presentes": 30, "ausentes": 5}, "votaciones": []}
    assert S.sesion_valida(ses)


