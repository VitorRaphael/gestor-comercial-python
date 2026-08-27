"""Relatórios: abas Histórico Diário (fechamentos) e Dashboard Mensal.

Só monta as duas sub-telas; navegação e permissão de acesso continuam sendo
decisão de `MainWindow`, igual às outras views (§ arquitetura, camadas). Cada
aba só carrega dados quando é aberta pela primeira vez — troca de aba nunca
dispara consulta se a aba já tiver sido vista antes nesta visita à tela.
"""

from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.views.dashboard_mensal_view import DashboardMensalView
from gestor_comercial.ui.views.historico_caixa_view import HistoricoCaixaView

_ABA_HISTORICO = 0
_ABA_DASHBOARD = 1


class RelatoriosView(QWidget):
    """Contêiner das duas visões de relatório, com carregamento sob demanda por aba."""

    def __init__(
        self,
        caixa_service: CaixaService,
        auth_service: AuthService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._historico_view = HistoricoCaixaView(caixa_service, auth_service, impressao_service)
        self._dashboard_view = DashboardMensalView(caixa_service)
        self._abas_carregadas: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._abas = QTabWidget()
        self._abas.addTab(self._historico_view, "Histórico Diário")
        self._abas.addTab(self._dashboard_view, "Histórico Mensal")
        self._abas.currentChanged.connect(self._ao_trocar_aba)
        layout.addWidget(self._abas)

    def atualizar(self) -> None:
        """Chamada pela navegação ao entrar na tela: recarrega só a aba visível."""
        self._abas_carregadas.clear()
        self._ao_trocar_aba(self._abas.currentIndex())

    def _ao_trocar_aba(self, indice: int) -> None:
        if indice in self._abas_carregadas:
            return
        self._abas_carregadas.add(indice)
        if indice == _ABA_HISTORICO:
            self._historico_view.atualizar()
        elif indice == _ABA_DASHBOARD:
            self._dashboard_view.atualizar()
