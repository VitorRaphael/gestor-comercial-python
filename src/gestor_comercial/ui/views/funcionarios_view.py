"""Funcionários de atendimento: cadastro, edição, (des)ativação, exclusão e
dívida de consumo interno.

`Funcionario` não loga (ver `LoginView`/`AuthService`, restritos a
`Usuario`) — esta tela é só gestão de quem atende a mesa/comanda. Cadastrar,
editar, (des)ativar e excluir exigem gerente logado (`FuncionarioService`);
quitar dívida exige o PIN de um gerente digitado na hora (reautenticação, não
a sessão corrente) — quem barra isso é `PagamentoService`, aqui só se mostra
o erro que o service levantar.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.pagamento_service import PagamentoService

_COLUNAS = ["Nome", "Cargo", "Status", "Consumo"]

_CARGOS_SUGERIDOS = ["Garçom", "Atendente", "Cozinha", "Caixa"]

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)


class FuncionariosView(QWidget):
    """CRUD de funcionário de atendimento + baixa de consumo interno."""

    def __init__(
        self,
        funcionario_service: FuncionarioService,
        pagamento_service: PagamentoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._funcionarios_service = funcionario_service
        self._pagamentos = pagamento_service
        self._funcionarios: list[Funcionario] = []
        self._saldos: dict[int, Decimal] = {}

        layout = QVBoxLayout(self)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout.addWidget(self._label_erro)

        barra = QHBoxLayout()
        barra.addStretch()
        botao_novo = QPushButton("Novo funcionário")
        botao_novo.setProperty("variante", "primario")
        botao_novo.clicked.connect(self._criar)
        barra.addWidget(botao_novo)
        layout.addLayout(barra)

        self._tabela = QTableWidget(0, len(_COLUNAS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tabela)

        acoes = QHBoxLayout()
        self._botao_editar = QPushButton("Editar")
        self._botao_editar.setProperty("variante", "secundario")
        self._botao_editar.clicked.connect(self._editar)
        acoes.addWidget(self._botao_editar)

        self._botao_status = QPushButton("Desativar")
        self._botao_status.setProperty("variante", "perigo")
        self._botao_status.clicked.connect(self._alternar_status)
        acoes.addWidget(self._botao_status)

        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setProperty("variante", "perigo")
        self._botao_excluir.clicked.connect(self._excluir)
        acoes.addWidget(self._botao_excluir)

        self._botao_quitar = QPushButton("Dar baixa no Consumo")
        self._botao_quitar.setProperty("variante", "neutro")
        self._botao_quitar.clicked.connect(self._quitar)
        acoes.addWidget(self._botao_quitar)
        acoes.addStretch()
        layout.addLayout(acoes)

        self.atualizar()

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._funcionarios = self._funcionarios_service.listar_todos()
        self._saldos = self._carregar_saldos()

        self._tabela.setRowCount(len(self._funcionarios))
        for linha, funcionario in enumerate(self._funcionarios):
            self._tabela.setItem(linha, 0, QTableWidgetItem(funcionario.nome))
            self._tabela.setItem(linha, 1, QTableWidgetItem(funcionario.cargo or "—"))
            status = "Ativo" if funcionario.ativo else "Desativado"
            self._tabela.setItem(linha, 2, QTableWidgetItem(status))
            saldo = self._saldos.get(funcionario.id, Decimal("0"))
            self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(saldo)))

    def _carregar_saldos(self) -> dict[int, Decimal]:
        # Consultar a dívida exige gerente logado (§3.8); num app sem gerente
        # na sessão, a coluna some por ora — a listagem de nome/cargo/status
        # continua útil pra quem só quer ver quem está cadastrado.
        try:
            saldos = self._pagamentos.listar_funcionarios_com_saldo()
        except _ERROS_SERVICE:
            return {}
        return {linha.funcionario_id: linha.saldo for linha in saldos}

    def _funcionario_selecionado(self) -> Funcionario | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._funcionarios):
            return None
        return self._funcionarios[linha]

    def _criar(self) -> None:
        modal = _FuncionarioDialog(parent=self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        nome, cargo, telefone = modal.resultado()

        self._label_erro.setText("")
        try:
            self._funcionarios_service.criar(nome, cargo, telefone)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _editar(self) -> None:
        funcionario = self._funcionario_selecionado()
        if funcionario is None:
            return
        modal = _FuncionarioDialog(funcionario=funcionario, parent=self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        nome, cargo, telefone = modal.resultado()

        self._label_erro.setText("")
        try:
            self._funcionarios_service.editar(funcionario.id, nome, cargo, telefone)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _alternar_status(self) -> None:
        funcionario = self._funcionario_selecionado()
        if funcionario is None:
            return
        self._label_erro.setText("")
        try:
            if funcionario.ativo:
                self._funcionarios_service.desativar(funcionario.id)
            else:
                self._funcionarios_service.ativar(funcionario.id)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _excluir(self) -> None:
        funcionario = self._funcionario_selecionado()
        if funcionario is None:
            return
        confirmacao = QMessageBox.question(
            self,
            "Excluir funcionário",
            f"Excluir {funcionario.nome} definitivamente? Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmacao != QMessageBox.StandardButton.Yes:
            return

        self._label_erro.setText("")
        try:
            self._funcionarios_service.excluir(funcionario.id)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _quitar(self) -> None:
        funcionario = self._funcionario_selecionado()
        if funcionario is None:
            return
        saldo = self._saldos.get(funcionario.id, Decimal("0"))
        if saldo <= 0:
            self._label_erro.setText(f"{funcionario.nome} não tem consumo em aberto.")
            return

        modal = _QuitarConsumoDialog(funcionario.nome, saldo, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            valor, pin_gerente = modal.resultado()
        except InvalidOperation:
            self._label_erro.setText("Valor inválido. Informe um valor em reais, como 20.00.")
            return

        self._label_erro.setText("")
        try:
            self._pagamentos.quitar(funcionario.id, valor, pin_gerente)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()


class _FuncionarioDialog(QDialog):
    """Modal de cadastro/edição: nome, cargo e telefone."""

    def __init__(self, funcionario: Funcionario | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar funcionário" if funcionario else "Novo funcionário")

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_nome = QLineEdit(funcionario.nome if funcionario else "")
        formulario.addRow("Nome", self._campo_nome)

        self._campo_cargo = QComboBox()
        self._campo_cargo.setEditable(True)
        self._campo_cargo.addItems(_CARGOS_SUGERIDOS)
        if funcionario and funcionario.cargo:
            if funcionario.cargo not in _CARGOS_SUGERIDOS:
                self._campo_cargo.addItem(funcionario.cargo)
            self._campo_cargo.setCurrentText(funcionario.cargo)
        else:
            self._campo_cargo.setCurrentIndex(-1)
        formulario.addRow("Cargo", self._campo_cargo)

        self._campo_telefone = QLineEdit(funcionario.telefone if funcionario and funcionario.telefone else "")
        self._campo_telefone.setPlaceholderText("Opcional")
        formulario.addRow("Telefone", self._campo_telefone)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[str, str | None, str | None]:
        nome = self._campo_nome.text().strip()
        cargo = self._campo_cargo.currentText().strip() or None
        telefone = self._campo_telefone.text().strip() or None
        return nome, cargo, telefone


class _QuitarConsumoDialog(QDialog):
    """Modal de baixa: valor a abater e PIN de um gerente para autorizar.

    A tela em si já é o controle de acesso pedido — sem PIN de gerente válido,
    `PagamentoService.quitar()` recusa a baixa (§3.8). Cada confirmação aqui
    grava um `QuitacaoConsumo` no banco (valor, data/hora, quem autorizou),
    dado bruto para o `sales_analytics` mais pra frente.
    """

    def __init__(self, nome_funcionario: str, saldo: Decimal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Dar baixa no consumo — {nome_funcionario}")

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Consumo atual: {_formatar_reais(saldo)}"))

        formulario = QFormLayout()

        self._campo_valor = QLineEdit(_formatar_campo(saldo))
        formulario.addRow("Valor descontado do salário", self._campo_valor)

        self._campo_pin_gerente = QLineEdit()
        self._campo_pin_gerente.setEchoMode(QLineEdit.EchoMode.Password)
        formulario.addRow("PIN do gerente", self._campo_pin_gerente)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Dar baixa")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[Decimal, str]:
        valor = Decimal(self._campo_valor.text().strip().replace(",", "."))
        pin_gerente = self._campo_pin_gerente.text().strip()
        return valor, pin_gerente


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def _formatar_campo(valor: Decimal) -> str:
    return f"{valor:.2f}".replace(".", ",")
