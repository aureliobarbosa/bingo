"""Testes das rotas HTTP."""

import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from bingo import api
from bingo.api import MAX_CORPO_BYTES, MAX_LOGO_CARACTERES, app
from bingo.models import MAX_ELEMENTOS, MAX_PALAVRA_CARACTERES

client = TestClient(app)


@pytest.fixture(autouse=True)
def cota_cheia():
    """O limite de taxa vive num dicionário de módulo, que sobrevive ao teste.

    Sem zerá-lo, a ordem dos testes passaria a importar e um arquivo maior
    acabaria esbarrando na cota por acidente.
    """
    api._historico.clear()
    api._proxima_limpeza = 0.0


CONFIG = {
    "tipo": "numeros",
    "numero_elementos": 75,
    "linhas": 5,
    "colunas": 5,
    "numero_folhas": 4,
    "centro_livre": True,
    "titulo": "BINGO",
    "subtitulo": "Festa",
}


def _paginas(conteudo: bytes) -> int:
    return len(PdfReader(io.BytesIO(conteudo)).pages)


def test_preview_devolve_pdf_de_uma_folha():
    r = client.post("/api/preview", json=CONFIG)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert _paginas(r.content) == 1


def test_jogo_devolve_pdf_com_todas_as_folhas_para_download():
    r = client.post("/api/jogo", json=CONFIG)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert _paginas(r.content) == CONFIG["numero_folhas"]


def test_bingo_de_palavras():
    r = client.post(
        "/api/jogo",
        json={
            "tipo": "palavras",
            "palavras": [f"palavra{i}" for i in range(20)],
            "linhas": 3,
            "colunas": 3,
            "numero_folhas": 2,
            "centro_livre": False,
        },
    )
    assert r.status_code == 200
    assert _paginas(r.content) == 2


def test_regra_de_negocio_violada_vira_422_em_portugues():
    r = client.post("/api/preview", json={**CONFIG, "numero_elementos": 10})
    assert r.status_code == 422
    assert "maior que os elementos por folha" in r.json()["detail"]


def test_campo_fora_do_intervalo_e_rejeitado_pelo_schema():
    r = client.post("/api/preview", json={**CONFIG, "numero_folhas": 0})
    assert r.status_code == 422


def test_index_e_servido():
    assert client.get("/").status_code == 200


def test_logo_invalido_vira_422_em_portugues():
    r = client.post(
        "/api/preview", json={**CONFIG, "logo_enviado": "data:image/gif;base64,R0lGOD"}
    )
    assert r.status_code == 422
    assert "PNG ou JPEG" in r.json()["detail"]


def test_folhas_acima_das_combinacoes_vira_422():
    r = client.post(
        "/api/jogo",
        json={
            "tipo": "palavras",
            "palavras": [f"p{i}" for i in range(9)],
            "linhas": 3,
            "colunas": 3,
            "centro_livre": True,
            "numero_folhas": 10,
        },
    )
    assert r.status_code == 422
    assert "apenas 9 folhas distintas" in r.json()["detail"]


def test_corpo_acima_do_limite_vira_413():
    # Content-Length declarado acima do teto: a rota nem chega a ser executada.
    corpo = b'{"tipo":"numeros"}'
    r = client.post(
        "/api/preview",
        content=corpo,
        headers={
            "content-type": "application/json",
            "content-length": str(MAX_CORPO_BYTES + 1),
        },
    )
    assert r.status_code == 413
    assert "limite de 4 MB" in r.json()["detail"]


def test_palavra_longa_demais_e_rejeitada_pelo_schema():
    r = client.post(
        "/api/preview",
        json={
            "tipo": "palavras",
            "palavras": ["x" * (MAX_PALAVRA_CARACTERES + 1), "b", "c", "d", "e"],
            "linhas": 2,
            "colunas": 2,
            "centro_livre": False,
        },
    )
    assert r.status_code == 422


def test_logo_gigante_e_barrado_antes_de_abrir_a_imagem():
    # Passa do teto de caracteres do campo, então o Pydantic recusa sem que
    # models.py precise contar os bytes do base64.
    r = client.post(
        "/api/preview",
        json={
            **CONFIG,
            "logo_enviado": "data:image/png;base64," + "A" * (MAX_LOGO_CARACTERES + 1),
        },
    )
    assert r.status_code == 422


def test_universo_acima_do_teto_e_rejeitado_pelo_schema():
    """O Pydantic barra antes de `universo` materializar a tupla."""
    r = client.post(
        "/api/preview", json={**CONFIG, "numero_elementos": MAX_ELEMENTOS + 1}
    )
    assert r.status_code == 422

    r = client.post(
        "/api/preview",
        json={
            **CONFIG,
            "tipo": "palavras",
            "palavras": [f"p{i}" for i in range(MAX_ELEMENTOS + 1)],
        },
    )
    assert r.status_code == 422


def test_janela_deslizante_libera_quando_a_janela_passa():
    for i in range(api.MAX_REQUISICOES_POR_JANELA):
        assert api._espera_necessaria("10.0.0.1", 1000.0 + i * 0.001) == 0.0

    espera = api._espera_necessaria("10.0.0.1", 1000.5)
    assert espera > 0

    # Passada a janela inteira, a cota volta sozinha.
    depois = 1000.0 + api.JANELA_SEGUNDOS + 1
    assert api._espera_necessaria("10.0.0.1", depois) == 0.0


def test_o_limite_conta_por_ip():
    for _ in range(api.MAX_REQUISICOES_POR_JANELA):
        api._espera_necessaria("10.0.0.1", 1000.0)

    assert api._espera_necessaria("10.0.0.1", 1000.0) > 0
    assert api._espera_necessaria("10.0.0.2", 1000.0) == 0.0


def test_o_historico_solta_os_ips_que_sumiram():
    """A limpeza roda uma vez por janela; sem ela o dicionário cresceria sem fim."""
    api._espera_necessaria("10.0.0.1", 1000.0)
    api._espera_necessaria("10.0.0.2", 1000.0 + api.JANELA_SEGUNDOS + 1)

    assert "10.0.0.1" not in api._historico
    assert "10.0.0.2" in api._historico


def test_excesso_de_requisicoes_vira_429(monkeypatch):
    monkeypatch.setattr(api, "MAX_REQUISICOES_POR_JANELA", 2)

    assert client.post("/api/preview", json=CONFIG).status_code == 200
    assert client.post("/api/preview", json=CONFIG).status_code == 200

    r = client.post("/api/preview", json=CONFIG)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert "Espere um instante" in r.json()["detail"]


def test_o_limite_de_taxa_nao_alcanca_a_pagina_nem_os_estaticos(monkeypatch):
    monkeypatch.setattr(api, "MAX_REQUISICOES_POR_JANELA", 1)

    assert client.post("/api/preview", json=CONFIG).status_code == 200
    assert client.post("/api/preview", json=CONFIG).status_code == 429

    # Quem estourou a cota de gerar PDF continua conseguindo abrir a página.
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_estaticos_pedem_revalidacao():
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["etag"]


def test_estatico_sem_mudanca_volta_304_e_segue_pedindo_revalidacao():
    """O `no-cache` só é barato porque a revalidação cabe num 304 sem corpo."""
    etag = client.get("/static/app.js").headers["etag"]

    r = client.get("/static/app.js", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert r.headers["cache-control"] == "no-cache"
    assert r.content == b""


def test_index_tambem_pede_revalidacao():
    r = client.get("/")
    assert r.headers["cache-control"] == "no-cache"


def test_cabecalhos_de_seguranca_na_pagina():
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_a_csp_libera_o_que_a_pagina_de_fato_usa():
    """Se a política apertar mais do que isto, o preview ou o Bootstrap somem."""
    csp = client.get("/").headers["content-security-policy"]
    # O PDF do preview chega como blob: dentro de um <iframe>.
    assert "frame-src blob:" in csp
    assert "object-src blob:" in csp
    # O CSS do Bootstrap vem do jsDelivr.
    assert "https://cdn.jsdelivr.net" in csp


def test_o_pdf_tambem_sai_com_nosniff():
    r = client.post("/api/preview", json=CONFIG)
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"


def test_as_respostas_de_recusa_tambem_levam_os_cabecalhos(monkeypatch):
    """O middleware é o mais externo, então cobre o que os de dentro recusam."""
    monkeypatch.setattr(api, "MAX_REQUISICOES_POR_JANELA", 1)
    client.post("/api/preview", json=CONFIG)

    r = client.post("/api/preview", json=CONFIG)
    assert r.status_code == 429
    assert r.headers["x-content-type-options"] == "nosniff"
