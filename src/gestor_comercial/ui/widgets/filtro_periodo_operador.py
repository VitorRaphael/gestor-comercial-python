"""Barra de filtro das telas de Relatórios: pílulas de operador à esquerda,
seletor de mês à direita.

As duas telas (Histórico Diário e Dashboard Mensal) montavam esta barra com
código idêntico e guardavam o estado do filtro em três atributos cada uma
(§6, Fase 6). O componente passa a ser o dono desse estado, e as telas só
perguntam o que está selecionado e reagem aos dois sinais.

Nenhuma pílula vem destacada ao abrir a tela — só depois que o usuário de fato
clica em uma delas (igual ao seletor de operador do Login). O filtro em si já
funciona como "Todos" desde o início; só o destaque visual espera o clique.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.ui.widgets.layout_utils import limpar_layout

# Sentinela do item "Todos" — combina com o `userData` de cada pílula, que
# também guarda `int` de verdade para cada funcionário.
TODOS_OS_OPERADORES = None

_ROTULO_TODOS = "Todos"
_MESES_NO_SELETOR = 12

_MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


class FiltroPeriodoOperador(QWidget):
    """Pílulas de operador + seletor de mês, com o estado do filtro dentro."""

    periodo_mudou = Signal(int)
    operador_mudou = Signal()

    def __init__(
        self,
        funcionario_service: FuncionarioService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # Sem objectName este QWidget herdaria a regra global
        # `QWidget { background: bg_marca }` e pintaria um retângulo por trás
        # da barra — mesmo motivo do `SecaoCancelamentos` (ver qss_app.py).
        self.setObjectName("relatoriosFiltro")
        self._funcionarios = funcionario_service
        self._operador_selecionado: int | None = TODOS_OS_OPERADORES
        self._nome_operador_selecionado = _ROTULO_TODOS
        self._algum_operador_clicado = False

        linha = QHBoxLayout(self)
        # Margem zero: antes esta barra era um `QHBoxLayout` aninhado, que no
        # Qt já nasce sem margem. Um layout instalado num widget herda a
        # margem do estilo — sem esta linha a barra desceria alguns pixels.
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(8)

        self._layout_pills_operador = QHBoxLayout()
        self._layout_pills_operador.setSpacing(8)
        linha.addLayout(self._layout_pills_operador)
        linha.addStretch()

        frame_mes = QFrame()
        frame_mes.setObjectName("relatoriosFiltroMes")
        layout_mes = QHBoxLayout(frame_mes)
        layout_mes.setContentsMargins(12, 4, 8, 4)
        layout_mes.setSpacing(4)
        icone = QLabel("📅")
        icone.setObjectName("relatoriosFiltroMesIcone")
        layout_mes.addWidget(icone)
        self._seletor_mes = QComboBox()
        self._seletor_mes.setObjectName("relatoriosComboMes")
        self._popular_seletor_mes()
        self._seletor_mes.currentIndexChanged.connect(self.periodo_mudou)
        layout_mes.addWidget(self._seletor_mes)
        linha.addWidget(frame_mes)

    # ------------------------------------------------------------------
    # Estado do filtro
    # ------------------------------------------------------------------

    def ano_mes(self) -> tuple[int, int] | None:
        """`(ano, mês)` do item selecionado, ou `None` se o seletor está vazio."""
        return self._seletor_mes.currentData()

    def texto_periodo(self) -> str:
        return self._seletor_mes.currentText()

    def operador_id(self) -> int | None:
        return self._operador_selecionado

    def nome_operador(self) -> str:
        return self._nome_operador_selecionado

    def conectar_mudanca_periodo(self, callback: Callable[[int], None]) -> None:
        self.periodo_mudou.connect(callback)

    # ------------------------------------------------------------------
    # Montagem / atualização
    # ------------------------------------------------------------------

    def atualizar_operadores(self) -> None:
        """Reconstrói as pílulas do zero: um funcionário desativado ou
        cadastrado entre duas visitas à tela tem que aparecer do jeito certo —
        e o histórico de quem foi desativado continua sendo dele."""
        selecionado = self._operador_selecionado
        limpar_layout(self._layout_pills_operador)

        opcoes: list[tuple[str, int | None]] = [(_ROTULO_TODOS, TODOS_OS_OPERADORES)]
        opcoes.extend(
            (operador.nome, operador.id) for operador in self._funcionarios.listar_operadores_caixa()
        )
        if selecionado not in (valor for _, valor in opcoes):
            selecionado = TODOS_OS_OPERADORES

        for nome, valor in opcoes:
            pill = QPushButton(nome)
            pill.setProperty("variante", "filtro-pill")
            pill.setProperty("ativo", self._algum_operador_clicado and valor == selecionado)
            pill.clicked.connect(lambda _=False, v=valor: self._selecionar_operador(v))
            self._layout_pills_operador.addWidget(pill)
            if valor == selecionado:
                self._nome_operador_selecionado = nome
        self._operador_selecionado = selecionado

    def _selecionar_operador(self, operador_id: int | None) -> None:
        self._operador_selecionado = operador_id
        self._algum_operador_clicado = True
        self.atualizar_operadores()
        self.operador_mudou.emit()

    def _popular_seletor_mes(self) -> None:
        # Mês vigente sempre entra primeiro, mesmo sem nenhum fechamento ainda —
        # é o caso normal de abrir o relatório no primeiro dia do mês novo.
        hoje = date.today()
        self._seletor_mes.blockSignals(True)
        self._seletor_mes.clear()
        self._seletor_mes.addItem(f"{_MESES[hoje.month - 1]}/{hoje.year}", (hoje.year, hoje.month))
        ano, mes = hoje.year, hoje.month
        for _ in range(_MESES_NO_SELETOR - 1):
            mes -= 1
            if mes == 0:
                mes = 12
                ano -= 1
            self._seletor_mes.addItem(f"{_MESES[mes - 1]}/{ano}", (ano, mes))
        self._seletor_mes.blockSignals(False)
