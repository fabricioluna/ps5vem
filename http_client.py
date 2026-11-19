"""Cliente HTTP comum às fontes: User-Agent realista, timeout, 2 tentativas, robots.txt.

Nunca tenta burlar bloqueio: 403/429/captcha viram FonteBloqueada e não são repetidos.
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
TIMEOUT = 15
TENTATIVAS = 2
PAUSA_SEGUNDOS = 2.0


class FonteErro(Exception):
    """Falha ao consultar uma fonte."""


class FonteBloqueada(FonteErro):
    """A fonte recusou o acesso (403, 429, captcha ou robots.txt)."""


_ultima_requisicao = 0.0


def _pausa():
    global _ultima_requisicao
    espera = PAUSA_SEGUNDOS - (time.monotonic() - _ultima_requisicao)
    if espera > 0:
        time.sleep(espera)
    _ultima_requisicao = time.monotonic()


@lru_cache(maxsize=32)
def _robots(base: str) -> RobotFileParser | None:
    rp = RobotFileParser()
    try:
        r = requests.get(f"{base}/robots.txt", headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return None  # sem robots.txt acessível: segue normalmente
    if r.status_code >= 400:
        return None
    rp.parse(r.text.splitlines())
    return rp


def permitido_pelo_robots(url: str) -> bool:
    p = urlsplit(url)
    rp = _robots(f"{p.scheme}://{p.netloc}")
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def baixar(url: str, params: dict | None = None) -> str:
    """Baixa a URL e devolve o texto. Lança FonteBloqueada ou FonteErro."""
    full = requests.Request("GET", url, params=params).prepare().url
    if not permitido_pelo_robots(full):
        raise FonteBloqueada(f"robots.txt não permite {full}")

    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        _pausa()
        try:
            r = requests.get(full, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as e:
            ultimo_erro = e
            log.warning("  tentativa %d/%d falhou: %s", tentativa, TENTATIVAS, e)
            continue
        if r.status_code in (401, 403, 429) or _parece_captcha(r.text):
            raise FonteBloqueada(f"HTTP {r.status_code} em {full}")
        if r.status_code >= 400:
            ultimo_erro = FonteErro(f"HTTP {r.status_code} em {full}")
            log.warning("  tentativa %d/%d: HTTP %d", tentativa, TENTATIVAS, r.status_code)
            continue
        r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
        return r.text
    raise FonteErro(str(ultimo_erro))


def _parece_captcha(html: str) -> bool:
    trecho = html[:5000].lower()
    return any(s in trecho for s in ("cf-challenge", "captcha-delivery", "g-recaptcha", "just a moment..."))
