"""O cartão que cadastra os dois níveis do cardápio: categoria e subcategoria (§9.12).

**Um modal só, com dois papéis** — e é essa a decisão que este arquivo carrega.
Antes havia duas telas para a mesma pergunta ("que nome tem este grupo?"):

* `_CategoriaDialog`, 20 linhas dentro de `cardapio_view.py`, com a moldura do
  sistema, um `QFormLayout` e o `QDialogButtonBox` de fábrica — a última janela
  do Cardápio que ainda parecia um formulário de 2005;
* `SubcategoriaDialog` (§9.9), já em cartão, mas com o desenho anterior ao
  mockup e uma cópia inteira de cabeçalho, campo, contador, rodapé e ciclo de
  vida — as mesmas cinco peças que a categoria precisaria copiar para ficar
  parecida com ela.

As duas telas do mockup do Vitor diferem em **seis frases, um glifo e a regra
de comparação de nome repetido**. Tudo o mais — o cartão, o cabeçalho, o campo
com anel de foco, o contador, a linha de validação, o rodapé, o teclado e a
limpeza — é igual. Por isso aqui é uma classe parametrizada por
`NivelDoCardapio`, e não duas classes irmãs: é a decisão do §9.6 (a
movimentação de caixa, `OPERACOES`), pelo mesmo motivo e com a mesma forma. O
que separa um papel do outro está em `PAPEIS`, numa linha por papel, e chega a
exatamente onde precisa chegar: o glifo do cabeçalho, os rótulos e a função que
decide se o nome digitado já existe.

Não é base + subclasses (a forma do §9.7, abertura/fechamento de caixa) porque
ali as duas colunas da esquerda não tinham nada em comum; aqui a tela é a mesma
tela, com outras palavras dentro.

## O que este diálogo NÃO faz

Regra de negócio nenhuma, e método de service nenhum é novo. Ele devolve
`DadosOrganizacao` e a view chama `criar_categoria`/`editar_categoria` ou
`criar_subcategoria`/`editar_subcategoria`. Quem exige gerente, quem apara o
nome e quem recusa o repetido continua sendo o `CardapioService` — e a
impressora de ninguém é tocada aqui: subcategoria não tem bobina, a categoria é
que decide (§9.8), e é por isso que o cartão de contexto diz a impressora em
voz alta em vez de deixar a pergunta no ar.

A conferência de duplicidade **desta tela é só um aviso**: ela usa a mesma
regra do service, mas quem decide é o service — se as duas divergirem um dia, o
cadastro é recusado com mensagem, não gravado errado.

### As duas regras de nome repetido são diferentes, e de propósito

`CardapioService._exigir_nome_de_categoria_livre` compara o nome **exato**
(`Categoria.nome == nome`); `_exigir_nome_de_subcategoria_livre` compara pela
`chave_de_agrupamento`, ignorando acento e caixa. Espelhar aqui a regra de cada
nível é o que impede a tela de **mentir**: um "✕ Nome já existente" em
"lanches" com "Lanches" cadastrada seria um botão desligado por uma regra que o
service não tem, e o gerente ficaria sem saber por que não consegue salvar.

## Ciclo de vida (o RNF do Celeron, §3.2/§3.9/§3.14)

* **destroy** — quem destrói é `executar_modal()`/`descartar_modal()` (§3.2),
  que fazem o `deleteLater()` depois de ler o resultado. `WA_DeleteOnClose` não
  serve: `done()` faz `hide()`, não `close()`, e `resultado()` é lido **depois**
  do `exec()`. Os filhos morrem com o cartão porque são filhos dele — o único
  widget que não é filho do diálogo é o **escurecedor**, que é filho da janela
  principal, e é por isso que `done()` existe aqui;
* **unbind** — não há atalho global: quem lê o teclado é o `keyPressEvent` do
  próprio diálogo, e um `QShortcut` de aplicação sobreviveria ao cartão. As
  ligações de sinal saem no `_soltar_recursos()`, uma a uma, e nenhuma usa
  `lambda` (§3.14);
* **timers** — nenhum. A conferência do nome roda na tecla e compara strings
  curtas contra a lista da própria categoria (no cardápio real, três nomes).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QShowEvent
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
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_CAMADAS,
    GLIFO_PASTA_MAIS,
    GLIFO_RAMO,
    GlifoSolto,
)
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

# O teto do campo. As duas colunas do banco são `String(80)`; o mockup pede 60,
# que é mais apertado e portanto seguro — o que a tela aceita nunca chega ao
# limite da coluna. Ver `_maximo_do_campo` para o caso do nome que JÁ existe
# mais longo que isto: cortá-lo na abertura da edição seria perder dado calado.
LIMITE_NOME = 60

# Abaixo disto o botão fica desligado. Uma letra sozinha não nomeia grupo
# nenhum, e um cardápio com uma categoria "L" é mais caro de consertar do que
# de evitar. O service aceitaria (ele só recusa vazio): esta é uma trava de
# tela, e está escrita aqui para não virar surpresa quando alguém comparar as
# duas camadas.
MINIMO_NOME = 2

_SEM_IMPRESSORA = "SEM IMPRESSORA"
_SECAO = "ORGANIZAÇÃO DO CARDÁPIO"
_RAIZ = "Raiz do cardápio"

_STATUS_VALIDO = "✓  Nome válido"
_STATUS_REPETIDO = "✕  Nome já existente"

# `✓`/`✕` e não `✅`/`❌`: os dois primeiros moram na fonte de texto, o par de
# emoji cairia no Segoe UI Emoji — sairia colorido, chapado, ignorando o tema, e
# a máquina limpa do food truck pode nem ter a fonte. É a armadilha do cadeado
# do PIN (§9.4) e do olho das senhas (§9.10), já paga duas vezes.


def _texto_aparado(texto: str) -> str:
    """O nome como ele vai para o banco: pontas aparadas, espaço interno único.

    É a forma que `resultado()` devolve, e por isso também a forma que a
    conferência de duplicidade da CATEGORIA compara — o service checa o nome
    exato que recebe, e o que ele recebe é isto.
    """
    return " ".join(texto.split())


class NivelDoCardapio(Enum):
    """Os dois níveis que este cartão cadastra."""

    CATEGORIA = "categoria"
    SUBCATEGORIA = "subcategoria"


@dataclass(frozen=True, slots=True)
class DadosOrganizacao:
    """O que o modal devolve — hoje um campo só, e ainda assim um tipo.

    Mesmo formato de `DadosProduto`, `DadosFuncionario` e `DadosMovimento`: o
    diálogo devolve dados, a view chama o service. Um `str` cru economizaria
    uma classe e custaria a próxima vez — foi exatamente assim que o modal de
    produto chegou a uma tupla de sete posições desempacotada por ordem.
    """

    nome: str


@dataclass(frozen=True, slots=True)
class _Modo:
    """As frases que mudam entre cadastrar e renomear, dentro de um mesmo papel."""

    titulo: str
    subtitulo: str
    ajuda: str
    rotulo_contexto: str
    botao: str
    atalhos: str


@dataclass(frozen=True, slots=True)
class _Papel:
    """Tudo o que separa "categoria" de "subcategoria" nesta tela.

    Sete campos. Se um dia for preciso um oitavo, ele entra aqui — e não num
    `if self._nivel is ...` espalhado pelo meio da montagem, que é como duas
    telas voltam a existir sem ninguém decidir isso.
    """

    glifo: str
    rotulo_campo: str
    placeholder: str
    destino_padrao: str
    # A forma canônica do nome para dizer se dois são o mesmo. É A REGRA DO
    # SERVICE DAQUELE NÍVEL, espelhada (ver o cabeçalho do módulo).
    normalizar: Callable[[str], str]
    criar: _Modo
    editar: _Modo


PAPEIS: dict[NivelDoCardapio, _Papel] = {
    NivelDoCardapio.CATEGORIA: _Papel(
        glifo=GLIFO_PASTA_MAIS,
        rotulo_campo="NOME DA CATEGORIA",
        placeholder="Ex.: Sobremesas, Pratos executivos",
        destino_padrao=_RAIZ,
        normalizar=_texto_aparado,
        criar=_Modo(
            titulo="Nova categoria",
            subtitulo="Crie um novo grupo principal para organizar seu cardápio.",
            ajuda="Depois, você poderá criar subcategorias dentro dela.",
            rotulo_contexto="SERÁ CRIADA EM",
            botao="+ Criar categoria",
            atalhos="ENTER PARA CRIAR · ESC PARA FECHAR",
        ),
        editar=_Modo(
            titulo="Editar categoria",
            subtitulo="Renomeie o grupo principal do cardápio.",
            ajuda="Os produtos e as subcategorias dela continuam onde estão.",
            rotulo_contexto="ESTÁ EM",
            botao="Salvar alterações",
            atalhos="ENTER PARA SALVAR · ESC PARA FECHAR",
        ),
    ),
    NivelDoCardapio.SUBCATEGORIA: _Papel(
        glifo=GLIFO_RAMO,
        rotulo_campo="NOME DA SUBCATEGORIA",
        placeholder="Ex.: Podrão, Artesanal, Guarnições",
        # Nunca usado: a subcategoria só é cadastrada de dentro de uma
        # categoria, e a view não abre este modal sem uma selecionada. Está
        # aqui porque o campo é do papel, e um `None` no lugar obrigaria todo
        # leitor do cartão de contexto a tratar a ausência.
        destino_padrao=_RAIZ,
        normalizar=chave_de_agrupamento,
        criar=_Modo(
            titulo="Nova subcategoria",
            subtitulo="Crie uma divisão para organizar os produtos desta categoria.",
            ajuda="Os produtos poderão ser adicionados depois.",
            rotulo_contexto="SERÁ CRIADA DENTRO DE",
            botao="+ Criar subcategoria",
            atalhos="ENTER PARA CRIAR · ESC PARA FECHAR",
        ),
        editar=_Modo(
            titulo="Editar subcategoria",
            subtitulo="Renomeie esta divisão da categoria.",
            ajuda="Os produtos dela continuam na mesma impressora.",
            rotulo_contexto="ESTÁ DENTRO DE",
            botao="Salvar alterações",
            atalhos="ENTER PARA SALVAR · ESC PARA FECHAR",
        ),
    ),
}


class OrganizacaoCardapioDialog(QDialog):
    """Cartão de cadastro/edição de um nível do cardápio.

    Construa pelos construtores nomeados (`para_categoria`, `para_subcategoria`)
    e não pelo `__init__`: é a convenção do `PinPadDialog` (§9.10), e o motivo é
    o mesmo — quem chama diz o que quer cadastrar, não como o cartão se veste.
    """

    # A largura do mockup. O pedido escrito dizia "entre 460 e 500", e medido
    # não fecha: o rodapé de UMA linha que o mockup desenha (atalhos à
    # esquerda, os dois botões à direita) pede 546px com a fonte da marca, que
    # é ~20% mais larga que a do desenho. A 500px o "+ Criar subcategoria"
    # saía cortado no meio e "ENTER PARA CRIAR · ESC PARA FECHAR" virava
    # "ENTER PARA CRIAR · ES" — o rodapé mentindo sobre a própria tecla.
    # 576 é a largura do cartão nas duas imagens, e com ela o subtítulo também
    # volta para uma linha só, como lá.
    LARGURA_CARTAO_PX = 576
    LADO_BOTAO_FECHAR_PX = 32
    LADO_BADGE_PX = 44
    LADO_ICONE_CONTEXTO_PX = 36
    ALTURA_CAMPO_PX = 48

    def __init__(
        self,
        nivel: NivelDoCardapio,
        parent: QWidget | None = None,
        *,
        destino: str | None = None,
        impressora: str | None = None,
        existentes: Sequence[str] = (),
        nome_inicial: str = "",
    ) -> None:
        super().__init__(parent)
        self._papel = PAPEIS[nivel]
        self._edicao = bool(nome_inicial)
        self._modo = self._papel.editar if self._edicao else self._papel.criar
        self._backdrop: Backdrop | None = None
        self._limpo = False
        # As chaves das que já existem, menos a própria (na edição): é contra
        # elas que a linha de validação confere o que está sendo digitado.
        propria = self._papel.normalizar(nome_inicial)
        self._chaves_ocupadas = {
            chave
            for nome in existentes
            if (chave := self._papel.normalizar(nome)) != propria
        }

        self.setObjectName("orgDialog")
        self.setWindowTitle(self._modo.titulo)
        # Sem moldura do sistema: o cabeçalho é do cartão, e o fundo translúcido
        # é o que faz os cantos de 16px saírem redondos de verdade.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("orgDialogCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        # Spacing zero e margem zero: as três faixas (cabeçalho, corpo, rodapé)
        # encostam uma na outra e quem as separa é o divisor de 1px, como no
        # mockup. A folga de cada faixa é a margem interna dela.
        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addWidget(self._montar_cabecalho())
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_corpo(destino, impressora, nome_inicial))
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_rodape())

        self._ao_digitar(nome_inicial)

    # ------------------------------------------------------------------
    # Construtores nomeados — o único lugar que sabe de nível
    # ------------------------------------------------------------------

    @classmethod
    def para_categoria(
        cls,
        existentes: Sequence[str],
        parent: QWidget | None = None,
        *,
        nome_inicial: str = "",
    ) -> "OrganizacaoCardapioDialog":
        """Grupo principal: nasce na raiz do cardápio, sem categoria em volta."""
        return cls(
            NivelDoCardapio.CATEGORIA,
            parent,
            existentes=existentes,
            nome_inicial=nome_inicial,
        )

    @classmethod
    def para_subcategoria(
        cls,
        categoria_nome: str,
        impressora_nome: str | None,
        existentes: Sequence[str],
        parent: QWidget | None = None,
        *,
        nome_inicial: str = "",
    ) -> "OrganizacaoCardapioDialog":
        """Divisão de uma categoria — e a impressora dela, dita em voz alta.

        A impressora está no cartão por causa da regra de ouro do §9.8: é a
        CATEGORIA que decide a bobina, e a subcategoria não muda nada disso.
        Quem cria "Podrão" dentro de "Lanches" vê, na hora, que os itens vão
        continuar saindo na impressora de Lanches — e essa é exatamente a
        pergunta que uma tela de subdivisão levanta.
        """
        return cls(
            NivelDoCardapio.SUBCATEGORIA,
            parent,
            destino=categoria_nome,
            impressora=impressora_nome,
            existentes=existentes,
            nome_inicial=nome_inicial,
        )

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _divisor(self) -> QFrame:
        linha = QFrame()
        linha.setObjectName("orgDialogDivisor")
        linha.setFixedHeight(1)
        return linha

    def _montar_cabecalho(self) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("orgDialogCabecalho")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(22, 18, 18, 16)
        linha.setSpacing(14)

        badge = QFrame()
        badge.setObjectName("orgDialogBadge")
        badge.setFixedSize(self.LADO_BADGE_PX, self.LADO_BADGE_PX)
        dentro = QHBoxLayout(badge)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(
            GlifoSolto(self._papel.glifo, 20, "cardapio_icone_glifo"),
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        linha.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        secao = QLabel(_SECAO)
        secao.setObjectName("orgDialogSecao")
        textos.addWidget(secao)
        titulo = QLabel(self._modo.titulo)
        titulo.setObjectName("orgDialogTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel(self._modo.subtitulo)
        subtitulo.setObjectName("orgDialogSubtitulo")
        subtitulo.setWordWrap(True)
        textos.addWidget(subtitulo)
        linha.addLayout(textos, 1)

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("orgDialogFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return faixa

    def _montar_corpo(
        self, destino: str | None, impressora: str | None, nome_inicial: str
    ) -> QWidget:
        """A faixa do meio: onde vai nascer, e com que nome.

        É um `PainelPontilhado` e não um `QWidget` porque a textura de pontos é
        o que o mockup mostra atrás do formulário — a mesma do login, da barra
        lateral e dos dois painéis do Cardápio (§9.11). Custa um `paintEvent`
        com ~30 pontos na região suja, e em troca o cartão pertence à tela de
        onde ele sai.
        """
        faixa = PainelPontilhado()
        faixa.setObjectName("orgDialogCorpo")
        coluna = QVBoxLayout(faixa)
        coluna.setContentsMargins(22, 18, 22, 20)
        coluna.setSpacing(18)
        coluna.addWidget(self._montar_contexto(destino, impressora))
        coluna.addWidget(self._montar_campo(nome_inicial))
        return faixa

    def _montar_contexto(self, destino: str | None, impressora: str | None) -> QFrame:
        painel = QFrame()
        painel.setObjectName("orgDialogContexto")
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(14, 12, 14, 12)
        linha.setSpacing(12)

        icone = QFrame()
        icone.setObjectName("orgDialogContextoIcone")
        icone.setFixedSize(self.LADO_ICONE_CONTEXTO_PX, self.LADO_ICONE_CONTEXTO_PX)
        dentro = QHBoxLayout(icone)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(
            GlifoSolto(GLIFO_CAMADAS, 18, "cardapio_icone_glifo"),
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        linha.addWidget(icone, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        rotulo = QLabel(self._modo.rotulo_contexto)
        rotulo.setObjectName("orgDialogRotulo")
        textos.addWidget(rotulo)
        alvo = QLabel(destino or self._papel.destino_padrao)
        alvo.setObjectName("orgDialogDestino")
        textos.addWidget(alvo)
        linha.addLayout(textos, 1)

        # O selo da bobina só existe quando há categoria em volta: na raiz não
        # há impressora nenhuma a citar, e um "SEM IMPRESSORA" ali diria de uma
        # categoria recém-nascida algo que não é escolha de quem a cria.
        if destino is not None:
            self._selo_impressora = QLabel((impressora or _SEM_IMPRESSORA).upper())
            self._selo_impressora.setObjectName("orgDialogImpressora")
            linha.addWidget(self._selo_impressora, 0, Qt.AlignmentFlag.AlignVCenter)
        return painel

    def _montar_campo(self, nome_inicial: str) -> QWidget:
        bloco = QWidget()
        coluna = QVBoxLayout(bloco)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(8)

        topo = QHBoxLayout()
        topo.setSpacing(10)
        rotulo = QLabel(self._papel.rotulo_campo)
        rotulo.setObjectName("orgDialogRotulo")
        topo.addWidget(rotulo)
        topo.addStretch()
        self._contador = QLabel()
        self._contador.setObjectName("orgDialogContador")
        topo.addWidget(self._contador)
        coluna.addLayout(topo)

        self._caixa_campo = QFrame()
        self._caixa_campo.setObjectName("orgDialogCaixa")
        self._caixa_campo.setFixedHeight(self.ALTURA_CAMPO_PX)
        self._caixa_campo.setProperty("foco", False)
        dentro = QHBoxLayout(self._caixa_campo)
        dentro.setContentsMargins(16, 0, 16, 0)
        dentro.setSpacing(0)

        self._campo_nome = QLineEdit(nome_inicial)
        self._campo_nome.setObjectName("orgDialogCampo")
        self._campo_nome.setPlaceholderText(self._papel.placeholder)
        self._campo_nome.setMaxLength(self._maximo_do_campo(nome_inicial))
        self._campo_nome.textChanged.connect(self._ao_digitar)
        # O anel é do QUADRO e o foco é do campo lá dentro: sem este filtro o
        # `[foco="true"]` nunca acenderia. Mesmo arranjo do §9.4, e
        # `_soltar_recursos()` remove o filtro.
        self._campo_nome.installEventFilter(self)
        dentro.addWidget(self._campo_nome, 1)
        coluna.addWidget(self._caixa_campo)

        # A linha de baixo tem dois papéis fixos: à esquerda o que vai acontecer
        # (ou o erro que o service devolveu), à direita o veredito do nome. São
        # dois rótulos e não um porque eles mudam por motivos diferentes — um
        # texto só piscaria entre ajuda e validação a cada tecla.
        pe = QHBoxLayout()
        pe.setSpacing(12)
        self._ajuda = QLabel(self._modo.ajuda)
        self._ajuda.setObjectName("orgDialogAjuda")
        self._ajuda.setWordWrap(True)
        self._ajuda.setProperty("estado", "dica")
        pe.addWidget(self._ajuda, 1)
        self._status = QLabel()
        self._status.setObjectName("orgDialogStatus")
        self._status.setProperty("estado", "neutro")
        pe.addWidget(self._status, 0, Qt.AlignmentFlag.AlignRight)
        coluna.addLayout(pe)
        return bloco

    def _maximo_do_campo(self, nome_inicial: str) -> int:
        """O teto do campo, nunca menor que o nome que já está lá dentro.

        `setMaxLength` **corta o texto existente** na hora em que é aplicado.
        Abrir a edição de um nome cadastrado antes deste teto e devolvê-lo
        aparado seria perder dado sem dizer nada — o tipo de mudança calada que
        este projeto persegue desde o §9.8. Nome novo continua limitado a
        `LIMITE_NOME`.
        """
        return max(LIMITE_NOME, len(nome_inicial))

    def _montar_rodape(self) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("orgDialogRodape")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(22, 14, 22, 16)
        linha.setSpacing(12)

        atalhos = QLabel(self._modo.atalhos)
        atalhos.setObjectName("orgDialogAtalhos")
        linha.addWidget(atalhos)
        linha.addStretch()

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("orgDialogCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = QPushButton(self._modo.botao)
        self._botao_confirmar.setObjectName("orgDialogConfirmar")
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self._confirmar)
        linha.addWidget(self._botao_confirmar)
        return faixa

    # ------------------------------------------------------------------
    # Digitação
    # ------------------------------------------------------------------

    def _ao_digitar(self, texto: str) -> None:
        nome = _texto_aparado(texto)
        self._contador.setText(f"{len(texto)}/{LIMITE_NOME}")
        # Qualquer tecla apaga o erro que o service tinha devolvido: ele falava
        # do texto anterior, e deixá-lo na tela enquanto se corrige é o aviso
        # contradizendo o campo.
        self._dizer_ajuda(self._modo.ajuda, "dica")

        if not nome:
            self._dizer_status("", "neutro")
            self._botao_confirmar.setEnabled(False)
            return
        if len(nome) < MINIMO_NOME:
            self._dizer_status(f"Mínimo de {MINIMO_NOME} letras", "neutro")
            self._botao_confirmar.setEnabled(False)
            return
        if self._papel.normalizar(nome) in self._chaves_ocupadas:
            # A mesma comparação do service: avisar aqui evita a ida e volta de
            # digitar, salvar e receber "já existe" de volta.
            self._dizer_status(_STATUS_REPETIDO, "erro")
            self._botao_confirmar.setEnabled(False)
            return
        self._dizer_status(_STATUS_VALIDO, "ok")
        self._botao_confirmar.setEnabled(True)

    def _dizer_status(self, mensagem: str, estado: str) -> None:
        self._status.setText(mensagem)
        aplicar_propriedade(self._status, "estado", estado)

    def _dizer_ajuda(self, mensagem: str, estado: str) -> None:
        if self._ajuda.text() == mensagem and self._ajuda.property("estado") == estado:
            return
        self._ajuda.setText(mensagem)
        aplicar_propriedade(self._ajuda, "estado", estado)

    def mostrar_erro_servico(self, mensagem: str) -> None:
        """Erro vindo do service, sem fechar o modal nem perder o que foi digitado.

        A mensagem toma a linha da ESQUERDA, que é a larga: as do service são
        frases inteiras ("Já existe a subcategoria 'Prensado' nesta categoria.")
        e não caberiam no selo da direita sem virar reticências.
        """
        self._dizer_ajuda(mensagem, "erro")
        self._campo_nome.setFocus(Qt.FocusReason.OtherFocusReason)

    def _confirmar(self) -> None:
        if self._botao_confirmar.isEnabled():
            self.accept()

    def resultado(self) -> DadosOrganizacao:
        """O nome já aparado. Quem valida de verdade é o service."""
        return DadosOrganizacao(nome=_texto_aparado(self._campo_nome.text()))

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
        """O `Enter` grava, e só quando há o que gravar.

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
        self.adjustSize()
        cartao_modal.centralizar_no_pai(self)
        self._campo_nome.setFocus(Qt.FocusReason.OtherFocusReason)
        self._campo_nome.selectAll()

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — e por isso o lugar certo da limpeza.

        Criar, Cancelar, o ✕ e o Esc passam todos por aqui; `closeEvent`
        sozinho não serviria, porque `done()` faz `hide()`, não `close()`
        (§3.9).
        """
        self._soltar_recursos()
        super().done(resultado)

    def _soltar_recursos(self) -> None:
        """Desliga o que este cartão ligou — e só uma vez.

        O que sai daqui:

        * o **filtro de eventos** do campo, que é a única coisa que este
          diálogo instala em outro objeto (ainda que num filho);
        * as **três ligações de sinal**, desconectadas nominalmente. Elas
          morreriam com os filhos de qualquer forma; explicitá-las é o que
          impede que uma quarta ligação a um objeto de FORA do cartão entre um
          dia sem ninguém notar que aquela, sim, sobreviveria ao fechamento;
        * o **escurecedor**, que é filho da JANELA e não do diálogo — é o único
          widget que o Qt não recolheria junto com o cartão.

        A trava `_limpo` existe porque `done()` pode ser chamado duas vezes: um
        `reject()` depois de um `accept()`, um Esc num diálogo que já está
        fechando. Nesta versão do PySide6 (6.11.2) o segundo `disconnect` não
        estoura — ele devolve `False` e imprime
        `RuntimeWarning: libpyside: Failed to disconnect`, um aviso por ligação
        e por fechamento. Não é cosmético: aviso previsível que aparece sempre é
        o que faz ninguém ler o aviso que importa quando ele vier. E é a trava
        que mantém a limpeza **idempotente** no dia em que ela passar a tocar
        algo que não aceita ser solto duas vezes.
        """
        if self._limpo:
            return
        self._limpo = True
        self._campo_nome.removeEventFilter(self)
        self._campo_nome.textChanged.disconnect(self._ao_digitar)
        self._botao_fechar.clicked.disconnect(self.reject)
        self._botao_cancelar.clicked.disconnect(self.reject)
        self._botao_confirmar.clicked.disconnect(self._confirmar)
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
