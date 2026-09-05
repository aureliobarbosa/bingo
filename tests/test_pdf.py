"""Testes da renderização das folhas em PDF."""

import io

from pypdf import PdfReader

from bingo.gerador import gerar_folha, gerar_jogo
from bingo.models import ConfiguracaoJogo

from bingo.pdf import dividir_texto, gerar_pdf_folha, gerar_pdf_jogo

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


def test_divisao_ocorre_no_espaco_mais_proximo_do_centro():
    assert dividir_texto("Os Paralamas do Sucesso") == ("Os Paralamas", "do Sucesso")
    assert dividir_texto("Buena Vista Social Club") == ("Buena Vista", "Social Club")
    assert dividir_texto("Tom Jobim") == ("Tom", "Jobim")


def test_texto_sem_espaco_fica_em_uma_linha():
    assert dividir_texto("Nirvana") == ("Nirvana",)
    assert dividir_texto("42") == ("42",)


def test_celula_quebrada_aparece_inteira_no_pdf():
    cfg = ConfiguracaoJogo(
        tipo="palavras",
        palavras=("Os Paralamas do Sucesso",) + tuple(f"artista{i}" for i in range(9)),
        linhas=3, colunas=3, centro_livre=False,
    )
    folha = gerar_folha(cfg)
    texto = _paginas(gerar_pdf_folha(folha, cfg))[0].extract_text()
    for celula in folha:
        for parte in dividir_texto(celula):
            assert parte in texto


def test_quebrar_em_duas_linhas_aumenta_a_fonte():
    """Nomes longos com espaço devem sair maiores do que sairiam em linha única."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as reportlab_canvas

    from bingo.pdf import FONTE_CELULA, _linhas_das_celulas, _tamanho_fonte_celula

    c = reportlab_canvas.Canvas(io.BytesIO(), pagesize=A4)
    nomes = ("Os Paralamas do Sucesso", "Buena Vista Social Club", "Queen")
    lado = 100.0
    quebrado = _tamanho_fonte_celula(c, _linhas_das_celulas(nomes), lado)
    inteiro = _tamanho_fonte_celula(c, tuple((n,) for n in nomes), lado)
    assert quebrado > inteiro


def test_logo_e_desenhado_na_celula_central():
    """Com centro livre, a página carrega exatamente uma imagem: o logo."""
    cfg = ConfiguracaoJogo(linhas=5, colunas=5, centro_livre=True)
    pagina = _paginas(gerar_pdf_folha(gerar_folha(cfg), cfg))[0]
    assert len(pagina.images) == 1


def test_sem_centro_livre_nao_ha_imagem():
    cfg = ConfiguracaoJogo(linhas=4, colunas=4, centro_livre=False)
    pagina = _paginas(gerar_pdf_folha(gerar_folha(cfg), cfg))[0]
    assert len(pagina.images) == 0
