"""Testes das rotas HTTP."""

import io

from fastapi.testclient import TestClient
from pypdf import PdfReader

from bingo.api import app

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
