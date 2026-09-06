"""As cores das telas acompanham a troca de tema. Ver §3.15.

O defeito do §3.15: ~11 cópias de `setStyleSheet(f"color: {tokens[...]}")`
resolvidas **na construção** da tela. Como stylesheet por widget tem
precedência sobre o QSS global, a paleta do boot vencia para sempre naquelas
linhas — alternar Claro/Escuro repintava o app inteiro, menos elas. O usuário
via texto de erro vermelho-escuro sobre fundo claro e legendas cinza-de-tema-
escuro no meio do tema claro.

A correção foi levar a cor ao QSS global e deixar no código só o `objectName`
ou a propriedade de estado. Estes testes provam as duas metades: que o
mecanismo é real (o teste de premissa) e que as telas de verdade adotaram.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QLabel, QWidget

import gestor_comercial.ui as pacote_ui
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.views.comanda_view import ComandaView
from gestor_comercial.ui.views.mesas_view import MesasView

RAIZ_UI = Path(pacote_ui.__file__).parent


@pytest.fixture
def tema(qapp):
    """Controlador com o QSS global aplicado, e o tema escuro de volta no fim."""
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield controlador
    finally:
        controlador.alternar_para(False)


def _cor(widget: QWidget) -> str:
    """A cor com que o widget vai desenhar o texto, depois do QSS aplicado."""
    return widget.palette().color(QPalette.ColorRole.WindowText).name()


def test_premissa_stylesheet_no_widget_congela_a_cor(qapp, tema):
    """O mecanismo do defeito, isolado: quem pinta no widget vence o QSS global
    e não muda mais. Enquanto este teste passar, o §3.15 tem razão de existir."""
    pai = QWidget()
    congelado = QLabel("erro", pai)
    congelado.setStyleSheet(f"color: {tema.tokens_atuais['perigo']};")
    pai.show()
    qapp.processEvents()
    antes = _cor(congelado)

    tema.alternar_para(True)
    qapp.processEvents()

    assert _cor(congelado) == antes, "a premissa mudou: stylesheet no widget passou a seguir o tema"


def test_a_linha_de_erro_do_qss_global_acompanha_o_tema(qapp, tema):
    """A mesma linha, agora pintada pelo QSS global."""
    pai = QWidget()
    rotulo = QLabel("erro", pai)
    rotulo.setObjectName("labelErro")
    pai.show()
    qapp.processEvents()
    escuro = _cor(rotulo)

    tema.alternar_para(True)
    qapp.processEvents()

    assert _cor(rotulo) != escuro, "a linha de erro continua com a cor do tema anterior"


@pytest.mark.parametrize("tela", ["Mesas", "Caixa", "Comanda"])
def test_a_linha_de_erro_das_telas_reais_acompanha_o_tema(
    qapp, tema, comandas, cardapio, caixas_service, impressao, funcionarios, tela
):
    """Nas telas montadas de verdade — é aqui que um `setStyleSheet` reaparecendo
    num `_label_erro` novo seria pego."""
    view = {
        "Mesas": lambda: MesasView(comandas),
        "Caixa": lambda: CaixaView(caixas_service, impressao),
        "Comanda": lambda: ComandaView(comandas, cardapio, impressao, funcionarios),
    }[tela]()
    view.show()
    qapp.processEvents()
    escuro = _cor(view._label_erro)

    tema.alternar_para(True)
    qapp.processEvents()

    assert view._label_erro.styleSheet() == "", (
        f"{tela} voltou a pintar a linha de erro no próprio widget: "
        f"{view._label_erro.styleSheet()!r}"
    )
    assert _cor(view._label_erro) != escuro, f"a linha de erro de {tela} não seguiu o tema"


def test_nenhuma_cor_de_tema_volta_para_setstylesheet():
    """A varredura de adoção: `setStyleSheet` não pode mais ler a paleta.

    `tokens_atuais` dentro de um `setStyleSheet` é exatamente a assinatura do
    defeito — a cor é resolvida uma vez e nunca mais. Lê-la fora de um
    `setStyleSheet` continua válido (`QColor` de `QPainter` e de
    `QTableWidgetItem` é recalculado a cada refresh, não congela).
    """
    infratores: list[str] = []
    for caminho in sorted(RAIZ_UI.rglob("*.py")):
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        relativo = caminho.relative_to(RAIZ_UI).as_posix()
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
                continue
            if no.func.attr != "setStyleSheet":
                continue
            if "tokens_atuais" in ast.unparse(no):
                infratores.append(f"{relativo}:{no.lineno}")

    assert not infratores, (
        "cor de tema congelada em setStyleSheet (§3.15):\n  " + "\n  ".join(infratores)
    )
