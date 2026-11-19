"""Testes dos parsers com HTML real salvo em tests/fixtures/ (coletado em 19/11/2026)."""
from datetime import datetime, timezone

import pytest

from filters import avaliar_qualidade
from http_client import FonteErro
from sources import buscape, kabum, pelando, promobit, zoom
from tests.conftest import fixture_text

AGORA = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)
CAMPOS = {"loja", "titulo", "preco_total", "parcelas", "valor_parcela", "sem_juros", "cupom", "imagem", "link", "fonte", "coletado_em"}


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
    assert havan.imagem.startswith("https://i.promobit.com.br/300/") and havan.imagem.endswith(".jpg")


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
    assert havan.imagem.startswith("https://media.pelando.com.br/") and "/0x300/" in havan.imagem
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
    assert o.imagem == "https://image.zst.com.br/D5CD8DD4A1A704B1CC4284D5C56968EA_235_235.jpg"
    assert o.link == "https://www.zoom.com.br/console-de-video-game/console-playstation-5-slim-825gb-sony-ps5-edicao-digital-bundle-4k"


def test_zoom_filtro(config):
    ofs = _validas(zoom.parse(fixture_text("zoom_busca.html")), config)
    titulos = [o.titulo for o in ofs]
    # 2 pacotes com Astro Bot + 3 consoles digitais (825GB, 1TB e edição de 30 anos)
    assert len(ofs) == 5
    assert all("digital" in t.lower() for t in titulos)
    assert any("astro bot" not in t.lower() for t in titulos)   # console sem jogos também entra
    # jogo avulso, controle, leitor de disco e suporte foram rejeitados
    assert not any("Leitor" in t or "Controle" in t or t.startswith("Jogo") for t in titulos)


# ---------- Buscapé (mesmo formato do Zoom) ----------
def test_buscape_parse(config):
    ofs = buscape.parse(fixture_text("buscape_busca.html"))
    assert len(ofs) == 8
    assert set(ofs[0].to_dict()) == CAMPOS
    assert all(o.fonte == "buscape" and o.link.startswith("https://www.buscape.com.br/") for o in ofs)
    validas = _validas(ofs, config)
    assert len(validas) == 4
    magalu = next(o for o in validas if o.loja == "Magazine Luiza")
    assert magalu.preco_total == 4179.05 and magalu.parcelas == 10 and magalu.valor_parcela == 439.9


# ---------- KaBuM ----------
def test_kabum_parse():
    ofs = kabum.parse(fixture_text("kabum_busca.html"), agora=AGORA)
    assert len(ofs) == 29
    assert set(ofs[0].to_dict()) == CAMPOS
    console = next(o for o in ofs if o.link.startswith("https://www.kabum.com.br/produto/1050570/"))
    assert console.preco_total == 4370.07          # preço à vista (Pix)
    assert console.parcelas == 10 and console.valor_parcela == 469.9
    assert console.sem_juros is True               # 10 x 469,90 = 4.699 = preço no cartão
    assert console.imagem.startswith("https://images.kabum.com.br/")


def test_kabum_oferta_relampago():
    ofs = kabum.parse(fixture_text("kabum_busca.html"), agora=AGORA)
    relampago = [o for o in ofs if "relâmpago" in o.loja]
    assert relampago and all(o.cupom is None for o in relampago)
    # depois que a oferta relâmpago termina, o preço dela deixa de valer
    depois = kabum.parse(fixture_text("kabum_busca.html"), agora=datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert not any("relâmpago" in o.loja for o in depois)


def test_kabum_filtro(config):
    titulos = [o.titulo for o in _validas(kabum.parse(fixture_text("kabum_busca.html"), agora=AGORA), config)]
    assert len(titulos) == 3
    # o console que vem com "Controle DualSense" no título passa; tampas, suportes e leitor de disco não
    assert any(t.startswith("Console Sony PlayStation 5 Edição Digital Slim") for t in titulos)
    assert not any(t.startswith(("Tampa", "Suporte", "Leitor")) for t in titulos)


def test_kabum_html_quebrado():
    with pytest.raises(FonteErro):
        kabum.parse('<script id="__NEXT_DATA__">{"props": {}}</script>')


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
