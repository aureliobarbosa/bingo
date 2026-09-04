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
        tipo="palavras", palavras=PALAVRAS, linhas=3, colunas=3,
        centro_livre=True, numero_folhas=4,
    )
    folhas = gerar_jogo(cfg)
    assert len(folhas) == 4
    for folha in folhas:
        assert len(folha) == 9
        assert {c for c in folha if c is not None} <= set(PALAVRAS)
