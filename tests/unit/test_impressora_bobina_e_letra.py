"""A bobina gravada e a letra grossa da impressora, no service. §9.22.

A regra de cada parâmetro, no mesmo formato do `colunas` que já existia:

* **no cadastro**, sem informar nada, sai o de sempre — 48 colunas, 80mm e letra
  fina —, e uma bobina não informada sai das colunas pela regra de antes de
  ela ser gravada (até 40 colunas é 58mm);
* **na edição**, `None` é "não mexe". Em especial, trocar só as colunas NÃO
  deduz a bobina de novo: "58mm + 48 col." é uma escolha que o gerente pode
  fazer, e é por isso que a bobina passou a ser gravada;
* **bobina fora de 58/80 é recusada** com mensagem, pela mesma porta que recusa
  colunas fora da faixa.
"""

from __future__ import annotations

import pytest

from gestor_comercial.domain.impressora import (
    BOBINA_58MM,
    BOBINA_80MM,
    TETO_COLUNAS_58MM,
    bobina_mm_das_colunas,
)
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.exceptions import RegraDeNegocioError


@pytest.fixture
def cardapio(uow, auth, gerente):
    return CardapioService(uow, auth)


@pytest.mark.parametrize(
    ("colunas", "bobina"),
    [(20, 58), (32, 58), (TETO_COLUNAS_58MM, 58), (TETO_COLUNAS_58MM + 1, 80), (42, 80), (48, 80), (96, 80)],
)
def test_a_regra_de_antes_le_a_bobina_das_colunas(colunas, bobina):
    assert bobina_mm_das_colunas(colunas) == bobina


# ----------------------------------------------------------------------
# Cadastro
# ----------------------------------------------------------------------


def test_o_cadastro_sem_nada_nasce_48_colunas_80mm_e_letra_fina(cardapio):
    impressora = cardapio.criar_impressora("Cozinha")

    assert (impressora.colunas, impressora.bobina_mm, impressora.letra_grossa) == (48, 80, False)


def test_sem_bobina_ela_sai_das_colunas(cardapio):
    """Quem chama pelo caminho antigo (`colunas=32`) ganha a bobina de 58mm."""
    impressora = cardapio.criar_impressora("Caixa", colunas=32)

    assert impressora.bobina_mm == BOBINA_58MM


@pytest.mark.parametrize(("colunas", "bobina_mm"), [(48, 58), (80, 58), (32, 80), (64, 80)])
def test_o_cadastro_grava_a_combinacao_escolhida(cardapio, colunas, bobina_mm):
    """Qualquer largura em qualquer bobina — a liberdade do pedido."""
    impressora = cardapio.criar_impressora("Caixa", colunas=colunas, bobina_mm=bobina_mm, letra_grossa=True)

    assert (impressora.colunas, impressora.bobina_mm, impressora.letra_grossa) == (colunas, bobina_mm, True)


def test_a_bobina_chega_como_texto_e_e_convertida(cardapio):
    """A porta do `_inteiro_positivo`: o que vem de campo de texto vira número."""
    assert cardapio.criar_impressora("Caixa", bobina_mm=" 58 ").bobina_mm == 58


@pytest.mark.parametrize("bobina_mm", [0, 76, 110, -58, "80mm", "abc", True, 58.0])
def test_bobina_que_nao_e_58_nem_80_e_recusada(cardapio, uow, bobina_mm):
    with pytest.raises(RegraDeNegocioError, match="58mm ou de 80mm"):
        cardapio.criar_impressora("Caixa", bobina_mm=bobina_mm)

    assert cardapio.listar_impressoras() == []


# ----------------------------------------------------------------------
# Edição
# ----------------------------------------------------------------------


def test_editar_sem_os_campos_novos_nao_mexe_neles(cardapio):
    """A chamada antiga, sem bobina nem letra, não apaga o que foi escolhido."""
    impressora = cardapio.criar_impressora("Caixa", colunas=48, bobina_mm=58, letra_grossa=True)

    cardapio.editar_impressora(impressora.id, "Caixa 01")

    assert (impressora.nome, impressora.colunas, impressora.bobina_mm, impressora.letra_grossa) == (
        "Caixa 01",
        48,
        58,
        True,
    )


def test_trocar_so_as_colunas_nao_deduz_a_bobina_de_novo(cardapio):
    """O ponto de gravar a bobina: com 32 colunas a regra de antes diria 58mm."""
    impressora = cardapio.criar_impressora("Caixa", colunas=48, bobina_mm=80)

    cardapio.editar_impressora(impressora.id, "Caixa", colunas=32)

    assert (impressora.colunas, impressora.bobina_mm) == (32, 80)


def test_a_edicao_grava_bobina_e_letra(cardapio):
    impressora = cardapio.criar_impressora("Caixa")

    cardapio.editar_impressora(impressora.id, "Caixa", colunas=64, bobina_mm=80, letra_grossa=True)
    cardapio.editar_impressora(impressora.id, "Caixa", bobina_mm=58, letra_grossa=False)

    assert (impressora.colunas, impressora.bobina_mm, impressora.letra_grossa) == (64, 58, False)


def test_bobina_invalida_na_edicao_nao_grava_nada(cardapio, uow):
    impressora = cardapio.criar_impressora("Caixa", colunas=48, bobina_mm=80)

    with pytest.raises(RegraDeNegocioError):
        cardapio.editar_impressora(impressora.id, "Outro nome", bobina_mm=76, letra_grossa=True)
    uow.rollback()

    recarregada = cardapio.buscar_impressora(impressora.id)
    assert (recarregada.nome, recarregada.bobina_mm, recarregada.letra_grossa) == ("Caixa", BOBINA_80MM, False)


def test_letra_grossa_e_gravada_como_booleano(cardapio):
    """A coluna é `Boolean`: um 1 que chegasse cru seria lido de volta como 1."""
    impressora = cardapio.criar_impressora("Caixa", letra_grossa=1)  # type: ignore[arg-type]

    assert impressora.letra_grossa is True
