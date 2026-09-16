"""O campo de dinheiro de verdade: teclado, área de transferência, foco e tema (§9.20).

`tests/unit/test_sanitizar_moeda.py` prende a regra pura. Aqui a pergunta é se o
`QLineEdit` a aplica por TODAS as portas de entrada — o motivo de ela morar num
validador e não num `keyPressEvent` —, se o "R$" fica fora do alcance do cursor,
e se nada disso custa objeto, sinal ou laço por tecla. No fim, o cadastro de
produto: o que se digita no preço chega ao SQLite como `Decimal`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFocusEvent, QKeySequence, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFormLayout, QLineEdit, QVBoxLayout, QWidget

import gestor_comercial.ui.views.cardapio_view as modulo_da_tela
from gestor_comercial.services.dinheiro import ZERO
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import campo_moeda as modulo_do_campo
from gestor_comercial.ui.widgets.campo_moeda import CampoMoeda


@pytest.fixture
def tema(qapp):
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield controlador
    finally:
        controlador.alternar_para(False)


@pytest.fixture
def janela(qapp, tema):
    """Dois campos numa janela ativa: o segundo é para onde o foco sai."""
    hospedeira = QWidget()
    layout = QVBoxLayout(hospedeira)
    campo, vizinho = CampoMoeda(), CampoMoeda()
    layout.addWidget(campo)
    layout.addWidget(vizinho)
    hospedeira.resize(300, 120)
    hospedeira.show()
    hospedeira.activateWindow()
    campo.setFocus()
    qapp.processEvents()
    assert campo.hasFocus(), "premissa: a plataforma offscreen entrega o foco"
    try:
        yield campo, vizinho
    finally:
        hospedeira.close()
        hospedeira.deleteLater()
        QApplication.clipboard().clear()


def _cor(widget: QWidget) -> str:
    return widget.palette().color(QPalette.ColorRole.WindowText).name()


def _ctrl_v(campo: QLineEdit) -> None:
    QTest.keySequence(campo, QKeySequence(QKeySequence.StandardKey.Paste))


def _colar_do_menu(campo: QLineEdit) -> None:
    # A ação "Colar" do menu de contexto é ligada, em C++, a este slot.
    campo.paste()


def _arrastar_e_soltar(campo: QLineEdit) -> None:
    # O `dropEvent` do QLineEdit insere pelo mesmo `insert()` do teclado.
    campo.insert(QApplication.clipboard().text())


# ---------------------------------------------------------------------------
# 1. Todas as portas de entrada passam pela mesma regra
# ---------------------------------------------------------------------------


def test_letras_e_simbolos_digitados_nao_entram(janela):
    campo, _ = janela
    QTest.keyClicks(campo, "1a2 b,c5!%")
    assert campo.text() == "12,5"


def test_ponto_vira_virgula_e_o_segundo_separador_nao_entra(janela):
    campo, _ = janela
    QTest.keyClicks(campo, "12.5.,3")
    assert campo.text() == "12,53"


@pytest.mark.parametrize("gesto", [_ctrl_v, _colar_do_menu, _arrastar_e_soltar])
@pytest.mark.parametrize(
    "colado, texto, valor",
    [
        ("R$ 15,90 kg", "15,90", "15.90"),
        ("abc12.5", "12,5", "12.50"),
        ("R$ 29,90", "29,90", "29.90"),
        ("R$ 1.234,56", "1234,56", "1234.56"),
    ],
)
def test_colar_saneia_por_qualquer_caminho(janela, gesto, colado, texto, valor):
    campo, _ = janela
    QApplication.clipboard().setText(colado)
    assert QApplication.clipboard().text() == colado, "premissa: a área de transferência funciona"

    gesto(campo)

    assert campo.text() == texto
    assert campo.valor() == Decimal(valor)


def test_colar_lixo_sobre_o_valor_selecionado_nao_o_apaga(janela):
    campo, _ = janela
    QTest.keyClicks(campo, "12,50")
    campo.selectAll()
    QApplication.clipboard().setText("R$ kg")

    _ctrl_v(campo)

    assert campo.text() == "12,50"


def test_settext_de_codigo_tambem_e_saneado(janela):
    """A porta que um `keyPressEvent` não cobriria, e a razão de o validador
    nunca devolver `Invalid`: por `setText` o Qt não desfaz, só marca."""
    campo, _ = janela
    campo.setText("R$ 7.5 kg")
    assert campo.text() == "7,5"
    assert campo.hasAcceptableInput()


# ---------------------------------------------------------------------------
# 2. Centavos ao sair do campo, e Backspace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "digitado, ao_sair",
    [
        ("12", "12,00"),
        ("12,", "12,00"),
        ("12,5", "12,50"),
        (",5", "0,50"),
        ("007", "7,00"),
        ("0", "0,00"),
        (",", ""),
        ("", ""),
    ],
)
def test_sair_do_campo_completa_os_centavos(qapp, janela, digitado, ao_sair):
    campo, vizinho = janela
    QTest.keyClicks(campo, digitado)

    vizinho.setFocus()
    qapp.processEvents()

    assert not campo.hasFocus()
    assert campo.text() == ao_sair


def test_sair_de_um_campo_ja_formatado_nao_reescreve_o_texto(qapp, janela):
    """`setText` com o mesmo texto não emite `textChanged` no Qt, mas apaga o
    histórico do Ctrl+Z — e é isso que se perderia a cada Tab."""
    campo, vizinho = janela
    QTest.keyClicks(campo, "12,50")
    assert campo.isUndoAvailable(), "premissa: digitar deixa o que desfazer"

    vizinho.setFocus()
    qapp.processEvents()

    assert campo.text() == "12,50"
    assert campo.isUndoAvailable()


def test_abrir_o_menu_de_contexto_nao_formata(janela):
    """O menu rouba o foco para abrir; formatar ali trocaria o texto debaixo da
    seleção de quem ia clicar em "Colar"."""
    campo, _ = janela
    QTest.keyClicks(campo, "12")

    QApplication.sendEvent(campo, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.PopupFocusReason))

    assert campo.text() == "12"
    assert campo._prefixo.property("foco") is True


def test_backspace_ate_esvaziar_nunca_quebra(janela):
    campo, _ = janela
    QTest.keyClicks(campo, "12,50")
    for _ in range(8):
        QTest.keyClick(campo, Qt.Key.Key_Backspace)
        valor = campo.valor()
        assert valor is None or valor >= ZERO
    assert campo.text() == ""
    assert campo.valor() is None


# ---------------------------------------------------------------------------
# 3. O "R$"
# ---------------------------------------------------------------------------


def test_o_prefixo_nao_e_texto_e_nao_se_apaga(janela):
    campo, _ = janela
    QTest.keyClicks(campo, "9,90")
    QTest.keyClick(campo, Qt.Key.Key_Home)
    QTest.keyClick(campo, Qt.Key.Key_Backspace)
    QTest.keyClick(campo, Qt.Key.Key_Backspace)

    assert campo.text() == "9,90"
    assert campo._prefixo.text() == "R$"
    assert campo._prefixo.isVisible()


def test_o_texto_comeca_depois_do_prefixo(janela):
    campo, _ = janela
    campo.setCursorPosition(0)
    prefixo = campo._prefixo.geometry()

    assert prefixo.left() >= 0 and prefixo.height() > 0
    assert campo.cursorRect().center().x() > prefixo.right()
    assert campo.textMargins().left() == prefixo.width() + modulo_do_campo.FOLGA_PREFIXO_PX
    # Medido na fonte que o QSS dá ao rótulo (negrito), e não na de antes do
    # polimento: medir a outra deixaria o "R$" cortado ou colado no número.
    assert campo._prefixo.font().bold()
    assert prefixo.width() == campo._prefixo.fontMetrics().horizontalAdvance("R$")


def test_clicar_no_prefixo_e_clicar_no_campo(janela):
    campo, _ = janela
    assert campo._prefixo.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_o_prefixo_nao_pinta_fundo_proprio(qapp, janela):
    """Sem `background: transparent` no QSS, o `QWidget {background}` global
    pinta um retângulo de `bg_marca` em volta do "R$", mais escuro que o campo."""
    campo, _ = janela
    qapp.processEvents()
    imagem = campo.grab().toImage()
    prefixo = campo._prefixo.geometry()

    no_prefixo = imagem.pixelColor(prefixo.left(), prefixo.top())
    no_campo_vazio = imagem.pixelColor(campo.width() - 20, prefixo.top())

    assert no_prefixo == no_campo_vazio


def test_o_prefixo_acende_com_o_foco_e_segue_o_tema(qapp, janela, tema):
    campo, vizinho = janela
    assert _cor(campo._prefixo) == tema.tokens_atuais["acento"].lower()

    vizinho.setFocus()
    qapp.processEvents()
    assert _cor(campo._prefixo) == tema.tokens_atuais["texto_fraquissimo"].lower()

    tema.alternar_para(True)
    qapp.processEvents()
    assert _cor(campo._prefixo) == tema.tokens_atuais["texto_fraquissimo"].lower()
    campo.setFocus()
    qapp.processEvents()
    assert _cor(campo._prefixo) == tema.tokens_atuais["acento"].lower()


# ---------------------------------------------------------------------------
# 4. O custo por tecla: nenhum laço, nenhum objeto
# ---------------------------------------------------------------------------


def test_uma_validacao_por_tecla_e_duas_quando_reescreve(qapp, tema, monkeypatch):
    chamadas: list[str] = []
    validar_original = modulo_do_campo.ValidadorMoeda.validate

    def _contando(self, texto, cursor):
        chamadas.append(texto)
        return validar_original(self, texto, cursor)

    monkeypatch.setattr(modulo_do_campo.ValidadorMoeda, "validate", _contando)
    campo = CampoMoeda()
    mudancas: list[str] = []
    campo.textChanged.connect(mudancas.append)
    try:
        chamadas.clear()
        QTest.keyClicks(campo, "1234")
        assert len(chamadas) == 4, chamadas
        assert mudancas == ["1", "12", "123", "1234"]

        chamadas.clear()
        QTest.keyClick(campo, Qt.Key.Key_A)
        assert len(chamadas) == 2, chamadas
        assert campo.text() == "1234"

        chamadas.clear()
        QApplication.clipboard().setText("R$ 15,90 kg")
        campo.selectAll()
        _ctrl_v(campo)
        assert chamadas == ["R$ 15,90 kg", "15,90"]
    finally:
        campo.textChanged.disconnect(mudancas.append)
        campo.deleteLater()
        QApplication.clipboard().clear()


def test_digitar_e_colar_nao_criam_objeto(janela):
    campo, _ = janela
    antes = len(campo.findChildren(QObject))

    for rodada in range(100):
        QTest.keyClicks(campo, "12a,5.0")
        QApplication.clipboard().setText(f"R$ {rodada},90 kg")
        campo.selectAll()
        _ctrl_v(campo)
        QTest.keyClick(campo, Qt.Key.Key_Backspace)
        campo.clear()

    assert len(campo.findChildren(QObject)) == antes


def test_o_campo_morre_junto_com_o_pai(qapp, tema, assentar):
    assentar()
    antes = len(QApplication.allWidgets())

    for _ in range(50):
        pai = QWidget()
        campo = CampoMoeda(Decimal("12.50"), pai)
        QTest.keyClicks(campo, "3")
        pai.deleteLater()
        del pai, campo
    assentar()

    assert len(QApplication.allWidgets()) == antes


# ---------------------------------------------------------------------------
# 5. O cadastro de produto
# ---------------------------------------------------------------------------


@pytest.fixture
def cadastro(qapp, tema):
    dialogos: list[QWidget] = []

    def _abrir(**kwargs):
        dialogo = modulo_da_tela._ProdutoDialog("Novo produto", kwargs.pop("categorias", []), **kwargs)
        dialogos.append(dialogo)
        return dialogo

    yield _abrir
    for dialogo in dialogos:
        dialogo.deleteLater()


def _rotulo(dialogo, campo: QWidget) -> str:
    formulario = dialogo.findChild(QFormLayout)
    return formulario.labelForField(campo).text()


def test_os_dois_precos_do_cadastro_sao_campo_de_moeda(cadastro):
    dialogo = cadastro()
    assert isinstance(dialogo._campo_preco, CampoMoeda)
    assert isinstance(dialogo._campo_custo, CampoMoeda)
    assert _rotulo(dialogo, dialogo._campo_preco) == "Preço de venda"
    assert _rotulo(dialogo, dialogo._campo_custo) == "Preço de custo"


def test_editar_abre_com_os_centavos(cadastro):
    dialogo = cadastro(preco_inicial=Decimal("12.5"), custo_inicial=Decimal("4"))
    assert dialogo._campo_preco.text() == "12,50"
    assert dialogo._campo_custo.text() == "4,00"


def test_letras_no_preco_nao_entram_e_o_resultado_e_decimal(cadastro):
    dialogo = cadastro(nome_inicial="X Tudo")
    QTest.keyClicks(dialogo._campo_preco, "abc9.9x0")
    QTest.keyClicks(dialogo._campo_custo, "R$ 3,5")

    assert dialogo._campo_preco.text() == "9,90"
    assert dialogo._validar()
    dados = dialogo.resultado()
    assert (dados.preco, dados.custo) == (Decimal("9.90"), Decimal("3.50"))
    assert isinstance(dados.preco, Decimal) and isinstance(dados.custo, Decimal)


@pytest.mark.parametrize(
    "digitado, frase",
    [("", "Informe o preço de venda."), ("0,00", "O preço de venda deve ser maior que zero.")],
)
def test_preco_vazio_e_preco_zero_tem_frases_proprias(cadastro, digitado, frase):
    dialogo = cadastro(nome_inicial="X Tudo")
    QTest.keyClicks(dialogo._campo_preco, digitado)

    assert not dialogo._validar()
    assert dialogo._erro_preco.text() == frase
    assert not dialogo._erro_preco.isHidden()
    assert dialogo._campo_preco.property("erro") is True


def test_custo_vazio_vai_como_zero(cadastro):
    dialogo = cadastro(nome_inicial="X Tudo", preco_inicial=Decimal("10"))
    assert dialogo._validar()
    assert dialogo.resultado().custo == ZERO


def test_o_digitado_chega_ao_sqlite_como_numero(cadastro, cardapio, gerente, categoria, session):
    """Da tecla ao banco: ponto e vírgula, e uma colagem suja, gravados como número."""
    from sqlalchemy import text

    dialogo = cadastro(nome_inicial="X Salada", categorias=[categoria], categoria_id_inicial=categoria.id)
    QTest.keyClicks(dialogo._campo_preco, "12.5")
    QApplication.clipboard().setText("custo: R$ 4,25 kg")
    try:
        _ctrl_v(dialogo._campo_custo)
    finally:
        QApplication.clipboard().clear()
    assert dialogo._validar()
    dados = dialogo.resultado()

    produto = cardapio.criar_produto(dados.nome, dados.preco, dados.categoria_id, dados.custo)
    session.expire_all()

    relido = cardapio.buscar_produto(produto.id)
    assert (relido.preco, relido.custo) == (Decimal("12.50"), Decimal("4.25"))
    tipos = session.execute(
        text("SELECT typeof(preco), typeof(custo) FROM produtos WHERE id = :id"), {"id": produto.id}
    ).one()
    assert set(tipos) <= {"real", "integer"}, tipos
