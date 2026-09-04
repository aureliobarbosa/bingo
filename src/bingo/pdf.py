"""Desenho das folhas de bingo em PDF (A4 retrato, uma folha por página)."""

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from bingo.gerador import Folha
from bingo.models import ConfiguracaoJogo

MARGEM = 15 * mm
ALTURA_CABECALHO = 22 * mm
ALTURA_RODAPE = 10 * mm

FONTE_TITULO = "Helvetica-Bold"
FONTE_TEXTO = "Helvetica"
FONTE_CELULA = "Helvetica-Bold"

CINZA_CENTRO = 0.92
PROPORCAO_FONTE = 0.45  # tamanho inicial da fonte da célula, relativo ao lado
MARGEM_TEXTO = 0.85  # fração do lado que o texto pode ocupar


def _tamanho_fonte_celula(c: canvas.Canvas, folha: Folha, lado: float) -> float:
    """Maior fonte em que todos os textos da folha cabem na célula."""
    textos = [t for t in folha if t]
    tamanho = lado * PROPORCAO_FONTE
    if not textos:
        return tamanho
    largura_max = lado * MARGEM_TEXTO
    mais_largo = max(textos, key=lambda t: c.stringWidth(t, FONTE_CELULA, 100))
    largura_a_100 = c.stringWidth(mais_largo, FONTE_CELULA, 100)
    if largura_a_100 > 0:
        tamanho = min(tamanho, largura_max * 100 / largura_a_100)
    return tamanho


def _desenhar_cabecalho(c: canvas.Canvas, cfg: ConfiguracaoJogo, topo: float) -> None:
    largura, _ = A4
    meio = largura / 2
    if cfg.titulo:
        c.setFont(FONTE_TITULO, 24)
        c.drawCentredString(meio, topo - 18, cfg.titulo)
    if cfg.subtitulo:
        c.setFont(FONTE_TEXTO, 12)
        c.drawCentredString(meio, topo - 34, cfg.subtitulo)


def _desenhar_rodape(c: canvas.Canvas, indice: int, total: int) -> None:
    largura, _ = A4
    c.setFont(FONTE_TEXTO, 9)
    c.setFillGray(0.4)
    c.drawCentredString(largura / 2, MARGEM - 4, f"Folha {indice} de {total}")
    c.setFillGray(0)


def desenhar_folha(
    c: canvas.Canvas,
    folha: Folha,
    cfg: ConfiguracaoJogo,
    indice: int = 1,
    total: int = 1,
) -> None:
    """Desenha uma folha na página atual do canvas."""
    largura, altura = A4
    _desenhar_cabecalho(c, cfg, altura - MARGEM)
    _desenhar_rodape(c, indice, total)

    # Espaço disponível para a grade, entre cabeçalho e rodapé.
    disp_largura = largura - 2 * MARGEM
    disp_altura = altura - 2 * MARGEM - ALTURA_CABECALHO - ALTURA_RODAPE

    # Células quadradas: a grade fica centrada no espaço disponível.
    lado = min(disp_largura / cfg.colunas, disp_altura / cfg.linhas)
    grade_largura = lado * cfg.colunas
    grade_altura = lado * cfg.linhas
    x0 = MARGEM + (disp_largura - grade_largura) / 2
    y0 = MARGEM + ALTURA_RODAPE + (disp_altura - grade_altura) / 2

    tamanho_fonte = _tamanho_fonte_celula(c, folha, lado)

    for posicao, texto in enumerate(folha):
        linha, coluna = divmod(posicao, cfg.colunas)
        x = x0 + coluna * lado
        # A primeira linha da folha é a de cima: y cresce para cima no PDF.
        y = y0 + (cfg.linhas - 1 - linha) * lado

        if texto is None:
            c.setFillGray(CINZA_CENTRO)
            c.rect(x, y, lado, lado, stroke=0, fill=1)
            c.setFillGray(0)

        c.setLineWidth(0.8)
        c.rect(x, y, lado, lado, stroke=1, fill=0)

        if texto is not None:
            c.setFont(FONTE_CELULA, tamanho_fonte)
            # Centralização vertical aproximada pela altura das maiúsculas.
            c.drawCentredString(x + lado / 2, y + (lado - tamanho_fonte * 0.7) / 2, texto)

    # Contorno externo mais forte.
    c.setLineWidth(2)
    c.rect(x0, y0, grade_largura, grade_altura, stroke=1, fill=0)


def _novo_canvas(buffer: io.BytesIO, cfg: ConfiguracaoJogo) -> canvas.Canvas:
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(cfg.titulo or "Bingo")
    return c


def gerar_pdf_folha(
    folha: Folha, cfg: ConfiguracaoJogo, indice: int = 1, total: int = 1
) -> bytes:
    """PDF de uma única folha."""
    buffer = io.BytesIO()
    c = _novo_canvas(buffer, cfg)
    desenhar_folha(c, folha, cfg, indice, total)
    c.showPage()
    c.save()
    return buffer.getvalue()


def gerar_pdf_jogo(folhas: tuple[Folha, ...], cfg: ConfiguracaoJogo) -> bytes:
    """PDF com todas as folhas do jogo, uma por página."""
    buffer = io.BytesIO()
    c = _novo_canvas(buffer, cfg)
    total = len(folhas)
    for indice, folha in enumerate(folhas, start=1):
        desenhar_folha(c, folha, cfg, indice, total)
        c.showPage()
    c.save()
    return buffer.getvalue()
