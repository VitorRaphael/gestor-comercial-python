"""O cartão "Composição do combo": os componentes em linhas com stepper (§9.15).

Substitui o `_ComboComponentesDialog` que morava dentro de `cardapio_view.py`: a
moldura do sistema, uma `QTableWidget` genérica de duas colunas ("Produto",
"Quantidade") e dois botões chapados. Mudar a quantidade de um componente ali
era **remover e associar de novo** — dois commits, e entre eles um combo com um
item a menos (ou, se era o único, um combo que tinha deixado de ser combo).

## O que a tela mostra, e de onde vem cada coisa

* **o subtítulo de cada linha é a CATEGORIA do componente** ("Bebidas",
  "Porções"). O mockup desenhava "Produto principal" / "Adicional", mas
  `combo_itens` não tem esse conceito — é combo + produto + quantidade — e o
  Vitor escolheu não inventá-lo: nem heurística ("o primeiro é o principal"),
  nem coluna nova que nenhuma outra tela leria. A categoria é dado real;
* **o selo âmbar com o visto marca a linha SELECIONADA**, a que o "Remover" e o
  `Delete` vão tirar. As outras ficam com o selo neutro de camadas. É o mesmo
  sinal da borda âmbar, dito duas vezes de propósito: a borda some fácil no
  tema claro, o selo não;
* o stepper grava **na hora**, um `UPDATE` por clique
  (`alterar_quantidade_componente`), e é por isso que o rodapé diz "ALTERAÇÕES
  APLICADAS NESTE COMBO": não há "Salvar" nem "Cancelar" para esquecer de
  apertar. O `synchronous=FULL` do banco (§8) fica como está — é um commit por
  clique de gerente, não por tecla de digitação.

## O que NÃO mudou

Regra de negócio nenhuma. Quem exige gerente, quem recusa quantidade zero, quem
recusa combo dentro de combo e o mesmo componente duas vezes, e quem desfaz o
combo quando o último componente sai continua sendo o `CardapioService` — o
diálogo só chama. O único método novo do service é o do stepper, e ele tem as
mesmas travas de `associar_componente`.

Impressão e estoque não leem `combo_itens` na V1: o combo sai no cupom como um
produto só, pela impressora da categoria DELE (§9.8), e a baixa de estoque dos
componentes que o Java fazia é backlog da V2 (`comanda_service`). Não havia o
que preservar ali além de não tocar — e nada lá foi tocado.

## Por que um widget por linha aqui, e não um delegado

A regra do §9.4 e do §9.11 é "widget por linha só quando a linha tem um controle
de verdade dentro dela", e esta tem: dois botões que gravam. Um delegado teria
de reimplementar clique, hover, estado desligado e acessibilidade de botão à
mão, para uma lista que no cardápio real tem **dois** itens por combo. O custo
que o §9.11 mediu (58 widgets repolidos a cada troca de categoria) não existe
aqui: as linhas são montadas uma vez, e o stepper só troca o texto de um rótulo.

## Ciclo de vida (o RNF do Celeron, §3.2/§3.9/§3.14)

O pedido falava em `destroy()`/`unbind` do Tkinter. Os equivalentes em PySide6:

* **destroy** — o diálogo é destruído por `executar_modal()` (§3.2). Uma linha
  REMOVIDA com o modal aberto é destruída na hora, em `_descartar_linha`: sai do
  layout, é desligada, perde o parent e recebe `deleteLater()` — o mesmo
  arranjo de `cartao_modal.descartar`. O `deleteLater()` sozinho só age quando o
  laço de eventos gira; o `setParent(None)` é o que a tira do diálogo NA HORA,
  e é o que faz a contagem de linhas vivas bater com a tela em qualquer instante;
* **unbind** — não há atalho global: o teclado é lido no `keyPressEvent` do
  próprio diálogo. As ligações de sinal são desconectadas nominalmente em
  `_soltar_recursos()`, inclusive as de cada linha, e nenhuma usa `lambda`: o
  botão do stepper carrega o próprio delta numa propriedade, e a linha avisa o
  diálogo por um sinal com o id do componente;
* **referências** — a linha guarda um instantâneo imutável
  (`LinhaDeComponente`), nunca o `ComboItem`: o commit do stepper expira as
  instâncias do SQLAlchemy, e ler `item.produto.nome` depois dele seria consulta
  a cada repintura (a lição do §9.4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.combo_item import ComboItem
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.adicionar_item_dialog import (
    MODOS,
    AdicionarItemDialog,
    ModoDeLancamento,
)
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_CAMADAS,
    GLIFO_LIXEIRA,
    GLIFO_MAIS,
    GLIFO_VISTO,
    BotaoComGlifo,
    GlifoSolto,
    RotuloComReticencias,
    desenhar_glifo,
)
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.modais import executar_modal
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

_ERROS_SERVICE = (
    RegraDeNegocioError,
    RecursoNaoEncontradoError,
    NaoAutorizadoError,
    AcessoNegadoError,
)

# O teto do stepper é o mesmo do cartão "Adicionar componente": as duas portas
# de entrada da quantidade de um componente não podem aceitar tetos diferentes.
QUANTIDADE_MAXIMA = MODOS[ModoDeLancamento.COMPONENTE].quantidade_maxima

_SECAO = "COMPOSIÇÃO DO COMBO"
_SUBTITULO = "Defina os itens e as quantidades entregues neste combo."
_RODAPE = "ALTERAÇÕES APLICADAS NESTE COMBO"
_INSTRUCAO = "SELECIONE UMA LINHA PARA REMOVER"
_VAZIO_STATUS = "NENHUM COMPONENTE · ADICIONE O PRIMEIRO"
_VAZIO_LISTA = (
    "Nenhum componente ainda.\nSem componentes, este produto é vendido como um item comum."
)
_SEM_CANDIDATOS = "Não há outro produto disponível para virar componente."


class ServicoDeComposicao(Protocol):
    """O que este diálogo usa do `CardapioService` — e nada além disso.

    Um `Protocol` e não o `CardapioService` como tipo: fica escrito num lugar só
    de quais cinco métodos a tela depende, e crescer essa lista passa a ser uma
    decisão visível em vez de um `self._servico.qualquer_coisa` a mais no meio
    do arquivo.
    """

    def listar_componentes(self, combo_id: int) -> list[ComboItem]: ...

    def alterar_quantidade_componente(self, combo_item_id: int, quantidade: int) -> object: ...

    def remover_componente(self, combo_item_id: int) -> None: ...

    def associar_componente(self, combo_id: int, produto_id: int, quantidade: int) -> object: ...

    def listar_produtos_para_lancamento(self) -> list[Produto]: ...


@dataclass(frozen=True, slots=True)
class LinhaDeComponente:
    """Instantâneo de um componente — sem ORM atrás (ver o cabeçalho)."""

    combo_item_id: int
    produto_id: int
    nome: str
    categoria: str
    quantidade: int


def instantaneo_dos_componentes(itens: Sequence[ComboItem]) -> list[LinhaDeComponente]:
    """Lê produto e categoria UMA vez, na abertura.

    `listar_componentes` já traz as duas relações carregadas
    (`ComboItemRepository.listar_por_combo`), então isto não vai ao banco.
    """
    return [
        LinhaDeComponente(
            combo_item_id=item.id,
            produto_id=item.produto_id,
            nome=item.produto.nome,
            categoria=item.produto.categoria.nome,
            quantidade=item.quantidade,
        )
        for item in itens
    ]


def texto_do_status(total: int) -> str:
    """A linha de baixo da lista: quantos componentes, e o que fazer com eles."""
    if total == 0:
        return _VAZIO_STATUS
    rotulo = "COMPONENTE" if total == 1 else "COMPONENTES"
    return f"{total} {rotulo} · {_INSTRUCAO}"


# ---------------------------------------------------------------------------
# Peças de uma linha
# ---------------------------------------------------------------------------


class SeloDoComponente(QWidget):
    """O quadrado à esquerda da linha: visto âmbar na selecionada, camadas nas outras.

    Pintado, e não um `QLabel` com `✓`: o visto e as camadas têm de sair da
    mesma grade de glifos (espessura e altura iguais), e a cor é relida do tema a
    cada pintura, então o alternador Claro/Escuro repinta de graça (§3.15).
    """

    LADO_PX = 36
    RAIO_PX = 10.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("comboSelo")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)
        # O clique no selo tem que chegar à linha, que é quem seleciona.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._selecionado = False

    def selecionado(self) -> bool:
        return self._selecionado

    def definir_selecionado(self, selecionado: bool) -> None:
        if selecionado == self._selecionado:
            return
        self._selecionado = selecionado
        self.update()

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        tokens = ThemeController.instancia().tokens_atuais
        area = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._selecionado:
            fundo = cor_do_token(tokens["acento"])
            pintor.setPen(QPen(fundo, 1.0))
            glifo, cor_glifo, espessura = GLIFO_VISTO, tokens["acento_texto"], 2.4
        else:
            fundo = cor_do_token(tokens["composicao_selo_bg"])
            pintor.setPen(QPen(cor_do_token(tokens["composicao_selo_borda"]), 1.0))
            glifo, cor_glifo, espessura = GLIFO_CAMADAS, tokens["composicao_selo_glifo"], 1.8
        pintor.setBrush(fundo)
        pintor.drawRoundedRect(area, self.RAIO_PX, self.RAIO_PX)
        lado = self.LADO_PX * 0.46
        alvo = QRectF(
            area.center().x() - lado / 2.0, area.center().y() - lado / 2.0, lado, lado
        )
        desenhar_glifo(pintor, glifo, alvo, cor_do_token(cor_glifo), espessura)
        pintor.end()


class LinhaDoCombo(QFrame):
    """Um componente: selo, nome, categoria e o stepper de quantidade.

    Não fala com o service. Avisa o diálogo por dois sinais — `clicada` e
    `passo_pedido` — com o id do componente, e o diálogo decide. É o que mantém
    a gravação num lugar só, e a linha sem referência nenhuma ao diálogo.
    """

    clicada = Signal(int)
    passo_pedido = Signal(int, int)

    LADO_PASSO_PX = 36
    LARGURA_VALOR_PX = 44
    ALTURA_PX = 64

    def __init__(self, linha: LinhaDeComponente, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._linha = linha
        self._limpo = False
        self.setObjectName("comboLinha")
        self.setProperty("selecionada", False)
        self.setFixedHeight(self.ALTURA_PX)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        corpo = QHBoxLayout(self)
        corpo.setContentsMargins(12, 0, 12, 0)
        corpo.setSpacing(12)

        self._selo = SeloDoComponente()
        corpo.addWidget(self._selo, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(2)
        textos.addStretch()
        # Com reticências: nome de produto vai até 120 letras, e um `QLabel`
        # comum empurraria o stepper para fora da linha.
        self._nome = RotuloComReticencias(linha.nome)
        self._nome.setObjectName("comboLinhaNome")
        textos.addWidget(self._nome)
        self._categoria = RotuloComReticencias(linha.categoria)
        self._categoria.setObjectName("comboLinhaCategoria")
        textos.addWidget(self._categoria)
        textos.addStretch()
        corpo.addLayout(textos, 1)

        corpo.addWidget(self._montar_stepper(), 0, Qt.AlignmentFlag.AlignVCenter)
        self._mostrar_quantidade()

    def _montar_stepper(self) -> QFrame:
        pilula = QFrame()
        pilula.setObjectName("comboPasso")
        dentro = QHBoxLayout(pilula)
        dentro.setContentsMargins(1, 1, 1, 1)
        dentro.setSpacing(0)

        self._botao_menos = self._criar_passo("−", -1, "Uma unidade a menos")
        dentro.addWidget(self._botao_menos)
        self._valor = QLabel()
        self._valor.setObjectName("comboPassoValor")
        self._valor.setFixedWidth(self.LARGURA_VALOR_PX)
        self._valor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dentro.addWidget(self._valor)
        self._botao_mais = self._criar_passo("+", 1, "Uma unidade a mais")
        dentro.addWidget(self._botao_mais)
        return pilula

    def _criar_passo(self, rotulo: str, delta: int, dica: str) -> QPushButton:
        botao = QPushButton(rotulo)
        botao.setObjectName("comboPassoBotao")
        botao.setFixedSize(self.LADO_PASSO_PX, self.LADO_PASSO_PX)
        botao.setToolTip(dica)
        # O delta vive na propriedade, e não numa `lambda` no clique (§3.14).
        botao.setProperty("delta", delta)
        cartao_modal.preparar_botao(botao)
        botao.clicked.connect(self._passo_clicado)
        return botao

    # -- leitura ---------------------------------------------------------

    @property
    def linha(self) -> LinhaDeComponente:
        return self._linha

    def selecionada(self) -> bool:
        return self._selo.selecionado()

    # -- escrita (quem chama é o diálogo, depois de o service aceitar) ------

    def definir_linha(self, linha: LinhaDeComponente) -> None:
        """Troca o instantâneo — numa recarga, o mesmo componente pode vir diferente."""
        if linha == self._linha:
            return
        self._linha = linha
        self._nome.setText(linha.nome)
        self._categoria.setText(linha.categoria)
        self._mostrar_quantidade()

    def definir_quantidade(self, quantidade: int) -> None:
        self.definir_linha(replace(self._linha, quantidade=quantidade))

    def definir_selecionada(self, selecionada: bool) -> None:
        if selecionada == self._selo.selecionado():
            return
        self._selo.definir_selecionado(selecionada)
        # Repolir custa um recálculo de estilo: só a linha que mudou paga.
        aplicar_propriedade(self, "selecionada", selecionada)

    def _mostrar_quantidade(self) -> None:
        quantidade = self._linha.quantidade
        self._valor.setText(str(quantidade))
        self._botao_menos.setEnabled(quantidade > 1)
        self._botao_mais.setEnabled(quantidade < QUANTIDADE_MAXIMA)

    # -- eventos ---------------------------------------------------------

    def _passo_clicado(self) -> None:
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        self.passo_pedido.emit(self._linha.combo_item_id, int(botao.property("delta") or 0))

    @nao_deixa_escapar()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicada.emit(self._linha.combo_item_id)
            event.accept()
            return
        super().mousePressEvent(event)

    def soltar(self) -> None:
        """Desliga os dois botões do stepper — e só uma vez (ver `_limpo` no diálogo)."""
        if self._limpo:
            return
        self._limpo = True
        self._botao_menos.clicked.disconnect(self._passo_clicado)
        self._botao_mais.clicked.disconnect(self._passo_clicado)


# ---------------------------------------------------------------------------
# O diálogo
# ---------------------------------------------------------------------------


class ComposicaoComboDialog(QDialog):
    """Cartão de composição do combo: listar, ajustar, remover e adicionar."""

    # O pedido escrito dizia "entre 560 e 600px", e medido não fecha — é o mesmo
    # achado do §9.12. O rodapé de UMA linha do mockup (o contexto à esquerda,
    # Remover e "+ Adicionar componente" à direita) pede 635px com a fonte da
    # marca, que é ~20% mais larga que a do desenho: a 600px o botão primário
    # saía como "olonar compone" e o contexto perdia o "COMBO". 640 fica entre o
    # teto do pedido e os 672px da própria imagem do mockup, e a folga do pior
    # caso está trancada em `test_o_rodape_cabe_no_cartao`.
    LARGURA_CARTAO_PX = 640
    ALTURA_LISTA_PX = 254
    ALTURA_STATUS_PX = 30
    MARGEM_LISTA_PX = 8
    LADO_BOTAO_FECHAR_PX = 32
    LADO_BADGE_PX = 48

    def __init__(
        self,
        servico: ServicoDeComposicao,
        combo_id: int,
        combo_nome: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._servico = servico
        self._combo_id = combo_id
        self._combo_nome = combo_nome
        self._linhas: list[LinhaDoCombo] = []
        self._backdrop: Backdrop | None = None
        self._limpo = False
        # Se algo foi gravado enquanto o cartão esteve aberto. A view só recarrega
        # o Cardápio quando isto é verdade: abrir, olhar e fechar não custa a
        # recarga da tela inteira.
        self.alterou = False

        self.setObjectName("comboDialog")
        self.setWindowTitle(f"Composição do combo: {combo_nome}")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        # Quem lê o teclado é o diálogo (setas, Delete, Esc): nenhum botão aceita
        # foco (`preparar_botao`), então ele tem que aceitar.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("comboDialogCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addWidget(self._montar_cabecalho())
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_corpo())
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_rodape())

        self._recarregar()
        if self._linhas:
            self._selecionar(self._linhas[0].linha.combo_item_id)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _divisor(self) -> QFrame:
        linha = QFrame()
        linha.setObjectName("comboDialogDivisor")
        linha.setFixedHeight(1)
        return linha

    def _montar_cabecalho(self) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("comboDialogCabecalho")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(24, 20, 20, 20)
        linha.setSpacing(16)

        badge = QFrame()
        badge.setObjectName("comboDialogBadge")
        badge.setFixedSize(self.LADO_BADGE_PX, self.LADO_BADGE_PX)
        dentro = QHBoxLayout(badge)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(
            GlifoSolto(GLIFO_CAMADAS, 22, "cardapio_icone_glifo"),
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        linha.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(4)
        secao = QLabel(_SECAO)
        secao.setObjectName("comboDialogSecao")
        textos.addWidget(secao)
        # O nome do combo vai até 120 letras: sem reticências ele pediria a
        # largura inteira e empurraria o ✕ para fora do cartão.
        self._titulo = RotuloComReticencias(self._combo_nome)
        self._titulo.setObjectName("comboDialogTitulo")
        textos.addWidget(self._titulo)
        subtitulo = QLabel(_SUBTITULO)
        subtitulo.setObjectName("comboDialogSubtitulo")
        subtitulo.setWordWrap(True)
        textos.addWidget(subtitulo)
        linha.addLayout(textos, 1)

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("comboDialogFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return faixa

    def _montar_corpo(self) -> QWidget:
        faixa = PainelPontilhado()
        faixa.setObjectName("comboDialogCorpo")
        coluna = QVBoxLayout(faixa)
        coluna.setContentsMargins(24, 18, 24, 16)
        coluna.setSpacing(10)

        # Os dois rótulos de coluna: "QUANTIDADE" centrado sobre o stepper, que
        # tem largura fixa — por isso um rótulo de largura fixa à direita, e não
        # um alinhamento à direita que o poria encostado na borda. A margem
        # direita é a soma do que separa o stepper da borda da lista (1px de
        # borda + 8 de margem interna + 12 da linha), para os dois centros
        # coincidirem.
        cabecalho = QHBoxLayout()
        cabecalho.setContentsMargins(13, 0, 21, 0)
        cabecalho.setSpacing(0)
        componente = QLabel("COMPONENTE")
        componente.setObjectName("comboDialogColuna")
        cabecalho.addWidget(componente)
        cabecalho.addStretch()
        quantidade = QLabel("QUANTIDADE")
        quantidade.setObjectName("comboDialogColuna")
        quantidade.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quantidade.setFixedWidth(2 * LinhaDoCombo.LADO_PASSO_PX + LinhaDoCombo.LARGURA_VALOR_PX + 2)
        cabecalho.addWidget(quantidade)
        coluna.addLayout(cabecalho)

        coluna.addWidget(self._montar_lista())

        self._status = QLabel()
        self._status.setObjectName("comboDialogStatus")
        self._status.setProperty("estado", "dica")
        self._status.setWordWrap(True)
        # Altura fixa de duas linhas do erro: o status troca de tamanho de letra
        # entre dica e erro, e sem isto o cartão cresceria no meio do uso.
        self._status.setFixedHeight(self.ALTURA_STATUS_PX)
        self._status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        coluna.addWidget(self._status)
        return faixa

    def _montar_lista(self) -> QFrame:
        """A lista em altura FIXA, com rolagem além de três linhas e meia.

        Fixa porque o cartão não pode pular de tamanho ao adicionar ou remover um
        componente: o botão que o dedo ia apertar sairia de baixo dele. A meia
        linha visível no fim é o que diz que há mais para rolar.
        """
        painel = QFrame()
        painel.setObjectName("comboDialogLista")
        painel.setFixedHeight(self.ALTURA_LISTA_PX)
        dentro = QVBoxLayout(painel)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.setSpacing(0)

        self._rolagem = QScrollArea()
        self._rolagem.setObjectName("comboDialogRolagem")
        self._rolagem.setWidgetResizable(True)
        self._rolagem.setFrameShape(QFrame.Shape.NoFrame)
        # Sem foco: as setas são do diálogo (trocam a linha selecionada), e não
        # da área de rolagem, que as usaria para rolar.
        self._rolagem.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # A barra só aparece a partir da quarta linha, e quando aparece ela come
        # a largura do viewport: as linhas encolheriam e os steppers sairiam de
        # baixo do rótulo "QUANTIDADE". `_acomodar_barra` devolve essa largura
        # tirando-a da margem direita.
        self._rolagem.verticalScrollBar().rangeChanged.connect(self._acomodar_barra)

        conteudo = QWidget()
        conteudo.setObjectName("comboDialogLinhas")
        self._layout_linhas = QVBoxLayout(conteudo)
        self._layout_linhas.setContentsMargins(
            self.MARGEM_LISTA_PX, self.MARGEM_LISTA_PX, self.MARGEM_LISTA_PX, self.MARGEM_LISTA_PX
        )
        self._layout_linhas.setSpacing(8)
        self._vazio = QLabel(_VAZIO_LISTA)
        self._vazio.setObjectName("comboDialogVazio")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vazio.setWordWrap(True)
        self._layout_linhas.addWidget(self._vazio, 1)
        self._layout_linhas.addStretch()
        self._rolagem.setWidget(conteudo)
        dentro.addWidget(self._rolagem)
        return painel

    def _montar_rodape(self) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("comboDialogRodape")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(24, 16, 24, 18)
        linha.setSpacing(10)

        contexto = QLabel(_RODAPE)
        contexto.setObjectName("comboDialogContexto")
        linha.addWidget(contexto)
        linha.addStretch()

        self._botao_remover = BotaoComGlifo(
            "Remover", GLIFO_LIXEIRA, "composicao_remover_texto", "texto_fraquissimo"
        )
        self._botao_remover.setObjectName("comboDialogRemover")
        self._botao_remover.setToolTip("Remover a linha selecionada (Delete)")
        cartao_modal.preparar_botao(self._botao_remover)
        self._botao_remover.clicked.connect(self._remover_selecionada)
        linha.addWidget(self._botao_remover)

        self._botao_adicionar = BotaoComGlifo(
            "Adicionar componente", GLIFO_MAIS, "acento_texto", "pilula_disabled_texto"
        )
        self._botao_adicionar.setObjectName("comboDialogAdicionar")
        cartao_modal.preparar_botao(self._botao_adicionar)
        self._botao_adicionar.clicked.connect(self._abrir_adicao)
        linha.addWidget(self._botao_adicionar)
        return faixa

    # ------------------------------------------------------------------
    # Linhas: montar, sincronizar, descartar
    # ------------------------------------------------------------------

    def _recarregar(self) -> None:
        """Lê os componentes do banco e acerta as linhas — sem refazer as que ficaram.

        Só é chamado na abertura e depois do cartão "Adicionar componente":
        stepper e remoção acertam a própria linha sem voltar ao banco, e é isso
        que mantém a tela sem piscar.
        """
        try:
            linhas = instantaneo_dos_componentes(
                self._servico.listar_componentes(self._combo_id)
            )
        except _ERROS_SERVICE as erro:
            self._atualizar_estado()
            self._dizer_erro(str(erro))
            return
        self._sincronizar(linhas)
        self._atualizar_estado()

    def _sincronizar(self, novas: list[LinhaDeComponente]) -> None:
        """Deixa as linhas da tela iguais a `novas`, na mesma ordem.

        A chave é o PAR (componente, produto), e não só o id do componente: o
        SQLite reaproveita o maior id quando a última linha é apagada, e um
        componente removido e outro adicionado em seguida podem sair com o mesmo
        número. Casar só pelo id trocaria o nome da linha antiga em vez de
        destruí-la e montar a nova.
        """
        chave = {(n.combo_item_id, n.produto_id): n for n in novas}
        for linha in list(self._linhas):
            if (linha.linha.combo_item_id, linha.linha.produto_id) not in chave:
                self._descartar_linha(linha)

        existentes = {(w.linha.combo_item_id, w.linha.produto_id): w for w in self._linhas}
        ordem: list[LinhaDoCombo] = []
        for posicao, nova in enumerate(novas):
            widget = existentes.get((nova.combo_item_id, nova.produto_id))
            if widget is None:
                widget = LinhaDoCombo(nova)
                widget.clicada.connect(self._ao_clicar_linha)
                widget.passo_pedido.connect(self._ao_pedir_passo)
                self._layout_linhas.insertWidget(posicao, widget)
            else:
                widget.definir_linha(nova)
            ordem.append(widget)
        self._linhas = ordem

    def _descartar_linha(self, linha: LinhaDoCombo) -> None:
        """Destrói a linha AGORA — ver "Ciclo de vida" no cabeçalho."""
        linha.clicada.disconnect(self._ao_clicar_linha)
        linha.passo_pedido.disconnect(self._ao_pedir_passo)
        linha.soltar()
        self._layout_linhas.removeWidget(linha)
        linha.hide()
        linha.setParent(None)
        linha.deleteLater()
        if linha in self._linhas:
            self._linhas.remove(linha)

    def _acomodar_barra(self, _minimo: int, maximo: int) -> None:
        """Mantém a borda direita das linhas no mesmo x, com ou sem barra de rolagem.

        Sem isto, a quarta linha adicionada faria todos os steppers andarem 8px
        para a esquerda de uma vez — o número que o gerente estava olhando muda
        de lugar embaixo do dedo. É o mesmo cuidado da coluna de resumo do Caixa
        (§9), que reservou a largura da barra.
        """
        margem = self.MARGEM_LISTA_PX
        if maximo > 0:
            margem = max(0, margem - self._rolagem.verticalScrollBar().sizeHint().width())
        atuais = self._layout_linhas.contentsMargins()
        if atuais.right() != margem:
            self._layout_linhas.setContentsMargins(
                atuais.left(), atuais.top(), margem, atuais.bottom()
            )

    def _linha_por_id(self, combo_item_id: int) -> LinhaDoCombo | None:
        return next(
            (w for w in self._linhas if w.linha.combo_item_id == combo_item_id), None
        )

    def linha_selecionada(self) -> LinhaDoCombo | None:
        return next((w for w in self._linhas if w.selecionada()), None)

    def _selecionar(self, combo_item_id: int | None) -> None:
        for widget in self._linhas:
            widget.definir_selecionada(widget.linha.combo_item_id == combo_item_id)
        alvo = self.linha_selecionada()
        if alvo is not None and self._rolagem.widget() is not None:
            self._rolagem.ensureWidgetVisible(alvo, 0, 8)
        self._atualizar_estado()

    def _atualizar_estado(self) -> None:
        """Botão Remover, aviso de lista vazia e a linha de status, num lugar só."""
        total = len(self._linhas)
        self._vazio.setVisible(total == 0)
        self._botao_remover.setEnabled(self.linha_selecionada() is not None)
        self._dizer_status(texto_do_status(total), "dica")

    def _dizer_status(self, mensagem: str, estado: str) -> None:
        if self._status.text() != mensagem:
            self._status.setText(mensagem)
        if self._status.property("estado") != estado:
            aplicar_propriedade(self._status, "estado", estado)

    def _dizer_erro(self, mensagem: str) -> None:
        """O erro do service toma a linha de status até a próxima ação que der certo.

        Não some sozinho: erro que desaparece é o gerente achando que a
        quantidade foi gravada quando não foi.
        """
        self._dizer_status(mensagem, "erro")

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------

    def _ao_clicar_linha(self, combo_item_id: int) -> None:
        self._selecionar(combo_item_id)

    def _ao_pedir_passo(self, combo_item_id: int, delta: int) -> None:
        """Um clique no stepper: grava, e só então muda o número na tela.

        A ordem é a garantia: o que o gerente vê é o que está no banco. Se o
        service recusar, o número não mexe e o motivo aparece no status.

        Mexer no stepper também seleciona a linha — a última linha tocada é a que
        o "Remover" tira, e não uma outra que ficou âmbar lá atrás.
        """
        widget = self._linha_por_id(combo_item_id)
        if widget is None:
            return
        self._selecionar(combo_item_id)
        nova = widget.linha.quantidade + delta
        if nova < 1 or nova > QUANTIDADE_MAXIMA:
            return
        try:
            self._servico.alterar_quantidade_componente(combo_item_id, nova)
        except _ERROS_SERVICE as erro:
            self._dizer_erro(str(erro))
            return
        self.alterou = True
        widget.definir_quantidade(nova)
        self._atualizar_estado()

    def _remover_selecionada(self) -> None:
        widget = self.linha_selecionada()
        if widget is None:
            return
        try:
            self._servico.remover_componente(widget.linha.combo_item_id)
        except _ERROS_SERVICE as erro:
            self._dizer_erro(str(erro))
            return
        self.alterou = True
        posicao = self._linhas.index(widget)
        self._descartar_linha(widget)
        # A seleção passa para quem ocupou o lugar — o comportamento da tabela
        # antiga, e o que permite tirar vários seguidos sem voltar ao mouse.
        if self._linhas:
            vizinha = self._linhas[min(posicao, len(self._linhas) - 1)]
            self._selecionar(vizinha.linha.combo_item_id)
        else:
            self._atualizar_estado()

    def _abrir_adicao(self) -> None:
        """Abre o cartão "Adicionar item" no modo componente, por cima deste.

        A lista é lida na hora, e não na abertura deste cartão: o stepper faz
        commit, o commit expira as instâncias, e um instantâneo guardado desde a
        abertura voltaria ao banco produto a produto (o N+1 do §9.4).
        `listar_produtos_para_lancamento` traz o mesmo conjunto do formulário
        antigo (`_vendavel`) com as relações carregadas.

        Fora da lista, de antemão, o que o service recusaria de qualquer jeito: o
        próprio combo, quem já é combo e quem já está na composição. O service
        continua recusando — isto só poupa o gerente de escolher e ouvir "não".
        """
        try:
            produtos = self._servico.listar_produtos_para_lancamento()
        except _ERROS_SERVICE as erro:
            self._dizer_erro(str(erro))
            return
        presentes = {w.linha.produto_id for w in self._linhas}
        candidatos = [
            p
            for p in produtos
            if p.id != self._combo_id and not p.is_combo and p.id not in presentes
        ]
        if not candidatos:
            self._dizer_erro(_SEM_CANDIDATOS)
            return

        modal = AdicionarItemDialog.para_componente(
            candidatos, self._combo_nome, self._associar, self
        )
        executar_modal(modal)
        del modal
        self._recarregar()
        if self._linhas and self.linha_selecionada() is None:
            self._selecionar(self._linhas[-1].linha.combo_item_id)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _associar(self, produto_id: int, quantidade: int, _observacao: str | None) -> None:
        """O `lancar_item` do cartão de adição. Erro do service sobe para ele,
        que o mostra na própria linha de aviso sem fechar."""
        self._servico.associar_componente(self._combo_id, produto_id, quantidade)
        self.alterou = True

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    def _mover_selecao(self, delta: int) -> None:
        if not self._linhas:
            return
        atual = self.linha_selecionada()
        posicao = -1 if atual is None else self._linhas.index(atual)
        nova = 0 if posicao == -1 else max(0, min(len(self._linhas) - 1, posicao + delta))
        self._selecionar(self._linhas[nova].linha.combo_item_id)

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """Setas trocam a linha, `Delete`/`Backspace` removem, `Esc` fecha.

        O Esc cai no `super()` de propósito: lá o `QDialog` o traduz em
        `reject()`, que passa por `done()` e pela mesma limpeza dos outros
        caminhos de saída. O Enter também cai lá, e lá não faz nada: não há
        "confirmar" aqui (tudo já foi gravado), e nenhum botão é padrão
        (`cartao_modal.preparar_botao`) para o `QDialog` clicar. Um ramo que o
        engolisse aqui chegou a existir e saiu — a mutação mostrou que ele não
        mudava nada.
        """
        tecla = event.key()
        if tecla == Qt.Key.Key_Down:
            self._mover_selecao(1)
            return
        if tecla == Qt.Key.Key_Up:
            self._mover_selecao(-1)
            return
        if tecla in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._remover_selecionada()
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        self._backdrop = cartao_modal.apresentar(self, self._backdrop)
        # O diálogo, e não um botão, é quem lê o teclado (setas, Delete, Esc).
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — ✕, Esc e o `reject()` de quem chamar passam aqui (§3.9)."""
        self._soltar_recursos()
        super().done(resultado)

    def _soltar_recursos(self) -> None:
        """Desliga o que este cartão ligou — e só uma vez.

        Saem: as três ligações do cabeçalho e do rodapé, as duas de cada linha
        (e as do stepper dentro dela), e o escurecedor, que é filho da JANELA e
        não do diálogo. A trava `_limpo` pela razão registrada no §9.12: um
        segundo `disconnect` nesta versão do PySide6 não estoura, imprime
        `RuntimeWarning` — um por ligação, a cada fechamento.
        """
        if self._limpo:
            return
        self._limpo = True
        self._botao_fechar.clicked.disconnect(self.reject)
        self._botao_remover.clicked.disconnect(self._remover_selecionada)
        self._botao_adicionar.clicked.disconnect(self._abrir_adicao)
        self._rolagem.verticalScrollBar().rangeChanged.disconnect(self._acomodar_barra)
        for linha in self._linhas:
            linha.clicada.disconnect(self._ao_clicar_linha)
            linha.passo_pedido.disconnect(self._ao_pedir_passo)
            linha.soltar()
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
