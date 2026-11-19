"""Modelo de oferta compartilhado por todas as fontes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Oferta:
    loja: str
    titulo: str
    preco_total: float
    link: str
    fonte: str
    parcelas: int = 1
    valor_parcela: float | None = None
    sem_juros: bool = False
    cupom: str | None = None
    coletado_em: str = field(default_factory=lambda: agora_utc().isoformat(timespec="seconds"))

    @property
    def id(self) -> str:
        """Identificador estável: link sem query string nem fragmento."""
        p = urlsplit(self.link.strip())
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", ""))

    def to_dict(self) -> dict:
        return asdict(self)
