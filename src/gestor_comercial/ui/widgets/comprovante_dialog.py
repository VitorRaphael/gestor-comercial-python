"""Modal do comprovante digital de fechamento de caixa (tela de Relatórios).

Renderiza o `Documento` de `comprovante_fechamento` como texto monoespaçado,
simulando a bobina térmica dentro de um painel com fundo contrastante. Não
tem regra de negócio: só pede os dataclasses prontos ao `CaixaService` e
manda para `comprovante_fechamento.montar_documento`.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services import comprovante_fechamento

# Courier New é a fonte monoespaçada padrão do Windows — mesma escolha do
# `_DriverArquivo` (que só simula em texto puro). Consolas como alternativa
# em máquinas onde Courier New não estiver disponível.
_FONTE_MONOESPACADA = ["Courier New", "Consolas", "monospace"]


class ComprovanteFechamentoDialog(QDialog):
    """Comprovante digital de um fechamento: texto do cupom + copiar/exportar."""

    def __init__(self, caixa: Caixa, texto: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._caixa = caixa
        self._texto = texto
        self.setWindowTitle(f"Comprovante — Caixa {caixa.id}")
        self.resize(520, 720)
        self.setObjectName("comprovanteDialog")

        layout = QVBoxLayout(self)

        titulo = QLabel("Comprovante Digital de Fechamento")
        titulo.setStyleSheet("font-weight: 600; font-size: 16px;")
        layout.addWidget(titulo)

        self._papel = QPlainTextEdit()
        self._papel.setReadOnly(True)
        self._papel.setPlainText(texto)
        fonte = QFont(_FONTE_MONOESPACADA)
        fonte.setStyleHint(QFont.StyleHint.Monospace)
        fonte.setPointSize(10)
        self._papel.setFont(fonte)
        self._papel.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._papel.setObjectName("comprovantePapel")
        layout.addWidget(self._papel, 1)

        rodape = QHBoxLayout()
        self._label_status = QLabel("")
        self._label_status.setObjectName("comprovanteStatus")
        rodape.addWidget(self._label_status)
        rodape.addStretch()

        botao_copiar = QPushButton("Copiar")
        botao_copiar.setProperty("variante", "secundario")
        botao_copiar.clicked.connect(self._copiar)
        rodape.addWidget(botao_copiar)

        botao_exportar = QPushButton("Exportar .txt")
        botao_exportar.setProperty("variante", "primario")
        botao_exportar.clicked.connect(self._exportar)
        rodape.addWidget(botao_exportar)
        layout.addLayout(rodape)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botoes.rejected.connect(self.reject)
        botoes.accepted.connect(self.accept)
        botoes.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(botoes)

    def _copiar(self) -> None:
        QApplication.clipboard().setText(self._texto)
        self._label_status.setText("Copiado para a área de transferência.")

    def _exportar(self) -> None:
        sugestao = f"fechamento_caixa_{self._caixa.id}.txt"
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar comprovante", sugestao, "Texto (*.txt)"
        )
        if not caminho:
            return
        try:
            with open(caminho, "w", encoding="utf-8", newline="\n") as arquivo:
                arquivo.write(self._texto)
        except OSError as erro:
            QMessageBox.critical(self, "Erro ao exportar", f"Não foi possível salvar o arquivo: {erro}")
            return
        self._label_status.setText(f"Exportado para {caminho}")


def montar_texto_comprovante(caixa_service: CaixaService, caixa: Caixa) -> str:
    """Monta o texto do comprovante de `caixa` a partir do `CaixaService`.

    Isolado da classe do modal para poder ser testado (e reaproveitado, se
    algum dia a exportação em lote precisar do mesmo texto) sem instanciar
    um `QDialog`.
    """
    titulo = None
    if caixa.numero_sequencial_dia is not None and caixa.fechado_em is not None:
        titulo = caixa_service.titulo_fechamento(caixa.id)
    resumo = caixa_service.resumo(caixa.id)
    conferencia = caixa_service.conferencia_pagamentos(caixa.id)
    grupos_categoria = caixa_service.resumo_vendas_por_categoria(caixa.id)
    movimentos = caixa_service.listar_movimentos(caixa.id)
    conferido_por = caixa_service.auth.usuario_atual().nome

    documento = comprovante_fechamento.montar_documento(
        caixa=caixa,
        titulo_fechamento=titulo,
        resumo=resumo,
        conferencia=conferencia,
        grupos_categoria=grupos_categoria,
        movimentos=movimentos,
        conferido_por=conferido_por,
        agora=datetime.now(),
    )
    return comprovante_fechamento.renderizar_texto(documento)
