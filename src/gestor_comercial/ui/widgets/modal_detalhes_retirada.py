"""Detalhes de uma retirada de consumo interno: itens à esquerda, assinatura à direita.

Só leitura. Recebe a `SessaoDeRetirada` já montada pelo service — o modal não
vai ao banco — e redesenha o traço gravado com `AssinaturaView`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from gestor_comercial.services.pagamento_service import SessaoDeRetirada
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.consumo_estilo import aplicar_estilo_cartao
from gestor_comercial.ui.widgets.layout_utils import rolagem_vertical
from gestor_comercial.ui.widgets.signature_pad import AssinaturaView


class ModalDetalhesRetirada(QDialog):
    def __init__(self, sessao: SessaoDeRetirada, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modalDetalhesRetirada")
        self.setWindowTitle(f"Detalhes da Retirada #{sessao.identificador}")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        titulo = QLabel(f"Detalhes da Retirada #{sessao.identificador}")
        titulo.setObjectName("consumoTitulo")
        layout.addWidget(titulo)
        meta = QLabel(
            f"Data/Hora: {sessao.data_hora:%d/%m/%Y - %H:%M}   ·   "
            f"Funcionário: {sessao.funcionario_nome}"
        )
        meta.setObjectName("consumoSubtitulo")
        layout.addWidget(meta)

        colunas = QHBoxLayout()
        colunas.setSpacing(20)
        colunas.addLayout(self._coluna_itens(sessao), 3)
        colunas.addLayout(self._coluna_assinatura(sessao), 2)
        layout.addLayout(colunas, 1)

        rodape = QHBoxLayout()
        rodape.addStretch()
        botao_fechar = QPushButton("Fechar")
        botao_fechar.setProperty("variante", "neutro")
        botao_fechar.clicked.connect(self.accept)
        rodape.addWidget(botao_fechar)
        layout.addLayout(rodape)

        aplicar_estilo_cartao(self)
        self.resize(820, 480)

    def _coluna_itens(self, sessao: SessaoDeRetirada) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(8)
        cabecalho = QHBoxLayout()
        for texto, estica, alinhamento in (
            ("QTD", 0, Qt.AlignmentFlag.AlignLeft),
            ("DESCRIÇÃO DO PRODUTO", 1, Qt.AlignmentFlag.AlignLeft),
            ("PREÇO UNIT.", 0, Qt.AlignmentFlag.AlignRight),
            ("PREÇO TOTAL", 0, Qt.AlignmentFlag.AlignRight),
        ):
            rotulo = QLabel(texto)
            rotulo.setObjectName("consumoRotulo")
            rotulo.setAlignment(alinhamento)
            if not estica:
                rotulo.setMinimumWidth(90 if texto != "QTD" else 40)
            cabecalho.addWidget(rotulo, estica)
        coluna.addLayout(cabecalho)

        conteudo = QWidget()
        linhas = QVBoxLayout(conteudo)
        linhas.setContentsMargins(0, 0, 0, 0)
        linhas.setSpacing(0)
        self.linhas_itens: list[QFrame] = []
        for item in sessao.itens:
            linha = QFrame()
            linha.setObjectName("consumoLinhaItem")
            dentro = QHBoxLayout(linha)
            dentro.setContentsMargins(0, 8, 0, 8)
            qtd = QLabel(f"{item.quantidade}×")
            qtd.setMinimumWidth(40)
            dentro.addWidget(qtd)
            dentro.addWidget(QLabel(item.descricao), 1)
            for valor in (item.preco_unitario, item.preco_total):
                label = QLabel(formatar_reais(valor))
                label.setMinimumWidth(90)
                label.setAlignment(Qt.AlignmentFlag.AlignRight)
                dentro.addWidget(label)
            linhas.addWidget(linha)
            self.linhas_itens.append(linha)
        linhas.addStretch()
        coluna.addWidget(rolagem_vertical(conteudo, "consumoItensRolagem"), 1)

        total = QHBoxLayout()
        rotulo_total = QLabel("TOTAL")
        rotulo_total.setObjectName("consumoRotulo")
        total.addWidget(rotulo_total)
        total.addStretch()
        self.label_total = QLabel(formatar_reais(sessao.valor))
        self.label_total.setObjectName("consumoTotal")
        total.addWidget(self.label_total)
        coluna.addLayout(total)
        return coluna

    def _coluna_assinatura(self, sessao: SessaoDeRetirada) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(8)
        rotulo = QLabel("ASSINATURA REGISTRADA")
        rotulo.setObjectName("consumoRotulo")
        coluna.addWidget(rotulo)
        self.quadro_assinatura = AssinaturaView(sessao.traco_json)
        coluna.addWidget(self.quadro_assinatura, 1)
        return coluna
