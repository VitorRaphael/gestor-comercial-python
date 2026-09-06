"""Painéis de fechamento reusados pelas duas telas de Relatórios (Histórico
Diário e Dashboard Mensal).

Os dois painéis do rodapé — "FECHAMENTO DA GAVETA" e "PERFORMANCE POR
ATENDENTE" — mostram o **mesmo** `FechamentoGaveta` e o **mesmo**
`ranking_por_atendente` do `CaixaService`, um por período do mês e outro pelo
mês civil inteiro. Estavam montados e preenchidos por código idêntico nos dois
arquivos de view (§6, Fase 6): mudar o rótulo de uma linha ou o texto de "sem
atendente" numa tela deixava a outra para trás.

Também mora aqui a linha "nome + valor + barra de proporção", que as duas telas
usavam com dois nomes diferentes (`_criar_linha_forma` e
`_criar_linha_atendente`) para código igual.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.services.caixa_service import FechamentoGaveta, ItemRankingAtendente
from gestor_comercial.ui.formatacao import formatar_reais, formatar_reais_com_sinal
from gestor_comercial.ui.widgets.layout_utils import limpar_layout

_SEM_VALOR = "—"
_MENSAGEM_SEM_ATENDENTE = "Nenhuma venda vinculada a atendente neste período."


def linha_barra_proporcao(nome: str, valor: Decimal, percentual: Decimal) -> QVBoxLayout:
    """Nome + valor em reais, barra de proporção e o percentual embaixo.

    Usada pela composição por forma de pagamento e pelos dois painéis de
    atendentes. O percentual entra na barra saturado em 0–100: o cálculo vem
    do service já em porcentagem, mas a barra não pode quebrar se um
    arredondamento devolver 100,4.
    """
    bloco = QVBoxLayout()
    bloco.setSpacing(4)

    topo = QHBoxLayout()
    label_nome = QLabel(nome)
    label_nome.setObjectName("relatoriosFormaNome")
    topo.addWidget(label_nome)
    topo.addStretch()
    label_valor = QLabel(formatar_reais(valor))
    label_valor.setObjectName("relatoriosFormaValor")
    topo.addWidget(label_valor)
    bloco.addLayout(topo)

    barra = QProgressBar()
    barra.setObjectName("relatoriosBarraForma")
    barra.setRange(0, 100)
    barra.setValue(min(100, max(0, int(percentual))))
    barra.setTextVisible(False)
    bloco.addWidget(barra)

    label_percentual = QLabel(f"{percentual:.1f}%")
    label_percentual.setObjectName("relatoriosFormaPercentual")
    bloco.addWidget(label_percentual)
    return bloco


class PainelGaveta(QFrame):
    """"FECHAMENTO DA GAVETA": identificação do período, total faturado, saldo
    apurado e a diferença (quebra/sobra) com sinal."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("relatoriosPainel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        titulo = QLabel("FECHAMENTO DA GAVETA")
        titulo.setObjectName("relatoriosPainelTitulo")
        layout.addWidget(titulo)

        self._label_identificacao = QLabel(_SEM_VALOR)
        self._label_identificacao.setObjectName("relatoriosFormaNome")
        self._label_identificacao.setWordWrap(True)
        layout.addWidget(self._label_identificacao)

        linha_faturado, self._label_faturado = _linha_rotulo_valor("Total faturado")
        linha_saldo, self._label_saldo = _linha_rotulo_valor("Saldo apurado")
        linha_diferenca, self._label_diferenca = _linha_rotulo_valor("Diferença (quebra/sobra)")
        layout.addLayout(linha_faturado)
        layout.addLayout(linha_saldo)
        layout.addLayout(linha_diferenca)
        layout.addStretch()

    def preencher(self, gaveta: FechamentoGaveta) -> None:
        self._label_identificacao.setText(gaveta.identificacao)
        self._label_faturado.setText(formatar_reais(gaveta.total_faturado))
        self._label_saldo.setText(formatar_reais(gaveta.saldo_apurado))
        # Diferença é `None` quando o turno não teve as duas contagens da
        # conferência: aí não existe quebra nem sobra para afirmar, e o traço
        # diz isso — zero diria que fechou certinho.
        if gaveta.diferenca is None:
            self._label_diferenca.setText(_SEM_VALOR)
        else:
            self._label_diferenca.setText(formatar_reais_com_sinal(gaveta.diferenca))


class PainelAtendentes(QFrame):
    """"PERFORMANCE POR ATENDENTE": uma linha com barra por atendente, ou a
    mensagem de período sem venda vinculada."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("relatoriosPainel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        titulo = QLabel("PERFORMANCE POR ATENDENTE")
        titulo.setObjectName("relatoriosPainelTitulo")
        layout.addWidget(titulo)

        self._layout_atendentes = QVBoxLayout()
        self._layout_atendentes.setSpacing(10)
        layout.addLayout(self._layout_atendentes)
        layout.addStretch()

    def preencher(self, ranking: list[ItemRankingAtendente]) -> None:
        limpar_layout(self._layout_atendentes)
        if not ranking:
            vazio = QLabel(_MENSAGEM_SEM_ATENDENTE)
            vazio.setObjectName("relatoriosFormaNome")
            self._layout_atendentes.addWidget(vazio)
            return
        for item in ranking:
            self._layout_atendentes.addLayout(
                linha_barra_proporcao(item.atendente_nome, item.valor_total, item.percentual)
            )


def _linha_rotulo_valor(rotulo: str) -> tuple[QHBoxLayout, QLabel]:
    """Uma linha "RÓTULO ... VALOR", devolvendo o `QLabel` do valor para quem
    monta guardar e atualizar depois."""
    linha = QHBoxLayout()
    label_rotulo = QLabel(rotulo)
    label_rotulo.setObjectName("relatoriosRodapeRotulo")
    linha.addWidget(label_rotulo)
    linha.addStretch()
    label_valor = QLabel(_SEM_VALOR)
    label_valor.setObjectName("relatoriosFormaValor")
    linha.addWidget(label_valor)
    return linha, label_valor
