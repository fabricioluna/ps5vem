"""Normalização de preço/texto e filtro de qualidade das ofertas."""
from __future__ import annotations

import re
import unicodedata

from models import Oferta

# "+ 10 jogos", "com 5 jogos", "+5 games": kits montados por revendedores
_KIT_JOGOS = re.compile(r"(?:\+|com)\s*(\d+)\s*(?:jogos|games)")
# "sem disco" / "sem leitor de disco" descreve a Edição Digital; não é motivo de rejeição
_CONSOLE = re.compile(r"\b(?:console|playstation\s*5|ps5)\b")
_CONTROLE = re.compile(r"\bcontroles?\b")
_SEM_DISCO = re.compile(r"\bsem\s+(?:leitor\s+(?:de\s+)?)?(?:disco|midia\s+fisica)\b")


def normalizar_texto(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def normalizar_preco(valor) -> float | None:
    """'R$ 4.029,00' -> 4029.0. Aceita número, '4.029', '4029.90', '3.599,9'."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    m = re.search(r"\d[\d.,]*", str(valor))
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if "," in s and "." in s:            # formato BR completo: 4.029,00
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                        # 4029,00
        s = s.replace(",", ".")
    elif "." in s:
        partes = s.split(".")
        if all(len(p) == 3 for p in partes[1:]):  # 4.029 ou 1.234.567 -> milhar
            s = s.replace(".", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _contem(texto: str, termo: str) -> bool:
    termo = normalizar_texto(termo)
    padrao = r"(?<![a-z0-9])" + re.escape(termo).replace(r"\ ", r"\s*") + r"(?![a-z0-9])"
    return re.search(padrao, texto) is not None


def avaliar_qualidade(oferta: Oferta, config: dict) -> tuple[bool, str]:
    """Devolve (aceita, motivo)."""
    prod = config["produto"]
    titulo = normalizar_texto(oferta.titulo)

    # cada item é uma palavra obrigatória, ou uma lista de alternativas (basta uma delas)
    for termo in prod.get("palavras_obrigatorias", []):
        opcoes = termo if isinstance(termo, list) else [termo]
        if not any(_contem(titulo, t) for t in opcoes):
            return False, f"falta '{' ou '.join(opcoes)}' no título"

    titulo_limpo = _SEM_DISCO.sub(" ", titulo)
    # "Console PS5 Digital ... + Controle DualSense": o controle acompanha o console.
    # Só conta como proibido quando o anúncio COMEÇA pelo controle ("Controle DualSense para PS5").
    console = _CONSOLE.search(titulo_limpo)
    if console:
        antes, depois = titulo_limpo[:console.start()], titulo_limpo[console.start():]
        titulo_limpo = antes + _CONTROLE.sub(" ", depois)
    for termo in prod.get("palavras_proibidas", []):
        if _contem(titulo_limpo, termo):
            return False, f"palavra proibida '{termo}'"

    kit = _KIT_JOGOS.search(titulo)
    if kit and int(kit.group(1)) >= 3:
        return False, f"kit com {kit.group(1)} jogos"

    minimo = prod.get("preco_minimo_valido", 1500)
    if oferta.preco_total is None or oferta.preco_total < minimo:
        return False, f"preço {oferta.preco_total} abaixo do mínimo válido ({minimo})"

    return True, "ok"
