"""Zoom: página de busca /busca/<termos> (o robots.txt bloqueia só '?q=', não o caminho /busca/).

Cada resultado traz o menor preço entre as lojas, a melhor loja e o parcelamento
(`installments`) com o indicador `hasInterest` (tem juros). Dados no <script id="__NEXT_DATA__">.
O Buscapé é do mesmo grupo e usa exatamente o mesmo formato (ver sources/buscape.py).
"""
from __future__ import annotations

from datetime import datetime

from http_client import FonteErro, baixar
from models import Oferta
from sources.base import next_data

NOME = "zoom"
URL_PADRAO = "https://www.zoom.com.br/busca/playstation+5+slim+digital"
BASE = "https://www.zoom.com.br"


def buscar(cfg_fonte: dict, idade_maxima_horas: float | None = None) -> list[Oferta]:
    # Zoom mostra preço atual de loja, não um post datado: idade não se aplica.
    return parse(baixar(cfg_fonte.get("url", URL_PADRAO)))


def parse(html: str, agora: datetime | None = None, idade_maxima_horas: float | None = None,
          base: str = BASE, fonte: str = NOME) -> list[Oferta]:
    dados = next_data(html)
    hits = dados["props"]["initialReduxState"]["hits"]["hits"]
    if not hits:
        # a listagem nunca fica vazia de verdade: vazio indica página alterada ou resposta parcial
        raise FonteErro("página veio sem resultados (resposta parcial ou HTML mudou)")
    ofertas = []
    for h in hits:
        preco = h.get("price")
        if not preco or not h.get("url"):
            continue
        inst = h.get("installments") or {}
        parcelas = int(inst["amount_months"]) if inst.get("amount_months") else None
        loja = h.get("merchantName") or (h.get("bestOffer") or {}).get("merchantName") or "?"
        url = h["url"] if h["url"].startswith("http") else base + h["url"]
        ofertas.append(Oferta(
            loja=loja,
            titulo=(h.get("name") or "").strip(),
            preco_total=round(float(preco), 2),
            parcelas=parcelas,
            valor_parcela=inst.get("price"),
            sem_juros=bool(parcelas and parcelas > 1 and not h.get("hasInterest", True)),
            cupom=None,
            imagem=h.get("image") if isinstance(h.get("image"), str) else None,
            link=url,
            fonte=fonte,
        ))
    return ofertas
