from datetime import datetime, timedelta, timezone

from models import Oferta
from rules import ESPECIAL, NENHUM, NORMAL, avaliar, dentro_do_periodo, preco_max_normal
from storage import Historico

# 15:00 UTC = 12:00 em Fortaleza (UTC-3)
T0 = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)


def of(preco, link="https://loja.com/ps5", parcelas=12, sem_juros=True):
    return Oferta(loja="Loja", titulo="PS5 Slim Digital Astro Bot", preco_total=preco, link=link,
                  fonte="t", parcelas=parcelas, valor_parcela=round(preco / parcelas, 2), sem_juros=sem_juros)


# ---------- período ----------
def test_dentro_do_periodo(config):
    assert dentro_do_periodo(config, T0)


def test_fora_do_periodo(config):
    assert not dentro_do_periodo(config, datetime(2026, 12, 1, 12, tzinfo=timezone.utc))
    assert not dentro_do_periodo(config, datetime(2026, 11, 18, 12, tzinfo=timezone.utc))


def test_periodo_usa_fuso_horario(config):
    # 01/12 02:00 UTC ainda é 30/11 23:00 em Fortaleza
    assert dentro_do_periodo(config, datetime(2026, 12, 1, 2, tzinfo=timezone.utc))


# ---------- alerta normal ----------
def test_normal_bate_limite(config):
    d = avaliar(of(3999), config, Historico(), T0)
    assert d.nivel == NORMAL and d.enviar


def test_normal_acima_do_limite(config):
    assert avaliar(of(4001), config, Historico(), T0).nivel == NENHUM


def test_faixas_por_horario(config):
    config["alerta_normal"]["faixas"] = [
        {"das": "08:00", "ate": "17:59", "preco_max": 3800},
        {"das": "18:00", "ate": "07:59", "preco_max": 4100},  # vira a meia-noite
    ]
    assert preco_max_normal(config, T0) == 3800                              # 12h local
    assert preco_max_normal(config, T0 + timedelta(hours=10)) == 4100        # 22h local
    assert preco_max_normal(config, T0 + timedelta(hours=15)) == 4100        # 03h local
    assert avaliar(of(3900), config, Historico(), T0).nivel == NENHUM
    assert avaliar(of(3900), config, Historico(), T0 + timedelta(hours=10)).nivel == NORMAL


def test_exigir_sem_juros(config):
    config["alerta_normal"]["exigir_sem_juros"] = True
    assert avaliar(of(3900, sem_juros=False), config, Historico(), T0).nivel == NENHUM
    assert avaliar(of(3900, sem_juros=True), config, Historico(), T0).nivel == NORMAL


def test_parcelas_minimas(config):
    config["alerta_normal"]["parcelas_minimas"] = 12
    assert avaliar(of(3900, parcelas=10), config, Historico(), T0).nivel == NENHUM
    assert avaliar(of(3900, parcelas=12), config, Historico(), T0).nivel == NORMAL


# ---------- alerta especial ----------
def test_especial_por_preco_max(config):
    d = avaliar(of(3200), config, Historico(), T0)
    assert d.nivel == ESPECIAL and d.enviar


def test_especial_por_queda_percentual(config):
    config["alerta_especial"]["preco_max"] = 1000
    h = Historico()
    for i in range(3):
        h.registrar_preco(of(4500, f"https://l/{i}"), T0 - timedelta(days=1))
    # 3500 é 22% abaixo de 4500
    d = avaliar(of(3500), config, h, T0)
    assert d.nivel == ESPECIAL and "média" in d.motivo
    # 3700 é só 18% abaixo -> normal
    assert avaliar(of(3700), config, h, T0).nivel == NORMAL


def test_queda_percentual_configuravel(config):
    config["alerta_especial"]["preco_max"] = 1000
    config["alerta_especial"]["queda_percentual"] = 10
    h = Historico()
    h.registrar_preco(of(4500, "https://l/a"), T0 - timedelta(days=1))
    assert avaliar(of(3900), config, h, T0).nivel == ESPECIAL


def test_especial_reenvia_a_cada_x_minutos(config):
    h = Historico()
    o = of(3100)
    h.registrar_alerta(o, ESPECIAL, T0)
    assert not avaliar(o, config, h, T0 + timedelta(minutes=29)).enviar
    assert avaliar(o, config, h, T0 + timedelta(minutes=30)).enviar
    config["alerta_especial"]["repetir_a_cada_minutos"] = 60
    assert not avaliar(o, config, h, T0 + timedelta(minutes=30)).enviar


def test_normal_que_vira_especial_reenvia_na_hora(config):
    h = Historico()
    h.registrar_alerta(of(3900), NORMAL, T0)
    d = avaliar(of(3190), config, h, T0 + timedelta(minutes=1))
    assert d.nivel == ESPECIAL and d.enviar


# ---------- anti-spam ----------
def test_nao_repete_mesma_oferta(config):
    h = Historico()
    h.registrar_alerta(of(3900), NORMAL, T0)
    assert not avaliar(of(3900), config, h, T0 + timedelta(minutes=179)).enviar
    assert avaliar(of(3900), config, h, T0 + timedelta(minutes=180)).enviar


def test_janela_anti_spam_configuravel(config):
    config["anti_spam"]["nao_repetir_mesma_oferta_por_minutos"] = 30
    h = Historico()
    h.registrar_alerta(of(3900), NORMAL, T0)
    assert avaliar(of(3900), config, h, T0 + timedelta(minutes=31)).enviar


def test_reenvia_se_preco_cair_mais_que_x(config):
    h = Historico()
    h.registrar_alerta(of(3900), NORMAL, T0)
    assert not avaliar(of(3860), config, h, T0 + timedelta(minutes=5)).enviar   # caiu 40
    assert avaliar(of(3850), config, h, T0 + timedelta(minutes=5)).enviar       # caiu 50
    config["anti_spam"]["avisar_so_se_preco_cair_mais"] = 100
    assert not avaliar(of(3850), config, h, T0 + timedelta(minutes=5)).enviar


# ---------- menor preço ----------
def test_menor_preco_ja_visto(config):
    h = Historico()
    h.registrar_preco(of(3950, "https://outra"), T0 - timedelta(hours=2))
    assert avaliar(of(3900), config, h, T0).menor_preco
    assert not avaliar(of(3990), config, h, T0).menor_preco


def test_historico_vazio_nao_marca_menor_preco(config):
    assert not avaliar(of(3900), config, Historico(), T0).menor_preco
