"""One fetch helper for every source (named red.py, not http.py, so it never shadows the stdlib http package).

- Per-host minimum spacing (senadord.gob.do asks for Crawl-delay: 120 in robots.txt).
- Retries on network errors and 429/5xx.
- Checks the body really is what we asked for (JSON parses, PDFs start with
  %PDF, XLSX is a zip). The dead GitHub Models endpoint answered HTTP 200 "OK":
  a 200 alone proves nothing.
- Every response leaves a receipt (url, status, type, bytes, sha256). Gate G4
  accepts a new source URL only if this run holds a 200 receipt for it.
"""
from __future__ import annotations

import hashlib
import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

def _contexto_ssl() -> ssl.SSLContext:
    """System CAs (Ubuntu runners have them). python.org builds on macOS ship
    without CAs, so use certifi's bundle when it is installed."""
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


SSL = _contexto_ssl()

UA = "Mozilla/5.0 (compatible; PoliticaSencillaRD-bot/2.0; +https://github.com/politica-sencilla-rd/leyes-rd)"

ESPERA_POR_HOST = {
    "www.senadord.gob.do": 120.0,
    "senadord.gob.do": 120.0,
}
ESPERA_DEFECTO = 0.2


class FalloFuente(Exception):
    """The source did not give us a usable answer."""


@dataclass
class Respuesta:
    url: str
    status: int
    tipo: str
    cuerpo: bytes
    cabeceras: dict = field(default_factory=dict)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.cuerpo).hexdigest()

    def json(self):
        return json.loads(self.cuerpo.decode("utf-8"))

    def texto(self) -> str:
        return self.cuerpo.decode("utf-8", errors="replace")


def _valida(esperado: str, r: Respuesta) -> None:
    c = r.cuerpo
    if esperado == "json":
        s = c.lstrip()[:1]
        if s not in (b"{", b"["):
            raise FalloFuente(f"{r.url}: se esperaba JSON y llegó {c[:40]!r} ({r.tipo})")
        try:
            json.loads(c.decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            raise FalloFuente(f"{r.url}: JSON inválido: {e}") from e
    elif esperado == "pdf":
        if not c.startswith(b"%PDF"):
            raise FalloFuente(f"{r.url}: no es un PDF ({c[:20]!r})")
    elif esperado == "xlsx":
        if not c.startswith(b"PK"):
            raise FalloFuente(f"{r.url}: no es un XLSX ({c[:20]!r})")
    elif esperado == "xls":
        if not (c.startswith(b"\xd0\xcf\x11\xe0") or c.startswith(b"PK")):
            raise FalloFuente(f"{r.url}: no es un XLS ({c[:20]!r})")
    elif esperado == "html":
        if b"<" not in c[:2000]:
            raise FalloFuente(f"{r.url}: no parece HTML")
    if len(c) == 0:
        raise FalloFuente(f"{r.url}: respuesta vacía")


class Cliente:
    def __init__(self, recibos_path: Path | None = None, espera: dict | None = None,
                 timeout: int = 90, reintentos: int = 3, dormir=time.sleep, ahora=time.monotonic):
        self.recibos_path = recibos_path
        self.espera = dict(ESPERA_POR_HOST)
        if espera:
            self.espera.update(espera)
        self.timeout = timeout
        self.reintentos = reintentos
        self._ultimo: dict[str, float] = {}
        self._dormir = dormir
        self._ahora = ahora
        self.recibos: list[dict] = []
        self._lock = threading.Lock()
        if recibos_path and recibos_path.exists():
            try:
                self.recibos = json.loads(recibos_path.read_text())
            except Exception:  # noqa: BLE001
                self.recibos = []

    def _esperar_turno(self, host: str) -> None:
        # Held while sleeping on purpose: threads queue up per spacing rule.
        with self._lock:
            gap = self.espera.get(host, ESPERA_DEFECTO)
            ult = self._ultimo.get(host)
            if ult is not None:
                falta = gap - (self._ahora() - ult)
                if falta > 0:
                    self._dormir(falta)
            self._ultimo[host] = self._ahora()

    def _recibo(self, r: Respuesta | None, url: str, error: str | None = None) -> None:
        rec = {"url": url, "status": r.status if r else None, "tipo": r.tipo if r else None,
               "bytes": len(r.cuerpo) if r else 0, "sha256": r.sha256 if r else None,
               "error": error, "hora": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with self._lock:
            self.recibos.append(rec)

    def guardar(self) -> None:
        """Write the receipts file (call once at the end of a run, also on failure)."""
        if self.recibos_path:
            self.recibos_path.parent.mkdir(parents=True, exist_ok=True)
            self.recibos_path.write_text(json.dumps(self.recibos, ensure_ascii=False, indent=1))

    def get(self, url: str, esperado: str = "json", data: bytes | None = None,
            cabeceras: dict | None = None) -> Respuesta:
        host = urllib.parse.urlsplit(url).hostname or ""
        h = {"User-Agent": UA, "Accept": "*/*"}
        if cabeceras:
            h.update(cabeceras)
        ultimo_error = None
        for intento in range(self.reintentos):
            self._esperar_turno(host)
            req = urllib.request.Request(url, headers=h, data=data)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=SSL) as resp:
                    r = Respuesta(resp.geturl(), resp.status, resp.headers.get("Content-Type", ""),
                                  resp.read(), dict(resp.headers.items()))
                _valida(esperado, r)
                self._recibo(r, url)
                return r
            except urllib.error.HTTPError as e:
                ultimo_error = f"HTTP {e.code}"
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except FalloFuente as e:
                ultimo_error = str(e)
                break  # wrong content will not fix itself on retry
            except Exception as e:  # noqa: BLE001 (URLError, timeout, reset)
                ultimo_error = f"{type(e).__name__}: {e}"
            if intento < self.reintentos - 1 and self.espera.get(host, ESPERA_DEFECTO) < 5:
                self._dormir(2.0 * (intento + 1))
        self._recibo(None, url, ultimo_error)
        raise FalloFuente(f"{url}: {ultimo_error}")


def recibo_ok(recibos: list[dict], url: str) -> bool:
    return any(r.get("url") == url and r.get("status") == 200 and not r.get("error") for r in recibos)
