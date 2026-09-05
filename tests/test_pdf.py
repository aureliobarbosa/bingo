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


def test_caixa_do_conteudo_ignora_a_margem_clara():
    from PIL import Image

    from bingo.pdf import caixa_do_conteudo

    imagem = Image.new("RGB", (100, 100), "white")
    for x in range(20, 60):
        for y in range(30, 70):
            imagem.putpixel((x, y), (0, 120, 130))
    assert caixa_do_conteudo(imagem) == (20, 30, 60, 70)


def test_imagem_toda_clara_nao_tem_o_que_recortar():
    from PIL import Image

    from bingo.pdf import caixa_do_conteudo

    assert caixa_do_conteudo(Image.new("RGB", (50, 50), "white")) is None


def test_logo_do_projeto_perde_a_margem_no_recorte():
    from PIL import Image

    from bingo.pdf import LOGO_PADRAO, caixa_do_conteudo

    with Image.open(LOGO_PADRAO) as arquivo:
        imagem = arquivo.convert("RGB")
    caixa = caixa_do_conteudo(imagem)
    assert caixa is not None
    largura = caixa[2] - caixa[0]
    altura = caixa[3] - caixa[1]
    assert largura < imagem.width and altura < imagem.height


def test_logo_do_arquivo_fica_em_cache():
    """Um jogo de muitas folhas não pode reabrir o arquivo a cada página."""
    from bingo.pdf import LOGO_PADRAO, _logo_do_arquivo

    versao = LOGO_PADRAO.stat().st_mtime
    assert _logo_do_arquivo(str(LOGO_PADRAO), versao) is _logo_do_arquivo(
        str(LOGO_PADRAO), versao
    )


def _data_uri_de_teste() -> str:
    """PNG com margem branca e um quadrado colorido no meio."""
    import base64
    import io as _io

    from PIL import Image

    imagem = Image.new("RGB", (300, 300), "white")
    for x in range(90, 210):
        for y in range(90, 210):
            imagem.putpixel((x, y), (200, 60, 20))
    buffer = _io.BytesIO()
    imagem.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_logo_enviado_substitui_o_padrao():
    cfg = ConfiguracaoJogo(
        linhas=5, colunas=5, centro_livre=True, logo_enviado=_data_uri_de_teste()
    )
    pagina = _paginas(gerar_pdf_folha(gerar_folha(cfg), cfg))[0]
    assert len(pagina.images) == 1


def test_logo_enviado_ilegivel_vira_erro_em_portugues():
    import pytest

    cfg = ConfiguracaoJogo(
        linhas=5, colunas=5, centro_livre=True,
        logo_enviado="data:image/png;base64,bm9uc2Vuc2U=",
    )
    with pytest.raises(ValueError, match="ler a imagem enviada"):
        gerar_pdf_folha(gerar_folha(cfg), cfg)


def test_logo_com_pixels_demais_e_rejeitado():
    """Imagem pequena em bytes pode descomprimir para muitos megapixels."""
    import base64
    import io as _io

    import pytest
    from PIL import Image

    from bingo.pdf import MAX_PIXELS_LOGO

    lado = int(MAX_PIXELS_LOGO**0.5) + 500
    buffer = _io.BytesIO()
    Image.new("RGB", (lado, lado), "white").save(buffer, format="PNG")
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    cfg = ConfiguracaoJogo(linhas=5, colunas=5, centro_livre=True, logo_enviado=uri)
    with pytest.raises(ValueError, match="megapixels"):
        gerar_pdf_folha(gerar_folha(cfg), cfg)
