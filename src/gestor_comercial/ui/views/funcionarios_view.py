"""Funcionários de atendimento: cadastro, edição, (des)ativação, exclusão e
dívida de consumo interno — tela "Concreto" (§3.14, Fase 3 do redesign).

`Funcionario` não loga (ver `LoginView`/`AuthService`, restritos a
`Usuario`) — esta tela é só gestão de quem atende a mesa/comanda. Cadastrar,
editar, (des)ativar e excluir exigem gerente logado (`FuncionarioService`);
quitar dívida exige a Senha Operacional (Gerente) digitada na hora
(reautenticação, não a sessão corrente) — quem barra isso é
`PagamentoService`, aqui só se mostra o erro que o service levantar.

Layout: cabeçalho com breadcrumb/ações, grade de 4 KPIs, painel esquerdo com
busca/filtro + lista (linhas customizadas com avatar/cargo/consumo/status) e
painel direito com o detalhe de quem está selecionado. Reaproveita os tokens
e variantes de botão/badge já existentes em `ui/theme/qss_app.py` — só
acrescenta seletores novos para o que não tinha equivalente (avatar, linha
selecionável, card de consumo do detalhe).
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.enums import CargoFuncionario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.pagamento_service import PagamentoService
from gestor_comercial.ui.formatacao import (
    formatar_para_campo,
    formatar_reais,
    safe_decimal,
)
from gestor_comercial.ui.rotulo_identidade import rotulo_identidade
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.modais import executar_modal
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.funcionario_dialog import (
    CARGOS_COM_ACESSO_TOTAL,
    FuncionarioDialog,
    iniciais,
)

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

# §3.14: "ACESSO" no painel de detalhe não existe como campo próprio no
# domínio (`Funcionario` não tem coluna de nível de acesso — só `Usuario`,
# que loga, tem perfil). Em vez de inventar um dado que o banco não guarda,
# deriva de `cargo`: Gerente/Caixa lidam com dinheiro e fechamento, os
# demais só atendem. Se um dia isso precisar ser um campo de verdade
# (editável, independente do cargo), é uma migração nova — documentado aqui
# para não passar como se fosse um dado gravado.
#
# A lista mora em `funcionario_dialog.CARGOS`, junto do texto que o modal
# mostra ("ACESSO LIBERADO", "APENAS PEDIDOS"): enquanto eram duas, o rodapé
# do cadastro e esta linha do detalhe podiam discordar sobre o mesmo cargo.

_FILTRO_TODOS = "TODOS"
_FILTRO_ATIVOS = "ATIVO"
_FILTRO_INATIVOS = "INATIVO"


class FuncionariosView(QWidget):
    """Equipe, permissões de operação e consumo interno."""

    def __init__(
        self,
        funcionario_service: FuncionarioService,
        pagamento_service: PagamentoService,
        auth_service: AuthService,
        caixa_service: CaixaService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._funcionarios_service = funcionario_service
        self._pagamentos = pagamento_service
        self._auth = auth_service
        self._caixa_service = caixa_service
        self._funcionarios: list[Funcionario] = []
        self._saldos: dict[int, Decimal] = {}
        self._filtro_status = _FILTRO_TODOS
        self._termo_busca = ""
        self._selecionado_id: int | None = None

        self._montar_layout()
        self.atualizar()

    # ------------------------------------------------------------------
    # Montagem do layout
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(0, 0, 0, 0)
        layout_externo.setSpacing(16)

        layout_externo.addLayout(self._montar_cabecalho())

        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        layout_externo.addWidget(self._label_erro)

        layout_externo.addLayout(self._montar_kpis())

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        corpo.addWidget(self._montar_painel_lista(), 60)
        corpo.addWidget(self._montar_painel_detalhe(), 40)
        layout_externo.addLayout(corpo, 1)

    def _montar_cabecalho(self) -> QHBoxLayout:
        cabecalho = QHBoxLayout()

        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        self._label_eyebrow = QLabel("GERENTE")
        self._label_eyebrow.setObjectName("caixaEyebrow")
        bloco_titulo.addWidget(self._label_eyebrow)

        titulo = QLabel("Funcionários")
        titulo.setObjectName("caixaTitulo")
        bloco_titulo.addWidget(titulo)

        subtitulo = QLabel("Equipe, permissões de operação e consumo interno")
        subtitulo.setObjectName("caixaSubtitulo")
        bloco_titulo.addWidget(subtitulo)

        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch()

        botao_baixa = QPushButton("Dar baixa no consumo")
        botao_baixa.setProperty("variante", "pilula-vazia")
        botao_baixa.clicked.connect(self._quitar)
        cabecalho.addWidget(botao_baixa, alignment=Qt.AlignmentFlag.AlignVCenter)

        botao_novo = QPushButton("Novo funcionário")
        botao_novo.setProperty("variante", "primario")
        botao_novo.clicked.connect(self._criar)
        cabecalho.addWidget(botao_novo, alignment=Qt.AlignmentFlag.AlignVCenter)
        return cabecalho

    def _montar_kpis(self) -> QHBoxLayout:
        grade = QHBoxLayout()
        grade.setSpacing(14)

        self._kpi_cadastrados = _CardKpiFuncionarios("👥", "Cadastrados")
        self._kpi_ativos = _CardKpiFuncionarios("🪪", "Ativos")
        self._kpi_consumo = _CardKpiFuncionarios("💰", "Consumo em aberto")
        self._kpi_pendencia = _CardKpiFuncionarios("⚠️", "Com pendência")
        for card in (self._kpi_cadastrados, self._kpi_ativos, self._kpi_consumo, self._kpi_pendencia):
            grade.addWidget(card)
        return grade

    def _montar_painel_lista(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("funcionariosPainel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        barra = QHBoxLayout()
        barra.setSpacing(8)
        self._pills_status: dict[str, QPushButton] = {}
        for chave, rotulo in ((_FILTRO_TODOS, "TODOS"), (_FILTRO_ATIVOS, "ATIVO"), (_FILTRO_INATIVOS, "INATIVO")):
            pill = QPushButton(rotulo)
            pill.setProperty("variante", "filtro-pill")
            pill.clicked.connect(lambda _=False, c=chave: self._selecionar_filtro(c))
            barra.addWidget(pill)
            self._pills_status[chave] = pill
        barra.addStretch()

        self._campo_busca = QLineEdit()
        self._campo_busca.setPlaceholderText("🔎 Buscar funcionário")
        self._campo_busca.setObjectName("funcionariosBusca")
        self._campo_busca.setFixedWidth(220)
        self._campo_busca.textChanged.connect(self._ao_buscar)
        barra.addWidget(self._campo_busca)
        layout.addLayout(barra)

        self._lista = QListWidget()
        self._lista.setObjectName("funcionariosLista")
        self._lista.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._lista.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._lista.itemClicked.connect(self._ao_clicar_item)
        layout.addWidget(self._lista, 1)
        self._atualizar_pills()
        return painel

    def _montar_painel_detalhe(self) -> QFrame:
        self._painel_detalhe = _PainelDetalheFuncionario()
        self._painel_detalhe.editar_solicitado.connect(self._editar_id)
        self._painel_detalhe.baixa_solicitada.connect(self._quitar_id)
        self._painel_detalhe.alternar_status_solicitado.connect(self._alternar_status_id)
        self._painel_detalhe.excluir_solicitado.connect(self._excluir_id)
        return self._painel_detalhe

    # ------------------------------------------------------------------
    # Carregamento / preenchimento
    # ------------------------------------------------------------------

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._label_eyebrow.setText(rotulo_identidade(self._auth, self._caixa_service).upper())

        self._funcionarios = self._funcionarios_service.listar_todos()
        self._saldos = self._carregar_saldos()
        self._preencher_kpis()
        self._preencher_lista()

    def _carregar_saldos(self) -> dict[int, Decimal]:
        # Consultar a dívida exige gerente logado (§3.8); num app sem gerente
        # na sessão, a coluna some por ora — a listagem de nome/cargo/status
        # continua útil pra quem só quer ver quem está cadastrado.
        try:
            saldos = self._pagamentos.listar_funcionarios_com_saldo()
        except _ERROS_SERVICE:
            return {}
        return {linha.funcionario_id: linha.saldo for linha in saldos}

    def _preencher_kpis(self) -> None:
        ativos = [f for f in self._funcionarios if f.ativo]
        consumo_total = sum((self._saldos.get(f.id, Decimal("0")) for f in self._funcionarios), Decimal("0"))
        com_pendencia = sum(1 for f in self._funcionarios if self._saldos.get(f.id, Decimal("0")) > 0)

        self._kpi_cadastrados.definir_valor(str(len(self._funcionarios)))
        self._kpi_ativos.definir_valor(f"{len(ativos)}/{len(self._funcionarios)}")
        self._kpi_consumo.definir_valor(formatar_reais(consumo_total))
        self._kpi_pendencia.definir_valor(str(com_pendencia))

    def _funcionarios_filtrados(self) -> list[Funcionario]:
        itens = self._funcionarios
        if self._filtro_status == _FILTRO_ATIVOS:
            itens = [f for f in itens if f.ativo]
        elif self._filtro_status == _FILTRO_INATIVOS:
            itens = [f for f in itens if not f.ativo]
        termo = self._termo_busca.strip().lower()
        if termo:
            itens = [f for f in itens if termo in f.nome.lower()]
        return itens

    def _preencher_lista(self) -> None:
        self._lista.clear()
        filtrados = self._funcionarios_filtrados()
        if not any(f.id == self._selecionado_id for f in filtrados):
            self._selecionado_id = filtrados[0].id if filtrados else None

        for funcionario in filtrados:
            saldo = self._saldos.get(funcionario.id, Decimal("0"))
            selecionado = funcionario.id == self._selecionado_id
            linha = _LinhaFuncionario(funcionario, saldo, selecionado=selecionado)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, funcionario.id)
            item.setSizeHint(linha.sizeHint())
            self._lista.addItem(item)
            self._lista.setItemWidget(item, linha)

        self._atualizar_detalhe()

    def _atualizar_detalhe(self) -> None:
        funcionario = self._funcionario_por_id(self._selecionado_id)
        if funcionario is None:
            self._painel_detalhe.limpar()
            return
        saldo = self._saldos.get(funcionario.id, Decimal("0"))
        self._painel_detalhe.carregar(funcionario, saldo)

    def _funcionario_por_id(self, funcionario_id: int | None) -> Funcionario | None:
        if funcionario_id is None:
            return None
        return next((f for f in self._funcionarios if f.id == funcionario_id), None)

    def _atualizar_pills(self) -> None:
        for chave, pill in self._pills_status.items():
            aplicar_propriedade(pill, "ativo", chave == self._filtro_status)

    # ------------------------------------------------------------------
    # Interação
    # ------------------------------------------------------------------

    def _selecionar_filtro(self, chave: str) -> None:
        self._filtro_status = chave
        self._atualizar_pills()
        self._preencher_lista()

    def _ao_buscar(self, texto: str) -> None:
        self._termo_busca = texto
        self._preencher_lista()

    def _ao_clicar_item(self, item: QListWidgetItem) -> None:
        self._selecionado_id = item.data(Qt.ItemDataRole.UserRole)
        self._preencher_lista()

    def _criar(self) -> None:
        modal = FuncionarioDialog(parent=self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        dados = modal.resultado()

        self._label_erro.setText("")
        try:
            novo = self._funcionarios_service.criar(dados.nome, dados.cargo, dados.telefone)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        # Fora do `try`: o cadastro já está gravado, e um tropeço na situação
        # não pode fazer a tela voltar sem mostrar quem acabou de entrar.
        self._aplicar_situacao(novo, dados.ativo)
        self._selecionado_id = novo.id
        self.atualizar()

    def _editar_id(self, funcionario_id: int) -> None:
        funcionario = self._funcionario_por_id(funcionario_id)
        if funcionario is None:
            return
        modal = FuncionarioDialog(funcionario=funcionario, parent=self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        dados = modal.resultado()

        self._label_erro.setText("")
        try:
            atualizado = self._funcionarios_service.editar(
                funcionario.id, dados.nome, dados.cargo, dados.telefone
            )
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._aplicar_situacao(atualizado, dados.ativo)
        self.atualizar()

    def _aplicar_situacao(self, funcionario: Funcionario, ativo: bool) -> None:
        """A situação escolhida no modal, escrita pelos métodos que já existiam.

        `FuncionarioService.criar()` não recebe situação — nasce ativo, e sempre
        nasceu. Quem liga e desliga é `ativar()`/`desativar()`, o mesmo par que
        o botão do painel de detalhe usa: o modal não trouxe caminho novo para
        o banco, só uma segunda porta para o caminho que já existia.

        Só chama quando a escolha **diverge** do estado atual. Os dois métodos
        levantam `RegraDeNegocioError` de propósito quando não há o que mudar
        ("já está ativo"), e essa mensagem, aqui, seria erro sem erro nenhum.
        """
        if funcionario.ativo == ativo:
            return
        try:
            if ativo:
                self._funcionarios_service.ativar(funcionario.id)
            else:
                self._funcionarios_service.desativar(funcionario.id)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))

    def _alternar_status_id(self, funcionario_id: int) -> None:
        funcionario = self._funcionario_por_id(funcionario_id)
        if funcionario is None:
            return
        self._label_erro.setText("")
        self._aplicar_situacao(funcionario, not funcionario.ativo)
        self.atualizar()

    def _excluir_id(self, funcionario_id: int) -> None:
        funcionario = self._funcionario_por_id(funcionario_id)
        if funcionario is None:
            return
        # A confirmação não é mais um "Sim/Não": é a Senha Master digitada na
        # hora (§3.13, Nível 3). O `exigir_gerente()` do service continua
        # valendo, mas ele é satisfeito pela SESSÃO — quem abriu o turno de
        # manhã autoriza qualquer exclusão que alguém clicar à tarde. Um
        # `QMessageBox` em cima disso separa a exclusão de um clique
        # distraído por outro clique, e a linha some do banco de vez.
        #
        # O modal se recusa sozinho quando o PIN não bate e só devolve
        # `Accepted` com a Senha Master certa; `executar_modal` descarta a
        # instância depois de ler o código de saída (§3.2).
        pin = PinPadDialog.para_exclusao(self._auth, funcionario.nome, self)
        if executar_modal(pin) != QDialog.DialogCode.Accepted:
            return

        self._label_erro.setText("")
        try:
            self._funcionarios_service.excluir(funcionario.id)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._selecionado_id = None
        self.atualizar()

    def _quitar(self) -> None:
        self._quitar_id(self._selecionado_id)

    def _quitar_id(self, funcionario_id: int | None) -> None:
        funcionario = self._funcionario_por_id(funcionario_id)
        if funcionario is None:
            self._label_erro.setText("Selecione um funcionário na lista para dar baixa no consumo.")
            return
        saldo = self._saldos.get(funcionario.id, Decimal("0"))
        if saldo <= 0:
            self._label_erro.setText(f"{funcionario.nome} não tem consumo em aberto.")
            return

        modal = _QuitarConsumoDialog(funcionario.nome, saldo, self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        valor, senha_gerente = modal.resultado()
        if valor is None:
            self._label_erro.setText("Valor inválido. Informe um valor em reais, como 20,00.")
            return

        self._label_erro.setText("")
        try:
            self._pagamentos.quitar(funcionario.id, valor, senha_gerente)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()


class _CardKpiFuncionarios(QFrame):
    """KPI com ícone + rótulo + valor — variação local de `CardKpi` (que só
    tem rótulo + valor) porque o mockup desta tela pede ícone no topo."""

    def __init__(self, icone: str, rotulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("funcionariosKpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        topo = QHBoxLayout()
        icone_label = QLabel(icone)
        icone_label.setObjectName("funcionariosKpiIcone")
        topo.addWidget(icone_label)
        topo.addStretch()
        layout.addLayout(topo)

        rotulo_label = QLabel(rotulo.upper())
        rotulo_label.setObjectName("funcionariosKpiRotulo")
        layout.addWidget(rotulo_label)

        self._label_valor = QLabel("—")
        self._label_valor.setObjectName("funcionariosKpiValor")
        layout.addWidget(self._label_valor)

    def definir_valor(self, texto: str) -> None:
        self._label_valor.setText(texto)


class _LinhaFuncionario(QFrame):
    """Uma linha da lista: avatar, nome/cargo, consumo e badge de status."""

    def __init__(self, funcionario: Funcionario, saldo: Decimal, *, selecionado: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("funcionariosLinha")
        self.setProperty("selecionado", selecionado)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        avatar = QLabel(iniciais(funcionario.nome))
        avatar.setObjectName("funcionariosAvatar")
        avatar.setFixedSize(38, 38)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(avatar)

        coluna_nome = QVBoxLayout()
        coluna_nome.setSpacing(2)
        nome = QLabel(funcionario.nome)
        nome.setObjectName("funcionariosLinhaNome")
        coluna_nome.addWidget(nome)
        cargo = QLabel((funcionario.cargo or "SEM CARGO").upper())
        cargo.setObjectName("funcionariosLinhaCargo")
        coluna_nome.addWidget(cargo)
        if funcionario.turno_horario:
            turno = QLabel(funcionario.turno_horario.upper())
            turno.setObjectName("funcionariosLinhaTurno")
            coluna_nome.addWidget(turno)
        layout.addLayout(coluna_nome, 1)

        coluna_consumo = QVBoxLayout()
        coluna_consumo.setSpacing(2)
        coluna_consumo.setAlignment(Qt.AlignmentFlag.AlignRight)
        valor = QLabel(formatar_reais(saldo))
        valor.setObjectName("funcionariosLinhaConsumoValor")
        valor.setAlignment(Qt.AlignmentFlag.AlignRight)
        coluna_consumo.addWidget(valor)
        rotulo_consumo = QLabel("CONSUMO")
        rotulo_consumo.setObjectName("funcionariosLinhaConsumoRotulo")
        rotulo_consumo.setAlignment(Qt.AlignmentFlag.AlignRight)
        coluna_consumo.addWidget(rotulo_consumo)
        layout.addLayout(coluna_consumo)

        badge = QLabel("ATIVO" if funcionario.ativo else "INATIVO")
        badge.setProperty("variante", "badge")
        badge.setProperty("status", "ativo" if funcionario.ativo else "inativo")
        layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)


class _PainelDetalheFuncionario(QFrame):
    """Painel direito: perfil do funcionário selecionado + card de consumo +
    metadados + ações. Emite sinais em vez de chamar os services direto —
    quem sabe falar com `FuncionarioService`/`PagamentoService` é a view mãe."""

    editar_solicitado = Signal(int)
    baixa_solicitada = Signal(int)
    alternar_status_solicitado = Signal(int)
    excluir_solicitado = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("funcionariosPainel")
        self._funcionario_id: int | None = None

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        conteudo = QWidget()
        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(16)

        cabecalho = QVBoxLayout()
        cabecalho.setSpacing(8)
        cabecalho.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._avatar_grande = QLabel("")
        self._avatar_grande.setObjectName("funcionariosAvatarGrande")
        self._avatar_grande.setFixedSize(64, 64)
        self._avatar_grande.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cabecalho.addWidget(self._avatar_grande, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._label_nome = QLabel("—")
        self._label_nome.setObjectName("funcionariosDetalheNome")
        self._label_nome.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        cabecalho.addWidget(self._label_nome)
        self._label_cargo = QLabel("")
        self._label_cargo.setObjectName("funcionariosDetalheCargo")
        self._label_cargo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        cabecalho.addWidget(self._label_cargo)
        layout.addLayout(cabecalho)

        card_consumo = QFrame()
        card_consumo.setObjectName("funcionariosCardConsumo")
        layout_consumo = QVBoxLayout(card_consumo)
        layout_consumo.setContentsMargins(16, 14, 16, 14)
        layout_consumo.setSpacing(4)
        rotulo_consumo = QLabel("CONSUMO EM ABERTO")
        rotulo_consumo.setObjectName("funcionariosCardConsumoRotulo")
        layout_consumo.addWidget(rotulo_consumo)
        self._label_consumo_valor = QLabel("R$ 0,00")
        self._label_consumo_valor.setObjectName("funcionariosCardConsumoValor")
        layout_consumo.addWidget(self._label_consumo_valor)
        nota = QLabel("Desconto previsto no fechamento do turno.")
        nota.setObjectName("funcionariosCardConsumoNota")
        nota.setWordWrap(True)
        layout_consumo.addWidget(nota)
        layout.addWidget(card_consumo)

        grid_meta = QVBoxLayout()
        grid_meta.setSpacing(8)
        self._label_status = _linha_meta(grid_meta, "STATUS")
        self._label_acesso = _linha_meta(grid_meta, "ACESSO")
        self._label_telefone = _linha_meta(grid_meta, "TELEFONE")
        self._label_turno = _linha_meta(grid_meta, "TURNO")
        self._label_senha = _linha_meta(grid_meta, "SENHA")
        layout.addLayout(grid_meta)

        layout.addStretch()

        linha1 = QHBoxLayout()
        linha1.setSpacing(10)
        self._botao_editar = QPushButton("Editar")
        self._botao_editar.setProperty("variante", "neutro")
        self._botao_editar.clicked.connect(self._emitir_editar)
        linha1.addWidget(self._botao_editar)
        self._botao_baixa = QPushButton("Dar baixa")
        self._botao_baixa.setProperty("variante", "pilula-ciano")
        self._botao_baixa.clicked.connect(self._emitir_baixa)
        linha1.addWidget(self._botao_baixa)
        layout.addLayout(linha1)

        linha2 = QHBoxLayout()
        linha2.setSpacing(10)
        self._botao_status = QPushButton("Desativar")
        self._botao_status.setProperty("variante", "neutro")
        self._botao_status.clicked.connect(self._emitir_alternar_status)
        linha2.addWidget(self._botao_status)
        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setProperty("variante", "perigo")
        self._botao_excluir.clicked.connect(self._emitir_excluir)
        linha2.addWidget(self._botao_excluir)
        layout.addLayout(linha2)

        area.setWidget(conteudo)
        layout_externo = QVBoxLayout(self)
        layout_externo.setContentsMargins(0, 0, 0, 0)
        layout_externo.addWidget(area)

        self.limpar()

    def carregar(self, funcionario: Funcionario, saldo: Decimal) -> None:
        self._funcionario_id = funcionario.id
        self.setEnabled(True)

        self._avatar_grande.setText(iniciais(funcionario.nome))
        self._label_nome.setText(funcionario.nome)
        self._label_cargo.setText((funcionario.cargo or "Sem cargo definido").upper())

        self._label_consumo_valor.setText(formatar_reais(saldo))

        self._label_status.setText("Ativo" if funcionario.ativo else "Inativo")
        acesso = "Total" if (funcionario.cargo in CARGOS_COM_ACESSO_TOTAL) else "Restrito"
        self._label_acesso.setText(acesso)
        self._label_telefone.setText(funcionario.telefone or "—")
        self._label_turno.setText(funcionario.turno_horario or "—")

        eh_caixa = funcionario.cargo == CargoFuncionario.CAIXA.value
        self._label_senha.setText("••••••" if eh_caixa else "—")

        self._botao_status.setText("Desativar" if funcionario.ativo else "Ativar")
        self._botao_baixa.setEnabled(saldo > 0)

    def limpar(self) -> None:
        self._funcionario_id = None
        self.setEnabled(False)
        self._avatar_grande.setText("—")
        self._label_nome.setText("Nenhum funcionário selecionado")
        self._label_cargo.setText("")
        self._label_consumo_valor.setText("R$ 0,00")
        self._label_status.setText("—")
        self._label_acesso.setText("—")
        self._label_telefone.setText("—")
        self._label_turno.setText("—")
        self._label_senha.setText("—")

    def _emitir_editar(self) -> None:
        if self._funcionario_id is not None:
            self.editar_solicitado.emit(self._funcionario_id)

    def _emitir_baixa(self) -> None:
        if self._funcionario_id is not None:
            self.baixa_solicitada.emit(self._funcionario_id)

    def _emitir_alternar_status(self) -> None:
        if self._funcionario_id is not None:
            self.alternar_status_solicitado.emit(self._funcionario_id)

    def _emitir_excluir(self) -> None:
        if self._funcionario_id is not None:
            self.excluir_solicitado.emit(self._funcionario_id)



def _linha_meta(layout_pai: QVBoxLayout, rotulo: str) -> QLabel:
    linha = QHBoxLayout()
    label_rotulo = QLabel(rotulo)
    label_rotulo.setObjectName("funcionariosMetaRotulo")
    linha.addWidget(label_rotulo)
    linha.addStretch()
    label_valor = QLabel("—")
    label_valor.setObjectName("funcionariosMetaValor")
    label_valor.setAlignment(Qt.AlignmentFlag.AlignRight)
    linha.addWidget(label_valor)
    layout_pai.addLayout(linha)
    return label_valor


class _QuitarConsumoDialog(QDialog):
    """Modal de baixa: valor a abater e Senha Operacional (Gerente) para autorizar.

    A tela em si já é o controle de acesso pedido — sem a senha certa,
    `PagamentoService.quitar()` recusa a baixa (§3.8). Cada confirmação aqui
    grava um `QuitacaoConsumo` no banco (valor, data/hora, quem autorizou),
    dado bruto para o `sales_analytics` mais pra frente.
    """

    def __init__(self, nome_funcionario: str, saldo: Decimal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Dar baixa no consumo — {nome_funcionario}")

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Consumo atual: {formatar_reais(saldo)}"))

        formulario = QFormLayout()

        self._campo_valor = QLineEdit(formatar_para_campo(saldo))
        formulario.addRow("Valor descontado do salário", self._campo_valor)

        self._campo_senha_gerente = QLineEdit()
        self._campo_senha_gerente.setEchoMode(QLineEdit.EchoMode.Password)
        formulario.addRow("Senha do gerente", self._campo_senha_gerente)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Dar baixa")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[Decimal | None, str]:
        valor = safe_decimal(self._campo_valor.text(), padrao=None)
        senha_gerente = self._campo_senha_gerente.text().strip()
        return valor, senha_gerente
