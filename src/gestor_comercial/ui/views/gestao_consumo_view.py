"""Gestão de Consumo Interno de um funcionário — aberta pelo "Ver consumo".

Mostra as retiradas em aberto (um cartão "SESSÃO DE RETIRADA #XXXX" por
consumo lançado no caixa) e, abaixo, o histórico já baixado. Dois cliques num
cartão abrem o `ModalDetalhesRetirada` com os itens e a assinatura redesenhada.

"Dar baixa no consumo" quita TUDO que está em aberto numa transação só
(`PagamentoService.dar_baixa_no_consumo`). Pede o PIN do gerente: a baixa é
desconto no salário, e o `QuitacaoConsumo` grava quem autorizou.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.pagamento_service import PagamentoService, SessaoDeRetirada
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.consumo_estilo import aplicar_estilo_cartao
from gestor_comercial.ui.widgets.layout_utils import limpar_layout, rolagem_vertical
from gestor_comercial.ui.widgets.modais import executar_modal
from gestor_comercial.ui.widgets.modal_detalhes_retirada import ModalDetalhesRetirada
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)


class CartaoRetirada(QFrame):
    """Um cartão "SESSÃO DE RETIRADA #XXXX"; dois cliques pedem o detalhe."""

    duplo_clique = Signal(object)  # SessaoDeRetirada

    def __init__(self, sessao: SessaoDeRetirada, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sessao = sessao
        self.setObjectName("consumoResumo" if sessao.ativa else "consumoCartaoHistorico")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Dois cliques para ver os itens e a assinatura")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel(f"SESSÃO DE RETIRADA #{sessao.identificador}")
        titulo.setObjectName("consumoRotulo")
        textos.addWidget(titulo)
        n = sessao.quantidade_itens
        situacao = "" if sessao.ativa else "  ·  baixada"
        detalhe = QLabel(
            f"{sessao.data_hora:%d/%m/%Y %H:%M}  ·  {n} {'item' if n == 1 else 'itens'}{situacao}"
        )
        detalhe.setObjectName("consumoSubtitulo")
        textos.addWidget(detalhe)
        layout.addLayout(textos, 1)
        valor = QLabel(formatar_reais(sessao.valor))
        valor.setObjectName("consumoResumoTexto" if sessao.ativa else "consumoSubtitulo")
        layout.addWidget(valor)

    @nao_deixa_escapar()
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.duplo_clique.emit(self.sessao)


class GestaoConsumoView(QDialog):
    def __init__(
        self,
        funcionario_id: int,
        nome_funcionario: str,
        pagamentos: PagamentoService,
        auth: AuthService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("gestaoConsumoView")
        self.setWindowTitle(f"Gestão de Consumo Interno — {nome_funcionario}")
        self.setModal(True)
        self._funcionario_id = funcionario_id
        self._pagamentos = pagamentos
        self._auth = auth
        self.sessoes: list[SessaoDeRetirada] = []
        self.cartoes: list[CartaoRetirada] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        titulo = QLabel("Gestão de Consumo Interno")
        titulo.setObjectName("consumoTitulo")
        layout.addWidget(titulo)
        self._label_saldo = QLabel("")
        self._label_saldo.setObjectName("consumoSubtitulo")
        layout.addWidget(self._label_saldo)
        self.label_erro = QLabel("")
        self.label_erro.setObjectName("labelErro")
        layout.addWidget(self.label_erro)

        conteudo = QWidget()
        self._lista = QVBoxLayout(conteudo)
        self._lista.setContentsMargins(0, 0, 0, 0)
        self._lista.setSpacing(8)
        layout.addWidget(rolagem_vertical(conteudo, "gestaoConsumoRolagem"), 1)

        rodape = QHBoxLayout()
        botao_fechar = QPushButton("Fechar")
        botao_fechar.setProperty("variante", "neutro")
        botao_fechar.clicked.connect(self.accept)
        rodape.addWidget(botao_fechar)
        rodape.addStretch()
        self.botao_baixa = QPushButton("🗑  Dar baixa no consumo")
        self.botao_baixa.setProperty("variante", "primario")
        self.botao_baixa.clicked.connect(self._dar_baixa)
        rodape.addWidget(self.botao_baixa)
        layout.addLayout(rodape)

        aplicar_estilo_cartao(self)
        self.resize(640, 560)
        self.atualizar()

    def atualizar(self) -> None:
        try:
            self.sessoes = self._pagamentos.sessoes_de_retirada(self._funcionario_id)
        except _ERROS_SERVICE as erro:
            self.label_erro.setText(str(erro))
            return
        limpar_layout(self._lista)
        self.cartoes = []
        ativas = [s for s in self.sessoes if s.ativa]
        historico = [s for s in self.sessoes if not s.ativa]
        em_aberto = sum((s.valor for s in ativas), Decimal("0"))
        self._label_saldo.setText(
            f"{len(ativas)} retirada(s) em aberto  ·  Total: {formatar_reais(em_aberto)}"
        )
        self.botao_baixa.setEnabled(bool(ativas))

        self._secao("EM ABERTO", ativas, "Nenhuma retirada em aberto.")
        if historico:
            self._secao("HISTÓRICO (JÁ BAIXADAS)", historico, "")
        self._lista.addStretch()

    def _secao(self, rotulo: str, sessoes: list[SessaoDeRetirada], vazio: str) -> None:
        cabecalho = QLabel(rotulo)
        cabecalho.setObjectName("consumoRotulo")
        self._lista.addWidget(cabecalho)
        if not sessoes and vazio:
            aviso = QLabel(vazio)
            aviso.setObjectName("consumoSubtitulo")
            self._lista.addWidget(aviso)
        for sessao in sessoes:
            cartao = CartaoRetirada(sessao)
            cartao.duplo_clique.connect(self.abrir_detalhes)
            self._lista.addWidget(cartao)
            self.cartoes.append(cartao)

    def abrir_detalhes(self, sessao: SessaoDeRetirada) -> None:
        executar_modal(ModalDetalhesRetirada(sessao, self))

    def _pedir_pin(self) -> str | None:
        modal = PinPadDialog.para_consumo_interno(self._auth, self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return None
        return modal.pin_confirmado

    def _dar_baixa(self) -> None:
        pin = self._pedir_pin()
        if pin is None:
            return
        self.label_erro.setText("")
        try:
            self._pagamentos.dar_baixa_no_consumo(self._funcionario_id, pin)
        except _ERROS_SERVICE as erro:
            self.label_erro.setText(str(erro))
            return
        self.atualizar()
