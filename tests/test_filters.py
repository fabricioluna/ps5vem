import pytest

from filters import avaliar_qualidade, normalizar_preco
from models import Oferta


@pytest.mark.parametrize("entrada,esperado", [
    ("R$ 4.029,00", 4029.0),
    ("R$4.029", 4029.0),
    ("3.599,9", 3599.9),
    ("4029,50", 4029.5),
    ("4029.50", 4029.5),
    ("R$ 1.234.567,89", 1234567.89),
    (3899, 3899.0),
    ("sem preço", None),
    (None, None),
])
def test_normalizar_preco(entrada, esperado):
    assert normalizar_preco(entrada) == esperado


def of(titulo, preco=3899.0):
    return Oferta(loja="L", titulo=titulo, preco_total=preco, link="https://x", fonte="t")


@pytest.mark.parametrize("titulo", [
    "Console PlayStation 5 Slim Edição Digital + Astro Bot",
    "PS5 Slim Digital + Pacote Astro Bot e Gran Turismo 7",
    "Console Sony PS5 Edicao Digital 1TB Pacote ASTRO BOT",
    "PlayStation 5 Digital sem leitor de disco + AstroBot",
])
def test_aceita_titulos_validos(config, titulo):
    ok, motivo = avaliar_qualidade(of(titulo), config)
    assert ok, motivo


@pytest.mark.parametrize("titulo,trecho", [
    ("Console PlayStation 5 Slim com Disco + Astro Bot", "astro"),   # falta 'digital'
    ("PS5 Slim Digital + God of War", "astro bot"),                  # falta astro bot
    ("PS5 Slim Digital Astro Bot Usado", "usado"),
    ("PS5 Slim Digital Astro Bot Open Box", "open box"),
    ("Controle DualSense Edição Digital Astro Bot", "controle"),
    ("PS5 Pro Digital + Astro Bot", "pro"),
    ("Capa protetora PS5 Digital Astro Bot", "capa"),
    ("PS5 Slim Digital Astro Bot + 10 jogos", "jogos"),
])
def test_rejeita_titulos_invalidos(config, titulo, trecho):
    ok, motivo = avaliar_qualidade(of(titulo), config)
    assert not ok
    assert trecho in motivo or "falta" in motivo


def test_rejeita_preco_absurdamente_baixo(config):
    ok, motivo = avaliar_qualidade(of("PS5 Slim Digital Astro Bot", 1499), config)
    assert not ok and "mínimo" in motivo


def test_palavras_vem_do_config(config):
    config["produto"]["palavras_proibidas"].append("magalu")
    ok, _ = avaliar_qualidade(of("PS5 Slim Digital Astro Bot Magalu"), config)
    assert not ok


def test_palavra_proibida_nao_casa_dentro_de_outra(config):
    # "pro" não pode rejeitar "produto" / "promoção"
    ok, motivo = avaliar_qualidade(of("Promoção PS5 Slim Digital Astro Bot produto oficial"), config)
    assert ok, motivo
