"""Testes das rotas HTTP."""

import io

from fastapi.testclient import TestClient
from pypdf import PdfReader

from bingo.api import MAX_CORPO_BYTES, MAX_LOGO_CARACTERES, app
from bingo.models import MAX_ELEMENTOS, MAX_PALAVRA_CARACTERES

client = TestClient(app)

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
