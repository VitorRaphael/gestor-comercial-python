"""Os dois cartões de itens da tela da mesa (§9.27).

"Aguardando envio" (o que a cozinha ainda não viu, com o "Enviar à produção" no
cabeçalho) e "Itens em produção" (o que já foi, agrupado por produto e preço)
são o MESMO cartão com outras palavras dentro: título, subtítulo, glifo, a
palavra do botão da linha e se ele tem a moldura de destaque. A tela antiga os
montava duas vezes, com duas `QTableWidget` e duas cópias do preenchimento.

## Linhas recicladas

Cada linha é um widget, e não pintura de delegado como o Cardápio (§9.11): ela
tem um controle de verdade dentro, o Remover/Cancelar — a regra do §9.15. Mas
ela NÃO é recriada a cada recarga. A tela recarrega a cada item lançado pelo
modal "Adicionar item", e a antiga destruía e refazia todas as células a cada
lançamento, polindo cada uma contra o QSS global (o custo que o §9.11 mediu).
Aqui `mostrar()` troca o texto das linhas que já existem, cria só as que faltam
e destrói na hora as que sobram — trocar de uma mesa de dez itens para uma de
dois solta oito linhas NAQUELE instante, sem esperar a próxima coleta:

* o botão de cada linha é ligado UMA vez, quando a linha nasce, a um método
  dela mesma — nada de `lambda` capturando o item a cada recarga;
* a linha guarda o instantâneo imutável (`LinhaDoPainel`), e não o
  `ItemComanda`: o clique devolve os ids que estavam na tela;
* a linha que sai é desligada pelo nome, sai do layout, perde o pai e recebe
  `deleteLater()` — o arranjo do `composicao_combo_dialog` (§9.15).
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from gestor_comercial.services.comanda_service import LinhaDoPainel
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_LIXEIRA,
    BotaoComGlifo,
    RotuloComReticencias,
    badge_com_glifo,
)
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado


class Colunas:
    """As larguras fixas das colunas de valor, iguais no cabeçalho e nas linhas.

    O nome é a única coluna que estica: é ela que absorve a largura da janela,
    e as outras ficam alinhadas em qualquer resolução. A da ação cabe
    "Cancelar" com a lixeira na fonte da marca (medido na renderização).
    """

    PRECO = 84
    QUANTIDADE = 40
    TOTAL = 90
    ACAO = 104
    ESPACO = 8


def _valor(nome_objeto: str, largura: int) -> QLabel:
    rotulo = QLabel("")
    rotulo.setObjectName(nome_objeto)
    rotulo.setFixedWidth(largura)
    rotulo.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return rotulo


class LinhaDeItem(QFrame):
    """Uma linha de item: nome (e observação), preço, quantidade, total e a ação."""

    acao_pedida = Signal(object)

    def __init__(self, rotulo_acao: str, dica_acao: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mesaDetLinha")
        self._linha: LinhaDoPainel | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 9, 0, 9)
        layout.setSpacing(Colunas.ESPACO)

        textos = QVBoxLayout()
        textos.setSpacing(1)
        self._nome = RotuloComReticencias()
        self._nome.setObjectName("mesaDetItemNome")
        textos.addWidget(self._nome)
        self._observacao = RotuloComReticencias()
        self._observacao.setObjectName("mesaDetItemObs")
        self._observacao.setVisible(False)
        textos.addWidget(self._observacao)
        layout.addLayout(textos, 1)

        self._preco = _valor("mesaDetItemValor", Colunas.PRECO)
        layout.addWidget(self._preco)
        self._quantidade = _valor("mesaDetItemQtd", Colunas.QUANTIDADE)
        layout.addWidget(self._quantidade)
        self._total = _valor("mesaDetItemTotal", Colunas.TOTAL)
        layout.addWidget(self._total)

        self._botao = BotaoComGlifo(
            rotulo_acao, GLIFO_LIXEIRA, "mesa_detalhe_perigo_texto", "pilula_disabled_texto", centrado=True
        )
        self._botao.setObjectName("mesaDetAcaoItem")
        self._botao.setToolTip(dica_acao)
        self._botao.setFixedWidth(Colunas.ACAO)
        self._botao.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao.clicked.connect(self._pedir)
        layout.addWidget(self._botao)

    @property
    def linha(self) -> LinhaDoPainel | None:
        return self._linha

    @property
    def botao(self) -> BotaoComGlifo:
        return self._botao

    def preencher(self, linha: LinhaDoPainel, *, acao_ligada: bool) -> None:
        """Troca o conteúdo da linha. Não cria nem liga nada."""
        self._botao.setEnabled(acao_ligada)
        if linha == self._linha:
            return
        self._linha = linha
        self._nome.setText(linha.nome)
        self._observacao.setText(linha.observacao or "")
        self._observacao.setVisible(bool(linha.observacao))
        self._preco.setText(formatar_reais(linha.preco_unit))
        self._quantidade.setText(str(linha.quantidade))
        self._total.setText(formatar_reais(linha.total))

    def soltar(self) -> None:
        """Desliga o botão pelo nome — a primeira coisa antes de destruir a linha."""
        self._botao.clicked.disconnect(self._pedir)

    def _pedir(self) -> None:
        if self._linha is not None:
            self.acao_pedida.emit(self._linha)


class CartaoDeItens(PainelPontilhado):
    """Um dos dois cartões de itens: cabeçalho, títulos das colunas e as linhas."""

    acao_pedida = Signal(object)

    def __init__(
        self,
        *,
        glifo: str,
        titulo: str,
        subtitulo: str,
        vazio: str,
        rotulo_acao: str,
        dica_acao: str,
        destaque: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mesaDetCartao")
        # A moldura de destaque só acende com linha dentro: "Aguardando envio"
        # vazio em petróleo diria que há o que mandar para a cozinha.
        self._destaque = destaque
        self.setProperty("destaque", False)
        self._rotulo_acao = rotulo_acao
        self._dica_acao = dica_acao
        self._linhas: list[LinhaDeItem] = []

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(18, 14, 18, 8)
        coluna.setSpacing(0)

        self._cabecalho = QHBoxLayout()
        self._cabecalho.setSpacing(12)
        tom = "pendente" if destaque else ""
        token = "mesa_detalhe_pendente_destaque" if destaque else "mesa_detalhe_badge_glifo"
        self._cabecalho.addWidget(
            badge_com_glifo(glifo, "mesaDetBadge", token, tom=tom), 0, Qt.AlignmentFlag.AlignVCenter
        )
        textos = QVBoxLayout()
        textos.setSpacing(2)
        self._titulo = QLabel(titulo)
        self._titulo.setObjectName("mesaDetCartaoTitulo")
        textos.addWidget(self._titulo)
        subtitulo_rotulo = QLabel(subtitulo)
        subtitulo_rotulo.setObjectName("mesaDetCartaoSubtitulo")
        textos.addWidget(subtitulo_rotulo)
        self._cabecalho.addLayout(textos, 1)
        coluna.addLayout(self._cabecalho)
        coluna.addSpacing(12)

        self._titulos_colunas = QFrame()
        self._titulos_colunas.setObjectName("mesaDetColunas")
        faixa = QHBoxLayout(self._titulos_colunas)
        faixa.setContentsMargins(0, 8, 0, 8)
        faixa.setSpacing(Colunas.ESPACO)
        rotulo_item = QLabel("ITEM")
        rotulo_item.setObjectName("mesaDetColunaRotulo")
        faixa.addWidget(rotulo_item, 1)
        for texto, largura in (
            ("PREÇO", Colunas.PRECO),
            ("QTD", Colunas.QUANTIDADE),
            ("TOTAL", Colunas.TOTAL),
            ("", Colunas.ACAO),
        ):
            rotulo = _valor("mesaDetColunaRotulo", largura)
            rotulo.setText(texto)
            faixa.addWidget(rotulo)
        coluna.addWidget(self._titulos_colunas)

        self._corpo = QVBoxLayout()
        self._corpo.setSpacing(0)
        coluna.addLayout(self._corpo)

        self._vazio = QLabel(vazio)
        self._vazio.setObjectName("mesaDetVazio")
        coluna.addWidget(self._vazio)

    def adicionar_ao_cabecalho(self, widget: QWidget) -> None:
        """Põe um widget na ponta direita do cabeçalho: o botão de envio, a pílula."""
        self._cabecalho.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    @property
    def linhas(self) -> list[LinhaDeItem]:
        """As linhas vivas, na ordem da tela. Cópia: quem lê não mexe no pool."""
        return list(self._linhas)

    def mostrar(self, linhas: Sequence[LinhaDoPainel], *, acao_ligada: bool) -> None:
        """Mostra `linhas`, reaproveitando as linhas-widget que já existem."""
        while len(self._linhas) < len(linhas):
            linha = LinhaDeItem(self._rotulo_acao, self._dica_acao)
            linha.acao_pedida.connect(self._repassar)
            self._corpo.addWidget(linha)
            self._linhas.append(linha)
        while len(self._linhas) > len(linhas):
            self._descartar(self._linhas.pop())

        for widget, linha in zip(self._linhas, linhas, strict=True):
            widget.preencher(linha, acao_ligada=acao_ligada)
        # A última linha não tem a borda de baixo: quem fecha o cartão é a
        # própria moldura, e a borda sobrando parecia uma linha vazia.
        for posicao, widget in enumerate(self._linhas):
            ultima = posicao == len(self._linhas) - 1
            if widget.property("ultima") != ultima:
                aplicar_propriedade(widget, "ultima", ultima)

        vazio = not linhas
        self._titulos_colunas.setVisible(not vazio)
        self._vazio.setVisible(vazio)
        destacado = self._destaque and not vazio
        if self.property("destaque") != destacado:
            aplicar_propriedade(self, "destaque", destacado)

    @property
    def destacado(self) -> bool:
        return bool(self.property("destaque"))

    def _repassar(self, linha: LinhaDoPainel) -> None:
        self.acao_pedida.emit(linha)

    def _descartar(self, linha: LinhaDeItem) -> None:
        """Destrói a linha AGORA — ver "Linhas recicladas" no cabeçalho."""
        linha.acao_pedida.disconnect(self._repassar)
        linha.soltar()
        self._corpo.removeWidget(linha)
        linha.hide()
        linha.setParent(None)
        linha.deleteLater()
