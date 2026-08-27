"""Detalhe da comanda: lista de itens + total, modal de adicionar item,
cancelamento de item/comanda com PIN de gerente — porte visual de
`.comanda-detalhe`/`.tabela` e dos modais `+ Item`/`Cancelar` do front-end
web (`GESTOR COMERCIAL/.../desktop/index.html` + `js/app.js`).

Não conhece `PagamentoDialog` nem navegação: emite `pagamento_solicitado`,
`voltar` e `comanda_cancelada` e deixa a janela principal decidir o que
fazer com cada um (o mesmo padrão de `MesasView.comanda_aberta`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import StatusComanda
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.views.cancelamento_dialog import CancelamentoDialog
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.busca_produto import BuscaProdutoWidget

_COLUNAS = ["Descrição", "Preço", "Qtd", "Total", ""]
# Largura suficiente para "Cancelar" em negrito 13px + padding do botão
# (ver `QPushButton[variante="perigo"]` em resources/qss/base.qss).
_LARGURA_COLUNA_ACAO = 110
_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_NADA_NOVO_PARA_IMPRIMIR = (
    "Nada novo para a produção: todos os itens desta comanda já foram enviados. "
    "Use '2ª via' para repetir o cupom inteiro."
)


class ComandaView(QWidget):
    """Lista de itens de uma comanda, com total, lançamento e cancelamento."""

    voltar = Signal()
    pagamento_solicitado = Signal(int)
    comanda_cancelada = Signal(int)

    def __init__(
        self,
        comanda_service: ComandaService,
        cardapio_service: CardapioService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._comanda_service = comanda_service
        self._cardapio_service = cardapio_service
        self._impressao_service = impressao_service
        self._comanda: Comanda | None = None

        self._montar_layout()

    def _montar_layout(self) -> None:
        layout_externo = QVBoxLayout(self)

        cabecalho = QHBoxLayout()

        self._botao_voltar = QPushButton("← Mesas")
        self._botao_voltar.setProperty("variante", "secundario")
        self._botao_voltar.clicked.connect(self._voltar_clicado)
        cabecalho.addWidget(self._botao_voltar)

        self._label_titulo = QLabel("")
        self._label_titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        cabecalho.addWidget(self._label_titulo)

        self._label_horario = QLabel("")
        self._label_horario.setStyleSheet("font-size: 13px; margin-left: 8px;")
        cabecalho.addWidget(self._label_horario)
        cabecalho.addStretch()

        self._botao_add_item = QPushButton("+ Item")
        self._botao_add_item.setProperty("variante", "secundario")
        self._botao_add_item.clicked.connect(self._abrir_modal_adicionar_item)
        cabecalho.addWidget(self._botao_add_item)

        self._botao_segunda_via = QPushButton("2ª via")
        self._botao_segunda_via.setProperty("variante", "secundario")
        self._botao_segunda_via.setToolTip("Repete a comanda inteira, para cupom rasgado ou perdido.")
        self._botao_segunda_via.clicked.connect(self._imprimir_segunda_via)
        cabecalho.addWidget(self._botao_segunda_via)

        self._botao_pagamento = QPushButton("Receber pagamento")
        self._botao_pagamento.setProperty("variante", "primario")
        self._botao_pagamento.clicked.connect(self._solicitar_pagamento)
        cabecalho.addWidget(self._botao_pagamento)

        self._botao_cancelar_comanda = QPushButton("Cancelar comanda")
        self._botao_cancelar_comanda.setProperty("variante", "perigo")
        self._botao_cancelar_comanda.clicked.connect(self._cancelar_comanda)
        cabecalho.addWidget(self._botao_cancelar_comanda)
        layout_externo.addLayout(cabecalho)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout_externo.addWidget(self._label_erro)

        self._aviso_impressao = AvisoDeImpressao()
        layout_externo.addWidget(self._aviso_impressao)

        # ---------- Seção "Pendentes de Envio" ----------
        self._secao_pendentes = QFrame()
        self._secao_pendentes.setObjectName("secao-pendentes")
        layout_pendentes = QVBoxLayout(self._secao_pendentes)

        titulo_pendentes = QLabel("Itens Pendentes de Envio")
        titulo_pendentes.setObjectName("titulo-secao-pendentes")
        layout_pendentes.addWidget(titulo_pendentes)

        self._tabela_pendentes = self._criar_tabela()
        layout_pendentes.addWidget(self._tabela_pendentes)

        rodape_pendentes = QHBoxLayout()
        rodape_pendentes.addStretch()
        self._botao_enviar_pedido = QPushButton("Enviar Pedido à Produção")
        self._botao_enviar_pedido.setProperty("variante", "sucesso")
        self._botao_enviar_pedido.setMinimumHeight(40)
        self._botao_enviar_pedido.setToolTip(
            "Manda para a produção todos os itens pendentes desta comanda. (Ctrl+Enter ou F5)"
        )
        self._botao_enviar_pedido.clicked.connect(self._imprimir_producao)
        rodape_pendentes.addWidget(self._botao_enviar_pedido)
        layout_pendentes.addLayout(rodape_pendentes)

        layout_externo.addWidget(self._secao_pendentes)

        # Atalhos de teclado para o envio em lote — guardados como atributos
        # para não serem coletados pelo GC do Python.
        self._atalho_enviar_ctrl_enter = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._atalho_enviar_ctrl_enter.activated.connect(self._imprimir_producao)
        self._atalho_enviar_f5 = QShortcut(QKeySequence("F5"), self)
        self._atalho_enviar_f5.activated.connect(self._imprimir_producao)

        # ---------- Seção "Lançados" ----------
        titulo_lancados = QLabel("Itens Lançados")
        titulo_lancados.setObjectName("titulo-secao-lancados")
        layout_externo.addWidget(titulo_lancados)

        self._tabela_lancados = self._criar_tabela()
        layout_externo.addWidget(self._tabela_lancados)

        linha_total = QHBoxLayout()
        linha_total.addStretch()
        linha_total.addWidget(QLabel("Total"))
        self._label_total = QLabel("R$ 0,00")
        self._label_total.setStyleSheet("font-weight: 700; font-size: 16px;")
        linha_total.addWidget(self._label_total)
        layout_externo.addLayout(linha_total)

    def _criar_tabela(self) -> QTableWidget:
        tabela = QTableWidget(0, len(_COLUNAS))
        tabela.setHorizontalHeaderLabels(_COLUNAS)
        tabela.verticalHeader().setVisible(False)
        tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabela.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Coluna de ação só tem `setCellWidget` (o botão), sem
        # `QTableWidgetItem` nenhum — e `ResizeToContents` mede o texto do
        # ITEM da coluna, não do widget nela. Sem item, a coluna encolhe pro
        # mínimo e o texto do botão ("Cancelar"/"Remover") fica cortado.
        # Largura fixa evita essa armadilha do Qt.
        tabela.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        tabela.setColumnWidth(4, _LARGURA_COLUNA_ACAO)
        return tabela

    def carregar_comanda(self, comanda: Comanda) -> None:
        self._comanda = comanda
        self.atualizar()

    def atualizar(self) -> None:
        if self._comanda is None:
            return
        self._label_erro.setText("")
        # Qualquer mudança na comanda — outra mesa, item novo, item cancelado —
        # envelhece o aviso do último cupom. Mantê-lo faria o operador achar que
        # a cozinha já viu o item que ele acabou de lançar.
        self._aviso_impressao.limpar()
        # Recarrega para pegar o status mais recente (ex.: acabou de ser
        # cancelada por este mesmo modal) — o objeto passado a
        # `carregar_comanda` pode estar desatualizado.
        self._comanda = self._comanda_service.buscar(self._comanda.id)

        titulo = f"Mesa {self._comanda.mesa.numero}" if self._comanda.mesa else "Balcão"
        self._label_titulo.setText(titulo)

        itens = self._comanda_service.listar_itens(self._comanda.id)
        itens_ativos = [item for item in itens if not item.cancelado]
        itens_pendentes = [item for item in itens_ativos if item.impresso_em is None]
        itens_lancados = [item for item in itens_ativos if item.impresso_em is not None]

        # O relógio só corre a partir do primeiro item que a cozinha de fato
        # viu — enquanto está tudo em "Pendentes" é rascunho, e numa mesa
        # grande lançar tudo pode levar minutos sem que isso seja atraso.
        primeiro_envio = ComandaService.hora_primeiro_envio(itens_ativos)
        self._label_horario.setText(
            self._formatar_tempo_aberta(primeiro_envio) if primeiro_envio else ""
        )

        self._tabela_pendentes.setRowCount(len(itens_pendentes))
        for linha, item in enumerate(itens_pendentes):
            self._preencher_linha_pendente(linha, item)

        grupos_lancados = self._agrupar_para_exibicao(itens_lancados)
        self._tabela_lancados.setRowCount(len(grupos_lancados))
        for linha, grupo in enumerate(grupos_lancados):
            self._preencher_linha_lancada(linha, grupo)

        total = self._comanda_service.calcular_total(self._comanda.id)
        self._label_total.setText(_formatar_reais(total))

        aberta = self._comanda.status is StatusComanda.ABERTA
        self._botao_add_item.setEnabled(aberta)
        self._botao_pagamento.setEnabled(aberta)
        self._botao_cancelar_comanda.setEnabled(aberta)
        # Botão de envio só faz sentido havendo algo pendente na comanda
        # aberta — a fechada não recebe mais item. A 2ª via continua
        # liberada: cupom da cozinha some ou rasga depois do pagamento também.
        self._botao_enviar_pedido.setEnabled(aberta and bool(itens_pendentes))
        self._botao_segunda_via.setEnabled(len(itens_ativos) > 0)

    @staticmethod
    def _agrupar_para_exibicao(itens: list[ItemComanda]) -> list[list[ItemComanda]]:
        """Agrupa itens já lançados por (produto, preço) para soma visual.

        Cada grupo guarda os `ItemComanda` originais — necessário porque o
        cancelamento continua sendo feito item a item (registro de
        auditoria), mesmo que a tabela mostre uma linha só com a soma.
        """
        grupos: dict[tuple[int, Decimal], list[ItemComanda]] = {}
        ordem: list[tuple[int, Decimal]] = []
        for item in itens:
            chave = (item.produto_id, item.preco_unit_congelado)
            if chave not in grupos:
                grupos[chave] = []
                ordem.append(chave)
            grupos[chave].append(item)
        return [grupos[chave] for chave in ordem]

    def _formatar_tempo_aberta(self, primeiro_envio: datetime) -> str:
        minutos = int((datetime.now() - primeiro_envio).total_seconds() // 60)
        if minutos >= 60:
            cor, tempo = "#f43f5e", f"{minutos // 60}h{minutos % 60:02d}"
        elif minutos >= 30:
            cor, tempo = "#eab308", f"{minutos} min"
        else:
            cor, tempo = "#94a3b8", f"{minutos} min"
        self._label_horario.setStyleSheet(f"font-size: 13px; margin-left: 8px; color: {cor};")
        return f"Na cozinha desde {primeiro_envio.strftime('%H:%M')} · há {tempo}"

    def _preencher_celulas_basicas(
        self, tabela: QTableWidget, linha: int, descricao: str, preco_unit: Decimal, quantidade: int
    ) -> None:
        total_item = preco_unit * quantidade
        tabela.setItem(linha, 0, QTableWidgetItem(descricao))
        tabela.setItem(linha, 1, QTableWidgetItem(_formatar_reais(preco_unit)))
        tabela.setItem(linha, 2, QTableWidgetItem(str(quantidade)))
        tabela.setItem(linha, 3, QTableWidgetItem(_formatar_reais(total_item)))

    @staticmethod
    def _aplicar_variante(botao: QPushButton, variante: str) -> None:
        # Botões criados no __init__ (voltar, +Item, etc.) já existem antes da
        # janela ser exibida, então o `setProperty` sozinho basta: o Qt
        # calcula o estilo pela primeira vez já com a propriedade presente.
        # Estes aqui (Remover/Cancelar) nascem depois, a cada `atualizar()`,
        # e vão direto para uma tabela já visível via `setCellWidget` — sem
        # unpolish/polish o seletor `[variante="perigo"]` só pinta o fundo e
        # o texto branco não é recalculado, some (bug conhecido do Qt com
        # QSS + propriedade dinâmica em widget inserido após o polish inicial).
        botao.setProperty("variante", variante)
        botao.style().unpolish(botao)
        botao.style().polish(botao)

    def _preencher_linha_pendente(self, linha: int, item: ItemComanda) -> None:
        descricao = item.produto.nome
        if item.observacao:
            descricao += f" ({item.observacao})"
        self._preencher_celulas_basicas(
            self._tabela_pendentes, linha, descricao, item.preco_unit_congelado, item.quantidade
        )

        acoes_item = QWidget()
        layout_acoes = QHBoxLayout(acoes_item)
        layout_acoes.setContentsMargins(0, 0, 0, 0)

        # Item ainda não impresso é rascunho, sem rastro a preservar: remoção
        # direta, sem confirmação (a única "trava" é o próprio botão — clique
        # errado é raro e o item nem chegou à cozinha). Texto puro, não
        # emoji: o glifo some em fontes sem suporte a emoji colorido e o
        # botão vira um quadrado vazio, sem afordância nenhuma.
        botao_remover = QPushButton("Remover")
        self._aplicar_variante(botao_remover, "perigo")
        botao_remover.setToolTip("Remover item da lista (ainda não foi enviado à produção).")
        botao_remover.clicked.connect(lambda _checked=False, i=item: self._remover_item(i))
        layout_acoes.addWidget(botao_remover)

        self._tabela_pendentes.setCellWidget(linha, 4, acoes_item)

    def _preencher_linha_lancada(self, linha: int, grupo: list[ItemComanda]) -> None:
        primeiro = grupo[0]
        descricao = primeiro.produto.nome
        if primeiro.observacao and len(grupo) == 1:
            descricao += f" ({primeiro.observacao})"
        quantidade_total = sum(item.quantidade for item in grupo)
        self._preencher_celulas_basicas(
            self._tabela_lancados, linha, descricao, primeiro.preco_unit_congelado, quantidade_total
        )

        acoes_item = QWidget()
        layout_acoes = QHBoxLayout(acoes_item)
        layout_acoes.setContentsMargins(0, 0, 0, 0)

        # Já foi para a produção: a única saída é Cancelar, com PIN de
        # gerente e motivo, porque a partir daí é registro de auditoria (ver
        # docs/arquitetura §3.6) — mesmo agrupado na tela, cada `ItemComanda`
        # do grupo é cancelado individualmente por baixo.
        botao_cancelar = QPushButton("Cancelar")
        self._aplicar_variante(botao_cancelar, "perigo")
        botao_cancelar.setToolTip(
            "Solicitar cancelamento do item. Já foi enviado à produção — exige senha do gerente."
        )
        botao_cancelar.clicked.connect(lambda _checked=False, g=grupo: self._cancelar_grupo(g))
        layout_acoes.addWidget(botao_cancelar)

        self._tabela_lancados.setCellWidget(linha, 4, acoes_item)

    def _mostrar_mensagem(self, texto: str, *, sucesso: bool) -> None:
        cor = "#22c55e" if sucesso else "#f43f5e"
        self._label_erro.setStyleSheet(f"color: {cor}; font-size: 12px;")
        self._label_erro.setText(texto)

    def _remover_item(self, item: ItemComanda) -> None:
        nome_produto = item.produto.nome
        try:
            self._comanda_service.remover_item(item.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_mensagem(str(erro), sucesso=False)
            return
        self.atualizar()
        self._mostrar_mensagem(f"{nome_produto} removido com sucesso.", sucesso=True)

    def _cancelar_grupo(self, grupo: list[ItemComanda]) -> None:
        nome_produto = grupo[0].produto.nome
        titulo = (
            f"Cancelar item — {nome_produto}"
            if len(grupo) == 1
            else f"Cancelar {len(grupo)}x {nome_produto}"
        )
        modal = CancelamentoDialog(titulo, self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        motivo, pin_gerente = modal.resultado()

        gerente_nome = "gerente"
        try:
            for item in grupo:
                item_cancelado = self._comanda_service.cancelar_item(item.id, motivo, pin_gerente)
                if item_cancelado.cancelado_por:
                    gerente_nome = item_cancelado.cancelado_por.nome
        except _ERROS_SERVICE as erro:
            self._mostrar_mensagem(str(erro), sucesso=False)
            return
        self.atualizar()
        self._mostrar_mensagem(
            f"Cancelamento de {nome_produto} autorizado por {gerente_nome}.", sucesso=True
        )

    def _cancelar_comanda(self) -> None:
        if self._comanda is None:
            return
        modal = CancelamentoDialog(f"Cancelar comanda {self._comanda.id}", self)
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        motivo, pin_gerente = modal.resultado()

        self._label_erro.setText("")
        try:
            self._comanda_service.cancelar(self._comanda.id, motivo, pin_gerente)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        comanda_id = self._comanda.id
        self.atualizar()
        self.comanda_cancelada.emit(comanda_id)

    def _imprimir_producao(self) -> None:
        """Via de acréscimo: manda para a cozinha só o que ela ainda não viu."""
        if self._comanda is None:
            return
        comanda_id = self._comanda.id

        self._label_erro.setText("")
        try:
            resultados = executar_impressao(
                lambda: self._impressao_service.imprimir_comanda(comanda_id)
            )
        except _ERROS_SERVICE as erro:
            # Impressora com defeito não passa por aqui: volta dentro de
            # `resultados` com sucesso=False. Aqui só chega comanda inexistente
            # ou sessão perdida, que são erro de verdade.
            self._label_erro.setText(str(erro))
            return
        # Move visualmente os itens de "Pendentes" para "Lançados" assim que
        # a impressão marca `impresso_em` — sem isto a tabela ficava com dado
        # velho até a próxima ação (ex.: abrir o modal de +Item de novo).
        # `atualizar()` limpa `_label_erro`, então a mensagem de confirmação
        # só pode ser escrita depois dele.
        self.atualizar()
        if resultados:
            # O pedido já está confirmado (ComandaService/ImpressaoService
            # marcam `impresso_em` do lote inteiro, com ou sem impressora) —
            # essa mensagem é sempre positiva. Falha de papel é só o aviso
            # âmbar logo abaixo, nunca motivo pra parecer que o pedido não
            # foi registrado.
            houve_falha = any(not resultado.sucesso for resultado in resultados)
            texto = (
                "Pedido registrado com sucesso! (Aviso: alguns itens não possuem "
                "impressora configurada — veja o detalhe abaixo.)"
                if houve_falha
                else "Pedido enviado para a produção com sucesso!"
            )
            self._mostrar_mensagem(texto, sucesso=True)
        self._aviso_impressao.mostrar(resultados, vazio=_NADA_NOVO_PARA_IMPRIMIR)

    def _imprimir_segunda_via(self) -> None:
        """Repete a comanda inteira sem mexer no que já foi marcado como impresso."""
        if self._comanda is None:
            return
        comanda_id = self._comanda.id

        self._label_erro.setText("")
        try:
            resultados = executar_impressao(
                lambda: self._impressao_service.reimprimir_comanda(comanda_id)
            )
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._aviso_impressao.mostrar(resultados, vazio="Esta comanda não tem itens para reimprimir.")

    def _voltar_clicado(self) -> None:
        self.tentar_sair(self.voltar.emit)

    def possui_itens_pendentes(self) -> bool:
        return self._tabela_pendentes.rowCount() > 0

    def tentar_sair(self, ao_sair: Callable[[], None]) -> None:
        """Ponto único de saída da comanda (§ requisito 4).

        `ao_sair` só é chamado se não houver pendência, ou se o operador
        resolveu a pendência explicitamente (enviar ou descartar) — nunca
        silenciosamente. Usado tanto pelo botão "← Mesas" quanto por
        qualquer navegação externa (`MainWindow`, sidebar, logout) que tente
        tirar o operador desta tela.
        """
        if not self.possui_itens_pendentes():
            ao_sair()
            return
        self._abrir_modal_saida_com_pendencias(ao_sair)

    def _abrir_modal_saida_com_pendencias(self, ao_sair: Callable[[], None]) -> None:
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Itens pendentes")
        caixa.setText("Existem itens pendentes que não foram enviados. O que deseja fazer?")
        caixa.setIcon(QMessageBox.Icon.Warning)

        botao_enviar = caixa.addButton("Enviar e Sair", QMessageBox.ButtonRole.AcceptRole)
        botao_descartar = caixa.addButton("Descartar Pendências e Sair", QMessageBox.ButtonRole.DestructiveRole)
        botao_continuar = caixa.addButton("Continuar Editando", QMessageBox.ButtonRole.RejectRole)
        caixa.setDefaultButton(botao_enviar)
        caixa.setEscapeButton(botao_continuar)
        botao_enviar.setProperty("variante", "sucesso")
        botao_descartar.setProperty("variante", "perigo")
        botao_continuar.setProperty("variante", "secundario")

        caixa.exec()
        clicado = caixa.clickedButton()

        if clicado is botao_enviar:
            self._imprimir_producao()
            if not self._label_erro.text():
                ao_sair()
        elif clicado is botao_descartar:
            self._descartar_pendencias(ao_sair)
        # botao_continuar (ou fechar a caixa): permanece na mesa atual.

    def _descartar_pendencias(self, ao_sair: Callable[[], None]) -> None:
        assert self._comanda is not None
        itens_pendentes = [
            item
            for item in self._comanda_service.listar_itens(self._comanda.id)
            if not item.cancelado and item.impresso_em is None
        ]
        for item in itens_pendentes:
            self._comanda_service.remover_item(item.id)
        ao_sair()

    def _solicitar_pagamento(self) -> None:
        if self._comanda is None:
            return
        self.pagamento_solicitado.emit(self._comanda.id)

    def _abrir_modal_adicionar_item(self) -> None:
        if self._comanda is None:
            return
        produtos = self._cardapio_service.listar_produtos_ativos()
        if not produtos:
            self._label_erro.setText("Não há produtos ativos no cardápio.")
            return

        modal = _AdicionarItemDialog(produtos, self._lancar_item_do_modal, self)
        modal.exec()
        # O modal já lança cada item na hora (fluxo rápido de PDV); ao
        # fechar, só falta atualizar a tabela com o que ficou de fora dela.
        self.atualizar()

    def _lancar_item_do_modal(
        self, produto_id: int, quantidade: int, observacao: str | None
    ) -> None:
        """Lança um item vindo do modal de busca e devolve a tabela atualizada.

        Repassa erro de regra de negócio para o modal exibir (ex.: comanda
        fechada entre um lançamento e outro) — quem decide fechar a tela
        continua sendo o operador.
        """
        assert self._comanda is not None
        self._comanda_service.lancar_item(self._comanda.id, produto_id, quantidade, observacao)
        self.atualizar()


class _AdicionarItemDialog(QDialog):
    """Modal `+ Item`: busca instantânea do cardápio + quantidade/observação.

    Fluxo de PDV: `Enter` no item destacado da busca já lança na comanda com
    a quantidade/observação atuais e limpa só o campo de busca, deixando o
    modal aberto para o próximo item — o operador lança vários produtos em
    sequência sem reabrir a tela a cada um. `Esc` com a busca vazia fecha.
    """

    def __init__(
        self,
        produtos: list[Produto],
        lancar_item: Callable[[int, int, str | None], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Adicionar item")
        self.setMinimumWidth(420)
        self._lancar_item = lancar_item

        layout = QVBoxLayout(self)

        self._busca = BuscaProdutoWidget(produtos)
        self._busca.produto_selecionado.connect(self._produto_selecionado)
        self._busca.busca_cancelada.connect(self.reject)
        layout.addWidget(self._busca)

        dica = QLabel("Duplo clique ou Enter no item lança direto. Ou selecione e use Adicionar.")
        dica.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(dica)

        formulario = QFormLayout()

        self._campo_quantidade = QSpinBox()
        self._campo_quantidade.setMinimum(1)
        self._campo_quantidade.setMaximum(999)
        self._campo_quantidade.setValue(1)
        formulario.addRow("Quantidade", self._campo_quantidade)

        self._campo_observacao = QLineEdit()
        self._campo_observacao.setPlaceholderText("Ex.: sem cebola")
        formulario.addRow("Observação", self._campo_observacao)

        layout.addLayout(formulario)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout.addWidget(self._label_erro)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        botoes.button(QDialogButtonBox.StandardButton.Close).setText("Fechar")
        botoes.rejected.connect(self.reject)

        self._botao_adicionar = botoes.addButton("Adicionar", QDialogButtonBox.ButtonRole.AcceptRole)
        self._botao_adicionar.setProperty("variante", "primario")
        self._botao_adicionar.clicked.connect(self._busca.confirmar_selecionado)

        layout.addWidget(botoes)

    def _produto_selecionado(self, produto_id: int) -> None:
        quantidade = self._campo_quantidade.value()
        observacao = self._campo_observacao.text().strip() or None

        self._label_erro.setText("")
        try:
            self._lancar_item(produto_id, quantidade, observacao)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return

        # Item lançado: reseta para o próximo, mas mantém o modal aberto e o
        # foco na busca — é aí que está o ganho de velocidade do PDV.
        self._campo_quantidade.setValue(1)
        self._campo_observacao.clear()
        self._busca.foco_busca()


def _formatar_reais(valor: Decimal) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")
