"""A seção "Dados da loja" da tela de Configurações (§9.30).

O service é coberto por `tests/unit/test_dados_da_loja.py`. Aqui se prova o
caminho da tela: o que se digita é o que fica gravado, os campos voltam como
o banco os guardou, e o erro do service aparece sem apagar o que foi digitado.
"""

from __future__ import annotations

from gestor_comercial.services.loja_config_service import LIMITE_NOME_LOJA
from gestor_comercial.ui.views.configuracoes_view import ConfiguracoesView


def test_a_tela_abre_com_o_que_esta_gravado(qapp, auth):
    auth.loja_config.salvar_dados_da_loja("Solvix Lanches", "(11) 98765-4321", "Campinas", "SP")

    tela = ConfiguracoesView(auth)

    assert tela._campo_nome_loja.text() == "Solvix Lanches"
    assert tela._campo_telefone.text() == "(11) 98765-4321"
    assert tela._campo_cidade.text() == "Campinas"
    assert tela._campo_uf.text() == "SP"


def test_salvar_grava_e_devolve_os_campos_normalizados(qapp, auth):
    tela = ConfiguracoesView(auth)
    tela._campo_nome_loja.setText("  Solvix   Lanches ")
    tela._campo_telefone.setText("(11) 98765-4321")
    tela._campo_cidade.setText("Campinas")
    tela._campo_uf.setText("sp")

    tela._botao_salvar_loja.click()

    assert auth.loja_config.dados_da_loja().nome == "Solvix Lanches"
    assert tela._campo_nome_loja.text() == "Solvix Lanches"
    assert tela._campo_uf.text() == "SP"
    assert tela._aviso_loja.text() == "Dados salvos."
    assert tela._label_erro.text() == ""


def test_o_erro_do_service_aparece_e_nao_apaga_o_digitado(qapp, auth):
    tela = ConfiguracoesView(auth)
    tela._campo_nome_loja.setText("Solvix")
    tela._campo_uf.setText("S1")

    tela._botao_salvar_loja.click()

    assert "duas letras" in tela._label_erro.text()
    assert tela._aviso_loja.text() == ""
    assert (tela._campo_nome_loja.text(), tela._campo_uf.text()) == ("Solvix", "S1")
    assert auth.loja_config.dados_da_loja().nome is None


def test_os_campos_tem_o_teto_das_colunas(qapp, auth):
    tela = ConfiguracoesView(auth)

    assert tela._campo_nome_loja.maxLength() == LIMITE_NOME_LOJA
    assert tela._campo_uf.maxLength() == 2
