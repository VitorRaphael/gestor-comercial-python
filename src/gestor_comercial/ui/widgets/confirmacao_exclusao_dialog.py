"""O cartão que confirma a exclusão de categoria, subcategoria e produto (§9.18).

**Um diálogo só, para as três entidades e os três níveis de proteção.** Antes
havia seis caixas de mensagem do sistema no Cardápio (`QMessageBox`, com a
moldura do Windows e o ícone amarelo de fábrica): a confirmação da categoria
vazia, o aviso de categoria com conteúdo, as mesmas duas para a subcategoria, e
o "Sim/Não" do produto — cada uma com a sua frase, os seus botões e o seu jeito
de tratar o Esc.

As três imagens do mockup do Vitor são o mesmo cartão com outras palavras: um
cabeçalho com a lixeira, o item selecionado, um aviso e dois botões. O que muda
de uma para outra se divide em DOIS eixos independentes, e cada um mora numa
tabela:

* **a entidade** (`ENTIDADES`) — o glifo do item, o rótulo ("PRODUTO
  SELECIONADO"), o título e a palavra do botão;
* **o nível de proteção** (`NIVEIS`) — a tarja de cima, o tom do aviso (coral ou
  âmbar) e se o botão confirma num clique, pede a Senha Master ou nem liga.

É a forma do §9.6 e do §9.12 (uma classe, tabelas por papel), e não
base + subclasses (§9.7): as três entidades não têm nenhuma coluna própria, só
palavras. Três classes seriam três cópias do cabeçalho, do aviso, do rodapé, do
teclado e da limpeza.

Quem sabe o nível de cada caso são os **construtores nomeados**
(`para_categoria`, `para_subcategoria`, `para_produto`): é neles, e só neles,
que "vazia" vira confirmação simples e "com conteúdo" vira Senha Master. A view
lê `protecao` depois do `exec()` para escolher o método do service — assim a
regra que decide o cartão e a que decide o service são a mesma linha, e não um
`if` na view repetindo o do cartão.

## A Senha Master abre POR CIMA do cartão

O botão "Excluir com Senha Master" não fecha o cartão: ele chama `autorizar`,
que a view entrega pronto (o `PinPadDialog.para_exclusao`, Nível 3, §9.10). O
PIN abre escurecendo o cartão, e quem desiste do PIN volta ao cartão — com o
item e o aviso ainda à vista — em vez de perder o gesto inteiro. O diálogo não
conhece `AuthService`: recebe uma função que diz se passou.

## O que este diálogo NÃO faz

Regra de negócio nenhuma, e ele não chama o service. Quem apaga, quem arquiva e
quem exige gerente continua sendo o `CardapioService`; se ele recusar (um
instantâneo velho, uma sessão que caiu), o erro aparece na linha vermelha da
tela, como já aparecia.

## Ciclo de vida (o RNF do Celeron, §3.2/§3.9/§3.14)

O pedido escrito falava em `destroy()`, `unbind()` e `after_cancel()`, que são
de Tkinter. Os equivalentes aqui:

* **destroy** — quem destrói é `executar_modal()` (§3.2), com `deleteLater()`
  depois de a view ler `protecao`. Os filhos morrem com o cartão; o único widget
  que não é filho dele é o **escurecedor**, que é filho da janela, e por isso
  `done()` o solta na hora;
* **unbind** — não há atalho global: quem lê Enter e Esc é o `keyPressEvent` do
  próprio diálogo. As três ligações de sinal saem em `_soltar_recursos()`, uma a
  uma, sem `lambda`;
* **timers** — nenhum. O cartão não anima nem espera nada.

Este cartão é **de uma abertura só** (`executar_modal`, nunca um
`while modal.exec()`): a limpeza em `done()` desliga os botões, e reabri-lo
depois dela deixaria o ✕ e o Cancelar mudos.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.services.cardapio_service import (
    VinculosDoProduto,
    contagem,
    quantidades_do_conteudo,
)
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_ALERTA,
    GLIFO_CAIXA,
    GLIFO_ETIQUETA,
    GLIFO_LIXEIRA,
    GLIFO_PASTA,
    BotaoComGlifo,
    GlifoSolto,
)
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

# "Abre a barreira de credencial sobre este cartão e diz se ela passou." Recebe
# o cartão para ser o parent do PIN: é assim que o escurecedor do PIN cobre o
# cartão, e não a tela de trás.
Autorizar = Callable[[QWidget], bool]


class EntidadeDoCardapio(Enum):
    CATEGORIA = "categoria"
    SUBCATEGORIA = "subcategoria"
    PRODUTO = "produto"


class Protecao(Enum):
    """O que o botão vermelho faz — e, por consequência, o que a view chama."""

    # Confirma num clique. O que sai não tem histórico a preservar.
    SIMPLES = "simples"
    # Abre o PIN Nível 3 antes de confirmar. O que tem venda é arquivado.
    SENHA_MASTER = "senha_master"
    # Não liga. O aviso diz o que fazer antes.
    BLOQUEADA = "bloqueada"


@dataclass(frozen=True, slots=True)
class Aviso:
    """As duas frases do cartão de aviso: o fato, e o que ele implica."""

    titulo: str
    descricao: str


@dataclass(frozen=True, slots=True)
class _Entidade:
    glifo: str
    rotulo: str
    titulo: str
    botao: str


@dataclass(frozen=True, slots=True)
class _Nivel:
    secao: str
    # O valor da propriedade `tom` do cartão de aviso no QSS, e o prefixo do
    # token do glifo de alerta (`exclusao_<tom>_glifo`).
    tom: str
    # O rótulo do botão quando é o NÍVEL que o nomeia ("Excluir com Senha
    # Master"); `None` usa o da entidade ("Excluir produto").
    botao: str | None
    liberado: bool


ENTIDADES: dict[EntidadeDoCardapio, _Entidade] = {
    EntidadeDoCardapio.CATEGORIA: _Entidade(
        glifo=GLIFO_PASTA,
        rotulo="CATEGORIA SELECIONADA",
        titulo="Excluir categoria",
        botao="Excluir categoria",
    ),
    EntidadeDoCardapio.SUBCATEGORIA: _Entidade(
        glifo=GLIFO_ETIQUETA,
        rotulo="SUBCATEGORIA SELECIONADA",
        titulo="Excluir subcategoria",
        botao="Excluir subcategoria",
    ),
    EntidadeDoCardapio.PRODUTO: _Entidade(
        glifo=GLIFO_CAIXA,
        # "SELECIONADO", e não o "SELECIONADA" que a imagem do produto traz:
        # a imagem foi montada a partir da de categoria, e a concordância
        # ficou para trás.
        rotulo="PRODUTO SELECIONADO",
        titulo="Excluir produto",
        botao="Excluir produto",
    ),
}

# As tarjas são as três das imagens, e cada imagem é um nível: "EXCLUSÃO
# PROTEGIDA" (categoria com conteúdo), "AÇÃO PERMANENTE" (produto sem venda),
# "CONFIRMAR EXCLUSÃO" (subcategoria bloqueada). Amarrá-las ao NÍVEL, e não à
# entidade, é o que impede o cartão de dizer "ação permanente" sobre um produto
# que vai ser arquivado, ou "exclusão protegida" sobre uma categoria vazia.
NIVEIS: dict[Protecao, _Nivel] = {
    Protecao.SIMPLES: _Nivel(
        secao="AÇÃO PERMANENTE", tom="perigo", botao=None, liberado=True
    ),
    Protecao.SENHA_MASTER: _Nivel(
        secao="EXCLUSÃO PROTEGIDA",
        tom="protegido",
        botao="Excluir com Senha Master",
        liberado=True,
    ),
    Protecao.BLOQUEADA: _Nivel(
        secao="CONFIRMAR EXCLUSÃO", tom="perigo", botao=None, liberado=False
    ),
}

_TOKEN_DO_ALERTA = {"perigo": "exclusao_perigo_glifo", "protegido": "exclusao_protegida_glifo"}

# A frase da Foto 1, dita pelas duas cascatas: categoria e subcategoria arquivam
# pelo mesmo critério (§9.13/§9.14), e duas redações do mesmo critério fariam o
# gerente procurar uma diferença que não existe.
_CASCATA = (
    "Para excluí-la, será necessário confirmar a Senha Master. Os produtos com "
    "vendas registradas serão arquivados e o histórico permanecerá intacto."
)


class ConfirmacaoExclusaoDialog(QDialog):
    """Cartão de confirmação de exclusão de um item do Cardápio.

    Construa pelos construtores nomeados: é neles que a contagem vira nível de
    proteção. O `__init__` existe para os três e para os testes.
    """

    # O pedido escrito dizia "entre 460 e 500px", e aqui fecha: sem a faixa de
    # atalhos que o rodapé do §9.12 tinha, o rodapé mais largo ("Cancelar" +
    # "Excluir com Senha Master") pede ~370px com a fonte da marca. A largura
    # trancada em teste é a da imagem.
    LARGURA_CARTAO_PX = 500
    LADO_BOTAO_FECHAR_PX = 32
    LADO_BADGE_PX = 44
    LADO_ICONE_ITEM_PX = 40

    def __init__(
        self,
        entidade: EntidadeDoCardapio,
        nome: str,
        protecao: Protecao,
        aviso: Aviso,
        parent: QWidget | None = None,
        *,
        autorizar: Autorizar | None = None,
    ) -> None:
        # Falha na construção, e não no clique: um cartão que promete a Senha
        # Master e confirma sem ela é o pior defeito que esta tela pode ter, e
        # ele só apareceria na hora em que alguém estivesse apagando algo.
        if protecao is Protecao.SENHA_MASTER and autorizar is None:
            raise ValueError("A exclusão protegida precisa de uma barreira de credencial.")
        super().__init__(parent)
        self._entidade = ENTIDADES[entidade]
        self._nivel = NIVEIS[protecao]
        self._protecao = protecao
        self._autorizar = autorizar
        self._backdrop: Backdrop | None = None
        self._limpo = False

        self.setObjectName("exclusaoDialog")
        self.setWindowTitle(self._entidade.titulo)
        # Sem moldura do sistema: o cabeçalho é do cartão, e o fundo translúcido
        # é o que faz os cantos de 16px saírem redondos de verdade.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        # Não há campo: é o próprio diálogo que recebe o foco e lê Enter e Esc.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("exclusaoDialogCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addWidget(self._montar_cabecalho())
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_corpo(nome, aviso))
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_rodape())

    # ------------------------------------------------------------------
    # Construtores nomeados — o único lugar que sabe de nível
    # ------------------------------------------------------------------

    @classmethod
    def para_categoria(
        cls,
        nome: str,
        produtos: int,
        subcategorias: int,
        autorizar: Autorizar,
        parent: QWidget | None = None,
    ) -> "ConfirmacaoExclusaoDialog":
        """Vazia é **nem produto nem subdivisão** (§9.14): as subdivisões iriam
        junto pelo `cascade`, e irem junto num clique desmancharia a organização
        de um grupo inteiro sem passar pela Senha Master."""
        if not produtos and not subcategorias:
            return cls(
                EntidadeDoCardapio.CATEGORIA,
                nome,
                Protecao.SIMPLES,
                Aviso(
                    "Deseja excluir esta categoria?",
                    "Ela está vazia — sem produtos e sem subcategorias. Nada mais é afetado.",
                ),
                parent,
                autorizar=autorizar,
            )
        return cls(
            EntidadeDoCardapio.CATEGORIA,
            nome,
            Protecao.SENHA_MASTER,
            Aviso(f"Esta categoria contém {quantidades_do_conteudo(produtos, subcategorias)}.", _CASCATA),
            parent,
            autorizar=autorizar,
        )

    @classmethod
    def para_subcategoria(
        cls,
        nome: str,
        produtos: int,
        autorizar: Autorizar,
        parent: QWidget | None = None,
        *,
        cascata: bool = True,
    ) -> "ConfirmacaoExclusaoDialog":
        """`cascata` é a regra da subdivisão com produtos dentro.

        `True` é a decisão do Vitor no §9.13, reafirmada no §9.18: a Senha
        Master libera a exclusão, e o que tem venda é arquivado. `False` é o
        bloqueio rígido da Foto 3 — o botão não liga e o aviso manda mover os
        produtos antes. O Cardápio de hoje só usa a primeira; a segunda existe
        porque o mockup a desenha e o pedido a descreve.
        """
        if not produtos:
            return cls(
                EntidadeDoCardapio.SUBCATEGORIA,
                nome,
                Protecao.SIMPLES,
                Aviso(
                    "Deseja excluir esta subcategoria?",
                    "Ela não tem nenhum produto dentro — nada mais é afetado.",
                ),
                parent,
                autorizar=autorizar,
            )
        titulo = f"Esta subcategoria contém {contagem(produtos, 'produto')}."
        if not cascata:
            return cls(
                EntidadeDoCardapio.SUBCATEGORIA,
                nome,
                Protecao.BLOQUEADA,
                Aviso(titulo, "Mova ou exclua os produtos antes de continuar."),
                parent,
                autorizar=autorizar,
            )
        return cls(
            EntidadeDoCardapio.SUBCATEGORIA,
            nome,
            Protecao.SENHA_MASTER,
            Aviso(titulo, _CASCATA),
            parent,
            autorizar=autorizar,
        )

    @classmethod
    def para_produto(
        cls,
        nome: str,
        vinculos: VinculosDoProduto,
        autorizar: Autorizar,
        parent: QWidget | None = None,
    ) -> "ConfirmacaoExclusaoDialog":
        """Sem vínculo, a Foto 2. Com qualquer vínculo, a Senha Master (§9.18).

        O título diz o vínculo mais pesado — a venda, depois o combo que o
        contém, depois a composição dele — e a descrição diz TUDO o que vai
        acontecer, porque arquivar um componente mexe num combo que ninguém
        mandou excluir, e quem digita a Senha Master precisa saber disso antes.
        """
        if not vinculos.tem_historico:
            return cls(
                EntidadeDoCardapio.PRODUTO,
                nome,
                Protecao.SIMPLES,
                Aviso(
                    "Deseja excluir este produto permanentemente?",
                    "Esta ação não pode ser desfeita.",
                ),
                parent,
                autorizar=autorizar,
            )
        if vinculos.vendido:
            titulo = "Este produto tem vendas registradas."
        elif vinculos.combos_que_o_contem:
            titulo = f"Este produto faz parte de {contagem(vinculos.combos_que_o_contem, 'combo')}."
        else:
            titulo = f"Este produto é um combo com {contagem(vinculos.componentes, 'componente')}."
        frases = ["Para excluí-lo, será necessário confirmar a Senha Master."]
        if vinculos.combos_que_o_contem:
            frases.append(
                f"Ele sai da composição de {contagem(vinculos.combos_que_o_contem, 'combo')}."
            )
        if vinculos.componentes:
            frases.append("A composição dele é desfeita, e os componentes continuam no cardápio.")
        frases.append(
            "Ele será arquivado: sai do cardápio e dos novos pedidos, e os relatórios "
            "e cupons passados continuam intactos."
        )
        return cls(
            EntidadeDoCardapio.PRODUTO,
            nome,
            Protecao.SENHA_MASTER,
            Aviso(titulo, " ".join(frases)),
            parent,
            autorizar=autorizar,
        )

    @property
    def protecao(self) -> Protecao:
        """O nível com que o cartão foi aberto — a view escolhe o service por ele."""
        return self._protecao

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _divisor(self) -> QFrame:
        linha = QFrame()
        linha.setObjectName("exclusaoDialogDivisor")
        linha.setFixedHeight(1)
        return linha

    def _quadro_com_glifo(self, nome_do_objeto: str, lado: int, glifo: str, token: str) -> QFrame:
        """O quadrado arredondado com um glifo no meio — a lixeira do cabeçalho e
        o ícone do item. O fundo e a borda vêm do QSS pelo nome do objeto."""
        quadro = QFrame()
        quadro.setObjectName(nome_do_objeto)
        quadro.setFixedSize(lado, lado)
        dentro = QHBoxLayout(quadro)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(GlifoSolto(glifo, lado // 2, token), 0, Qt.AlignmentFlag.AlignCenter)
        return quadro

    def _montar_cabecalho(self) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("exclusaoDialogCabecalho")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(22, 18, 18, 18)
        linha.setSpacing(14)
        linha.addWidget(
            self._quadro_com_glifo(
                "exclusaoDialogBadge", self.LADO_BADGE_PX, GLIFO_LIXEIRA, "exclusao_badge_glifo"
            ),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        textos = QVBoxLayout()
        textos.setSpacing(3)
        self._secao = QLabel(self._nivel.secao)
        self._secao.setObjectName("exclusaoDialogSecao")
        textos.addWidget(self._secao)
        self._titulo = QLabel(self._entidade.titulo)
        self._titulo.setObjectName("exclusaoDialogTitulo")
        textos.addWidget(self._titulo)
        linha.addLayout(textos, 1)

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("exclusaoDialogFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignVCenter)
        return faixa

    def _montar_corpo(self, nome: str, aviso: Aviso) -> QWidget:
        """A faixa pontilhada do meio: o que vai sair, e o que isso implica.

        `PainelPontilhado` pela mesma razão do §9.12: é a textura que o mockup
        mostra atrás do conteúdo, a mesma do Cardápio de onde o cartão sai.
        """
        faixa = PainelPontilhado()
        faixa.setObjectName("exclusaoDialogCorpo")
        coluna = QVBoxLayout(faixa)
        coluna.setContentsMargins(22, 20, 22, 20)
        coluna.setSpacing(16)
        coluna.addWidget(self._montar_item(nome))
        coluna.addWidget(self._montar_aviso(aviso))
        return faixa

    def _montar_item(self, nome: str) -> QFrame:
        painel = QFrame()
        painel.setObjectName("exclusaoDialogItem")
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(16, 14, 16, 14)
        linha.setSpacing(14)
        linha.addWidget(
            self._quadro_com_glifo(
                "exclusaoDialogItemIcone",
                self.LADO_ICONE_ITEM_PX,
                self._entidade.glifo,
                "cardapio_icone_glifo",
            ),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        textos = QVBoxLayout()
        textos.setSpacing(3)
        rotulo = QLabel(self._entidade.rotulo)
        rotulo.setObjectName("exclusaoDialogRotulo")
        textos.addWidget(rotulo)
        # Quebra de linha, e não reticências: é o nome do que vai ser apagado, e
        # "Cachorro Quente Lin…" numa confirmação destrutiva é pedir para o
        # gerente confirmar o que ele não leu inteiro.
        self._nome = QLabel(nome)
        self._nome.setObjectName("exclusaoDialogNome")
        self._nome.setWordWrap(True)
        textos.addWidget(self._nome)
        linha.addLayout(textos, 1)
        return painel

    def _montar_aviso(self, aviso: Aviso) -> QFrame:
        painel = QFrame()
        painel.setObjectName("exclusaoDialogAviso")
        painel.setProperty("tom", self._nivel.tom)
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(16, 14, 16, 16)
        linha.setSpacing(12)
        linha.addWidget(
            GlifoSolto(GLIFO_ALERTA, 18, _TOKEN_DO_ALERTA[self._nivel.tom]),
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        textos = QVBoxLayout()
        textos.setSpacing(6)
        self._aviso_titulo = QLabel(aviso.titulo)
        self._aviso_titulo.setObjectName("exclusaoDialogAvisoTitulo")
        self._aviso_titulo.setWordWrap(True)
        textos.addWidget(self._aviso_titulo)
        self._aviso_texto = QLabel(aviso.descricao)
        self._aviso_texto.setObjectName("exclusaoDialogAvisoTexto")
        self._aviso_texto.setWordWrap(True)
        textos.addWidget(self._aviso_texto)
        linha.addLayout(textos, 1)
        return painel

    def _montar_rodape(self) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("exclusaoDialogRodape")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(22, 16, 22, 18)
        linha.setSpacing(12)
        linha.addStretch()

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("exclusaoDialogCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = BotaoComGlifo(
            self._nivel.botao or self._entidade.botao,
            GLIFO_LIXEIRA,
            "exclusao_acao_texto",
            "exclusao_acao_desligada_texto",
        )
        self._botao_confirmar.setObjectName("exclusaoDialogConfirmar")
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.setEnabled(self._nivel.liberado)
        self._botao_confirmar.clicked.connect(self._confirmar)
        linha.addWidget(self._botao_confirmar)
        return faixa

    # ------------------------------------------------------------------
    # Confirmação
    # ------------------------------------------------------------------

    def _confirmar(self) -> None:
        """O botão vermelho e o Enter chegam aqui — e só passam se puderem.

        Na Senha Master o cartão continua aberto enquanto o PIN está na tela: se
        o PIN for recusado ou fechado, o gerente volta a este cartão, que
        continua dizendo o que ia sair. Só a credencial aceita fecha o cartão
        como aceito.
        """
        if not self._botao_confirmar.isEnabled():
            return
        if self._protecao is Protecao.SENHA_MASTER and not self._autorizar(self):
            return
        self.accept()

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """Enter aciona o botão vermelho, se ele estiver ligado; Esc cancela.

        Os `QMessageBox` que este cartão substitui faziam o contrário — o botão
        padrão era o Cancelar. O pedido escrito do §9.18 manda o Enter excluir,
        e o risco que a regra antiga cobria continua coberto por outros dois
        lados: chegar aqui já exige um gesto (Excluir ou Delete), e o que tem
        histórico ainda exige a Senha Master depois do Enter.

        O Esc cai no `super()`: lá o `QDialog` o traduz em `reject()`, que passa
        por `done()` e pela mesma limpeza dos outros caminhos de saída.
        """
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirmar()
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        self._backdrop = cartao_modal.apresentar(self, self._backdrop)
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — Excluir, Cancelar, ✕ e Esc passam todos por aqui.

        `closeEvent` sozinho não serviria: `done()` faz `hide()`, não `close()`
        (§3.9).
        """
        self._soltar_recursos()
        super().done(resultado)

    def _soltar_recursos(self) -> None:
        """Desliga o que este cartão ligou — e só uma vez.

        As três ligações de sinal saem nominalmente, e o escurecedor é solto da
        janela agora (ele é o único widget que o Qt não recolheria junto com o
        cartão). A trava `_limpo` é a do §9.12: o segundo `disconnect` não
        estoura nesta versão do PySide6, mas imprime um `RuntimeWarning` por
        ligação, e aviso que aparece sempre é o que faz ninguém ler o que
        importa.
        """
        if self._limpo:
            return
        self._limpo = True
        self._botao_fechar.clicked.disconnect(self.reject)
        self._botao_cancelar.clicked.disconnect(self.reject)
        self._botao_confirmar.clicked.disconnect(self._confirmar)
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
