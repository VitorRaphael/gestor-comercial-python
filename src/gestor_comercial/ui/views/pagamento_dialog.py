"""Modal de recebimento da conta — porte visual de `abrirModalPagamento` /
`corpoModalPagamento` do front-end web (`GESTOR COMERCIAL/.../desktop/js/app.js`).

Fica aberto recebendo pagamentos parciais até a comanda fechar (igual ao JS:
só chama `fecharModal()` quando `resposta.comandaFechada`); a cada pagamento
o resumo (total/pago/restante/troco) é atualizado na tela.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.enums import FormaPagamento
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.pagamento_service import PagamentoService, ResumoPagamento
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.theme.controller import ThemeController

_ROTULOS_FORMA = {
    FormaPagamento.CREDITO: "Crédito",
    FormaPagamento.DEBITO: "Débito",
    FormaPagamento.DINHEIRO: "Dinheiro",
    FormaPagamento.PIX: "PIX",
    FormaPagamento.CONSUMO_INTERNO: "Consumo interno",
}


class PagamentoDialog(QDialog):
    """Pagamento da comanda: resumo, forma, valor, troco e consumo interno."""

    def __init__(
        self,
        pagamento_service: PagamentoService,
        comanda_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pagamento da comanda")
        self._pagamentos = pagamento_service
        self._comanda_id = comanda_id
        self.comanda_fechada = False

        self._montar_layout()
        self._atualizar_resumo()

    def _montar_layout(self) -> None:
        layout = QVBoxLayout(self)

        self._label_resumo = QLabel("")
        layout.addWidget(self._label_resumo)

        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        layout.addWidget(self._label_erro)

        formulario = QFormLayout()

        self._combo_forma = QComboBox()
        for forma, rotulo in _ROTULOS_FORMA.items():
            self._combo_forma.addItem(rotulo, forma)
        self._combo_forma.currentIndexChanged.connect(self._atualizar_visibilidade_consumo)
        formulario.addRow("Forma de pagamento", self._combo_forma)

        self._campo_valor = QLineEdit()
        formulario.addRow("Valor", self._campo_valor)

        self._campo_pin_gerente = QLineEdit()
        self._campo_pin_gerente.setEchoMode(QLineEdit.EchoMode.Password)
        self._linha_pin_gerente = formulario.addRow("PIN do gerente", self._campo_pin_gerente)

        self._combo_funcionario_consumo = QComboBox()
        for funcionario in self._pagamentos.funcionarios.listar_ativos():
            self._combo_funcionario_consumo.addItem(funcionario.nome, funcionario.id)
        self._linha_funcionario_consumo = formulario.addRow(
            "Funcionário", self._combo_funcionario_consumo
        )

        layout.addLayout(formulario)

        self._botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Registrar pagamento")
        self._botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Fechar")
        self._botoes.accepted.connect(self._registrar_pagamento)
        self._botoes.rejected.connect(self.reject)
        layout.addWidget(self._botoes)

        self._atualizar_visibilidade_consumo()

    def _atualizar_visibilidade_consumo(self) -> None:
        consumo_interno = self._combo_forma.currentData() is FormaPagamento.CONSUMO_INTERNO
        for campo, rotulo in (
            (self._campo_pin_gerente, self._linha_pin_gerente),
            (self._combo_funcionario_consumo, self._linha_funcionario_consumo),
        ):
            campo.setVisible(consumo_interno)
            if rotulo is not None:
                rotulo.setVisible(consumo_interno)

    def _atualizar_resumo(self, resumo: ResumoPagamento | None = None) -> None:
        if resumo is None:
            total_conta = self._pagamentos.comandas.calcular_total(self._comanda_id)
            total_pago = self._pagamentos.calcular_total_pago(self._comanda_id)
            restante = self._pagamentos.calcular_restante(self._comanda_id)
            troco = None
        else:
            total_conta = resumo.total_conta
            total_pago = resumo.total_pago
            restante = resumo.restante
            troco = resumo.troco

        linhas = [
            f"Total da conta: {formatar_reais(total_conta)}",
            f"Total pago: {formatar_reais(total_pago)}",
            f"Restante: {formatar_reais(restante)}",
        ]
        if troco is not None:
            linhas.append(f"Troco: {formatar_reais(troco)}")
        self._label_resumo.setText("\n".join(linhas))
        self._campo_valor.setText(f"{restante:.2f}")

    def _registrar_pagamento(self) -> None:
        self._label_erro.setText("")

        forma = self._combo_forma.currentData()
        try:
            valor = Decimal(self._campo_valor.text().strip().replace(",", "."))
        except InvalidOperation:
            self._label_erro.setText("Valor inválido. Informe um valor em reais, como 50.00.")
            return

        pin_gerente = None
        funcionario_consumo_id = None
        if forma is FormaPagamento.CONSUMO_INTERNO:
            pin_gerente = self._campo_pin_gerente.text().strip()
            funcionario_consumo_id = self._combo_funcionario_consumo.currentData()

        try:
            resumo = self._pagamentos.registrar(
                self._comanda_id,
                forma,
                valor,
                pin_gerente=pin_gerente,
                funcionario_consumo_id=funcionario_consumo_id,
            )
        except (
            RegraDeNegocioError,
            RecursoNaoEncontradoError,
            NaoAutorizadoError,
            AcessoNegadoError,
        ) as erro:
            self._label_erro.setText(str(erro))
            return

        self._campo_pin_gerente.clear()
        self._atualizar_resumo(resumo)

        if resumo.comanda_fechada:
            self.comanda_fechada = True
            self.accept()
