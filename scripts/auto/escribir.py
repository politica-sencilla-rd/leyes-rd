#!/usr/bin/env python3
"""AI writer + independent AI checker -> docs/data/resumenes.json.

Nobody approves the text by hand. Instead every sentence must survive:
  1. Code checks (no AI): each sentence carries a word-for-word quote ("cita")
     that must appear in the official source; every number is written in
     digits and appears in the source; no number words; no party names,
     judgement words or roster names; bills not yet passed must be worded as a
     proposal; length caps.
  2. An independent checker model (different family from the writer) answers
     one yes/no question at a time about ONE sentence and a window of the
     source. Anything other than exactly SI / NO is a failure.
  3. A canary before the run: a known-good sentence must pass and three
     known-bad ones must fail, or the whole run stops (checker degraded).

Fail closed: HTTP error, timeout, non-JSON (the dead GitHub Models endpoint
answers 200 "OK"), finishReason != STOP, safety block, schema error or any
exception -> nothing is published for that item. Drafts go to the run log only.

Usage:
  python3 scripts/auto/escribir.py [--dry-run] [--stub]
  --stub   use a local fake model (no network, no key). Only for plumbing tests;
           it says nothing about real model quality.
Env: GEMINI_API_KEY (repo secret), PSRD_IA must be "si" in Actions.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comun import (PARECE_LEY, ROOT, Arbol, hoy_et, nombra_persona, norm, numero_en_letras,  # noqa: E402
                   numeros_ausentes, patrones_nombres)

RES = "docs/data/resumenes.json"
COLA = "pipeline-state/cola_resumenes.json"
CANARIO = ROOT / "tests" / "fixtures" / "ia_canario.json"
INICIO_PROPUESTA = ("La propuesta busca", "Si se aprueba,")


class Rechazo(Exception):
    pass


# ------------------------------------------------------------------ models
class Gemini:
    def __init__(self, conf: dict, key: str):
        self.conf, self.key = conf, key
        self._lock = threading.Lock()
        self._ultima = 0.0

    def _turno(self):
        with self._lock:
            falta = self.conf["segundos_entre_llamadas"] - (time.monotonic() - self._ultima)
            if falta > 0:
                time.sleep(falta)
            self._ultima = time.monotonic()

    def generar(self, modelo: str, prompt: str, system: str | None = None, schema: dict | None = None) -> str:
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}}
        if system:
            if modelo.startswith("gemma"):  # Gemma on this API has no system role
                body["contents"][0]["parts"][0]["text"] = system + "\n\n" + prompt
            else:
                body["systemInstruction"] = {"parts": [{"text": system}]}
        if schema:
            body["generationConfig"].update(responseMimeType="application/json", responseSchema=schema)
        url = self.conf["api"].format(modelo=modelo)
        for intento in range(2):
            self._turno()
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "x-goog-api-key": self.key})
            try:
                from red import SSL
                with urllib.request.urlopen(req, timeout=self.conf["timeout_segundos"], context=SSL) as r:
                    ctype, raw = r.headers.get("Content-Type", ""), r.read().decode()
                return interpretar_respuesta(modelo, ctype, raw)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 503) and intento == 0:
                    time.sleep(15)
                    continue
                raise Rechazo(f"{modelo}: HTTP {e.code}") from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if intento == 0:
                    time.sleep(5)
                    continue
                raise Rechazo(f"{modelo}: {type(e).__name__}") from e
        raise Rechazo(f"{modelo}: sin respuesta")


def interpretar_respuesta(modelo: str, ctype: str, raw: str) -> str:
    """Fail-closed parsing of a generateContent answer (unit-tested with real saved responses)."""
    if "json" not in ctype.lower():
        raise Rechazo(f"{modelo}: respuesta 200 que no es JSON ({raw[:30]!r})")
    try:
        j = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Rechazo(f"{modelo}: JSON inválido") from e
    cands = j.get("candidates") or []
    if not cands:
        raise Rechazo(f"{modelo}: sin candidatos (bloqueo: {j.get('promptFeedback')})")
    c = cands[0]
    if c.get("finishReason") != "STOP":
        raise Rechazo(f"{modelo}: finishReason={c.get('finishReason')}")
    partes = (c.get("content") or {}).get("parts") or []
    texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
    if not texto.strip():
        raise Rechazo(f"{modelo}: texto vacío")
    return texto


class Cadena:
    """Tries each model of a role in order; a model that errors (HTTP, timeout,
    block) is skipped. Remembers which one answered. All fail -> Rechazo."""

    def __init__(self, modelo_obj, modelos: list[str]):
        self.m, self.modelos, self.usado = modelo_obj, modelos, None

    def generar(self, _ignorado: str, prompt: str, system=None, schema=None) -> str:
        errores = []
        for mod in ([self.usado] if self.usado else []) + [x for x in self.modelos if x != self.usado]:
            try:
                out = self.m.generar(mod, prompt, system, schema)
                self.usado = mod
                return out
            except Rechazo as e:
                errores.append(str(e)[:100])
        raise Rechazo("todos los modelos fallaron: " + "; ".join(errores))


class Stub:
    """Offline fake model for plumbing tests. The writer copies the first
    clause of the source; the checker applies crude rules. NOT a quality test."""

    OPINION = re.compile(r"\b(inteligente|importante|necesari[oa]|positiv[oa]|negativ[oa]|mejor|peor|justa?)\b", re.I)

    def generar(self, modelo: str, prompt: str, system: str | None = None, schema: dict | None = None) -> str:
        if schema:  # writer
            fuente = prompt.split("<<<\n", 1)[1].split("\n>>>", 1)[0]
            campos = json.loads(prompt.rsplit("CAMPOS: ", 1)[1].split("\n", 1)[0])
            limpio = " ".join(fuente.split())
            cita = limpio[:120].rsplit(" ", 1)[0]
            base = re.sub(r"^(Proyecto de ley|Resolución)\s+(que|mediante la cual)\s+", "", cita, flags=re.I)
            palabras = [w for w in base.split() if not re.search(r"\d", w)][:12]
            frase = (" ".join(palabras).rstrip(",;:") + ".").capitalize()
            frases = []
            for c in campos:
                t = frase if c != "te_afecta" else "La propuesta busca " + frase[0].lower() + frase[1:]
                frases.append({"campo": c, "texto": t, "cita": cita})
            return json.dumps({"frases": frases}, ensure_ascii=False)
        # checker: one question
        frase = re.search(r'FRASE: "(.*?)"\n', prompt, re.S)
        f = frase.group(1) if frase else ""
        fuente = prompt.split("<<<\n", 1)[1].split("\n>>>", 1)[0] if "<<<\n" in prompt else ""
        nf = norm(fuente)
        pal = [w for w in re.findall(r"\w+", norm(f)) if len(w) > 3]
        if "apoya" in prompt:
            return "SI" if pal and sum(w in nf for w in pal) / len(pal) >= 0.7 else "NO"
        if "NO aparece" in prompt:
            return "SI" if pal and sum(w in nf for w in pal) / len(pal) < 0.7 else "NO"
        if "opinión" in prompt:
            return "SI" if self.OPINION.search(f) else "NO"
        if "dos hechos" in prompt:
            return "SI" if re.search(r"\by (la|lo|las|los) \w+ó\b|;", f) else "NO"
        if "persona" in prompt:
            return "NO"
        if "solo propone" in prompt:
            return "SI" if PARECE_LEY.search(f) else "NO"
        if "ya es ley" in prompt:
            return "SI" if PARECE_LEY.search(f) else "NO"
        return "NO"


# ------------------------------------------------------------------ checks
def _n(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).split())


def ventana(fuente: str, cita: str, conf: dict) -> str:
    if len(fuente) < conf["fuente_completa_si_menor_de"]:
        return fuente
    f = _n(fuente)
    i = f.find(_n(cita))
    w = conf["ventana_caracteres"]
    return f[max(0, i - w): i + len(_n(cita)) + w] if i >= 0 else f[: 2 * w]


def chequeos_codigo(frases: list[dict], fuente: str, item: dict, conf: dict, prohibidas, nombres) -> list[str]:
    err = []
    fn = _n(fuente)
    no_aprobado = item.get("estado_ley") not in ("aprobada", "promulgada")
    por_campo: dict[str, list[str]] = {}
    for fr in frases:
        t, cita, campo = fr.get("texto", "").strip(), fr.get("cita", "").strip(), fr.get("campo")
        if campo not in conf["campos_por_tipo"][item["tipo"]]:
            err.append(f"campo no pedido: {campo}")
            continue
        por_campo.setdefault(campo, []).append(t)
        if not t:
            err.append(f"{campo}: frase vacía")
            continue
        if re.search(r"[<>{}]|https?://", t):
            err.append("(5) la frase trae código o enlaces")
        if not cita or _n(cita) not in fn:
            err.append(f"(1) la cita no aparece tal cual en la fuente: {cita[:60]!r}")
        if len(cita) > conf["max_caracteres_cita"]:
            err.append("(5) cita demasiado larga")
        for num in numeros_ausentes(t, fuente):
            err.append(f"(2) el número {num} no está en la fuente")
        if numero_en_letras(t):
            err.append(f"(2) número escrito en letras: {numero_en_letras(t)!r}")
        for rx in prohibidas:
            m = rx.search(t)
            if m:
                err.append(f"(3) palabra no permitida: {m.group(0)!r}")
        persona = nombra_persona(t, nombres)
        if persona:
            err.append(f"(3) nombra a una persona: {persona}")
        if no_aprobado:
            if campo == "te_afecta" and not t.startswith(INICIO_PROPUESTA):
                err.append("(4) en un proyecto no aprobado 'te_afecta' empieza con 'La propuesta busca' o 'Si se aprueba,'")
            if PARECE_LEY.search(t):
                err.append(f"(4) presenta como hecho algo no aprobado: {PARECE_LEY.search(t).group(0)!r}")
        if len(t.split()) > conf["max_palabras_frase"]:
            err.append(f"(5) frase de más de {conf['max_palabras_frase']} palabras")
    for campo in conf["campos_por_tipo"][item["tipo"]]:
        if not por_campo.get(campo):
            err.append(f"falta el campo {campo}")
    if item["tipo"] == "titulo_voto" and len(" ".join(por_campo.get("titulo_facil", [])).split()) > conf["max_palabras_titulo_facil"]:
        err.append(f"(5) titulo_facil de más de {conf['max_palabras_titulo_facil']} palabras")
    if len(por_campo.get("en_30_segundos", [])) > 1:
        err.append("(5) en_30_segundos debe ser una sola frase")
    return err


PREGUNTAS = [
    ("Q1", "¿El TEXTO FUENTE apoya lo que dice la FRASE?", True, True),
    ("Q2", "¿La FRASE contiene algún dato que NO aparece en el TEXTO FUENTE?", False, True),
    ("Q3", "¿La FRASE expresa una opinión o un juicio?", False, False),
    ("Q4", "¿La FRASE afirma dos hechos distintos o más?", False, False),
    ("Q5", "¿La FRASE menciona a una persona por su nombre?", False, False),
    ("Q6", "¿La FRASE presenta como un hecho algo que el TEXTO FUENTE solo propone?", False, True),
]


def pregunta(modelo_obj, revisor: str, q: str, frase: str, fuente: str | None) -> bool:
    p = (f"TEXTO FUENTE:\n<<<\n{fuente}\n>>>\n" if fuente is not None else "") + \
        f'FRASE: "{frase}"\nPregunta: {q}\nResponde con UNA sola palabra: SI o NO.'
    a = unicodedata.normalize("NFKD", modelo_obj.generar(revisor, p)).encode("ascii", "ignore").decode().upper()
    a = re.sub(r"[^A-Z]", "", a)
    if a not in ("SI", "NO"):
        raise Rechazo(f"el revisor no respondió SI o NO: {a[:20]!r}")
    return a == "SI"


def revisar(frases: list[dict], fuente: str, item: dict, modelo_obj, revisor: str, conf: dict) -> tuple[int, int, list]:
    """Returns (passed, total, failures). Any exception propagates as Rechazo."""
    no_aprobado = item.get("estado_ley") not in ("aprobada", "promulgada")
    pasadas, total, fallos = 0, 0, []
    for fr in frases:
        win = ventana(fuente, fr["cita"], conf)
        for qid, q, esperado, con_fuente in PREGUNTAS:
            if qid == "Q6" and not no_aprobado:
                continue
            total += 1
            got = pregunta(modelo_obj, revisor, q, fr["texto"], win if con_fuente else None)
            if got == esperado:
                pasadas += 1
            else:
                fallos.append({"pregunta": qid, "texto_pregunta": q, "frase": fr["texto"], "campo": fr["campo"]})
    # Q7 guards only against over-claiming: it is asked when the item is NOT law
    # yet. For a passed law, a summary that doesn't repeat "es ley" is not wrong.
    if no_aprobado:
        resumen = " ".join(f["texto"] for f in frases)
        total += 1
        if not pregunta(modelo_obj, revisor, "¿El RESUMEN dice que esto ya es ley?", resumen, None):
            pasadas += 1
        else:
            fallos.append({"pregunta": "Q7", "texto_pregunta": "¿El RESUMEN dice que esto ya es ley?", "frase": resumen,
                           "campo": "*"})
    return pasadas, total, fallos


SISTEMA = ("Eres un redactor neutral. Explicas el gobierno de República Dominicana a un niño de 12 años. "
           "Usa SOLO datos del TEXTO FUENTE. No opines, no juzgues, no nombres partidos ni personas. "
           "Cada frase dice UNA sola cosa y tiene como máximo 20 palabras. Escribe los números con cifras, "
           "copiados de la fuente. Cada frase lleva una 'cita': un pedazo copiado letra por letra de la fuente "
           "(máximo 300 caracteres) que la respalda. Si el proyecto no está aprobado, no digas que es ley: "
           "en 'te_afecta' cada frase empieza con 'La propuesta busca' o con 'Si se aprueba,'. "
           "Escribe con tildes y ñ correctas.")
ESQUEMA = {"type": "OBJECT", "properties": {"frases": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"campo": {"type": "STRING"}, "texto": {"type": "STRING"}, "cita": {"type": "STRING"}},
    "required": ["campo", "texto", "cita"]}}}, "required": ["frases"]}
GUIA_CAMPOS = {"titulo_facil": "un título corto (máximo 14 palabras) de qué trata",
               "que_es": "qué es, en 1 a 3 frases", "por_que": "por qué se propone, según la fuente, en 1 o 2 frases",
               "te_afecta": "cómo podría afectar a la gente, en 1 o 2 frases",
               "en_30_segundos": "una sola frase que lo resume"}


def escribir(modelo_obj, escritor: str, fuente: str, item: dict, conf: dict, feedback: str | None) -> list[dict]:
    campos = conf["campos_por_tipo"][item["tipo"]]
    guia = "; ".join(f"{c}: {GUIA_CAMPOS[c]}" for c in campos)
    estado = "APROBADO/PROMULGADO" if item.get("estado_ley") in ("aprobada", "promulgada") else "NO APROBADO (solo propuesto)"
    prompt = (f"TEXTO FUENTE:\n<<<\n{fuente}\n>>>\nESTADO: {estado}\nCAMPOS: {json.dumps(campos)}\n"
              f"Escribe estos campos ({guia}).")
    if feedback:
        prompt += f"\nTu intento anterior fue rechazado: {feedback}. Corrígelo."
    raw = modelo_obj.generar(escritor, prompt, SISTEMA, ESQUEMA)
    try:
        out = json.loads(raw)
        frases = [{"campo": f["campo"], "texto": f["texto"].strip(), "cita": f["cita"].strip()} for f in out["frases"]]
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
        raise Rechazo(f"el escritor no devolvió el esquema pedido: {e}") from e
    if not frases:
        raise Rechazo("el escritor no devolvió frases")
    return frases


def cargar_listas(arbol: Arbol):
    neu = arbol.leer("config/neutralidad.json")
    prohibidas = []
    if neu["prohibidas_exactas"]:
        prohibidas.append(re.compile(r"\b(" + "|".join(map(re.escape, neu["prohibidas_exactas"])) + r")\b"))
    if neu["prohibidas"]:
        prohibidas.append(re.compile(r"\b(" + "|".join(neu["prohibidas"]) + r")\b", re.I))
    nombres = list(arbol.leer("config/personas_publicas.json")["nombres"])
    for p in arbol.leer("docs/data/provincias.json")["provincias"]:
        for l in p["lideres"]:
            if len((l.get("nombre") or "").split()) >= 2:
                nombres.append(l["nombre"])
    return prohibidas, patrones_nombres(nombres)


def procesar(item: dict, fuente: str, modelo_obj, conf: dict, listas, escritores, revisores) -> dict:
    """One item -> {'estado': 'verificado', ...} or {'estado': 'rechazado', 'motivo', 'fallos', 'borrador'}."""
    if set(escritores) & set(revisores):
        return {"estado": "rechazado", "motivo": "el revisor no puede ser un modelo escritor"}
    esc_c, rev_c = Cadena(modelo_obj, escritores), Cadena(modelo_obj, revisores)
    feedback, borrador, fallos = None, None, []
    try:
        for _ in range(conf["max_reescrituras"] + 1):
            frases = escribir(esc_c, "", fuente, item, conf, feedback)
            borrador = frases
            errs = chequeos_codigo(frases, fuente, item, conf, *listas)
            if errs:
                fallos = [{"pregunta": "codigo", "texto_pregunta": e, "frase": "", "campo": ""} for e in errs]
                feedback = "; ".join(errs[:4])
                continue
            pasadas, total, fallos = revisar(frases, fuente, item, rev_c, "", conf)
            if pasadas == total:
                escritor, revisor = esc_c.usado, rev_c.usado
                rec = {"tipo": item["tipo"], "estado": "verificado", "estado_ley": item.get("estado_ley"),
                       "fuente_url": item["fuente_url"], "fuente_nombre": item.get("fuente_nombre", ""),
                       "fuente_sha256": item["fuente_sha256"], "modelo_escritor": escritor,
                       "modelo_revisor": revisor, "checks_pasados": pasadas, "checks_total": total,
                       "fecha": hoy_et().isoformat()}
                for c in conf["campos_por_tipo"][item["tipo"]]:
                    rec[c] = " ".join(f["texto"] for f in frases if f["campo"] == c)
                return rec
            feedback = "; ".join(f"{f['pregunta']} ({f['texto_pregunta']}) falló en: {f['frase'][:80]}" for f in fallos[:3])
        return {"estado": "rechazado", "motivo": "no pasó las revisiones", "fallos": fallos, "borrador": borrador}
    except Rechazo as e:
        return {"estado": "rechazado", "motivo": str(e), "fallos": fallos, "borrador": borrador}
    except Exception as e:  # noqa: BLE001  anything unexpected is a rejection too
        return {"estado": "rechazado", "motivo": f"{type(e).__name__}: {e}", "borrador": borrador}


def canario(modelo_obj, conf: dict, listas, escritores, revisores) -> tuple[bool, list[str]]:
    c = json.loads(CANARIO.read_text(encoding="utf-8"))
    item = {"tipo": "ley", "estado_ley": c["estado_ley"], "fuente_url": "", "fuente_sha256": ""}
    revisor = Cadena(modelo_obj, revisores)
    log, ok = [], True
    for caso in c["casos"]:
        frases = [{"campo": "que_es", "texto": caso["frase"], "cita": caso["cita"]}]
        try:
            errs = chequeos_codigo(frases, c["fuente"], item, conf, *listas)
            if errs:
                got = "rechazado"
            else:
                p, t, _ = revisar(frases, c["fuente"], item, revisor, "", conf)
                got = "verificado" if p == t else "rechazado"
        except Rechazo as e:
            got = f"error: {e}"
        log.append(f"canario {caso['nombre']}: esperado {caso['esperado']}, salió {got}")
        ok &= got == caso["esperado"]
    return ok, log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--max-items", type=int)
    a = ap.parse_args(argv)
    arbol = Arbol("escribir", dry_run=a.dry_run)
    conf = arbol.leer("config/ia.json")
    if a.stub:
        modelo_obj, escritores, revisores = Stub(), ["stub-escritor"], ["stub-revisor"]
    else:
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            print("Falta GEMINI_API_KEY: no se escribe nada (falla cerrada).", file=sys.stderr)
            arbol.anotar_run("resumenes_ia", estado="sin_clave")
            return 1
        modelo_obj, escritores, revisores = Gemini(conf, key), conf["escritores"], conf["revisores"]
    if set(escritores) & set(revisores):
        print("Ningún revisor puede ser también escritor (config/ia.json).", file=sys.stderr)
        return 1
    listas = cargar_listas(arbol)

    ok, log = canario(modelo_obj, conf, listas, escritores, revisores)
    print("\n".join(log))
    if not ok:
        arbol.anotar_run("resumenes_ia", estado="roto", error="el canario falló: el revisor se degradó", canario=log)
        print("CANARIO FALLÓ: no se publica nada en esta corrida.", file=sys.stderr)
        return 1

    cola = arbol.leer(COLA, {"items": []})
    res = arbol.leer(RES, {"_nota": "", "resumenes": {}, "sin_resumen": {}})
    res.setdefault("sin_resumen", {})
    pend = [it for it in cola["items"] if it.get("intentos", 0) < conf["max_intentos"]]
    pend = pend[: a.max_items or conf["max_items_por_corrida"]]
    inicio = time.monotonic()
    fallos_issue, hechos = [], 0

    def uno(it):
        if (time.monotonic() - inicio) / 60 > conf["max_minutos_por_corrida"]:
            return it, None
        f = arbol.p(f"pipeline-state/textos/{it['fuente_sha256']}.txt")
        if not f.exists():
            return it, {"estado": "rechazado", "motivo": "falta el texto fuente guardado"}
        return it, procesar(it, f.read_text(encoding="utf-8"), modelo_obj, conf, listas, escritores, revisores)

    with ThreadPoolExecutor(conf["llamadas_en_paralelo"]) as ex:
        for it, r in ex.map(uno, pend):
            if r is None:
                continue
            if r["estado"] == "verificado":
                res["resumenes"][it["id"]] = r
                res["sin_resumen"].pop(it["id"], None)
                cola["items"] = [x for x in cola["items"] if x["id"] != it["id"]]
                hechos += 1
                print(f"{it['id']}: verificado ({r['checks_pasados']}/{r['checks_total']})")
            else:
                it["intentos"] = it.get("intentos", 0) + 1
                print(f"{it['id']}: rechazado ({r['motivo']}) intento {it['intentos']}")
                arbol.escribir_texto(f".psrd-run/borradores/{it['id']}.json",
                                     json.dumps(r, ensure_ascii=False, indent=1))
                primer = (r.get("fallos") or [{}])[0]
                it["ultimo_fallo"] = {"campo": primer.get("campo", ""),
                                      "pregunta": (primer.get("pregunta", "") + " " + primer.get("texto_pregunta", "")).strip()
                                      or r["motivo"][:120]}
                fallos_issue.append(it["id"])
                if it["intentos"] >= conf["max_intentos"]:
                    res["sin_resumen"][it["id"]] = {"intentos": it["intentos"], "fuente_url": it["fuente_url"]}
    res["_nota"] = ("Resúmenes automáticos: los escribe un modelo de IA y otro modelo distinto los revisa "
                    "pregunta por pregunta contra el documento oficial. Solo se publica lo que pasa todas las "
                    "revisiones. 'sin_resumen' lista lo que no pasó tras 3 intentos.")
    arbol.escribir(RES, res)
    arbol.escribir(COLA, cola)
    # The rolling issue lists EVERY item still failing (not only this run's), so it closes only when all clear.
    tabla = [{"id": it["id"], "campo": (it.get("ultimo_fallo") or {}).get("campo", ""),
              "pregunta": (it.get("ultimo_fallo") or {}).get("pregunta", ""), "intentos": it["intentos"],
              "fuente_url": it["fuente_url"]} for it in cola["items"] if it.get("intentos", 0) > 0]
    arbol.escribir_texto(".psrd-run/ia-fallos.json", json.dumps(tabla, ensure_ascii=False, indent=1))
    arbol.anotar_run("resumenes_ia", estado="ok", verificados=hechos, rechazados=len(fallos_issue),
                     en_cola=len(cola["items"]), modelo="stub" if a.stub else escritores[0])
    print(f"listo: {hechos} verificados, {len(fallos_issue)} rechazados, {len(cola['items'])} en cola")
    return 0


if __name__ == "__main__":
    sys.exit(main())
