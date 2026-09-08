"""Modal "Novo funcionário": identidade com avatar, cargo em cards e situação.

Substitui o `_FuncionarioDialog` que morava dentro de `funcionarios_view.py` —
três campos empilhados num `QFormLayout` com a moldura de janela do sistema, um
`QComboBox` de setinha para o cargo e nenhuma pista do que cada cargo significa
no PDV. É o mesmo salto que o §9.4 deu no modal de lançar item, e pelo mesmo
motivo: quem cadastra a equipe é o pai do Vitor, de pé, e "Cargo: [Garçom ▾]"
não diz o que um garçom pode fazer no sistema.

## O que NÃO mudou

**Nenhuma regra de negócio, e nenhum método de service novo.** O diálogo não
conhece `FuncionarioService`: ele coleta `DadosFuncionario` e a view chama
`criar`/`editar` exatamente como antes. Cargo continua sendo validado no
service contra `CargoFuncionario` (§3.13) — a grade de cards é uma forma de
escolher, não uma segunda validação. A situação Ativo/Inativo também não virou
campo novo: o `Funcionario` nasce ativo em `criar()` como sempre, e a view
usa `ativar()`/`desativar()`, que já existiam, quando a escolha diverge do
estado atual.

O que o cargo libera no PDV (`ACESSO LIBERADO`, `APENAS PEDIDOS`) é a MESMA
derivação que o painel de detalhe da tela já fazia — não é dado gravado, é
leitura do cargo. Antes ela morava solta em `funcionarios_view` como um
conjunto de dois cargos; agora mora em `CARGOS`, junto do rótulo e da descrição
que o card mostra, para o texto do rodapé e o "ACESSO" do detalhe não poderem
divergir.

## Ciclo de vida (o RNF do Celeron, e §3.2/§3.9)

O briefing pediu, no vocabulário do Tkinter, `destroy()` + `unbind` + limpeza de
referências ao descartar. Em PySide6:

* **destroy** — `executar_modal()` (§3.2) faz o `deleteLater()` do diálogo
  depois de ler o resultado, e com ele vão os filhos, em C++. O que `done()`
  acrescenta é soltar o **escurecedor**, que é filho da janela principal e não
  do diálogo: sem isso, uma tarde de idas e voltas ao cadastro deixaria uma
  pilha de retângulos pretos invisíveis pendurada no `MainWindow`, que vive o
  processo inteiro;
* **unbind** — não há o que desamarrar, e isso é uma decisão, não um descuido.
  Sinal nenhum sai do diálogo: todo `connect` daqui liga um filho a um método
  do próprio diálogo, a conexão vive no filho, o filho morre com o pai. Sinal
  nenhum é ligado por `lambda` (§3.14) — os cards de cargo e as pílulas de
  situação entram por método ligado, e quem disparou sai do `sender()`.
  `tests/ui/test_funcionario_dialog.py` cobra as trinta idas e voltas;
* **timers** — não existe nenhum. O avatar é recalculado na tecla (duas letras
  de uma string curta), a busca não existe aqui e nada é agendado. Não há
  `after_cancel` a fazer porque não há `after`.

`done()` ainda esvazia os dois dicionários de widgets. Eles não seguram nada
que o Qt já não fosse liberar, mas custam uma linha e deixam o descarte
explícito em vez de dependente de detalhe de implementação — mesmo critério do
`modais.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.enums import CargoFuncionario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade


@dataclass(frozen=True, slots=True)
class Cargo:
    """Uma opção da grade: o que vai para o banco e o que o operador lê.

    `valor` é o texto que `FuncionarioService` valida e grava — vem do
    `CargoFuncionario` de propósito, para o enum continuar sendo a fonte da
    verdade e um cargo novo não poder nascer só aqui na tela.
    """

    valor: str
    descricao: str
    acesso: str
    acesso_total: bool


# A ordem é a da grade (2 colunas, o quinto card sozinho na terceira fileira),
# e é a mesma do mockup: os dois cargos que mexem em dinheiro em cima, os três
# de operação embaixo.
CARGOS: tuple[Cargo, ...] = (
    Cargo(CargoFuncionario.GERENTE.value, "Acesso total, abre e fecha caixa", "ACESSO TOTAL", True),
    Cargo(CargoFuncionario.CAIXA.value, "Recebe pagamentos e fecha comandas", "ACESSO LIBERADO", True),
    Cargo(CargoFuncionario.GARCOM.value, "Lança pedidos nas mesas", "APENAS PEDIDOS", False),
    Cargo(CargoFuncionario.COZINHA.value, "Vê e prepara os pedidos", "APENAS PREPARO", False),
    Cargo(CargoFuncionario.ENTREGADOR.value, "Recebe as entregas do delivery", "APENAS ENTREGAS", False),
)

# §3.14: "ACESSO" não é campo do domínio (`Funcionario` não tem coluna de nível
# de acesso — só `Usuario`, que loga, tem perfil). É derivado do cargo, e
# derivado num lugar só: o rodapé deste modal e a linha ACESSO do painel de
# detalhe leem daqui. Enquanto eram duas listas, "Gerente e Caixa" precisava
# estar certo em dois arquivos ao mesmo tempo.
CARGOS_COM_ACESSO_TOTAL: frozenset[str] = frozenset(c.valor for c in CARGOS if c.acesso_total)

_SEM_CARGO = "SELECIONE UM CARGO"
_SEM_INICIAIS = "—"
# O telefone é opcional e guardado como texto livre. A máscara só se aplica ao
# que PARECE um telefone brasileiro; qualquer outra coisa que já estivesse
# gravada (um ramal, um recado) passa intacta -- ver `formatar_telefone`.
_DIGITOS_DE_TELEFONE = 11
_PONTUACAO_DA_MASCARA = frozenset("()- .")


@dataclass(frozen=True, slots=True)
class DadosFuncionario:
    """O que o modal devolve. `cargo=None` é cadastro sem função definida, que
    o service aceita (compatibilidade com cadastros antigos, §`_validar_cargo`)."""

    nome: str
    cargo: str | None
    telefone: str | None
    ativo: bool


def iniciais(nome: str) -> str:
    """`"Ana Beatriz Souza"` vira `"AB"` — primeira e última palavra.

    Mora neste módulo, e não na view, porque o avatar do modal e o avatar da
    lista têm que gerar as MESMAS duas letras: se divergirem, o cadastro que a
    pessoa acabou de conferir aparece com outra sigla na linha de baixo.
    """
    partes = [parte for parte in nome.strip().split() if parte]
    if not partes:
        return _SEM_INICIAIS
    if len(partes) == 1:
        return partes[0][0].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def resumo_de_acesso(cargo: str | None) -> str:
    """`"Caixa"` vira `"CAIXA · ACESSO LIBERADO"` — o rodapé do modal.

    Cargo desconhecido cai no mesmo texto de "nenhum cargo": é o caso de um
    cadastro gravado antes de uma opção mudar de nome, e inventar um acesso
    para ele seria afirmar na tela algo que o sistema não sabe.
    """
    for opcao in CARGOS:
        if opcao.valor == cargo:
            return f"{opcao.valor.upper()} · {opcao.acesso}"
    return _SEM_CARGO


def formatar_telefone(texto: str | None) -> str:
    """Aplica `(11) 90000-0000` progressivamente, enquanto o operador digita.

    Devolve o texto **intacto** quando ele não cabe na máscara: mais de onze
    dígitos, ou qualquer caractere que não seja dígito nem pontuação de
    telefone. `Funcionario.telefone` é `String` livre e sempre foi — um
    cadastro antigo com "falar com a Ana" não pode ser remontado como se fosse
    um número na primeira vez que alguém abrir o modal para editar outra coisa.
    """
    if not texto:
        return ""
    digitos = [caractere for caractere in texto if caractere.isdigit()]
    resto = [caractere for caractere in texto if not caractere.isdigit()]
    if len(digitos) > _DIGITOS_DE_TELEFONE or any(c not in _PONTUACAO_DA_MASCARA for c in resto):
        return texto

    numero = "".join(digitos)
    if not numero:
        return ""
    if len(numero) <= 2:
        return f"({numero}"
    ddd, assinante = numero[:2], numero[2:]
    if len(numero) <= 6:
        return f"({ddd}) {assinante}"
    # Fixo tem 8 dígitos depois do DDD e celular tem 9: o corte anda uma casa
    # só quando o décimo primeiro dígito chega.
    corte = 5 if len(numero) > 10 else 4
    return f"({ddd}) {assinante[:corte]}-{assinante[corte:]}"


class _IconeUsuarioNovo(QWidget):
    """O ícone de "cadastrar pessoa" do cabeçalho, desenhado à mão.

    Mesma decisão do cadeado do `pin_pad_dialog` e da lupa do
    `adicionar_item_dialog`: o glifo equivalente mora no bloco de emoji, cai no
    Segoe UI Emoji, sai colorido e chapado e ignora o tema — e a máquina limpa
    do food truck pode nem ter a fonte. A cor daqui é relida a cada repintura,
    então o ícone acompanha o alternador Claro/Escuro de graça (§3.15).
    """

    LADO_PX = 22

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("funcDialogGlifo")
        self.setFixedSize(self.LADO_PX, self.LADO_PX)

    @nao_deixa_escapar()
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (override Qt)
        paleta = ThemeController.instancia().tokens_atuais
        cor = QColor(paleta["badge_icone_glifo"])

        caneta = QPen(cor, 1.8)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)

        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.setPen(caneta)
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        # Cabeça e ombros: um círculo e a meia-volta de cima de uma elipse
        # (0° a 180°, em 1/16 de grau, como o Qt pede).
        pintor.drawEllipse(QRectF(4.4, 3.4, 7.2, 7.2))
        pintor.drawArc(QRectF(2.4, 10.6, 11.2, 10.0), 0, 180 * 16)

        # O "+" fica em cima do ombro direito, e o disco na cor da caixa é o que
        # abre espaço para ele — mesmo truque do furo da fechadura do cadeado.
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(paleta["badge_icone_bg"]))
        pintor.drawEllipse(QRectF(10.8, 10.3, 10.4, 10.4))
        pintor.setPen(caneta)
        pintor.drawLine(QPointF(12.9, 15.5), QPointF(19.1, 15.5))
        pintor.drawLine(QPointF(16.0, 12.4), QPointF(16.0, 18.6))
        pintor.end()


class _CartaoCargo(QFrame):
    """Um card da grade de cargos: nome, o que ele faz e o ✓ de escolhido.

    É `QFrame` e não `QPushButton` checável pelo mesmo motivo do `_CartaoMesa`
    da tela de Mesas: são duas linhas com tamanhos, pesos e cores diferentes, e
    o texto único de um `QPushButton` não estiliza isso via QSS.

    Não aceita foco de propósito. Quem lê o teclado neste modal é o diálogo (o
    `Enter` cadastra), e um card focado engoliria a tecla.
    """

    clicado = Signal()

    def __init__(self, cargo: Cargo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("funcDialogCargo")
        self.setProperty("selecionado", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        topo = QHBoxLayout()
        topo.setSpacing(6)
        nome = QLabel(cargo.valor)
        nome.setObjectName("funcDialogCargoNome")
        topo.addWidget(nome)
        topo.addStretch()
        # O ✓ existe SEMPRE, e o que muda é a cor (o QSS o deixa transparente
        # enquanto o card não está escolhido). Mostrar e esconder o rótulo
        # mudaria a largura da linha do título a cada clique, e card que muda
        # de tamanho ao ser escolhido é o que faz o dedo errar o próximo.
        marca = QLabel("✓")
        marca.setObjectName("funcDialogCargoMarca")
        topo.addWidget(marca)
        layout.addLayout(topo)

        descricao = QLabel(cargo.descricao)
        descricao.setObjectName("funcDialogCargoDescricao")
        descricao.setWordWrap(True)
        layout.addWidget(descricao)

    @nao_deixa_escapar()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
        super().mousePressEvent(event)


class FuncionarioDialog(QDialog):
    """Cartão de cadastro/edição: identidade, cargo, telefone e situação."""

    LARGURA_CARTAO_PX = 520
    LADO_BOTAO_FECHAR_PX = 32
    LADO_AVATAR_PX = 48
    COLUNAS_DE_CARGO = 2
    LIMITE_NOME = 120
    LIMITE_TELEFONE = 30

    def __init__(self, funcionario: Funcionario | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._edicao = funcionario is not None
        self._cargo_escolhido: str | None = funcionario.cargo if funcionario else None
        self._ativo = funcionario.ativo if funcionario else True
        self._backdrop: Backdrop | None = None
        self._cards: dict[str, _CartaoCargo] = {}
        self._pills: dict[bool, QPushButton] = {}

        self.setObjectName("funcDialog")
        self.setWindowTitle("Editar funcionário" if self._edicao else "Novo funcionário")
        # Sem moldura do sistema: o cabeçalho (badge, título e o ✕) é do
        # cartão, e o fundo translúcido é o que faz os cantos de 16px saírem
        # redondos em vez de recortados contra um retângulo opaco.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)

        cartao = QFrame()
        cartao.setObjectName("funcDialogCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(22, 18, 22, 16)
        corpo.setSpacing(14)
        corpo.addLayout(self._montar_cabecalho())
        corpo.addWidget(self._montar_identidade())
        corpo.addLayout(self._montar_cargos())
        corpo.addLayout(self._montar_contato_e_situacao())
        corpo.addWidget(self._montar_divisor())
        corpo.addLayout(self._montar_acoes())

        self._preencher(funcionario)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_cabecalho(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(12)

        caixa_icone = QFrame()
        caixa_icone.setObjectName("funcDialogIcone")
        caixa_icone.setFixedSize(42, 42)
        dentro = QHBoxLayout(caixa_icone)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(_IconeUsuarioNovo(), 0, Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(caixa_icone, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel("Editar funcionário" if self._edicao else "Novo funcionário")
        titulo.setObjectName("funcDialogTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel(
            "Atualize os dados e o acesso ao PDV."
            if self._edicao
            else "Cadastre a equipe e defina o acesso ao PDV."
        )
        subtitulo.setObjectName("funcDialogSubtitulo")
        textos.addWidget(subtitulo)
        linha.addLayout(textos)
        linha.addStretch()

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("funcDialogFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return linha

    def _montar_identidade(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("funcDialogIdentidade")
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(14, 12, 14, 12)
        linha.setSpacing(14)

        self._avatar = QLabel(_SEM_INICIAIS)
        self._avatar.setObjectName("funcDialogAvatar")
        self._avatar.setFixedSize(self.LADO_AVATAR_PX, self.LADO_AVATAR_PX)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        coluna = QVBoxLayout()
        coluna.setSpacing(5)
        coluna.addWidget(self._rotulo("NOME"))
        self._campo_nome = QLineEdit()
        self._campo_nome.setObjectName("funcDialogCampo")
        self._campo_nome.setPlaceholderText("Nome completo")
        self._campo_nome.setMaxLength(self.LIMITE_NOME)
        # `textChanged`, e não `textEdited`: o avatar também tem que estar certo
        # na abertura de uma edição, quando quem escreve no campo é o código.
        self._campo_nome.textChanged.connect(self._ao_mudar_nome)
        coluna.addWidget(self._campo_nome)
        linha.addLayout(coluna, 1)
        return painel

    def _montar_cargos(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(8)
        coluna.addWidget(self._rotulo("CARGO"))

        grade = QGridLayout()
        grade.setHorizontalSpacing(10)
        grade.setVerticalSpacing(8)
        for indice, cargo in enumerate(CARGOS):
            card = _CartaoCargo(cargo)
            # O cargo vive na propriedade, e não numa `lambda` amarrada no
            # clique: ver o cabeçalho do arquivo (§3.14).
            card.setProperty("cargo", cargo.valor)
            card.clicado.connect(self._cargo_clicado)
            grade.addWidget(card, *divmod(indice, self.COLUNAS_DE_CARGO))
            self._cards[cargo.valor] = card
        for coluna_indice in range(self.COLUNAS_DE_CARGO):
            grade.setColumnStretch(coluna_indice, 1)
        coluna.addLayout(grade)
        return coluna

    def _montar_contato_e_situacao(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(16)

        telefone = QVBoxLayout()
        telefone.setSpacing(5)
        telefone.addWidget(self._rotulo("TELEFONE (opcional)"))
        self._campo_telefone = QLineEdit()
        self._campo_telefone.setObjectName("funcDialogCampo")
        self._campo_telefone.setPlaceholderText("(11) 90000-0000")
        self._campo_telefone.setMaxLength(self.LIMITE_TELEFONE)
        # `textEdited` dispara só na digitação do operador. Com `textChanged` o
        # `setText` da própria máscara reentraria na máscara, e a edição de um
        # cadastro antigo reformataria um telefone que ninguém pediu para mexer.
        self._campo_telefone.textEdited.connect(self._ao_digitar_telefone)
        telefone.addWidget(self._campo_telefone)
        linha.addLayout(telefone, 1)

        situacao = QVBoxLayout()
        situacao.setSpacing(5)
        situacao.addWidget(self._rotulo("SITUAÇÃO"))
        pills = QHBoxLayout()
        pills.setSpacing(8)
        for ativo, rotulo in ((True, "Ativo"), (False, "Inativo")):
            pill = QPushButton(rotulo)
            pill.setObjectName("funcDialogSituacao")
            pill.setProperty("papel", "ativo" if ativo else "inativo")
            pill.setProperty("marcada", False)
            cartao_modal.preparar_botao(pill)
            pill.clicked.connect(self._situacao_clicada)
            pills.addWidget(pill)
            self._pills[ativo] = pill
        situacao.addLayout(pills)
        linha.addLayout(situacao)
        return linha

    def _montar_divisor(self) -> QFrame:
        divisor = QFrame()
        divisor.setObjectName("funcDialogDivisor")
        divisor.setFixedHeight(1)
        return divisor

    def _montar_acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(10)

        self._label_resumo = QLabel(_SEM_CARGO)
        self._label_resumo.setObjectName("funcDialogResumo")
        linha.addWidget(self._label_resumo, 1)

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("funcDialogCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = QPushButton("Salvar" if self._edicao else "Cadastrar")
        self._botao_confirmar.setObjectName("funcDialogConfirmar")
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self.accept)
        linha.addWidget(self._botao_confirmar)
        return linha

    def _rotulo(self, texto: str) -> QLabel:
        rotulo = QLabel(texto.upper())
        rotulo.setObjectName("funcDialogRotulo")
        return rotulo

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def _preencher(self, funcionario: Funcionario | None) -> None:
        if funcionario is not None:
            self._campo_nome.setText(funcionario.nome)
            self._campo_telefone.setText(formatar_telefone(funcionario.telefone))
        self._pintar_cargos()
        self._pintar_situacao()
        self._ao_mudar_nome(self._campo_nome.text())

    def _ao_mudar_nome(self, texto: str) -> None:
        self._avatar.setText(iniciais(texto))
        # Sem nome não há cadastro: `FuncionarioService._validar_nome` recusa, e
        # deixar o botão aceso só para o operador levar o erro de volta na tela
        # de trás é uma ida e volta que o cartão pode evitar.
        self._botao_confirmar.setEnabled(bool(texto.strip()))

    def _ao_digitar_telefone(self, texto: str) -> None:
        formatado = formatar_telefone(texto)
        if formatado != texto:
            # O cursor vai para o fim: quem digita no balcão digita do começo ao
            # fim, e reposicionar o cursor no meio de uma máscara custa mais
            # código do que o caso raro merece.
            self._campo_telefone.setText(formatado)

    def _cargo_clicado(self) -> None:
        card = self.sender()
        if not isinstance(card, _CartaoCargo):
            return
        self._cargo_escolhido = str(card.property("cargo"))
        self._pintar_cargos()

    def _pintar_cargos(self) -> None:
        for valor, card in self._cards.items():
            escolhido = valor == self._cargo_escolhido
            # Repolir custa um recálculo de estilo: só quem mudou de estado
            # paga (mesma economia do `_pintar_marcadores` do modal de PIN).
            if card.property("selecionado") != escolhido:
                aplicar_propriedade(card, "selecionado", escolhido)
        self._label_resumo.setText(resumo_de_acesso(self._cargo_escolhido))

    def _situacao_clicada(self) -> None:
        pill = self.sender()
        if not isinstance(pill, QPushButton):
            return
        self._ativo = pill.property("papel") == "ativo"
        self._pintar_situacao()

    def _pintar_situacao(self) -> None:
        for ativo, pill in self._pills.items():
            marcada = ativo == self._ativo
            if pill.property("marcada") != marcada:
                aplicar_propriedade(pill, "marcada", marcada)

    # ------------------------------------------------------------------
    # Resultado
    # ------------------------------------------------------------------

    def resultado(self) -> DadosFuncionario:
        """O que a view leva para `FuncionarioService`. Lido DEPOIS do `exec()`
        — o `executar_modal` (§3.2) só descarta o diálogo na volta."""
        return DadosFuncionario(
            nome=self._campo_nome.text().strip(),
            cargo=self._cargo_escolhido,
            telefone=self._campo_telefone.text().strip() or None,
            ativo=self._ativo,
        )

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """O `Enter` cadastra, venha o cursor do nome ou do telefone.

        O `QLineEdit` ignora o Return e ele sobe até aqui — ligar
        `returnPressed` dos campos ALÉM disto seria o caminho para o cadastro
        ser enviado duas vezes com um Enter só (§9.4).

        O Esc cai no `super()` de propósito: lá o `QDialog` o traduz em
        `reject()`, que passa por `done()` e portanto pela mesma limpeza dos
        outros caminhos de saída.
        """
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._botao_confirmar.isEnabled():
                self.accept()
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        if self._backdrop is None:
            self._backdrop = cartao_modal.montar(self)
        self.adjustSize()
        cartao_modal.centralizar_no_pai(self)
        self._campo_nome.setFocus(Qt.FocusReason.OtherFocusReason)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única — e por isso o lugar certo da limpeza.

        Cadastrar, Cancelar, o ✕ e o Esc passam todos por aqui; `closeEvent`
        sozinho não serviria, porque `done()` faz `hide()`, não `close()`
        (§3.9). Sai o escurecedor, que é filho da JANELA e não do diálogo, e
        saem as duas tabelas de widgets.
        """
        self._cards.clear()
        self._pills.clear()
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
        super().done(resultado)
