"""Como o texto digitado num campo vira dinheiro (`Mitigação de Falhas.md`, Fase 5).

`test_formatacao.py` cobre a ida (Decimal -> tela). Este cobre a volta, que é o
lado perigoso: é por aqui que entra o que o operador digitou de fato — com
espaço sobrando, vírgula onde o teclado mandou ponto, "R$" colado, ou nada.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from gestor_comercial.services.dinheiro import ZERO
from gestor_comercial.ui.formatacao import formatar_para_campo, safe_decimal


@pytest.mark.parametrize(
    "digitado, esperado",
    [
        # Vírgula e ponto valem os dois: o teclado numérico manda um ou outro
        # conforme o layout do Windows, e o operador não tem como saber qual.
        ("12,50", "12.50"),
        ("12.50", "12.50"),
        ("12", "12.00"),
        # Com os dois presentes, o último é o decimal. Cobre o formato que a
        # tela ao lado mostra ("R$ 1.234,50") e o americano de planilha.
        ("1.234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        # Sujeira que o operador cola ou digita sem querer.
        ("R$ 12,50", "12.50"),
        ("  12,50  ", "12.50"),
        ("R$12,50", "12.50"),
        ("-12,50", "-12.50"),
        # Arredondamento é o do balcão (meio pra cima), igual ao resto do sistema.
        ("2,345", "2.35"),
    ],
)
def test_le_o_que_o_operador_realmente_digita(digitado, esperado):
    assert safe_decimal(digitado) == Decimal(esperado)


@pytest.mark.parametrize(
    "lixo",
    ["", "   ", None, "abc", "-", "+", ",", ".", "1,2,3", "R$", "12,,50", "∞", "NaN"],
)
def test_lixo_nunca_levanta(lixo):
    """O contrato inteiro desta função: entrada quebrada não vira exceção.

    Antes da Fase 5 cada campo tinha o seu `except InvalidOperation` copiado à
    mão. Bastava o nono campo esquecer o `try` para um espaço a mais derrubar o
    clique no meio do pico.
    """
    assert safe_decimal(lixo) == ZERO
    assert safe_decimal(lixo, padrao=None) is None


def test_valor_fora_do_teto_do_banco_tambem_cai_no_padrao():
    """`NUMERIC(10,2)` não guarda isso; gravar truncado em silêncio seria pior."""
    assert safe_decimal("999999999999,00", padrao=None) is None


def test_padrao_none_e_o_modo_dos_campos_obrigatorios():
    """Num fechamento de caixa, "não consegui ler" não pode virar "contou zero".

    Ler um campo ilegível como `Decimal("0")` inventaria uma diferença de caixa
    do tamanho do turno inteiro, e o pai do Vitor iria procurar dinheiro que
    nunca faltou.
    """
    assert safe_decimal("abc", padrao=None) is None
    assert safe_decimal("abc") == ZERO


def test_ida_e_volta_fecham():
    """`formatar_para_campo` e `safe_decimal` são inversos — a trava contra
    divergência entre os dois, no espírito do §3.8."""
    for valor in (Decimal("0.00"), Decimal("12.50"), Decimal("1234.56"), Decimal("-8.09")):
        assert safe_decimal(formatar_para_campo(valor)) == valor


def test_nenhuma_view_converte_valor_no_bra_o(  # noqa: N802 - nome longo de propósito
):
    """Nenhuma tela pode voltar a fazer `Decimal(campo.text()...)` na mão.

    Esta é a trava que a Fase 5 existe para instalar. As 8 conversões antigas
    estavam todas corretas; o problema era o **padrão** — copiar a conversão
    junto com o `try` oito vezes garante que a nona cópia esqueça um dos dois.
    É o mesmo defeito que o §3.8 matou nas dez cópias de `_formatar_reais`.
    """
    import ast

    import gestor_comercial.ui as pacote_ui
    from pathlib import Path

    infratores: list[str] = []
    for arquivo in sorted(Path(pacote_ui.__file__).parent.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            # `Decimal(<algo>.text() ...)` — a assinatura da conversão crua.
            if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)):
                continue
            if no.func.id != "Decimal" or not no.args:
                continue
            if any(
                isinstance(interno, ast.Call)
                and isinstance(interno.func, ast.Attribute)
                and interno.func.attr == "text"
                for interno in ast.walk(no.args[0])
            ):
                infratores.append(f"{arquivo.name}:{no.lineno}")

    assert not infratores, (
        "conversão monetária crua voltou para uma view — use `safe_decimal` "
        "(ver `ui/formatacao.py`):\n  " + "\n  ".join(infratores)
    )
