"""Monitor de ofertas do PS5 Slim Digital + Astro Bot.

Uso:
  python monitor.py              # execução normal (GitHub Actions)
  python monitor.py --dry-run    # busca e mostra o que enviaria; não notifica nem grava histórico
  python monitor.py --test-notify  # manda uma notificação de teste
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from filters import avaliar_qualidade, normalizar_texto
from http_client import FonteBloqueada
from models import Oferta, agora_utc
from notifier import (Mensagem, NotificacaoErro, brl, criar_notificador, formatar_alerta,
                      mensagem_manutencao, mensagem_teste)
from rules import NENHUM, Decisao, avaliar, dentro_do_periodo, hora_local, preco_max_normal
from sources import FONTES
from storage import Historico

log = logging.getLogger("monitor")
RAIZ = Path(__file__).parent


def carregar_config(caminho: Path) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


def coletar(config: dict, hist: Historico) -> tuple[list[Oferta], list[tuple[str, Mensagem]], dict]:
    """Consulta todas as fontes ativas. Uma fonte com erro nunca derruba as outras.
    Devolve (ofertas, avisos de manutenção, status por fonte)."""
    cfg_fontes = config.get("fontes") or {}
    limite_falhas = int(cfg_fontes.get("falhas_para_aviso_manutencao", 6))
    idade = cfg_fontes.get("idade_maxima_horas")
    ofertas: list[Oferta] = []
    avisos: list[tuple[str, Mensagem]] = []   # (fonte, aviso de manutenção)
    status: dict[str, dict] = {}

    for nome, modulo in FONTES.items():
        cfg = cfg_fontes.get(nome) or {}
        if not cfg.get("ativo", False):
            log.info("[%s] desativada no config.yaml", nome)
            status[nome] = {"status": "desativada"}
            continue
        log.info("[%s] consultando...", nome)
        try:
            achadas = modulo.buscar(cfg, idade_maxima_horas=idade)
        except Exception as e:  # noqa: BLE001 - qualquer erro de fonte é isolado
            tipo = "BLOQUEADA" if isinstance(e, FonteBloqueada) else "ERRO"
            log.error("[%s] %s: %s", nome, tipo, e)
            status[nome] = {"status": tipo.lower(), "erro": str(e)[:200]}
            if hist.registrar_falha_fonte(nome, limite_falhas):
                avisos.append((nome, mensagem_manutencao(nome, hist.dados["falhas"][nome]["seguidas"], str(e))))
            continue
        hist.registrar_sucesso_fonte(nome)
        log.info("[%s] %d anúncios encontrados", nome, len(achadas))
        status[nome] = {"status": "ok", "anuncios": len(achadas)}
        ofertas.extend(achadas)
    return ofertas, avisos, status


def deduplicar(ofertas: list[Oferta]) -> list[Oferta]:
    """Remove repetidos: mesmo link, ou mesma loja + mesmo título + mesmo preço vindo de fontes
    diferentes (Zoom e Buscapé mostram as mesmas ofertas). Fica a primeira fonte da lista."""
    por_id: dict[str, Oferta] = {}
    for o in ofertas:
        if o.id not in por_id or o.preco_total < por_id[o.id].preco_total:
            por_id[o.id] = o
    unicas: dict[tuple, Oferta] = {}
    for o in por_id.values():
        chave = (normalizar_texto(o.titulo), normalizar_texto(o.loja), o.preco_total)
        unicas.setdefault(chave, o)
    return sorted(unicas.values(), key=lambda o: o.preco_total)


def _itens_execucao(ofertas: list[Oferta], decisoes: list[tuple[Oferta, Decisao]],
                    descartes: dict[str, str]) -> list[dict]:
    """Retrato de cada anúncio desta execução, para a página web."""
    por_id = {o.id: d for o, d in decisoes}
    itens = []
    for o in ofertas:
        item = {k: v for k, v in o.to_dict().items() if k != "coletado_em"}
        d = por_id.get(o.id)
        if d is None:
            item.update(valida=False, motivo=descartes.get(o.id, ""))
        else:
            item.update(valida=True, nivel=d.nivel, alertar=d.enviar, menor_preco=d.menor_preco, motivo=d.motivo)
        itens.append(item)
    return itens


HERANCA_MINUTOS = 30


def _herdar_itens(hist: Historico, status_fontes: dict, agora) -> list[dict]:
    """Se uma fonte falhou agora (ex.: Pelando bloqueia o GitHub), mantém na página o que ela mostrou
    na execução anterior, desde que tenha sido há menos de 30 min (ex.: rodando no seu computador)."""
    anterior = hist.dados.get("ultima_execucao") or {}
    if not anterior.get("ts"):
        return []
    idade = (agora - datetime.fromisoformat(anterior["ts"])).total_seconds() / 60
    if idade > HERANCA_MINUTOS:
        return []
    falharam = {nome for nome, s in status_fontes.items() if s.get("status") not in ("ok", "desativada")}
    herdados = []
    for item in anterior.get("itens", []):
        if item.get("fonte") in falharam:
            herdados.append({**item, "visto_em": item.get("visto_em") or anterior["ts"]})
    return herdados


def _limites(config: dict, agora) -> dict:
    return {"normal": preco_max_normal(config, agora), "especial": config["alerta_especial"]["preco_max"],
            "parcelas_minimas": config["alerta_normal"].get("parcelas_minimas", 1)}


def executar(config: dict, hist: Historico, dry_run: bool, env: dict | None = None) -> int:
    agora = agora_utc()
    log.info("Horário local: %s", hora_local(config, agora).strftime("%d/%m/%Y %H:%M"))
    if not dentro_do_periodo(config, agora):
        p = config.get("periodo", {})
        log.info("Fora do período configurado (%s a %s). Nada a fazer.", p.get("inicio"), p.get("fim"))
        return 0

    brutas, avisos, status_fontes = coletar(config, hist)
    ofertas = deduplicar(brutas)

    validas: list[Oferta] = []
    descartes: dict[str, str] = {}
    log.info("---- Filtro de qualidade (%d anúncios) ----", len(ofertas))
    for o in ofertas:
        ok, motivo = avaliar_qualidade(o, config)
        if ok:
            validas.append(o)
        else:
            descartes[o.id] = motivo
            log.info("  descartado  %-12s %-10s %s | %s", brl(o.preco_total), o.fonte, o.titulo[:70], motivo)

    # Decide tudo com base no histórico ANTERIOR a esta execução; só depois registra os preços.
    decisoes: list[tuple[Oferta, Decisao]] = [(o, avaliar(o, config, hist, agora)) for o in validas]
    for o, _ in decisoes:
        hist.registrar_preco(o, agora)
        hist.registrar_vista(o, agora)

    log.info("---- Decisões (%d ofertas válidas) ----", len(decisoes))
    # cada envio leva a ação a registrar no histórico se a notificação sair com sucesso
    envios: list[tuple[Mensagem, Callable[[], None]]] = []
    for o, d in decisoes:
        acao = "ENVIAR" if d.enviar else ("segurar" if d.nivel != NENHUM else "-")
        log.info("  %-8s %-8s %-12s %-14s %-9s %s | %s", d.nivel.upper(), acao, brl(o.preco_total),
                 o.loja[:14], o.fonte, o.titulo[:60], d.motivo)
        if d.enviar:
            envios.append((formatar_alerta(o, d.nivel, d.menor_preco, config),
                           lambda o=o, n=d.nivel: hist.registrar_alerta(o, n, agora)))
    envios += [(m, lambda f=fonte: hist.marcar_aviso_manutencao(f)) for fonte, m in avisos]

    if not envios:
        log.info("Nenhuma notificação a enviar.")
    codigo = 0
    if dry_run:
        for msg, _ in envios:
            log.info("[dry-run] enviaria (prioridade %d):\n  %s\n  %s", msg.prioridade, msg.titulo,
                     msg.corpo.replace("\n", "\n  "))
        log.info("[dry-run] histórico NÃO foi gravado.")
        return 0

    if envios:
        try:
            notificador = criar_notificador(config, env)
        except NotificacaoErro as e:
            log.error("Não foi possível configurar a notificação: %s", e)
            notificador, codigo = None, 1
        for msg, registrar in envios:
            if notificador is None:
                break
            try:
                notificador.enviar(msg)
                log.info("Notificação enviada: %s", msg.titulo)
                registrar()
            except Exception as e:  # noqa: BLE001
                log.error("Falha ao enviar notificação '%s': %s", msg.titulo, e)
                codigo = 1

    itens = _itens_execucao(ofertas, decisoes, descartes) + _herdar_itens(hist, status_fontes, agora)
    hist.registrar_execucao(status_fontes, itens, _limites(config, agora), agora)
    hist.salvar()
    log.info("Histórico gravado em %s", hist.caminho)
    return codigo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor de ofertas do PS5 Slim Digital + Astro Bot")
    parser.add_argument("--dry-run", action="store_true", help="busca e mostra o que enviaria, sem notificar nem gravar")
    parser.add_argument("--test-notify", action="store_true", help="envia uma notificação de teste e sai")
    parser.add_argument("--config", default=str(RAIZ / "config.yaml"), help="caminho do config.yaml")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout)

    config = carregar_config(Path(args.config))

    if args.test_notify:
        try:
            criar_notificador(config).enviar(mensagem_teste())
        except Exception as e:  # noqa: BLE001
            log.error("Notificação de teste falhou: %s", e)
            return 1
        log.info("Notificação de teste enviada pelo canal '%s'.", config.get("notificacao", {}).get("canal", "ntfy"))
        return 0

    return executar(config, Historico.carregar(), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
