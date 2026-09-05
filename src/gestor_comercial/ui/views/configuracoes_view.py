"""Tela de Configurações: preferências gerais do app + Senhas e Acesso.

Hoje tem duas seções: "Selecionar Tema" (claro/escuro, que antes vivia
duplicado na tela de Login e no rodapé da sidebar — ver `ThemeController`) e
"Senhas e Acesso" (§3.13), o módulo de segredos operacionais da loja — cascata
de 3 níveis (Senha de Login, Senha Operacional/Caixa, Senha Master/Dono) e
CPF do Dono — sempre mascarados na tela, cada troca exigindo o segredo de
nível acima (`LojaConfigService`). A troca do Nível 1 (Login) é a única que
aceita duas credenciais alternativas (Nível 2 OU Nível 3): por isso
`_alterar_senha_login` não passa um rótulo fixo de credencial, e sim chama
`LojaConfigService.alterar_senha_login`, que já faz essa checagem "ou" —
`_AlterarSegredoDialog` só coleta os dois valores, sem saber qual regra vale.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.loja_config_service import MASCARA, LojaConfigService
from gestor_comercial.ui.theme.controller import ThemeController

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)


class ConfiguracoesView(QWidget):
    """Central de preferências do app: tema e Senhas e Acesso da loja."""

    def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loja_config: LojaConfigService = auth_service.loja_config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(4)

        eyebrow = QLabel("PREFERÊNCIAS")
        eyebrow.setObjectName("configEyebrow")
        layout.addWidget(eyebrow)

        titulo = QLabel("Configurações")
        titulo.setObjectName("configTitulo")
        layout.addWidget(titulo)

        subtitulo = QLabel("Preferências gerais do sistema")
        subtitulo.setObjectName("configSubtitulo")
        layout.addWidget(subtitulo)

        layout.addSpacing(28)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        layout.addWidget(self._label_erro)

        layout.addWidget(self._montar_card_tema())
        layout.addSpacing(20)
        layout.addWidget(self._montar_card_senhas())

        layout.addStretch()

    # ------------------------------------------------------------------
    # Seção "Selecionar Tema"
    # ------------------------------------------------------------------

    def _montar_card_tema(self) -> QWidget:
        bloco = QWidget()
        bloco_layout = QVBoxLayout(bloco)
        bloco_layout.setContentsMargins(0, 0, 0, 0)
        bloco_layout.setSpacing(10)

        secao_titulo = QLabel("SELECIONAR TEMA")
        secao_titulo.setObjectName("configSecaoTitulo")
        bloco_layout.addWidget(secao_titulo)

        cartao = QFrame()
        cartao.setObjectName("configCard")
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(20, 20, 20, 20)
        cartao_layout.setSpacing(10)

        descricao = QLabel("Escolha a aparência usada em todas as telas do sistema.")
        descricao.setProperty("variante", "fraco")
        cartao_layout.addWidget(descricao)

        pilula = QFrame()
        pilula.setProperty("variante", "pilula-tema")
        pilula.setFixedWidth(280)
        layout_pilula = QHBoxLayout(pilula)
        layout_pilula.setContentsMargins(3, 3, 3, 3)
        layout_pilula.setSpacing(0)

        botao_claro = QPushButton("MODO CLARO")
        botao_escuro = QPushButton("MODO ESCURO")
        for botao in (botao_claro, botao_escuro):
            botao.setProperty("variante", "temaBotao")
            botao.setCheckable(True)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            layout_pilula.addWidget(botao)

        controlador = ThemeController.instancia()
        grupo = QButtonGroup(self)
        grupo.setExclusive(True)
        grupo.addButton(botao_claro)
        grupo.addButton(botao_escuro)
        botao_claro.setChecked(controlador.claro)
        botao_escuro.setChecked(not controlador.claro)
        botao_claro.toggled.connect(lambda marcado: marcado and controlador.alternar_para(True))
        botao_escuro.toggled.connect(lambda marcado: marcado and controlador.alternar_para(False))
        controlador.mudou.connect(lambda _tokens: botao_claro.setChecked(controlador.claro))

        cartao_layout.addWidget(pilula)
        bloco_layout.addWidget(cartao)
        return bloco

    # ------------------------------------------------------------------
    # Seção "Senhas e Acesso" (§3.13)
    # ------------------------------------------------------------------

    def _montar_card_senhas(self) -> QWidget:
        bloco = QWidget()
        bloco_layout = QVBoxLayout(bloco)
        bloco_layout.setContentsMargins(0, 0, 0, 0)
        bloco_layout.setSpacing(10)

        secao_titulo = QLabel("SENHAS E ACESSO")
        secao_titulo.setObjectName("configSecaoTitulo")
        bloco_layout.addWidget(secao_titulo)

        cartao = QFrame()
        cartao.setObjectName("configCard")
        cartao_layout = QVBoxLayout(cartao)
        cartao_layout.setContentsMargins(20, 20, 20, 20)
        cartao_layout.setSpacing(4)

        descricao = QLabel(
            "Segredos operacionais da loja. Cada valor só é trocado informando o "
            "segredo de nível acima — nunca são exibidos, só mascarados."
        )
        descricao.setProperty("variante", "fraco")
        descricao.setWordWrap(True)
        cartao_layout.addWidget(descricao)
        cartao_layout.addSpacing(12)

        self._botao_senha_login, self._valor_senha_login = self._criar_linha_segredo(
            cartao_layout, "Senha de Login", self._alterar_senha_login
        )
        self._botao_senha_operacional, self._valor_senha_operacional = self._criar_linha_segredo(
            cartao_layout, "Senha Operacional (Gerente)", self._alterar_senha_operacional
        )
        self._botao_senha_master, self._valor_senha_master = self._criar_linha_segredo(
            cartao_layout, "Senha Master (Dono)", self._alterar_senha_master
        )
        self._botao_cpf_dono, self._valor_cpf_dono = self._criar_linha_segredo(
            cartao_layout, "CPF do Dono", self._alterar_cpf_dono
        )

        bloco_layout.addWidget(cartao)
        self._atualizar_secao_senhas()
        return bloco

    def _criar_linha_segredo(self, layout_pai: QVBoxLayout, rotulo: str, ao_clicar) -> tuple[QPushButton, QLabel]:
        linha = QHBoxLayout()
        linha.setSpacing(10)

        coluna_texto = QVBoxLayout()
        coluna_texto.setSpacing(2)
        label_rotulo = QLabel(rotulo)
        coluna_texto.addWidget(label_rotulo)
        label_valor = QLabel(MASCARA)
        label_valor.setProperty("variante", "fraco")
        coluna_texto.addWidget(label_valor)
        linha.addLayout(coluna_texto)
        linha.addStretch()

        botao = QPushButton("Alterar")
        botao.setProperty("variante", "secundario")
        botao.clicked.connect(ao_clicar)
        linha.addWidget(botao, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout_pai.addLayout(linha)
        return botao, label_valor

    def _atualizar_secao_senhas(self) -> None:
        # Todos os valores ficam sempre mascarados (§3.13) — o único estado
        # visível que muda é se o CPF do Dono já foi cadastrado ou não, pra
        # trocar o rótulo do botão e o texto do diálogo (primeiro cadastro
        # não exige "CPF atual", porque ele nunca existiu).
        cadastrado = self._loja_config.cpf_dono_definido()
        self._botao_cpf_dono.setText("Alterar" if cadastrado else "Cadastrar")
        self._valor_cpf_dono.setText(MASCARA if cadastrado else "Não cadastrado")

    def _alterar_senha_login(self) -> None:
        modal = _AlterarSegredoDialog(
            "Alterar Senha de Login",
            rotulo_credencial="Senha Operacional (Caixa) ou Senha Master (Dono)",
            rotulo_novo="Nova Senha de Login",
            parent=self,
        )
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        senha_nivel_2_ou_3, nova_senha = modal.resultado()

        self._label_erro.setText("")
        try:
            self._loja_config.alterar_senha_login(senha_nivel_2_ou_3, nova_senha)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_secao_senhas()

    def _alterar_senha_operacional(self) -> None:
        modal = _AlterarSegredoDialog(
            "Alterar Senha Operacional",
            rotulo_credencial="Senha Master (Dono) atual",
            rotulo_novo="Nova Senha Operacional",
            parent=self,
        )
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        senha_master, nova_senha = modal.resultado()

        self._label_erro.setText("")
        try:
            self._loja_config.alterar_senha_operacional(senha_master, nova_senha)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_secao_senhas()

    def _alterar_senha_master(self) -> None:
        modal = _AlterarSegredoDialog(
            "Alterar Senha Master",
            rotulo_credencial="CPF do Dono atual",
            rotulo_novo="Nova Senha Master",
            mascarar_credencial=False,
            parent=self,
        )
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        cpf_atual, nova_senha = modal.resultado()

        self._label_erro.setText("")
        try:
            self._loja_config.alterar_senha_master(cpf_atual, nova_senha)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_secao_senhas()

    def _alterar_cpf_dono(self) -> None:
        ja_cadastrado = self._loja_config.cpf_dono_definido()
        modal = _AlterarSegredoDialog(
            "Cadastrar CPF do Dono" if not ja_cadastrado else "Alterar CPF do Dono",
            rotulo_credencial="CPF do Dono atual",
            rotulo_novo="Novo CPF do Dono",
            exigir_credencial=ja_cadastrado,
            mascarar_credencial=False,
            mascarar_novo=False,
            parent=self,
        )
        if modal.exec() != QDialog.DialogCode.Accepted:
            return
        cpf_atual, novo_cpf = modal.resultado()

        self._label_erro.setText("")
        try:
            self._loja_config.definir_ou_alterar_cpf_dono(cpf_atual, novo_cpf)
        except _ERROS_SERVICE as erro:
            self._label_erro.setText(str(erro))
            return
        self._atualizar_secao_senhas()


class _AlterarSegredoDialog(QDialog):
    """Modal genérico de troca de segredo: credencial de nível acima (quando
    exigida) + novo valor. Reaproveitado pelas 3 linhas de "Senhas e Acesso"
    — só rótulos e mascaramento mudam entre elas."""

    def __init__(
        self,
        titulo: str,
        *,
        rotulo_credencial: str,
        rotulo_novo: str,
        exigir_credencial: bool = True,
        mascarar_credencial: bool = True,
        mascarar_novo: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(titulo)

        layout = QVBoxLayout(self)
        formulario = QFormLayout()

        self._campo_credencial: QLineEdit | None = None
        if exigir_credencial:
            self._campo_credencial = QLineEdit()
            if mascarar_credencial:
                self._campo_credencial.setEchoMode(QLineEdit.EchoMode.Password)
            formulario.addRow(rotulo_credencial, self._campo_credencial)

        self._campo_novo = QLineEdit()
        if mascarar_novo:
            self._campo_novo.setEchoMode(QLineEdit.EchoMode.Password)
        formulario.addRow(rotulo_novo, self._campo_novo)

        layout.addLayout(formulario)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Confirmar")
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)

    def resultado(self) -> tuple[str | None, str]:
        credencial = self._campo_credencial.text().strip() if self._campo_credencial else None
        novo_valor = self._campo_novo.text().strip()
        return credencial, novo_valor
