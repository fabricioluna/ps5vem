"""Motor de regras: decide se uma oferta gera alerta normal, especial ou nenhum."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from models import Oferta
from storage import Historico

NENHUM, NORMAL, ESPECIAL = "nenhum", "normal", "especial"


@dataclass
class Decisao:
    nivel: str             # nenhum | normal | especial
    enviar: bool           # passou pelo anti-spam?
    menor_preco: bool      # menor preço já visto no histórico
    motivo: str


def hora_local(config: dict, agora: datetime) -> datetime:
    return agora.astimezone(ZoneInfo(config.get("fuso_horario", "America/Fortaleza")))


def dentro_do_periodo(config: dict, agora: datetime) -> bool:
    p = config.get("periodo") or {}
    hoje = hora_local(config, agora).date()
    inicio = date.fromisoformat(p["inicio"]) if p.get("inicio") else date.min
    fim = date.fromisoformat(p["fim"]) if p.get("fim") else date.max
    return inicio <= hoje <= fim


def preco_max_normal(config: dict, agora: datetime) -> float | None:
    """Preço máximo da primeira faixa de horário que contém a hora local (aceita faixas que viram a meia-noite)."""
    t = hora_local(config, agora).time().replace(second=0, microsecond=0)
    for f in config["alerta_normal"].get("faixas", []):
        das, ate = time.fromisoformat(f["das"]), time.fromisoformat(f["ate"])
        dentro = das <= t <= ate if das <= ate else (t >= das or t <= ate)
        if dentro:
            return float(f["preco_max"])
    return None


def _bate_normal(oferta: Oferta, config: dict, agora: datetime) -> tuple[bool, str]:
    cfg = config["alerta_normal"]
    limite = preco_max_normal(config, agora)
    if limite is None:
        return False, "nenhuma faixa de horário ativa"
    if oferta.preco_total > limite:
        return False, f"acima do limite normal (R$ {limite:.0f})"
    if cfg.get("exigir_sem_juros") and not oferta.sem_juros:
        return False, "não é sem juros"
    minimas = cfg.get("parcelas_minimas", 1)
    if minimas > 1:
        if oferta.parcelas is None:
            if not cfg.get("aceitar_parcelamento_nao_informado", True):
                return False, "parcelamento não informado"
        elif oferta.parcelas < minimas:
            return False, f"só {oferta.parcelas}x (mínimo {minimas}x)"
    return True, f"<= R$ {limite:.0f}"


def _bate_especial(oferta: Oferta, config: dict, hist: Historico, agora: datetime) -> tuple[bool, str]:
    cfg = config["alerta_especial"]
    if oferta.preco_total <= cfg["preco_max"]:
        return True, f"<= R$ {cfg['preco_max']} (super promoção)"
    queda = cfg.get("queda_percentual")
    media = hist.media_recente(cfg.get("janela_media_dias", 7), agora)
    if queda and media:
        pct = (1 - oferta.preco_total / media) * 100
        if pct >= queda:
            return True, f"{pct:.0f}% abaixo da média recente (R$ {media:.0f})"
    return False, ""


def _passa_anti_spam(oferta: Oferta, nivel: str, config: dict, hist: Historico, agora: datetime) -> tuple[bool, str]:
    ultimo = hist.ultimo_alerta(oferta.id)
    if ultimo is None:
        return True, "oferta nova"
    anti = config["anti_spam"]
    minutos = (agora - datetime.fromisoformat(ultimo["ts"])).total_seconds() / 60
    queda = ultimo["preco"] - oferta.preco_total
    if queda >= anti.get("avisar_so_se_preco_cair_mais", 0) and queda > 0:
        return True, f"preço caiu R$ {queda:.0f} desde o último aviso"
    if nivel == ESPECIAL:
        if ultimo["nivel"] != ESPECIAL:
            return True, "subiu para alerta especial"
        if minutos >= config["alerta_especial"].get("repetir_a_cada_minutos", 30):
            return True, "reenvio de alerta especial ainda ativo"
        return False, f"especial já avisado há {minutos:.0f} min"
    if minutos >= anti.get("nao_repetir_mesma_oferta_por_minutos", 180):
        return True, "janela anti-spam expirou"
    return False, f"já avisado há {minutos:.0f} min"


def avaliar(oferta: Oferta, config: dict, hist: Historico, agora: datetime) -> Decisao:
    """Chamar ANTES de registrar o preço da oferta no histórico."""
    menor = hist.menor_preco()
    eh_menor = menor is not None and oferta.preco_total < menor

    ok_esp, motivo_esp = _bate_especial(oferta, config, hist, agora)
    if ok_esp:
        nivel, motivo = ESPECIAL, motivo_esp
    else:
        ok_norm, motivo_norm = _bate_normal(oferta, config, agora)
        if not ok_norm:
            return Decisao(NENHUM, False, eh_menor, motivo_norm)
        nivel, motivo = NORMAL, motivo_norm

    enviar, motivo_spam = _passa_anti_spam(oferta, nivel, config, hist, agora)
    return Decisao(nivel, enviar, eh_menor, f"{motivo}; {motivo_spam}")
