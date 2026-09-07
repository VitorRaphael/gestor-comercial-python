"""Impressoras: cadastro, escolha da padrão e cupom de teste (§3.12).

Tela nova, sem equivalente no front-end web do Gestor Comercial (Java): lá a
impressora era só um nome numa lista e a impressão era simulada em log. Aqui o
cadastro precisa carregar os parâmetros de conexão de verdade — vendor/product
id, porta serial, host, fila do Windows ou caminho do .txt — porque é com eles
que `hardware/impressora_escpos` abre o driver.

O formulário mostra só os campos do tipo de conexão escolhido: quem cadastra é
o gerente do food truck no dia da instalação, não um técnico, e ver oito campos
vazios ao mesmo tempo é convite para preencher o errado.

Cadastrar, editar, excluir e definir padrão são ações administrativas e exigem
gerente — quem barra isso é `CardapioService` (via `AuthService.exigir_gerente`);
aqui só se mostra o erro que o service levantar.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QMouseEvent

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.domain.impressora import COLUNAS_PADRAO, Impressora
from gestor_comercial.services.cardapio_service import (
    COLUNAS_MAXIMAS,
    COLUNAS_MINIMAS,
    CardapioService,
)
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.theme.controller import ThemeController
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
        coluna.addWidget(painel)

        self._label_ajuda = QLabel(
            "A impressora padrão recebe o recibo do cliente, o fechamento de caixa e "
            "os itens de categorias sem impressora própria. O tipo Arquivo grava o "
            "cupom num .txt — serve para conferir tudo antes de a impressora chegar."
        )
        self._label_ajuda.setProperty("variante", "fraco")
        self._label_ajuda.setWordWrap(True)
        coluna.addWidget(self._label_ajuda)

        envelope = QWidget()
        envelope.setLayout(coluna)
        return envelope

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
        modal = _ImpressoraDialog("Nova impressora", self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        nome, tipo, parametros = modal.resultado()

        self._mostrar_erro("")
        try:
            self._service.criar_impressora(nome, tipo, **parametros)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()

    def _editar(self) -> None:
        impressora = self._impressora_selecionada()
        if impressora is None:
            self._mostrar_erro("Selecione uma impressora na lista.")
            return
        modal = _ImpressoraDialog("Editar impressora", self, impressora=impressora)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        nome, tipo, parametros = modal.resultado()

        self._mostrar_erro("")
        try:
            self._service.editar_impressora(impressora.id, nome, tipo, **parametros)
        except _ERROS_SERVICE as erro:
            self._mostrar_erro(str(erro))
            return
        self.atualizar()

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


class _ImpressoraDialog(QDialog):
    """Modal de cadastro/edição: nome, bobina e só os campos do tipo escolhido."""

    def __init__(
        self,
        titulo: str,
        parent: QWidget | None = None,
        *,
        impressora: Impressora | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        self._formulario = QFormLayout()

        self._campo_nome = QLineEdit(impressora.nome if impressora else "")
        self._campo_nome.setPlaceholderText("Ex.: Cozinha")
        self._formulario.addRow("Nome", self._campo_nome)

        self._combo_tipo = QComboBox()
        for tipo in TipoConexaoImpressora:
            self._combo_tipo.addItem(_ROTULOS_TIPO[tipo], tipo)
        # Cadastro novo já abre em ARQUIVO, o mesmo default de
        # `criar_impressora`: é o único tipo que funciona sem hardware nenhum,
        # então é o que faz o food truck imprimir no dia em que o app chega.
        tipo_inicial = impressora.tipo_conexao if impressora else TipoConexaoImpressora.ARQUIVO
        indice = self._combo_tipo.findData(tipo_inicial)
        if indice >= 0:
            self._combo_tipo.setCurrentIndex(indice)
        self._combo_tipo.currentIndexChanged.connect(self._atualizar_campos_visiveis)
        self._formulario.addRow("Tipo de conexão", self._combo_tipo)

        self._campo_vendor_id = self._campo_texto(
            "Vendor id (USB)", _texto(impressora, "vendor_id"), "Ex.: 0x04b8"
        )
        self._campo_product_id = self._campo_texto(
            "Product id (USB)", _texto(impressora, "product_id"), "Ex.: 0x0202"
        )
        self._campo_porta_serial = self._campo_texto(
            "Porta serial", _texto(impressora, "porta_serial"), "Ex.: COM3"
        )
        self._campo_baudrate = self._campo_texto(
            "Baudrate", _texto(impressora, "baudrate"), "Opcional, padrão 9600"
        )
        self._campo_host = self._campo_texto(
            "Endereço de rede", _texto(impressora, "host"), "Ex.: 192.168.0.50"
        )
        self._campo_porta_rede = self._campo_texto(
            "Porta de rede", _texto(impressora, "porta_rede"), "Opcional, padrão 9100"
        )
        self._campo_nome_fila = self._campo_texto(
            "Nome no Windows",
            _texto(impressora, "nome_fila"),
            "Como aparece em Dispositivos e Impressoras",
        )
        self._campo_caminho_arquivo = self._campo_texto(
            "Arquivo do cupom",
            _texto(impressora, "caminho_arquivo"),
            "Opcional, padrão cupons/<nome>.txt",
        )

        self._campos_por_tipo = {
            TipoConexaoImpressora.USB: (self._campo_vendor_id, self._campo_product_id),
            TipoConexaoImpressora.SERIAL: (self._campo_porta_serial, self._campo_baudrate),
            TipoConexaoImpressora.REDE: (self._campo_host, self._campo_porta_rede),
            TipoConexaoImpressora.WINDOWS: (self._campo_nome_fila,),
            TipoConexaoImpressora.ARQUIVO: (self._campo_caminho_arquivo,),
        }

        self._campo_colunas = QSpinBox()
        self._campo_colunas.setMinimum(COLUNAS_MINIMAS)
        self._campo_colunas.setMaximum(COLUNAS_MAXIMAS)
        self._campo_colunas.setSuffix(" colunas")
        self._campo_colunas.setValue(impressora.colunas if impressora else COLUNAS_PADRAO)
        self._formulario.addRow("Largura da bobina", self._campo_colunas)

        # "Ativa" só existe na edição: `criar_impressora` sempre nasce ativa, e
        # um checkbox desmarcável no cadastro só produziria impressora nascida
        # morta. Desativar é decisão posterior, sobre algo que já existe.
        self._campo_ativa: QCheckBox | None = None
        if impressora is not None:
            self._campo_ativa = QCheckBox("Impressora em uso")
            self._campo_ativa.setChecked(impressora.ativa)
            self._formulario.addRow("Ativa", self._campo_ativa)

        layout.addLayout(self._formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Salvar")
        botoes.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

        self._atualizar_campos_visiveis()

    def _campo_texto(self, rotulo: str, valor: str, dica: str) -> QLineEdit:
        campo = QLineEdit(valor)
        campo.setPlaceholderText(dica)
        self._formulario.addRow(rotulo, campo)
        return campo

    def _atualizar_campos_visiveis(self) -> None:
        """Esconde os campos que não são do tipo de conexão escolhido."""
        tipo_atual = self._combo_tipo.currentData()
        for tipo, campos in self._campos_por_tipo.items():
            for campo in campos:
                # `setRowVisible` some com o rótulo junto com o campo — esconder
                # só o QLineEdit deixaria o texto órfão flutuando no formulário.
                self._formulario.setRowVisible(campo, tipo is tipo_atual)
        self.adjustSize()

    def resultado(self) -> tuple[str, TipoConexaoImpressora, dict[str, object]]:
        """Devolve (nome, tipo, parâmetros) prontos para `**kwargs` no service.

        Manda todos os campos, inclusive os escondidos: `CardapioService` limpa
        os que o tipo escolhido não usa e só valida os que usa. Filtrar aqui
        duplicaria essa regra na tela.
        """
        parametros: dict[str, object] = {
            "vendor_id": _ou_nulo(self._campo_vendor_id),
            "product_id": _ou_nulo(self._campo_product_id),
            "porta_serial": _ou_nulo(self._campo_porta_serial),
            "baudrate": _ou_nulo(self._campo_baudrate),
            "host": _ou_nulo(self._campo_host),
            "porta_rede": _ou_nulo(self._campo_porta_rede),
            "nome_fila": _ou_nulo(self._campo_nome_fila),
            "caminho_arquivo": _ou_nulo(self._campo_caminho_arquivo),
            "colunas": self._campo_colunas.value(),
        }
        if self._campo_ativa is not None:
            parametros["ativa"] = self._campo_ativa.isChecked()
        return self._campo_nome.text().strip(), self._combo_tipo.currentData(), parametros


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


def _texto(impressora: Impressora | None, campo: str) -> str:
    if impressora is None:
        return ""
    valor = getattr(impressora, campo)
    return "" if valor is None else str(valor)


def _ou_nulo(campo: QLineEdit) -> str | None:
    return campo.text().strip() or None
