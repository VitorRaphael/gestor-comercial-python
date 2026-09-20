"""A tela "Receber Pagamento" (§9.25).

Substitui o `PagamentoDialog`, que era a última janela de fábrica do fluxo de
venda: um `QFormLayout` com combo de forma de pagamento, um campo de texto para
o valor, um campo de PIN e um resumo em três linhas de texto corrido. Quem
recebia não via o que o cliente estava pagando — a lista de itens ficava na tela
de trás — e o troco só aparecia depois de registrar.

O mockup do Vitor é uma TELA, não um modal: sai do fluxo de janela sobre janela
e entra na navegação do shell, com "← Voltar à mesa" e "Imprimir 2ª via" no
cabeçalho. Duas colunas:

* **esquerda, "Consumo da mesa"** — os itens, o subtotal, a taxa de serviço, o
  bloco âmbar do total e o "dividir por", que só mostra quanto dá por pessoa;
* **direita, "Registrar pagamento"** — as cinco formas em cards, o valor
  recebido, o troco ao vivo, o card da comissão do garçom e os dois botões.

## A conta vem pronta do service

`PagamentoService.conta_para_pagamento` devolve um `ContaParaPagamento`
imutável (itens, totais, o que já foi pago, a comissão). A tela só mostra e
recalcula o troco na tecla — nenhuma conta de dinheiro nasce aqui, e nenhuma
leitura de `Comanda` acontece durante a pintura (a lição do §9.4: todo commit
expira as instâncias do SQLAlchemy).

## A comissão

O card do garçom aparece quando a conta tem taxa de serviço E atendente
vinculado — sem um dos dois não há repasse a fazer. Os dois botões são um
seletor de status: "Comissão paga" (verde) e "Comissão não paga" (âmbar). O
padrão é **não paga**: nenhum dinheiro sai da gaveta sem alguém dizer que saiu,
e a conta entra na lista de pendentes que o gerente acerta no fim do turno. A
escolha viaja no mesmo commit que fecha a conta (`registrar(...,
comissao_paga=...)`), e é o service que decide se o repasse vira saída de
gaveta — só quando a conta entrou em dinheiro.

## Consumo interno

O card "Consumo" abre o fluxo restrito: PIN do gerente (Nível 2) e a escolha do
funcionário, que é quem fica com o valor no saldo devedor. Quem exige as duas
coisas é o `PagamentoService`; a tela só coleta.

## Ciclo de vida (o RNF do Celeron)

A tela é montada uma vez, no boot, como as outras nove (§3.2) — `carregar()`
troca os dados. As linhas de item são widgets, recriados a cada recarga por
`limpar_layout` (§ layout_utils), e não delegados como o Cardápio (§9.11):
aqui são poucas linhas, elas não rolam e não têm controle dentro; um delegado
custaria mais código do que economiza. Os diálogos que ela abre (PIN, aviso de
impressão) passam por `executar_modal`.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.enums import FormaPagamento
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.formatador_cupom import percentual
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.services.pagamento_service import (
    ComissaoDaConta,
    ContaParaPagamento,
    PagamentoService,
)
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.campo_moeda import CampoMoeda
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_ARQUIVO_TEXTO,
    GLIFO_CARTAO,
    GLIFO_CEDULA,
    GLIFO_CELULAR,
    GLIFO_CIFRAO,
    GLIFO_IMPRESSORA,
    GLIFO_PESSOA,
    GLIFO_VISTO,
    BotaoComGlifo,
    GlifoSolto,
)
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.layout_utils import limpar_layout
from gestor_comercial.ui.widgets.modais import executar_modal
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

# As cinco formas do mockup, na ordem em que aparecem. "Consumo" é o
# CONSUMO_INTERNO de sempre — o vale do funcionário —, renomeado na tela por
# pedido do Vitor: no balcão ninguém chama aquilo de "consumo interno".
FORMAS = (
    (FormaPagamento.DINHEIRO, "Dinheiro", GLIFO_CEDULA),
    (FormaPagamento.PIX, "Pix", GLIFO_CELULAR),
    (FormaPagamento.DEBITO, "Débito", GLIFO_CARTAO),
    (FormaPagamento.CREDITO, "Crédito", GLIFO_CARTAO),
    (FormaPagamento.CONSUMO_INTERNO, "Consumo", GLIFO_PESSOA),
)

# Em quantas pessoas a conta pode ser dividida na tela. Seis é o que cabe numa
# fileira de pílulas na largura do card, e é mesa grande de food truck.
PESSOAS_MAXIMO = 6

# Como o card do garçom abre em toda conta: NÃO PAGA (decisão do Vitor,
# confirmada). Nenhum dinheiro sai da gaveta sem um clique deliberado, e a
# conta entra na lista de pendentes que o gerente acerta no fim do turno.
# Constante, e não dois literais: o valor é lido na montagem da tela E a cada
# conta carregada, e os dois têm que dizer a mesma coisa.
COMISSAO_PAGA_PADRAO = False


class _CartaoForma(QFrame):
    """Um card de forma de pagamento. O card inteiro é o alvo do clique."""

    clicado = Signal(object)

    ALTURA_PX = 44

    def __init__(self, forma: FormaPagamento, rotulo: str, glifo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.forma = forma
        self.setObjectName("pagFormaCard")
        self.setProperty("ativa", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Piso de altura: numa página de 738px o layout espreme o que não cabe,
        # e o Qt para de desenhar o texto quando a caixa fica menor que ele — foi
        # o que a renderização pegou, com os cards virando faixas vazias.
        self.setMinimumHeight(self.ALTURA_PX)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(14, 12, 12, 12)
        linha.setSpacing(10)
        self._glifo = GlifoSolto(glifo, 16, "pagamento_opcao_glifo")
        linha.addWidget(self._glifo, 0, Qt.AlignmentFlag.AlignVCenter)
        self._rotulo = QLabel(rotulo)
        self._rotulo.setObjectName("pagFormaRotulo")
        self._rotulo.setProperty("ativa", False)
        linha.addWidget(self._rotulo, 1)
        self._visto = GlifoSolto(GLIFO_VISTO, 14, "pagamento_opcao_ativa_glifo")
        self._visto.setVisible(False)
        linha.addWidget(self._visto, 0, Qt.AlignmentFlag.AlignVCenter)

    def definir_ativa(self, ativa: bool) -> None:
        if self.property("ativa") == ativa:
            return
        aplicar_propriedade(self, "ativa", ativa)
        aplicar_propriedade(self._rotulo, "ativa", ativa)
        self._glifo.trocar_token(
            "pagamento_opcao_ativa_glifo" if ativa else "pagamento_opcao_glifo"
        )
        self._visto.setVisible(ativa)

    @nao_deixa_escapar()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit(self.forma)
        super().mousePressEvent(event)


class _CartaoComissao(QFrame):
    """"Comissão de [garçom]" com o seletor de status: paga ou não paga.

    Os dois botões são um seletor, e não duas ações: o que estiver aceso é o que
    vai ser gravado quando a conta fechar. Quem grava é o service, no mesmo
    commit do fechamento.
    """

    escolhido = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pagComissaoCard")

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(16, 12, 16, 12)
        coluna.setSpacing(10)

        topo = QHBoxLayout()
        topo.setSpacing(12)
        avatar = QFrame()
        avatar.setObjectName("pagComissaoAvatar")
        avatar.setFixedSize(34, 34)
        dentro = QHBoxLayout(avatar)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(GlifoSolto(GLIFO_PESSOA, 17, "pagamento_avatar_glifo"), 0, Qt.AlignmentFlag.AlignCenter)
        topo.addWidget(avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        self._titulo = QLabel("")
        self._titulo.setObjectName("pagComissaoTitulo")
        textos.addWidget(self._titulo)
        self._detalhe = QLabel("")
        self._detalhe.setObjectName("pagComissaoDetalhe")
        textos.addWidget(self._detalhe)
        topo.addLayout(textos, 1)
        coluna.addLayout(topo)

        botoes = QHBoxLayout()
        botoes.setSpacing(10)
        self.botao_paga = BotaoComGlifo(
            "Comissão paga", GLIFO_VISTO, "pagamento_comissao_paga_texto", "pagamento_comissao_paga_texto"
        )
        self.botao_paga.setObjectName("pagComissaoPaga")
        self.botao_nao_paga = BotaoComGlifo(
            "Comissão não paga",
            GLIFO_CIFRAO,
            "pagamento_comissao_pendente_texto",
            "pagamento_comissao_pendente_texto",
        )
        self.botao_nao_paga.setObjectName("pagComissaoNaoPaga")
        for botao, paga in ((self.botao_paga, True), (self.botao_nao_paga, False)):
            botao.setMinimumHeight(34)
            botao.setProperty("ativa", False)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            botao.setAutoDefault(False)
            botoes.addWidget(botao, 1)
        self.botao_paga.clicked.connect(self._marcar_paga)
        self.botao_nao_paga.clicked.connect(self._marcar_pendente)
        coluna.addLayout(botoes)

    def carregar(self, comissao: ComissaoDaConta, paga: bool) -> None:
        self._titulo.setText(f"Comissão de {comissao.nome}")
        self._detalhe.setText(f"Referente ao serviço · {formatar_reais(comissao.valor)}")
        self.definir(paga)

    def definir(self, paga: bool) -> None:
        for botao, aceso in ((self.botao_paga, paga), (self.botao_nao_paga, not paga)):
            if botao.property("ativa") != aceso:
                aplicar_propriedade(botao, "ativa", aceso)

    def _marcar_paga(self) -> None:
        self.escolhido.emit(True)

    def _marcar_pendente(self) -> None:
        self.escolhido.emit(False)


class PagamentoView(QWidget):
    """Recebimento da conta: consumo à esquerda, pagamento e comissão à direita."""

    voltar = Signal()
    pagamento_concluido = Signal(int)

    def __init__(
        self,
        pagamento_service: PagamentoService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pagamentos = pagamento_service
        self._impressao = impressao_service
        self._auth = pagamento_service.auth
        self._comanda_id: int | None = None
        self._conta: ContaParaPagamento | None = None
        self._forma = FormaPagamento.DINHEIRO
        self._pessoas = 1
        self._comissao_paga = COMISSAO_PAGA_PADRAO

        self._montar_layout()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addLayout(self._montar_cabecalho())

        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        layout.addWidget(self._label_erro)

        self._aviso_impressao = AvisoDeImpressao()
        layout.addWidget(self._aviso_impressao)

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        corpo.addWidget(self._montar_coluna_consumo(), 52)
        corpo.addWidget(self._rolar(self._montar_coluna_registro()), 48)
        layout.addLayout(corpo, 1)

    @staticmethod
    def _rolar(coluna: QWidget) -> QScrollArea:
        """Põe a coluna numa rolagem — ela não cabe inteira em 768px.

        Sem isto o Qt não corta: ELE ESPREME (a lição do §9.1 e da Configurações
        na Fase 7). Medido na renderização com a fonte da marca: os cards de
        forma de pagamento viravam faixas de 20px e o Qt parava de desenhar o
        texto deles — "Dinheiro", "Pix" e "Crédito" simplesmente sumiam da tela.
        """
        rolagem = QScrollArea()
        rolagem.setObjectName("pagColunaRolagem")
        rolagem.setWidget(coluna)
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return rolagem

    def _montar_cabecalho(self) -> QHBoxLayout:
        cabecalho = QHBoxLayout()
        bloco = QVBoxLayout()
        bloco.setSpacing(2)
        self._eyebrow = QLabel("")
        self._eyebrow.setObjectName("pagEyebrow")
        bloco.addWidget(self._eyebrow)
        self._titulo = QLabel("Receber Pagamento")
        self._titulo.setObjectName("pagTitulo")
        bloco.addWidget(self._titulo)
        self._subtitulo = QLabel("")
        self._subtitulo.setObjectName("pagSubtitulo")
        bloco.addWidget(self._subtitulo)
        cabecalho.addLayout(bloco)
        cabecalho.addStretch()

        self._botao_voltar = QPushButton("← Voltar à mesa")
        self._botao_voltar.setProperty("variante", "pilula-voltar")
        self._botao_voltar.clicked.connect(self.voltar.emit)
        cabecalho.addWidget(self._botao_voltar, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._botao_segunda_via = QPushButton("Imprimir 2ª via")
        self._botao_segunda_via.setProperty("variante", "pilula-secundario")
        self._botao_segunda_via.setToolTip("Repete o recibo do cliente desta conta.")
        self._botao_segunda_via.clicked.connect(self._imprimir_recibo)
        cabecalho.addWidget(self._botao_segunda_via, alignment=Qt.AlignmentFlag.AlignVCenter)
        return cabecalho

    def _montar_coluna_consumo(self) -> QWidget:
        cartao = PainelPontilhado()
        cartao.setObjectName("pagCartao")
        coluna = QVBoxLayout(cartao)
        coluna.setContentsMargins(24, 22, 24, 22)
        coluna.setSpacing(14)

        topo = QHBoxLayout()
        textos = QVBoxLayout()
        textos.setSpacing(3)
        self._rotulo_comanda = QLabel("")
        self._rotulo_comanda.setObjectName("pagCartaoRotulo")
        textos.addWidget(self._rotulo_comanda)
        self._titulo_consumo = QLabel("Consumo da mesa")
        self._titulo_consumo.setObjectName("pagCartaoTitulo")
        textos.addWidget(self._titulo_consumo)
        topo.addLayout(textos, 1)
        topo.addWidget(self._badge(GLIFO_ARQUIVO_TEXTO), 0, Qt.AlignmentFlag.AlignTop)
        coluna.addLayout(topo)

        # As linhas de item rolam: uma mesa grande tem mais itens do que cabe
        # na altura útil de um monitor de 768px, e sem rolagem o Qt espreme as
        # linhas em vez de cortar (a lição do §9.1).
        self._itens = QVBoxLayout()
        self._itens.setSpacing(0)
        conteudo = QWidget()
        conteudo.setObjectName("pagListaConteudo")
        dentro = QVBoxLayout(conteudo)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addLayout(self._itens)
        dentro.addStretch()
        rolagem = QScrollArea()
        rolagem.setObjectName("pagListaRolagem")
        rolagem.setWidget(conteudo)
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        coluna.addWidget(rolagem, 1)

        self._linha_subtotal, self._valor_subtotal = self._linha_de_total("Subtotal")
        coluna.addLayout(self._linha_subtotal)
        self._linha_taxa, self._valor_taxa = self._linha_de_total("Serviço")
        self._rotulo_taxa = self._linha_taxa.itemAt(0).widget()
        coluna.addLayout(self._linha_taxa)

        total = QFrame()
        total.setObjectName("pagTotalCard")
        linha_total = QHBoxLayout(total)
        linha_total.setContentsMargins(18, 14, 18, 14)
        rotulo_total = QLabel("Total da conta")
        rotulo_total.setObjectName("pagTotalRotulo")
        linha_total.addWidget(rotulo_total)
        linha_total.addStretch()
        self._valor_total = QLabel("R$ 0,00")
        self._valor_total.setObjectName("pagTotalValor")
        linha_total.addWidget(self._valor_total)
        coluna.addWidget(total)

        linha_pessoa, self._valor_por_pessoa = self._linha_de_total("Por pessoa (1)")
        self._rotulo_por_pessoa = linha_pessoa.itemAt(0).widget()
        coluna.addLayout(linha_pessoa)

        divisao = QHBoxLayout()
        divisao.setSpacing(8)
        rotulo_divisao = QLabel("DIVIDIR POR")
        rotulo_divisao.setObjectName("pagCartaoRotulo")
        divisao.addWidget(rotulo_divisao)
        self._pilulas: list[QPushButton] = []
        for pessoas in range(1, PESSOAS_MAXIMO + 1):
            pilula = QPushButton(str(pessoas))
            pilula.setObjectName("pagPilulaPessoas")
            pilula.setProperty("ativa", pessoas == 1)
            pilula.setFixedSize(30, 30)
            pilula.setCursor(Qt.CursorShape.PointingHandCursor)
            pilula.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            pilula.clicked.connect(lambda _marcado=False, n=pessoas: self._dividir_por(n))
            self._pilulas.append(pilula)
            divisao.addWidget(pilula)
        divisao.addStretch()
        coluna.addLayout(divisao)
        return cartao

    def _montar_coluna_registro(self) -> QWidget:
        cartao = PainelPontilhado()
        cartao.setObjectName("pagCartao")
        coluna = QVBoxLayout(cartao)
        # Margens e espaçamento um degrau menores que os da coluna da esquerda:
        # é o que faz a coluna inteira caber nos 738px úteis de um monitor de
        # 768px sem a barra de rolagem aparecer (medido na renderização).
        coluna.setContentsMargins(22, 18, 22, 18)
        coluna.setSpacing(10)

        topo = QHBoxLayout()
        topo.setSpacing(14)
        topo.addWidget(self._badge(GLIFO_CIFRAO), 0, Qt.AlignmentFlag.AlignTop)
        textos = QVBoxLayout()
        textos.setSpacing(3)
        titulo = QLabel("Registrar pagamento")
        titulo.setObjectName("pagCartaoTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel("Informe o recebimento e a comissão.")
        subtitulo.setObjectName("pagCartaoSubtitulo")
        textos.addWidget(subtitulo)
        topo.addLayout(textos, 1)
        coluna.addLayout(topo)

        coluna.addWidget(self._rotulo_secao("FORMA DE PAGAMENTO"))
        grade = QGridLayout()
        grade.setSpacing(8)
        self._cartoes_forma: dict[FormaPagamento, _CartaoForma] = {}
        for posicao, (forma, rotulo, glifo) in enumerate(FORMAS):
            card = _CartaoForma(forma, rotulo, glifo)
            card.clicado.connect(self._escolher_forma)
            grade.addWidget(card, posicao // 2, posicao % 2)
            self._cartoes_forma[forma] = card
        coluna.addLayout(grade)

        # Só aparece no "Consumo": é quem fica com o valor no saldo devedor.
        self._combo_funcionario = QComboBox()
        self._combo_funcionario.setObjectName("pagFuncionario")
        self._combo_funcionario.setVisible(False)
        coluna.addWidget(self._combo_funcionario)

        coluna.addWidget(self._rotulo_secao("VALOR RECEBIDO"))
        self._campo_valor = CampoMoeda()
        self._campo_valor.setObjectName("pagValorRecebido")
        self._campo_valor.textChanged.connect(self._mostrar_troco)
        coluna.addWidget(self._campo_valor)

        troco = QFrame()
        troco.setObjectName("pagTrocoCard")
        linha_troco = QHBoxLayout(troco)
        linha_troco.setContentsMargins(18, 10, 18, 10)
        rotulo_troco = QLabel("TROCO")
        rotulo_troco.setObjectName("pagCartaoRotulo")
        linha_troco.addWidget(rotulo_troco)
        linha_troco.addStretch()
        self._valor_troco = QLabel("R$ 0,00")
        self._valor_troco.setObjectName("pagTrocoValor")
        linha_troco.addWidget(self._valor_troco)
        coluna.addWidget(troco)

        self._cartao_comissao = _CartaoComissao()
        self._cartao_comissao.escolhido.connect(self._escolher_comissao)
        coluna.addWidget(self._cartao_comissao)

        coluna.addStretch()

        self._botao_registrar = BotaoComGlifo(
            "Registrar pagamento", GLIFO_VISTO, "acento_texto", "pilula_disabled_texto"
        )
        self._botao_registrar.setObjectName("pagBotaoRegistrar")
        self._botao_registrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_registrar.clicked.connect(self._registrar)
        coluna.addWidget(self._botao_registrar)

        self._botao_registrar_imprimir = BotaoComGlifo(
            "Registrar e imprimir comprovante",
            GLIFO_IMPRESSORA,
            "texto",
            "pilula_disabled_texto",
        )
        self._botao_registrar_imprimir.setObjectName("pagBotaoRegistrarImprimir")
        self._botao_registrar_imprimir.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_registrar_imprimir.clicked.connect(self._registrar_e_imprimir)
        coluna.addWidget(self._botao_registrar_imprimir)
        return cartao

    @staticmethod
    def _badge(glifo: str) -> QFrame:
        badge = QFrame()
        badge.setObjectName("pagBadge")
        badge.setFixedSize(38, 38)
        dentro = QHBoxLayout(badge)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(GlifoSolto(glifo, 18, "pagamento_badge_glifo"), 0, Qt.AlignmentFlag.AlignCenter)
        return badge

    @staticmethod
    def _rotulo_secao(texto: str) -> QLabel:
        rotulo = QLabel(texto)
        rotulo.setObjectName("pagCartaoRotulo")
        return rotulo

    @staticmethod
    def _linha_de_total(rotulo: str) -> tuple[QHBoxLayout, QLabel]:
        linha = QHBoxLayout()
        nome = QLabel(rotulo)
        nome.setObjectName("pagResumoRotulo")
        linha.addWidget(nome)
        linha.addStretch()
        valor = QLabel("R$ 0,00")
        valor.setObjectName("pagResumoValor")
        linha.addWidget(valor)
        return linha, valor

    # ------------------------------------------------------------------
    # Carregamento
    # ------------------------------------------------------------------

    def carregar(self, comanda_id: int) -> None:
        """Abre a tela para uma conta — o ponto de entrada da navegação."""
        self._comanda_id = comanda_id
        self._pessoas = 1
        # Conta nova, escolha nova: sem este reset, a comissão marcada como paga
        # numa mesa seguiria marcada na próxima que abrisse.
        self._comissao_paga = COMISSAO_PAGA_PADRAO
        self._aviso_impressao.limpar()
        self._label_erro.setText("")
        self._escolher_forma(FormaPagamento.DINHEIRO)
        self.atualizar()

    def atualizar(self) -> None:
        if self._comanda_id is None:
            return
        self._label_erro.setText("")
        try:
            conta = self._pagamentos.conta_para_pagamento(self._comanda_id)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._conta = conta
        self._popular_funcionarios()

        self._eyebrow.setText(self._identidade())
        self._titulo.setText(f"Receber Pagamento · {conta.origem}")
        garcom = conta.atendente_nome or "sem atendente"
        self._subtitulo.setText(f"Comanda #{conta.comanda_id} · Garçom {garcom}")
        self._rotulo_comanda.setText(f"COMANDA #{conta.comanda_id}")
        self._titulo_consumo.setText(
            "Consumo da mesa" if conta.mesa_numero is not None else "Consumo da comanda"
        )

        self._preencher_itens(conta)
        self._valor_subtotal.setText(formatar_reais(conta.subtotal))
        tem_taxa = conta.valor_taxa > 0
        # `percentual` é o mesmo do cupom e do cartão de conferência: o papel e
        # as duas telas dizem "10%", nunca "10,00%" (o `:g` do Decimal manteria
        # as casas mortas).
        self._rotulo_taxa.setText(
            f"Serviço {percentual(conta.taxa_percentual)}%" if conta.taxa_percentual else "Serviço"
        )
        self._rotulo_taxa.setVisible(tem_taxa)
        self._valor_taxa.setVisible(tem_taxa)
        self._valor_taxa.setText(formatar_reais(conta.valor_taxa))
        self._valor_total.setText(formatar_reais(conta.total))
        self._mostrar_divisao()

        self._cartao_comissao.setVisible(conta.comissao is not None)
        if conta.comissao is not None:
            self._comissao_paga = conta.comissao.paga or self._comissao_paga
            self._cartao_comissao.carregar(conta.comissao, self._comissao_paga)

        # O campo já vem com o que falta receber: no caminho normal o operador
        # só confere e confirma, e o troco aparece quando ele digita mais.
        self._campo_valor.definir_valor(conta.restante)
        self._mostrar_troco()

    def _identidade(self) -> str:
        usuario = self._auth.usuario_logado
        return "" if usuario is None else f"{usuario.perfil.value} · {usuario.nome}".upper()

    def _popular_funcionarios(self) -> None:
        atual = self._combo_funcionario.currentData()
        self._combo_funcionario.blockSignals(True)
        self._combo_funcionario.clear()
        for funcionario in self._pagamentos.funcionarios.listar_ativos():
            self._combo_funcionario.addItem(funcionario.nome, funcionario.id)
        indice = self._combo_funcionario.findData(atual)
        if indice >= 0:
            self._combo_funcionario.setCurrentIndex(indice)
        self._combo_funcionario.blockSignals(False)

    def _preencher_itens(self, conta: ContaParaPagamento) -> None:
        limpar_layout(self._itens)
        for item in conta.itens:
            linha = QFrame()
            linha.setObjectName("pagItemLinha")
            dentro = QHBoxLayout(linha)
            dentro.setContentsMargins(0, 10, 0, 10)
            dentro.setSpacing(8)
            quantidade = QLabel(f"{item.quantidade}×")
            quantidade.setObjectName("pagItemQuantidade")
            dentro.addWidget(quantidade)
            descricao = QLabel(item.descricao)
            descricao.setObjectName("pagItemDescricao")
            dentro.addWidget(descricao, 1)
            valor = QLabel(formatar_reais(item.valor))
            valor.setObjectName("pagItemValor")
            dentro.addWidget(valor)
            self._itens.addWidget(linha)

    # ------------------------------------------------------------------
    # Interação
    # ------------------------------------------------------------------

    def _escolher_forma(self, forma: FormaPagamento) -> None:
        self._forma = forma
        for uma_forma, card in self._cartoes_forma.items():
            card.definir_ativa(uma_forma is forma)
        consumo = forma is FormaPagamento.CONSUMO_INTERNO
        self._combo_funcionario.setVisible(consumo)
        self._mostrar_troco()

    def _dividir_por(self, pessoas: int) -> None:
        self._pessoas = pessoas
        self._mostrar_divisao()

    def _mostrar_divisao(self) -> None:
        """Só mostra quanto dá por pessoa — decisão do Vitor (§9.25).

        O pagamento continua sendo lançado por valor recebido: dividir na tela
        é a conta que o garçom faria no papel antes de falar com a mesa.
        """
        for pilula in self._pilulas:
            ativa = pilula.text() == str(self._pessoas)
            if pilula.property("ativa") != ativa:
                aplicar_propriedade(pilula, "ativa", ativa)
        self._rotulo_por_pessoa.setText(f"Por pessoa ({self._pessoas})")
        if self._conta is not None:
            self._valor_por_pessoa.setText(formatar_reais(self._conta.por_pessoa(self._pessoas)))

    def _escolher_comissao(self, paga: bool) -> None:
        self._comissao_paga = paga
        self._cartao_comissao.definir(paga)

    def _mostrar_troco(self) -> None:
        """O troco ao vivo — a conta que o operador fazia de cabeça.

        Só dinheiro gera troco (é a regra do `PagamentoService`): nas outras
        formas o excedente não é aceito, e mostrar um troco ali prometeria o
        que o registro vai recusar.
        """
        if self._conta is None:
            return
        recebido = self._campo_valor.valor()
        troco = Decimal("0")
        if recebido is not None and self._forma is FormaPagamento.DINHEIRO:
            troco = max(recebido - self._conta.restante, Decimal("0"))
        self._valor_troco.setText(formatar_reais(troco))

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------

    def _registrar(self) -> None:
        self._registrar_pagamento(imprimir=False)

    def _registrar_e_imprimir(self) -> None:
        self._registrar_pagamento(imprimir=True)

    def _registrar_pagamento(self, *, imprimir: bool) -> None:
        if self._comanda_id is None or self._conta is None:
            return
        self._label_erro.setText("")
        self._aviso_impressao.limpar()

        valor = self._campo_valor.valor()
        if valor is None:
            self._label_erro.setText("Informe o valor recebido.")
            return

        pin_gerente = None
        funcionario_id = None
        if self._forma is FormaPagamento.CONSUMO_INTERNO:
            funcionario_id = self._combo_funcionario.currentData()
            if funcionario_id is None:
                self._label_erro.setText("Escolha o funcionário do consumo.")
                return
            pin_gerente = self._pedir_pin_gerente()
            if pin_gerente is None:
                return

        comanda_id = self._comanda_id
        try:
            resumo = self._pagamentos.registrar(
                comanda_id,
                self._forma,
                valor,
                pin_gerente=pin_gerente,
                funcionario_consumo_id=funcionario_id,
                comissao_paga=self._comissao_paga,
            )
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return

        self.atualizar()
        if not resumo.comanda_fechada:
            # Pagamento parcial: a tela continua aberta com o que falta.
            self._label_erro.setText(
                f"Recebido {formatar_reais(resumo.total_pago)}. "
                f"Falta {formatar_reais(resumo.restante)}."
            )
            return

        if imprimir:
            self._imprimir_recibo()
        self.pagamento_concluido.emit(comanda_id)

    def _pedir_pin_gerente(self) -> str | None:
        """O PIN do Nível 2 que autoriza o consumo interno, devolvido para o service.

        O cartão de PIN confere a credencial na hora (é o `validador` dele), e
        esta tela guarda o que passou só para repassar ao `PagamentoService` —
        que reconfere antes de gravar. Quem manda é o service: a tela não
        autoriza nada, só coleta.
        """
        modal = PinPadDialog.para_consumo_interno(self._auth, self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return None
        return modal.pin_confirmado

    def _imprimir_recibo(self) -> None:
        if self._comanda_id is None:
            return
        comanda_id = self._comanda_id
        self._label_erro.setText("")
        try:
            resultado = executar_impressao(lambda: self._impressao.imprimir_recibo(comanda_id))
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._aviso_impressao.mostrar_um(resultado, contexto="Recibo do cliente")
