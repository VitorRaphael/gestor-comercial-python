"""Tela inicial do PDV: grid de mesas + balcão — porte visual de
`.grid-mesas`/`.mesa-card` do front-end web (`GESTOR COMERCIAL/.../desktop/css/style.css`)
e da lógica de `carregarMesas`/`abrirComandaDaMesa`/`abrirComandaBalcao` (`.../desktop/js/app.js`).

Layout "Dark Industrial" (redesign 2026-09): 3 colunas dentro da própria view
(a sidebar de navegação já é do shell) -- coluna central com cabeçalho, pills
de filtro por status e o grid de mesas; painel direito com o resumo
financeiro do salão e a lista de comandas ativas. Tudo calculado a partir dos
mesmos dados de `ComandaService.listar_mesas`, sem endpoint novo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.enums import StatusComanda, StatusMesa
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)

_COLUNAS_GRADE = 8
_ESPACAMENTO = 14

_FILTROS = ("todas", "livres", "ocupadas", "fechando")
_ROTULOS_FILTRO = {"todas": "TODAS", "livres": "LIVRES", "ocupadas": "OCUPADAS", "fechando": "FECHANDO"}
_ROTULOS_TAG = {"livre": "LIVRE", "ocupada": "OCUPADA", "fechando": "FECHANDO"}


def _formatar_reais(valor: Decimal) -> str:
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@dataclass
class _ResumoMesa:
    """Snapshot de uma mesa pronto pra UI: status (`livre`/`ocupada`/`fechando`,
    onde "fechando" é uma comanda ocupada já em `EM_CONFERENCIA`, pré-conta
    emitida) + valor da comanda aberta + quem atende."""

    mesa: Mesa
    status: str
    valor: Decimal
    atendente: str | None
    minutos_espera: int | None


class _CartaoMesa(QFrame):
    """Card clicável de uma mesa. É `QFrame` (não `QPushButton` como antes) porque
    uma mesa ocupada tem 4 linhas com tamanhos/pesos/cores diferentes (número
    grande, tag de status colorida, valor, nome do atendente) — um único texto
    de `QPushButton` não estiliza isso via QSS."""

    clicado = Signal()

    def __init__(self, resumo: _ResumoMesa, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("variante", "mesa")
        self.setProperty("ocupada", "true" if resumo.status != "livre" else "false")
        self.setProperty("fechando", "true" if resumo.status == "fechando" else "false")
        self.setProperty("alerta", "true" if (resumo.minutos_espera or 0) >= 30 else "false")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(96, 96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 12)
        layout.setSpacing(3)

        numero = QLabel(str(resumo.mesa.numero))
        numero.setObjectName("mesaCartaoNumero")
        numero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(numero)

        tag = QLabel(_ROTULOS_TAG[resumo.status])
        tag.setObjectName("mesaCartaoTag")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(tag)

        if resumo.status == "livre":
            layout.addStretch()
        else:
            valor = QLabel(_formatar_reais(resumo.valor))
            valor.setObjectName("mesaCartaoValor")
            valor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(valor)

            if resumo.atendente:
                nome = QLabel(resumo.atendente)
                nome.setObjectName("mesaCartaoNome")
                nome.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(nome)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
        super().mousePressEvent(event)


class _BarraProgresso(QWidget):
    """Barra de ocupação fina: trilho + preenchimento proporcional, ambos
    `QFrame` coloridos via QSS -- mais simples que estilizar um `QProgressBar`
    nativo pra ficar fino e com cantos arredondados como no design."""

    _ALTURA = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self._ALTURA)
        self._trilho = QFrame(self)
        self._trilho.setObjectName("painelBarraTrilho")
        self._preenchida = QFrame(self)
        self._preenchida.setObjectName("painelBarraPreenchida")
        self._percentual = 0.0

    def definir_percentual(self, percentual: float) -> None:
        self._percentual = max(0.0, min(100.0, percentual))
        self._reposicionar()

    def resizeEvent(self, event) -> None:  # noqa: N802 (override Qt)
        super().resizeEvent(event)
        self._reposicionar()

    def _reposicionar(self) -> None:
        self._trilho.setGeometry(0, 0, self.width(), self._ALTURA)
        largura = round(self.width() * self._percentual / 100)
        self._preenchida.setGeometry(0, 0, largura, self._ALTURA)


class MesasView(QWidget):
    """Coluna central (cabeçalho + filtros + grid de mesas) e painel direito
    (resumo do salão + comandas ativas). Emite `comanda_aberta` ao abrir uma."""

    comanda_aberta = Signal(object)

    def __init__(self, comanda_service: ComandaService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._comanda_service = comanda_service
        self._resumos: list[_ResumoMesa] = []
        self._filtro_atual = "todas"

        self._montar_layout()
        self.carregar_mesas()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        layout_raiz = QHBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)
        layout_raiz.setSpacing(20)
        layout_raiz.addLayout(self._montar_coluna_central(), 1)
        layout_raiz.addWidget(self._montar_painel_direito())

    def _montar_coluna_central(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(16)
        coluna.addLayout(self._montar_cabecalho())
        coluna.addLayout(self._montar_filtros())

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px; background: transparent;")
        coluna.addWidget(self._label_erro)

        coluna.addWidget(self._montar_container_grade(), 1)
        return coluna

    def _montar_cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        bloco = QVBoxLayout()
        bloco.setSpacing(2)
        titulo = QLabel("Mesas")
        titulo.setObjectName("mesasTitulo")
        bloco.addWidget(titulo)
        self._label_legenda = QLabel("")
        self._label_legenda.setObjectName("mesasSubtitulo")
        bloco.addWidget(self._label_legenda)
        linha.addLayout(bloco)
        linha.addStretch()

        self._botao_balcao = QPushButton("Balcão")
        self._botao_balcao.setObjectName("btn-balcao")
        self._botao_balcao.setProperty("variante", "secundario")
        self._botao_balcao.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_balcao.clicked.connect(self._abrir_balcao)
        linha.addWidget(self._botao_balcao)

        botao_nova = QPushButton("+  Nova comanda")
        botao_nova.setProperty("variante", "primario")
        botao_nova.setCursor(Qt.CursorShape.PointingHandCursor)
        # Mesma ação de "Balcão" por enquanto: o app só tem um fluxo de
        # comanda sem mesa (ver `ComandaService.abrir_balcao`). O botão
        # próprio existe pra bater com o layout de referência (dois pontos
        # de entrada) e já fica pronto pra divergir no dia em que houver
        # mais de um jeito de abrir uma comanda nova.
        botao_nova.clicked.connect(self._abrir_balcao)
        linha.addWidget(botao_nova)
        return linha

    def _montar_filtros(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(8)
        self._botoes_filtro: dict[str, QPushButton] = {}
        for chave in _FILTROS:
            botao = QPushButton(_ROTULOS_FILTRO[chave])
            botao.setProperty("variante", "filtro-pill")
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.clicked.connect(lambda _checked=False, f=chave: self._selecionar_filtro(f))
            linha.addWidget(botao)
            self._botoes_filtro[chave] = botao
        linha.addStretch()
        return linha

    def _montar_container_grade(self) -> QWidget:
        container = QFrame()
        container.setObjectName("mesasContainer")
        layout_container = QVBoxLayout(container)
        layout_container.setContentsMargins(20, 20, 20, 20)

        self._grade = QGridLayout()
        self._grade.setSpacing(_ESPACAMENTO)

        conteudo_scroll = QWidget()
        conteudo_scroll.setLayout(self._grade)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(conteudo_scroll)
        layout_container.addWidget(scroll)
        return container

    def _montar_painel_direito(self) -> QWidget:
        painel = QWidget()
        painel.setFixedWidth(320)
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._montar_card_resumo())
        layout.addWidget(self._montar_card_comandas(), 1)
        return painel

    def _montar_card_resumo(self) -> QWidget:
        card = QFrame()
        card.setObjectName("painelResumoSalao")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        titulo = QLabel("EM ABERTO NO SALÃO")
        titulo.setObjectName("painelTituloSecao")
        layout.addWidget(titulo)

        self._label_total_aberto = QLabel("R$ 0,00")
        self._label_total_aberto.setObjectName("painelValorGrande")
        layout.addWidget(self._label_total_aberto)
        layout.addSpacing(8)

        linha_ocupacao = QHBoxLayout()
        rotulo_ocupacao = QLabel("OCUPAÇÃO")
        rotulo_ocupacao.setObjectName("painelRotuloMini")
        linha_ocupacao.addWidget(rotulo_ocupacao)
        linha_ocupacao.addStretch()
        self._label_percentual = QLabel("0%")
        self._label_percentual.setObjectName("painelRotuloMini")
        linha_ocupacao.addWidget(self._label_percentual)
        layout.addLayout(linha_ocupacao)

        self._barra_ocupacao = _BarraProgresso()
        layout.addWidget(self._barra_ocupacao)
        layout.addSpacing(12)

        linha_mini = QHBoxLayout()
        linha_mini.setSpacing(8)
        self._mini_stats: dict[str, QLabel] = {}
        for chave, rotulo, dot_object in (
            ("livre", "LIVRE", "painelMiniStatDotLivre"),
            ("ocupada", "OCUPADA", "painelMiniStatDotOcupada"),
            ("fechando", "FECHANDO", "painelMiniStatDotFechando"),
        ):
            frame, valor_label = self._montar_mini_stat(rotulo, dot_object)
            linha_mini.addWidget(frame)
            self._mini_stats[chave] = valor_label
        layout.addLayout(linha_mini)
        return card

    def _montar_mini_stat(self, rotulo: str, dot_object: str) -> tuple[QWidget, QLabel]:
        frame = QFrame()
        frame.setObjectName("painelMiniStat")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        linha_rotulo = QHBoxLayout()
        linha_rotulo.setSpacing(4)
        ponto = QLabel("●")
        ponto.setObjectName(dot_object)
        linha_rotulo.addWidget(ponto)
        texto = QLabel(rotulo)
        texto.setObjectName("painelMiniStatRotulo")
        linha_rotulo.addWidget(texto)
        linha_rotulo.addStretch()
        layout.addLayout(linha_rotulo)

        valor = QLabel("0")
        valor.setObjectName("painelMiniStatValor")
        layout.addWidget(valor)
        return frame, valor

    def _montar_card_comandas(self) -> QWidget:
        card = QFrame()
        card.setObjectName("painelComandasAtivas")
        layout_externo = QVBoxLayout(card)
        layout_externo.setContentsMargins(20, 20, 20, 20)
        layout_externo.setSpacing(10)

        titulo = QLabel("COMANDAS ATIVAS")
        titulo.setObjectName("painelTituloSecao")
        layout_externo.addWidget(titulo)

        self._layout_lista_comandas = QVBoxLayout()
        self._layout_lista_comandas.setSpacing(12)
        self._layout_lista_comandas.addStretch()

        conteudo = QWidget()
        conteudo.setLayout(self._layout_lista_comandas)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(conteudo)
        layout_externo.addWidget(scroll, 1)
        return card

    # ------------------------------------------------------------------
    # Dados
    # ------------------------------------------------------------------

    def carregar_mesas(self) -> None:
        self._resumos = [self._montar_resumo(mesa) for mesa in self._comanda_service.listar_mesas()]
        self._atualizar_legenda()
        self._atualizar_filtros()
        self._atualizar_painel_direito()
        self._reorganizar_grade()

    def _montar_resumo(self, mesa: Mesa) -> _ResumoMesa:
        if mesa.status is not StatusMesa.OCUPADA:
            return _ResumoMesa(mesa=mesa, status="livre", valor=Decimal("0"), atendente=None, minutos_espera=None)

        comanda_aberta = next(
            (c for c in mesa.comandas if c.status in (StatusComanda.ABERTA, StatusComanda.EM_CONFERENCIA)),
            None,
        )
        if comanda_aberta is None:
            # Mesa marcada ocupada sem comanda em aberto não deveria acontecer
            # em operação normal, mas não é motivo pra grade quebrar.
            return _ResumoMesa(mesa=mesa, status="ocupada", valor=Decimal("0"), atendente=None, minutos_espera=None)

        status = "fechando" if comanda_aberta.status is StatusComanda.EM_CONFERENCIA else "ocupada"
        valor = self._comanda_service.calcular_total_a_pagar(comanda_aberta.id)
        atendente = comanda_aberta.atendente.nome if comanda_aberta.atendente else comanda_aberta.usuario.nome

        minutos_espera = None
        # O relógio só corre a partir do primeiro item que a cozinha de fato
        # viu — enquanto o operador ainda está lançando os itens (mesa
        # grande, comanda em rascunho), isso não é atraso nenhum.
        primeiro_envio = ComandaService.hora_primeiro_envio(comanda_aberta.itens)
        if primeiro_envio is not None:
            minutos_espera = int((datetime.now() - primeiro_envio).total_seconds() // 60)

        return _ResumoMesa(mesa=mesa, status=status, valor=valor, atendente=atendente, minutos_espera=minutos_espera)

    def _atualizar_legenda(self) -> None:
        ocupadas = sum(1 for r in self._resumos if r.status != "livre")
        self._label_legenda.setText(f"{len(self._resumos)} mesas · {ocupadas} em atendimento")

    def _atualizar_filtros(self) -> None:
        contagens = {
            "todas": len(self._resumos),
            "livres": sum(1 for r in self._resumos if r.status == "livre"),
            "ocupadas": sum(1 for r in self._resumos if r.status == "ocupada"),
            "fechando": sum(1 for r in self._resumos if r.status == "fechando"),
        }
        for chave, botao in self._botoes_filtro.items():
            botao.setText(f"{_ROTULOS_FILTRO[chave]}  {contagens[chave]}")
            botao.setProperty("ativo", "true" if chave == self._filtro_atual else "false")
            botao.style().unpolish(botao)
            botao.style().polish(botao)

    def _atualizar_painel_direito(self) -> None:
        livres = sum(1 for r in self._resumos if r.status == "livre")
        ocupadas = sum(1 for r in self._resumos if r.status == "ocupada")
        fechando = sum(1 for r in self._resumos if r.status == "fechando")
        total_aberto = sum((r.valor for r in self._resumos if r.status != "livre"), Decimal("0"))

        self._label_total_aberto.setText(_formatar_reais(total_aberto))
        self._mini_stats["livre"].setText(str(livres))
        self._mini_stats["ocupada"].setText(str(ocupadas))
        self._mini_stats["fechando"].setText(str(fechando))

        total_mesas = len(self._resumos) or 1
        percentual = (ocupadas + fechando) / total_mesas * 100
        self._label_percentual.setText(f"{round(percentual)}%")
        self._barra_ocupacao.definir_percentual(percentual)

        self._atualizar_lista_comandas_ativas()

    def _atualizar_lista_comandas_ativas(self) -> None:
        layout = self._layout_lista_comandas
        while layout.count() > 1:  # o último item é o stretch fixo
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        ativas = [r for r in self._resumos if r.status != "livre"]
        for resumo in ativas:
            layout.insertWidget(layout.count() - 1, self._montar_linha_comanda(resumo))

    def _montar_linha_comanda(self, resumo: _ResumoMesa) -> QWidget:
        linha = QWidget()
        layout = QHBoxLayout(linha)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        ponto = QLabel("●")
        ponto.setObjectName("comandaListaPontoFechando" if resumo.status == "fechando" else "comandaListaPontoOcupada")
        layout.addWidget(ponto)

        mesa_label = QLabel(f"Mesa {resumo.mesa.numero}")
        mesa_label.setObjectName("comandaListaMesa")
        layout.addWidget(mesa_label)

        if resumo.atendente:
            nome = QLabel(resumo.atendente)
            nome.setObjectName("comandaListaAtendente")
            layout.addWidget(nome)

        layout.addStretch()

        valor = QLabel(_formatar_reais(resumo.valor))
        valor.setObjectName("comandaListaValor")
        layout.addWidget(valor)
        return linha

    # ------------------------------------------------------------------
    # Filtro + grade
    # ------------------------------------------------------------------

    def _selecionar_filtro(self, filtro: str) -> None:
        self._filtro_atual = filtro
        self._atualizar_filtros()
        self._reorganizar_grade()

    def _resumos_filtrados(self) -> list[_ResumoMesa]:
        if self._filtro_atual == "livres":
            return [r for r in self._resumos if r.status == "livre"]
        if self._filtro_atual == "ocupadas":
            return [r for r in self._resumos if r.status == "ocupada"]
        if self._filtro_atual == "fechando":
            return [r for r in self._resumos if r.status == "fechando"]
        return self._resumos

    def _reorganizar_grade(self) -> None:
        while self._grade.count():
            item = self._grade.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for indice, resumo in enumerate(self._resumos_filtrados()):
            linha, coluna = divmod(indice, _COLUNAS_GRADE)
            cartao = _CartaoMesa(resumo)
            cartao.clicado.connect(lambda m=resumo.mesa: self._abrir_mesa(m))
            self._grade.addWidget(cartao, linha, coluna)

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------

    def _abrir_mesa(self, mesa: Mesa) -> None:
        self._label_erro.setText("")
        try:
            comanda = self._comanda_service.abrir_por_mesa(mesa.id)
        except (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError) as erro:
            self._label_erro.setText(str(erro))
            return
        self.carregar_mesas()
        self.comanda_aberta.emit(comanda)

    def _abrir_balcao(self) -> None:
        self._label_erro.setText("")
        try:
            comanda = self._comanda_service.abrir_balcao()
        except (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError) as erro:
            self._label_erro.setText(str(erro))
            return
        self.comanda_aberta.emit(comanda)
