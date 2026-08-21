"""Funcionários: cadastro, desativação e dívida de consumo interno — porte
visual da tela de funcionários do front-end web
(`GESTOR COMERCIAL/.../desktop/js/app.js`, funções
`salvarFuncionario`/`quitarConsumo`).

Cadastrar e desativar exigem gerente logado, e quitar dívida exige o PIN de
um gerente digitado na hora (reautenticação, não a sessão corrente) — quem
barra isso é `AuthService`/`PagamentoService`; aqui só se mostra o erro que
o service levantar.
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
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.enums import PerfilFuncionario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.pagamento_service import PagamentoService

_COLUNAS = ["Nome", "Perfil", "Status", "Saldo devedor"]

_ROTULOS_PERFIL = {
    PerfilFuncionario.ATENDENTE: "Atendente",
    PerfilFuncionario.GERENTE: "Gerente",
}

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)


class FuncionariosView(QWidget):
    """CRUD básico de funcionário e quitação de saldo devedor de consumo interno."""

    def __init__(
        self,
        auth_service: AuthService,
        pagamento_service: PagamentoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._auth = auth_service
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
        self._botao_desativar = QPushButton("Desativar")
        self._botao_desativar.setProperty("variante", "perigo")
        self._botao_desativar.clicked.connect(self._desativar)
        acoes.addWidget(self._botao_desativar)

        self._botao_quitar = QPushButton("Quitar consumo")
        self._botao_quitar.clicked.connect(self._quitar)
        acoes.addWidget(self._botao_quitar)
        acoes.addStretch()
        layout.addLayout(acoes)

        self.atualizar()

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._funcionarios = self._auth.listar_todos()
        self._saldos = self._carregar_saldos()

        self._tabela.setRowCount(len(self._funcionarios))
        for linha, funcionario in enumerate(self._funcionarios):
            self._tabela.setItem(linha, 0, QTableWidgetItem(funcionario.nome))
            self._tabela.setItem(
                linha, 1, QTableWidgetItem(_ROTULOS_PERFIL.get(funcionario.perfil, funcionario.perfil.value))
            )
            status = "Ativo" if funcionario.ativo else "Desativado"
            self._tabela.setItem(linha, 2, QTableWidgetItem(status))
            saldo = self._saldos.get(funcionario.id, Decimal("0"))
            self._tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(saldo)))

    def _carregar_saldos(self) -> dict[int, Decimal]:
        # Consultar a dívida exige gerente logado (§3.8); num app sem gerente
        # na sessão, a coluna some por ora — a listagem de nome/perfil/status
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
        modal = _FuncionarioDialog(self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        nome, pin, perfil = modal.resultado()

        self._label_erro.setText("")
        try:
            self._auth.criar_funcionario(nome, pin, perfil)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _desativar(self) -> None:
        funcionario = self._funcionario_selecionado()
        if funcionario is None:
            return
        self._label_erro.setText("")
        try:
            self._auth.desativar_funcionario(funcionario.id)
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
            self._label_erro.setText(f"{funcionario.nome} não tem saldo devedor em aberto.")
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
    """Modal de cadastro: nome, PIN e perfil."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Novo funcionário")

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_nome = QLineEdit()
        formulario.addRow("Nome", self._campo_nome)

        self._campo_pin = QLineEdit()
        self._campo_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_pin.setPlaceholderText("4 a 8 dígitos")
        formulario.addRow("PIN", self._campo_pin)

        self._seletor_perfil = QComboBox()
        for perfil, rotulo in _ROTULOS_PERFIL.items():
            self._seletor_perfil.addItem(rotulo, perfil)
        formulario.addRow("Perfil", self._seletor_perfil)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[str, str, PerfilFuncionario]:
        nome = self._campo_nome.text().strip()
        pin = self._campo_pin.text().strip()
        perfil = self._seletor_perfil.currentData()
        return nome, pin, perfil


class _QuitarConsumoDialog(QDialog):
    """Modal de quitação: valor a abater e PIN de um gerente para autorizar."""

    def __init__(self, nome_funcionario: str, saldo: Decimal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Quitar consumo — {nome_funcionario}")

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Saldo devedor atual: {_formatar_reais(saldo)}"))

        formulario = QFormLayout()

        self._campo_valor = QLineEdit(_formatar_campo(saldo))
        formulario.addRow("Valor a quitar", self._campo_valor)

        self._campo_pin_gerente = QLineEdit()
        self._campo_pin_gerente.setEchoMode(QLineEdit.EchoMode.Password)
        formulario.addRow("PIN do gerente", self._campo_pin_gerente)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Quitar")
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
