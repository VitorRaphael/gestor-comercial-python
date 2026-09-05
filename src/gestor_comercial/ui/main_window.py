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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
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
from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.domain.usuario import Usuario
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
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.services.pagamento_service import PagamentoService
from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.views.cardapio_view import CardapioView
from gestor_comercial.ui.views.comanda_view import ComandaView
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView
from gestor_comercial.ui.views.estoque_view import EstoqueView
from gestor_comercial.ui.views.funcionarios_view import FuncionariosView
from gestor_comercial.ui.views.impressoras_view import ImpressorasView
from gestor_comercial.ui.views.loja_hub_view import LojaHubView
from gestor_comercial.ui.views.login_view import LoginView
from gestor_comercial.ui.views.mesas_view import MesasView
from gestor_comercial.ui.views.pagamento_dialog import PagamentoDialog
from gestor_comercial.ui.views.relatorios_view import RelatoriosView
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.gerente_pin_dialog import GerentePinDialog
from gestor_comercial.ui.widgets.loja_pin_dialog import LojaPinDialog
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

# Destinos administrativos atrás do PIN de supervisor da Loja (ver
# _abrir_area_loja): só existem como card dentro do hub "Central de Loja"
# (ver LojaHubView), sem atalho próprio na sidebar. O PIN é exigido a cada
# acesso e tranca de novo assim que qualquer um deles é abandonado por fora
# da área da Loja (ex.: clique direto em "Mesas"). "Configurações" fica de
# fora: não expõe dado sensível, não precisa de PIN.
_ROTULOS_LOJA = {"Loja", "Cardápio", "Estoque", "Impressoras", "Funcionários", "Relatórios"}

# Módulos alcançados só a partir de um card da Central de Loja (todo
# `_ROTULOS_LOJA` menos o próprio hub, mais "Configurações", que não é
# PIN-gated): mostram a barra "← Central de Loja" (ver
# `_montar_barra_voltar_loja`/`_navegar_agora`) porque não têm outro caminho
# de volta visível dentro da própria tela.
_MODULOS_HUB = (_ROTULOS_LOJA - {"Loja"}) | {"Configurações"}

_ROTULOS_PERFIL = {
    PerfilUsuario.ADMIN: "Admin",
    PerfilUsuario.GERENTE: "Gerente",
    PerfilUsuario.OPERADOR_CAIXA: "Operador de Caixa",
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
        funcionario_service: FuncionarioService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gestor Comercial")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)

        self._auth = auth_service
        self._pagamentos = pagamento_service
        self._impressao = impressao_service
        self._funcionarios = funcionario_service

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
        coluna_direita.addWidget(self._montar_barra_voltar_loja())

        self._mesas_view = MesasView(comanda_service)
        self._mesas_view.comanda_aberta.connect(self._abrir_comanda)

        self._comanda_view = ComandaView(
            comanda_service, cardapio_service, self._impressao, self._funcionarios
        )
        self._comanda_view.voltar.connect(self._voltar_para_mesas)
        self._comanda_view.comanda_cancelada.connect(self._ao_comanda_cancelada)
        self._comanda_view.pagamento_solicitado.connect(self._abrir_pagamento)

        self._caixa_view = CaixaView(caixa_service, self._impressao)
        self._cardapio_view = CardapioView(cardapio_service)
        self._estoque_view = EstoqueView()
        self._funcionarios_view = FuncionariosView(self._funcionarios, self._pagamentos)
        self._impressoras_view = ImpressorasView(cardapio_service, self._impressao)
        self._relatorios_view = RelatoriosView(caixa_service, auth_service, self._impressao)
        self._configuracoes_view = ConfiguracoesView()

        self._loja_hub_view = LojaHubView()
        self._loja_hub_view.destino_selecionado.connect(self._navegar_agora)
        self._loja_hub_view.voltar.connect(self._sair_da_loja)
        self._loja_desbloqueada = False
        # Mesmo raciocínio da Loja (ver _abrir_area_loja): a tela de Caixa expõe a
        # gaveta, movimentos e histórico de fechamentos, então também fica
        # atrás de PIN — só que de um gerente de verdade, não do código de
        # supervisor fixo da Loja (ver GerentePinDialog).
        self._caixa_desbloqueada = False

        self._paginas = QStackedWidget()
        for pagina in (
            self._mesas_view,
            self._comanda_view,
            self._caixa_view,
            self._cardapio_view,
            self._estoque_view,
            self._funcionarios_view,
            self._impressoras_view,
            self._relatorios_view,
            self._configuracoes_view,
            self._loja_hub_view,
        ):
            self._paginas.addWidget(pagina)
        coluna_direita.addWidget(self._paginas)

        layout_shell.addLayout(coluna_direita)
        return shell

    def _montar_sidebar(self) -> QWidget:
        sidebar = PainelPontilhado()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(212)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 24, 12, 20)
        layout.setSpacing(4)

        selo = QLabel("●  GESTOR COMERCIAL")
        selo.setObjectName("sidebarSelo")
        layout.addWidget(selo)
        marca = QLabel("Ponto de Venda")
        marca.setObjectName("sidebarMarca")
        layout.addWidget(marca)
        layout.addSpacing(24)

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
            "Loja": lambda: (self._loja_hub_view, lambda: None),
            "Cardápio": lambda: (self._cardapio_view, self._cardapio_view.atualizar),
            "Estoque": lambda: (self._estoque_view, self._estoque_view.atualizar),
            "Funcionários": lambda: (self._funcionarios_view, self._funcionarios_view.atualizar),
            "Impressoras": lambda: (self._impressoras_view, self._impressoras_view.atualizar),
            "Relatórios": lambda: (self._relatorios_view, self._relatorios_view.atualizar),
            "Configurações": lambda: (self._configuracoes_view, lambda: None),
        }
        self._botoes_nav: dict[str, QPushButton] = {}

        layout.addWidget(self._montar_rotulo_grupo("OPERAÇÃO"))
        layout.addSpacing(4)
        for rotulo in ("Mesas", "Caixa"):
            botao = QPushButton(rotulo)
            botao.setProperty("variante", "nav")
            if rotulo == "Caixa":
                # Caixa exige PIN de gerente a cada acesso (ver _abrir_caixa),
                # então não passa pelo _navegar genérico como Mesas.
                botao.clicked.connect(self._abrir_caixa)
            else:
                botao.clicked.connect(lambda _checked=False, r=rotulo: self._navegar(r))
            layout.addWidget(botao)
            self._botoes_nav[rotulo] = botao

        layout.addStretch()

        # Cardápio, Estoque, Funcionários, Impressoras, Relatórios e
        # Configurações vivem só como cards dentro da Central de Loja (ver
        # `LojaHubView`) -- não duplicam entrada aqui na sidebar. Um único
        # atalho, atrás do PIN de supervisor (ver LojaPinDialog/
        # _abrir_area_loja), no rodapé, logo acima do "Sair".
        botao_loja = QPushButton("Central de Loja")
        botao_loja.setProperty("variante", "nav")
        botao_loja.clicked.connect(lambda _checked=False: self._abrir_area_loja("Loja"))
        layout.addWidget(botao_loja)
        self._botoes_nav["Loja"] = botao_loja
        layout.addSpacing(8)

        divisor = QFrame()
        divisor.setObjectName("sidebarDivisor")
        layout.addWidget(divisor)
        layout.addSpacing(8)

        botao_sair = QPushButton("Sair")
        botao_sair.setProperty("variante", "nav")
        botao_sair.clicked.connect(self._deslogar)
        layout.addWidget(botao_sair)

        return sidebar

    def _montar_rotulo_grupo(self, texto: str) -> QLabel:
        rotulo = QLabel(texto)
        rotulo.setObjectName("sidebarGrupoRotulo")
        return rotulo

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

    def _montar_barra_voltar_loja(self) -> QWidget:
        """Único caminho de volta visível dentro de um módulo administrativo
        (Cardápio, Estoque, Funcionários, Impressoras, Relatórios,
        Configurações): sem isto, sair de um desses exigia lembrar que o
        próprio botão "Central de Loja" da sidebar também serve pra voltar.
        Fica oculta fora desses módulos (ver `_navegar_agora`)."""
        self._barra_voltar_loja = QWidget()
        layout = QHBoxLayout(self._barra_voltar_loja)
        layout.setContentsMargins(0, 0, 0, 12)
        botao = QPushButton("← Central de Loja")
        botao.setProperty("variante", "voltar-pdv")
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        # Direto pra `_navegar_agora`, sem passar por `_abrir_area_loja`: o
        # PIN já foi pedido pra entrar nesta área (ver sidebar/hub) -- pedir
        # de novo só pra voltar um nível, dentro da mesma área já
        # desbloqueada, não faz sentido nenhum pro usuário.
        botao.clicked.connect(lambda: self._navegar_agora("Loja"))
        layout.addWidget(botao)
        layout.addStretch()
        self._barra_voltar_loja.setVisible(False)
        return self._barra_voltar_loja

    # ------------------------------------------------------------------
    # Navegação dentro do shell
    # ------------------------------------------------------------------

    def _navegar(self, rotulo: str) -> None:
        # A sidebar troca de página direto, sem passar pelo botão "← Mesas"
        # da comanda — sem este desvio, o guard de itens pendentes (§
        # ComandaView.tentar_sair) nunca disparava para quem saía por aqui.
        if self._paginas.currentWidget() is self._comanda_view:
            self._comanda_view.tentar_sair(lambda: self._navegar_agora(rotulo))
            return
        self._navegar_agora(rotulo)

    def _abrir_area_loja(self, rotulo: str) -> None:
        """Ponto de entrada comum para o botão "Central de Loja" da sidebar
        e para cada card do hub (ver `_ROTULOS_LOJA`) -- todos atrás do
        mesmo PIN de supervisor, exigido a cada acesso."""
        if self._paginas.currentWidget() is self._comanda_view:
            self._comanda_view.tentar_sair(lambda: self._abrir_area_loja(rotulo))
            return
        if not self._loja_desbloqueada:
            # Reautenticação a cada acesso, não só na primeira vez: um PIN
            # digitado há uma hora não prova quem está com o mouse na mão
            # agora, e a área guarda faturamento/diferença de caixa do mês.
            modal = LojaPinDialog(self)
            if modal.exec() != QDialog.DialogCode.Accepted:
                return
            self._loja_desbloqueada = True
        self._navegar_agora(rotulo)

    def _sair_da_loja(self) -> None:
        self._trancar_loja()
        self._navegar("Mesas")

    def _trancar_loja(self) -> None:
        self._loja_desbloqueada = False

    def _abrir_caixa(self) -> None:
        if self._paginas.currentWidget() is self._comanda_view:
            self._comanda_view.tentar_sair(self._abrir_caixa)
            return
        if not self._caixa_desbloqueada:
            # Reautenticação a cada acesso, mesmo raciocínio da Loja (ver
            # _abrir_area_loja): gaveta e histórico de fechamentos são dados
            # sensíveis, e um PIN digitado há uma hora não prova quem está
            # com o mouse na mão agora.
            modal = GerentePinDialog(self._auth, self)
            if modal.exec() != QDialog.DialogCode.Accepted:
                return
            self._caixa_desbloqueada = True
        self._navegar_agora("Caixa")

    def _trancar_caixa(self) -> None:
        self._caixa_desbloqueada = False

    def _navegar_agora(self, rotulo: str) -> None:
        pagina, recarregar = self._destinos_nav[rotulo]()
        recarregar()
        self._mostrar_pagina(pagina)
        self._barra_voltar_loja.setVisible(rotulo in _MODULOS_HUB)
        # Sair de um dos módulos administrativos sem passar pelo "← Voltar
        # ao PDV" do hub (ex.: clicando direto em "Mesas" na sidebar) também
        # tranca a Loja — o PIN nunca deve valer para a próxima entrada.
        if rotulo in _ROTULOS_LOJA:
            # Só "Central de Loja" tem botão próprio na sidebar (ver
            # _montar_sidebar) -- os demais módulos da área só existem como
            # card dentro do hub, então qualquer um deles mantém o mesmo
            # botão "Central de Loja" aceso.
            self._marcar_nav_ativo("Loja")
        else:
            self._trancar_loja()
            # Mesma lógica pro Caixa: só continua destravado enquanto o
            # próprio Caixa está na tela. Sair pra Mesas (ou qualquer outro
            # destino) exige o PIN de novo na próxima entrada.
            if rotulo != "Caixa":
                self._trancar_caixa()
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
        modal = PagamentoDialog(self._pagamentos, comanda_id, self)
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

    def _ao_logar(self, usuario: Usuario) -> None:
        rotulo_perfil = _ROTULOS_PERFIL.get(usuario.perfil, usuario.perfil.value)
        self._label_usuario.setText(f"{usuario.nome} · {rotulo_perfil}")
        self._loja_hub_view.definir_usuario(f"{rotulo_perfil.upper()} · {usuario.nome.upper()}")
        # Sessão nova: Loja e Caixa não herdam o desbloqueio de quem usou antes.
        self._trancar_loja()
        self._trancar_caixa()
        # Aviso de impressão é da sessão anterior; quem entra agora não tem o que
        # fazer com o cupom de outro turno.
        self._aviso_impressao.limpar()
        self._pilha_raiz.setCurrentIndex(1)
        self._navegar("Mesas")

    def _deslogar(self) -> None:
        if self._paginas.currentWidget() is self._comanda_view:
            self._comanda_view.tentar_sair(self._deslogar_agora)
            return
        self._deslogar_agora()

    def _deslogar_agora(self) -> None:
        self._trancar_loja()
        self._auth.logout()
        self._pilha_raiz.setCurrentIndex(0)
