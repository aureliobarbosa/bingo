"""Desenho das folhas de bingo em PDF (A4 retrato, uma folha por página)."""

import base64
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
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

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
LOGO_PADRAO = RAIZ_PROJETO / "static" / "images" / "logo.jpeg"
PROPORCAO_LOGO = 0.88  # fração do lado da célula ocupada pelo logo
LIMIAR_BRANCO = 250  # acima disto o pixel conta como margem, não como desenho
MAX_PIXELS_LOGO = 25_000_000  # trava contra imagem pequena que descomprime enorme
PROPORCAO_FONTE = 0.45  # tamanho inicial da fonte da célula, relativo ao lado
MARGEM_TEXTO = 0.85  # fração do lado que o texto pode ocupar
ENTRELINHA = 1.15  # espaçamento entre as linhas de uma mesma célula


def dividir_texto(texto: str) -> tuple[str, ...]:
    """Quebra o texto em duas linhas, no espaço mais próximo do centro.

    Textos sem espaço (números, palavras únicas) ficam em uma linha só. Dividir
    encurta a linha mais larga da folha, o que permite uma fonte bem maior.
    """
    espacos = [i for i, ch in enumerate(texto) if ch == " "]
    if not espacos:
        return (texto,)
    meio = len(texto) / 2
    corte = min(espacos, key=lambda i: abs(i - meio))
    return (texto[:corte], texto[corte + 1 :])


def _linhas_das_celulas(folha: Folha) -> tuple[tuple[str, ...], ...]:
    return tuple(dividir_texto(t) for t in folha if t)


def _tamanho_fonte_celula(
    c: canvas.Canvas, linhas_das_celulas: tuple[tuple[str, ...], ...], lado: float
) -> float:
    """Maior fonte em que todas as células da folha cabem, em largura e altura."""
    tamanho = lado * PROPORCAO_FONTE
    todas = [linha for celula in linhas_das_celulas for linha in celula]
    if not todas:
        return tamanho

    # Largura: limitada pela linha mais larga da folha.
    mais_larga = max(todas, key=lambda t: c.stringWidth(t, FONTE_CELULA, 100))
    largura_a_100 = c.stringWidth(mais_larga, FONTE_CELULA, 100)
    if largura_a_100 > 0:
        tamanho = min(tamanho, lado * MARGEM_TEXTO * 100 / largura_a_100)

    # Altura: limitada pela célula com mais linhas.
    mais_linhas = max(len(celula) for celula in linhas_das_celulas)
    tamanho = min(tamanho, lado * MARGEM_TEXTO / (mais_linhas * ENTRELINHA))
    return tamanho


def caixa_do_conteudo(imagem: Image.Image) -> tuple[int, int, int, int] | None:
    """Retângulo que envolve o desenho, descartando a margem clara em volta.

    Devolve None quando a imagem é inteiramente clara — aí não há o que recortar.
    """
    mascara = imagem.convert("L").point(lambda v: 255 if v < LIMIAR_BRANCO else 0)
    return mascara.getbbox()


def _sem_margem(imagem: Image.Image) -> ImageReader:
    """Descarta a margem clara em volta e entrega a imagem ao reportlab."""
    caixa = caixa_do_conteudo(imagem)
    if caixa:
        imagem = imagem.crop(caixa)
    return ImageReader(imagem)


@lru_cache(maxsize=8)
def _logo_do_arquivo(caminho: str, versao: float) -> ImageReader:
    """Logo padrão, lido do disco.

    O resultado fica em cache: um jogo inteiro abre o arquivo uma vez só.
    `versao` é o mtime do arquivo e serve para invalidar o cache se ele mudar.
    """
    with Image.open(caminho) as arquivo:
        return _sem_margem(arquivo.convert("RGB"))


@lru_cache(maxsize=2)
def _logo_enviado(data_uri: str) -> ImageReader:
    """Logo que veio na requisição, como data URI (`data:image/png;base64,...`)."""
    _, _, dados = data_uri.partition(",")
    try:
        arquivo = Image.open(io.BytesIO(base64.b64decode(dados, validate=True)))
    except Exception as erro:
        raise ValueError("Não foi possível ler a imagem enviada como logo.") from erro

    with arquivo:
        largura, altura = arquivo.size
        if largura * altura > MAX_PIXELS_LOGO:
            raise ValueError(
                f"O logo tem {largura}x{altura} pixels, acima do limite de "
                f"{MAX_PIXELS_LOGO // 1_000_000} megapixels."
            )
        return _sem_margem(arquivo.convert("RGB"))


def _logo_para_desenho(cfg: ConfiguracaoJogo) -> ImageReader | None:
    """Imagem a desenhar na célula central: a enviada, ou a padrão do projeto."""
    if cfg.logo_enviado:
        return _logo_enviado(cfg.logo_enviado)
    if LOGO_PADRAO.is_file():
        return _logo_do_arquivo(str(LOGO_PADRAO), LOGO_PADRAO.stat().st_mtime)
    return None


def _desenhar_logo(
    c: canvas.Canvas, cfg: ConfiguracaoJogo, x: float, y: float, lado: float
) -> bool:
    """Desenha o logo na célula central. Devolve False se não houver imagem."""
    logo = _logo_para_desenho(cfg)
    if logo is None:
        return False
    tamanho = lado * PROPORCAO_LOGO
    borda = (lado - tamanho) / 2
    c.drawImage(
        logo,
        x + borda,
        y + borda,
        width=tamanho,
        height=tamanho,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )
    return True


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

    tamanho_fonte = _tamanho_fonte_celula(c, _linhas_das_celulas(folha), lado)

    for posicao, texto in enumerate(folha):
        linha, coluna = divmod(posicao, cfg.colunas)
        x = x0 + coluna * lado
        # A primeira linha da folha é a de cima: y cresce para cima no PDF.
        y = y0 + (cfg.linhas - 1 - linha) * lado

        if texto is None:
            # A célula central recebe o logo; sem arquivo de logo, fica cinza.
            if not _desenhar_logo(c, cfg, x, y, lado):
                c.setFillGray(CINZA_CENTRO)
                c.rect(x, y, lado, lado, stroke=0, fill=1)
                c.setFillGray(0)

        c.setLineWidth(0.8)
        c.rect(x, y, lado, lado, stroke=1, fill=0)

        if texto is not None:
            c.setFont(FONTE_CELULA, tamanho_fonte)
            linhas_texto = dividir_texto(texto)
            passo = tamanho_fonte * ENTRELINHA
            # Bloco de linhas centrado na célula; o 0,25 compensa opticamente a
            # altura das maiúsculas, que ficam acima da linha de base.
            primeira = (
                y + lado / 2 + len(linhas_texto) * passo / 2 - passo + tamanho_fonte * 0.25
            )
            for numero, linha_texto in enumerate(linhas_texto):
                c.drawCentredString(x + lado / 2, primeira - numero * passo, linha_texto)

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
