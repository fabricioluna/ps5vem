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
from pathlib import Path
from typing import Callable

import yaml

from filters import avaliar_qualidade
from http_client import FonteBloqueada
from models import Oferta, agora_utc
from notifier import (Mensagem, NotificacaoErro, brl, criar_notificador, formatar_alerta,
                      mensagem_manutencao, mensagem_teste)
from rules import NENHUM, Decisao, avaliar, dentro_do_periodo, hora_local
from sources import FONTES
from storage import Historico

log = logging.getLogger("monitor")
RAIZ = Path(__file__).parent


def carregar_config(caminho: Path) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


def coletar(config: dict, hist: Historico) -> tuple[list[Oferta], list[tuple[str, Mensagem]]]:
    """Consulta todas as fontes ativas. Uma fonte com erro nunca derruba as outras."""
    cfg_fontes = config.get("fontes") or {}
    limite_falhas = int(cfg_fontes.get("falhas_para_aviso_manutencao", 6))
    idade = cfg_fontes.get("idade_maxima_horas")
    ofertas: list[Oferta] = []
    avisos: list[tuple[str, Mensagem]] = []   # (fonte, aviso de manutenção)

    for nome, modulo in FONTES.items():
        cfg = cfg_fontes.get(nome) or {}
        if not cfg.get("ativo", False):
            log.info("[%s] desativada no config.yaml", nome)
            continue
        log.info("[%s] consultando...", nome)
        try:
            achadas = modulo.buscar(cfg, idade_maxima_horas=idade)
        except Exception as e:  # noqa: BLE001 - qualquer erro de fonte é isolado
            tipo = "BLOQUEADA" if isinstance(e, FonteBloqueada) else "ERRO"
            log.error("[%s] %s: %s", nome, tipo, e)
            if hist.registrar_falha_fonte(nome, limite_falhas):
                avisos.append((nome, mensagem_manutencao(nome, hist.dados["falhas"][nome]["seguidas"], str(e))))
            continue
        hist.registrar_sucesso_fonte(nome)
        log.info("[%s] %d anúncios encontrados", nome, len(achadas))
        ofertas.extend(achadas)
    return ofertas, avisos


def deduplicar(ofertas: list[Oferta]) -> list[Oferta]:
    por_id: dict[str, Oferta] = {}
    for o in ofertas:
        if o.id not in por_id or o.preco_total < por_id[o.id].preco_total:
            por_id[o.id] = o
    return sorted(por_id.values(), key=lambda o: o.preco_total)


def executar(config: dict, hist: Historico, dry_run: bool, env: dict | None = None) -> int:
    agora = agora_utc()
    log.info("Horário local: %s", hora_local(config, agora).strftime("%d/%m/%Y %H:%M"))
    if not dentro_do_periodo(config, agora):
        p = config.get("periodo", {})
        log.info("Fora do período configurado (%s a %s). Nada a fazer.", p.get("inicio"), p.get("fim"))
        return 0

    brutas, avisos = coletar(config, hist)
    ofertas = deduplicar(brutas)

    validas: list[Oferta] = []
    log.info("---- Filtro de qualidade (%d anúncios) ----", len(ofertas))
    for o in ofertas:
        ok, motivo = avaliar_qualidade(o, config)
        if ok:
            validas.append(o)
        else:
            log.info("  descartado  %-12s %-10s %s | %s", brl(o.preco_total), o.fonte, o.titulo[:70], motivo)

    # Decide tudo com base no histórico ANTERIOR a esta execução; só depois registra os preços.
    decisoes: list[tuple[Oferta, Decisao]] = [(o, avaliar(o, config, hist, agora)) for o in validas]
    for o, _ in decisoes:
        hist.registrar_preco(o, agora)

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
