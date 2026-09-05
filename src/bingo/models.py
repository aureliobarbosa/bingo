"""Configuração de um jogo de bingo e suas regras de validação."""

import math
from dataclasses import dataclass
from typing import Literal

TipoBingo = Literal["numeros", "palavras"]

MAX_CELULAS = 100
MAX_FOLHAS = 500

FORMATOS_LOGO = ("image/png", "image/jpeg")
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB: o data URI trafega a cada preview


@dataclass(frozen=True)
class ConfiguracaoJogo:
    """Um jogo é um conjunto válido de parâmetros do bingo.

    Os elementos de uma folha são sorteados do `universo`: os números de 1 a
    `numero_elementos` (tipo "numeros") ou a lista `palavras` (tipo "palavras").
    """

    tipo: TipoBingo = "numeros"
    numero_elementos: int = 75
    palavras: tuple[str, ...] = ()
    linhas: int = 5
    colunas: int = 5
    numero_folhas: int = 10
    centro_livre: bool = True
    # Imagem enviada pelo usuário, como data URI. Vazio: usa o logo padrão.
    logo_enviado: str = ""
    titulo: str = "BINGO"
    subtitulo: str = ""

    def __post_init__(self) -> None:
        self.validar()

    # -- propriedades derivadas ------------------------------------------------

    @property
    def celulas(self) -> int:
        """Total de células da grade impressa."""
        return self.linhas * self.colunas

    @property
    def elementos_por_folha(self) -> int:
        """Quantos elementos são sorteados por folha (o centro livre não conta)."""
        return self.celulas - (1 if self.centro_livre else 0)

    @property
    def universo(self) -> tuple[str, ...]:
        """Conjunto de elementos disponíveis para sorteio, já como texto."""
        if self.tipo == "numeros":
            return tuple(str(n) for n in range(1, self.numero_elementos + 1))
        return self.palavras

    @property
    def combinacoes_possiveis(self) -> int:
        """Quantas folhas distintas o universo permite formar.

        Folhas são comparadas como conjuntos: os mesmos elementos em ordens
        diferentes são a mesma folha. Daí a combinação C(n, k) = n! / (k!(n-k)!),
        com n = elementos disponíveis e k = elementos sorteados por folha.
        """
        disponiveis = len(self.universo)
        if disponiveis <= self.elementos_por_folha:
            return 0
        return math.comb(disponiveis, self.elementos_por_folha)

    @property
    def maximo_folhas(self) -> int:
        """Maior número de folhas aceitável: o que o universo permite, com teto."""
        return min(MAX_FOLHAS, self.combinacoes_possiveis)

    @property
    def indice_centro(self) -> int | None:
        """Posição da célula central na ordem de leitura, ou None."""
        if not self.centro_livre:
            return None
        return (self.linhas // 2) * self.colunas + self.colunas // 2

    # -- validação -------------------------------------------------------------

    def validar(self) -> None:
        """Levanta ValueError com mensagem em português na primeira regra violada."""
        if self.tipo not in ("numeros", "palavras"):
            raise ValueError("Tipo de bingo deve ser 'numeros' ou 'palavras'.")

        if self.logo_enviado:
            self._validar_logo()

        if self.linhas < 1 or self.colunas < 1:
            raise ValueError("A grade precisa ter ao menos uma linha e uma coluna.")

        if self.celulas > MAX_CELULAS:
            raise ValueError(
                f"A grade não pode passar de {MAX_CELULAS} células "
                f"(pedido: {self.linhas}x{self.colunas} = {self.celulas})."
            )

        if self.centro_livre and (self.linhas % 2 == 0 or self.colunas % 2 == 0):
            raise ValueError(
                "A célula central livre exige número ímpar de linhas e de colunas."
            )

        if not 1 <= self.numero_folhas <= MAX_FOLHAS:
            raise ValueError(f"O número de folhas deve estar entre 1 e {MAX_FOLHAS}.")

        if self.tipo == "numeros":
            if self.numero_elementos < 1:
                raise ValueError("O número de elementos deve ser ao menos 1.")
        else:
            if any(not p.strip() for p in self.palavras):
                raise ValueError("A lista de palavras não pode conter linhas vazias.")
            if len(set(self.palavras)) != len(self.palavras):
                raise ValueError("A lista de palavras não pode conter repetições.")

        disponiveis = len(self.universo)
        if disponiveis <= self.elementos_por_folha:
            raise ValueError(
                f"O número de elementos ({disponiveis}) deve ser maior que os "
                f"elementos por folha ({self.elementos_por_folha})."
            )

        # Não adianta pedir mais folhas do que existem combinações distintas.
        # Só morde em universos pequenos: acima de 500 combinações quem limita
        # é MAX_FOLHAS, já validado acima.
        combinacoes = self.combinacoes_possiveis
        if self.numero_folhas > combinacoes:
            raise ValueError(
                f"Com {disponiveis} elementos e {self.elementos_por_folha} por "
                f"folha existem apenas {combinacoes} folhas distintas possíveis."
            )

    def _validar_logo(self) -> None:
        """Checa o logo enviado sem decodificar a imagem.

        O formato vem do cabeçalho do data URI e o tamanho é calculado do
        comprimento do base64 — abrir a imagem é trabalho do módulo de PDF.
        """
        cabecalho, separador, dados = self.logo_enviado.partition(",")
        if not separador or not cabecalho.startswith("data:"):
            raise ValueError("O logo enviado não está num formato reconhecido.")

        formato = cabecalho.removeprefix("data:").split(";")[0]
        if formato not in FORMATOS_LOGO:
            raise ValueError(
                f"O logo precisa ser PNG ou JPEG (recebido: {formato or 'desconhecido'})."
            )

        # base64 usa 4 caracteres para cada 3 bytes; o '=' final é enchimento.
        bytes_imagem = len(dados) * 3 // 4 - dados.count("=")
        if bytes_imagem > MAX_LOGO_BYTES:
            limite = MAX_LOGO_BYTES // (1024 * 1024)
            raise ValueError(
                f"O logo tem {bytes_imagem / (1024 * 1024):.1f} MB e o limite é "
                f"{limite} MB."
            )
