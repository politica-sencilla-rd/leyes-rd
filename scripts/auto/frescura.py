#!/usr/bin/env python3
"""Weekly freshness check. Never commits; only opens/updates/closes issues
(one per key, label "datos-viejos"), via issues.py.

  1. Source quiet    : the source itself published nothing new for longer than
                       config/fuentes.json max_dias_sin_novedad.
  2. We are behind   : the Senate list has an acta newer than ours for > 14 days
                       (one listing request; crawl-delay respected).
  3. Source broken   : fallos_seguidos >= 2, or revisado_el older than
                       max_dias_sin_revisar (a workflow died or was disabled).
  4. Links           : every link in docs/data/*.json and docs/*.html answers 200
                       AND is not a "Página no encontrada" page served with 200
                       (the soft-404 the 2026-09-23 critique found on
                       consultoria.gov.do/consulta; lychee cannot see those, so
                       this reuses the pipeline's own fetch helper instead).
                       senadord.gob.do: only 5 links per week, 120 s apart.
  5. Live site       : each live docs/data/*.json must equal main (a failed Pages
                       deploy would otherwise go unnoticed). Skipped for 1 hour
                       after a data commit (Pages cache).

Usage: python3 scripts/auto/frescura.py [--dir .] [--sin-red] [--sin-enlaces]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import ROOT, hoy_et  # noqa: E402
import issues  # noqa: E402
from red import Cliente, FalloFuente  # noqa: E402

SITIO = "https://politica-sencilla-rd.github.io/leyes-rd/"
LISTADO_SENADO = ("https://www.senadord.gob.do/wp-admin/admin-ajax.php?juwpfisadmin=false&action=wpfd"
                  "&task=files.display&view=files&id=1387&rootcat=1387&page=1")
ETQ = "datos-viejos"
PAGINA_404 = re.compile(r"P[áa]gina no encontrada|Page not found|404 Not Found|Error 404", re.I)


def dias(desde: str | None, hoy: date) -> int | None:
    if not desde:
        return None
    s = desde if len(desde) > 7 else desde + "-28"  # "2026-08" -> end of that month, roughly
    return (hoy - date.fromisoformat(s[:10])).days


def revisar_estado(ef: dict, conf: dict, hoy: date) -> tuple[dict, set]:
    """Pure (unit-tested). -> ({clave: (titulo, cuerpo)}, all keys checked)."""
    abrir, claves = {}, set()
    for k, c in conf["fuentes"].items():
        e = ef.get(k) or {}
        q, r = f"quieta-{k}", f"rota-{k}"
        claves |= {q, r}
        ref = e.get("subido_por_la_fuente") or e.get("datos_al")
        d = dias(ref, hoy)
        if c.get("max_dias_sin_novedad") and d is not None and d > c["max_dias_sin_novedad"]:
            abrir[q] = (f"[auto] Fuente callada: {c['nombre']}",
                        f"La fuente oficial no ha publicado nada nuevo en {d} días (último: {ref}; límite "
                        f"{c['max_dias_sin_novedad']}). No es un error nuestro: el sitio muestra la fecha real "
                        f"('Datos al'). Fuente: {c['url_fuente']}")
        rev = dias(e.get("revisado_el"), hoy)
        if e.get("fallos_seguidos", 0) >= 2:
            abrir[r] = (f"[auto] Fuente rota: {c['nombre']}",
                        f"El robot falló {e['fallos_seguidos']} veces seguidas al leer esta fuente (estado: "
                        f"{e.get('estado')}). El sitio conserva el último dato bueno. Fuente: {c['url_fuente']}")
        elif e.get("revisado_el") and rev is not None and rev > c.get("max_dias_sin_revisar", 10):
            abrir[r] = (f"[auto] Robot parado: {c['nombre']}",
                        f"Nadie revisa esta fuente desde hace {rev} días (último: {e['revisado_el']}). "
                        f"Revisa que el workflow siga activo en la pestaña Actions.")
    return abrir, claves


def senado_atrasado(cli: Cliente, ef: dict, hoy: date) -> tuple[str, str] | None:
    j = cli.get(LISTADO_SENADO, "json").json()
    nuevas = []
    for f in j.get("files", []):
        m = re.search(r"ACTA\s+N[ÚU]M\.?\s*(\d{4})", f.get("post_title", ""), re.I)
        if m:
            d, mo, y = f["created"].split("-")
            nuevas.append((m.group(1), f"{y}-{mo}-{d}"))
    nuestra = re.search(r"(\d{4})", (ef.get("senado_actas") or {}).get("ultimo_leido", "") or "")
    if not nuestra:
        return None
    atras = [(a, s) for a, s in nuevas if a > nuestra.group(1) and (hoy - date.fromisoformat(s)).days > 14]
    if atras:
        return ("[auto] Vamos atrasados: actas del Senado",
                f"El Senado ya publicó {len(atras)} actas que no tenemos (la más vieja subida el "
                f"{min(s for _, s in atras)}). El robot del Senado debería haberlas leído: revisa su última corrida.")
    return None


def no_comprobable(error: str) -> bool:
    """A robot can't tell if these work for a person: 403/429 are bot blocks, and
    'unable to get local issuer certificate' is a server that omits its
    intermediate certificate (browsers fetch it, Python does not). Logged, no issue."""
    return bool(re.search(r"HTTP (403|429)\b|unable to get local issuer certificate", error))


def urls_de(d: Path) -> set[str]:
    urls = set()
    for f in list((d / "docs" / "data").glob("*.json")) + list((d / "docs").glob("*.html")):
        urls |= set(re.findall(r"https?://[^\s\"'<>)\\]+", f.read_text(encoding="utf-8")))
    return {u.rstrip(".,;") for u in urls}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT))
    ap.add_argument("--sin-red", action="store_true")
    ap.add_argument("--sin-enlaces", action="store_true")
    ap.add_argument("--muestra-senado", type=int, default=5)
    a = ap.parse_args(argv)
    d = Path(a.dir)
    hoy = hoy_et()
    conf = json.loads((d / "config" / "fuentes.json").read_text(encoding="utf-8"))
    ef = json.loads((d / "docs" / "data" / "estado-fuentes.json").read_text(encoding="utf-8"))["fuentes"]
    abrir, claves = revisar_estado(ef, conf, hoy)
    informe = []
    cli = Cliente(d / ".psrd-run" / "recibos-frescura.json", timeout=60, reintentos=2)
    if not a.sin_red:
        claves.add("atrasados-senado")
        try:
            r = senado_atrasado(cli, ef, hoy)
            if r:
                abrir["atrasados-senado"] = r
        except FalloFuente as e:
            informe.append(f"listado del Senado: {e}")
        # 4. Senate links sample (lychee skips senadord.gob.do because of its crawl-delay)
        claves.add("enlaces-senado")
        todas = sorted(u for u in urls_de(d) if "senadord.gob.do" in u)
        semana = hoy.isocalendar()[1]
        muestra = [todas[(semana * a.muestra_senado + i) % len(todas)] for i in range(min(a.muestra_senado, len(todas)))] if todas else []
        rotos = []
        for u in muestra:
            try:
                cli.get(u, "pdf" if "/Descargas/" in u else "html")
            except FalloFuente as e:
                rotos.append(f"- {u}: {e}")
        if rotos:
            abrir["enlaces-senado"] = ("[auto] Enlaces rotos del Senado", "Estos enlaces del Senado no respondieron bien:\n\n" + "\n".join(rotos))
        # 5. live site equals main
        claves.add("sitio-desfasado")
        ult = subprocess.run(["git", "log", "-1", "--format=%ct", "--", "docs/data"], cwd=d, capture_output=True, text=True).stdout.strip()
        if ult and time.time() - int(ult) > 3600:
            distintos = []
            for f in sorted((d / "docs" / "data").glob("*.json")):
                try:
                    vivo = cli.get(SITIO + "data/" + f.name + f"?nocache={int(time.time())}", "json").cuerpo
                except FalloFuente as e:
                    distintos.append(f"- {f.name}: {e}")
                    continue
                if hashlib.sha256(vivo).hexdigest() != hashlib.sha256(f.read_bytes()).hexdigest():
                    distintos.append(f"- {f.name}: el sitio publicado no es igual a main")
            if distintos:
                abrir["sitio-desfasado"] = ("[auto] El sitio publicado no coincide con main",
                                            "GitHub Pages no publicó la última versión:\n\n" + "\n".join(distintos) +
                                            "\n\nRevisa la pestaña Actions > pages-build-deployment.")
        if not a.sin_enlaces:
            claves.add("enlaces-rotos")
            rotos, dudosos = [], []
            for u in sorted(urls_de(d)):
                if "senadord.gob.do" in u or u.startswith(SITIO) or "w3.org" in u or "goatcounter.com" in u:
                    continue
                try:
                    r = cli.get(u, "cualquiera")
                    if "html" in r.tipo and PAGINA_404.search(r.texto()[:20000]):
                        rotos.append(f"- {u}: responde 200 pero la página dice que no existe")
                except FalloFuente as e:
                    (dudosos if no_comprobable(str(e)) else rotos).append(f"- {u}: {e}")
            for linea in dudosos:
                print("no se pudo comprobar (bloqueo de robots o certificado incompleto):", linea)
            if rotos:
                abrir["enlaces-rotos"] = ("[auto] Enlaces rotos", "Estos enlaces no respondieron bien:\n\n" + "\n".join(rotos))
    cli.guardar()
    for k in sorted(claves):
        if k in abrir:
            titulo, cuerpo = abrir[k]
            informe.append(f"ABRIR {k}: {titulo} -> {issues.abrir(k, titulo, cuerpo, ETQ)}")
        else:
            informe.append(f"ok {k} -> {issues.cerrar(k, ETQ)}")
    (d / ".psrd-run").mkdir(exist_ok=True)
    (d / ".psrd-run" / "frescura.txt").write_text("\n".join(informe) + "\n", encoding="utf-8")
    print("\n".join(informe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
