"""Testes da renderização das folhas em PDF."""

import io

from pypdf import PdfReader

from bingo.gerador import gerar_folha, gerar_jogo
from bingo.models import ConfiguracaoJogo

from bingo.pdf import gerar_pdf_folha, gerar_pdf_jogo

PALAVRAS = tuple(f"palavra{i}" for i in range(20))


def _paginas(pdf: bytes) -> list:
    return PdfReader(io.BytesIO(pdf)).pages


def test_pdf_de_uma_folha_tem_uma_pagina():
    cfg = ConfiguracaoJogo()
    pdf = gerar_pdf_folha(gerar_folha(cfg), cfg)
    assert pdf.startswith(b"%PDF")
    assert len(_paginas(pdf)) == 1


def test_pdf_do_jogo_tem_uma_pagina_por_folha():
    cfg = ConfiguracaoJogo(numero_folhas=5)
    pdf = gerar_pdf_jogo(gerar_jogo(cfg), cfg)
    assert len(_paginas(pdf)) == 5


def test_celulas_e_cabecalho_aparecem_no_texto_da_pagina():
    cfg = ConfiguracaoJogo(
        tipo="palavras", palavras=PALAVRAS, linhas=3, colunas=3,
        centro_livre=False, titulo="Bingo da Escola", subtitulo="Turma A",
    )
    folha = gerar_folha(cfg)
    texto = _paginas(gerar_pdf_folha(folha, cfg))[0].extract_text()
    assert "Bingo da Escola" in texto
    assert "Turma A" in texto
    for celula in folha:
        assert celula in texto


def test_rodape_numera_as_folhas():
    cfg = ConfiguracaoJogo(numero_folhas=3)
    paginas = _paginas(gerar_pdf_jogo(gerar_jogo(cfg), cfg))
    assert "Folha 1 de 3" in paginas[0].extract_text()
    assert "Folha 3 de 3" in paginas[2].extract_text()
