"""Sorteio das folhas de um jogo de bingo."""

import random

from bingo.models import ConfiguracaoJogo

Folha = tuple[str | None, ...]


def gerar_folha(cfg: ConfiguracaoJogo) -> Folha:
    """Sorteia uma folha: as células em ordem de leitura (esquerda→direita,
    cima→baixo). None marca a célula central livre, quando houver."""
    celulas: list[str | None] = random.sample(cfg.universo, cfg.elementos_por_folha)
    if cfg.indice_centro is not None:
        celulas.insert(cfg.indice_centro, None)
    return tuple(celulas)


def gerar_jogo(cfg: ConfiguracaoJogo) -> tuple[Folha, ...]:
    """Sorteia todas as folhas do jogo, uma tupla por folha."""
    return tuple(gerar_folha(cfg) for _ in range(cfg.numero_folhas))
