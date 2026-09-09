"""Modal "Nova subcategoria": a subdivisão de uma categoria do cardápio (§9.9).

**Sétimo modal em cartão do app**, e o primeiro que cadastra uma coisa que não
existia antes: até o §9.8 a subcategoria era uma coluna de texto no produto, e
"criar" uma significava digitar a palavra dentro do cadastro de um item. Não
dava para planejar a organização antes de ter os itens — que é justamente como
alguém organiza um cardápio.

## O que a tela mostra, e por quê

O cartão inteiro é sobre **onde** a subdivisão vai morar:

* o **cartão de contexto** no topo diz a categoria e a impressora dela
  (`ACOMPANHAMENTOS · COZINHA`). Está ali por causa da regra de ouro do §9.8: é
  a categoria que decide a bobina, e a subcategoria não muda nada disso. Quem
  cria "Podrão" dentro de "Lanches" vê, na hora, que os itens vão continuar
  saindo na impressora de Lanches;
* o **campo do nome**, com anel de foco e contador de caracteres;
* as **sugestões** — as subdivisões que já existem naquela categoria, como
  pílulas apagadas. Não são clicáveis para preencher: existem para o gerente
  ver o que já tem antes de criar uma quase-igual. Clicar numa delas para
  depois receber "já existe" seria uma armadilha;
* o **rodapé** diz o que vai acontecer com os itens (`OS ITENS ENTRAM DEPOIS,
  PELO CADASTRO DO PRODUTO`), porque a pergunta seguinte de quem acabou de
  criar um grupo vazio é "e agora, cadê os produtos".

## O que este diálogo NÃO faz

Regra de negócio nenhuma. Ele devolve `DadosSubcategoria` e a view chama
`criar_subcategoria`/`editar_subcategoria`; quem exige gerente, quem apara o
nome e quem recusa um nome repetido na mesma categoria (ignorando acento e
caixa) continua sendo o `CardapioService`. A checagem de duplicidade daqui é
**só** um aviso enquanto se digita: ela usa a mesma `chave_de_agrupamento` do
service, mas quem decide é o service — se as duas divergirem um dia, o cadastro
é recusado com mensagem, não gravado errado.

## Ciclo de vida (o RNF do Celeron, §3.2/§3.9/§3.14)

* **destroy** — `executar_modal()` faz o `deleteLater()` do diálogo depois de
  ler o resultado. O que `done()` acrescenta é soltar o **escurecedor**, que é
  filho da janela principal e não do diálogo;
* **unbind** — sinal nenhum sai do diálogo, e nenhum `connect` usa `lambda`
  (§3.14): tudo liga um filho a um método do próprio diálogo, a conexão vive no
  filho e o filho morre com o pai;
* **timers** — não existe nenhum. A conferência do nome roda na tecla e é uma
  comparação de strings curtas contra uma lista de, no pior caso do cardápio
  real, três nomes. Não há `after` a cancelar porque não há `after`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.services.texto import chave_de_agrupamento
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.flow_layout import FlowLayout

# O mesmo teto de `Subcategoria.nome` no banco (`String(80)`).
LIMITE_NOME = 80
_SEM_IMPRESSORA = "SEM IMPRESSORA"


@dataclass(frozen=True, slots=True)
class DadosSubcategoria:
    """O que o modal devolve — hoje um campo só, e ainda assim um tipo.

    Mesmo formato de `DadosProduto`, `DadosFuncionario` e `DadosMovimento`: o
    diálogo devolve dados, a view chama o service. Um `str` cru economizaria
    uma classe e custaria a próxima vez — foi exatamente assim que o modal de
    produto chegou a uma tupla de sete posições desempacotada por ordem.
    """

    nome: str


class _IconeDeRamo(QWidget):
    """O glifo do cabeçalho: um tronco com dois ramos saindo dele.

    Desenhado à mão pelo mesmo motivo do cadeado do PIN e da lupa do modal de
    lançamento (§9.4): o símbolo mais próximo disto no Unicode mora no bloco de
    emoji, cairia no Segoe UI Emoji, sairia colorido e chapado, ignoraria o tema
    — e a máquina limpa do food truck pode nem ter a fonte. Doze linhas de
    `QPainter` custam menos, e a cor daqui é relida a cada repintura, então o
    ícone acompanha o alternador Claro/Escuro de graça (§3.15).

    A figura é a própria ideia da tela: um nó que se abre em dois.
    """

    LADO_PX = 18

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("subDialogGlifo")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        cor = QColor(ThemeController.instancia().tokens_atuais["subcategoria_glifo"])
        caneta = QPen(cor, 1.5)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        # O tronco desce pela esquerda e abre em dois ramos à direita.
        pintor.drawLine(QPointF(4.0, 2.5), QPointF(4.0, 14.0))
        pintor.drawLine(QPointF(4.0, 6.5), QPointF(9.5, 6.5))
        pintor.drawLine(QPointF(4.0, 14.0), QPointF(9.5, 14.0))
        pintor.setBrush(cor)
        pintor.drawEllipse(QRectF(2.6, 1.2, 2.8, 2.8))
        pintor.drawRoundedRect(QRectF(10.0, 4.6, 5.4, 3.8), 1.2, 1.2)
        pintor.drawRoundedRect(QRectF(10.0, 12.1, 5.4, 3.8), 1.2, 1.2)
        pintor.end()


class SubcategoriaDialog(QDialog):
    """Cartão de cadastro/edição de uma subdivisão da categoria."""

    LARGURA_CARTAO_PX = 460
    LADO_BOTAO_FECHAR_PX = 32
    ALTURA_CAMPO_PX = 46
    # Teto da faixa de sugestões, em fileiras. Mesmo critério (e mesmo motivo)
    # do modal "Adicionar item": sem teto, uma categoria com muitas subdivisões
    # empurraria o rodapé do cartão para fora de um monitor de 768px.
    FILEIRAS_DE_SUGESTAO = 2

    def __init__(
        self,
        categoria_nome: str,
        impressora_nome: str | None,
        existentes: list[str],
        parent: QWidget | None = None,
        *,
        nome_inicial: str = "",
    ) -> None:
        super().__init__(parent)
        self._edicao = bool(nome_inicial)
        self._nome_original = nome_inicial
        self._backdrop: Backdrop | None = None
        self._pills: list[QPushButton] = []
        # As chaves das que já existem, menos a própria (na edição): é contra
        # elas que a linha de aviso confere o que está sendo digitado.
        self._chaves_ocupadas = {
            chave_de_agrupamento(nome)
            for nome in existentes
            if chave_de_agrupamento(nome) != chave_de_agrupamento(nome_inicial)
        }

        self.setObjectName("subDialog")
        self.setWindowTitle("Editar subcategoria" if self._edicao else "Nova subcategoria")
        # Sem moldura do sistema: o cabeçalho é do cartão, e o fundo translúcido
        # é o que faz os cantos de 16px saírem redondos de verdade.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("subDialogCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(22, 18, 22, 18)
        corpo.setSpacing(14)
        corpo.addLayout(self._montar_cabecalho())
        corpo.addWidget(self._montar_contexto(categoria_nome, impressora_nome))
        corpo.addWidget(self._montar_campo(nome_inicial))
        corpo.addWidget(self._montar_sugestoes(existentes))
        corpo.addLayout(self._montar_acoes())

        # Depois do `addWidget`, e não dentro de `_montar_sugestoes`: pôr um
        # widget escondido num layout desfaz o `setVisible(False)` — o Qt
        # reexibe o filho ao reparentá-lo. Escondendo aqui, a faixa nasce
        # invisível de verdade numa categoria sem subdivisão.
        self._faixa.setVisible(bool(existentes))

        self._ao_digitar(nome_inicial)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(12)

        selo = QFrame()
        selo.setObjectName("subDialogIcone")
        selo.setFixedSize(42, 42)
        dentro = QHBoxLayout(selo)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(_IconeDeRamo(), 0, Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(selo, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        titulo = QLabel("Editar subcategoria" if self._edicao else "Nova subcategoria")
        titulo.setObjectName("subDialogTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel("Uma subdivisão dentro da categoria, para organizar o cardápio")
        subtitulo.setObjectName("subDialogSubtitulo")
        subtitulo.setWordWrap(True)
        textos.addWidget(subtitulo)
        linha.addLayout(textos, 1)

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("subDialogFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return linha

    def _montar_contexto(self, categoria_nome: str, impressora_nome: str | None) -> QFrame:
        """Onde a subdivisão vai morar — e para onde os itens dela vão imprimir.

        A impressora aparece porque é a pergunta que uma tela de subdivisão
        naturalmente levanta ("isso muda onde meu pedido sai?"), e a resposta é
        não: a bobina é da CATEGORIA (§9.8), e continua sendo depois disto.
        """
        painel = QFrame()
        painel.setObjectName("subDialogContexto")
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(14, 11, 14, 11)
        linha.setSpacing(10)

        rotulo = QLabel("DENTRO DE")
        rotulo.setObjectName("subDialogRotulo")
        linha.addWidget(rotulo)

        destino = QLabel(
            f"{categoria_nome.upper()} · {(impressora_nome or _SEM_IMPRESSORA).upper()}"
        )
        destino.setObjectName("subDialogDestino")
        linha.addWidget(destino, 1)
        return painel

    def _montar_campo(self, nome_inicial: str) -> QWidget:
        bloco = QWidget()
        coluna = QVBoxLayout(bloco)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(7)

        rotulo = QLabel("NOME DA SUBCATEGORIA")
        rotulo.setObjectName("subDialogRotulo")
        coluna.addWidget(rotulo)

        self._caixa_campo = QFrame()
        self._caixa_campo.setObjectName("subDialogCaixa")
        self._caixa_campo.setFixedHeight(self.ALTURA_CAMPO_PX)
        self._caixa_campo.setProperty("foco", False)
        dentro = QHBoxLayout(self._caixa_campo)
        dentro.setContentsMargins(14, 0, 14, 0)
        dentro.setSpacing(10)

        self._campo_nome = QLineEdit(nome_inicial)
        self._campo_nome.setObjectName("subDialogCampo")
        self._campo_nome.setPlaceholderText("Ex.: Podrão, Artesanal, Guarnições")
        self._campo_nome.setMaxLength(LIMITE_NOME)
        self._campo_nome.textChanged.connect(self._ao_digitar)
        # O anel é do QUADRO e o foco é do campo lá dentro: sem este filtro o
        # `[foco="true"]` nunca acenderia. Mesmo arranjo do §9.4, e `done()`
        # remove o filtro.
        self._campo_nome.installEventFilter(self)
        dentro.addWidget(self._campo_nome, 1)

        self._contador = QLabel()
        self._contador.setObjectName("subDialogContador")
        dentro.addWidget(self._contador, 0, Qt.AlignmentFlag.AlignVCenter)
        coluna.addWidget(self._caixa_campo)

        self._aviso = QLabel()
        self._aviso.setObjectName("subDialogAviso")
        self._aviso.setWordWrap(True)
        self._aviso.setProperty("estado", "dica")
        coluna.addWidget(self._aviso)
        return bloco

    def _montar_sugestoes(self, existentes: list[str]) -> QWidget:
        """As subdivisões que a categoria já tem, apagadas e NÃO clicáveis.

        Existem para o gerente ver o que já há antes de criar uma quase-igual —
        é o mesmo problema que a checagem de duplicidade resolve no service, um
        passo antes. Não preenchem o campo de propósito: clicar numa delas só
        poderia levar a "já existe", e um controle cuja única resposta é um erro
        é pior que controle nenhum.
        """
        self._faixa = QWidget()
        self._faixa.setObjectName("subDialogFaixa")
        coluna = QVBoxLayout(self._faixa)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(7)

        rotulo = QLabel("JÁ EXISTEM NESTA CATEGORIA")
        rotulo.setObjectName("subDialogRotulo")
        coluna.addWidget(rotulo)

        recipiente = QWidget()
        fluxo = FlowLayout(recipiente, spacing=6)
        for nome in existentes:
            pill = QLabel(nome.upper())
            pill.setObjectName("subDialogPill")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fluxo.addWidget(pill)
            self._pills.append(pill)
        coluna.addWidget(recipiente)
        return self._faixa

    def _montar_acoes(self) -> QVBoxLayout:
        """A nota em cima, os botões embaixo — e não os três na mesma linha.

        Lado a lado, a nota quebrava em quatro linhas para caber nos ~180px que
        sobravam dos botões, e o rodapé ficava mais alto que o campo do nome.
        """
        coluna = QVBoxLayout()
        coluna.setSpacing(10)

        nota = QLabel("OS ITENS ENTRAM DEPOIS, PELO CADASTRO DO PRODUTO")
        nota.setObjectName("subDialogNota")
        nota.setWordWrap(True)
        coluna.addWidget(nota)

        linha = QHBoxLayout()
        linha.setSpacing(10)
        linha.addStretch()

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("subDialogCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = QPushButton("Salvar" if self._edicao else "Criar subcategoria")
        self._botao_confirmar.setObjectName("subDialogConfirmar")
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self._confirmar)
        linha.addWidget(self._botao_confirmar)
        coluna.addLayout(linha)
        return coluna

    # ------------------------------------------------------------------
    # Digitação
    # ------------------------------------------------------------------

    def _ao_digitar(self, texto: str) -> None:
        nome = " ".join(texto.split())
        self._contador.setText(f"{len(texto)}/{LIMITE_NOME}")

        if not nome:
            self._avisar("DÊ UM NOME CURTO — ELE VIRA UM GRUPO NA LISTA", "dica")
            self._botao_confirmar.setEnabled(False)
            return
        if chave_de_agrupamento(nome) in self._chaves_ocupadas:
            # A mesma comparação do service (acento e caixa ignorados): avisar
            # aqui evita a ida e volta de digitar, salvar e receber o erro.
            self._avisar("JÁ EXISTE UMA SUBCATEGORIA COM ESSE NOME AQUI", "erro")
            self._botao_confirmar.setEnabled(False)
            return
        self._avisar("PRONTO PARA CRIAR", "ok")
        self._botao_confirmar.setEnabled(True)

    def _avisar(self, mensagem: str, estado: str) -> None:
        self._aviso.setText(mensagem)
        aplicar_propriedade(self._aviso, "estado", estado)

    def mostrar_erro_servico(self, mensagem: str) -> None:
        """Erro vindo do service, sem fechar o modal nem perder o que foi digitado."""
        self._avisar(mensagem.upper(), "erro")
        self._campo_nome.setFocus(Qt.FocusReason.OtherFocusReason)

    def _confirmar(self) -> None:
        if self._botao_confirmar.isEnabled():
            self.accept()

    def resultado(self) -> DadosSubcategoria:
        """O nome já aparado. Quem valida de verdade é o service."""
        return DadosSubcategoria(nome=" ".join(self._campo_nome.text().split()))

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar(retorno=False)
    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:  # noqa: N802 (override Qt)
        if watched is self._campo_nome and event.type() in (
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        ):
            aplicar_propriedade(
                self._caixa_campo, "foco", event.type() == QEvent.Type.FocusIn
            )
        return super().eventFilter(watched, event)

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """O `Enter` cria, e só quando há o que criar.

        O `QLineEdit` ignora o Return e ele sobe até aqui — ligar
        `returnPressed` do campo ALÉM disto seria o caminho para o cadastro ser
        enviado duas vezes com um Enter só (§9.4). O Esc cai no `super()` de
        propósito: lá o `QDialog` o traduz em `reject()`, que passa por `done()`
        e portanto pela mesma limpeza dos outros caminhos de saída.
        """
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirmar()
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        if self._backdrop is None:
            self._backdrop = cartao_modal.montar(self)
        self._ajustar_altura_da_faixa()
        self.adjustSize()
        cartao_modal.centralizar_no_pai(self)
        self._campo_nome.setFocus(Qt.FocusReason.OtherFocusReason)
        self._campo_nome.selectAll()

    def _ajustar_altura_da_faixa(self) -> None:
        """Fecha a faixa de sugestões no teto de fileiras.

        Roda no `showEvent`, e não na construção, pelo mesmo motivo do §9.4: a
        altura de uma pílula só é verdade **depois** do primeiro `polish`, e
        antes disso o `sizeHint` não conhece o `padding` que o QSS aplica.
        """
        if not self._pills:
            return
        altura_pill = max(pill.sizeHint().height() for pill in self._pills)
        teto = self.FILEIRAS_DE_SUGESTAO * altura_pill + (self.FILEIRAS_DE_SUGESTAO - 1) * 6
        recipiente = self._pills[0].parentWidget()
        if recipiente is None:
            return
        fluxo = recipiente.layout()
        largura = max(recipiente.width(), self.LARGURA_CARTAO_PX - 44)
        altura = fluxo.heightForWidth(largura) if fluxo is not None else altura_pill
        recipiente.setFixedHeight(min(altura, teto))

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — e por isso o lugar certo da limpeza.

        Criar, Cancelar, o ✕ e o Esc passam todos por aqui; `closeEvent`
        sozinho não serviria, porque `done()` faz `hide()`, não `close()`
        (§3.9). Saem o filtro de eventos do campo, a lista de pílulas e o
        escurecedor, que é filho da JANELA e não do diálogo.
        """
        self._campo_nome.removeEventFilter(self)
        self._pills.clear()
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
        super().done(resultado)
