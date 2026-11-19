import pytest

import notifier
from models import Oferta
from notifier import (Mensagem, NotificacaoErro, NtfyNotificador, TelegramNotificador, brl,
                      criar_notificador, formatar_alerta)


def of(**kw):
    base = dict(loja="Amazon", titulo="PS5 Slim Digital Astro Bot", preco_total=3899.0,
                link="https://loja.com/ps5", fonte="zoom", parcelas=12, valor_parcela=324.92, sem_juros=True)
    base.update(kw)
    return Oferta(**base)


class Resp:
    def __init__(self, code=200, text="ok"):
        self.status_code, self.text = code, text


def test_brl():
    assert brl(3899) == "R$ 3.899"
    assert brl(324.92) == "R$ 324,92"
    assert brl(4029.5) == "R$ 4.029,50"


def test_formato_mensagem_normal(config):
    m = formatar_alerta(of(), "normal", True, config)
    assert m.titulo == "PS5 Slim Digital: R$ 3.899"
    assert m.corpo.splitlines()[:4] == ["PS5 Slim Digital Astro Bot", "12x de R$ 324,92 sem juros",
                                        "Loja: Amazon | Cupom: nenhum", "Menor preço já visto!"]
    assert "https://loja.com/ps5" in m.corpo
    assert m.prioridade == 3 and m.link == "https://loja.com/ps5"


def test_formato_mensagem_especial(config):
    m = formatar_alerta(of(cupom="MELIMAIS200"), "especial", False, config)
    assert m.titulo.startswith("SUPER PROMOÇÃO!")
    assert m.prioridade == 5
    assert "Cupom: MELIMAIS200" in m.corpo
    assert "Menor preço" not in m.corpo


def test_prioridade_especial_configuravel(config):
    config["alerta_especial"]["prioridade"] = "alta"
    assert formatar_alerta(of(), "especial", False, config).prioridade == 4


def test_ntfy_envia_campos(monkeypatch):
    enviado = {}
    monkeypatch.setattr(notifier.requests, "post", lambda url, json, timeout: enviado.update(url=url, **json) or Resp())
    NtfyNotificador("topico-secreto").enviar(Mensagem("T", "C", 5, "https://x", ["a"]))
    assert enviado == {"url": "https://ntfy.sh", "topic": "topico-secreto", "title": "T", "message": "C",
                       "priority": 5, "tags": ["a"], "click": "https://x"}


def test_ntfy_erro_http(monkeypatch):
    monkeypatch.setattr(notifier.requests, "post", lambda *a, **k: Resp(500, "falhou"))
    with pytest.raises(NotificacaoErro):
        NtfyNotificador("t").enviar(Mensagem("T", "C"))


def test_telegram_envia_html(monkeypatch):
    enviado = {}
    monkeypatch.setattr(notifier.requests, "post", lambda url, json, timeout: enviado.update(url=url, **json) or Resp())
    TelegramNotificador("TOKEN", "123").enviar(Mensagem("PS5 <b>", "corpo", 5, "https://x"))
    assert enviado["url"] == "https://api.telegram.org/botTOKEN/sendMessage"
    assert enviado["chat_id"] == "123" and enviado["parse_mode"] == "HTML"
    assert "&lt;b&gt;" in enviado["text"] and 'href="https://x"' in enviado["text"]


def test_criar_notificador_pelo_config(config):
    assert isinstance(criar_notificador(config, {"NTFY_TOPIC": "abc"}), NtfyNotificador)
    config["notificacao"]["canal"] = "telegram"
    n = criar_notificador(config, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"})
    assert isinstance(n, TelegramNotificador)


def test_criar_notificador_sem_secret(config):
    with pytest.raises(NotificacaoErro):
        criar_notificador(config, {})
    config["notificacao"]["canal"] = "telegram"
    with pytest.raises(NotificacaoErro):
        criar_notificador(config, {"TELEGRAM_BOT_TOKEN": "t"})
