"""Novedades/RSS, 'Datos al', freshness issues and the issue helper."""
import json
from datetime import date

import datos_al as DA
import frescura as F
import issues as I
import novedades as N
from conftest import ROOT


def test_rss_is_rebuilt_from_json():
    nov = json.loads((ROOT / "docs/data/novedades.json").read_text())
    assert N.construir_xml(nov) == (ROOT / "docs/novedades.xml").read_text()


def test_one_novedad_from_templates():
    fam, fr = N.frases_de({"senado_actas": {"nuevas": ["0107", "0127", "0110"], "corregidas": ["0104"]},
                           "dinero": {"cambiados": ["inflacion (agosto 2026)"]}}, {})
    assert fam == "senado"
    assert fr[0] == "Agregamos 3 sesiones del Senado (actas 0107 a 0127), leídas de las actas oficiales."
    assert "inflación (agosto 2026)" in fr[-1]
    assert N.frases_de({}, {}) == ("", [])
    # same Cámara date as last week -> nothing to announce
    assert N.frases_de({"camara_diputados": {"datos_al": "2026-09-09"}}, {"camara_diputados": {"datos_al": "2026-09-09"}})[1] == []


def test_datos_al_merge_and_failure_count():
    conf = json.loads((ROOT / "config/fuentes.json").read_text())
    viejo = {"senado_actas": {"fallos_seguidos": 1, "revisado_el": "2026-09-15", "estado": "roto"}}
    calc = {"senado_actas": {"datos_al": "2026-07-22", "ultimo_leido": "Acta 0127"}}
    out = DA.actualizar(viejo, calc, {"senado_actas": {"estado": "sin_respuesta"}}, conf, "2026-09-29")
    assert out["senado_actas"]["fallos_seguidos"] == 2 and out["senado_actas"]["revisado_el"] == "2026-09-29"
    assert out["senado_actas"]["datos_al"] == "2026-07-22"
    ok = DA.actualizar(out, calc, {"senado_actas": {"estado": "ok"}}, conf, "2026-10-06")
    assert ok["senado_actas"]["fallos_seguidos"] == 0
    # a source not in this run keeps its old check date
    assert ok["camara_diputados"]["estado"] == "sin_revisar"


def test_freshness_rules():
    conf = json.loads((ROOT / "config/fuentes.json").read_text())
    ef = {"senado_actas": {"subido_por_la_fuente": "2026-05-01", "revisado_el": "2026-09-01", "fallos_seguidos": 0},
          "dinero_inflacion": {"datos_al": "2026-08", "revisado_el": "2026-09-20", "fallos_seguidos": 2}}
    abrir, claves = F.revisar_estado(ef, conf, date(2026, 9, 24))
    assert "quieta-senado_actas" in abrir          # 146 days > 90
    assert "rota-senado_actas" in abrir            # not checked for 23 days > 10
    assert "rota-dinero_inflacion" in abrir        # 2 failures in a row
    assert "quieta-dinero_inflacion" not in abrir  # August data in late September is normal
    assert "quieta-camara_diputados" in claves and "quieta-camara_diputados" not in abrir


def test_issues_dry_mode_and_table(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert I.abrir("k", "t", "c", "datos-viejos") == "seco"
    assert I.cerrar("k", "datos-viejos") == "seco"
    t = I.tabla_ia([{"id": "a", "campo": "que_es", "pregunta": "Q2 x|y", "intentos": 1, "fuente_url": "u"}])
    assert "| a | que_es | Q2 x/y | 1 | u |" in t


def test_bot_blocks_are_not_broken_links():
    assert F.no_comprobable("HTTP 403")
    assert F.no_comprobable("URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                            "unable to get local issuer certificate (_ssl.c:1000)>")
    assert not F.no_comprobable("HTTP 404")
    assert not F.no_comprobable("URLError: certificate has expired")


def test_r3_issues_are_dry_unless_publishing_is_on(monkeypatch, capsys):
    llamadas = []
    monkeypatch.setattr(I, "_gh", lambda args, entrada=None: llamadas.append(args) or "[]")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.delenv("PSRD_ISSUES_SECO", raising=False)
    for valor in (None, "no", "SI "):
        if valor is None:
            monkeypatch.delenv("PSRD_AUTOPUBLICAR", raising=False)
        else:
            monkeypatch.setenv("PSRD_AUTOPUBLICAR", valor)
        assert I.abrir("k", "t", "c", "datos-viejos") == "seco"
        assert I.cerrar("k", "datos-viejos") == "seco"
    assert llamadas == [] and "[seco]" in capsys.readouterr().out
    monkeypatch.setenv("PSRD_AUTOPUBLICAR", "si")
    assert I.abrir("k", "t", "c", "datos-viejos") == "creado" and llamadas


def test_r3_a_dead_source_opens_one_issue(monkeypatch, tmp_path):
    """consultoria.gov.do answers 403 to GitHub runners: the run must open (or update) ONE issue for it."""
    abiertos = []
    monkeypatch.setattr(I, "abrir", lambda clave, titulo, cuerpo, etiqueta: abiertos.append((clave, etiqueta, cuerpo)) or "ok")
    monkeypatch.setattr(I, "cerrar", lambda clave, etiqueta, comentario="": "cerrado")
    (tmp_path / ".psrd-run").mkdir()
    (tmp_path / ".psrd-run" / "resumen.json").write_text(json.dumps({"fuentes": {
        "vigencia_consultoria": {"estado": "sin_respuesta", "error": "HTTP 403"},
        "leyes_sil": {"estado": "ok"}}}))
    hechos = I.issues_de_run(tmp_path, "leyes")
    assert [a[0] for a in abiertos] == ["fuente-vigencia_consultoria"] and "403" in abiertos[0][2]
    assert "cerrado" in hechos  # the SIL, which answered, closes its own issue


def test_r3_leyes_workflow_publishes_the_source_that_answered():
    # plain text on purpose: PyYAML is not installed on the runner
    wf = (ROOT / ".github/workflows/leyes.yml").read_text()
    pasos = {b.split("\n", 1)[0].strip().strip('"'): b for b in wf.split("      - name: ")[1:]}
    leer = next(b for n, b in pasos.items() if n.startswith("Leer las fuentes"))
    assert "continue-on-error" not in leer and "exit 0" in leer
    publicar = next(b for n, b in pasos.items() if n.startswith("Publicar"))
    assert "steps.fuente.outputs.leyes == '0' || steps.fuente.outputs.vigencia == '0'" in publicar  # one source is enough
    assert "--fallo" not in publicar
    rojo = next(b for n, b in pasos.items() if n.startswith("Dejar el job en rojo"))
    assert "always()" in rojo and "exit 1" in rojo                                                   # ...and the job goes red
    assert "PSRD_AUTOPUBLICAR: ${{ vars.PSRD_AUTOPUBLICAR }}" in (ROOT / ".github/workflows/frescura.yml").read_text()


def test_r3_browser_scripts_wait_for_the_full_load():
    import re
    for js in sorted((ROOT / "scripts").glob("*.js")):
        for valor in re.findall(r"waitUntil:\s*\"(\w+)\"", js.read_text()):
            assert valor == "load", js.name
