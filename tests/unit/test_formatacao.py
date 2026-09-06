"""O formato do dinheiro na tela — uma decisão, um lugar, um teste.

Ver `REMASTERIZACAO-V1.md` §3.8 e a Fase 3. Antes destes testes o sistema tinha
dez cópias de `_formatar_reais` e nenhuma verificação de nenhuma delas: a
divergência da tela de Mesas (`R$ 1.234,50` contra `R$ 1234,50` das outras nove)
viveu na base sem a suíte dizer uma palavra.

O que este arquivo tranca:

1. **O formato escolhido** — `R$ 1.234,50`, com separador de milhar.
2. **A igualdade com o cupom impresso** — tela e papel dizem o mesmo número.
3. **A ausência de cópias locais** — nenhuma view pode voltar a definir a sua.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from gestor_comercial.services.formatador_cupom import moeda
from gestor_comercial.ui.formatacao import (
    SEM_DIFERENCA,
    formatar_reais,
    formatar_reais_com_sinal,
)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("0", "R$ 0,00"),
        ("7", "R$ 7,00"),
        ("10.5", "R$ 10,50"),
        ("999.99", "R$ 999,99"),
        ("1000", "R$ 1.000,00"),
        ("1234.5", "R$ 1.234,50"),
        ("1234567.89", "R$ 1.234.567,89"),
        # O teto do NUMERIC(10,2) das colunas monetárias — o maior valor que o
        # banco aceita guardar, e portanto o maior que a tela pode receber.
        ("99999999.99", "R$ 99.999.999,99"),
    ],
)
def test_formata_com_separador_de_milhar(valor, esperado):
    assert formatar_reais(Decimal(valor)) == esperado


def test_o_separador_de_milhar_e_o_ponto_e_o_decimal_e_a_virgula():
    """A troca em três passos é fácil de errar: um `replace` desfazendo o outro
    devolveria `'1,234,50'`. Este teste é o que pega isso."""
    texto = formatar_reais(Decimal("1234.50"))

    assert texto.count(".") == 1
    assert texto.count(",") == 1
    assert texto.index(".") < texto.index(",")


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("-12", "-R$ 12,00"),
        ("-1234.5", "-R$ 1.234,50"),
    ],
)
def test_negativo_leva_o_sinal_antes_do_simbolo(valor, esperado):
    """Antes da unificação a mesma tela do Caixa mostrava `R$ -12,00` na
    diferença de fechamento e `-R$ 12,00` na linha de sangria logo acima."""
    assert formatar_reais(Decimal(valor)) == esperado


def test_com_sinal_trata_zero_como_ausencia_de_diferenca():
    """Diferença zero é a notícia boa do fechamento: merece `—`, não `R$ 0,00`."""
    assert formatar_reais_com_sinal(Decimal("0")) == SEM_DIFERENCA
    assert formatar_reais(Decimal("0")) == "R$ 0,00"


def test_com_sinal_e_igual_ao_normal_fora_do_zero():
    for valor in ("-1234.5", "-0.01", "0.01", "1234.5"):
        assert formatar_reais_com_sinal(Decimal(valor)) == formatar_reais(Decimal(valor))


@pytest.mark.parametrize(
    "valor",
    ["0", "0.01", "7", "10.5", "999.99", "1000", "1234.5", "1234567.89", "-12", "-1234.5"],
)
def test_a_tela_e_o_cupom_mostram_o_mesmo_numero(valor):
    """Se um dos dois mudar sozinho, o pai do Vitor lê uma coisa na tela e
    entrega outra impressa na mão do cliente. Este teste é o que impede isso.

    A comparação é sobre o número; o símbolo e a posição do sinal são
    convenções da tela, e o cupom não tem espaço de bobina para gastar com
    `R$` em toda linha.
    """
    numero = Decimal(valor)
    esperado = moeda(abs(numero))
    sinal = "-" if numero < 0 else ""

    assert formatar_reais(numero) == f"{sinal}R$ {esperado}"


def test_arredonda_meio_pra_cima_como_o_resto_do_sistema():
    """`f"{Decimal('0.005'):.2f}"` devolve `'0.00'`: o padrão do Python é meio
    para o par. O critério do balcão — e o do `dinheiro()`, e o do cupom — é
    meio para cima. Passar por `dinheiro()` é o que alinha os três."""
    assert formatar_reais(Decimal("0.005")) == "R$ 0,01"
    assert formatar_reais(Decimal("2.345")) == "R$ 2,35"


def test_recusa_float():
    """Herdado de `dinheiro()`: `0.1 + 0.2` em float é `0.30000000000000004`, e
    um erro desses aparece semanas depois como centavo perdido no fechamento."""
    with pytest.raises(TypeError):
        formatar_reais(10.5)


def test_nenhuma_tela_define_a_propria_copia():
    """A regra que impede a divergência de voltar.

    Dez cópias não nasceram de uma vez: nasceram uma por tela, cada uma
    parecendo inofensiva. Este teste falha na primeira que reaparecer.
    """
    ui = Path(__file__).resolve().parents[2] / "src" / "gestor_comercial" / "ui"
    padrao = re.compile(r"^def _?formatar_reais", re.MULTILINE)

    culpados = [
        caminho.relative_to(ui).as_posix()
        for caminho in ui.rglob("*.py")
        if caminho.name != "formatacao.py" and padrao.search(caminho.read_text(encoding="utf-8"))
    ]

    assert culpados == [], (
        f"{culpados} voltaram a definir a própria formatação de dinheiro. "
        "Importe de `gestor_comercial.ui.formatacao`."
    )
