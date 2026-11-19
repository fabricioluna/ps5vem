"""Testes dos parsers com HTML real salvo em tests/fixtures/ (coletado em 19/11/2026)."""
from datetime import datetime, timezone

import pytest

from filters import avaliar_qualidade
from http_client import FonteErro
from sources import pelando, promobit, zoom
from tests.conftest import fixture_text

AGORA = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)
CAMPOS = {"loja", "titulo", "preco_total", "parcelas", "valor_parcela", "sem_juros", "cupom", "link", "fonte", "coletado_em"}


def _validas(ofertas, config):
    return [o for o in ofertas if avaliar_qualidade(o, config)[0]]


# ---------- Promobit ----------
def test_promobit_parse():
    ofs = promobit.parse(fixture_text("promobit_playstation5.html"), agora=AGORA)
    assert len(ofs) == 12
    assert set(ofs[0].to_dict()) == CAMPOS
    havan = next(o for o in ofs if o.loja == "Havan")
    assert havan.preco_total == 3799.99
    assert "Slim Digital" in havan.titulo
    assert havan.link.startswith("https://www.promobit.com.br/oferta/playstation-5-slim-digital-825gb")
    assert havan.fonte == "promobit"


def test_promobit_filtro_deixa_so_o_ps5_digital(config):
    ofs = _validas(promobit.parse(fixture_text("promobit_playstation5.html"), agora=AGORA), config)
    assert [o.loja for o in ofs] == ["Havan"]   # jogos, faceplate e versão com disco caem


def test_promobit_idade_maxima():
    # AGORA = 15:00 em Brasília; com 2h só ficam as publicadas depois das 13:00 (14:24, 14:14, 13:30)
    ofs = promobit.parse(fixture_text("promobit_playstation5.html"), agora=AGORA, idade_maxima_horas=2)
    assert len(ofs) == 3
    assert "Havan" in [o.loja for o in ofs]


def test_promobit_html_quebrado():
    with pytest.raises(FonteErro):
        promobit.parse("<html><body>mudou</body></html>")


# ---------- Pelando ----------
def test_pelando_ignora_expiradas():
    # todas as ofertas da fixture estavam expiradas no momento da coleta
    assert pelando.parse(fixture_text("pelando_busca.html"), agora=AGORA) == []


def test_pelando_parse_ativa(config):
    html = fixture_text("pelando_busca.html").replace("&quot;expired&quot;", "&quot;active&quot;")
    ofs = pelando.parse(html, agora=AGORA)
    assert len(ofs) == 20
    assert set(ofs[0].to_dict()) == CAMPOS
    havan = ofs[0]
    assert havan.loja == "Havan" and havan.preco_total == 3799.0
    assert havan.link == ("https://www.pelando.com.br/d/lojas-fisicas-parcelado-playstation-5-slim-digital"
                          "-825gb-pacote-astro-bot-e-gran-turismo-7-5f4d")
    assert len(_validas(ofs, config)) >= 3


def test_pelando_html_quebrado():
    with pytest.raises(FonteErro):
        pelando.parse("<html></html>")


# ---------- Zoom ----------
def test_zoom_parse():
    ofs = zoom.parse(fixture_text("zoom_busca.html"))
    assert len(ofs) == 18
    assert set(ofs[0].to_dict()) == CAMPOS
    o = ofs[0]
    assert o.preco_total == 4184.07
    assert o.loja == "KaBuM!"
    assert o.parcelas == 10 and o.valor_parcela == 449.9 and o.sem_juros is False
    assert o.link == "https://www.zoom.com.br/console-de-video-game/console-playstation-5-slim-825gb-sony-ps5-edicao-digital-bundle-4k"


def test_zoom_filtro(config):
    ofs = _validas(zoom.parse(fixture_text("zoom_busca.html")), config)
    titulos = [o.titulo for o in ofs]
    assert len(ofs) == 2
    assert all("astro bot" in t.lower() and "digital" in t.lower() for t in titulos)
    # jogo avulso, controle, leitor de disco e suporte foram rejeitados
    assert not any("Leitor" in t or "Controle" in t or t.startswith("Jogo") for t in titulos)


def test_zoom_html_quebrado():
    with pytest.raises(FonteErro):
        zoom.parse("<html></html>")


@pytest.mark.parametrize("modulo,arquivo,vazio", [
    (promobit, "promobit_playstation5.html", ('"before":2771067,"offers":[', '"before":2771067,"offers":[],"_x":[')),
    (zoom, "zoom_busca.html", ('"hits":[', '"hits":[],"_x":[')),
])
def test_listagem_vazia_conta_como_falha(modulo, arquivo, vazio):
    html = fixture_text(arquivo).replace(*vazio, 1)
    with pytest.raises(FonteErro):
        modulo.parse(html)


def test_pelando_listagem_vazia_conta_como_falha():
    html = fixture_text("pelando_busca.html")
    i = html.index("&quot;deals&quot;:[1,[")
    html = html[:i] + "&quot;deals&quot;:[1,[]],&quot;_x&quot;:[1,[" + html[i + len("&quot;deals&quot;:[1,["):]
    with pytest.raises(FonteErro):
        pelando.parse(html)
