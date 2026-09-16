"""O que o campo de dinheiro aceita enquanto se digita e se cola (§9.20).

`test_safe_decimal.py` cobre como o texto de um campo vira dinheiro. Este cobre
o passo de antes: o que chega a ser texto do campo. A regra é pura (sem Qt) para
poder ser exercida tecla a tecla, e `tests/ui/test_campo_moeda.py` confere que o
`QLineEdit` de verdade chega aos mesmos resultados.

`_digitar` repete o que o `QLineEdit` faz a cada tecla: insere no cursor, põe o
cursor depois do que entrou e entrega o texto ao validador.
"""

from __future__ import annotations

import random
import re
import time
from decimal import Decimal

import pytest

from gestor_comercial.services.dinheiro import LIMITE, ZERO, dinheiro
from gestor_comercial.ui.formatacao import (
    CASAS_DECIMAIS,
    DIGITOS_INTEIROS,
    safe_decimal,
    sanitizar_edicao_moeda,
)

CANONICO = re.compile(rf"\d{{0,{DIGITOS_INTEIROS}}}(,\d{{0,{CASAS_DECIMAIS}}})?")


def _digitar(teclas: str, texto: str = "", cursor: int | None = None) -> tuple[str, int]:
    posicao = len(texto) if cursor is None else cursor
    for tecla in teclas:
        montado = texto[:posicao] + tecla + texto[posicao:]
        texto, posicao = sanitizar_edicao_moeda(texto, montado, posicao + 1)
    return texto, posicao


def _colar(colado: str, texto: str = "") -> str:
    """Ctrl+V com o campo inteiro selecionado — o gesto de quem cola um valor."""
    return sanitizar_edicao_moeda(texto, colado, len(colado))[0]


# ---------------------------------------------------------------------------
# 1. Digitação
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "teclas, esperado",
    [
        ("12a,5", "12,5"),
        ("abc", ""),
        ("1 2", "12"),
        ("R$5", "5"),
        ("1e3", "13"),
        # Sinal não entra: preço e custo não são negativos, e o campo não tem
        # como montar um valor que o service recusaria.
        ("-7", "7"),
        ("+7", "7"),
        ("7%", "7"),
        # Dígitos para `str.isdigit()`, lixo para `Decimal` e para o operador.
        ("1²2", "12"),
        ("١٢3", "3"),
    ],
)
def test_letras_espacos_e_simbolos_digitados_nao_entram(teclas, esperado):
    assert _digitar(teclas)[0] == esperado


def test_tecla_recusada_deixa_o_cursor_onde_estava():
    texto, cursor = _digitar("x", texto="12,50", cursor=2)
    assert (texto, cursor) == ("12,50", 2)


def test_ponto_digitado_vira_virgula():
    assert _digitar("12.5")[0] == "12,5"


@pytest.mark.parametrize("segundo", [",", "."])
def test_segundo_separador_digitado_e_recusado(segundo):
    """O ponto depois da vírgula é o caso que importa: lido como milhar (que é
    como uma colagem "1.234,56" é lida), "12,5" + "." viraria 125."""
    assert _digitar(segundo, texto="12,5") == ("12,5", 4)
    assert _digitar(segundo, texto="12,5", cursor=0) == ("12,5", 0)


def test_terceira_casa_decimal_e_recusada_no_fim_e_no_meio():
    assert _digitar("12,505")[0] == "12,50"
    assert _digitar("7", texto="12,50", cursor=4) == ("12,50", 4)


def test_o_teto_de_digitos_inteiros_e_o_do_banco():
    assert DIGITOS_INTEIROS == len(str(int(LIMITE))) == 8
    texto, _ = _digitar("123456789")
    assert texto == "12345678"
    assert dinheiro(safe_decimal(texto)) <= LIMITE


def test_virgula_antes_de_tres_digitos_que_ja_estavam_e_recusada():
    """Aceitá-la apagaria dígitos que o operador não tocou (1250 → 1,25)."""
    assert _digitar(",", texto="1250", cursor=1) == ("1250", 1)
    assert _digitar(",", texto="1250", cursor=2) == ("12,50", 3)


def test_backspace_ate_esvaziar_nunca_quebra():
    texto, cursor = "12,50", 5
    vistos = []
    while texto:
        montado = texto[: cursor - 1] + texto[cursor:]
        texto, cursor = sanitizar_edicao_moeda(texto, montado, cursor - 1)
        vistos.append(texto)
        assert CANONICO.fullmatch(texto)
        valor = safe_decimal(texto, padrao=None)
        assert valor is None or valor >= ZERO
    assert vistos == ["12,5", "12,", "12", "1", ""]
    assert safe_decimal("", padrao=None) is None


def test_apagar_a_virgula_junta_os_digitos():
    assert sanitizar_edicao_moeda("12,50", "1250", 2) == ("1250", 2)


# ---------------------------------------------------------------------------
# 2. Colagem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "colado, texto, valor",
    [
        ("R$ 15,90 kg", "15,90", "15.90"),
        ("abc12.5", "12,5", "12.50"),
        ("R$ 29,90", "29,90", "29.90"),
        ("  12,50  ", "12,50", "12.50"),
        ("-12,50", "12,50", "12.50"),
        # Milhar: lido como a `safe_decimal` lê o que as telas mostram.
        ("R$ 1.234,56", "1234,56", "1234.56"),
        ("1,234.56", "1234,56", "1234.56"),
        ("1.234.567", "1234567", "1234567.00"),
        ("1.234.567,89", "1234567,89", "1234567.89"),
        # Excesso colado é cortado, não recusado inteiro.
        ("15,905", "15,90", "15.90"),
        ("123456789", "12345678", "12345678.00"),
    ],
)
def test_colagem_suja_vira_so_numero(colado, texto, valor):
    assert _colar(colado) == texto
    assert safe_decimal(texto, padrao=None) == Decimal(valor)


@pytest.mark.parametrize("lixo", ["R$", "abc", "kg", "  ", "-", "R$ - kg"])
def test_colagem_so_de_lixo_nao_apaga_o_valor_selecionado(lixo):
    assert sanitizar_edicao_moeda("12,50", lixo, len(lixo)) == ("12,50", 0)


def test_colagem_no_meio_nao_cria_segundo_separador():
    texto, _ = sanitizar_edicao_moeda("12,5", "12,53,4", 7)
    assert texto == "12,53"


def test_o_excesso_cortado_e_o_do_que_foi_colado_na_ordem_em_que_foi_colado():
    """Colar "05" depois de "12,5" dá "12,50". Sem olhar o cursor, a comparação
    de prefixo e sufixo acharia que o colado foi "50" ANTES do último 5 — e
    cortaria o zero, deixando "12,55", um valor que ninguém digitou."""
    assert sanitizar_edicao_moeda("12,5", "12,505", 6) == ("12,50", 5)


def test_colar_32_mil_caracteres_nao_trava():
    """O `maxLength` padrão do `QLineEdit` deixa colar 32.767 caracteres. Uma
    regra quadrática no número de separadores congelaria a tela por minutos."""
    enorme = ",." * 16_383
    inicio = time.perf_counter()
    texto, _ = sanitizar_edicao_moeda("", enorme, len(enorme))
    assert time.perf_counter() - inicio < 2.0
    assert CANONICO.fullmatch(texto)


# ---------------------------------------------------------------------------
# 3. As invariantes, sobre milhares de edições
# ---------------------------------------------------------------------------


def _edicoes(quantidade: int):
    sorteio = random.Random(20260916)
    alfabeto = "0123456789,.,.-+R$ abc\t²"
    for _ in range(quantidade):
        anterior = "".join(sorteio.choice(alfabeto) for _ in range(sorteio.randint(0, 14)))
        if sorteio.random() < 0.7:
            anterior = _colar(anterior)  # na vida real, o anterior é canônico
        inicio = sorteio.randint(0, len(anterior))
        fim = sorteio.randint(inicio, len(anterior))
        trecho = "".join(sorteio.choice(alfabeto) for _ in range(sorteio.randint(0, 6)))
        yield anterior, anterior[:inicio] + trecho + anterior[fim:], inicio + len(trecho)


def test_toda_edicao_sai_canonica_legivel_e_e_ponto_fixo():
    """O ponto fixo é o que impede o validador de entrar em laço: o Qt valida de
    novo o texto que o validador reescreveu, e a segunda passada precisa
    devolvê-lo igual."""
    for anterior, montado, cursor in _edicoes(3000):
        texto, novo_cursor = sanitizar_edicao_moeda(anterior, montado, cursor)

        contexto = f"{anterior!r} -> {montado!r} @ {cursor}"
        assert CANONICO.fullmatch(texto), contexto
        assert 0 <= novo_cursor <= len(texto), contexto
        assert sanitizar_edicao_moeda(texto, texto, novo_cursor) == (texto, novo_cursor), contexto
        valor = safe_decimal(texto, padrao=None)
        assert valor is None or ZERO <= valor <= LIMITE, contexto


def test_texto_do_campo_vira_decimal_de_duas_casas_que_o_banco_aceita():
    """A ponta que chega ao service: `Decimal` quantizado, nunca `float`
    (`dinheiro()` levanta TypeError com float, de propósito)."""
    for teclas in ("12,5", "12.5", "12", ",5", "0,05"):
        texto, _ = _digitar(teclas)
        valor = safe_decimal(texto, padrao=None)
        assert isinstance(valor, Decimal)
        assert valor.as_tuple().exponent == -2
        assert dinheiro(valor) == valor
