"""A bobina gravada e a escala da fonte da impressora, no service. §9.22, §9.30.

A regra de cada parâmetro, no mesmo formato do `colunas` que já existia:

* **no cadastro**, sem informar nada, sai o de sempre — 48 colunas, 80mm e
  destaque em 2x —, e uma bobina não informada sai das colunas pela regra de
  antes de ela ser gravada (até 40 colunas é 58mm);
* **na edição**, `None` é "não mexe". Em especial, trocar só as colunas NÃO
  deduz a bobina de novo: "58mm + 48 col." é uma escolha que o gerente pode
  fazer, e é por isso que a bobina passou a ser gravada;
* **bobina fora de 58/80 e escala fora de 2/3/4 são recusadas** com mensagem,
  pela mesma porta que recusa colunas fora da faixa — e nada é gravado.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from gestor_comercial.domain.impressora import (
    BOBINA_58MM,
    BOBINA_80MM,
    ESCALA_FONTE_PADRAO,
    ESCALAS_FONTE,
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


def test_as_escalas_sao_as_tres_inteiras_do_pedido():
    """2x, 3x e 4x: o `GS !` só multiplica por inteiro, e o 2,5x saiu (§9.30)."""
    assert ESCALAS_FONTE == (2, 3, 4)
    assert ESCALA_FONTE_PADRAO == 2


# ----------------------------------------------------------------------
# Cadastro
# ----------------------------------------------------------------------


def test_o_cadastro_sem_nada_nasce_48_colunas_80mm_e_2x(cardapio):
    impressora = cardapio.criar_impressora("Cozinha")

    assert (impressora.colunas, impressora.bobina_mm, impressora.escala_fonte) == (48, 80, 2)


def test_sem_bobina_ela_sai_das_colunas(cardapio):
    """Quem chama pelo caminho antigo (`colunas=32`) ganha a bobina de 58mm."""
    impressora = cardapio.criar_impressora("Caixa", colunas=32)

    assert impressora.bobina_mm == BOBINA_58MM


@pytest.mark.parametrize(("colunas", "bobina_mm"), [(48, 58), (80, 58), (32, 80), (64, 80)])
def test_o_cadastro_grava_a_combinacao_escolhida(cardapio, colunas, bobina_mm):
    """Qualquer largura em qualquer bobina — a liberdade do pedido."""
    impressora = cardapio.criar_impressora("Caixa", colunas=colunas, bobina_mm=bobina_mm, escala_fonte=3)

    assert (impressora.colunas, impressora.bobina_mm, impressora.escala_fonte) == (colunas, bobina_mm, 3)


def test_a_bobina_chega_como_texto_e_e_convertida(cardapio):
    """A porta do `_inteiro_positivo`: o que vem de campo de texto vira número."""
    assert cardapio.criar_impressora("Caixa", bobina_mm=" 58 ").bobina_mm == 58


@pytest.mark.parametrize("bobina_mm", [0, 76, 110, -58, "80mm", "abc", True, 58.0])
def test_bobina_que_nao_e_58_nem_80_e_recusada(cardapio, uow, bobina_mm):
    with pytest.raises(RegraDeNegocioError, match="58mm ou de 80mm"):
        cardapio.criar_impressora("Caixa", bobina_mm=bobina_mm)

    assert cardapio.listar_impressoras() == []


@pytest.mark.parametrize("escala", ESCALAS_FONTE)
def test_cada_escala_do_seletor_e_gravada(cardapio, escala):
    assert cardapio.criar_impressora("Caixa", escala_fonte=escala).escala_fonte == escala


@pytest.mark.parametrize("escala", [0, 1, 5, 8, -2, "2.5", "2,5", 2.5, "3x", True])
def test_escala_fora_de_2_3_4_e_recusada_sem_gravar(cardapio, escala):
    """2,5x em especial: recusar é melhor que arredondar calado para 2 ou 3."""
    with pytest.raises(RegraDeNegocioError, match="2x, 3x ou 4x"):
        cardapio.criar_impressora("Caixa", escala_fonte=escala)

    assert cardapio.listar_impressoras() == []


def test_a_escala_chega_como_texto_e_e_convertida(cardapio):
    assert cardapio.criar_impressora("Caixa", escala_fonte=" 4 ").escala_fonte == 4


# ----------------------------------------------------------------------
# Edição
# ----------------------------------------------------------------------


def test_editar_sem_os_campos_novos_nao_mexe_neles(cardapio):
    """A chamada antiga, sem bobina nem escala, não apaga o que foi escolhido."""
    impressora = cardapio.criar_impressora("Caixa", colunas=48, bobina_mm=58, escala_fonte=4)

    cardapio.editar_impressora(impressora.id, "Caixa 01")

    assert (impressora.nome, impressora.colunas, impressora.bobina_mm, impressora.escala_fonte) == (
        "Caixa 01",
        48,
        58,
        4,
    )


def test_trocar_so_as_colunas_nao_deduz_a_bobina_de_novo(cardapio):
    """O ponto de gravar a bobina: com 32 colunas a regra de antes diria 58mm."""
    impressora = cardapio.criar_impressora("Caixa", colunas=48, bobina_mm=80)

    cardapio.editar_impressora(impressora.id, "Caixa", colunas=32)

    assert (impressora.colunas, impressora.bobina_mm) == (32, 80)


def test_a_edicao_grava_bobina_e_escala(cardapio):
    impressora = cardapio.criar_impressora("Caixa")

    cardapio.editar_impressora(impressora.id, "Caixa", colunas=64, bobina_mm=80, escala_fonte=4)
    cardapio.editar_impressora(impressora.id, "Caixa", bobina_mm=58, escala_fonte=3)

    assert (impressora.colunas, impressora.bobina_mm, impressora.escala_fonte) == (64, 58, 3)


def test_a_escala_persiste_no_banco_e_nao_so_na_instancia(cardapio, uow):
    """Relida do SQLite depois do commit, e não do objeto em memória: o
    `expire_all` obriga a próxima leitura a ir ao banco."""
    impressora = cardapio.criar_impressora("Caixa", escala_fonte=3)
    cardapio.editar_impressora(impressora.id, "Caixa", escala_fonte=4)

    uow.session.expire_all()
    (valor,) = uow.session.execute(
        text("SELECT escala_fonte FROM impressoras WHERE id = :id"),
        {"id": impressora.id},
    ).one()

    assert valor == 4
    assert cardapio.buscar_impressora(impressora.id).escala_fonte == 4


def test_invalido_na_edicao_nao_grava_nada(cardapio, uow):
    """Uma validação só falhando deixa o cadastro INTEIRO como estava: nome e
    escala antigos, e não metade do formulário."""
    impressora = cardapio.criar_impressora("Caixa", colunas=48, bobina_mm=80, escala_fonte=3)

    with pytest.raises(RegraDeNegocioError):
        cardapio.editar_impressora(impressora.id, "Outro nome", bobina_mm=76, escala_fonte=4)
    uow.rollback()
    with pytest.raises(RegraDeNegocioError):
        cardapio.editar_impressora(impressora.id, "Outro nome", escala_fonte=5)
    uow.rollback()

    recarregada = cardapio.buscar_impressora(impressora.id)
    assert (recarregada.nome, recarregada.bobina_mm, recarregada.escala_fonte) == ("Caixa", BOBINA_80MM, 3)
