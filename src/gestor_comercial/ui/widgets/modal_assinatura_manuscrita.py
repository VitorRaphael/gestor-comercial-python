"""Modal de assinatura do consumo interno — substitui o PIN do gerente no caixa.

A tela coleta; quem grava é o `PagamentoService.registrar`, que revalida o
traço (`services/assinatura.py`) e salva pagamento + assinatura no mesmo
commit. O modal só devolve o JSON em `traco_json`.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.consumo_estilo import aplicar_estilo_cartao
from gestor_comercial.ui.widgets.signature_pad import SignaturePadWidget


class ModalAssinaturaManuscrita(QDialog):
    def __init__(
        self,
        nome_funcionario: str,
        quantidade_itens: int,
        total: Decimal,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("modalAssinaturaManuscrita")
        self.setWindowTitle("Assinatura de Consumo Interno")
        self.setModal(True)
        self.traco_json: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(12)
        icone = QLabel("✍")
        icone.setObjectName("consumoIcone")
        cabecalho.addWidget(icone)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel("Assinatura de Consumo Interno")
        titulo.setObjectName("consumoTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel(f"Colaborador: {nome_funcionario}")
        subtitulo.setObjectName("consumoSubtitulo")
        textos.addWidget(subtitulo)
        cabecalho.addLayout(textos, 1)
        layout.addLayout(cabecalho)

        resumo = QFrame()
        resumo.setObjectName("consumoResumo")
        dentro = QHBoxLayout(resumo)
        dentro.setContentsMargins(14, 10, 14, 10)
        rotulo_itens = "item" if quantidade_itens == 1 else "itens"
        self._label_resumo = QLabel(
            f"{quantidade_itens} {rotulo_itens}  |  Total: {formatar_reais(total)}"
        )
        self._label_resumo.setObjectName("consumoResumoTexto")
        dentro.addWidget(self._label_resumo)
        layout.addWidget(resumo)

        instrucao = QLabel("Assine com o mouse na área abaixo")
        instrucao.setObjectName("consumoRotulo")
        layout.addWidget(instrucao)

        self.pad = SignaturePadWidget()
        self.pad.assinatura_alterada.connect(self._ao_alterar)
        layout.addWidget(self.pad, 1)

        rodape = QHBoxLayout()
        self.botao_limpar = QPushButton("↺  Limpar")
        self.botao_limpar.setProperty("variante", "neutro")
        self.botao_limpar.clicked.connect(self.pad.limpar)
        rodape.addWidget(self.botao_limpar)
        rodape.addStretch()
        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.setProperty("variante", "neutro")
        botao_cancelar.clicked.connect(self.reject)
        rodape.addWidget(botao_cancelar)
        self.botao_confirmar = QPushButton("✓  Confirmar e Finalizar")
        self.botao_confirmar.setProperty("variante", "primario")
        self.botao_confirmar.setEnabled(False)
        self.botao_confirmar.clicked.connect(self._confirmar)
        rodape.addWidget(self.botao_confirmar)
        layout.addLayout(rodape)

        aplicar_estilo_cartao(self)
        self.resize(600, 460)

    def _ao_alterar(self, tem_traco: bool) -> None:
        self.botao_confirmar.setEnabled(tem_traco)

    def _confirmar(self) -> None:
        if not self.pad.tem_traco:
            return
        self.traco_json = self.pad.para_json()
        self.accept()
