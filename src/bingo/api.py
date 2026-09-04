"""API HTTP do gerador de bingo.

O serviço é stateless: cada requisição traz a configuração completa do jogo
e recebe de volta um PDF.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bingo.gerador import gerar_folha, gerar_jogo
from bingo.models import MAX_FOLHAS, ConfiguracaoJogo, TipoBingo
from bingo.pdf import gerar_pdf_folha, gerar_pdf_jogo

STATIC = Path(__file__).resolve().parents[2] / "static"

app = FastAPI(title="Bingo", description="Gerador de cartelas de bingo para impressão")


class ConfiguracaoIn(BaseModel):
    """Configuração recebida do frontend; espelha ConfiguracaoJogo."""

    tipo: TipoBingo = "numeros"
    numero_elementos: int = Field(default=75, ge=1, le=10_000)
    palavras: list[str] = Field(default_factory=list)
    linhas: int = Field(default=5, ge=1, le=20)
    colunas: int = Field(default=5, ge=1, le=20)
    numero_folhas: int = Field(default=10, ge=1, le=MAX_FOLHAS)
    centro_livre: bool = True
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
            titulo=self.titulo.strip(),
            subtitulo=self.subtitulo.strip(),
        )


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
