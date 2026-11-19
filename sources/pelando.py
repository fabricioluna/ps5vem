"""Pelando: página de busca /busca/<termos> (permitida no robots.txt; não há RSS público).

O site é feito em Astro: as ofertas vêm no atributo `props` do <astro-island> SearchFeedContent,
serializadas no formato [tipo, valor] (0 = valor simples, 1 = lista).
Ofertas com status 'expired' são ignoradas.
"""
from __future__ import annotations

import json
from datetime import datetime

from bs4 import BeautifulSoup

from http_client import FonteErro, baixar
from models import Oferta, agora_utc
from sources.base import parcelas_do_texto, recente

NOME = "pelando"
URL_PADRAO = "https://www.pelando.com.br/busca/ps5-digital-astro-bot"
BASE = "https://www.pelando.com.br"


def buscar(cfg_fonte: dict, idade_maxima_horas: float | None = None) -> list[Oferta]:
    return parse(baixar(cfg_fonte.get("url", URL_PADRAO)), idade_maxima_horas=idade_maxima_horas)


def _decodificar(no):
    """Converte o formato [tipo, valor] das props do Astro para Python puro."""
    if isinstance(no, list) and len(no) == 2 and isinstance(no[0], int):
        tipo, valor = no
        if tipo == 1:
            return [_decodificar(v) for v in valor]
        if isinstance(valor, dict):
            return {k: _decodificar(v) for k, v in valor.items()}
        return valor
    if isinstance(no, dict):
        return {k: _decodificar(v) for k, v in no.items()}
    return no


def parse(html: str, agora: datetime | None = None, idade_maxima_horas: float | None = None) -> list[Oferta]:
    agora = agora or agora_utc()
    ilha = BeautifulSoup(html, "html.parser").find("astro-island", attrs={"component-export": "SearchFeedContent"})
    if not ilha or not ilha.get("props"):
        raise FonteErro("bloco SearchFeedContent não encontrado (o HTML da página mudou?)")
    props = _decodificar(json.loads(ilha["props"]))
    deals = ((props.get("initialData") or {}).get("deals") or {}).get("deals") or []
    if not deals:
        # a listagem nunca fica vazia de verdade: vazio indica página alterada ou resposta parcial
        raise FonteErro("página veio sem ofertas (resposta parcial ou HTML mudou)")

    ofertas = []
    for d in deals:
        if (d.get("status") or "").lower() == "expired":
            continue
        if not recente(_data(d.get("createdAt")), agora, idade_maxima_horas):
            continue
        preco = d.get("price")
        if not preco:
            continue
        cupom = d.get("couponCode") or None
        parcelas, sem_juros = parcelas_do_texto(d.get("title"), cupom)
        ofertas.append(Oferta(
            loja=(d.get("store") or {}).get("name") or "?",
            titulo=d.get("title", ""),
            preco_total=round(float(preco), 2),
            parcelas=parcelas,
            valor_parcela=round(float(preco) / parcelas, 2) if parcelas > 1 else None,
            sem_juros=sem_juros,
            cupom=cupom,
            imagem=_imagem(d),
            link=f"{BASE}/d/{d['slug']}",
            fonte=NOME,
        ))
    return ofertas


def _imagem(d: dict) -> str | None:
    """Prefere a maior versão do srcset (300px); senão, imageUrl."""
    srcset = [i for i in (d.get("imageSrcset") or []) if isinstance(i, dict) and i.get("url")]
    if srcset:
        return max(srcset, key=lambda i: i.get("width") or 0)["url"]
    return d.get("imageUrl") or None


def _data(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
