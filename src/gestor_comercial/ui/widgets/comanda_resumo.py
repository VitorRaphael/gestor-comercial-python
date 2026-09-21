"""O cartão "Resumo da comanda" da tela da mesa (§9.27).

Itens lançados, o que aguarda envio e o TOTAL ESTIMADO no bloco âmbar — a
barra "TOTAL" solta no pé da tela antiga, agora com a decomposição que o
operador fazia de cabeça ("quanto disso a cozinha ainda nem viu?").

Nenhuma conta nasce aqui: os três números são propriedades do
`PainelDaComanda`, e o total é a soma dos itens e nada mais — sem taxa de
serviço desde o §9.26. Por isso a nota do bloco diz o que o número É ("soma
dos itens da comanda"), e não o que ele não é: o "Não inclui taxa de serviço"
do mockup falaria de uma coisa que o sistema não tem mais.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gestor_comercial.services.comanda_service import PainelDaComanda
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

ROTULO_TOTAL_ABERTA = "TOTAL ESTIMADO"
# Em conferência os itens estão travados: o número deixou de ser estimativa.
ROTULO_TOTAL_CONFERENCIA = "TOTAL DA CONTA"
NOTA_TOTAL = "Soma dos itens da comanda"


class ComandaResumoWidget(PainelPontilhado):
    """Os totais da comanda, lidos do instantâneo a cada recarga."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mesaDetCartao")
        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(18, 14, 18, 16)
        coluna.setSpacing(0)

        sobrescrito = QLabel("RESUMO DA COMANDA")
        sobrescrito.setObjectName("mesaDetRotuloSecao")
        coluna.addWidget(sobrescrito)
        coluna.addSpacing(3)
        subtitulo = QLabel("Atualizado a cada item lançado")
        subtitulo.setObjectName("mesaDetCartaoSubtitulo")
        coluna.addWidget(subtitulo)
        coluna.addSpacing(4)

        _linha, self._valor_enviado = self._linha(coluna, "Itens lançados")
        _linha, self._valor_pendente = self._linha(coluna, "Aguardando envio")
        self._valor_pendente.setProperty("tom", "pendente")
        self._linha_recebido, self._valor_recebido = self._linha(coluna, "Já recebido")
        self._linha_recebido.setVisible(False)
        coluna.addSpacing(12)

        bloco = QFrame()
        bloco.setObjectName("mesaDetTotalCard")
        dentro = QVBoxLayout(bloco)
        dentro.setContentsMargins(16, 10, 16, 10)
        dentro.setSpacing(2)
        self._rotulo_total = QLabel(ROTULO_TOTAL_ABERTA)
        self._rotulo_total.setObjectName("mesaDetTotalRotulo")
        dentro.addWidget(self._rotulo_total)
        self._valor_total = QLabel(formatar_reais(0))
        self._valor_total.setObjectName("mesaDetTotalValor")
        dentro.addWidget(self._valor_total)
        nota = QLabel(NOTA_TOTAL)
        nota.setObjectName("mesaDetTotalNota")
        dentro.addWidget(nota)
        coluna.addWidget(bloco)

    @staticmethod
    def _linha(coluna: QVBoxLayout, rotulo: str) -> tuple[QFrame, QLabel]:
        linha = QFrame()
        linha.setObjectName("mesaDetResumoLinha")
        dentro = QHBoxLayout(linha)
        dentro.setContentsMargins(0, 8, 0, 8)
        nome = QLabel(rotulo)
        nome.setObjectName("mesaDetResumoRotulo")
        dentro.addWidget(nome)
        dentro.addStretch()
        valor = QLabel(formatar_reais(0))
        valor.setObjectName("mesaDetResumoValor")
        dentro.addWidget(valor)
        coluna.addWidget(linha)
        return linha, valor

    def mostrar(self, painel: PainelDaComanda) -> None:
        self._valor_enviado.setText(formatar_reais(painel.total_enviado))
        self._valor_pendente.setText(formatar_reais(painel.total_pendente))
        # Só existe depois de um pagamento parcial: numa mesa comum a linha
        # "Já recebido R$ 0,00" seria ruído em toda conta.
        self._linha_recebido.setVisible(painel.total_pago > 0)
        self._valor_recebido.setText(formatar_reais(painel.total_pago))
        self._rotulo_total.setText(
            ROTULO_TOTAL_CONFERENCIA if painel.em_conferencia else ROTULO_TOTAL_ABERTA
        )
        self._valor_total.setText(formatar_reais(painel.total))

    @property
    def texto_total(self) -> str:
        return self._valor_total.text()
