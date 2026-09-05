import pytest
from sqlalchemy import text

from gestor_comercial.services.exceptions import AcessoNegadoError, RegraDeNegocioError
from gestor_comercial.services.loja_config_service import (
    SENHA_LOGIN_PADRAO,
    SENHA_MASTER_PADRAO,
    SENHA_OPERACIONAL_PADRAO,
    LojaConfigService,
)


@pytest.fixture
def loja_config(uow):
    return LojaConfigService(uow)


def test_bootstrap_cria_singleton_com_senhas_padrao(loja_config):
    loja_config.validar_senha_master(SENHA_MASTER_PADRAO)
    loja_config.validar_senha_operacional(SENHA_OPERACIONAL_PADRAO)
    loja_config.validar_senha_login(SENHA_LOGIN_PADRAO)


def test_bootstrap_e_idempotente(uow, loja_config):
    loja_config.obter_ou_criar()
    loja_config.obter_ou_criar()
    assert len(uow.session.execute(text("SELECT id FROM loja_config")).all()) == 1


def test_senha_master_errada_nao_confere(loja_config):
    with pytest.raises(AcessoNegadoError):
        loja_config.validar_senha_master("000000")


def test_senha_operacional_errada_nao_confere(loja_config):
    with pytest.raises(AcessoNegadoError):
        loja_config.validar_senha_operacional("000000")


def test_alterar_senha_operacional_exige_senha_master(loja_config):
    with pytest.raises(AcessoNegadoError):
        loja_config.alterar_senha_operacional("senha-errada", "nova-senha-op")

    loja_config.alterar_senha_operacional(SENHA_MASTER_PADRAO, "nova-senha-op")
    loja_config.validar_senha_operacional("nova-senha-op")
    with pytest.raises(AcessoNegadoError):
        loja_config.validar_senha_operacional(SENHA_OPERACIONAL_PADRAO)


def test_alterar_senha_master_exige_cpf_do_dono(loja_config):
    with pytest.raises(RegraDeNegocioError):
        loja_config.alterar_senha_master("12345678901", "nova-senha-master")

    loja_config.definir_ou_alterar_cpf_dono(None, "123.456.789-01")
    loja_config.alterar_senha_master("12345678901", "nova-senha-master")
    loja_config.validar_senha_master("nova-senha-master")


def test_alterar_cpf_dono_exige_cpf_atual_depois_do_primeiro_cadastro(loja_config):
    loja_config.definir_ou_alterar_cpf_dono(None, "11122233344")

    with pytest.raises(RegraDeNegocioError):
        loja_config.definir_ou_alterar_cpf_dono(None, "55566677788")
    with pytest.raises(AcessoNegadoError):
        loja_config.definir_ou_alterar_cpf_dono("00000000000", "55566677788")

    loja_config.definir_ou_alterar_cpf_dono("11122233344", "55566677788")
    loja_config.validar_cpf_dono("55566677788")


def test_cpf_invalido_e_recusado(loja_config):
    with pytest.raises(RegraDeNegocioError):
        loja_config.definir_ou_alterar_cpf_dono(None, "123")


def test_senha_operacional_confere_nao_levanta_erro(loja_config):
    assert loja_config.senha_operacional_confere(SENHA_OPERACIONAL_PADRAO) is True
    assert loja_config.senha_operacional_confere("errada") is False


def test_senha_login_errada_nao_confere(loja_config):
    with pytest.raises(AcessoNegadoError):
        loja_config.validar_senha_login("000000")


def test_senha_login_confere_nao_levanta_erro(loja_config):
    assert loja_config.senha_login_confere(SENHA_LOGIN_PADRAO) is True
    assert loja_config.senha_login_confere("errada") is False


def test_alterar_senha_login_exige_operacional_ou_master(loja_config):
    with pytest.raises(AcessoNegadoError):
        loja_config.alterar_senha_login("senha-errada", "nova-senha-login")

    loja_config.alterar_senha_login(SENHA_OPERACIONAL_PADRAO, "nova-senha-login")
    loja_config.validar_senha_login("nova-senha-login")
    with pytest.raises(AcessoNegadoError):
        loja_config.validar_senha_login(SENHA_LOGIN_PADRAO)


def test_alterar_senha_login_aceita_a_master_tambem(loja_config):
    loja_config.alterar_senha_login(SENHA_MASTER_PADRAO, "outra-nova-senha-login")
    loja_config.validar_senha_login("outra-nova-senha-login")


def test_mascarar_sempre_devolve_pontos():
    assert LojaConfigService.mascarar("qualquer-coisa") == "••••••••"
    assert LojaConfigService.mascarar() == "••••••••"
