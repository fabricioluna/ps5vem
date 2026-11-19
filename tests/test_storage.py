from datetime import datetime, timedelta, timezone

from models import Oferta
from storage import Historico

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def of(preco, link="https://loja.com/ps5?utm=x"):
    return Oferta(loja="Loja", titulo="PS5 Digital Astro Bot", preco_total=preco, link=link, fonte="teste")


def test_id_ignora_query_string():
    assert of(1, "https://Loja.com/ps5/?a=1#x").id == "https://loja.com/ps5"


def test_salvar_e_carregar(tmp_path):
    h = Historico(caminho=tmp_path / "h.json")
    h.registrar_preco(of(4000), agora=datetime.now(timezone.utc))
    h.salvar()
    h2 = Historico.carregar(tmp_path / "h.json")
    assert h2.menor_preco() == 4000
    assert len(h2.dados["precos"]) == 1


def test_arquivo_corrompido_vira_historico_vazio(tmp_path):
    p = tmp_path / "h.json"
    p.write_text("{quebrado", encoding="utf-8")
    assert Historico.carregar(p).dados["precos"] == []


def test_nao_duplica_preco_igual_em_menos_de_1h():
    h = Historico()
    h.registrar_preco(of(4000), T0)
    h.registrar_preco(of(4000), T0 + timedelta(minutes=10))
    h.registrar_preco(of(3900), T0 + timedelta(minutes=20))
    assert [p["preco"] for p in h.dados["precos"]] == [4000, 3900]
    assert h.menor_preco() == 3900


def test_media_recente_respeita_janela():
    h = Historico()
    h.registrar_preco(of(5000, "https://a"), T0 - timedelta(days=10))
    h.registrar_preco(of(4000, "https://b"), T0 - timedelta(days=1))
    h.registrar_preco(of(4200, "https://c"), T0)
    assert h.media_recente(7, T0) == 4100


def test_falhas_avisam_uma_unica_vez():
    h = Historico()
    avisos = [h.registrar_falha_fonte("zoom", 6) for _ in range(5)]
    assert not any(avisos)
    assert h.registrar_falha_fonte("zoom", 6) is True
    h.marcar_aviso_manutencao("zoom")
    assert h.registrar_falha_fonte("zoom", 6) is False
    h.registrar_sucesso_fonte("zoom")
    assert h.dados["falhas"]["zoom"]["seguidas"] == 0
