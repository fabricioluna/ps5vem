"""Leitura e escrita do histórico em data/history.json.

Formato:
{
  "precos":  [{"id", "preco", "loja", "fonte", "ts"}],   # observações (últimos 30 dias)
  "menor_preco": {"preco", "loja", "link", "ts"} | null,  # menor preço já visto (nunca é podado)
  "alertas": {"<id>": {"preco", "nivel", "ts"}},          # último alerta enviado por oferta
  "falhas":  {"<fonte>": {"seguidas": int, "aviso_enviado": bool}},
  # usados pela página web (docs/index.html):
  "ultima_execucao": {"ts", "limites", "fontes": {...}, "itens": [...]},  # retrato da última verificação
  "ofertas": {"<id>": {"titulo", "loja", "fonte", "link", "primeiro_visto", "ultimo_visto",
                       "ultimo_preco", "menor_preco"}},   # catálogo de ofertas válidas vistas
  "alertas_enviados": [{"ts", "nivel", "preco", "loja", "titulo", "link"}]   # últimos 200
}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from models import Oferta, agora_utc

log = logging.getLogger(__name__)

RETENCAO_DIAS = 30
MAX_ALERTAS_LOG = 200
CAMINHO_PADRAO = Path(__file__).parent / "data" / "history.json"


def _vazio() -> dict:
    return {"precos": [], "menor_preco": None, "alertas": {}, "falhas": {},
            "ultima_execucao": None, "ofertas": {}, "alertas_enviados": []}


class Historico:
    def __init__(self, dados: dict | None = None, caminho: Path | None = None):
        self.caminho = caminho or CAMINHO_PADRAO
        base = _vazio()
        base.update(dados or {})
        self.dados = base

    # ---------- persistência ----------
    @classmethod
    def carregar(cls, caminho: Path | str | None = None) -> "Historico":
        caminho = Path(caminho) if caminho else CAMINHO_PADRAO
        if not caminho.exists():
            return cls(caminho=caminho)
        try:
            return cls(json.loads(caminho.read_text(encoding="utf-8")), caminho)
        except (json.JSONDecodeError, OSError) as e:
            log.error("Histórico ilegível (%s); começando do zero.", e)
            return cls(caminho=caminho)

    def salvar(self) -> None:
        self._podar()
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.caminho.write_text(
            json.dumps(self.dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _podar(self, agora: datetime | None = None) -> None:
        limite = (agora or agora_utc()) - timedelta(days=RETENCAO_DIAS)
        self.dados["precos"] = [p for p in self.dados["precos"] if _dt(p["ts"]) >= limite]
        self.dados["alertas"] = {k: v for k, v in self.dados["alertas"].items() if _dt(v["ts"]) >= limite}
        self.dados["ofertas"] = {k: v for k, v in self.dados["ofertas"].items() if _dt(v["ultimo_visto"]) >= limite}
        self.dados["alertas_enviados"] = self.dados["alertas_enviados"][-MAX_ALERTAS_LOG:]

    # ---------- preços ----------
    def registrar_preco(self, oferta: Oferta, agora: datetime | None = None) -> None:
        agora = agora or agora_utc()
        ultimos = [p for p in self.dados["precos"] if p["id"] == oferta.id]
        # evita inflar o arquivo: só grava se o preço mudou ou passou 1h
        if ultimos:
            u = ultimos[-1]
            if u["preco"] == oferta.preco_total and agora - _dt(u["ts"]) < timedelta(hours=1):
                return
        self.dados["precos"].append({
            "id": oferta.id, "preco": oferta.preco_total, "loja": oferta.loja,
            "fonte": oferta.fonte, "ts": agora.isoformat(timespec="seconds"),
        })
        menor = self.dados.get("menor_preco")
        if menor is None or oferta.preco_total < menor["preco"]:
            self.dados["menor_preco"] = {
                "preco": oferta.preco_total, "loja": oferta.loja, "link": oferta.link,
                "ts": agora.isoformat(timespec="seconds"),
            }

    def menor_preco(self) -> float | None:
        m = self.dados.get("menor_preco")
        return m["preco"] if m else None

    def media_recente(self, dias: int, agora: datetime | None = None) -> float | None:
        limite = (agora or agora_utc()) - timedelta(days=dias)
        valores = [p["preco"] for p in self.dados["precos"] if _dt(p["ts"]) >= limite]
        return sum(valores) / len(valores) if valores else None

    # ---------- alertas ----------
    def ultimo_alerta(self, oferta_id: str) -> dict | None:
        return self.dados["alertas"].get(oferta_id)

    def registrar_alerta(self, oferta: Oferta, nivel: str, agora: datetime | None = None) -> None:
        ts = (agora or agora_utc()).isoformat(timespec="seconds")
        self.dados["alertas"][oferta.id] = {"preco": oferta.preco_total, "nivel": nivel, "ts": ts}
        self.dados["alertas_enviados"].append({
            "ts": ts, "nivel": nivel, "preco": oferta.preco_total, "loja": oferta.loja,
            "titulo": oferta.titulo, "link": oferta.link, "fonte": oferta.fonte, "imagem": oferta.imagem,
        })

    # ---------- catálogo e retrato da execução (página web) ----------
    def registrar_vista(self, oferta: Oferta, agora: datetime | None = None) -> None:
        ts = (agora or agora_utc()).isoformat(timespec="seconds")
        o = self.dados["ofertas"].get(oferta.id)
        if o is None:
            o = self.dados["ofertas"][oferta.id] = {"primeiro_visto": ts, "menor_preco": oferta.preco_total}
        o.update({"titulo": oferta.titulo, "loja": oferta.loja, "fonte": oferta.fonte, "link": oferta.link,
                  "ultimo_visto": ts, "ultimo_preco": oferta.preco_total, "imagem": oferta.imagem,
                  "menor_preco": min(o["menor_preco"], oferta.preco_total)})

    def registrar_execucao(self, fontes: dict, itens: list[dict], limites: dict,
                           agora: datetime | None = None) -> None:
        self.dados["ultima_execucao"] = {
            "ts": (agora or agora_utc()).isoformat(timespec="seconds"),
            "fontes": fontes, "itens": itens, "limites": limites,
        }

    # ---------- saúde das fontes ----------
    def registrar_sucesso_fonte(self, fonte: str) -> None:
        self.dados["falhas"][fonte] = {"seguidas": 0, "aviso_enviado": False}

    def registrar_falha_fonte(self, fonte: str, limite: int) -> bool:
        """Soma uma falha. Devolve True se é hora de mandar o aviso de manutenção (uma única vez)."""
        f = self.dados["falhas"].setdefault(fonte, {"seguidas": 0, "aviso_enviado": False})
        f["seguidas"] += 1
        return f["seguidas"] >= limite and not f["aviso_enviado"]

    def marcar_aviso_manutencao(self, fonte: str) -> None:
        self.dados["falhas"][fonte]["aviso_enviado"] = True


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)
