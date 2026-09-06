"""Tela de login: split-screen (identidade da marca + terminal de autenticação
por PIN) com numpad e alternador de tema claro/escuro escopado a esta tela.

Suporte a teclado físico: dígitos 0-9, Backspace, Enter e Escape (limpar)
funcionam junto com o clique nos botões do numpad.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QKeyEvent,
    QLinearGradient,
    QPaintEvent,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.domain.usuario import Usuario
from gestor_comercial.services.auth_service import AuthService, PIN_MAX_DIGITOS
from gestor_comercial.services.exceptions import NaoAutorizadoError
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.tokens import TEMA_CLARO_LOGIN as _TEMA_CLARO
from gestor_comercial.ui.theme.tokens import TEMA_ESCURO_LOGIN as _TEMA_ESCURO
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

# Os dicts de paleta (`TEMA_ESCURO_LOGIN`/`TEMA_CLARO_LOGIN`) vivem em
# `ui/theme/tokens.py`, mas são uma cópia congelada só desta tela --
# propositalmente isolada do redesign "Concreto" do resto do shell
# (`TEMA_ESCURO`/`TEMA_CLARO`, consumidos via `ThemeController`), pra manter
# o login visualmente intacto. Esta tela ainda mantém seu próprio
# `setStyleSheet` local (ver `_aplicar_tema`) porque tem widgets/gradientes
# só dela (o painel de marca, o logo isométrico) que não fazem sentido no
# QSS genérico do app -- mas troca de tema aqui também empurra pro
# `ThemeController`, pra sidebar/shell entrarem já no tema certo depois do
# login.


def _interpolar_cor(a: QColor, b: QColor, fator: float) -> QColor:
    return QColor(
        round(a.red() + (b.red() - a.red()) * fator),
        round(a.green() + (b.green() - a.green()) * fator),
        round(a.blue() + (b.blue() - a.blue()) * fator),
    )


class _LogoIsometrico(QWidget):
    """Monograma "GC" com efeito de extrusão isométrica (bloco 3D), desenhado
    via `QPainter` — sem nenhum asset PNG novo. Trocar de tema só muda a
    paleta e chama `update()`; nenhum widget é recriado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._clara = QColor("#f0d38a")
        self._media = QColor("#caa04d")
        self._escura = QColor("#7c5f28")
        self.setMinimumSize(96, 96)

    def definir_paleta(self, clara: str, media: str, escura: str) -> None:
        self._clara = QColor(clara)
        self._media = QColor(media)
        self._escura = QColor(escura)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        fonte = QFont("Archivo Black", weight=QFont.Weight.Black)
        fonte.setPixelSize(int(self.height() * 0.56))

        caminho = QPainterPath()
        caminho.addText(0, 0, fonte, "GC")
        limites = caminho.boundingRect()
        escala = min(
            (self.width() * 0.82) / max(limites.width(), 1),
            (self.height() * 0.82) / max(limites.height(), 1),
        )

        centro = QRectF(self.rect()).center()
        offset_texto = QPointF(
            centro.x() - (limites.x() + limites.width() / 2) * escala,
            centro.y() - (limites.y() + limites.height() / 2) * escala,
        )

        # Sombra suave no chão, no espaço do widget (antes do scale do glifo)
        # para não esticar junto com as letras.
        sombra = QRadialGradient(centro.x(), centro.y() + limites.height() * escala * 0.62, self.width() * 0.5)
        sombra.setColorAt(0.0, QColor(0, 0, 0, 70))
        sombra.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(sombra))
        painter.drawEllipse(
            centro + QPointF(escala * 6, limites.height() * escala * 0.55),
            self.width() * 0.42,
            self.height() * 0.14,
        )

        painter.translate(offset_texto)
        painter.scale(escala, escala)

        # Extrusão em degraus nítidos (poucas camadas bem contrastadas, cada
        # uma com contorno próprio) em vez de muitas camadas finas — isso é o
        # que dá o efeito de bloco "faceado" da referência, não um borrão de
        # sombra.
        profundidade_px = 6.0
        etapas = 5
        vetor = QPointF(1.05, 1.05)
        contorno = QPen(self._escura)
        contorno.setWidthF(0.6)
        for i in range(etapas, 0, -1):
            fator = i / etapas
            cor_camada = _interpolar_cor(self._media, self._escura, fator)
            painter.setPen(contorno)
            painter.setBrush(QBrush(cor_camada))
            painter.drawPath(caminho.translated(vetor * (profundidade_px * fator)))

        # Face frontal: gradiente diagonal claro→base simulando luz vindo de
        # cima-esquerda, com contorno escuro para separar bem do fundo.
        gradiente_face = QLinearGradient(limites.topLeft(), limites.bottomRight())
        gradiente_face.setColorAt(0.0, _interpolar_cor(self._clara, QColor("#ffffff"), 0.35))
        gradiente_face.setColorAt(1.0, self._clara)
        painter.setPen(contorno)
        painter.setBrush(QBrush(gradiente_face))
        painter.drawPath(caminho)

        # Aresta de brilho fina no topo-esquerda da face frontal.
        brilho = QPen(_interpolar_cor(self._clara, QColor("#ffffff"), 0.6))
        brilho.setWidthF(0.9)
        painter.setPen(brilho)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(caminho)

        painter.end()


def _construir_qss(t: dict[str, str]) -> str:
    return f"""
    QWidget#loginRoot {{ background: {t['bg_marca']}; }}

    /* Reset: base.qss define `QWidget {{ background: ... }}` globalmente, o
    que vaza como um retângulo escuro atrás de cada QLabel se não for
    zerado aqui — labels e frames de texto desta tela são todos
    transparentes por padrão; só os cartões/pílulas abaixo recebem
    fundo próprio. */
    QWidget#loginRoot QLabel {{ background: transparent; }}

    /* Mesmo motivo do reset acima: sem isso a barra que envolve a pílula de
    tema (um `QWidget` puro, sem cartão próprio) herda o fundo genérico de
    `QWidget` do `base.qss` e aparece como um retângulo preto sólido por
    cima do fundo fosco do painel do terminal. */
    QWidget#loginBarraTema {{ background: transparent; }}

    /* Canto superior-esquerdo com leve mancha azulada + linha vertical
    separando os dois painéis (fiel à referência: lado direito um tom mais
    claro que o esquerdo). */
    QFrame#loginPainelMarca {{
        background: qradialgradient(cx:0.05, cy:0.05, radius:1.7, fx:0.05, fy:0.05,
            stop:0 {t['canto_azul']}, stop:0.4 {t['bg_marca']}, stop:1 {t['bg_marca']});
        border-right: 1px solid {t['divisor_vertical']};
    }}
    QLabel#loginMarcaSelo {{ color: {t['texto_fraquissimo']}; font-size: 11px; letter-spacing: 2px; }}
    QLabel#loginTitulo {{ color: {t['texto']}; font-size: 30px; font-weight: 700; }}
    QLabel#loginTituloAcento {{ color: {t['acento']}; font-size: 30px; font-weight: 700; }}
    QLabel#loginSubtitulo {{ color: {t['texto_fraco']}; font-size: 13px; }}
    QFrame#loginDivisor {{ background: {t['borda']}; max-height: 1px; min-height: 1px; }}
    QLabel#loginRodapeMarca {{ color: {t['texto']}; font-size: 14px; font-weight: 700; }}
    QLabel#loginRodapeTags {{ color: {t['texto_fraquissimo']}; font-size: 10px; letter-spacing: 1px; }}

    QFrame#loginPainelTerminal {{ background: {t['bg_terminal']}; }}
    QFrame#loginCartao {{
        background: {t['superficie']};
        border: 1px solid {t['borda']};
        border-radius: 18px;
    }}
    QLabel#loginTerminalId {{ color: {t['texto_fraquissimo']}; font-size: 10px; letter-spacing: 2px; }}
    QLabel#loginTerminalTitulo {{ color: {t['texto']}; font-size: 20px; font-weight: 700; }}
    QLabel#loginStatusOnline {{
        color: {t['sucesso']};
        background: transparent;
        border: 1px solid {t['borda']};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QLabel#loginCampoRotulo {{ color: {t['texto_fraquissimo']}; font-size: 10px; letter-spacing: 1px; }}
    QPushButton#loginVerPin {{
        background: transparent;
        color: {t['texto_fraco']};
        border: none;
        font-size: 10px;
        letter-spacing: 1px;
        font-weight: 600;
        padding: 0px;
    }}
    QPushButton#loginVerPin:hover {{ color: {t['texto']}; }}

    QComboBox#loginOperador, QLineEdit#loginPin {{
        background: {t['superficie_2']};
        border: 1px solid {t['borda']};
        border-radius: 10px;
        padding: 10px 14px;
        color: {t['texto']};
        font-size: 14px;
    }}
    QComboBox#loginOperador:focus, QLineEdit#loginPin:focus {{ border: 1px solid {t['acento']}; }}
    QLineEdit#loginPin {{ font-size: 22px; letter-spacing: 6px; }}
    QComboBox#loginOperador::drop-down {{ border: none; width: 20px; }}
    QComboBox#loginOperador::down-arrow {{ image: none; width: 0px; height: 0px; }}
    QComboBox#loginOperador QAbstractItemView {{
        background: {t['superficie_2']};
        border: 1px solid {t['borda']};
        border-radius: 8px;
        padding: 4px;
        outline: none;
        color: {t['texto']};
        selection-background-color: {t['acento']};
        selection-color: {t['acento_texto']};
    }}
    QComboBox#loginOperador QAbstractItemView::item {{
        padding: 8px 10px;
        min-height: 22px;
        border: none;
        color: {t['texto']};
        background: {t['superficie_2']};
    }}
    QComboBox#loginOperador QAbstractItemView::item:hover,
    QComboBox#loginOperador QAbstractItemView::item:selected {{
        background: {t['acento']};
        color: {t['acento_texto']};
    }}

    QPushButton#loginTecla {{
        background: {t['superficie_2']};
        border: 1px solid {t['borda']};
        border-radius: 10px;
        color: {t['texto']};
        font-size: 17px;
        font-weight: 600;
        padding: 14px 0px;
    }}
    QPushButton#loginTecla:hover {{ background: {t['borda']}; }}
    QPushButton#loginTecla:pressed {{ background: {t['acento']}; color: {t['acento_texto']}; }}
    QPushButton#loginTecla[apagar="true"] {{ color: {t['perigo']}; }}

    QPushButton#loginConfirmar {{
        background: {t['acento']};
        color: {t['acento_texto']};
        border: none;
        border-radius: 10px;
        padding: 14px 0px;
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QPushButton#loginConfirmar:hover {{ background: {t['acento']}; }}
    QPushButton#loginConfirmar:disabled {{ background: {t['borda']}; color: {t['texto_fraquissimo']}; }}

    QLabel#loginErro {{ color: {t['perigo']}; font-size: 12px; }}
    QLabel#loginRodapeVersao {{ color: {t['texto_fraquissimo']}; font-size: 10px; }}
    """


class LoginView(QWidget):
    """Tela de login: identidade da marca à esquerda, terminal de PIN à direita."""

    autenticado = Signal(Usuario)

    def __init__(self, auth_service: AuthService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("loginRoot")
        self._auth_service = auth_service
        self._pin = ""
        self._pin_visivel = False

        self._montar_layout()
        self._carregar_usuarios()

        # Sem isto, o PIN só passa a ser lido depois de um clique manual: no
        # abrir da tela nenhum widget tem foco (ou o combo de operador herda
        # o foco padrão e engole os dígitos como busca incremental de item),
        # então o teclado físico não alcança `keyPressEvent` desta view.
        # `NoFocus` nos filhos clicáveis garante que o foco nunca sai daqui
        # -- ver também `showEvent`, chamado de novo sempre que a tela volta
        # a aparecer (ex.: depois de deslogar).
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._combo_usuario.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._botao_ver_pin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._botao_confirmar.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        controlador = ThemeController.instancia()
        self._aplicar_tema(_TEMA_CLARO if controlador.claro else _TEMA_ESCURO)
        # Tema agora só se troca na tela de Configurações (dentro do shell
        # autenticado) — se o usuário deslogar depois de trocar, o login
        # precisa refletir sem precisar de um seletor próprio aqui.
        controlador.mudou.connect(self._ao_mudar_tema)

    def _ao_mudar_tema(self, _tokens: dict[str, str]) -> None:
        """Repinta o logo isométrico, que é `QPainter` e não pega o QSS global.

        Método ligado, e não `lambda`: o `ThemeController` é singleton e vive o
        processo inteiro, então uma conexão sem objeto receptor nunca seria
        desfeita e seguraria a tela junto. Hoje a `LoginView` também vive o
        processo inteiro e isso não cresce — mas basta alguém passar a recriar
        a tela para virar vazamento de verdade (§3.14). Com `self` do outro
        lado, o Qt desconecta sozinho quando a view morre.
        """
        controlador = ThemeController.instancia()
        self._aplicar_tema(_TEMA_CLARO if controlador.claro else _TEMA_ESCURO)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        # Só o `corpo` (as duas colunas) ocupa a raiz -- assim a borda direita
        # do painel da marca (linha vertical divisória) nasce em y=0 e desce
        # contínua até a base, sem um retângulo/barra de largura total por
        # cima interrompendo a divisão no topo. A pílula de tema entra
        # dentro do próprio painel do terminal (ver `_montar_painel_terminal`).
        layout_raiz = QHBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)
        layout_raiz.setSpacing(0)
        layout_raiz.addWidget(self._montar_painel_marca(), 6)
        layout_raiz.addWidget(self._montar_painel_terminal(), 5)

    def _montar_painel_marca(self) -> QWidget:
        painel = PainelPontilhado()
        painel.setObjectName("loginPainelMarca")
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(56, 56, 56, 40)
        layout.setSpacing(0)

        selo = QLabel("●  GESTOR COMERCIAL  ·  PDV FOOD TRUCK")
        selo.setObjectName("loginMarcaSelo")
        layout.addWidget(selo)
        layout.addStretch(2)

        self._logo = _LogoIsometrico()
        self._logo.setFixedSize(300, 300)
        layout.addWidget(self._logo)
        layout.addSpacing(28)

        titulo1 = QLabel("Gestor Comercial")
        titulo1.setObjectName("loginTitulo")
        layout.addWidget(titulo1)
        titulo2 = QLabel("Ponto de Venda")
        titulo2.setObjectName("loginTituloAcento")
        layout.addWidget(titulo2)
        layout.addSpacing(14)

        subtitulo = QLabel("Comandas, caixa e cardápio operando 100% offline,\ndireto na máquina do food truck.")
        subtitulo.setObjectName("loginSubtitulo")
        layout.addWidget(subtitulo)
        layout.addStretch(3)

        divisor = QFrame()
        divisor.setObjectName("loginDivisor")
        divisor.setFixedWidth(48)
        layout.addWidget(divisor)
        layout.addSpacing(14)

        rodape_marca = QLabel("Gestor Comercial Python")
        rodape_marca.setObjectName("loginRodapeMarca")
        layout.addWidget(rodape_marca)
        rodape_tags = QLabel("OFFLINE FIRST  ·  BAIXO CONSUMO DE RAM  ·  SQLITE LOCAL")
        rodape_tags.setObjectName("loginRodapeTags")
        layout.addWidget(rodape_tags)

        return painel

    def _montar_painel_terminal(self) -> QWidget:
        painel = QFrame()
        painel.setObjectName("loginPainelTerminal")
        layout_externo = QVBoxLayout(painel)
        layout_externo.setContentsMargins(0, 0, 56, 0)
        layout_externo.setSpacing(0)
        layout_externo.addStretch()

        self._cartao = QFrame()
        self._cartao.setObjectName("loginCartao")
        self._cartao.setFixedWidth(360)
        layout = QVBoxLayout(self._cartao)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(0)

        cabecalho = QHBoxLayout()
        bloco_titulo = QVBoxLayout()
        bloco_titulo.setSpacing(2)
        terminal_id = QLabel("TERMINAL 01")
        terminal_id.setObjectName("loginTerminalId")
        bloco_titulo.addWidget(terminal_id)
        terminal_titulo = QLabel("Autenticação")
        terminal_titulo.setObjectName("loginTerminalTitulo")
        bloco_titulo.addWidget(terminal_titulo)
        cabecalho.addLayout(bloco_titulo)
        cabecalho.addStretch()
        status = QLabel("● ONLINE")
        status.setObjectName("loginStatusOnline")
        cabecalho.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(cabecalho)
        layout.addSpacing(20)

        rotulo_operador = QLabel("OPERADOR")
        rotulo_operador.setObjectName("loginCampoRotulo")
        layout.addWidget(rotulo_operador)
        layout.addSpacing(6)
        self._combo_usuario = QComboBox()
        self._combo_usuario.setObjectName("loginOperador")
        layout.addWidget(self._combo_usuario)
        layout.addSpacing(16)

        linha_pin = QHBoxLayout()
        rotulo_pin = QLabel("PIN DE ACESSO")
        rotulo_pin.setObjectName("loginCampoRotulo")
        linha_pin.addWidget(rotulo_pin)
        linha_pin.addStretch()
        self._botao_ver_pin = QPushButton("VER")
        self._botao_ver_pin.setObjectName("loginVerPin")
        self._botao_ver_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_ver_pin.clicked.connect(self._alternar_visibilidade_pin)
        linha_pin.addWidget(self._botao_ver_pin)
        layout.addLayout(linha_pin)
        layout.addSpacing(6)

        self._campo_pin = QLineEdit()
        self._campo_pin.setObjectName("loginPin")
        self._campo_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_pin.setMaxLength(PIN_MAX_DIGITOS)
        self._campo_pin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._campo_pin.setReadOnly(True)
        self._campo_pin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._campo_pin)
        layout.addSpacing(16)

        layout.addLayout(self._montar_numpad())
        layout.addSpacing(16)

        self._label_erro = QLabel("")
        self._label_erro.setObjectName("loginErro")
        self._label_erro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_erro.setFixedHeight(18)
        layout.addWidget(self._label_erro)
        layout.addSpacing(6)

        self._botao_confirmar = QPushButton("ENTER / CONFIRMAR")
        self._botao_confirmar.setObjectName("loginConfirmar")
        self._botao_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_confirmar.clicked.connect(self._tentar_login)
        layout.addWidget(self._botao_confirmar)
        layout.addSpacing(14)

        rodape = QLabel("GESTOR COMERCIAL PDV  ·  100% OFFLINE")
        rodape.setObjectName("loginRodapeVersao")
        rodape.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(rodape)

        layout_externo.addWidget(self._cartao, 0, Qt.AlignmentFlag.AlignCenter)
        layout_externo.addStretch()
        return painel

    def _montar_numpad(self) -> QGridLayout:
        grade = QGridLayout()
        grade.setSpacing(10)

        teclas = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("LIMPAR", 3, 0), ("0", 3, 1), ("⌫", 3, 2),
        ]
        for rotulo, linha, coluna in teclas:
            botao = QPushButton(rotulo)
            botao.setObjectName("loginTecla")
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.setMinimumHeight(48)
            botao.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # Clicar no numpad não pode roubar o foco da tela: senão o
            # próximo dígito digitado no teclado físico vai parar no botão
            # (que ignora), exigindo outro clique pra "acordar" o teclado.
            botao.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if rotulo == "LIMPAR":
                botao.clicked.connect(self._limpar_pin)
            elif rotulo == "⌫":
                botao.setProperty("apagar", True)
                botao.clicked.connect(self._apagar_digito_pin)
            else:
                botao.clicked.connect(lambda _=False, d=rotulo: self._adicionar_digito_pin(d))
            grade.addWidget(botao, linha, coluna)
        return grade

    # ------------------------------------------------------------------
    # Tema
    # ------------------------------------------------------------------

    def _aplicar_tema(self, tokens: dict[str, str]) -> None:
        """Reaplica só a folha de estilo — nenhum widget é recriado."""
        self.setStyleSheet(_construir_qss(tokens))
        self._logo.definir_paleta(tokens["logo_clara"], tokens["logo_media"], tokens["logo_escura"])

    # ------------------------------------------------------------------
    # PIN / numpad
    # ------------------------------------------------------------------

    def _adicionar_digito_pin(self, digito: str) -> None:
        if len(self._pin) >= PIN_MAX_DIGITOS:
            return
        self._pin += digito
        self._campo_pin.setText(self._pin)
        self._label_erro.setText("")

    def _apagar_digito_pin(self) -> None:
        self._pin = self._pin[:-1]
        self._campo_pin.setText(self._pin)

    def _limpar_pin(self) -> None:
        self._pin = ""
        self._campo_pin.setText("")
        self._label_erro.setText("")

    def _alternar_visibilidade_pin(self) -> None:
        self._pin_visivel = not self._pin_visivel
        modo = QLineEdit.EchoMode.Normal if self._pin_visivel else QLineEdit.EchoMode.Password
        self._campo_pin.setEchoMode(modo)
        self._botao_ver_pin.setText("OCULTAR" if self._pin_visivel else "VER")

    # ------------------------------------------------------------------
    # Teclado físico
    # ------------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        # Chamado toda vez que esta tela volta a ficar visível (abertura do
        # app e cada logout) -- garante que o PIN já é lido sem precisar de
        # um clique manual antes.
        self.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        texto = event.text()
        if texto.isdigit():
            self._adicionar_digito_pin(texto)
        elif event.key() == Qt.Key.Key_Backspace:
            self._apagar_digito_pin()
        elif event.key() == Qt.Key.Key_Escape:
            self._limpar_pin()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._tentar_login()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Autenticação
    # ------------------------------------------------------------------

    def _carregar_usuarios(self) -> None:
        funcionarios = self._auth_service.listar_ativos()

        if not funcionarios:
            self._label_erro.setText("Nenhum usuário disponível no sistema.")
            self._combo_usuario.setEnabled(False)
            self._botao_confirmar.setEnabled(False)
            return

        for funcionario in funcionarios:
            self._combo_usuario.addItem(funcionario.nome, funcionario)
        self._combo_usuario.setCurrentIndex(0)

    def _tentar_login(self) -> None:
        funcionario_selecionado = self._combo_usuario.currentData()

        if not funcionario_selecionado:
            self._label_erro.setText("Selecione um operador.")
            return

        if not self._pin:
            self._label_erro.setText("Digite o PIN.")
            return

        try:
            # Autentica contra o operador ESCOLHIDO no dropdown, não contra
            # "qualquer usuário ativo cujo PIN bata" — necessário desde que
            # dois operadores (Caixa Turno - Manhã/Noite) passaram a poder
            # compartilhar o mesmo PIN (ver `AuthService.login_como`).
            funcionario = self._auth_service.login_como(funcionario_selecionado.id, self._pin)
        except NaoAutorizadoError as erro:
            self._label_erro.setText(str(erro))
            self._limpar_pin()
            return

        self._limpar_pin()
        self.autenticado.emit(funcionario)
