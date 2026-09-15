"""Impressoras: cadastro, escolha da padrão e cupom de teste (§3.12).

Tela nova, sem equivalente no front-end web do Gestor Comercial (Java): lá a
impressora era só um nome numa lista e a impressão era simulada em log. Aqui o
cadastro precisa carregar os parâmetros de conexão de verdade — vendor/product
id, porta serial, host, fila do Windows ou caminho do .txt — porque é com eles
que `hardware/impressora_escpos` abre o driver.

O cadastro e a edição moram no cartão `widgets/impressora_dialog.py` (§9.19):
três cards de conexão em vez de cinco tipos num combo, a bobina em milímetros
em vez de colunas, e o uso ("Recibo do cliente" é a padrão) escolhido ali mesmo.
Quem cadastra é o gerente do food truck no dia da instalação, não um técnico.

Cadastrar, editar, excluir e definir padrão são ações administrativas e exigem
gerente — quem barra isso é `CardapioService` (via `AuthService.exigir_gerente`);
aqui só se mostra o erro que o service levantar.
"""

from __future__ import annotations

from functools import partial

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QMouseEvent

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.impressora_dialog import DadosImpressora, ImpressoraDialog
from gestor_comercial.ui.widgets.modais import executar_modal
from gestor_comercial.ui.widgets.tabelas import definir_celula, limpar_tabela
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade

# Coluna 0 é só o traço indicador (~4px) da linha selecionada -- não é
# impressora nenhuma, então não entra em `_preencher_linha` como dado.
_COLUNAS = ["", "Nome", "Conexão", "Destino", "Bobina", "Padrão", "Status"]

_ROTULOS_TIPO = {
    TipoConexaoImpressora.USB: "USB",
    TipoConexaoImpressora.SERIAL: "Serial",
    TipoConexaoImpressora.REDE: "Rede",
    TipoConexaoImpressora.WINDOWS: "Windows",
    TipoConexaoImpressora.ARQUIVO: "Arquivo (.txt)",
}

# Glifo de conexão por tipo -- só decoração, não afeta a leitura da coluna.
_GLIFOS_CONEXAO = {
    TipoConexaoImpressora.USB: "🔌",
    TipoConexaoImpressora.SERIAL: "🔌",
    TipoConexaoImpressora.REDE: "🌐",
    TipoConexaoImpressora.WINDOWS: "🖥",
    TipoConexaoImpressora.ARQUIVO: "📄",
}

# Teto da lista de cupons pendentes: ~5 linhas. Passando disso ela rola, para
# uma fila grande não empurrar a tabela de impressoras para fora da tela.
_ALTURA_MAXIMA_FILA = 150

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)


class ImpressorasView(QWidget):
    """CRUD de impressora, marcação da padrão e cupom de teste."""

    def __init__(
        self,
        cardapio_service: CardapioService,
        impressao_service: ImpressaoService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = cardapio_service
        self._impressao = impressao_service
        self._impressoras: list[Impressora] = []
        # O id que a última gravação do cartão devolveu, para a lista recarregada
        # voltar com ela selecionada.
        self._id_gravado: int | None = None

        self._montar_layout()
        self.atualizar()

    def _montar_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(4)

        self._breadcrumb = QLabel("GERENTE")
        self._breadcrumb.setObjectName("centralLojaBreadcrumb")
        layout.addWidget(self._breadcrumb)

        cabecalho = QHBoxLayout()
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(4)
        titulo = QLabel("Impressoras")
        titulo.setObjectName("centralLojaTitulo")
        bloco_titulo.addWidget(titulo)
        subtitulo = QLabel("Recibo do cliente, fechamento de caixa e produção")
        subtitulo.setObjectName("centralLojaSubtitulo")
        bloco_titulo.addWidget(subtitulo)
        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch()

        botao_nova = QPushButton("Nova impressora")
        botao_nova.setProperty("variante", "pilula-destaque")
        botao_nova.clicked.connect(self._criar)
        cabecalho.addWidget(botao_nova, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(cabecalho)
        layout.addSpacing(20)

        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        layout.addWidget(self._label_erro)

        self._aviso = AvisoDeImpressao()
        layout.addWidget(self._aviso)

        linha_principal = QHBoxLayout()
        linha_principal.setSpacing(16)
        linha_principal.addWidget(self._montar_painel_tabela(), stretch=2)
        linha_principal.addWidget(self._montar_painel_categorias(), stretch=1)
        layout.addLayout(linha_principal)

    def _montar_painel_tabela(self) -> QWidget:
        coluna = QVBoxLayout()
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(10)

        painel = QFrame()
        painel.setObjectName("impressorasPainel")
        layout_painel = QVBoxLayout(painel)
        layout_painel.setContentsMargins(0, 0, 0, 0)
        layout_painel.setSpacing(0)

        self._tabela = QTableWidget(0, len(_COLUNAS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS)
        self._tabela.setFrameShape(QFrame.Shape.NoFrame)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tabela.setShowGrid(False)
        self._tabela.verticalHeader().setDefaultSectionSize(52)
        cabecalho_tabela = self._tabela.horizontalHeader()
        cabecalho_tabela.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._tabela.setColumnWidth(0, 4)
        cabecalho_tabela.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        cabecalho_tabela.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tabela.itemSelectionChanged.connect(self._ao_selecionar_linha)
        layout_painel.addWidget(self._tabela)

        barra_acoes = QFrame()
        barra_acoes.setObjectName("impressorasBarraAcoes")
        layout_acoes = QHBoxLayout(barra_acoes)
        layout_acoes.setContentsMargins(16, 12, 16, 12)

        self._label_selecao = QLabel("NENHUMA SELECIONADA")
        self._label_selecao.setObjectName("impressorasSelecaoLabel")
        layout_acoes.addWidget(self._label_selecao)
        layout_acoes.addStretch()

        self._botao_editar = QPushButton("Editar")
        self._botao_editar.setProperty("variante", "secundario")
        self._botao_editar.clicked.connect(self._editar)
        layout_acoes.addWidget(self._botao_editar)

        self._botao_padrao = QPushButton("Definir como padrão")
        self._botao_padrao.setProperty("variante", "pilula-ciano")
        self._botao_padrao.clicked.connect(self._definir_padrao)
        layout_acoes.addWidget(self._botao_padrao)

        self._botao_teste = QPushButton("Imprimir teste")
        self._botao_teste.setProperty("variante", "secundario")
        self._botao_teste.clicked.connect(self._imprimir_teste)
        layout_acoes.addWidget(self._botao_teste)

        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setProperty("variante", "perigo")
        self._botao_excluir.clicked.connect(self._excluir)
        layout_acoes.addWidget(self._botao_excluir)

        layout_painel.addWidget(barra_acoes)
        # `stretch=1` só na tabela: sem isto o espaço que sobra na coluna é
        # dividido com o painel da fila, que fica com um vão vazio enorme entre
        # a lista e os botões. A tabela é quem deve crescer.
        coluna.addWidget(painel, stretch=1)

        self._label_ajuda = QLabel(
            "A impressora padrão recebe o recibo do cliente, o fechamento de caixa e "
            "os itens de categorias sem impressora própria. O tipo Arquivo grava o "
            "cupom num .txt — serve para conferir tudo antes de a impressora chegar."
        )
        self._label_ajuda.setProperty("variante", "fraco")
        self._label_ajuda.setWordWrap(True)
        coluna.addWidget(self._label_ajuda)

        coluna.addWidget(self._montar_painel_fila())

        envelope = QWidget()
        envelope.setLayout(coluna)
        return envelope

    def _montar_painel_fila(self) -> QWidget:
        """Os cupons que não saíram no papel, e o que fazer com eles (Fase 3).

        Sem esta lista a fila de contingência seria promessa vazia: o aviso âmbar
        diz "o cupom ficou salvo na fila para reimpressão", e o operador precisa
        de um lugar onde de fato reimprimir. Fica na tela de Impressoras porque é
        onde ele já vai quando a impressora dá problema.

        O painel some inteiro quando a fila está vazia — que é o dia normal. Uma
        seção permanente vazia só ensinaria o operador a ignorar aquela área da
        tela, e é justamente ali que a informação urgente aparece.
        """
        self._painel_fila = QFrame()
        self._painel_fila.setObjectName("impressorasPainel")
        layout = QVBoxLayout(self._painel_fila)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        eyebrow = QLabel("CUPONS QUE NÃO SAÍRAM")
        eyebrow.setObjectName("impressorasSelecaoLabel")
        layout.addWidget(eyebrow)

        ajuda = QLabel(
            "Ficaram guardados quando a impressora não respondeu. Resolva o "
            "papel ou o cabo e clique em Reimprimir."
        )
        ajuda.setProperty("variante", "fraco")
        ajuda.setWordWrap(True)
        layout.addWidget(ajuda)

        self._lista_fila = QListWidget()
        self._lista_fila.setFrameShape(QFrame.Shape.NoFrame)
        self._lista_fila.setStyleSheet("background: transparent;")
        self._lista_fila.setMaximumHeight(_ALTURA_MAXIMA_FILA)
        self._painel_fila.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        layout.addWidget(self._lista_fila)

        acoes = QHBoxLayout()
        acoes.addStretch()

        self._botao_reimprimir = QPushButton("Reimprimir")
        self._botao_reimprimir.setProperty("variante", "pilula-ciano")
        self._botao_reimprimir.clicked.connect(self._reimprimir_da_fila)
        acoes.addWidget(self._botao_reimprimir)

        self._botao_descartar = QPushButton("Descartar")
        self._botao_descartar.setProperty("variante", "perigo")
        self._botao_descartar.clicked.connect(self._descartar_da_fila)
        acoes.addWidget(self._botao_descartar)

        layout.addLayout(acoes)
        return self._painel_fila

    def _montar_painel_categorias(self) -> QWidget:
        painel = QFrame()
        painel.setObjectName("impressorasPainel")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        eyebrow = QLabel("CATEGORIAS DESTA IMPRESSORA")
        eyebrow.setObjectName("impressorasSelecaoLabel")
        layout.addWidget(eyebrow)

        self._titulo_categorias = QLabel("—")
        self._titulo_categorias.setStyleSheet("font-weight: 700; font-size: 16px;")
        layout.addWidget(self._titulo_categorias)
        layout.addSpacing(6)

        self._lista_categorias = QListWidget()
        self._lista_categorias.setFrameShape(QFrame.Shape.NoFrame)
        self._lista_categorias.setStyleSheet("background: transparent;")
        self._lista_categorias.setSpacing(6)
        self._lista_categorias.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self._lista_categorias, stretch=1)

        ajuda = QLabel(
            "Marque as categorias que devem sair nesta impressora. Uma "
            "categoria marcada em outra impressora troca para esta."
        )
        ajuda.setProperty("variante", "fraco")
        ajuda.setWordWrap(True)
        layout.addWidget(ajuda)

        self._label_pendentes = QLabel("")
        self._label_pendentes.setObjectName("impressorasPendentesLink")
        self._label_pendentes.setWordWrap(True)
        layout.addWidget(self._label_pendentes)

        return painel

    def definir_usuario(self, nome_perfil: str) -> None:
        """`nome_perfil` já vem formatado (ex.: "GERENTE · VITOR"), igual ao
        breadcrumb do restante do shell (ver `MainWindow._ao_logar`)."""
        self._breadcrumb.setText(nome_perfil)

    def atualizar(self) -> None:
        self._label_erro.setText("")
        # Cadastro alterado envelhece o aviso do último teste: a impressora que
        # respondeu pode ser justamente a que acabou de mudar de porta.
        self._aviso.limpar()
        self._impressoras = self._service.listar_impressoras()
        limpar_tabela(self._tabela, linhas=len(self._impressoras), preservar_selecao=True)
        for linha, impressora in enumerate(self._impressoras):
            self._preencher_linha(linha, impressora)
        self._ao_selecionar_linha()
        # Depois de `self._impressoras`: a lista da fila mostra o NOME da
        # impressora de destino, e o mapa de nomes sai daí.
        self._atualizar_fila()

    def _ao_selecionar_linha(self) -> None:
        self._atualizar_indicadores_linha()
        impressora = self._impressora_selecionada()
        self._label_selecao.setText(
            f"SELECIONADA · {impressora.nome.upper()}" if impressora else "NENHUMA SELECIONADA"
        )
        self._atualizar_categorias()

    def _atualizar_indicadores_linha(self) -> None:
        linha_selecionada = self._tabela.currentRow()
        for linha in range(self._tabela.rowCount()):
            indicador = self._tabela.cellWidget(linha, 0)
            if indicador is None:
                continue
            aplicar_propriedade(indicador, "ativo", "true" if linha == linha_selecionada else "false")

    def _atualizar_categorias(self) -> None:
        self._lista_categorias.clear()

        impressora = self._impressora_selecionada()
        if impressora is None:
            self._titulo_categorias.setText("—")
            self._label_pendentes.setText("")
            return

        self._titulo_categorias.setText(impressora.nome)

        todas_categorias = self._service.listar_categorias()
        vinculadas = {c.id for c in self._service.listar_categorias_da_impressora(impressora.id)}
        for categoria in todas_categorias:
            linha = _LinhaCategoria(categoria.id, categoria.nome, categoria.id in vinculadas)
            linha.alternada.connect(self._ao_marcar_categoria)
            item = QListWidgetItem()
            item.setSizeHint(linha.sizeHint())
            self._lista_categorias.addItem(item)
            self._lista_categorias.setItemWidget(item, linha)

        if impressora.padrao:
            sem_impressora = sum(1 for c in todas_categorias if c.impressora_id is None)
            self._label_pendentes.setText(
                f"{sem_impressora} seguem para a padrão." if sem_impressora else ""
            )
        else:
            self._label_pendentes.setText("")

    def _ao_marcar_categoria(self, categoria_id: int, marcada: bool) -> None:
        impressora = self._impressora_selecionada()
        if impressora is None:
            return

        self._mostrar_erro("")
        try:
            if marcada:
                self._service.associar_impressora(categoria_id, impressora.id)
            else:
                self._service.desassociar_impressora(categoria_id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
        # Outra impressora pode ter perdido essa categoria (troca de vínculo);
        # a checklist dela só se atualiza quando o gerente clicar nela de novo,
        # então não há duplicidade visível, só desatualizada até o próximo clique.
        if impressora.padrao:
            todas_categorias = self._service.listar_categorias()
            sem_impressora = sum(1 for c in todas_categorias if c.impressora_id is None)
            self._label_pendentes.setText(
                f"{sem_impressora} seguem para a padrão." if sem_impressora else ""
            )

    def _preencher_linha(self, linha: int, impressora: Impressora) -> None:
        indicador = _CelulaSelecionavel(self._tabela)
        indicador.setObjectName("impressorasIndicador")
        indicador.setFixedWidth(4)
        definir_celula(self._tabela, linha, 0, indicador)

        definir_celula(self._tabela, linha, 1, self._montar_celula_nome(impressora))
        definir_celula(self._tabela, linha, 2, self._montar_celula_conexao(impressora))

        item_destino = QTableWidgetItem(_descricao_destino(impressora))
        item_destino.setFlags(item_destino.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._tabela.setItem(linha, 3, item_destino)

        item_bobina = QTableWidgetItem(f"{impressora.colunas} colunas")
        item_bobina.setFlags(item_bobina.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._tabela.setItem(linha, 4, item_bobina)

        definir_celula(self._tabela, linha, 5, self._montar_celula_padrao(impressora))
        definir_celula(self._tabela, linha, 6, self._montar_celula_status(impressora))

    def _montar_celula_nome(self, impressora: Impressora) -> QWidget:
        celula = _CelulaSelecionavel(self._tabela)
        layout = QHBoxLayout(celula)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        icone_box = QFrame()
        icone_box.setObjectName("impressoraIconeBox")
        icone_box.setFixedSize(36, 36)
        layout_icone = QVBoxLayout(icone_box)
        layout_icone.setContentsMargins(0, 0, 0, 0)
        glifo = QLabel("🖨")
        glifo.setObjectName("impressoraIconeGlifo")
        glifo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_icone.addWidget(glifo)
        layout.addWidget(icone_box)

        bloco_texto = QVBoxLayout()
        bloco_texto.setSpacing(2)
        nome = QLabel(impressora.nome)
        nome.setObjectName("impressoraNomeLabel")
        bloco_texto.addWidget(nome)
        total_categorias = len(self._service.listar_categorias_da_impressora(impressora.id))
        rotulo = "CATEGORIA" if total_categorias == 1 else "CATEGORIAS"
        sub = QLabel(f"{total_categorias} {rotulo}")
        sub.setObjectName("impressoraSubLabel")
        bloco_texto.addWidget(sub)
        layout.addLayout(bloco_texto)
        layout.addStretch()
        return celula

    def _montar_celula_conexao(self, impressora: Impressora) -> QWidget:
        celula = _CelulaSelecionavel(self._tabela)
        layout = QHBoxLayout(celula)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        glifo = QLabel(_GLIFOS_CONEXAO.get(impressora.tipo_conexao, "🔌"))
        glifo.setObjectName("impressoraConexaoIcone")
        layout.addWidget(glifo)

        texto = QLabel(_ROTULOS_TIPO.get(impressora.tipo_conexao, impressora.tipo_conexao.value))
        texto.setObjectName("impressoraConexaoTexto")
        layout.addWidget(texto)
        layout.addStretch()
        return celula

    def _montar_celula_padrao(self, impressora: Impressora) -> QWidget:
        celula = _CelulaSelecionavel(self._tabela)
        layout = QHBoxLayout(celula)
        layout.setContentsMargins(12, 6, 12, 6)

        rotulo = QLabel("★ SIM" if impressora.padrao else "NÃO")
        rotulo.setProperty("variante", "badgePadrao")
        rotulo.setProperty("ativo", "true" if impressora.padrao else "false")
        layout.addWidget(rotulo)
        layout.addStretch()
        return celula

    def _montar_celula_status(self, impressora: Impressora) -> QWidget:
        celula = _CelulaSelecionavel(self._tabela)
        layout = QHBoxLayout(celula)
        layout.setContentsMargins(12, 6, 12, 6)

        rotulo = QLabel("ONLINE" if impressora.ativa else "OFFLINE")
        rotulo.setProperty("variante", "badgeStatusImpressora")
        rotulo.setProperty("status", "online" if impressora.ativa else "offline")
        layout.addWidget(rotulo)
        layout.addStretch()
        return celula

    def _impressora_selecionada(self) -> Impressora | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._impressoras):
            return None
        return self._impressoras[linha]

    def _criar(self) -> None:
        self._mostrar_erro("")
        modal = ImpressoraDialog.para_nova(
            self._nomes_de_impressora(),
            self,
            ha_padrao_ativa=self._ha_padrao_ativa(excluindo=None),
            salvar=partial(self._gravar, None),
            listar_destinos=self._impressao.listar_destinos_locais,
        )
        self._abrir_cadastro(modal)

    def _editar(self) -> None:
        impressora = self._impressora_selecionada()
        if impressora is None:
            self._mostrar_erro("Selecione uma impressora na lista.")
            return
        self._mostrar_erro("")
        modal = ImpressoraDialog.para_editar(
            impressora,
            self._nomes_de_impressora(),
            self,
            outra_padrao_ativa=self._ha_padrao_ativa(excluindo=impressora.id),
            salvar=partial(self._gravar, impressora.id),
            listar_destinos=self._impressao.listar_destinos_locais,
        )
        self._abrir_cadastro(modal)

    def _abrir_cadastro(self, modal: ImpressoraDialog) -> None:
        """Um site de modal só para cadastrar e editar.

        O cartão grava pela função `salvar` e só fecha aceito se o service
        aceitou — então aqui não há erro a mostrar, só a lista a recarregar,
        com a impressora gravada selecionada (a nova entra no fim da lista).
        """
        self._id_gravado = None
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        self.atualizar()
        self._selecionar_por_id(self._id_gravado)

    def _gravar(self, impressora_id: int | None, dados: DadosImpressora) -> str | None:
        """O que o cartão chama ao salvar: `None` se gravou, a mensagem se não.

        O erro volta como texto, e não como exceção, para o cartão continuar
        aberto com tudo o que foi escolhido. A transação é do service: um
        commit só, com a troca de padrão dentro (`_aplicar_uso`).
        """
        try:
            if impressora_id is None:
                gravada = self._service.criar_impressora(
                    dados.nome, dados.tipo_conexao, **dados.parametros()
                )
            else:
                gravada = self._service.editar_impressora(
                    impressora_id, dados.nome, dados.tipo_conexao, **dados.parametros()
                )
        except _ERROS_SERVICE as erro:
            return str(erro)
        self._id_gravado = gravada.id
        return None

    def _nomes_de_impressora(self) -> list[str]:
        """Para o cartão avisar do nome repetido antes de salvar."""
        return [impressora.nome for impressora in self._impressoras]

    def _ha_padrao_ativa(self, *, excluindo: int | None) -> bool:
        """Existe outra impressora recebendo o recibo? Decide o aviso do cartão."""
        return any(
            impressora.padrao and impressora.ativa and impressora.id != excluindo
            for impressora in self._impressoras
        )

    def _selecionar_por_id(self, impressora_id: int | None) -> None:
        if impressora_id is None:
            return
        for linha, impressora in enumerate(self._impressoras):
            if impressora.id == impressora_id:
                self._tabela.selectRow(linha)
                return

    def _definir_padrao(self) -> None:
        impressora = self._impressora_selecionada()
        if impressora is None:
            self._mostrar_erro("Selecione uma impressora na lista.")
            return

        self._mostrar_erro("")
        try:
            self._service.definir_padrao(impressora.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()

    def _excluir(self) -> None:
        impressora = self._impressora_selecionada()
        if impressora is None:
            self._mostrar_erro("Selecione uma impressora na lista.")
            return

        self._mostrar_erro("")
        try:
            self._service.excluir_impressora(impressora.id)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()

    def _imprimir_teste(self) -> None:
        impressora = self._impressora_selecionada()
        if impressora is None:
            self._mostrar_erro("Selecione uma impressora na lista.")
            return

        self._mostrar_erro("")
        try:
            resultado = executar_impressao(lambda: self._impressao.imprimir_teste(impressora.id))
        except _ERROS_SERVICE as erro:
            # Só chega aqui se a impressora sumiu do banco entre a listagem e o
            # clique: cabo solto, papel acabado e afins voltam em `resultado`.
            self._mostrar_erro(str(erro))
            return
        self._aviso.mostrar_um(resultado, contexto="Teste")

    # ------------------------------------------------------------------
    # Fila de contingência (Fase 3 de `Mitigação de Falhas.md`)
    # ------------------------------------------------------------------

    def _atualizar_fila(self) -> None:
        pendentes = self._impressao.listar_fila()
        # Painel escondido no dia normal: seção permanentemente vazia ensina o
        # operador a ignorar aquela área da tela, e é ali que aparece o urgente.
        self._painel_fila.setVisible(bool(pendentes))
        self._lista_fila.clear()
        por_id = {impressora.id: impressora.nome for impressora in self._impressoras}
        for item in pendentes:
            destino = por_id.get(item.impressora_id, "impressora removida")
            rotulo = f"{item.criado_em:%H:%M} · {item.descricao} → {destino}"
            if item.tentativas > 1:
                rotulo += f" ({item.tentativas} tentativas)"
            linha = QListWidgetItem(rotulo)
            linha.setData(Qt.ItemDataRole.UserRole, item.id)
            self._lista_fila.addItem(linha)

        # A lista tem a altura do que ela mostra, até o teto. Sem isto ela ocupa
        # sempre o máximo e sobra um vão entre o último cupom e os botões — numa
        # tela de 768px, espaço vazio é espaço tirado da tabela de impressoras.
        if pendentes:
            altura_linha = self._lista_fila.sizeHintForRow(0)
            self._lista_fila.setFixedHeight(
                min(_ALTURA_MAXIMA_FILA, altura_linha * len(pendentes) + 8)
            )

    def _item_da_fila_selecionado(self) -> int | None:
        linha = self._lista_fila.currentItem()
        return None if linha is None else linha.data(Qt.ItemDataRole.UserRole)

    def _reimprimir_da_fila(self) -> None:
        item_id = self._item_da_fila_selecionado()
        if item_id is None:
            self._mostrar_erro("Escolha na lista qual cupom reimprimir.")
            return

        self._mostrar_erro("")
        try:
            resultado = executar_impressao(lambda: self._impressao.reimprimir_da_fila(item_id))
        except _ERROS_SERVICE as erro:
            # A impressora do cupom sumiu do cadastro entre a listagem e o
            # clique. Cabo solto e papel acabado voltam em `resultado`.
            self._mostrar_erro(str(erro))
            self._atualizar_fila()
            return
        self._aviso.mostrar_um(resultado, contexto="Reimpressão")
        self._atualizar_fila()

    def _descartar_da_fila(self) -> None:
        item_id = self._item_da_fila_selecionado()
        if item_id is None:
            self._mostrar_erro("Escolha na lista qual cupom descartar.")
            return

        self._mostrar_erro("")
        self._impressao.descartar_da_fila(item_id)
        self._atualizar_fila()

    def _mostrar_erro(self, mensagem: str) -> None:
        self._label_erro.setText(mensagem)


class _CelulaSelecionavel(QWidget):
    """Widget de célula da tabela de impressoras que repassa o clique para a
    linha: por padrão o Qt entrega o mousePressEvent ao `cellWidget` e nunca
    ao `QTableWidget`, então sem isso clicar no nome/conexão/padrão/status
    nunca selecionava a linha (e o painel de categorias ficava sempre vazio).
    """

    def __init__(self, tabela: QTableWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tabela = tabela

    @nao_deixa_escapar()
    def mousePressEvent(self, evento: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        indice = self._tabela.indexAt(self.pos())
        if indice.isValid():
            self._tabela.selectRow(indice.row())
        super().mousePressEvent(evento)


class _LinhaCategoria(QFrame):
    """Card clicável de uma categoria no painel lateral -- substitui o item
    checkável padrão do `QListWidget` pelo marcador circular do mockup.
    Alterna o próprio estado visual no clique; quem decide se a chamada ao
    service (associar/desassociar) foi aceita é o `_ImpressorasView`."""

    alternada = Signal(int, bool)

    def __init__(self, categoria_id: int, nome: str, marcada: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("categoriaLinha")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._id = categoria_id
        self._marcada = marcada

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self._marcador = QLabel()
        self._marcador.setObjectName("categoriaMarcador")
        self._marcador.setFixedSize(16, 16)
        layout.addWidget(self._marcador)

        nome_label = QLabel(nome)
        nome_label.setObjectName("categoriaNomeLabel")
        layout.addWidget(nome_label, stretch=1)

        self._aplicar_estado()

    @nao_deixa_escapar(retorno=QSize(0, 0))

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), 40)

    @nao_deixa_escapar()
    def mousePressEvent(self, evento: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if evento.button() == Qt.MouseButton.LeftButton:
            self._marcada = not self._marcada
            self._aplicar_estado()
            self.alternada.emit(self._id, self._marcada)
        super().mousePressEvent(evento)

    def _aplicar_estado(self) -> None:
        valor = "true" if self._marcada else "false"
        for widget in (self, self._marcador):
            aplicar_propriedade(widget, "marcada", valor)


def _descricao_destino(impressora: Impressora) -> str:
    """Resume, numa coluna só, para onde o cupom desta impressora vai."""
    tipo = impressora.tipo_conexao
    if tipo is TipoConexaoImpressora.USB:
        return f"{impressora.vendor_id or '?'} : {impressora.product_id or '?'}"
    if tipo is TipoConexaoImpressora.SERIAL:
        return f"{impressora.porta_serial or '?'} · {impressora.baudrate or '?'} bps"
    if tipo is TipoConexaoImpressora.REDE:
        return f"{impressora.host or '?'} : {impressora.porta_rede or '?'}"
    if tipo is TipoConexaoImpressora.WINDOWS:
        return impressora.nome_fila or "?"
    return impressora.caminho_arquivo or "?"
