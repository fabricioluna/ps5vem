"""Envio de notificações. Interface única (Notificador.enviar) com ntfy (padrão) e Telegram.

Segredos vêm só de variáveis de ambiente:
  ntfy:     NTFY_TOPIC
  telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass, field

import requests

from models import Oferta

log = logging.getLogger(__name__)

PRIORIDADES = {"minima": 1, "baixa": 2, "normal": 3, "alta": 4, "urgente": 5}


class NotificacaoErro(Exception):
    pass


@dataclass
class Mensagem:
    titulo: str
    corpo: str
    prioridade: int = 3           # 1..5 (escala do ntfy)
    link: str | None = None
    tags: list[str] = field(default_factory=list)


# ---------------- formatação ----------------
def brl(valor: float) -> str:
    """3899 -> 'R$ 3.899'; 324.92 -> 'R$ 324,92'."""
    if float(valor).is_integer():
        s = f"{int(valor):,}".replace(",", ".")
    else:
        s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def formatar_alerta(oferta: Oferta, nivel: str, menor_preco: bool, config: dict) -> Mensagem:
    nome = config["produto"]["nome"]
    titulo = f"{nome}: {brl(oferta.preco_total)}"
    if nivel == "especial":
        titulo = f"SUPER PROMOÇÃO! {titulo}"

    # o título do anúncio diz se é só o console ou um pacote com jogos
    linhas = [oferta.titulo if len(oferta.titulo) <= 90 else oferta.titulo[:87] + "..."]
    if oferta.parcelas and oferta.parcelas > 1:
        valor = oferta.valor_parcela or oferta.preco_total / oferta.parcelas
        linhas.append(f"{oferta.parcelas}x de {brl(round(valor, 2))}" + (" sem juros" if oferta.sem_juros else ""))
    else:
        linhas.append("Parcelamento não informado")
    linhas.append(f"Loja: {oferta.loja} | Cupom: {oferta.cupom or 'nenhum'}")
    if menor_preco:
        linhas.append("Menor preço já visto!")
    linhas.append(f"(via {oferta.fonte}) {oferta.link}")

    if nivel == "especial":
        prioridade = PRIORIDADES.get(str(config["alerta_especial"].get("prioridade", "urgente")).lower(), 5)
        tags = ["rotating_light", "video_game"]
    else:
        prioridade, tags = 3, ["video_game"]
    if menor_preco:
        tags.append("chart_with_downwards_trend")
    return Mensagem(titulo, "\n".join(linhas), prioridade, oferta.link, tags)


def mensagem_manutencao(fonte: str, falhas: int, erro: str) -> Mensagem:
    return Mensagem(
        titulo=f"Monitor PS5: fonte '{fonte}' com problema",
        corpo=f"A fonte {fonte} falhou {falhas} vezes seguidas.\nÚltimo erro: {erro}\n"
              "Pode ser bloqueio ou mudança no site. Este aviso não será repetido até ela voltar a funcionar.",
        prioridade=2, tags=["wrench"],
    )


def mensagem_teste() -> Mensagem:
    return Mensagem(
        titulo="Monitor PS5: notificação de teste",
        corpo="Se você está lendo isto, as notificações estão funcionando.",
        prioridade=3, link="https://ntfy.sh", tags=["white_check_mark"],
    )


# ---------------- canais ----------------
class Notificador:
    def enviar(self, msg: Mensagem) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class NtfyNotificador(Notificador):
    def __init__(self, topico: str, servidor: str = "https://ntfy.sh"):
        self.topico, self.servidor = topico, servidor.rstrip("/")

    def enviar(self, msg: Mensagem) -> None:
        # Publicação em JSON (POST na raiz do servidor): equivale aos cabeçalhos Title/Priority/Tags/Click
        # e aceita acentos e emojis sem problema de codificação de cabeçalho HTTP.
        payload = {"topic": self.topico, "title": msg.titulo, "message": msg.corpo,
                   "priority": msg.prioridade, "tags": msg.tags}
        if msg.link:
            payload["click"] = msg.link
        r = requests.post(self.servidor, json=payload, timeout=15)
        if r.status_code >= 400:
            raise NotificacaoErro(f"ntfy respondeu HTTP {r.status_code}: {r.text[:200]}")


class TelegramNotificador(Notificador):
    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, chat_id

    def enviar(self, msg: Mensagem) -> None:
        texto = f"<b>{html.escape(msg.titulo)}</b>\n{html.escape(msg.corpo)}"
        if msg.link:
            texto += f'\n<a href="{html.escape(msg.link, quote=True)}">Abrir oferta</a>'
        r = requests.post(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            json={"chat_id": self.chat_id, "text": texto, "parse_mode": "HTML",
                  "disable_notification": msg.prioridade <= 2},
            timeout=15,
        )
        if r.status_code >= 400:
            # não loga a URL: ela contém o token
            raise NotificacaoErro(f"Telegram respondeu HTTP {r.status_code}: {r.text[:200]}")


def criar_notificador(config: dict, env: dict | None = None) -> Notificador:
    env = os.environ if env is None else env
    cfg = config.get("notificacao") or {}
    canal = str(cfg.get("canal", "ntfy")).lower()
    if canal == "ntfy":
        topico = env.get("NTFY_TOPIC", "").strip()
        if not topico:
            raise NotificacaoErro("variável de ambiente NTFY_TOPIC não definida")
        return NtfyNotificador(topico, cfg.get("ntfy_servidor", "https://ntfy.sh"))
    if canal == "telegram":
        token, chat = env.get("TELEGRAM_BOT_TOKEN", "").strip(), env.get("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat:
            raise NotificacaoErro("TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID precisam estar definidos")
        return TelegramNotificador(token, chat)
    raise NotificacaoErro(f"canal de notificação desconhecido: {canal}")
