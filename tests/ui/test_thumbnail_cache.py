"""Cache de miniaturas: a chave, o teto e a virada de tema. Ver §3.10.

O §3.10 abriu com uma boa notícia — o cache **já** tinha LRU com teto rígido de
200 entradas, do jeito que o briefing pedia. O defeito estava na chave:
`(imagem_path, tamanho)`, sem a inicial. Como o `imagem_path` de todo produto
sem foto é o mesmo `None`, todos caíam na mesma entrada, e o primeiro a ser
desenhado emprestava a letra dele para o cardápio inteiro:

    Coca-Cola e Xis Salada devolvem o MESMO objeto? True

No balcão isso é a Coca-Cola aparecendo com um "X" na tela do cardápio.

O segundo defeito, registrado junto: o placeholder é pintado com as cores do
tema, mas o cache não tinha como saber que o tema virou — os quadrados escuros
ficavam no meio do tema claro até alguém reiniciar o app.
"""

from __future__ import annotations

import pytest

from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import thumbnail_cache
from gestor_comercial.ui.widgets.thumbnail_cache import LIMITE_ENTRADAS, obter_pixmap

TAMANHO = 64


@pytest.fixture(autouse=True)
def cache_limpo(qapp):
    """O cache é estado de módulo: sem zerar, um teste contamina o outro.

    Zera também `_tema_do_cache`, senão a primeira miniatura de cada teste
    acharia que o tema acabou de virar.
    """
    def _zerar() -> None:
        thumbnail_cache.limpar()
        thumbnail_cache._tema_do_cache = None

    _zerar()
    controlador = ThemeController.instancia()
    try:
        yield
    finally:
        controlador.alternar_para(False)
        _zerar()


def test_produtos_sem_foto_nao_dividem_a_mesma_entrada(qapp):
    """O bug do §3.10, direto: dois produtos sem foto, duas miniaturas."""
    coca = obter_pixmap(None, TAMANHO, "Coca-Cola")
    xis = obter_pixmap(None, TAMANHO, "Xis Salada")

    assert coca is not xis, "os dois produtos sem foto voltaram a dividir a mesma entrada"


def test_a_inicial_desenhada_e_a_que_entra_na_chave(qapp):
    """`is not` sozinho provaria pouco: duas entradas separadas ainda poderiam
    ser desenhadas com a mesma letra. O que amarra as duas pontas é a chave
    carregar exatamente a inicial que o desenho usa — por isso `_inicial()` é
    uma função só, chamada nos dois lugares.

    A comparação óbvia — `pixmap.toImage()` de um contra o do outro — **não
    serve aqui**, e vale registrar para ninguém tentar de novo: a suíte roda na
    plataforma `offscreen`, que não rasteriza texto. Os dois placeholders saem
    byte a byte idênticos ali (só o retângulo arredondado é pintado) e voltam a
    diferir na plataforma `windows`. Um teste de pixel passaria verde com o bug
    do §3.10 de volta.
    """
    for nome in ("Coca-Cola", "Xis Salada", "Batata"):
        obter_pixmap(None, TAMANHO, nome)

    iniciais = {chave[2] for chave in thumbnail_cache._cache}

    assert iniciais == {"C", "X", "B"}, f"a chave não carrega a inicial do produto: {iniciais}"


def test_produtos_com_a_mesma_inicial_reaproveitam_a_entrada(qapp):
    """O outro lado da chave: a inicial é o que o desenho usa, então "Batata" e
    "Brahma" podem — e devem — compartilhar o mesmo "B" já pintado."""
    batata = obter_pixmap(None, TAMANHO, "Batata")
    brahma = obter_pixmap(None, TAMANHO, "Brahma")

    assert batata is brahma


def test_o_mesmo_produto_no_mesmo_tamanho_volta_do_cache(qapp):
    """A razão de o cache existir: sem isto, cada repaint redesenha tudo."""
    primeira = obter_pixmap(None, TAMANHO, "Coca-Cola")
    segunda = obter_pixmap(None, TAMANHO, "Coca-Cola")

    assert primeira is segunda


def test_tamanhos_diferentes_sao_entradas_diferentes(qapp):
    assert obter_pixmap(None, 32, "Coca-Cola") is not obter_pixmap(None, 64, "Coca-Cola")


def test_a_virada_de_tema_invalida_os_placeholders(qapp):
    """Placeholder é pintado com `superficie_2`/`borda_card`/`texto_fraquissimo`.
    Depois de acender o modo claro, a miniatura não pode voltar com as cores do
    tema escuro."""
    escuro = obter_pixmap(None, TAMANHO, "Coca-Cola").toImage()

    ThemeController.instancia().alternar_para(True)
    claro = obter_pixmap(None, TAMANHO, "Coca-Cola").toImage()

    assert claro != escuro, "o placeholder voltou do cache com as cores do tema anterior"


def test_o_teto_de_entradas_continua_valendo(qapp):
    """O que o §3.10 elogiou e não pode ser perdido na correção da chave: numa
    tela que fica horas aberta, o cache não pode crescer sem fim."""
    for indice in range(LIMITE_ENTRADAS + 50):
        obter_pixmap(None, TAMANHO, f"Produto {indice}")

    assert len(thumbnail_cache._cache) <= LIMITE_ENTRADAS


def test_a_entrada_mais_usada_sobrevive_ao_despejo(qapp):
    """LRU de verdade: quem foi pedido agora não pode ser o primeiro a sair."""
    obter_pixmap(None, TAMANHO, "Ancora")
    for indice in range(LIMITE_ENTRADAS - 1):
        obter_pixmap(None, TAMANHO, f"Produto {indice}")
    ancora = obter_pixmap(None, TAMANHO, "Ancora")  # volta para o fim da fila

    for indice in range(50):
        obter_pixmap(None, TAMANHO, f"Novo {indice}")

    assert obter_pixmap(None, TAMANHO, "Ancora") is ancora
