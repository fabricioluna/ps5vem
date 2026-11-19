"""Promobit: página da categoria PlayStation 5.

A busca (/buscar) e a API (/api) são proibidas no robots.txt, então lemos a página
pública da subcategoria, que traz as ofertas em JSON no <script id="__NEXT_DATA__">.
O Promobit não informa parcelas em campo próprio; tentamos ler '12x'/'sem juros' do título e do cupom.
"""
from __future__ import annotations

from datetime import datetime

from http_client import FonteErro, baixar
from models import Oferta, agora_utc
from sources.base import next_data, parcelas_do_texto, recente

NOME = "promobit"
URL_PADRAO = "https://www.promobit.com.br/promocoes/playstation-5/s/"
BASE = "https://www.promobit.com.br"
STATUS_ENCERRADOS = ("FINISH", "EXPIR", "REJECT", "INACTIVE", "DELETED")


def buscar(cfg_fonte: dict, idade_maxima_horas: float | None = None) -> list[Oferta]:
    return parse(baixar(cfg_fonte.get("url", URL_PADRAO)), idade_maxima_horas=idade_maxima_horas)


def parse(html: str, agora: datetime | None = None, idade_maxima_horas: float | None = None) -> list[Oferta]:
    agora = agora or agora_utc()
    dados = next_data(html)
    brutas = dados["props"]["pageProps"]["serverOffers"]["offers"]
    if not brutas:
        # a listagem nunca fica vazia de verdade: vazio indica página alterada ou resposta parcial
        raise FonteErro("página veio sem ofertas (resposta parcial ou HTML mudou)")
    ofertas = []
    for o in brutas:
        status = (o.get("offerStatusName") or "").upper()
        if any(s in status for s in STATUS_ENCERRADOS):
            continue
        publicado = _data(o.get("offerPublished"))
        if not recente(publicado, agora, idade_maxima_horas):
            continue
        preco = o.get("offerPrice")
        if not preco:
            continue
        cupom = (o.get("offerCoupon") or "").strip() or None
        parcelas, sem_juros = parcelas_do_texto(o.get("offerTitle"), cupom)
        ofertas.append(Oferta(
            loja=o.get("storeName") or "?",
            titulo=o.get("offerTitle", ""),
            preco_total=round(float(preco), 2),
            parcelas=parcelas,
            valor_parcela=round(float(preco) / parcelas, 2) if parcelas > 1 else None,
            sem_juros=sem_juros,
            cupom=cupom,
            imagem=_imagem(o.get("offerPhoto")),
            link=f"{BASE}/oferta/{o['offerSlug']}/",
            fonte=NOME,
        ))
    return ofertas


def _imagem(foto: str | None) -> str | None:
    """offerPhoto vem como '/123.jpg'; o CDN serve em tamanhos fixos (120, 180, 300...)."""
    if not foto:
        return None
    if foto.startswith("http"):
        return foto
    return f"https://i.promobit.com.br/300/{foto.lstrip('/')}"


def _data(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
