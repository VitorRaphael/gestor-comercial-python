"""O card "garçom responsável" da tela da mesa (§9.27).

No mockup ele é um cartão com o avatar, o nome e "Garçom responsável". Na tela
antiga era a linha "Atendeu:" com um combo — e o combo era repovoado com a lista
inteira de funcionários a CADA recarga da comanda, ou seja, a cada item lançado
pelo modal "Adicionar item": uma consulta por item, para mostrar um nome que
quase nunca muda.

Aqui o nome é o do instantâneo (`PainelDaComanda.atendente_nome`), sem consulta,
e a lista só é lida quando o operador abre o combo (`showPopup`). Trocar o
garçom continua sendo um clique no nome, como antes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.ui.widgets.cardapio_cartoes import GLIFO_PESSOA, badge_com_glifo

# (id, nome) de quem pode ser escolhido — o id `None` é "ninguém".
OpcaoDeGarcom = tuple[int | None, str]

SEM_GARCOM = "Sem garçom"
_CARGO_PADRAO = "Garçom"


class _ComboPreguicoso(QComboBox):
    """Combo que só pede a lista de opções quando vai abri-la."""

    def __init__(self, opcoes: Callable[[], Sequence[OpcaoDeGarcom]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._opcoes = opcoes

    def carregar_opcoes(self) -> None:
        """Troca o item único pela lista inteira, mantendo quem está escolhido."""
        atual = self.currentData()
        self.blockSignals(True)
        try:
            self.clear()
            for funcionario_id, nome in self._opcoes():
                self.addItem(nome, funcionario_id)
            indice = self.findData(atual)
            self.setCurrentIndex(indice if indice >= 0 else 0)
        finally:
            self.blockSignals(False)

    @nao_deixa_escapar()
    def showPopup(self) -> None:  # noqa: N802 (override Qt)
        self.carregar_opcoes()
        super().showPopup()


class SeletorDeGarcom(QFrame):
    """O cartão do garçom: avatar, nome clicável e o cargo embaixo."""

    # O id do funcionário escolhido, ou None para "ninguém". Só dispara pela mão
    # do operador (`activated`), nunca quando a tela mostra outra comanda.
    garcom_escolhido = Signal(object)

    def __init__(
        self, opcoes: Callable[[], Sequence[OpcaoDeGarcom]], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mesaDetGarcom")
        linha = QHBoxLayout(self)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)
        linha.addWidget(
            badge_com_glifo(GLIFO_PESSOA, "mesaDetBadge", "mesa_detalhe_badge_glifo", lado=36, lado_glifo=16),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        textos = QVBoxLayout()
        textos.setSpacing(0)
        self._combo = _ComboPreguicoso(opcoes)
        self._combo.setObjectName("mesaDetGarcomNome")
        self._combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._combo.setToolTip("Clique para trocar quem está atendendo a mesa.")
        self._combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._combo.activated.connect(self._ao_escolher)
        textos.addWidget(self._combo)
        self._cargo = QLabel("")
        self._cargo.setObjectName("mesaDetGarcomCargo")
        textos.addWidget(self._cargo)
        linha.addLayout(textos)

    @property
    def combo(self) -> _ComboPreguicoso:
        return self._combo

    def mostrar(self, funcionario_id: int | None, nome: str | None, cargo: str | None) -> None:
        """Mostra quem atende, sem ler o banco: um item só, o do instantâneo."""
        self._combo.blockSignals(True)
        try:
            self._combo.clear()
            self._combo.addItem(nome or SEM_GARCOM, funcionario_id)
        finally:
            self._combo.blockSignals(False)
        self._cargo.setText(
            f"{cargo or _CARGO_PADRAO} responsável" if funcionario_id is not None else "Clique para escolher"
        )

    def _ao_escolher(self, indice: int) -> None:
        self.garcom_escolhido.emit(self._combo.itemData(indice))
