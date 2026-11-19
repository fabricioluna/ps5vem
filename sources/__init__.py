"""Registro das fontes de preço. Para adicionar uma fonte: crie o módulo com NOME e buscar(),
inclua aqui e ative no config.yaml (fontes.<nome>.ativo)."""
from sources import buscape, kabum, pelando, promobit, zoom

FONTES = {m.NOME: m for m in (promobit, pelando, zoom, buscape, kabum)}
