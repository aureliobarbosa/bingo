"""Testes da configuração do jogo e de suas regras de validação."""

import pytest

from bingo.models import ConfiguracaoJogo

PALAVRAS = tuple(f"palavra{i}" for i in range(20))


def test_configuracao_de_numeros_valida():
    cfg = ConfiguracaoJogo(
        tipo="numeros", numero_elementos=75, linhas=5, colunas=5, centro_livre=True
    )
    assert cfg.celulas == 25
    assert cfg.elementos_por_folha == 24
    assert cfg.indice_centro == 12
    assert cfg.universo[0] == "1" and cfg.universo[-1] == "75"


def test_configuracao_de_palavras_valida():
    cfg = ConfiguracaoJogo(
        tipo="palavras", palavras=PALAVRAS, linhas=3, colunas=3, centro_livre=False
    )
    assert cfg.elementos_por_folha == 9
    assert cfg.indice_centro is None
    assert cfg.universo == PALAVRAS


def test_grade_precisa_ter_linhas_e_colunas():
    with pytest.raises(ValueError, match="ao menos uma linha"):
        ConfiguracaoJogo(linhas=0, colunas=5, centro_livre=False)


def test_grade_grande_demais_e_rejeitada():
    with pytest.raises(ValueError, match="100 células"):
        ConfiguracaoJogo(linhas=11, colunas=11, numero_elementos=200)


def test_centro_livre_exige_dimensoes_impares():
    with pytest.raises(ValueError, match="ímpar"):
        ConfiguracaoJogo(linhas=4, colunas=5, centro_livre=True)


def test_numero_de_folhas_fora_do_intervalo():
    with pytest.raises(ValueError, match="entre 1 e 500"):
        ConfiguracaoJogo(numero_folhas=0)
    with pytest.raises(ValueError, match="entre 1 e 500"):
        ConfiguracaoJogo(numero_folhas=501)


def test_elementos_devem_superar_os_elementos_por_folha():
    with pytest.raises(ValueError, match="deve ser maior"):
        ConfiguracaoJogo(
            tipo="numeros", numero_elementos=24, linhas=5, colunas=5, centro_livre=True
        )


def test_palavras_vazias_sao_rejeitadas():
    with pytest.raises(ValueError, match="linhas vazias"):
        ConfiguracaoJogo(
            tipo="palavras", palavras=("a", "  ", "c"), linhas=1, colunas=2,
            centro_livre=False,
        )


def test_palavras_repetidas_sao_rejeitadas():
    with pytest.raises(ValueError, match="repetições"):
        ConfiguracaoJogo(
            tipo="palavras", palavras=("a", "b", "a"), linhas=1, colunas=2,
            centro_livre=False,
        )


def test_tipo_invalido():
    with pytest.raises(ValueError, match="'numeros' ou 'palavras'"):
        ConfiguracaoJogo(tipo="letras")


def _uri_de_logo(formato: str = "image/png", bytes_extra: int = 0) -> str:
    import base64
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (80, 80), "white").save(buffer, format="PNG")
    dados = buffer.getvalue() + b"\0" * bytes_extra
    return f"data:{formato};base64," + base64.b64encode(dados).decode()


def test_logo_em_png_ou_jpeg_e_aceito():
    ConfiguracaoJogo(logo_enviado=_uri_de_logo("image/png"))
    ConfiguracaoJogo(logo_enviado=_uri_de_logo("image/jpeg"))


def test_logo_em_outro_formato_e_rejeitado():
    with pytest.raises(ValueError, match="PNG ou JPEG"):
        ConfiguracaoJogo(logo_enviado=_uri_de_logo("image/gif"))
    with pytest.raises(ValueError, match="PNG ou JPEG"):
        ConfiguracaoJogo(logo_enviado="data:text/plain;base64,bXVpdG8=")


def test_logo_acima_do_limite_de_tamanho():
    with pytest.raises(ValueError, match="o limite é 2 MB"):
        ConfiguracaoJogo(logo_enviado=_uri_de_logo(bytes_extra=3 * 1024 * 1024))


def test_data_uri_malformado():
    with pytest.raises(ValueError, match="formato reconhecido"):
        ConfiguracaoJogo(logo_enviado="data:image/png;base64")
