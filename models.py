"""Modelo de oferta compartilhado por todas as fontes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PARAMS_RASTREAMENTO = {"gclid", "fbclid", "ref", "tag", "src", "source", "_lc"}


def _rastreamento(chave: str) -> bool:
    chave = chave.lower()
    return chave.startswith("utm_") or chave in _PARAMS_RASTREAMENTO


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
    imagem: str | None = None   # foto do anúncio (usada só na página web)
    coletado_em: str = field(default_factory=lambda: agora_utc().isoformat(timespec="seconds"))

    @property
    def id(self) -> str:
        """Identificador estável: link sem fragmento e sem parâmetros de rastreamento (utm_*, etc.).
        Os demais parâmetros ficam, pois às vezes identificam a oferta (ex.: Zoom /lead?oid=123)."""
        p = urlsplit(self.link.strip())
        query = sorted((k, v) for k, v in parse_qsl(p.query) if not _rastreamento(k))
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(query), ""))

    def to_dict(self) -> dict:
        return asdict(self)
