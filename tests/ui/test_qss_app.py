"""O QSS monta nos dois temas, e as duas paletas continuam espelhadas. Ver §3.12.

A faxina do §3.12 tirou do `qss_app.py` um bloco inteiro que estava morto
(`variante="pilula-ciano"`, sobrescrito por uma segunda declaração 220 linhas
abaixo) e seis seletores que nenhum widget usava — e, junto, as chaves de tema
que só aquele bloco lia.

O risco desse tipo de limpeza é silencioso: `construir_qss_app` interpola
`{t['chave']}`, então uma chave removida a mais só aparece como `KeyError` na
hora em que o app pinta a tela — no balcão, não na suíte. Estes testes fecham
essa porta.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest

from gestor_comercial.ui.theme import tokens
from gestor_comercial.ui.theme.qss_app import construir_qss_app

PALETAS = {"escuro": tokens.TEMA_ESCURO, "claro": tokens.TEMA_CLARO}


def _seletores(qss: str) -> list[str]:
    """Os seletores de cada regra do QSS, na ordem em que aparecem.

    Tira os comentários antes de cortar: sem isso, o `/* ---- Seção ---- */`
    que precede uma regra entra colado no seletor dela e cada regra vira única.
    """
    sem_comentarios = re.sub(r"/\*.*?\*/", "", qss, flags=re.S)
    achados = []
    for bloco in sem_comentarios.split("}"):
        cabeca = " ".join(bloco.split("{")[0].split())
        if cabeca:
            achados.append(cabeca)
    return achados


@pytest.mark.parametrize("nome", sorted(PALETAS))
def test_o_qss_monta_na_paleta(nome):
    """`KeyError` aqui significa: o QSS lê uma chave que a paleta não tem mais."""
    qss = construir_qss_app(PALETAS[nome])

    assert qss.strip(), f"o QSS do tema {nome} saiu vazio"


def test_as_duas_paletas_tem_exatamente_as_mesmas_chaves():
    """O QSS é um só para os dois temas: chave que existe numa e não na outra
    quebra a troca de tema, não o boot — e por isso passa despercebida."""
    so_no_escuro = sorted(set(tokens.TEMA_ESCURO) - set(tokens.TEMA_CLARO))
    so_no_claro = sorted(set(tokens.TEMA_CLARO) - set(tokens.TEMA_ESCURO))

    assert not so_no_escuro and not so_no_claro, (
        f"só no escuro: {so_no_escuro} | só no claro: {so_no_claro}"
    )


def test_o_leitor_de_seletores_enxerga_as_regras():
    """Premissa do teste abaixo: se o corte parar de achar regra, ele passa
    verde sem ter olhado nada — que foi exatamente o que aconteceu na primeira
    versão deste arquivo."""
    seletores = _seletores(construir_qss_app(tokens.TEMA_ESCURO))

    assert len(seletores) > 100, f"o corte só achou {len(seletores)} regras no QSS"
    assert 'QPushButton[variante="pilula-ciano"]' in seletores


def test_nenhum_seletor_e_declarado_duas_vezes():
    """O defeito exato do bloco `pilula-ciano` do §3.12: duas declarações do
    mesmo seletor, a segunda vencendo em silêncio e a primeira virando peso
    morto que ainda parece documentação de estilo.

    Pseudo-estados (`:hover`, `:disabled`) e combinações com propriedade
    (`[status="ocupada"]`) são seletores diferentes e contam separado — a
    repetição que interessa é a do seletor idêntico.
    """
    contagem = Counter(_seletores(construir_qss_app(tokens.TEMA_ESCURO)))

    repetidos = sorted(nome for nome, vezes in contagem.items() if vezes > 1)

    assert not repetidos, "seletores declarados mais de uma vez:\n  " + "\n  ".join(repetidos)
