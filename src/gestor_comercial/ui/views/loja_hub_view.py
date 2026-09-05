"""Central de Loja: hub administrativo com os módulos de configuração da
operação, organizados por área em cards.

Agrupa Cardápio, Estoque, Impressoras, Funcionários, Relatórios e
Configurações atrás de um único ponto de entrada com PIN na sidebar (ver
`MainWindow._abrir_area_loja`). Não tem botão de saída próprio -- voltar ao
PDV é só clicar em "Mesas" na sidebar, como qualquer outra tela do shell.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gestor_comercial.ui.widgets.flow_layout import FlowLayout

# (rótulo, subtítulo, glifo do ícone)
_SECAO_CATALOGO = (
    ("Cardápio", "Categorias, produtos, preços e combos", "C"),
    ("Estoque", "Insumos, saldos mínimos e custo", "E"),
    ("Impressoras", "Recibo, produção e impressora padrão", "⎙"),
)
_SECAO_EQUIPE = (
    ("Funcionários", "Cargos, status e consumo interno", "F"),
    ("Relatórios", "Histórico de turnos e faturamento", "▤"),
    ("Configurações", "Seleção de temas e preferências gerais", "⚙"),
)


class _CardModulo(QFrame):
    """Card clicável de um módulo administrativo -- QFrame em vez de
    QPushButton porque o layout interno (ícone + título + subtítulo) não
    cabe direito dentro do padding fixo de um botão comum."""

    clicado = Signal()

    def __init__(self, rotulo: str, subtitulo: str, glifo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("variante", "loja-hub-card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(300)
        self.setMinimumHeight(84)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        icone = QLabel(glifo)
        icone.setProperty("variante", "loja-hub-icone")
        icone.setFixedSize(48, 48)
        icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icone)

        bloco_texto = QVBoxLayout()
        bloco_texto.setSpacing(3)
        titulo = QLabel(rotulo)
        titulo.setProperty("variante", "loja-hub-card-titulo")
        bloco_texto.addWidget(titulo)
        sub = QLabel(subtitulo)
        sub.setProperty("variante", "loja-hub-card-subtitulo")
        sub.setWordWrap(True)
        bloco_texto.addWidget(sub)
        layout.addLayout(bloco_texto, 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
        super().mousePressEvent(event)


class LojaHubView(QWidget):
    destino_selecionado = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(4)

        self._breadcrumb = QLabel("GERENTE")
        self._breadcrumb.setObjectName("centralLojaBreadcrumb")
        layout.addWidget(self._breadcrumb)

        titulo = QLabel("Central de Loja")
        titulo.setObjectName("centralLojaTitulo")
        layout.addWidget(titulo)

        subtitulo = QLabel("Tudo que configura a operação — organizado por área")
        subtitulo.setObjectName("centralLojaSubtitulo")
        layout.addWidget(subtitulo)

        layout.addSpacing(28)
        layout.addWidget(self._montar_secao("CATÁLOGO E PRODUÇÃO", _SECAO_CATALOGO))
        layout.addSpacing(24)
        layout.addWidget(self._montar_secao("EQUIPE, RESULTADOS E SISTEMA", _SECAO_EQUIPE))

        layout.addStretch()

    def _montar_secao(self, titulo: str, destinos: tuple[tuple[str, str, str], ...]) -> QWidget:
        secao = QWidget()
        layout = QVBoxLayout(secao)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        rotulo_secao = QLabel(titulo)
        rotulo_secao.setObjectName("centralLojaSecaoTitulo")
        layout.addWidget(rotulo_secao)

        grade = QWidget()
        fluxo = FlowLayout(grade, spacing=12)
        for rotulo, subtitulo, glifo in destinos:
            card = _CardModulo(rotulo, subtitulo, glifo)
            card.clicado.connect(lambda r=rotulo: self.destino_selecionado.emit(r))
            fluxo.addWidget(card)
        layout.addWidget(grade)

        return secao

    def definir_usuario(self, nome_perfil: str) -> None:
        """`nome_perfil` já vem formatado (ex.: "GERENTE · VITOR"), igual ao
        breadcrumb do mockup -- ver `MainWindow._ao_logar`."""
        self._breadcrumb.setText(nome_perfil)
