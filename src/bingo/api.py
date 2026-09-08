"""API HTTP do gerador de bingo.

O serviço é stateless: cada requisição traz a configuração completa do jogo
e recebe de volta um PDF.
"""

import math
import time
from collections import deque
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from bingo.gerador import gerar_folha, gerar_jogo
from bingo.models import (
    MAX_ELEMENTOS,
    MAX_FOLHAS,
    MAX_LOGO_BYTES,
    MAX_PALAVRA_CARACTERES,
    ConfiguracaoJogo,
    TipoBingo,
)
from bingo.pdf import RAIZ_PROJETO, gerar_pdf_folha, gerar_pdf_jogo

STATIC = RAIZ_PROJETO / "static"

# Teto do corpo da requisição. O pior caso legítimo é um logo de 2 MB, que vira
# ~2,8 MB em base64, mais as palavras e o cabeçalho — 4 MB deixa folga. Sem este
# limite o corpo inteiro é lido na memória antes de qualquer validação.
MAX_CORPO_BYTES = 4 * 1024 * 1024

# base64 gasta 4 caracteres a cada 3 bytes; a folga cobre o cabeçalho do data URI.
MAX_LOGO_CARACTERES = MAX_LOGO_BYTES * 4 // 3 + 100

# Limite de taxa por IP: janela deslizante em memória, com biblioteca padrão.
# O teto é generoso de propósito. O preview tem debounce de 400 ms, então nem
# quem mexe no painel sem parar passa de ~150 requisições por minuto — e, na
# prática, fica bem abaixo disso. Um bot em laço estoura em segundos.
#
# O que este limite NÃO faz, e é preciso dizer: cada instância tem o seu próprio
# dicionário. Com `--max-instances 3` o teto efetivo é até 3x o configurado, e
# ele zera quando a instância recicla. Serve para conter bot em laço, não
# atacante determinado — isso exigiria armazenamento compartilhado, que este
# serviço stateless não tem e não vai ter por causa de dez usuários por ano.
JANELA_SEGUNDOS = 60.0
MAX_REQUISICOES_POR_JANELA = 120

# IP -> marcas de tempo (monotônicas) das requisições dentro da janela.
_historico: dict[str, deque[float]] = {}
_proxima_limpeza = 0.0

Palavra = Annotated[str, StringConstraints(max_length=MAX_PALAVRA_CARACTERES)]

app = FastAPI(title="Bingo", description="Gerador de cartelas de bingo para impressão")


class ConfiguracaoIn(BaseModel):
    """Configuração recebida do frontend; espelha ConfiguracaoJogo."""

    tipo: TipoBingo = "numeros"
    numero_elementos: int = Field(default=75, ge=1, le=MAX_ELEMENTOS)
    palavras: list[Palavra] = Field(default_factory=list, max_length=MAX_ELEMENTOS)
    linhas: int = Field(default=5, ge=1, le=20)
    colunas: int = Field(default=5, ge=1, le=20)
    numero_folhas: int = Field(default=10, ge=1, le=MAX_FOLHAS)
    centro_livre: bool = True
    logo_enviado: str = Field(default="", max_length=MAX_LOGO_CARACTERES)
    titulo: str = Field(default="BINGO", max_length=80)
    subtitulo: str = Field(default="", max_length=120)

    def para_jogo(self) -> ConfiguracaoJogo:
        """Converte para a dataclass do domínio, que faz a validação de regras."""
        return ConfiguracaoJogo(
            tipo=self.tipo,
            numero_elementos=self.numero_elementos,
            palavras=tuple(p.strip() for p in self.palavras if p.strip()),
            linhas=self.linhas,
            colunas=self.colunas,
            numero_folhas=self.numero_folhas,
            centro_livre=self.centro_livre,
            logo_enviado=self.logo_enviado,
            titulo=self.titulo.strip(),
            subtitulo=self.subtitulo.strip(),
        )


@app.middleware("http")
async def limitar_tamanho_do_corpo(request: Request, call_next):
    """Recusa corpos grandes antes de lê-los.

    A checagem é no `Content-Length`, que é o que todo cliente honesto manda.
    Uma requisição em `chunked`, sem esse cabeçalho, escapa daqui — mas segue
    limitada pelos tetos de cada campo e pelo limite da própria plataforma.
    """
    declarado = request.headers.get("content-length")
    if declarado is not None:
        try:
            tamanho = int(declarado)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Cabeçalho Content-Length inválido."},
            )
        if tamanho > MAX_CORPO_BYTES:
            limite = MAX_CORPO_BYTES // (1024 * 1024)
            return JSONResponse(
                status_code=413,
                content={"detail": f"A requisição passa do limite de {limite} MB."},
            )
    return await call_next(request)


def _cliente(request: Request) -> str:
    """IP de quem pediu.

    O uvicorn sobe com `--proxy-headers`, então atrás do Cloud Run isto já é o
    IP real do cliente e não o do Google Front End. Sem aquilo, o serviço
    inteiro contaria como um cliente só e este limite não funcionaria.
    """
    return request.client.host if request.client else "desconhecido"


def _descartar_antigas(marcas: deque[float], agora: float) -> None:
    limite = agora - JANELA_SEGUNDOS
    while marcas and marcas[0] <= limite:
        marcas.popleft()


def _limpar_historico(agora: float) -> None:
    """Solta os IPs que sumiram, para o dicionário não crescer sem fim."""
    velhos = [
        ip
        for ip, marcas in _historico.items()
        if not marcas or marcas[-1] <= agora - JANELA_SEGUNDOS
    ]
    for ip in velhos:
        del _historico[ip]


def _espera_necessaria(ip: str, agora: float) -> float:
    """Registra a requisição e devolve quantos segundos faltam; 0 se ela cabe.

    Roda inteira no laço de eventos, sem `await` no meio, então duas
    requisições nunca a executam ao mesmo tempo e nenhum cadeado é preciso.
    """
    global _proxima_limpeza
    if agora >= _proxima_limpeza:
        _limpar_historico(agora)
        _proxima_limpeza = agora + JANELA_SEGUNDOS

    marcas = _historico.setdefault(ip, deque())
    _descartar_antigas(marcas, agora)
    if len(marcas) >= MAX_REQUISICOES_POR_JANELA:
        return marcas[0] + JANELA_SEGUNDOS - agora
    marcas.append(agora)
    return 0.0


@app.middleware("http")
async def limitar_taxa(request: Request, call_next):
    """Limite de taxa por IP, só nas rotas `/api/`.

    Os estáticos ficam de fora: são baratos e uma visita normal já pede três
    deles, o que gastaria a cota de quem não fez nada de errado. O custo real
    está em gerar PDF, e é isso que este limite protege.
    """
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    espera = _espera_necessaria(_cliente(request), time.monotonic())
    if espera > 0:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Muitas requisições em pouco tempo. "
                "Espere um instante e tente de novo."
            },
            headers={"Retry-After": str(max(1, math.ceil(espera)))},
        )
    return await call_next(request)


@app.exception_handler(ValueError)
async def erro_de_regra(request: Request, exc: ValueError) -> JSONResponse:
    """Traduz as regras de negócio violadas em 422 com a mensagem em português."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.post("/api/preview", response_class=Response)
def preview(entrada: ConfiguracaoIn) -> Response:
    """PDF de uma única folha, para o painel de visualização."""
    cfg = entrada.para_jogo()
    pdf = gerar_pdf_folha(gerar_folha(cfg), cfg, indice=1, total=cfg.numero_folhas)
    return Response(content=pdf, media_type="application/pdf")


@app.post("/api/jogo", response_class=Response)
def jogo(entrada: ConfiguracaoIn) -> Response:
    """PDF com todas as folhas do jogo, para download."""
    cfg = entrada.para_jogo()
    pdf = gerar_pdf_jogo(gerar_jogo(cfg), cfg)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="bingo.pdf"'},
    )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
