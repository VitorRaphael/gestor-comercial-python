"""Tela de Configurações: preferências gerais do app.

Hoje só tem a seção "Selecionar Tema" (claro/escuro), que antes vivia
duplicada na tela de Login e no rodapé da sidebar (ver `ThemeController`).
Centralizar aqui evita repetir o mesmo alternador em dois lugares e dá
espaço para futuras preferências sem inchar o rodapé do menu lateral.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.ui.theme.controller import ThemeController


class ConfiguracoesView(QWidget):
    """Central de preferências do app -- por enquanto, só o tema."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(4)

        eyebrow = QLabel("PREFERÊNCIAS")
        eyebrow.setObjectName("configEyebrow")
        layout.addWidget(eyebrow)

        titulo = QLabel("Configurações")
        titulo.setObjectName("configTitulo")
        layout.addWidget(titulo)

        subtitulo = QLabel("Preferências gerais do sistema")
        subtitulo.setObjectName("configSubtitulo")
        layout.addWidget(subtitulo)

        layout.addSpacing(28)

        secao_titulo = QLabel("SELECIONAR TEMA")
        secao_titulo.setObjectName("configSecaoTitulo")
        layout.addWidget(secao_titulo)
        layout.addSpacing(10)

        cartao = QFrame()
        cartao.setObjectName("configCard")
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(20, 20, 20, 20)
        cartao_layout.setSpacing(10)

        descricao = QLabel("Escolha a aparência usada em todas as telas do sistema.")
        descricao.setProperty("variante", "fraco")
        cartao_layout.addWidget(descricao)

        pilula = QFrame()
        pilula.setProperty("variante", "pilula-tema")
        pilula.setFixedWidth(280)
        layout_pilula = QHBoxLayout(pilula)
        layout_pilula.setContentsMargins(3, 3, 3, 3)
        layout_pilula.setSpacing(0)

        botao_claro = QPushButton("MODO CLARO")
        botao_escuro = QPushButton("MODO ESCURO")
        for botao in (botao_claro, botao_escuro):
            botao.setProperty("variante", "temaBotao")
            botao.setCheckable(True)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            layout_pilula.addWidget(botao)

        controlador = ThemeController.instancia()
        grupo = QButtonGroup(self)
        grupo.setExclusive(True)
        grupo.addButton(botao_claro)
        grupo.addButton(botao_escuro)
        botao_claro.setChecked(controlador.claro)
        botao_escuro.setChecked(not controlador.claro)
        botao_claro.toggled.connect(lambda marcado: marcado and controlador.alternar_para(True))
        botao_escuro.toggled.connect(lambda marcado: marcado and controlador.alternar_para(False))
        controlador.mudou.connect(lambda _tokens: botao_claro.setChecked(controlador.claro))

        cartao_layout.addWidget(pilula)
        layout.addWidget(cartao)

        layout.addStretch()
