"""Sorteio das folhas de um jogo de bingo."""

import random

from bingo.models import ConfiguracaoJogo

Folha = tuple[str | None, ...]


def gerar_folha(cfg: ConfiguracaoJogo, sorteador: random.Random | None = None) -> Folha:
    """Sorteia uma folha: as células em ordem de leitura (esquerda→direita,
    cima→baixo). None marca a célula central livre, quando houver.

    Sem `sorteador`, abre um `random.Random(cfg.semente)` novo — e é isso que
    faz o preview valer: `gerar_jogo` sorteia a primeira folha antes de
    qualquer descarte por repetição, então este caminho devolve exatamente a
    primeira folha do jogo. Com `cfg.semente` em None o `Random` sorteia da
    entropia do sistema, sem ramo condicional nenhum.
    """
    if sorteador is None:
        sorteador = random.Random(cfg.semente)
    celulas: list[str | None] = sorteador.sample(cfg.universo, cfg.elementos_por_folha)
    if cfg.indice_centro is not None:
        celulas.insert(cfg.indice_centro, None)
    return tuple(celulas)


def _identidade(folha: Folha) -> frozenset[str]:
    """Chave que identifica a folha ignorando a ordem das células.

    Duas folhas com os mesmos elementos em posições diferentes são a mesma
    folha para efeito de jogo: quem marcar uma marca a outra.
    """
    return frozenset(celula for celula in folha if celula is not None)


def gerar_jogo(cfg: ConfiguracaoJogo) -> tuple[Folha, ...]:
    """Sorteia todas as folhas do jogo, sem repetir nenhuma.

    A folha continua sendo uma tupla ordenada, porque a ordem define a posição
    de cada elemento na grade; o conjunto entra apenas como chave de comparação.
    `ConfiguracaoJogo` já garante que existem combinações suficientes, e o teto
    de tentativas é só uma trava contra laço infinito.

    O sorteador é um só para o jogo inteiro: com semente, o jogo é reproduzível
    de ponta a ponta; sem ela, cada chamada dá um jogo novo.
    """
    sorteador = random.Random(cfg.semente)
    limite_tentativas = max(1000, cfg.numero_folhas * 50)
    vistas: set[frozenset[str]] = set()
    folhas: list[Folha] = []

    for _ in range(limite_tentativas):
        if len(folhas) == cfg.numero_folhas:
            return tuple(folhas)
        folha = gerar_folha(cfg, sorteador)
        identidade = _identidade(folha)
        if identidade not in vistas:
            vistas.add(identidade)
            folhas.append(folha)

    raise ValueError(
        f"Não foi possível sortear {cfg.numero_folhas} folhas diferentes com os "
        f"elementos disponíveis."
    )
