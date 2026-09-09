"""O teclado numérico e o acumulador de centavos que os três modais dividem.

Esta é a peça por onde passa **todo valor em dinheiro digitado à mão** no
sistema: sangria, reforço, despesa, fundo de troco e as duas contagens do
fechamento. Um erro aqui não aparece como tela feia — aparece como diferença de
caixa no fim da noite, e o operador não tem como saber de onde veio.

Os testes cobrem, nessa ordem:

1. **o acumulador conta certo** — dígito pela direita, `00`, apagar, e o teto
   amarrado ao do banco;
2. **o teto é o do banco, não um número escolhido na tela** — sem essa amarra o
   numpad monta um valor que o service recusaria com `ValueError`, que não está
   em `_ERROS_SERVICE` e subiria como estouro no balcão;
3. **o teclado só avisa; quem soma é o acumulador** — é essa separação que
   permite ao modal de fechamento apontar o mesmo teclado para duas contagens;
4. **nada sobra na memória** — o RNF do Celeron.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gestor_comercial.services.dinheiro import LIMITE, dinheiro
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.teclado_numerico import (
    ROTULO_APAGAR,
    ROTULO_DOIS_ZEROS,
    AcumuladorDeCentavos,
    TecladoNumerico,
)


@pytest.fixture
def acumulador():
    return AcumuladorDeCentavos()


@pytest.fixture
def teclado(qapp):
    widget = TecladoNumerico()
    yield widget
    widget.deleteLater()


# ---------------------------------------------------------------------------
# O acumulador
# ---------------------------------------------------------------------------


def test_o_valor_entra_pela_direita_como_maquina_de_cartao(acumulador):
    """É o ganho central de todos os modais que usam esta peça: `5`,`0`,`0`,`0`
    tem que dar R$ 50,00 e nunca "valor ilegível"."""
    esperados = ["R$ 0,05", "R$ 0,50", "R$ 5,00", "R$ 50,00"]

    for digito, esperado in zip("5000", esperados):
        acumulador.digitar(digito)
        assert acumulador.texto == esperado


def test_a_tecla_00_empurra_dois_zeros_de_uma_vez(acumulador):
    """A tecla existe porque valor de caixa é redondo: R$ 5,00 são dois toques
    com ela e três sem."""
    acumulador.digitar("5")
    acumulador.digitar(ROTULO_DOIS_ZEROS)

    assert acumulador.valor == Decimal("5.00")


def test_o_apagar_tira_so_o_ultimo_digito(acumulador):
    acumulador.digitar("5000")

    acumulador.apagar()

    assert acumulador.texto == "R$ 5,00"


def test_apagar_com_o_visor_zerado_nao_quebra(acumulador):
    """O dedo bate no apagar antes de digitar o tempo todo. Zero dividido
    continua zero — o que não pode é virar negativo nem estourar."""
    acumulador.apagar()
    acumulador.apagar()

    assert acumulador.valor == Decimal("0.00")


def test_o_valor_sai_como_decimal_de_duas_casas(acumulador):
    acumulador.digitar("5000")

    assert acumulador.valor == Decimal("50.00")
    assert acumulador.valor.as_tuple().exponent == -2


def test_o_texto_usa_o_mesmo_formato_do_resto_do_app(acumulador):
    """§3.8: o valor que o operador confere aqui sai idêntico na tabela de
    movimentos e no relatório de fechamento impresso. Uma segunda formatação de
    dinheiro é como a divergência `R$ 1234,50` × `R$ 1.234,50` voltaria."""
    acumulador.digitar("123456")

    assert acumulador.texto == formatar_reais(Decimal("1234.56"))


def test_o_teto_do_acumulador_e_o_teto_do_banco(acumulador):
    """Amarrado a `dinheiro.LIMITE`, e não a um número escolhido na tela: sem
    isso o numpad conseguiria montar um valor que o service recusaria com
    `ValueError` — que não está em `_ERROS_SERVICE` e subiria como estouro no
    balcão, não como mensagem na linha de erro."""
    assert AcumuladorDeCentavos.TETO_EM_CENTAVOS == int(LIMITE * 100)

    acumulador.digitar("9" * 10)
    no_teto = acumulador.valor

    assert no_teto == LIMITE
    assert dinheiro(no_teto) == no_teto, "o teto do visor tem que passar por dinheiro()"
    assert acumulador.digitar("9") is False
    assert acumulador.valor == no_teto, "o dígito que estouraria o teto não pode entrar"


def test_o_00_no_teto_nao_entra_pela_metade(acumulador):
    """Os dígitos entram todos ou nenhum. Meio `00` deixaria o visor num valor
    que o operador não digitou — e ele olha para o visor, não para a tecla."""
    acumulador.digitar("9" * 9)
    antes = acumulador.valor

    assert acumulador.digitar(ROTULO_DOIS_ZEROS) is False
    assert acumulador.valor == antes


def test_o_atalho_soma_ao_que_ja_esta_no_visor(acumulador):
    acumulador.digitar("550")  # R$ 5,50

    assert acumulador.somar_reais(50) is True
    assert acumulador.valor == Decimal("55.50")


def test_atalho_que_estouraria_o_teto_nao_faz_nada(acumulador):
    acumulador.digitar("9" * 10)

    assert acumulador.somar_reais(500) is False
    assert acumulador.valor == LIMITE


def test_definir_troca_o_valor_inteiro(acumulador):
    """O caminho das pílulas da abertura e do "preencher valores esperados" do
    fechamento."""
    acumulador.digitar("550")

    assert acumulador.definir(Decimal("970.00")) is True
    assert acumulador.valor == Decimal("970.00")


def test_definir_recusa_valor_negativo(acumulador):
    """O saldo esperado da gaveta fica negativo quando as sangrias passam do que
    entrou. Preencher a contagem FÍSICA com um número negativo seria afirmar que
    a gaveta deve dinheiro — e o numpad não tem como digitar isso de volta."""
    acumulador.digitar("100")

    assert acumulador.definir(Decimal("-1.00")) is False
    assert acumulador.valor == Decimal("1.00")


def test_definir_recusa_acima_do_teto_sem_levantar(acumulador):
    """`dinheiro()` levantaria `ValueError` aqui, e este método é chamado de
    dentro de slot de clique: um estouro ali evapora sem mensagem nenhuma (ver
    `core/resilience.py`)."""
    assert acumulador.definir(LIMITE + Decimal("0.01")) is False
    assert acumulador.valor == Decimal("0.00")


def test_zerar_apaga_o_valor(acumulador):
    acumulador.digitar("5000")

    acumulador.zerar()

    assert acumulador.valor == Decimal("0.00")


# ---------------------------------------------------------------------------
# O teclado
# ---------------------------------------------------------------------------


def test_o_teclado_tem_as_treze_teclas_do_mockup(teclado):
    esperadas = set("0123456789") | {ROTULO_DOIS_ZEROS, ROTULO_APAGAR}

    assert set(teclado.teclas) == esperadas


def test_a_tecla_de_digito_avisa_qual_foi(qapp, teclado):
    apertados: list[str] = []
    teclado.digitou.connect(apertados.append)

    teclado.teclas["7"].click()
    teclado.teclas[ROTULO_DOIS_ZEROS].click()

    assert apertados == ["7", ROTULO_DOIS_ZEROS]


def test_a_tecla_de_apagar_avisa_por_um_sinal_proprio(qapp, teclado):
    """Separada do dígito porque o destino é outro: quem escuta não precisa
    saber que "⌫" não é número."""
    apagou: list[bool] = []
    digitou: list[str] = []
    teclado.apagou.connect(lambda: apagou.append(True))
    teclado.digitou.connect(digitou.append)

    teclado.teclas[ROTULO_APAGAR].click()

    assert apagou == [True]
    assert digitou == []


def test_nenhuma_tecla_rouba_o_foco_do_dialogo(teclado):
    """Num modal em cartão quem lê o teclado é o DIÁLOGO, no `keyPressEvent`
    dele. Com o foco parado numa tecla, o Enter dispararia aquela tecla em vez
    de confirmar, e o Espaço "clicaria" a última usada — bug clássico de teclado
    em Qt, e no balcão ele vira valor errado gravado na gaveta."""
    from PySide6.QtCore import Qt

    for tecla in teclado.teclas.values():
        assert tecla.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert tecla.autoDefault() is False


def test_soltar_libera_a_tabela_de_teclas(teclado):
    """O RNF do Celeron: os botões morrem com o widget, mas a tabela guarda a
    referência do lado Python — é ela que sobreviveria a uma tarde de idas e
    voltas ao modal."""
    assert teclado.teclas

    teclado.soltar()

    assert teclado.teclas == {}
