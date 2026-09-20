"""O cartão "Fechar conta para conferência". §9.23, sem a escolha desde o §9.25.

Pedido do Vitor, com o mockup: trocar o diálogo de fábrica do "Fechar conta" —
moldura do Windows, um `QCheckBox` e OK/Cancelar — por um cartão que diz quanto
a mesa vai pagar ANTES de imprimir a pré-conta. A caixinha de marcar a taxa
existiu por um dia: no §9.25 ela saiu ("deixa de existir como etapa de escolha
do operador"), e quem decide se a loja cobra os 10% é a Central de Loja.

O que esta suíte cobra:

1. **as frases do mockup** — cabeçalho, os dois valores, a linha da taxa, o
   aviso e o rodapé, na mesa e no balcão;
2. **a taxa vem da loja** — o total já abre com ela, o cartão devolve o
   percentual sem perguntar nada, e não há como alterá-lo pela tela;
3. **a loja sem taxa** — o bloco não é criado e o total é o subtotal;
4. **zero SQL** — repintar o cartão não vai ao banco;
5. **o teclado** — Enter fecha e imprime, Esc cancela, os botões não roubam foco;
6. **o desenho** — nada espremido, nos dois temas, abaixo dos 728px úteis;
7. **o ciclo de vida** — o escurecedor sai com o cartão, as ligações saem
   nominalmente, e trinta aberturas não deixam nada para trás.
"""

from __future__ import annotations

import warnings
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QFontDatabase, QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QWidget
from sqlalchemy import event

import gestor_comercial
from gestor_comercial.services.comanda_service import TAXA_SERVICO_PADRAO, PreviaDeConferencia
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.conferencia_dialog import (
    AVISO_TEXTO,
    SUBTITULO,
    ConferenciaMesaDialog,
    _CartaoTaxa,
)

MOCKUP = PreviaDeConferencia(mesa_numero=12, subtotal=Decimal("131.50"), taxa_percentual=TAXA_SERVICO_PADRAO)
BALCAO = PreviaDeConferencia(mesa_numero=None, subtotal=Decimal("48.00"), taxa_percentual=TAXA_SERVICO_PADRAO)
SEM_TAXA = PreviaDeConferencia(mesa_numero=12, subtotal=Decimal("131.50"), taxa_percentual=None)


@pytest.fixture
def criar(qapp):
    """Monta cartões sem `exec()` e os descarta no fim do teste."""
    criados: list[ConferenciaMesaDialog] = []

    def _criar(previa: PreviaDeConferencia, parent: QWidget | None = None) -> ConferenciaMesaDialog:
        modal = ConferenciaMesaDialog(previa, parent)
        criados.append(modal)
        return modal

    yield _criar
    for modal in criados:
        modal.deleteLater()


def _textos(modal: QWidget) -> list[str]:
    return [rotulo.text() for rotulo in modal.findChildren(QLabel)]


def _tecla(modal: QWidget, tecla: Qt.Key) -> None:
    QApplication.sendEvent(modal, QKeyEvent(QEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


# ---------------------------------------------------------------------------
# 1. As frases do mockup
# ---------------------------------------------------------------------------


def test_o_mockup_frase_por_frase(criar):
    modal = criar(MOCKUP)
    textos = _textos(modal)

    assert modal._secao.text() == "MESA 12 · CONFERÊNCIA"
    assert modal._titulo.text() == "Fechar conta para conferência"
    assert modal._subtitulo.text() == SUBTITULO == "Revise os valores antes de imprimir a pré-conta."
    for frase in (
        "SUBTOTAL",
        "TOTAL DA PRÉ-CONTA",
        "Taxa de serviço incluída",
        "10% sobre o consumo da mesa",
        "R$ 13,15",
        "A mesa ficará em conferência",
        AVISO_TEXTO,
        "AÇÃO SEGURA",
    ):
        assert frase in textos, frase
    assert modal._valor_subtotal.text() == "R$ 131,50"
    assert modal._botao_cancelar.text() == "Cancelar"
    assert modal._botao_confirmar.text() == "Fechar e imprimir"
    assert "“Reabrir” com o PIN de gerente" in AVISO_TEXTO


def test_o_balcao_nao_fala_em_mesa(criar):
    """O "Fechar conta" da comanda de balcão é o mesmo cartão, e dizer "a mesa
    ficará em conferência" sobre uma comanda sem mesa seria mentir."""
    modal = criar(BALCAO)
    textos = _textos(modal)

    assert modal._secao.text() == "BALCÃO · CONFERÊNCIA"
    assert "A comanda ficará em conferência" in textos
    assert "10% sobre o consumo da comanda" in textos
    assert not any("mesa" in texto.lower() for texto in textos if texto != AVISO_TEXTO)


# ---------------------------------------------------------------------------
# 2. A taxa vem da loja, e o cartão não pergunta nada
# ---------------------------------------------------------------------------


def test_o_total_ja_abre_com_a_taxa(criar):
    """§9.25: sem etapa de escolha. Quem decide é a Central de Loja, e o cartão
    abre com a conta pronta — os R$ 144,65 do mockup."""
    modal = criar(MOCKUP)

    assert modal._valor_total.text() == "R$ 144,65"
    assert modal._valor_subtotal.text() == "R$ 131,50"
    assert modal.resultado() == Decimal("10")
    assert modal._cartao_taxa.valor.text() == "R$ 13,15"


def test_nao_existe_controle_nenhum_para_a_taxa(criar):
    """A caixinha sumiu: o card da taxa não é clicável, não tem cursor de mão e
    não existe método para alternar. Uma delas que voltasse traria de volta a
    pergunta que o §9.25 tirou do balcão."""
    modal = criar(MOCKUP)

    assert not hasattr(modal, "alternar_taxa")
    assert not hasattr(modal, "cobrar_taxa")
    assert not hasattr(modal._cartao_taxa, "clicado")
    assert modal._cartao_taxa.cursor().shape() == Qt.CursorShape.ArrowCursor
    # O Espaço, que alternava, não faz mais nada com os números.
    _tecla(modal, Qt.Key.Key_Space)
    assert modal._valor_total.text() == "R$ 144,65"
    assert modal.result() == 0


# ---------------------------------------------------------------------------
# 3. A loja sem taxa
# ---------------------------------------------------------------------------


def test_loja_sem_taxa_nem_cria_o_bloco(criar):
    """Não é escondido: não existe. Nenhum widget invisível ocupando memória."""
    modal = criar(SEM_TAXA)

    assert modal.findChildren(_CartaoTaxa) == []
    assert not any("axa de serviço" in texto for texto in _textos(modal))
    assert modal._valor_total.text() == modal._valor_subtotal.text() == "R$ 131,50"
    assert modal.resultado() is None


# ---------------------------------------------------------------------------
# 4. Zero SQL
# ---------------------------------------------------------------------------


def test_repintar_o_cartao_nao_vai_ao_banco(qapp, uow, comandas, gerente, caixa_aberto, mesa, produto):
    """A prévia é um instantâneo: o commit que expira as instâncias do
    SQLAlchemy (a lição do §9.4) não alcança o cartão."""
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, produto.id, 3)
    modal = ConferenciaMesaDialog(comandas.previa_de_conferencia(comanda.id))
    comandas.lancar_item(comanda.id, produto.id, 1)  # commit: expira tudo
    consultas: list[str] = []

    def _contar(_conexao, _cursor, sql, *_resto) -> None:
        consultas.append(sql)

    motor = uow.session.get_bind()
    event.listen(motor, "before_cursor_execute", _contar)
    try:
        for _ in range(20):
            modal.grab()
    finally:
        event.remove(motor, "before_cursor_execute", _contar)
        modal.deleteLater()

    assert consultas == []


# ---------------------------------------------------------------------------
# 5. O teclado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tecla", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_fecha_e_imprime(criar, tecla):
    modal = criar(MOCKUP)

    _tecla(modal, tecla)

    assert modal.result() == QDialog.DialogCode.Accepted
    assert modal.resultado() == Decimal("10")


def test_esc_cancela(criar):
    modal = criar(MOCKUP)
    modal.setResult(QDialog.DialogCode.Accepted)

    _tecla(modal, Qt.Key.Key_Escape)

    assert modal.result() == QDialog.DialogCode.Rejected


@pytest.mark.parametrize("nome_do_botao", ["_botao_fechar", "_botao_cancelar"])
def test_o_x_e_o_cancelar_rejeitam(criar, nome_do_botao):
    modal = criar(MOCKUP)
    modal.setResult(QDialog.DialogCode.Accepted)

    getattr(modal, nome_do_botao).click()

    assert modal.result() == QDialog.DialogCode.Rejected


def test_o_botao_fechar_e_imprimir_aceita(criar):
    modal = criar(SEM_TAXA)
    modal._botao_confirmar.click()

    assert modal.result() == QDialog.DialogCode.Accepted
    assert modal.resultado() is None


def test_os_botoes_nao_roubam_o_teclado(criar):
    """Com o foco num botão, o Enter fecharia a conta pelo botão errado."""
    modal = criar(MOCKUP)
    botoes = modal.findChildren(QPushButton)

    assert len(botoes) == 3
    assert all(botao.focusPolicy() == Qt.FocusPolicy.NoFocus for botao in botoes)
    assert all(not botao.autoDefault() and not botao.isDefault() for botao in botoes)


# ---------------------------------------------------------------------------
# 6. O desenho
# ---------------------------------------------------------------------------


@pytest.fixture(params=[False, True], ids=["escuro", "claro"])
def com_fonte_e_tema(qapp, request):
    """A fonte da marca e o QSS, antes de medir. Sem a fonte, o `offscreen`
    mede quase nada e o aperto não acontece (a armadilha do §9.5); nos dois
    temas porque um token que faltasse num deles estouraria só ali."""
    caminho = (
        Path(gestor_comercial.__file__).resolve().parents[2]
        / "resources"
        / "fonts"
        / "ArchivoBlack-Regular.ttf"
    )
    if not caminho.exists():  # pragma: no cover - só num checkout incompleto
        pytest.skip(f"fonte da marca ausente em {caminho}")
    identificador = QFontDatabase.addApplicationFont(str(caminho))
    assert identificador != -1, "o Qt recusou a fonte da marca"
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    controlador.alternar_para(request.param)
    try:
        yield
    finally:
        controlador.alternar_para(False)
        QFontDatabase.removeApplicationFont(identificador)


_VARIANTES = {
    "mockup": MOCKUP,
    "balcao": BALCAO,
    "sem_taxa": SEM_TAXA,
    # A conta grande de uma mesa de festa: cinco dígitos nos dois cartões.
    "conta_grande": PreviaDeConferencia(
        mesa_numero=60, subtotal=Decimal("9999.99"), taxa_percentual=TAXA_SERVICO_PADRAO
    ),
}


@pytest.mark.parametrize("variante", list(_VARIANTES))
def test_nada_do_cartao_e_espremido(qapp, com_fonte_e_tema, variante, assentar):
    """Nenhum rótulo nem botão desenhado menor do que pede, a largura do
    mockup, e o cartão inteiro abaixo dos 728px úteis de um monitor de 768px."""
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = ConferenciaMesaDialog(_VARIANTES[variante], janela)
    modal.show()
    qapp.processEvents()

    espremidos = {}
    for peca in modal.findChildren(QWidget):
        if not isinstance(peca, (QLabel, QPushButton)):
            continue
        if isinstance(peca, QLabel) and peca.wordWrap():
            if peca.height() < peca.heightForWidth(peca.width()):
                espremidos[peca.objectName()] = ("altura", peca.height(), peca.heightForWidth(peca.width()))
        elif peca.width() < peca.sizeHint().width():
            espremidos[peca.objectName()] = ("largura", peca.width(), peca.sizeHint().width())
    altura, largura = modal.height(), modal.width()

    modal.reject()
    modal.deleteLater()
    # Fecha e descarta a janela de verdade: visível esquecida, ela continua
    # ativa e rouba o foco do diálogo do teste seguinte (§9.25).
    janela.close()
    janela.deleteLater()
    assentar()
    assert not espremidos, f"peças espremidas (eixo, tem, pede): {espremidos}"
    assert largura == ConferenciaMesaDialog.LARGURA_CARTAO_PX
    assert altura <= 728


def test_os_tokens_da_familia_existem_nos_dois_temas():
    """O QSS e as pinturas leem `conferencia_mesa_*` e `interruptor_*` pelo nome:
    um token que faltasse num tema estouraria só na hora de pintar ali."""
    from gestor_comercial.ui.theme.tokens import TEMA_CLARO, TEMA_ESCURO

    familia = {chave for chave in TEMA_ESCURO if chave.startswith(("conferencia_mesa_", "interruptor_"))}
    assert len(familia) > 20
    assert familia == {chave for chave in TEMA_CLARO if chave.startswith(("conferencia_mesa_", "interruptor_"))}
    assert not any(chave.startswith("impressora_interruptor") for chave in TEMA_ESCURO | TEMA_CLARO)


# ---------------------------------------------------------------------------
# 7. Ciclo de vida
# ---------------------------------------------------------------------------


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar):
    """O escurecedor é filho da JANELA: sem soltá-lo, uma noite de mesas
    fechadas deixaria retângulos pretos invisíveis pendurados no `MainWindow`."""
    janela = QWidget()
    janela.show()

    for previa in (MOCKUP, SEM_TAXA, BALCAO):
        modal = ConferenciaMesaDialog(previa, janela)
        modal.show()
        qapp.processEvents()
        assert len(janela.findChildren(Backdrop)) == 1
        modal.reject()
        modal.deleteLater()
    assentar()

    assert janela.findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar):
    """O caminho real do app: aberto com `exec()` e fechado pelo gesto — pelos
    quatro caminhos de saída, alternando."""
    pai = QWidget()
    variantes = (MOCKUP, SEM_TAXA, BALCAO)

    for volta in range(30):
        modal = ConferenciaMesaDialog(variantes[volta % 3], pai)
        saida = (modal.reject, modal._botao_cancelar.click, modal._botao_fechar.click, modal.accept)[volta % 4]
        QTimer.singleShot(0, saida)
        modal.exec()
        del modal
    assentar()

    assert pai.findChildren(ConferenciaMesaDialog) == []
    assert pai.findChildren(QWidget) == []


def test_fechar_desliga_as_tres_ligacoes(criar):
    """Depois de fechado, nenhum dos três botões mexe no resultado — as
    ligações saíram uma a uma, pelo nome."""
    modal = criar(MOCKUP)
    modal.reject()
    modal.setResult(QDialog.DialogCode.Accepted)

    modal._botao_confirmar.click()
    modal._botao_cancelar.click()
    modal._botao_fechar.click()

    assert modal.result() == QDialog.DialogCode.Accepted
    assert modal._backdrop is None


def test_soltar_os_recursos_duas_vezes_e_silencioso(criar):
    """A trava `_limpo`, medida pelo AVISO (§9.12): nesta versão do PySide6 o
    segundo `disconnect` devolve `False` e imprime `RuntimeWarning`."""
    for previa in (MOCKUP, SEM_TAXA):
        modal = criar(previa)
        modal.reject()

        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter("always")
            modal._soltar_recursos()

        assert [str(aviso.message) for aviso in avisos] == []
