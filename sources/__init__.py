"""Registro das fontes de preço. Para adicionar uma fonte: crie o módulo com NOME e buscar() e inclua aqui."""
from sources import pelando, promobit, zoom

FONTES = {m.NOME: m for m in (promobit, pelando, zoom)}
