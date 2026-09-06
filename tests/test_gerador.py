"""Testes do sorteio das folhas."""

from bingo.gerador import gerar_folha, gerar_jogo
from bingo.models import ConfiguracaoJogo

PALAVRAS = tuple(f"palavra{i}" for i in range(20))


def test_jogo_tem_o_numero_de_folhas_pedido():
    cfg = ConfiguracaoJogo(numero_folhas=7)
    assert len(gerar_jogo(cfg)) == 7


def test_folha_tem_uma_celula_por_posicao_da_grade():
    cfg = ConfiguracaoJogo(linhas=3, colunas=9, centro_livre=False)
    folha = gerar_folha(cfg)
    assert len(folha) == 27


def test_celulas_vem_do_universo_e_nao_se_repetem():
    cfg = ConfiguracaoJogo(numero_elementos=75, linhas=5, colunas=5, centro_livre=False)
    folha = gerar_folha(cfg)
    assert set(folha) <= set(cfg.universo)
    assert len(set(folha)) == len(folha)


def test_centro_livre_fica_vazio_e_as_demais_celulas_preenchidas():
    cfg = ConfiguracaoJogo(linhas=5, colunas=5, centro_livre=True)
    folha = gerar_folha(cfg)
    assert folha[cfg.indice_centro] is None
    assert sum(1 for c in folha if c is None) == 1
    assert len(folha) == 25


def test_sem_centro_livre_nenhuma_celula_e_vazia():
    cfg = ConfiguracaoJogo(linhas=4, colunas=4, centro_livre=False)
    folha = gerar_folha(cfg)
    assert all(c is not None for c in folha)


def test_bingo_de_palavras():
    cfg = ConfiguracaoJogo(
        tipo="palavras",
        palavras=PALAVRAS,
        linhas=3,
        colunas=3,
        centro_livre=True,
        numero_folhas=4,
    )
    folhas = gerar_jogo(cfg)
    assert len(folhas) == 4
    for folha in folhas:
        assert len(folha) == 9
        assert {c for c in folha if c is not None} <= set(PALAVRAS)


def test_jogo_nao_repete_folhas_mesmo_com_universo_apertado():
    """Com 9 palavras numa grade 3x3 só existem 9 folhas: todas devem sair uma vez."""
    cfg = ConfiguracaoJogo(
        tipo="palavras",
        palavras=tuple(f"p{i}" for i in range(9)),
        linhas=3,
        colunas=3,
        centro_livre=True,
        numero_folhas=9,
    )
    folhas = gerar_jogo(cfg)
    identidades = {frozenset(c for c in folha if c is not None) for folha in folhas}
    assert len(identidades) == 9


def test_folhas_com_os_mesmos_elementos_em_outra_ordem_contam_como_iguais():
    from bingo.gerador import _identidade

    assert _identidade(("a", "b", None, "c")) == _identidade(("c", None, "a", "b"))


def test_jogo_grande_continua_sem_repetir():
    cfg = ConfiguracaoJogo(
        tipo="palavras",
        palavras=tuple(f"p{i}" for i in range(12)),
        linhas=3,
        colunas=3,
        centro_livre=True,
        numero_folhas=30,
    )
    folhas = gerar_jogo(cfg)
    identidades = {frozenset(c for c in folha if c is not None) for folha in folhas}
    assert len(identidades) == 30
