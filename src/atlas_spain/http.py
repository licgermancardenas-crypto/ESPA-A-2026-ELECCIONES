"""Cliente HTTP común.

Reglas:
- User-Agent honesto que identifica al cliente. Nunca se imita un navegador.
- Reintentos con backoff solo para errores transitorios (429, 5xx, red).
- Si la respuesta es un desafío anti-bot (p. ej. Cloudflare "Just a moment..."),
  se reporta como BlockedByChallenge y NO se intenta eludir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

# Identificador corto y honesto. (El WAF del Congreso rechaza UAs que incluyen una URL.)
USER_AGENT = "ATLAS-Spain-ETL/0.1 (public open-data research)"

RETRY_STATUS = {429, 500, 502, 503, 504}


class BlockedByChallenge(RuntimeError):
    """El servidor exige un desafío interactivo (anti-bot). Requiere carga manual."""


class HttpError(RuntimeError):
    def __init__(self, url: str, status: int):
        super().__init__(f"HTTP {status} en {url}")
        self.url = url
        self.status = status


@dataclass
class Fetched:
    url: str
    status: int
    content: bytes
    content_type: str


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


_SESSION = _session()


def looks_like_challenge(status: int, content_type: str, body_head: bytes) -> bool:
    if "text/html" not in (content_type or ""):
        return False
    head = body_head[:4000].lower()
    return status in (403, 503) and (b"just a moment" in head or b"cf-chl" in head or b"challenge-platform" in head)


def fetch(url: str, *, timeout: float = 60, retries: int = 3, backoff: float = 2.0,
          headers: dict | None = None) -> Fetched:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            r = _SESSION.get(url, timeout=timeout, headers=headers or {})
            ctype = r.headers.get("Content-Type", "")
            if looks_like_challenge(r.status_code, ctype, r.content):
                raise BlockedByChallenge(f"Desafío anti-bot en {url}")
            if r.status_code in RETRY_STATUS and attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            if r.status_code >= 400:
                raise HttpError(url, r.status_code)
            return Fetched(url=url, status=r.status_code, content=r.content, content_type=ctype)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
    raise RuntimeError(f"Fallo inesperado en {url}: {last_exc}")


def probe(url: str, timeout: float = 45, headers: dict | None = None) -> dict:
    """Verificación ligera de disponibilidad para el registro de fuentes."""
    try:
        r = _SESSION.get(url, timeout=timeout, stream=True, headers=headers or {})
        head = r.raw.read(4096, decode_content=True) or b""
        ctype = r.headers.get("Content-Type", "")
        size = r.headers.get("Content-Length")
        r.close()
        if looks_like_challenge(r.status_code, ctype, head):
            estado = "bloqueado_antibot"
        elif r.status_code < 400:
            estado = "disponible"
        else:
            estado = f"error_http_{r.status_code}"
        return {"http_status": r.status_code, "content_type": ctype.split(";")[0],
                "content_length": int(size) if size and size.isdigit() else None, "estado": estado}
    except requests.RequestException as exc:
        return {"http_status": None, "content_type": None, "content_length": None,
                "estado": f"error_red:{type(exc).__name__}"}
