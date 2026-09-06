"""Relatórios: cabeçalho compartilhado (breadcrumb, título dinâmico, ações) +
alternador segmentado entre Histórico Diário (fechamentos) e Dashboard
Mensal.

Só monta as duas sub-telas; navegação e permissão de acesso continuam sendo
decisão de `MainWindow`, igual às outras views (§ arquitetura, camadas). Cada
aba só carrega dados quando é aberta pela primeira vez — troca de aba nunca
dispara consulta se a aba já tiver sido vista antes nesta visita à tela.

"Ver cancelamentos" e "Reimprimir fechamento" só fazem sentido com um
fechamento selecionado no Histórico Diário — ficam desabilitados no Dashboard
Mensal (não há linha selecionável lá).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.views.dashboard_mensal_view import DashboardMensalView
from gestor_comercial.ui.views.historico_caixa_view import HistoricoCaixaView
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade

_ABA_HISTORICO = 0
_ABA_DASHBOARD = 1

_TITULOS_ABA = {
    _ABA_HISTORICO: "Histórico Diário",
    _ABA_DASHBOARD: "Dashboard Mensal",
}


class RelatoriosView(QWidget):
    """Contêiner das duas visões de relatório, com carregamento sob demanda por aba."""

    def __init__(
        self,
        caixa_service: CaixaService,
        auth_service: AuthService,
        impressao_service: ImpressaoService,
        funcionario_service: FuncionarioService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._historico_view = HistoricoCaixaView(
            caixa_service, auth_service, impressao_service, funcionario_service
        )
        self._dashboard_view = DashboardMensalView(caixa_service, funcionario_service)
        self._abas_carregadas: set[int] = set()

        self._montar_layout()
        self._historico_view.conectar_mudanca_periodo(lambda: self._atualizar_subtitulo(_ABA_HISTORICO))
        self._dashboard_view.conectar_mudanca_periodo(lambda: self._atualizar_subtitulo(_ABA_DASHBOARD))

    def _montar_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        layout.addLayout(self._montar_cabecalho())
        layout.addWidget(self._montar_segmentado())

        self._pilha = QStackedWidget()
        self._pilha.addWidget(self._historico_view)
        self._pilha.addWidget(self._dashboard_view)
        layout.addWidget(self._pilha, 1)

    def _montar_cabecalho(self) -> QHBoxLayout:
        cabecalho = QHBoxLayout()

        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        self._label_breadcrumb = QLabel("GERENTE")
        self._label_breadcrumb.setObjectName("relatoriosBreadcrumb")
        bloco_titulo.addWidget(self._label_breadcrumb)

        self._label_titulo = QLabel(_TITULOS_ABA[_ABA_HISTORICO])
        self._label_titulo.setObjectName("relatoriosTitulo")
        bloco_titulo.addWidget(self._label_titulo)

        self._label_subtitulo = QLabel("")
        self._label_subtitulo.setObjectName("relatoriosSubtitulo")
        bloco_titulo.addWidget(self._label_subtitulo)

        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch()

        self._botao_cancelamentos = QPushButton("Ver cancelamentos")
        self._botao_cancelamentos.setProperty("variante", "pilula-secundario")
        self._botao_cancelamentos.clicked.connect(lambda: self._historico_view.ver_cancelamentos())
        cabecalho.addWidget(self._botao_cancelamentos)

        self._botao_reimprimir = QPushButton("Reimprimir fechamento")
        self._botao_reimprimir.setProperty("variante", "pilula-destaque")
        self._botao_reimprimir.clicked.connect(lambda: self._historico_view.reimprimir())
        cabecalho.addWidget(self._botao_reimprimir)
        return cabecalho

    def _montar_segmentado(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("relatoriosSegmentado")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._botao_aba_historico = QPushButton("🗓️  Histórico Diário")
        self._botao_aba_dashboard = QPushButton("📈  Dashboard Mensal")
        for botao, indice in (
            (self._botao_aba_historico, _ABA_HISTORICO),
            (self._botao_aba_dashboard, _ABA_DASHBOARD),
        ):
            botao.setProperty("variante", "segmento")
            botao.clicked.connect(lambda _=False, i=indice: self._selecionar_aba(i))
            layout.addWidget(botao)
        layout.addStretch()

        frame_wrapper = QHBoxLayout()
        frame_wrapper.addWidget(frame)
        frame_wrapper.addStretch()
        container = QWidget()
        container.setLayout(frame_wrapper)
        return container

    def definir_usuario(self, nome_perfil: str) -> None:
        """`nome_perfil` já vem formatado (ex.: "GERENTE · VITOR"), igual ao
        padrão usado em `LojaHubView`/`ImpressorasView`."""
        self._label_breadcrumb.setText(nome_perfil)

    def atualizar(self) -> None:
        """Chamada pela navegação ao entrar na tela: recarrega só a aba visível."""
        self._abas_carregadas.clear()
        self._selecionar_aba(self._pilha.currentIndex())

    def _selecionar_aba(self, indice: int) -> None:
        self._pilha.setCurrentIndex(indice)
        aplicar_propriedade(self._botao_aba_historico, "ativo", indice == _ABA_HISTORICO)
        aplicar_propriedade(self._botao_aba_dashboard, "ativo", indice == _ABA_DASHBOARD)

        self._label_titulo.setText(_TITULOS_ABA[indice])
        no_historico = indice == _ABA_HISTORICO
        self._botao_cancelamentos.setEnabled(no_historico)
        self._botao_reimprimir.setEnabled(no_historico)

        if indice not in self._abas_carregadas:
            self._abas_carregadas.add(indice)
            if indice == _ABA_HISTORICO:
                self._historico_view.atualizar()
            elif indice == _ABA_DASHBOARD:
                self._dashboard_view.atualizar()
        self._atualizar_subtitulo(indice)

    def _atualizar_subtitulo(self, indice: int) -> None:
        periodo = (
            self._historico_view.periodo_atual()
            if indice == _ABA_HISTORICO
            else self._dashboard_view.periodo_atual()
        )
        self._label_subtitulo.setText(f"{periodo} · unidade Centro")
