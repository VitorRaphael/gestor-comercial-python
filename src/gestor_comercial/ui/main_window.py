"""Janela principal: alterna entre a tela de login e o shell autenticado
(sidebar de navegação + página de conteúdo) — porte da SPA de página única
do front-end web (`GESTOR COMERCIAL/.../desktop/index.html` + `js/app.js`,
onde `mostrarTela()` trocava `.tela-ativa` por CSS) para um `QStackedWidget`
duplo: um para login/shell, outro para as páginas dentro do shell.

As views não se conhecem entre si — cada uma só emite sinais (`autenticado`,
`comanda_aberta`, `voltar`, `pagamento_solicitado`, `comanda_cancelada`) e é
esta janela quem decide para onde navegar. Isso é o que permite testar cada
view isolada, como os testes manuais desta sessão já fizeram.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import PerfilFuncionario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.services.pagamento_service import PagamentoService
from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.views.cardapio_view import CardapioView
from gestor_comercial.ui.views.comanda_view import ComandaView
from gestor_comercial.ui.views.funcionarios_view import FuncionariosView
from gestor_comercial.ui.views.impressoras_view import ImpressorasView
from gestor_comercial.ui.views.login_view import LoginView
from gestor_comercial.ui.views.mesas_view import MesasView
from gestor_comercial.ui.views.pagamento_dialog import PagamentoDialog
from gestor_comercial.ui.views.relatorios_view import RelatoriosView
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao

_ROTULOS_PERFIL = {
    PerfilFuncionario.ATENDENTE: "Atendente",
    PerfilFuncionario.GERENTE: "Gerente",
}

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)


class MainWindow(QMainWindow):
    """Janela única do PDV: login, depois sidebar + páginas."""

    def __init__(
        self,
        auth_service: AuthService,
        comanda_service: ComandaService,
        cardapio_service: CardapioService,
        caixa_service: CaixaService,
        pagamento_service: PagamentoService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gestor Comercial")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)

        self._auth = auth_service
        self._pagamentos = pagamento_service
        self._impressao = impressao_service

        self._pilha_raiz = QStackedWidget()
        self.setCentralWidget(self._pilha_raiz)

        self._login_view = LoginView(auth_service)
        self._login_view.autenticado.connect(self._ao_logar)
        self._pilha_raiz.addWidget(self._login_view)

        self._pilha_raiz.addWidget(
            self._montar_shell(comanda_service, cardapio_service, caixa_service, auth_service)
        )
        self._pilha_raiz.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Montagem do shell autenticado: sidebar + páginas
    # ------------------------------------------------------------------

    def _montar_shell(
        self,
        comanda_service: ComandaService,
        cardapio_service: CardapioService,
        caixa_service: CaixaService,
        auth_service: AuthService,
    ) -> QWidget:
        shell = QWidget()
        layout_shell = QHBoxLayout(shell)
        layout_shell.setContentsMargins(0, 0, 0, 0)
        layout_shell.setSpacing(0)
        layout_shell.addWidget(self._montar_sidebar())

        coluna_direita = QVBoxLayout()
        coluna_direita.setContentsMargins(24, 20, 24, 20)
        coluna_direita.addLayout(self._montar_barra_usuario())

        self._mesas_view = MesasView(comanda_service)
        self._mesas_view.comanda_aberta.connect(self._abrir_comanda)

        self._comanda_view = ComandaView(comanda_service, cardapio_service, self._impressao)
        self._comanda_view.voltar.connect(self._voltar_para_mesas)
        self._comanda_view.comanda_cancelada.connect(self._ao_comanda_cancelada)
        self._comanda_view.pagamento_solicitado.connect(self._abrir_pagamento)

        self._caixa_view = CaixaView(caixa_service, self._impressao)
        self._cardapio_view = CardapioView(cardapio_service)
        self._funcionarios_view = FuncionariosView(auth_service, self._pagamentos)
        self._impressoras_view = ImpressorasView(cardapio_service, self._impressao)
        self._relatorios_view = RelatoriosView(caixa_service, auth_service, self._impressao)

        self._paginas = QStackedWidget()
        for pagina in (
            self._mesas_view,
            self._comanda_view,
            self._caixa_view,
            self._cardapio_view,
            self._funcionarios_view,
            self._impressoras_view,
            self._relatorios_view,
        ):
            self._paginas.addWidget(pagina)
        coluna_direita.addWidget(self._paginas)

        layout_shell.addLayout(coluna_direita)
        return shell

    def _montar_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(4)

        marca = QLabel("Gestor Comercial")
        marca.setStyleSheet("font-weight: 600; font-size: 14px; padding: 0 12px 16px 12px;")
        layout.addWidget(marca)

        # Cada destino recarrega a própria página antes de mostrá-la, para
        # nunca exibir dado velho de quando o app ainda estava no login.
        self._destinos_nav = {
            "Mesas": lambda: (self._mesas_view, self._mesas_view.carregar_mesas),
            "Caixa": lambda: (self._caixa_view, self._caixa_view.atualizar),
            # "Histórico de Fechamentos" foi tirado do menu de propósito: é
            # estrutura interna de auditoria, não deve aparecer navegável no
            # dia a dia (funcionário mal-intencionado ajustando comportamento
            # ao saber que existe é o cenário que essa tela existe pra pegar).
            # Os dados de fechamento continuam sendo gravados normalmente —
            # só não tem UI pra consultar por enquanto. Ver HistoricoCaixaView.
            "Cardápio": lambda: (self._cardapio_view, self._cardapio_view.atualizar),
            "Funcionários": lambda: (self._funcionarios_view, self._funcionarios_view.atualizar),
            "Impressoras": lambda: (self._impressoras_view, self._impressoras_view.atualizar),
        }
        self._botoes_nav: dict[str, QPushButton] = {}
        for rotulo in self._destinos_nav:
            botao = QPushButton(rotulo)
            botao.setProperty("variante", "nav")
            botao.clicked.connect(lambda _checked=False, r=rotulo: self._navegar(r))
            layout.addWidget(botao)
            self._botoes_nav[rotulo] = botao

        layout.addStretch()

        # Relatórios (Histórico Diário + Dashboard Mensal) fica fixo no rodapé,
        # separado da navegação do dia a dia, e só aparece pra gerente — é a
        # mesma estrutura de auditoria que HistoricoCaixaView já protegia
        # ficando fora do menu; aqui ela volta a ficar visível, mas restrita
        # a quem tem perfil pra ver esse tipo de dado (o funcionário comum
        # nunca sabe que essa tela existe).
        self._botao_relatorios = QPushButton("Relatórios")
        self._botao_relatorios.setProperty("variante", "nav")
        self._botao_relatorios.clicked.connect(lambda: self._navegar("Relatórios"))
        self._botao_relatorios.setVisible(False)
        layout.addWidget(self._botao_relatorios)
        self._botoes_nav["Relatórios"] = self._botao_relatorios
        self._destinos_nav["Relatórios"] = lambda: (self._relatorios_view, self._relatorios_view.atualizar)

        botao_sair = QPushButton("Sair")
        botao_sair.setProperty("variante", "nav")
        botao_sair.clicked.connect(self._deslogar)
        layout.addWidget(botao_sair)

        return sidebar

    def _montar_barra_usuario(self) -> QHBoxLayout:
        barra = QHBoxLayout()
        self._label_usuario = QLabel("")
        self._label_usuario.setProperty("variante", "fraco")
        barra.addWidget(self._label_usuario)
        barra.addStretch()

        # Barra de status do shell. O recibo do cliente sai depois que a comanda
        # fecha, e nesse instante a tela já voltou para Mesas — sem um lugar fixo
        # aqui em cima, o operador nunca saberia se o cupom saiu ou não.
        self._aviso_impressao = AvisoDeImpressao()
        barra.addWidget(self._aviso_impressao)
        return barra

    # ------------------------------------------------------------------
    # Navegação dentro do shell
    # ------------------------------------------------------------------

    def _navegar(self, rotulo: str) -> None:
        pagina, recarregar = self._destinos_nav[rotulo]()
        recarregar()
        self._mostrar_pagina(pagina)
        self._marcar_nav_ativo(rotulo)

    def _mostrar_pagina(self, pagina: QWidget) -> None:
        self._paginas.setCurrentWidget(pagina)

    def _marcar_nav_ativo(self, rotulo: str | None) -> None:
        for nome, botao in self._botoes_nav.items():
            botao.setProperty("ativo", "true" if nome == rotulo else "false")
            botao.style().unpolish(botao)
            botao.style().polish(botao)

    def _abrir_comanda(self, comanda: Comanda) -> None:
        self._comanda_view.carregar_comanda(comanda)
        self._mostrar_pagina(self._comanda_view)
        # Comanda é uma tela de detalhe, alcançada a partir de Mesas — não
        # tem item próprio na sidebar, então nenhum botão de nav fica aceso.
        self._marcar_nav_ativo(None)

    def _voltar_para_mesas(self) -> None:
        self._navegar("Mesas")

    def _ao_comanda_cancelada(self, _comanda_id: int) -> None:
        # Comanda cancelada não tem mais nada a mostrar nesta tela — e a
        # mesa que ela ocupava acabou de ser liberada (ComandaService.cancelar
        # libera a mesa antes de emitir o sinal), então a grade de Mesas
        # precisa recarregar para refletir isso.
        self._voltar_para_mesas()

    def _abrir_pagamento(self, comanda_id: int) -> None:
        self._aviso_impressao.limpar()
        modal = PagamentoDialog(self._pagamentos, self._auth, comanda_id, self)
        modal.exec()
        if modal.comanda_fechada:
            # Recibo só quando a conta fecha: um cupom por pagamento parcial
            # gastaria bobina e nenhum deles traria o total final nem o troco.
            self._imprimir_recibo(comanda_id)
            self._voltar_para_mesas()
        else:
            # Pagamento parcial: a comanda continua aberta, só o total pago
            # e o restante mudaram.
            self._comanda_view.atualizar()

    def _imprimir_recibo(self, comanda_id: int) -> None:
        """Recibo do cliente, disparado assim que o pagamento fecha a comanda.

        Roda depois de `PagamentoService.registrar` ter feito commit: o dinheiro
        já entrou. Por isso nada aqui pode escapar como exceção — nem falha de
        impressora (que volta em `ResultadoImpressao`) nem erro de negócio.
        """
        try:
            resultado = executar_impressao(lambda: self._impressao.imprimir_recibo(comanda_id))
        except _ERROS_SERVICE as erro:
            self._aviso_impressao.mostrar_falha(f"Recibo não impresso: {erro}")
            return
        self._aviso_impressao.mostrar_um(resultado, contexto="Recibo do cliente")

    # ------------------------------------------------------------------
    # Sessão
    # ------------------------------------------------------------------

    def _ao_logar(self, funcionario: Funcionario) -> None:
        rotulo_perfil = _ROTULOS_PERFIL.get(funcionario.perfil, funcionario.perfil.value)
        self._label_usuario.setText(f"{funcionario.nome} · {rotulo_perfil}")
        # Atendente nunca vê o botão — nem sabe que a auditoria de fechamentos existe.
        self._botao_relatorios.setVisible(funcionario.perfil is PerfilFuncionario.GERENTE)
        # Aviso de impressão é da sessão anterior; quem entra agora não tem o que
        # fazer com o cupom de outro turno.
        self._aviso_impressao.limpar()
        self._pilha_raiz.setCurrentIndex(1)
        self._navegar("Mesas")

    def _deslogar(self) -> None:
        self._auth.logout()
        self._pilha_raiz.setCurrentIndex(0)
