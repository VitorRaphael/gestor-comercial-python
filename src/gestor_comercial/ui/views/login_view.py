"""Tela de login refatorada — seleção de usuário + campo de senha padrão.

Suporte completo a teclado físico: navegação via Tab, submissão via Enter,
e campo de senha com visibilidade toggle.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.usuario import Usuario
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.exceptions import NaoAutorizadoError


class LoginView(QWidget):
    """Tela de login moderna: dropdown de usuário + campo de senha + teclado físico."""

    autenticado = Signal(Usuario)

    def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("tela-login")
        self._auth_service = auth_service

        self._montar_layout()
        self._carregar_usuarios()

    def _montar_layout(self) -> None:
        cartao = QFrame(self)
        cartao.setObjectName("cartao-login")
        cartao.setFixedWidth(360)
        layout_cartao = QVBoxLayout(cartao)
        layout_cartao.setContentsMargins(28, 32, 28, 32)
        layout_cartao.setSpacing(0)

        marca = QLabel("Gestor Comercial")
        marca.setStyleSheet("font-weight: 600; font-size: 16px;")
        marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_cartao.addWidget(marca)

        subtitulo = QLabel("Faça login para continuar")
        subtitulo.setObjectName("login-subtitulo")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_cartao.addSpacing(10)
        layout_cartao.addWidget(subtitulo)
        layout_cartao.addSpacing(18)

        # Seletor de usuário
        label_usuario = QLabel("Usuário:")
        layout_cartao.addWidget(label_usuario)
        self._combo_usuario = QComboBox()
        self._combo_usuario.setObjectName("combo-usuario")
        layout_cartao.addWidget(self._combo_usuario)
        layout_cartao.addSpacing(12)

        # Campo de senha
        label_senha = QLabel("Senha:")
        layout_cartao.addWidget(label_senha)
        self._campo_senha = QLineEdit()
        self._campo_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_senha.setPlaceholderText("Digite o PIN")
        self._campo_senha.returnPressed.connect(self._tentar_login)
        layout_cartao.addWidget(self._campo_senha)

        # Label de erro
        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #f43f5e; font-size: 12px;")
        self._label_erro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_erro.setFixedHeight(18)
        layout_cartao.addWidget(self._label_erro)
        layout_cartao.addSpacing(12)

        # Botão de submissão
        self._botao_entrar = QPushButton("Acessar")
        self._botao_entrar.setProperty("variante", "primario")
        self._botao_entrar.clicked.connect(self._tentar_login)
        layout_cartao.addWidget(self._botao_entrar)

        layout_externo = QVBoxLayout(self)
        layout_externo.addStretch()
        layout_externo.addWidget(cartao, 0, Qt.AlignmentFlag.AlignCenter)
        layout_externo.addStretch()

    def _carregar_usuarios(self) -> None:
        """Carrega funcionários ativos no dropdown e pré-seleciona o padrão (ADMIN/Gerente)."""
        funcionarios = self._auth_service.listar_ativos()

        if not funcionarios:
            self._label_erro.setText("Nenhum usuário disponível no sistema.")
            self._combo_usuario.setEnabled(False)
            self._campo_senha.setEnabled(False)
            self._botao_entrar.setEnabled(False)
            return

        for funcionario in funcionarios:
            self._combo_usuario.addItem(funcionario.nome, funcionario)

        # Pré-seleciona o primeiro usuário (idealmente o ADMIN/Gerente)
        # Se quiser priorizar GERENTE especificamente, adicione lógica aqui
        self._combo_usuario.setCurrentIndex(0)

        # Focus automático no campo de senha já que o usuário está pré-selecionado
        self._campo_senha.setFocus()

    def _tentar_login(self) -> None:
        """Autentica o usuário selecionado com a senha (PIN) fornecida."""
        funcionario_selecionado = self._combo_usuario.currentData()
        pin_digitado = self._campo_senha.text()

        if not funcionario_selecionado:
            self._label_erro.setText("Selecione um usuário.")
            return

        if not pin_digitado:
            self._label_erro.setText("Digite a senha.")
            self._campo_senha.setFocus()
            return

        try:
            # Autentica pelo PIN
            funcionario = self._auth_service.login(pin_digitado)

            # Valida se é o usuário selecionado
            if funcionario.id != funcionario_selecionado.id:
                self._label_erro.setText("A senha não corresponde ao usuário selecionado.")
                self._campo_senha.clear()
                self._campo_senha.setFocus()
                return

        except NaoAutorizadoError as erro:
            self._label_erro.setText(str(erro))
            self._campo_senha.clear()
            self._campo_senha.setFocus()
            return

        # Sucesso: limpa e emite sinal
        self._campo_senha.clear()
        self.autenticado.emit(funcionario)
