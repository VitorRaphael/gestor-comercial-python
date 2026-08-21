"""Tela inicial do PDV: grid de mesas + balcão — porte visual de
`.grid-mesas`/`.mesa-card` do front-end web (`GESTOR COMERCIAL/.../desktop/css/style.css`)
e da lógica de `carregarMesas`/`abrirComandaDaMesa`/`abrirComandaBalcao` (`.../desktop/js/app.js`).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.enums import StatusMesa
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)

_LARGURA_MIN_CARD = 120
_ESPACAMENTO = 14


class MesasView(QWidget):
    """Grid de mesas (livre/ocupada) + botão de balcão. Emite `comanda_aberta` ao abrir uma."""

    comanda_aberta = Signal(object)

    def __init__(self, comanda_service: ComandaService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._comanda_service = comanda_service
        self._botoes_por_mesa: dict[int, QPushButton] = {}

        self._montar_layout()
        self.carregar_mesas()

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)

        barra_topo = QHBoxLayout()
        titulo = QLabel("Mesas")
        titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        barra_topo.addWidget(titulo)

        self._label_legenda = QLabel("")
        self._label_legenda.setProperty("variante", "fraco")
        barra_topo.addWidget(self._label_legenda)
        barra_topo.addStretch()

        self._botao_balcao = QPushButton("Balcão")
        self._botao_balcao.setObjectName("btn-balcao")
        self._botao_balcao.setProperty("variante", "primario")
        self._botao_balcao.clicked.connect(self._abrir_balcao)
        barra_topo.addWidget(self._botao_balcao)

        layout_externo.addLayout(barra_topo)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout_externo.addWidget(self._label_erro)

        self._grade = QGridLayout()
        self._grade.setSpacing(_ESPACAMENTO)

        conteudo_scroll = QWidget()
        conteudo_scroll.setLayout(self._grade)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(conteudo_scroll)
        layout_externo.addWidget(scroll)

    def carregar_mesas(self) -> None:
        for botao in self._botoes_por_mesa.values():
            self._grade.removeWidget(botao)
            botao.deleteLater()
        self._botoes_por_mesa.clear()

        mesas = self._comanda_service.listar_mesas()
        ocupadas = 0
        for mesa in mesas:
            ocupada = mesa.status is StatusMesa.OCUPADA
            if ocupada:
                ocupadas += 1
            botao = QPushButton(f"{mesa.numero}\n{'ocupada' if ocupada else 'livre'}")
            botao.setProperty("variante", "mesa")
            botao.setProperty("ocupada", "true" if ocupada else "false")
            botao.clicked.connect(lambda _checked=False, m=mesa: self._abrir_mesa(m))
            self._botoes_por_mesa[mesa.id] = botao

        self._label_legenda.setText(f"{len(mesas)} mesas • {ocupadas} ocupadas")
        self._reorganizar_grade()

    def _abrir_mesa(self, mesa: Mesa) -> None:
        self._label_erro.setText("")
        try:
            comanda = self._comanda_service.abrir_por_mesa(mesa.id)
        except (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError) as erro:
            self._label_erro.setText(str(erro))
            return
        self.carregar_mesas()
        self.comanda_aberta.emit(comanda)

    def _abrir_balcao(self) -> None:
        self._label_erro.setText("")
        try:
            comanda = self._comanda_service.abrir_balcao()
        except (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError) as erro:
            self._label_erro.setText(str(erro))
            return
        self.comanda_aberta.emit(comanda)

    def _reorganizar_grade(self) -> None:
        largura = self.width()
        colunas = max(1, (largura + _ESPACAMENTO) // (_LARGURA_MIN_CARD + _ESPACAMENTO))
        for indice, botao in enumerate(self._botoes_por_mesa.values()):
            linha, coluna = divmod(indice, colunas)
            self._grade.addWidget(botao, linha, coluna)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reorganizar_grade()
