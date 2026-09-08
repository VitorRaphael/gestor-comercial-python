"""O modal de sangria/reforço/despesa: parametrização, visor, teclado e limpeza.

Esta é a tela por onde **dinheiro sai e entra da gaveta sem passar por venda**.
Um erro aqui não aparece como tela feia: aparece como diferença no fechamento do
turno, horas depois, sem ninguém conseguir explicar. Os testes cobrem, nessa
ordem:

1. **uma classe veste as três operações** — sangria, reforço e despesa saem da
   mesma `OPERACOES`, e é dela que a tela de Caixa também tira o rótulo do botão
   e a cor do badge da tabela. Enquanto forem listas separadas, uma pode mudar
   sozinha (é o remédio que o §9.5 aplicou em `CARGOS`);
2. **o visor conta centavos, não texto** — é o ganho central do §9.6: digitar
   `5`,`0`,`0`,`0` tem que dar `R$ 50,00` e nunca "valor ilegível". O teto é o do
   banco, não um número inventado aqui;
3. **o valor que sai é o valor que a view grava** — com a `CaixaView` de
   verdade, o service de verdade e o banco de verdade, porque a promessa do §9.6
   é "nenhuma regra financeira mudou" e essa promessa se prova gravando;
4. **o teclado do balcão faz o mesmo que o dedo** — numérico USB, `Enter`,
   `Esc`, `Backspace` e o `Tab` que alterna visor ↔ descrição;
5. **nada sobra na memória** — o RNF do Celeron. E, o oposto: o valor digitado
   NÃO pode ser apagado no fechamento, senão toda sangria vira R$ 0,00.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QWidget

from gestor_comercial.domain.enums import TipoMovimento
from gestor_comercial.services.dinheiro import LIMITE, dinheiro
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.theme import tokens
from gestor_comercial.ui.views.caixa_view import CaixaView
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.movimentacao_caixa_dialog import (
    ATALHOS_EM_REAIS,
    OPERACOES,
    MovimentacaoCaixaDialog,
    papel_do_movimento,
    rotulo_do_movimento,
)

TIPOS = tuple(OPERACOES)


@pytest.fixture
def abrir(qapp):
    """Monta o modal sem `exec()` — e o descarta no fim do teste."""
    criados: list[MovimentacaoCaixaDialog] = []

    def _abrir(tipo=TipoMovimento.SANGRIA, operador=None, pai=None):
        modal = MovimentacaoCaixaDialog(tipo, operador, pai)
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        modal.deleteLater()


@pytest.fixture
def caixa_na_tela(qapp, caixas_service, impressao, gerente):
    """A tela de Caixa com o turno aberto — o estado em que o botão de sangria vive."""
    caixas_service.abrir(Decimal("100.00"))
    view = CaixaView(caixas_service, impressao)
    yield view
    view.deleteLater()


def _tecla(modal: MovimentacaoCaixaDialog, tecla: Qt.Key, texto: str = "") -> None:
    """Manda a tecla pelo mesmo caminho do teclado físico: o `keyPressEvent`."""
    modal.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier, texto)
    )


def _digitar(modal: MovimentacaoCaixaDialog, digitos: str) -> None:
    for digito in digitos:
        _tecla(modal, Qt.Key(Qt.Key.Key_0 + int(digito)), digito)


def _clicar(modal: MovimentacaoCaixaDialog, rotulo: str) -> None:
    """Clica numa tecla do numpad como o dedo clica — pelo sinal, não pelo estado."""
    modal._teclas[rotulo].click()


# ---------------------------------------------------------------------------
# Uma classe, três operações
# ---------------------------------------------------------------------------


def test_as_movimentacoes_manuais_sao_exatamente_as_do_enum_menos_consumo():
    """`CONSUMO_FUNCIONARIO` fica de fora porque `registrar_movimento` o recusa:
    consumo interno já é rastreado como pagamento da comanda, e um movimento
    manual descontaria a mesma dívida uma segunda vez. Oferecer o botão seria
    oferecer um erro — e é este teste que segura o dia em que alguém "completar"
    a lista com o quarto membro do enum."""
    esperado = set(TipoMovimento) - {TipoMovimento.CONSUMO_FUNCIONARIO}

    assert set(OPERACOES) == esperado


def test_consumo_de_funcionario_nao_constroi_o_modal(qapp):
    """Falhar na construção, e não abrir um cartão sem título, sem cor e sem
    sugestões que o service recusaria no fim."""
    with pytest.raises(ValueError, match="movimentação manual"):
        MovimentacaoCaixaDialog(TipoMovimento.CONSUMO_FUNCIONARIO)


@pytest.mark.parametrize("tipo", TIPOS, ids=lambda t: t.value)
def test_cada_operacao_veste_o_proprio_texto(abrir, tipo):
    operacao = OPERACOES[tipo]
    modal = abrir(tipo)

    assert modal.windowTitle() == operacao.titulo
    assert modal._botao_confirmar.text() == operacao.rotulo_confirmar
    assert modal._campo_descricao.placeholderText() == operacao.placeholder
    assert tuple(modal._chips) == operacao.tags


@pytest.mark.parametrize("tipo", TIPOS, ids=lambda t: t.value)
def test_o_papel_da_operacao_chega_aos_dois_lugares_que_tem_cor(abrir, tipo):
    """O QSS pinta por `[operacao="..."]`, e são só dois widgets: o badge do
    cabeçalho e o botão que grava. Se a propriedade não subir, o cartão abre
    cinza e a sangria fica igual ao reforço."""
    modal = abrir(tipo)
    badge = modal._botao_fechar.parentWidget().findChild(QWidget, "movCaixaBadge")

    assert badge is not None
    assert badge.property("operacao") == OPERACOES[tipo].papel
    assert modal._botao_confirmar.property("operacao") == OPERACOES[tipo].papel


@pytest.mark.parametrize("nome", ["escuro", "claro"])
def test_as_cores_de_cada_operacao_existem_nas_duas_paletas(nome):
    """`Operacao` guarda NOMES de token, e o `_IconeMovimento` os lê para
    pintar. Um nome errado estouraria `KeyError` dentro de um `paintEvent` —
    que, blindado por `nao_deixa_escapar`, simplesmente não desenha nada e não
    avisa ninguém. Este teste é o aviso."""
    paleta = {"escuro": tokens.TEMA_ESCURO, "claro": tokens.TEMA_CLARO}[nome]

    faltando = [
        chave
        for operacao in OPERACOES.values()
        for chave in (operacao.token_tinta, operacao.token_glifo)
        if chave not in paleta
    ]

    assert faltando == [], f"tokens ausentes no tema {nome}: {faltando}"


def test_a_tela_de_caixa_le_o_rotulo_e_o_papel_da_mesma_lista(caixa_na_tela):
    """A outra metade do DRY: o botão "+ Sangria" e o badge da tabela saem de
    `OPERACOES`, não de dicionários paralelos dentro da view. Eram três listas
    dizendo a mesma coisa, e "Reforço" precisava estar certo nas três."""
    rotulos = {
        tipo: botao.text() for tipo, botao in caixa_na_tela._botoes_movimento_por_tipo.items()
    }

    assert rotulos == {tipo: f"+ {op.titulo}" for tipo, op in OPERACOES.items()}
    assert [papel_do_movimento(t) for t in OPERACOES] == ["sangria", "reforco", "despesa"]


def test_o_consumo_interno_nao_sai_em_branco_na_tabela():
    """Ele não tem `Operacao` (não é movimentação manual), mas aparece na tabela
    de movimentos do turno, gravado por outro caminho. Sem o valor cru do enum
    como reserva, a coluna "Tipo" daquela linha sairia vazia."""
    assert rotulo_do_movimento(TipoMovimento.CONSUMO_FUNCIONARIO) == "CONSUMO_FUNCIONARIO"
    assert papel_do_movimento(TipoMovimento.CONSUMO_FUNCIONARIO) == ""


# ---------------------------------------------------------------------------
# O visor — centavos entrando pela direita
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("digitados", "esperado"),
    [
        ("", "R$ 0,00"),
        ("5", "R$ 0,05"),
        ("50", "R$ 0,50"),
        ("500", "R$ 5,00"),
        ("5000", "R$ 50,00"),
        ("012345", "R$ 123,45"),
        ("100000", "R$ 1.000,00"),
    ],
)
def test_os_digitos_entram_pela_direita_como_maquina_de_cartao(abrir, digitados, esperado):
    """O comportamento que apaga a classe inteira de defeito do modal antigo:
    não existe mais "valor ilegível", porque nunca houve texto para ler de
    volta. O zero à esquerda de `012345` some sozinho pela mesma razão."""
    modal = abrir()

    _digitar(modal, digitados)

    assert modal._label_valor.text() == esperado


def test_a_tecla_00_empurra_dois_zeros_de_uma_vez(abrir):
    """A tecla existe porque valor de caixa é redondo: R$ 50,00 são quatro
    toques com ela e cinco sem."""
    modal = abrir()

    _clicar(modal, "5")
    _clicar(modal, "00")

    assert modal.valor() == Decimal("5.00")


def test_o_apagar_tira_so_o_ultimo_digito(abrir):
    modal = abrir()
    _digitar(modal, "5000")

    _clicar(modal, "⌫")

    assert modal._label_valor.text() == "R$ 5,00"


def test_apagar_com_o_visor_zerado_nao_quebra(abrir):
    """O dedo bate no ⌫ antes de digitar o tempo todo. Zero dividido continua
    zero — o que não pode é virar valor negativo nem estourar."""
    modal = abrir()

    _clicar(modal, "⌫")
    _clicar(modal, "⌫")

    assert modal.valor() == Decimal("0.00")


def test_o_visor_usa_o_mesmo_formato_do_resto_do_app(abrir):
    """§3.8: o valor que o operador confere aqui tem que sair idêntico na tabela
    de movimentos e no relatório de fechamento impresso. Uma segunda formatação
    de dinheiro é como a divergência `R$ 1234,50` × `R$ 1.234,50` voltaria."""
    modal = abrir()

    _digitar(modal, "123456")

    assert modal._label_valor.text() == formatar_reais(Decimal("1234.56"))


def test_o_valor_sai_como_decimal_de_duas_casas(abrir):
    modal = abrir()

    _digitar(modal, "5000")

    assert modal.valor() == Decimal("50.00")
    assert modal.valor().as_tuple().exponent == -2


def test_o_teto_do_visor_e_o_teto_do_banco(abrir):
    """Amarrado a `dinheiro.LIMITE`, e não a um número escolhido na tela: sem
    isso o numpad conseguiria montar um valor que `registrar_movimento`
    recusaria com `ValueError` — que não está em `_ERROS_SERVICE` e subiria como
    estouro no balcão, não como mensagem na linha de erro."""
    modal = abrir()

    assert modal.TETO_EM_CENTAVOS == int(LIMITE * 100)

    _digitar(modal, "9" * 10)
    no_teto = modal.valor()
    _digitar(modal, "9")

    assert no_teto == LIMITE
    assert modal.valor() == no_teto, "o dígito que estouraria o teto não pode entrar"
    assert dinheiro(no_teto) == no_teto, "o teto do visor tem que passar por dinheiro()"


@pytest.mark.parametrize("reais", ATALHOS_EM_REAIS)
def test_os_atalhos_somam_ao_que_ja_esta_no_visor(abrir, reais):
    modal = abrir()
    _digitar(modal, "550")  # R$ 5,50

    modal._atalhos[reais].click()

    assert modal.valor() == Decimal("5.50") + reais


def test_atalho_que_estouraria_o_teto_nao_faz_nada(abrir):
    """Ignorar é melhor que cortar ou zerar: o operador olha para o visor, não
    para a pílula que apertou."""
    modal = abrir()
    _digitar(modal, "9" * 10)

    modal._atalhos[500].click()

    assert modal.valor() == LIMITE


# ---------------------------------------------------------------------------
# Descrição e chips
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", TIPOS, ids=lambda t: t.value)
def test_o_chip_preenche_a_descricao(abrir, tipo):
    modal = abrir(tipo)
    tag = OPERACOES[tipo].tags[0]

    modal._chips[tag].click()

    assert modal.resultado().descricao == tag


def test_o_chip_substitui_em_vez_de_emendar(abrir):
    """Emendar produziria "Envio ao cofreTroco para o malote" no primeiro clique
    errado, e o operador teria que apagar com o dedo dentro do campo — que é
    exatamente o que os chips existem para evitar."""
    modal = abrir(TipoMovimento.SANGRIA)

    modal._chips["Envio ao cofre"].click()
    modal._chips["Troco para o malote"].click()

    assert modal.resultado().descricao == "Troco para o malote"


def test_descricao_vazia_vira_none(abrir):
    """`MovimentoCaixa.descricao` é opcional, e o service já trata `None`.
    Gravar `""` faria a tabela de movimentos mostrar uma célula vazia que parece
    dado perdido em vez de campo não preenchido."""
    modal = abrir()

    modal._campo_descricao.setText("   ")

    assert modal.resultado().descricao is None


def test_a_descricao_sai_sem_espaco_sobrando(abrir):
    modal = abrir()

    modal._campo_descricao.setText("  troco para o malote  ")

    assert modal.resultado().descricao == "troco para o malote"


# ---------------------------------------------------------------------------
# Confirmar, cancelar e teclado
# ---------------------------------------------------------------------------


def test_com_o_visor_zerado_o_botao_de_confirmar_fica_desligado(abrir):
    """`registrar_movimento` recusa valor menor ou igual a zero. Deixar o botão
    aceso só faria o operador levar o erro de volta para a linha vermelha da
    tela de trás."""
    modal = abrir()
    assert modal._botao_confirmar.isEnabled() is False

    _digitar(modal, "5")
    assert modal._botao_confirmar.isEnabled() is True

    _clicar(modal, "⌫")
    assert modal._botao_confirmar.isEnabled() is False


def test_enter_confirma_o_lancamento(qapp, abrir):
    modal = abrir()
    _digitar(modal, "5000")

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Return))

    assert modal.exec() == QDialog.DialogCode.Accepted
    assert modal.resultado().valor == Decimal("50.00")


def test_enter_com_o_visor_zerado_nao_confirma(qapp, abrir):
    """O Enter passa pelo mesmo portão do botão: sem valor, não fecha. Sem isto
    o teclado seria um caminho paralelo por onde o movimento de R$ 0,00
    escaparia até o service."""
    modal = abrir()

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Return))
    QTimer.singleShot(30, modal.reject)

    assert modal.exec() == QDialog.DialogCode.Rejected


def test_esc_fecha_sem_gravar(qapp, abrir):
    modal = abrir()
    _digitar(modal, "5000")

    QTimer.singleShot(0, lambda: _tecla(modal, Qt.Key.Key_Escape))

    assert modal.exec() == QDialog.DialogCode.Rejected


def test_backspace_do_teclado_fisico_apaga_no_visor(abrir):
    """O balcão tem teclado numérico USB, e ele tem que fazer o mesmo que o
    dedo na tela — inclusive apagar."""
    modal = abrir()
    _digitar(modal, "5000")

    _tecla(modal, Qt.Key.Key_Backspace)

    assert modal.valor() == Decimal("5.00")


def test_tab_leva_o_foco_para_a_descricao_e_o_traz_de_volta(qapp, abrir):
    """Os dois lados do `Tab`, que é o que o briefing pediu.

    O diálogo tem `FocusPolicy.NoFocus` (como todo modal em cartão daqui), então
    a navegação natural do Qt pularia o diálogo e o `Tab` não faria nada: quem
    manda o foco para o campo é o `keyPressEvent`, e quem o traz de volta é o
    `eventFilter` instalado no campo.
    """
    modal = abrir()
    modal.show()
    qapp.processEvents()

    _tecla(modal, Qt.Key.Key_Tab)
    assert modal._campo_descricao.hasFocus() is True

    modal.eventFilter(
        modal._campo_descricao,
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier),
    )
    assert modal.hasFocus() is True

    modal.reject()


def test_o_anel_do_visor_diz_para_onde_o_digito_vai(qapp, abrir):
    """Com o cursor na descrição, dígito é texto de descrição — e é assim que
    tem que ser. O anel é o único sinal disso: sem ele, o operador só descobre
    a diferença depois de ler o que saiu."""
    modal = abrir()
    modal.show()
    qapp.processEvents()
    assert modal._visor.property("foco") is True

    _tecla(modal, Qt.Key.Key_Tab)

    assert modal._visor.property("foco") is False
    modal.reject()


def test_o_dialogo_ignora_digito_unicode_que_nao_e_algarismo(abrir):
    """`"²".isdigit()` é `True` em Python, e `int("²")` estoura. O acumulador
    só aceita os dez algarismos de verdade."""
    modal = abrir()

    _tecla(modal, Qt.Key.Key_unknown, "²")

    assert modal.valor() == Decimal("0.00")


# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------


def test_o_rodape_diz_quem_esta_operando(abrir):
    """Sangria e despesa exigem gerente, e a gaveta é conferida no fim do turno:
    quem está com o terminal na mão precisa ver o próprio nome antes de tirar
    dinheiro."""
    modal = abrir(operador="Caixa Turno - Noite")

    assert modal._label_operador.text() == "OPERADOR · CAIXA TURNO - NOITE"


def test_sem_ninguem_logado_o_rodape_mostra_travessao(abrir):
    """A view lê `usuario_logado` (que pode ser `None`) e não `usuario_atual()`
    (que levantaria): quem barra a ação sem login é o service, na hora de
    gravar — o rótulo da tela não pode impedir o modal de abrir."""
    assert abrir(operador=None)._label_operador.text() == "OPERADOR · —"
    assert abrir(operador="   ")._label_operador.text() == "OPERADOR · —"


# ---------------------------------------------------------------------------
# O caminho real — a view, o service e o banco
# ---------------------------------------------------------------------------


def _lancar_pela_tela(qapp, view, tipo, digitos, descricao=None):
    """Aperta o botão da tela de Caixa e opera o modal que abrir, de verdade.

    É a única forma de provar a promessa do §9.6 ("nenhuma regra financeira
    mudou"): o `executar_modal` roda, o `exec()` roda, `registrar_movimento`
    grava e o banco responde. Um dublê do diálogo provaria só que o teste sabe
    chamar o service.
    """

    def operar() -> None:
        modal = view.findChildren(MovimentacaoCaixaDialog)[0]
        _digitar(modal, digitos)
        if descricao is not None:
            modal._campo_descricao.setText(descricao)
        modal.accept()

    QTimer.singleShot(0, operar)
    view._botoes_movimento_por_tipo[tipo].click()
    qapp.processEvents()


@pytest.mark.parametrize("tipo", TIPOS, ids=lambda t: t.value)
def test_a_tela_grava_o_movimento_com_tipo_valor_e_descricao(
    qapp, caixa_na_tela, caixas_service, tipo
):
    _lancar_pela_tela(qapp, caixa_na_tela, tipo, "5000", "teste de balcão")

    movimentos = caixas_service.listar_movimentos(caixa_na_tela._caixa_id)

    assert len(movimentos) == 1
    assert movimentos[0].tipo is tipo
    assert movimentos[0].valor == Decimal("50.00")
    assert movimentos[0].descricao == "teste de balcão"
    assert caixa_na_tela._label_erro.text() == ""


def test_a_sangria_sai_do_saldo_esperado_da_gaveta(qapp, caixa_na_tela, caixas_service):
    """A conta do saldo é do `CaixaService` e não mudou — o teste está aqui para
    provar que o valor que o numpad monta é o mesmo que entra nela."""
    _lancar_pela_tela(qapp, caixa_na_tela, TipoMovimento.SANGRIA, "5000")

    assert caixas_service.calcular_saldo_esperado(caixa_na_tela._caixa_id) == Decimal("50.00")


def test_cancelar_no_modal_nao_grava_nada(qapp, caixa_na_tela, caixas_service):
    def desistir() -> None:
        modal = caixa_na_tela.findChildren(MovimentacaoCaixaDialog)[0]
        _digitar(modal, "5000")
        modal.reject()

    QTimer.singleShot(0, desistir)
    caixa_na_tela._botoes_movimento_por_tipo[TipoMovimento.SANGRIA].click()
    qapp.processEvents()

    assert caixas_service.listar_movimentos(caixa_na_tela._caixa_id) == []


# ---------------------------------------------------------------------------
# Ciclo de vida — o RNF do Celeron
# ---------------------------------------------------------------------------


def test_o_valor_sobrevive_ao_fechamento_para_a_view_ler(abrir):
    """O contrário da limpeza do modal de PIN, e de propósito.

    Lá o segredo digitado tem que sumir da memória em `done()`, e ninguém o lê
    de volta. Aqui `resultado()` é lido DEPOIS do `exec()` (§3.2), e zerar o
    visor no fechamento faria toda sangria ser gravada como R$ 0,00 — sem erro,
    sem aviso, com o turno fechando errado no fim da noite.
    """
    modal = abrir()
    _digitar(modal, "5000")
    modal._campo_descricao.setText("envio ao cofre")

    modal.accept()

    assert modal.resultado().valor == Decimal("50.00")
    assert modal.resultado().descricao == "envio ao cofre"


def test_fechar_solta_as_tabelas_de_widget(qapp, abrir):
    modal = abrir()
    assert modal._atalhos and modal._teclas and modal._chips

    modal.reject()

    assert modal._atalhos == {}
    assert modal._teclas == {}
    assert modal._chips == {}


def test_fechar_remove_o_filtro_do_campo_de_descricao(qapp, abrir):
    """O `unbind` que o briefing pediu. É o único `eventFilter` do arquivo, e
    ele guarda uma referência do diálogo dentro do campo: deixá-lo instalado é
    o tipo de nó que sobrevive ao `deleteLater()` do lado Python."""
    modal = abrir()
    removidos: list[object] = []
    modal._campo_descricao.removeEventFilter = removidos.append

    modal.reject()

    assert removidos == [modal]


def test_o_filtro_do_campo_so_engole_o_tab(qapp, abrir):
    """Consumir mais que o `Tab` faria o campo parar de aceitar letra — e a
    descrição é justamente o que o operador digita ali."""
    modal = abrir()
    evento = QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier, "a"
    )

    assert modal.eventFilter(modal._campo_descricao, evento) is False
    assert modal.eventFilter(modal._campo_descricao, QEvent(QEvent.Type.Paint)) is False


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar):
    """O escurecedor é filho da JANELA, não do diálogo: `deleteLater()` do
    diálogo não o levaria junto. Um turno inteiro de sangrias e reforços
    deixaria uma pilha de retângulos pretos invisíveis pendurada no
    `MainWindow`, que vive o processo inteiro."""
    pai = QWidget()
    pai.show()

    for _ in range(10):
        modal = MovimentacaoCaixaDialog(TipoMovimento.SANGRIA, "Gerente", pai)
        modal.show()
        qapp.processEvents()
        modal.reject()
        modal.deleteLater()
    assentar()

    assert pai.window().findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar, caixa_na_tela):
    """O caminho real: a tela de Caixa como parent, `exec()` de verdade e
    fechamento pelo Cancelar. Se alguém trocar `executar_modal()` por um
    `.exec()` cru em `_abrir_modal_movimento`, é aqui que aparece."""
    for _ in range(30):
        modal = MovimentacaoCaixaDialog(TipoMovimento.REFORCO, "Gerente", caixa_na_tela)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        modal.deleteLater()
        del modal
    assentar()

    assert caixa_na_tela.findChildren(MovimentacaoCaixaDialog) == []


def test_o_cartao_cabe_na_tela_do_food_truck(qapp, abrir):
    """1366x768 é a máquina do balcão, e o Windows come uma barra de tarefas.

    A moldura é 728px de altura útil, e a suíte roda `offscreen` — que sobe sem
    banco de fontes e mede TUDO maior que a máquina real (medido: 680px aqui
    contra 611px no Windows). Ou seja, o teste é pessimista de propósito: se
    passa aqui, passa lá. A despesa é a que estoura primeiro, porque tem quatro
    sugestões de descrição e é a que quebra a faixa de chips em duas fileiras.
    """
    ALTURA_UTIL_PX = 728

    for tipo in OPERACOES:
        modal = abrir(tipo)
        modal.show()
        qapp.processEvents()
        modal.adjustSize()
        altura = modal.height()
        modal.reject()

        assert altura <= ALTURA_UTIL_PX, (
            f"o cartão de {tipo.value} pediu {altura}px de altura — num monitor de "
            "768px ele sairia da tela pela borda de baixo"
        )
