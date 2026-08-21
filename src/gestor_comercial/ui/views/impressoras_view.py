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
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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

_COLUNAS = ["Nome", "Conexão", "Destino", "Bobina", "Padrão", "Status"]

_ROTULOS_TIPO = {
    TipoConexaoImpressora.USB: "USB",
    TipoConexaoImpressora.SERIAL: "Serial",
    TipoConexaoImpressora.REDE: "Rede",
    TipoConexaoImpressora.WINDOWS: "Windows",
    TipoConexaoImpressora.ARQUIVO: "Arquivo (.txt)",
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

        cabecalho = QHBoxLayout()
        titulo = QLabel("Impressoras")
        titulo.setStyleSheet("font-weight: 600; font-size: 18px;")
        cabecalho.addWidget(titulo)
        cabecalho.addStretch()

        botao_nova = QPushButton("Nova impressora")
        botao_nova.setProperty("variante", "primario")
        botao_nova.clicked.connect(self._criar)
        cabecalho.addWidget(botao_nova)
        layout.addLayout(cabecalho)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout.addWidget(self._label_erro)

        self._aviso = AvisoDeImpressao()
        layout.addWidget(self._aviso)

        self._tabela = QTableWidget(0, len(_COLUNAS))
        self._tabela.setHorizontalHeaderLabels(_COLUNAS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tabela.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tabela)

        acoes = QHBoxLayout()
        self._botao_editar = QPushButton("Editar")
        self._botao_editar.clicked.connect(self._editar)
        acoes.addWidget(self._botao_editar)

        self._botao_padrao = QPushButton("Definir como padrão")
        self._botao_padrao.setProperty("variante", "secundario")
        self._botao_padrao.clicked.connect(self._definir_padrao)
        acoes.addWidget(self._botao_padrao)

        self._botao_teste = QPushButton("Imprimir teste")
        self._botao_teste.setProperty("variante", "secundario")
        self._botao_teste.clicked.connect(self._imprimir_teste)
        acoes.addWidget(self._botao_teste)

        self._botao_excluir = QPushButton("Excluir")
        self._botao_excluir.setProperty("variante", "perigo")
        self._botao_excluir.clicked.connect(self._excluir)
        acoes.addWidget(self._botao_excluir)
        acoes.addStretch()
        layout.addLayout(acoes)

        self._label_ajuda = QLabel(
            "A impressora padrão recebe o recibo do cliente, o fechamento de caixa e "
            "os itens de categorias sem impressora própria. O tipo Arquivo grava o "
            "cupom num .txt — serve para conferir tudo antes de a impressora chegar."
        )
        self._label_ajuda.setProperty("variante", "fraco")
        self._label_ajuda.setWordWrap(True)
        layout.addWidget(self._label_ajuda)

    def atualizar(self) -> None:
        self._label_erro.setText("")
        # Cadastro alterado envelhece o aviso do último teste: a impressora que
        # respondeu pode ser justamente a que acabou de mudar de porta.
        self._aviso.limpar()
        self._impressoras = self._service.listar_impressoras()
        self._tabela.setRowCount(len(self._impressoras))
        for linha, impressora in enumerate(self._impressoras):
            self._preencher_linha(linha, impressora)

    def _preencher_linha(self, linha: int, impressora: Impressora) -> None:
        tipo = _ROTULOS_TIPO.get(impressora.tipo_conexao, impressora.tipo_conexao.value)
        self._tabela.setItem(linha, 0, QTableWidgetItem(impressora.nome))
        self._tabela.setItem(linha, 1, QTableWidgetItem(tipo))
        self._tabela.setItem(linha, 2, QTableWidgetItem(_descricao_destino(impressora)))
        self._tabela.setItem(linha, 3, QTableWidgetItem(f"{impressora.colunas} colunas"))
        self._tabela.setItem(linha, 4, QTableWidgetItem("Sim" if impressora.padrao else "—"))
        status = "Ativa" if impressora.ativa else "Desativada"
        self._tabela.setItem(linha, 5, QTableWidgetItem(status))

    def _impressora_selecionada(self) -> Impressora | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._impressoras):
            return None
        return self._impressoras[linha]

    def _criar(self) -> None:
        modal = _ImpressoraDialog("Nova impressora", self)
        if modal.exec() != QDialog.DialogCode.Accepted:
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
        if modal.exec() != QDialog.DialogCode.Accepted:
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
