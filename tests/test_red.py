import pytest

from conftest import FIX
from red import Cliente, FalloFuente, Respuesta, _valida, recibo_ok


def test_github_models_200_ok_is_not_json():
    # models.github.ai answers HTTP 200 text/plain "OK" since it was retired (tested 2026-09-24)
    r = Respuesta("https://models.github.ai/x", 200, "text/plain", (FIX / "ia" / "github_models_200_ok.txt").read_bytes())
    with pytest.raises(FalloFuente):
        _valida("json", r)


def test_json_served_as_html_is_accepted_when_body_is_json():
    # the Senate WPFD listing answers text/html but the body is JSON
    r = Respuesta("u", 200, "text/html", (FIX / "senado" / "listado_p1.json").read_bytes())
    _valida("json", r)


def test_pdf_and_xlsx_magic():
    _valida("pdf", Respuesta("u", 200, "application/pdf", (FIX / "senado" / "acta_0127.pdf").read_bytes()))
    _valida("xlsx", Respuesta("u", 200, "x", (FIX / "dinero" / "deuda_historico.xlsx").read_bytes()))
    with pytest.raises(FalloFuente):
        _valida("pdf", Respuesta("u", 200, "text/html", b"<html>login</html>"))


def test_spacing_per_host_is_enforced():
    reloj = [0.0]
    dormido = []

    def dormir(s):
        dormido.append(s)
        reloj[0] += s
    c = Cliente(espera={"a.gob.do": 120}, dormir=dormir, ahora=lambda: reloj[0])
    c._esperar_turno("a.gob.do")
    reloj[0] += 5
    c._esperar_turno("a.gob.do")
    assert dormido == [115]


def test_recibo_ok():
    rec = [{"url": "u", "status": 200, "error": None}, {"url": "v", "status": None, "error": "HTTP 404"}]
    assert recibo_ok(rec, "u") and not recibo_ok(rec, "v") and not recibo_ok(rec, "w")
