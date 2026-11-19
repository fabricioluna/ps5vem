"""Utilidades comuns aos parsers de fontes."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from http_client import FonteErro

_PARCELAS = re.compile(r"(\d{1,2})\s*x", re.I)


def next_data(html: str) -> dict:
    """Extrai o JSON de <script id="__NEXT_DATA__"> (sites em Next.js)."""
    tag = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        raise FonteErro("__NEXT_DATA__ não encontrado (o HTML da página mudou?)")
    return json.loads(tag.string)


def parcelas_do_texto(*textos: str | None) -> tuple[int | None, bool]:
    """Procura '12x' e 'sem juros' em textos livres (título, cupom). Devolve (parcelas ou None, sem_juros)."""
    junto = " ".join(t for t in textos if t).lower()
    m = _PARCELAS.search(junto)
    parcelas = int(m.group(1)) if m and 1 < int(m.group(1)) <= 24 else None
    return parcelas, "sem juros" in junto


def recente(publicado: datetime | None, agora: datetime, idade_maxima_horas: float | None) -> bool:
    if publicado is None or not idade_maxima_horas:
        return True
    return agora - publicado <= timedelta(hours=idade_maxima_horas)
