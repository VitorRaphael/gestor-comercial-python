"""Token de tema em `rgba()` vira a cor certa quando pintado com `QPainter`. §9.11.

A paleta foi escrita para o QSS, que entende `rgba(255, 255, 255, 0.08)`. O
`QColor` do Qt não entende: devolve uma cor inválida, que pinta como preto
opaco, sem erro. Achado ao desenhar o Cardápio em cartões, e já estava no app:
a borda do placeholder das miniaturas saía preta no tema escuro.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor

from gestor_comercial.ui.theme import tokens
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token
from gestor_comercial.ui.widgets import thumbnail_cache


def test_premissa_o_qcolor_nao_entende_rgba_do_css():
    """Enquanto isto passar, `cor_do_token` tem razão de existir."""
    assert QColor("rgba(255, 255, 255, 0.08)").isValid() is False


@pytest.mark.parametrize(
    ("valor", "rgb", "alfa"),
    [
        ("rgba(255, 255, 255, 0.08)", (255, 255, 255), 20),
        ("rgba(229, 169, 60, 0.22)", (229, 169, 60), 56),
        ("rgb(1, 2, 3)", (1, 2, 3), 255),
        ("#DC2626", (220, 38, 38), 255),
    ],
)
def test_cor_do_token_entende_as_duas_grafias(valor, rgb, alfa):
    cor = cor_do_token(valor)

    assert cor.isValid()
    assert (cor.red(), cor.green(), cor.blue()) == rgb
    assert cor.alpha() == alfa


@pytest.mark.parametrize("paleta", [tokens.TEMA_ESCURO, tokens.TEMA_CLARO], ids=["escuro", "claro"])
def test_todo_token_da_paleta_vira_uma_cor_valida(paleta):
    """Nenhum token pode chegar ao `QPainter` como preto por engano."""
    invalidos = sorted(nome for nome, valor in paleta.items() if not cor_do_token(valor).isValid())

    assert not invalidos, f"tokens que não viram cor: {invalidos}"


def test_a_borda_do_placeholder_nao_sai_mais_preta_no_escuro(qapp):
    """O placeholder é o que o cardápio real mostra em quase todo produto (poucos
    têm foto). A borda dele é `borda_card`, que no escuro é branco a 8% — e
    saía preta opaca, escurecendo o contorno em vez de clareá-lo."""
    ThemeController.instancia().alternar_para(False)
    thumbnail_cache.limpar()
    tamanho = 36

    imagem = thumbnail_cache.obter_pixmap(None, tamanho, "Arroz").toImage()

    fundo = cor_do_token(tokens.TEMA_ESCURO["superficie_2"])
    borda = imagem.pixelColor(1, tamanho // 2)
    assert borda.red() > fundo.red(), (
        f"a borda do placeholder saiu {borda.name()} sobre o fundo {fundo.name()} — escureceu"
    )
