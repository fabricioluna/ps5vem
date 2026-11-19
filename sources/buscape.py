"""Buscapé: mesma empresa e mesmo formato de página do Zoom (/busca/<termos>, dados em __NEXT_DATA__)."""
from __future__ import annotations

from datetime import datetime

from http_client import baixar
from models import Oferta
from sources import zoom

NOME = "buscape"
URL_PADRAO = "https://www.buscape.com.br/busca/playstation+5+slim+digital"
BASE = "https://www.buscape.com.br"


def buscar(cfg_fonte: dict, idade_maxima_horas: float | None = None) -> list[Oferta]:
    return parse(baixar(cfg_fonte.get("url", URL_PADRAO)))


def parse(html: str, agora: datetime | None = None, idade_maxima_horas: float | None = None) -> list[Oferta]:
    return zoom.parse(html, base=BASE, fonte=NOME)
