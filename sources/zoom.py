"""Zoom: página de busca /busca/<termos> (o robots.txt bloqueia só '?q=', não o caminho /busca/).

Cada resultado traz o menor preço entre as lojas, a melhor loja e o parcelamento
(`installments`) com o indicador `hasInterest` (tem juros). Dados no <script id="__NEXT_DATA__">.
"""
from __future__ import annotations

from datetime import datetime

from http_client import baixar
from models import Oferta
from sources.base import next_data

NOME = "zoom"
URL_PADRAO = "https://www.zoom.com.br/busca/playstation+5+slim+digital+astro+bot"
BASE = "https://www.zoom.com.br"


def buscar(cfg_fonte: dict, idade_maxima_horas: float | None = None) -> list[Oferta]:
    # Zoom mostra preço atual de loja, não um post datado: idade não se aplica.
    return parse(baixar(cfg_fonte.get("url", URL_PADRAO)))


def parse(html: str, agora: datetime | None = None, idade_maxima_horas: float | None = None) -> list[Oferta]:
    dados = next_data(html)
    hits = dados["props"]["initialReduxState"]["hits"]["hits"]
    ofertas = []
    for h in hits:
        preco = h.get("price")
        if not preco:
            continue
        inst = h.get("installments") or {}
        parcelas = int(inst.get("amount_months") or 1)
        loja = h.get("merchantName") or (h.get("bestOffer") or {}).get("merchantName") or "?"
        ofertas.append(Oferta(
            loja=loja,
            titulo=(h.get("name") or "").strip(),
            preco_total=round(float(preco), 2),
            parcelas=parcelas,
            valor_parcela=inst.get("price"),
            sem_juros=parcelas > 1 and not h.get("hasInterest", True),
            cupom=None,
            link=BASE + h["url"],
            fonte=NOME,
        ))
    return ofertas
