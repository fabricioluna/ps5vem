"""KaBuM!: loja que vende direto. Página de busca /busca/<termos> (permitida no robots.txt).

Os produtos vêm em __NEXT_DATA__ (props.pageProps.data.catalogServer.data) com:
  price             preço no cartão (parcelado)
  priceWithDiscount preço à vista (Pix)
  offer             oferta relâmpago "OFERTAS KABUM", com preço próprio e horário de término
  maxInstallment    texto como "10x de R$ 469,90"
Usamos o menor preço à vista disponível como preco_total, igual às outras fontes.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from http_client import FonteErro, baixar
from models import Oferta, agora_utc
from sources.base import next_data

NOME = "kabum"
URL_PADRAO = "https://www.kabum.com.br/busca/ps5-slim-digital"
BASE = "https://www.kabum.com.br"
_PARCELA = re.compile(r"(\d{1,2})\s*x\s*de\s*R\$\s*([\d.,]+)", re.I)


def buscar(cfg_fonte: dict, idade_maxima_horas: float | None = None) -> list[Oferta]:
    return parse(baixar(cfg_fonte.get("url", URL_PADRAO)))


def _numero(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def parse(html: str, agora: datetime | None = None, idade_maxima_horas: float | None = None) -> list[Oferta]:
    agora = agora or agora_utc()
    dados = next_data(html)
    try:
        itens = dados["props"]["pageProps"]["data"]["catalogServer"]["data"]
    except (KeyError, TypeError) as e:
        raise FonteErro(f"lista de produtos não encontrada (o HTML da página mudou?): {e}") from e
    if not itens:
        raise FonteErro("página veio sem produtos (resposta parcial ou HTML mudou)")

    ofertas = []
    for p in itens:
        if not p.get("available"):
            continue
        precos = [p.get("priceWithDiscount"), p.get("price")]
        oferta = p.get("offer") or {}
        relampago = False
        if oferta.get("priceWithDiscount") and oferta.get("endsAt"):
            termina = datetime.fromtimestamp(oferta["endsAt"], tz=timezone.utc)
            if termina > agora:
                precos.append(oferta["priceWithDiscount"])
                relampago = oferta["priceWithDiscount"] <= min(x for x in precos if x)
        precos = [float(x) for x in precos if x]
        if not precos:
            continue

        parcelas = valor = None
        sem_juros = False
        m = _PARCELA.search(p.get("maxInstallment") or "")
        if m:
            parcelas, valor = int(m.group(1)), _numero(m.group(2))
            # sem juros quando parcelas x valor bate com o preço no cartão
            sem_juros = parcelas > 1 and abs(parcelas * valor - float(p.get("price") or 0)) <= parcelas * 0.01 + 0.05

        ofertas.append(Oferta(
            loja=(p.get("sellerName") or "KaBuM!") + (" (oferta relâmpago)" if relampago else ""),
            titulo=(p.get("name") or "").strip(),
            preco_total=round(min(precos), 2),
            parcelas=parcelas,
            valor_parcela=valor,
            sem_juros=sem_juros,
            cupom=None,
            imagem=p.get("image") or None,
            link=f"{BASE}/produto/{p['code']}/{p.get('friendlyName', '')}".rstrip("/"),
            fonte=NOME,
        ))
    return ofertas
