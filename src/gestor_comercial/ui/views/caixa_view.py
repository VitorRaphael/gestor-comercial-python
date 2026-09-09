"""Caixa do dia: status, abertura/fechamento e movimentos da gaveta — dashboard
financeiro operacional do turno, no estilo "Dark Industrial / Concreto" do
resto do shell (`ui/theme/qss_app.py`).

Sangria/reforço/despesa e o próprio abrir/fechar exigem gerente logado —
quem barra isso é `CaixaService` (via `AuthService.exigir_gerente`), então
aqui só se mostra o erro que o service levantar.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.enums import FormaPagamento, TipoMovimento
from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.services.caixa_service import (
    CaixaService,
    ResumoCaixa,
    periodo_do_turno,
)
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.abertura_caixa_dialog import AberturaCaixaDialog
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.fechamento_caixa_dialog import FechamentoCaixaDialog
from gestor_comercial.ui.widgets.layout_utils import limpar_layout
from gestor_comercial.ui.widgets.modais import executar_modal
from gestor_comercial.ui.widgets.movimentacao_caixa_dialog import (
    OPERACOES,
    MovimentacaoCaixaDialog,
    papel_do_movimento,
    rotulo_do_movimento,
)
from gestor_comercial.ui.widgets.secao_cancelamentos import SecaoCancelamentos
from gestor_comercial.ui.widgets.estilo import repolir
from gestor_comercial.ui.widgets.tabelas import definir_celula, limpar_tabela

_COLUNAS_MOVIMENTOS = ["Quando", "Tipo", "Descrição", "Valor"]

# O rótulo do tipo ("Sangria") e a chave de estilo do badge ("sangria") moram
# em `movimentacao_caixa_dialog.OPERACOES`, junto do título, do subtítulo e das
# sugestões de descrição do modal que grava o movimento. Eram três dicionários
# paralelos aqui dentro, e "Reforço" precisava estar certo nos três ao mesmo
# tempo — mesmo remédio que o §9.5 aplicou em `CARGOS`.

# Largura da coluna de resumo (saldo, recebimentos e ajustes). Vive aqui porque
# são dois donos: o cartão de saldo, que dita a largura dos três, e a rolagem
# que os envolve — sem os mesmos limites nos dois, a coluna muda de tamanho.
_LARGURA_MIN_RESUMO = 340
_LARGURA_MAX_RESUMO = 400

# Formas de recebimento mostradas no card "Recebimentos", nesta ordem.
_FORMAS_RECEBIMENTO = [
    (FormaPagamento.DINHEIRO, "Dinheiro"),
    (FormaPagamento.DEBITO, "Débito"),
    (FormaPagamento.CREDITO, "Crédito"),
    (FormaPagamento.PIX, "Pix"),
]

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

def _cor_texto() -> QColor:
    return QColor(ThemeController.instancia().tokens_atuais["texto"])


def _cor_perigo() -> QColor:
    return QColor(ThemeController.instancia().tokens_atuais["perigo"])


class CaixaView(QWidget):
    """Status do caixa, abertura/fechamento, movimentos da gaveta e conferência."""

    def __init__(
        self,
        caixa_service: CaixaService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._caixa_service = caixa_service
        self._impressao_service = impressao_service
        self._caixa_id: int | None = None
        # Guarda o último caixa conhecido mesmo depois de fechado: o relatório
        # de fechamento é justamente o papel que some ou borra na hora errada,
        # e sem isto o gerente perderia a reimpressão no instante em que fechou.
        self._ultimo_caixa_id: int | None = None

        self._montar_layout()
        self.atualizar()

    # ------------------------------------------------------------------
    # Montagem do layout
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)
        layout_externo.setSpacing(16)

        layout_externo.addLayout(self._montar_cabecalho())

        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        layout_externo.addWidget(self._label_erro)

        self._aviso_impressao = AvisoDeImpressao()
        layout_externo.addWidget(self._aviso_impressao)

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        corpo.addWidget(self._montar_coluna_esquerda(), 0)
        corpo.addLayout(self._montar_coluna_direita(), 1)
        layout_externo.addLayout(corpo, 1)

    def _montar_cabecalho(self) -> QHBoxLayout:
        cabecalho = QHBoxLayout()

        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        self._label_eyebrow = QLabel("GERENTE")
        self._label_eyebrow.setObjectName("caixaEyebrow")
        bloco_titulo.addWidget(self._label_eyebrow)

        self._label_titulo = QLabel("Caixa")
        self._label_titulo.setObjectName("caixaTitulo")
        bloco_titulo.addWidget(self._label_titulo)

        self._label_subtitulo = QLabel("")
        self._label_subtitulo.setObjectName("caixaSubtitulo")
        bloco_titulo.addWidget(self._label_subtitulo)

        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch()

        self._botao_abrir = QPushButton("Abrir caixa")
        self._botao_abrir.setProperty("variante", "primario")
        self._botao_abrir.clicked.connect(self._abrir_caixa)
        cabecalho.addWidget(self._botao_abrir, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._botao_imprimir = QPushButton("Imprimir fechamento")
        self._botao_imprimir.setProperty("variante", "pilula-vazia")
        self._botao_imprimir.setToolTip(
            "Relatório de conferência da gaveta. Funciona com o caixa ainda aberto."
        )
        self._botao_imprimir.clicked.connect(self._imprimir_fechamento)
        cabecalho.addWidget(self._botao_imprimir, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._botao_fechar = QPushButton("Fechar caixa")
        self._botao_fechar.setProperty("variante", "pilula-perigo")
        self._botao_fechar.clicked.connect(self._fechar_caixa)
        cabecalho.addWidget(self._botao_fechar, alignment=Qt.AlignmentFlag.AlignVCenter)
        return cabecalho

    def _montar_coluna_esquerda(self) -> QScrollArea:
        """Resumo do turno (saldo, recebimentos, ajustes), dentro de uma rolagem.

        Os três cartões somam altura fixa e, num monitor de 768px — a máquina do
        food truck —, pedem mais do que a página oferece. Um `QVBoxLayout` sem
        rolagem, nesse caso, **não corta: espreme**, e as linhas de
        "Recebimentos" saíam com 6px de 16px, cortadas ao meio. É o mesmo
        defeito que a Fase 7 encontrou na Configurações, com o mesmo remédio.

        A coluna da direita fica de fora de propósito: lá quem cede altura é a
        tabela de movimentos, que já rola sozinha — envolver as duas criaria
        rolagem dentro de rolagem.
        """
        conteudo = QWidget()
        conteudo.setObjectName("caixaResumoConteudo")
        coluna = QVBoxLayout(conteudo)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(16)

        coluna.addWidget(self._montar_card_saldo())
        coluna.addWidget(self._montar_card_recebimentos())
        coluna.addWidget(self._montar_card_ajustes())
        coluna.addStretch()

        rolagem = QScrollArea()
        rolagem.setObjectName("caixaRolagemResumo")
        rolagem.setWidget(conteudo)
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # A largura da coluna era ditada pelos limites do cartão de saldo; a
        # rolagem no meio interrompe essa herança, então ela repete os mesmos
        # limites — mais a largura da própria barra. Sem essa reserva o viewport
        # nasce menor que o mínimo do cartão (326 contra 340 medidos aqui) e,
        # com a barra horizontal desligada, a lateral direita do cartão é
        # cortada: troca-se um corte por outro.
        barra = rolagem.verticalScrollBar().sizeHint().width()
        rolagem.setMinimumWidth(_LARGURA_MIN_RESUMO + barra)
        rolagem.setMaximumWidth(_LARGURA_MAX_RESUMO + barra)
        return rolagem

    def _montar_card_saldo(self) -> QFrame:
        card, layout = _criar_card()
        card.setMinimumWidth(_LARGURA_MIN_RESUMO)
        card.setMaximumWidth(_LARGURA_MAX_RESUMO)

        layout.addWidget(_rotulo_card("SALDO ESPERADO NA GAVETA"))

        self._label_saldo = QLabel("R$ 0,00")
        self._label_saldo.setObjectName("caixaValorGrande")
        layout.addWidget(self._label_saldo)

        grid_mini = QHBoxLayout()
        grid_mini.setSpacing(10)
        self._mini_recebido, self._label_recebido = _criar_mini_stat("RECEBIDO")
        self._mini_comandas, self._label_comandas = _criar_mini_stat("COMANDAS")
        grid_mini.addWidget(self._mini_recebido)
        grid_mini.addWidget(self._mini_comandas)
        layout.addLayout(grid_mini)
        return card

    def _montar_card_recebimentos(self) -> QFrame:
        card, layout = _criar_card()
        layout.addWidget(_rotulo_card("RECEBIMENTOS"))

        self._barras_forma: dict[FormaPagamento, tuple[QLabel, QProgressBar]] = {}
        for forma, rotulo in _FORMAS_RECEBIMENTO:
            linha = QHBoxLayout()
            nome = QLabel(rotulo)
            nome.setObjectName("caixaFormaNome")
            valor = QLabel("R$ 0,00")
            valor.setObjectName("caixaFormaValor")
            linha.addWidget(nome)
            linha.addStretch()
            linha.addWidget(valor)
            layout.addLayout(linha)

            barra = QProgressBar()
            barra.setObjectName("caixaBarraPagamento")
            barra.setRange(0, 100)
            barra.setValue(0)
            barra.setTextVisible(False)
            layout.addWidget(barra)

            self._barras_forma[forma] = (valor, barra)
        return card

    def _montar_card_ajustes(self) -> QFrame:
        card, layout = _criar_card()
        layout.addWidget(_rotulo_card("AJUSTES DO TURNO"))

        self._labels_ajuste: dict[str, QLabel] = {}
        for chave, rotulo in (
            ("abertura", "Abertura"),
            ("reforcos", "Reforços"),
            ("sangrias", "Sangrias"),
            ("despesas", "Despesas"),
            ("consumo_interno", "Consumo interno"),
        ):
            linha = QHBoxLayout()
            nome = QLabel(rotulo)
            nome.setObjectName("caixaAjusteRotulo")
            valor = QLabel("R$ 0,00")
            valor.setObjectName("caixaAjusteValor")
            linha.addWidget(nome)
            linha.addStretch()
            linha.addWidget(valor)
            layout.addLayout(linha)
            self._labels_ajuste[chave] = valor
        return card

    def _montar_coluna_direita(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(16)
        coluna.addWidget(self._montar_card_movimentos(), 1)

        rodape = QHBoxLayout()
        rodape.setSpacing(16)
        rodape.addWidget(self._montar_card_cancelamentos(), 1)
        rodape.addWidget(self._montar_card_fechamentos(), 1)
        coluna.addLayout(rodape)
        return coluna

    def _montar_card_movimentos(self) -> QFrame:
        card = QFrame()
        card.setObjectName("caixaMovimentosCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        topo = QHBoxLayout()
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        titulo = QLabel("Movimentos")
        titulo.setObjectName("caixaMovimentosTitulo")
        subtitulo = QLabel("Sangrias, reforços e despesas do turno atual.")
        subtitulo.setObjectName("caixaMovimentosSubtitulo")
        bloco_titulo.addWidget(titulo)
        bloco_titulo.addWidget(subtitulo)
        topo.addLayout(bloco_titulo)
        topo.addStretch()

        # A ordem e o conjunto dos botões saem de `OPERACOES`, e não de uma
        # tupla escrita aqui: movimentação manual nova entra num lugar só e
        # ganha botão, modal e badge de uma vez.
        self._botoes_movimento_por_tipo: dict[TipoMovimento, QPushButton] = {}
        _VARIANTE_BOTAO_MOVIMENTO = {TipoMovimento.SANGRIA: "enviar-pedido"}
        for tipo, operacao in OPERACOES.items():
            botao = QPushButton(f"+ {operacao.titulo}")
            botao.setProperty("variante", _VARIANTE_BOTAO_MOVIMENTO.get(tipo, "pilula-vazia"))
            botao.clicked.connect(lambda _checked=False, t=tipo: self._abrir_modal_movimento(t))
            self._botoes_movimento_por_tipo[tipo] = botao
            topo.addWidget(botao)
        layout.addLayout(topo)

        self._tabela = QTableWidget(0, len(_COLUNAS_MOVIMENTOS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS_MOVIMENTOS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tabela)
        return card

    def _montar_card_cancelamentos(self) -> QFrame:
        card, layout = _criar_card()
        self._secao_cancelamentos = SecaoCancelamentos()
        layout.addWidget(self._secao_cancelamentos)
        return card

    def _montar_card_fechamentos(self) -> QFrame:
        card, layout = _criar_card()
        titulo = QLabel("Últimos fechamentos")
        titulo.setStyleSheet("font-weight: 600; font-size: 15px;")
        layout.addWidget(titulo)

        self._layout_fechamentos = QVBoxLayout()
        self._layout_fechamentos.setSpacing(8)
        layout.addLayout(self._layout_fechamentos)
        layout.addStretch()
        return card

    # ------------------------------------------------------------------
    # Atualização de dados
    # ------------------------------------------------------------------

    def atualizar(self) -> None:
        self._label_erro.setText("")
        self._aviso_impressao.limpar()
        try:
            caixa = self._caixa_service.buscar_aberto()
        except RegraDeNegocioError:
            self._caixa_id = None
            self._label_titulo.setText("Caixa — fechado")
            self._label_subtitulo.setText("Nenhum caixa aberto. Abra o caixa para começar o dia.")
            limpar_tabela(self._tabela)
            self._definir_acoes_disponiveis(caixa_aberto=False)
            self._atualizar_fechamentos()
            return

        self._caixa_id = caixa.id
        self._ultimo_caixa_id = caixa.id
        self._label_titulo.setText(self._caixa_service.identificacao_turno(caixa))
        self._label_subtitulo.setText(
            f"Aberto às {caixa.aberto_em:%H:%M}"
            + (f" por {caixa.aberto_por.nome}" if caixa.aberto_por else "")
        )
        self._definir_acoes_disponiveis(caixa_aberto=True)
        self._atualizar_resumo()
        self._atualizar_movimentos()
        self._atualizar_cancelamentos()
        self._atualizar_fechamentos()

    def _definir_acoes_disponiveis(self, *, caixa_aberto: bool) -> None:
        self._botao_abrir.setVisible(not caixa_aberto)
        self._botao_fechar.setEnabled(caixa_aberto)
        # Reimprimir o relatório do caixa recém-fechado continua valendo, então
        # este botão segue o último caixa conhecido, não o que está aberto.
        self._botao_imprimir.setEnabled(self._ultimo_caixa_id is not None)
        for botao in self._botoes_movimento_por_tipo.values():
            botao.setEnabled(caixa_aberto)

    def _atualizar_resumo(self) -> None:
        if self._caixa_id is None:
            return
        resumo = self._caixa_service.resumo(self._caixa_id)
        self._preencher_card_saldo(resumo)
        self._preencher_card_recebimentos(resumo)
        self._preencher_card_ajustes(resumo)

    def _preencher_card_saldo(self, resumo: ResumoCaixa) -> None:
        self._label_saldo.setText(formatar_reais(resumo.saldo_esperado))
        total_recebido = resumo.total_dinheiro + resumo.total_maquininha
        self._label_recebido.setText(formatar_reais(total_recebido))
        self._label_comandas.setText(str(resumo.quantidade_comandas))

    def _preencher_card_recebimentos(self, resumo: ResumoCaixa) -> None:
        totais_forma = self._caixa_service.totais_por_forma(self._caixa_id)
        valores: dict[FormaPagamento, Decimal] = {
            FormaPagamento.DINHEIRO: resumo.total_dinheiro,
            FormaPagamento.DEBITO: totais_forma.get(FormaPagamento.DEBITO, Decimal("0")),
            FormaPagamento.CREDITO: totais_forma.get(FormaPagamento.CREDITO, Decimal("0")),
            FormaPagamento.PIX: totais_forma.get(FormaPagamento.PIX, Decimal("0")),
        }
        maior = max(valores.values(), default=Decimal("0"))
        for forma, _rotulo in _FORMAS_RECEBIMENTO:
            valor = valores[forma]
            label_valor, barra = self._barras_forma[forma]
            label_valor.setText(formatar_reais(valor))
            percentual = int((valor / maior) * 100) if maior > 0 else 0
            barra.setValue(percentual)

    def _preencher_card_ajustes(self, resumo: ResumoCaixa) -> None:
        self._definir_valor_ajuste("abertura", resumo.valor_abertura, negativo=False)
        self._definir_valor_ajuste("reforcos", resumo.reforcos, negativo=False)
        self._definir_valor_ajuste("sangrias", resumo.sangrias, negativo=True)
        self._definir_valor_ajuste("despesas", resumo.despesas, negativo=True)
        self._definir_valor_ajuste("consumo_interno", resumo.total_consumo_interno, negativo=True)

    def _definir_valor_ajuste(self, chave: str, valor: Decimal, *, negativo: bool) -> None:
        label = self._labels_ajuste[chave]
        label.setObjectName("caixaAjusteValorNegativo" if negativo else "caixaAjusteValor")
        prefixo = "-" if negativo and valor != 0 else ""
        label.setText(f"{prefixo}{formatar_reais(valor)}")
        repolir(label)

    def _atualizar_movimentos(self) -> None:
        if self._caixa_id is None:
            return
        movimentos = self._caixa_service.listar_movimentos(self._caixa_id)
        limpar_tabela(self._tabela, linhas=len(movimentos))
        for linha, movimento in enumerate(movimentos):
            self._preencher_linha(linha, movimento)

    def _atualizar_cancelamentos(self) -> None:
        if self._caixa_id is None:
            return
        self._secao_cancelamentos.carregar(
            self._caixa_service.resumo_cancelamentos(self._caixa_id)
        )

    def _atualizar_fechamentos(self) -> None:
        limpar_layout(self._layout_fechamentos)
        try:
            historico = self._caixa_service.listar_historico()
        except _ERROS_SERVICE:
            historico = []

        if not historico:
            vazio = QLabel("Nenhum fechamento registrado ainda.")
            vazio.setProperty("variante", "fraco")
            self._layout_fechamentos.addWidget(vazio)
            return

        for caixa in historico[:3]:
            self._layout_fechamentos.addWidget(self._criar_item_fechamento(caixa))

    def _criar_item_fechamento(self, caixa: Caixa) -> QFrame:
        item = QFrame()
        item.setObjectName("caixaMiniCard")
        layout = QHBoxLayout(item)
        layout.setContentsMargins(12, 10, 12, 10)

        bloco_esquerda = QVBoxLayout()
        bloco_esquerda.setSpacing(2)
        identificacao = QLabel(f"T{caixa.numero_sequencial_dia} · #{caixa.id}")
        identificacao.setObjectName("caixaMiniCardTitulo")
        operador = caixa.fechado_por.nome if caixa.fechado_por else "—"
        data_hora = caixa.fechado_em.strftime("%d/%m") if caixa.fechado_em else "—"
        metadados = QLabel(f"{data_hora} · {operador.upper()}")
        metadados.setObjectName("caixaMiniCardSub")
        bloco_esquerda.addWidget(identificacao)
        bloco_esquerda.addWidget(metadados)
        layout.addLayout(bloco_esquerda)
        layout.addStretch()

        bloco_direita = QVBoxLayout()
        bloco_direita.setSpacing(2)
        resumo = self._caixa_service.resumo(caixa.id)
        total_faturado = resumo.total_dinheiro + resumo.total_maquininha + resumo.total_consumo_interno
        valor = QLabel(formatar_reais(total_faturado))
        valor.setObjectName("caixaMiniCardTitulo")
        valor.setAlignment(Qt.AlignmentFlag.AlignRight)
        bloco_direita.addWidget(valor)

        diferenca = resumo.diferenca_total
        status = QLabel(self._texto_status_diferenca(diferenca))
        status.setObjectName(
            "caixaMiniCardValorNeutro" if diferenca is None
            else "caixaMiniCardValorPositivo" if diferenca >= 0
            else "caixaMiniCardValorNegativo"
        )
        status.setAlignment(Qt.AlignmentFlag.AlignRight)
        bloco_direita.addWidget(status)
        layout.addLayout(bloco_direita)
        return item

    @staticmethod
    def _texto_status_diferenca(diferenca: Decimal | None) -> str:
        if diferenca is None:
            return "—"
        if diferenca == 0:
            return "sem diferença"
        return formatar_reais(diferenca)

    def _preencher_linha(self, linha: int, movimento: MovimentoCaixa) -> None:
        quando = movimento.registrado_em.strftime("%d/%m %H:%M")
        tipo_texto = rotulo_do_movimento(movimento.tipo)

        self._tabela.setItem(linha, 0, QTableWidgetItem(quando))
        definir_celula(
            self._tabela, linha, 1, _criar_badge_movimento(movimento.tipo, tipo_texto)
        )
        self._tabela.setItem(linha, 2, QTableWidgetItem(movimento.descricao or ""))

        sai_da_gaveta = movimento.tipo in (TipoMovimento.SANGRIA, TipoMovimento.DESPESA)
        prefixo = "- " if sai_da_gaveta else ""
        item_valor = QTableWidgetItem(f"{prefixo}{formatar_reais(movimento.valor)}")
        item_valor.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        item_valor.setForeground(_cor_perigo() if sai_da_gaveta else _cor_texto())
        self._tabela.setItem(linha, 3, item_valor)

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------

    def _abrir_caixa(self) -> None:
        """Abre o cartão do fundo de troco e manda ao service o que ele devolver.

        Quem decide se PODE continua sendo o service: abertura exige gerente
        (§3.1), valor negativo é recusado lá e turno anterior esquecido levanta
        `TurnoAnteriorPendenteError` (§3.13) — todos aparecem na linha de erro
        da tela, como antes. O que sumiu deste caminho foi a checagem de "valor
        ilegível": o modal monta o valor em centavos pelo numpad, e não há mais
        texto para `safe_decimal` recusar.
        """
        modal = AberturaCaixaDialog(self._turno_a_abrir(), self._nome_do_operador(), self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        dados = modal.resultado()

        self._label_erro.setText("")
        try:
            self._caixa_service.abrir(dados.valor, observacao=dados.observacao)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()

    def _turno_a_abrir(self) -> str:
        """"Turno da Noite" — o turno que está prestes a começar.

        Deriva de `periodo_do_turno`, a mesma heurística de hora que
        `identificacao_turno` usa para nomear um turno já existente (§3.1). Não
        dá para chamar `identificacao_turno` aqui porque ela recebe um `Caixa`,
        e neste ponto ele ainda não existe — é justamente o que o modal vai
        criar.
        """
        return f"Turno da {periodo_do_turno(datetime.now())}"

    def _fechar_caixa(self) -> None:
        """Abre o cartão de conferência e fecha o turno com o que ele devolver.

        O `resumo` é lido ANTES de abrir o modal porque é dele que saem os dois
        esperados que o operador confere (saldo da gaveta e total da
        maquininha). É leitura, não gravação: quem apura de verdade continua
        sendo o service, que recalcula tudo dentro de `fechar` — a prévia da
        diferença que o modal mostra é conferência visual, não a conta gravada.
        """
        if self._caixa_id is None:
            return
        resumo = self._caixa_service.resumo(self._caixa_id)
        modal = FechamentoCaixaDialog(resumo.saldo_esperado, resumo.total_maquininha, self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        dados = modal.resultado()

        self._label_erro.setText("")
        try:
            self._caixa_service.fechar(
                self._caixa_id, dados.dinheiro, dados.maquininha, dados.observacao
            )
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self.atualizar()
        # O relatório sai sozinho no fim do turno — é o momento em que o gerente
        # confere a gaveta, e esperar que ele lembre de clicar em Imprimir depois
        # de o caixa já estar fechado é pedir para o papel nunca sair. Vem DEPOIS
        # do `fechar` porque impressão não pode, em hipótese alguma, impedir o
        # fechamento: se falhar, vira aviso na tela e o caixa continua fechado.
        self._imprimir_fechamento()

    def _imprimir_fechamento(self) -> None:
        """Relatório de conferência da gaveta, na impressora padrão."""
        caixa_id = self._ultimo_caixa_id
        if caixa_id is None:
            return

        try:
            resultado = executar_impressao(
                lambda: self._impressao_service.imprimir_fechamento_caixa(caixa_id)
            )
        except _ERROS_SERVICE as erro:
            # Impressora quebrada volta em `resultado`; aqui só chega caixa
            # inexistente ou sessão perdida.
            self._label_erro.setText(str(erro))
            return
        self._aviso_impressao.mostrar_um(resultado, contexto="Fechamento de caixa")

    def _abrir_modal_movimento(self, tipo: TipoMovimento) -> None:
        """Abre o cartão de sangria/reforço/despesa e grava o que ele devolver.

        Quem decide se PODE continua sendo o service: sangria e despesa exigem
        gerente (§3.1) e valor zero é recusado lá. O modal só não deixa o
        gerente chegar até aqui com R$ 0,00 — o botão nasce desligado —, e por
        isso a checagem de "valor ilegível" que o campo de texto antigo exigia
        não existe mais neste caminho.
        """
        modal = MovimentacaoCaixaDialog(tipo, self._nome_do_operador(), self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        dados = modal.resultado()

        self._label_erro.setText("")
        try:
            self._caixa_service.registrar_movimento(tipo, dados.valor, dados.descricao)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_resumo()
        self._atualizar_movimentos()

    def _nome_do_operador(self) -> str | None:
        """Quem está logado, para o rodapé do modal — `None` quando ninguém está.

        Lê a sessão em memória (`AuthService.usuario_logado`), e não
        `usuario_atual()`, porque este é um rótulo de tela: sem sessão ele mostra
        um travessão, enquanto `usuario_atual()` levantaria `NaoAutorizadoError`
        e o modal nem abriria. Quem tem que barrar a ação sem login é o service,
        na hora de gravar.
        """
        usuario = self._caixa_service.auth.usuario_logado
        return usuario.nome if usuario is not None else None


def _criar_card() -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("caixaCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(10)
    return card, layout


def _rotulo_card(texto: str) -> QLabel:
    rotulo = QLabel(texto)
    rotulo.setObjectName("caixaCardRotulo")
    return rotulo


def _criar_mini_stat(rotulo_texto: str) -> tuple[QFrame, QLabel]:
    mini = QFrame()
    mini.setObjectName("caixaMiniStat")
    layout = QVBoxLayout(mini)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(2)

    rotulo = QLabel(rotulo_texto)
    rotulo.setObjectName("caixaMiniStatRotulo")
    layout.addWidget(rotulo)

    valor = QLabel("R$ 0,00")
    valor.setObjectName("caixaMiniStatValor")
    layout.addWidget(valor)
    return mini, valor


def _criar_badge_movimento(tipo: TipoMovimento, texto: str) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)

    badge = QLabel(texto.upper())
    badge.setProperty("variante", "badgeMovimento")
    badge.setProperty("tipo", papel_do_movimento(tipo))
    layout.addWidget(badge)
    layout.addStretch()
    return container
