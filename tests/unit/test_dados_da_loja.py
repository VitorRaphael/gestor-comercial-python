"""Os dados da loja que o recibo imprime no cabeçalho (§9.30).

`LojaConfigService.salvar_dados_da_loja`: vazio vira `NULL`, espaço sobrando é
aparado, UF sai maiúscula, e — o que importa na queda de energia e no erro de
digitação — tudo é validado antes de tocar na linha, num commit só.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from gestor_comercial.services.exceptions import RegraDeNegocioError
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.services.loja_config_service import LojaConfigService
from gestor_comercial.services.recibo_formatter import DadosDaLoja
from tests.unit.test_impressao_service import (
    nova_categoria_com_produto,
    nova_comanda,
    nova_impressora,
    novo_item,
)


@pytest.fixture
def loja_config(uow):
    return LojaConfigService(uow)


def _gravado(uow) -> tuple:
    uow.session.expire_all()
    return tuple(
        uow.session.execute(text("SELECT nome_loja, telefone, cidade, uf FROM loja_config")).one()
    )


def test_sem_nada_cadastrado_os_dados_vem_vazios(loja_config):
    assert loja_config.dados_da_loja() == DadosDaLoja()


def test_salvar_grava_no_banco_ja_normalizado(uow, loja_config):
    dados = loja_config.salvar_dados_da_loja("  Solvix   Lanches ", "(11) 98765-4321", " Campinas ", "sp")

    assert dados == DadosDaLoja("Solvix Lanches", "(11) 98765-4321", "Campinas", "SP")
    assert _gravado(uow) == ("Solvix Lanches", "(11) 98765-4321", "Campinas", "SP")
    assert loja_config.dados_da_loja() == dados


def test_campo_vazio_vira_null(uow, loja_config):
    loja_config.salvar_dados_da_loja("Solvix", "11 9999-0000", "Campinas", "SP")
    loja_config.salvar_dados_da_loja("Solvix", "   ", "", None)

    assert _gravado(uow) == ("Solvix", None, None, None)


@pytest.mark.parametrize(
    ("campos", "mensagem"),
    [
        (("x" * 61, None, None, None), "nome da loja"),
        ((None, "1" * 21, None, None), "telefone aceita"),
        ((None, "ramal abc", None, None), "só aceita números"),
        ((None, None, "c" * 61, None), "cidade"),
        ((None, None, None, "S"), "duas letras"),
        ((None, None, None, "S1"), "duas letras"),
        ((None, None, None, "SPA"), "duas letras"),
    ],
)
def test_invalido_e_recusado_sem_gravar_nada(uow, loja_config, campos, mensagem):
    """Um campo recusado não deixa os OUTROS gravados: o recibo não pode sair
    com o nome novo e o telefone antigo."""
    loja_config.salvar_dados_da_loja("Antigo", "11 1111-1111", "Campinas", "SP")
    nome, telefone, cidade, uf = campos

    with pytest.raises(RegraDeNegocioError, match=mensagem):
        loja_config.salvar_dados_da_loja(nome or "Novo", telefone, cidade, uf)
    uow.rollback()

    assert _gravado(uow) == ("Antigo", "11 1111-1111", "Campinas", "SP")


def test_o_recibo_imprime_o_que_foi_salvo(uow, auth, driver, gerente, caixa_aberto):
    """Do cadastro ao papel: o cabeçalho lê a mesma linha que a tela gravou."""
    LojaConfigService(uow).salvar_dados_da_loja("Solvix Lanches", "(11) 98765-4321", "Campinas", "SP")
    nova_impressora(uow, "Balcão", padrao=True, colunas=48)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", None)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    ImpressaoService(uow, auth, abrir_driver=driver).imprimir_recibo(comanda.id)
    blocos = driver.blocos_de("Balcão")
    texto = driver.texto_de("Balcão")

    assert blocos[0].texto == "SOLVIX LANCHES" and blocos[0].ampliado
    assert "Tel: (11) 98765-4321" in texto
    assert "Campinas/SP" in texto
    assert "RECIBO" in texto
