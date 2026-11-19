"""Testes de integração do monitor.py, sem rede (fontes e notificador substituídos)."""
from datetime import datetime, timedelta, timezone

import pytest

import http_client
import monitor
import notifier
from http_client import FonteBloqueada, FonteErro
from models import Oferta
from storage import Historico

DENTRO = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)


class FonteFake:
    def __init__(self, nome, resultado):
        self.NOME, self.resultado = nome, resultado

    def buscar(self, cfg, idade_maxima_horas=None):
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


def of(preco, link="https://loja/1", titulo="PS5 Slim Digital + Astro Bot"):
    return Oferta(loja="Loja", titulo=titulo, preco_total=preco, link=link, fonte="fake")


@pytest.fixture
def ambiente(monkeypatch, tmp_path, config):
    enviados = []

    class NotFake(notifier.Notificador):
        def enviar(self, msg):
            enviados.append(msg)

    monkeypatch.setattr(monitor, "agora_utc", lambda: DENTRO)
    monkeypatch.setattr(monitor, "criar_notificador", lambda cfg, env=None: NotFake())
    for nome in ("a", "b"):
        config["fontes"][nome] = {"ativo": True}

    def rodar(fontes, dry_run=False, hist=None):
        monkeypatch.setattr(monitor, "FONTES", {f.NOME: f for f in fontes})
        hist = hist or Historico(caminho=tmp_path / "h.json")
        codigo = monitor.executar(config, hist, dry_run=dry_run)
        return codigo, hist

    return rodar, enviados, config, tmp_path


def test_fonte_quebrada_nao_derruba_execucao(ambiente):
    rodar, enviados, _, _ = ambiente
    codigo, hist = rodar([FonteFake("a", FonteBloqueada("HTTP 403")), FonteFake("b", [of(3900)])])
    assert codigo == 0
    assert len(enviados) == 1 and "3.899" not in enviados[0].titulo and "3.900" in enviados[0].titulo
    assert hist.dados["falhas"]["a"]["seguidas"] == 1


def test_aviso_de_manutencao_uma_unica_vez(ambiente):
    rodar, enviados, _, tmp = ambiente
    hist = Historico(caminho=tmp / "h.json")
    for _ in range(8):
        rodar([FonteFake("a", FonteErro("timeout"))], hist=hist)
    avisos = [m for m in enviados if "problema" in m.titulo]
    assert len(avisos) == 1 and "'a'" in avisos[0].titulo


def test_nao_repete_na_execucao_seguinte(ambiente):
    rodar, enviados, _, tmp = ambiente
    hist = Historico(caminho=tmp / "h.json")
    rodar([FonteFake("a", [of(3900)])], hist=hist)
    rodar([FonteFake("a", [of(3900)])], hist=hist)
    assert len(enviados) == 1


def test_dry_run_nao_envia_nem_grava(ambiente):
    rodar, enviados, _, tmp = ambiente
    codigo, _ = rodar([FonteFake("a", [of(3100)])], dry_run=True)
    assert codigo == 0 and enviados == []
    assert not (tmp / "h.json").exists()


def test_fora_do_periodo_nao_busca(ambiente, monkeypatch):
    rodar, enviados, config, _ = ambiente
    config["periodo"] = {"inicio": "2026-12-01", "fim": "2026-12-31"}
    chamada = FonteFake("a", AssertionError("não deveria buscar"))
    codigo, _ = rodar([chamada])
    assert codigo == 0 and enviados == []


def test_fonte_desativada_no_config(ambiente):
    rodar, enviados, config, _ = ambiente
    config["fontes"]["a"]["ativo"] = False
    rodar([FonteFake("a", [of(3900)])])
    assert enviados == []


def test_filtro_descarta_antes_de_alertar(ambiente):
    rodar, enviados, _, _ = ambiente
    rodar([FonteFake("a", [of(3100, titulo="PS5 Slim Digital Astro Bot Usado"), of(900, "https://l/2")])])
    assert enviados == []


def test_mudar_config_muda_comportamento(ambiente):
    rodar, enviados, config, _ = ambiente
    config["alerta_normal"]["faixas"] = [{"das": "00:00", "ate": "23:59", "preco_max": 3500}]
    rodar([FonteFake("a", [of(3900)])])
    assert enviados == []


def test_especial_tem_prioridade_urgente(ambiente):
    rodar, enviados, _, _ = ambiente
    rodar([FonteFake("a", [of(3150)])])
    assert enviados[0].prioridade == 5 and enviados[0].titulo.startswith("SUPER")


def test_sem_secret_retorna_erro_mas_grava_historico(ambiente, monkeypatch):
    rodar, enviados, _, tmp = ambiente

    def falha(cfg, env=None):
        raise notifier.NotificacaoErro("NTFY_TOPIC não definida")

    monkeypatch.setattr(monitor, "criar_notificador", falha)
    codigo, hist = rodar([FonteFake("a", [of(3900)])])
    assert codigo == 1
    assert (tmp / "h.json").exists() and hist.ultimo_alerta(of(3900).id) is None


# ---------- http_client: bloqueio não é burlado ----------
class R:
    def __init__(self, code, text=""):
        self.status_code, self.text, self.encoding = code, text, "utf-8"


def test_http_403_vira_fonte_bloqueada_sem_nova_tentativa(monkeypatch):
    chamadas = []
    monkeypatch.setattr(http_client, "permitido_pelo_robots", lambda url: True)
    monkeypatch.setattr(http_client, "_pausa", lambda: None)
    monkeypatch.setattr(http_client.requests, "get", lambda *a, **k: chamadas.append(1) or R(403))
    with pytest.raises(FonteBloqueada):
        http_client.baixar("https://exemplo.com/x")
    assert len(chamadas) == 1


def test_http_500_tenta_duas_vezes(monkeypatch):
    chamadas = []
    monkeypatch.setattr(http_client, "permitido_pelo_robots", lambda url: True)
    monkeypatch.setattr(http_client, "_pausa", lambda: None)
    monkeypatch.setattr(http_client.requests, "get", lambda *a, **k: chamadas.append(1) or R(500))
    with pytest.raises(FonteErro):
        http_client.baixar("https://exemplo.com/x")
    assert len(chamadas) == 2


def test_robots_proibido(monkeypatch):
    monkeypatch.setattr(http_client, "permitido_pelo_robots", lambda url: False)
    with pytest.raises(FonteBloqueada):
        http_client.baixar("https://exemplo.com/buscar")


def test_grava_retrato_da_execucao_para_pagina(ambiente):
    rodar, _, _, _ = ambiente
    _, hist = rodar([FonteFake("a", [of(3900), of(3100, "https://l/2", "PS5 Digital Astro Bot Usado")]),
                     FonteFake("b", FonteBloqueada("HTTP 403"))])
    ex = hist.dados["ultima_execucao"]
    assert ex["fontes"]["a"] == {"status": "ok", "anuncios": 2}
    assert ex["fontes"]["b"]["status"] == "bloqueada"
    assert ex["limites"] == {"normal": 4000.0, "especial": 3700, "parcelas_minimas": 10}
    validos = [i for i in ex["itens"] if i["valida"]]
    assert len(validos) == 1 and validos[0]["nivel"] == "normal" and validos[0]["alertar"]
    assert any(not i["valida"] and "usado" in i["motivo"] for i in ex["itens"])
    assert len(hist.dados["alertas_enviados"]) == 1
    assert of(3900).id in hist.dados["ofertas"]


def test_deduplica_mesma_oferta_em_fontes_diferentes():
    a = Oferta(loja="Amazon", titulo="Playstation 5 Slim Edição Digital 1TB", preco_total=4589.99,
               link="https://www.zoom.com.br/x", fonte="zoom")
    b = Oferta(loja="Amazon", titulo="Playstation 5 Slim Edição Digital 1TB", preco_total=4589.99,
               link="https://www.buscape.com.br/x", fonte="buscape")
    c = Oferta(loja="KaBuM!", titulo="Playstation 5 Slim Edição Digital 1TB", preco_total=4589.99,
               link="https://www.kabum.com.br/x", fonte="kabum")
    unicas = monitor.deduplicar([a, b, c])
    assert [o.fonte for o in unicas] == ["zoom", "kabum"]


def test_fonte_bloqueada_mantem_itens_recentes_na_pagina(ambiente):
    rodar, _, _, tmp = ambiente
    hist = Historico(caminho=tmp / "h.json")
    # execução anterior (ex.: no computador) viu uma oferta pela fonte "a", há 10 min
    hist.dados["ultima_execucao"] = {
        "ts": (DENTRO - timedelta(minutes=10)).isoformat(), "fontes": {}, "limites": {},
        "itens": [{"fonte": "a", "titulo": "PS5 Slim Digital", "preco_total": 3599.1, "valida": True, "link": "https://x"}],
    }
    rodar([FonteFake("a", FonteBloqueada("HTTP 403")), FonteFake("b", [of(3900)])], hist=hist)
    itens = hist.dados["ultima_execucao"]["itens"]
    herdado = [i for i in itens if i["fonte"] == "a"]
    assert len(herdado) == 1 and herdado[0]["visto_em"] == (DENTRO - timedelta(minutes=10)).isoformat()


def test_nao_herda_itens_antigos(ambiente):
    rodar, _, _, tmp = ambiente
    hist = Historico(caminho=tmp / "h.json")
    hist.dados["ultima_execucao"] = {
        "ts": (DENTRO - timedelta(minutes=45)).isoformat(), "fontes": {}, "limites": {},
        "itens": [{"fonte": "a", "titulo": "x", "preco_total": 3599.1, "valida": True, "link": "https://x"}],
    }
    rodar([FonteFake("a", FonteBloqueada("HTTP 403"))], hist=hist)
    assert not [i for i in hist.dados["ultima_execucao"]["itens"] if i["fonte"] == "a"]
