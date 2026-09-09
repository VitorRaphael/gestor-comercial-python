"""`LojaConfigService.revelar` — o CPF do Dono como chave para ver um segredo.

A cascata de 3 níveis (§3.13) nasceu com a regra de que nenhum segredo é
recuperável. O pedido do Vitor abriu uma exceção estreita e explícita: um olho
ao lado de cada linha de "Senhas e Acesso" que mostra o valor real, mediante o
CPF do Dono — porque quem esquece a Senha Master não tem para onde ir, já que a
única credencial acima dela é o próprio CPF.

O que estes testes trancam:

* **a exceção continua estreita** — `revelar` devolve texto para a tela e não
  abre nenhuma outra porta; o hash segue sendo a única coisa contra a qual um
  PIN digitado é conferido, e trocar uma senha não pode deixar o olho mostrando
  a anterior;
* **quem não provou ser o dono não recebe nada**, nem o valor nem a informação
  de que aquele campo tem ou não cópia;
* **o que não existe não é inventado**: sem cópia recuperável, a resposta é uma
  instrução ("altere-a uma vez"), nunca um chute.
"""

from __future__ import annotations

import pytest

from gestor_comercial.services.exceptions import AcessoNegadoError, RegraDeNegocioError
from gestor_comercial.services.loja_config_service import (
    CAMPO_CPF_DONO,
    CAMPO_SENHA_LOGIN,
    CAMPO_SENHA_MASTER,
    CAMPO_SENHA_OPERACIONAL,
    SENHA_LOGIN_PADRAO,
    SENHA_MASTER_PADRAO,
    SENHA_OPERACIONAL_PADRAO,
    LojaConfigService,
)

CPF_DO_DONO = "12345678901"
CPF_DE_OUTRA_PESSOA = "98765432100"


@pytest.fixture
def loja_config(uow):
    return LojaConfigService(uow)


@pytest.fixture
def com_cpf(loja_config):
    loja_config.definir_ou_alterar_cpf_dono(None, CPF_DO_DONO)
    return loja_config


# ----------------------------------------------------------------------
# O caminho feliz
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "campo, esperado",
    [
        (CAMPO_SENHA_MASTER, SENHA_MASTER_PADRAO),
        (CAMPO_SENHA_OPERACIONAL, SENHA_OPERACIONAL_PADRAO),
        (CAMPO_SENHA_LOGIN, SENHA_LOGIN_PADRAO),
    ],
)
def test_as_senhas_de_fabrica_ja_nascem_visiveis(com_cpf, campo, esperado):
    """Banco novo: o olho funciona desde o primeiro boot, sem exigir que o
    Vitor troque a senha uma vez só para poder vê-la."""
    assert com_cpf.revelar(campo, CPF_DO_DONO) == esperado


def test_o_cpf_do_dono_revela_a_si_mesmo(com_cpf):
    assert com_cpf.revelar(CAMPO_CPF_DONO, CPF_DO_DONO) == CPF_DO_DONO


def test_o_cpf_e_conferido_pelos_digitos_e_nao_pela_pontuacao(com_cpf):
    """O cadastro guarda o CPF **limpo** (`_validar_cpf_formato` tira a
    pontuação antes do hash), então o que confere é a string de onze dígitos —
    e só ela. Um "123.456.789-01" digitado não bate.

    Não é um defeito: é o contrato que `CpfDonoDialog` cumpre ao acumular
    dígitos e entregar `"12345678901"`, com a pontuação existindo só no visor.
    Este teste é o que avisa se alguém trocar o visor pela fonte do dado.
    """
    assert com_cpf.revelar(CAMPO_SENHA_MASTER, CPF_DO_DONO) == SENHA_MASTER_PADRAO
    with pytest.raises(AcessoNegadoError):
        com_cpf.revelar(CAMPO_SENHA_MASTER, "123.456.789-01")


def test_a_senha_trocada_passa_a_ser_a_que_o_olho_mostra(com_cpf):
    """O que o olho mostra é o valor ATUAL, nunca o anterior.

    Hash novo com cópia velha seria pior que cópia nenhuma: o dono conferiria
    uma senha que não abre mais nada.
    """
    com_cpf.alterar_senha_master(CPF_DO_DONO, "778899")

    assert com_cpf.revelar(CAMPO_SENHA_MASTER, CPF_DO_DONO) == "778899"


def test_trocar_a_senha_de_login_atualiza_a_copia(com_cpf):
    com_cpf.alterar_senha_login(SENHA_OPERACIONAL_PADRAO, "4321")

    assert com_cpf.revelar(CAMPO_SENHA_LOGIN, CPF_DO_DONO) == "4321"


def test_trocar_a_senha_operacional_atualiza_a_copia(com_cpf):
    com_cpf.alterar_senha_operacional(SENHA_MASTER_PADRAO, "55667")

    assert com_cpf.revelar(CAMPO_SENHA_OPERACIONAL, CPF_DO_DONO) == "55667"


def test_trocar_o_cpf_atualiza_a_copia_do_cpf(com_cpf):
    com_cpf.definir_ou_alterar_cpf_dono(CPF_DO_DONO, CPF_DE_OUTRA_PESSOA)

    assert com_cpf.revelar(CAMPO_CPF_DONO, CPF_DE_OUTRA_PESSOA) == CPF_DE_OUTRA_PESSOA


# ----------------------------------------------------------------------
# As recusas
# ----------------------------------------------------------------------


def test_cpf_errado_nao_revela(com_cpf):
    with pytest.raises(AcessoNegadoError):
        com_cpf.revelar(CAMPO_SENHA_MASTER, CPF_DE_OUTRA_PESSOA)


def test_sem_cpf_cadastrado_a_resposta_manda_cadastrar(loja_config):
    """Não é acesso negado: não há nada contra o que comparar."""
    with pytest.raises(RegraDeNegocioError, match="CPF do Dono ainda não foi cadastrado"):
        loja_config.revelar(CAMPO_SENHA_MASTER, CPF_DO_DONO)


def test_campo_desconhecido_e_recusado(com_cpf):
    with pytest.raises(RegraDeNegocioError, match="Campo desconhecido"):
        com_cpf.revelar("senha_do_wifi", CPF_DO_DONO)


def test_sem_copia_recuperavel_a_resposta_e_uma_instrucao(uow, com_cpf):
    """O banco que já existia com a senha trocada antes das colunas novas.

    A migração `b6e2d80a3f14` deixa a coluna `NULL` de propósito nesse caso (ela
    só recupera o que ainda está na senha de fábrica), e a resposta certa é
    dizer o que fazer — não chutar o padrão de fábrica.
    """
    config = com_cpf.obter_ou_criar()
    config.senha_master_cifrada = None
    uow.commit()

    with pytest.raises(RegraDeNegocioError, match="Altere-a uma vez"):
        com_cpf.revelar(CAMPO_SENHA_MASTER, CPF_DO_DONO)


def test_a_recusa_por_cpf_vem_antes_da_recusa_por_falta_de_copia(uow, com_cpf):
    """Quem não provou ser o dono não fica sabendo nem que aquele campo está
    sem cópia — isso é informação sobre o cadastro da loja."""
    config = com_cpf.obter_ou_criar()
    config.senha_master_cifrada = None
    uow.commit()

    with pytest.raises(AcessoNegadoError):
        com_cpf.revelar(CAMPO_SENHA_MASTER, CPF_DE_OUTRA_PESSOA)


def test_copia_adulterada_no_banco_nao_vira_senha_falsa(uow, com_cpf):
    """Adulteração devolve a instrução, e não uma senha diferente com cara de
    verdadeira — é o selo de `segredo_reversivel` chegando até a tela."""
    config = com_cpf.obter_ou_criar()
    config.senha_master_cifrada = "AAAA" + (config.senha_master_cifrada or "")[4:]
    uow.commit()

    with pytest.raises(RegraDeNegocioError, match="Altere-a uma vez"):
        com_cpf.revelar(CAMPO_SENHA_MASTER, CPF_DO_DONO)


# ----------------------------------------------------------------------
# O que NÃO muda
# ----------------------------------------------------------------------


def test_revelar_nao_e_autenticacao(com_cpf):
    """O CPF revela o valor e mais nada: ele não passa a valer como senha.

    Se um dia `revelar` virar porta de entrada, este teste é o que avisa.
    """
    assert com_cpf.senha_master_confere(CPF_DO_DONO) is False
    assert com_cpf.senha_operacional_confere(CPF_DO_DONO) is False
    assert com_cpf.senha_login_confere(CPF_DO_DONO) is False


def test_a_senha_continua_sendo_conferida_pelo_hash(uow, com_cpf):
    """Apagar a cópia recuperável não pode afetar o login de ninguém."""
    config = com_cpf.obter_ou_criar()
    config.senha_login_cifrada = None
    config.senha_master_cifrada = None
    config.senha_operacional_cifrada = None
    uow.commit()

    com_cpf.validar_senha_login(SENHA_LOGIN_PADRAO)
    com_cpf.validar_senha_master(SENHA_MASTER_PADRAO)
    com_cpf.validar_senha_operacional(SENHA_OPERACIONAL_PADRAO)


def test_o_banco_nao_guarda_a_senha_em_texto_puro(com_cpf):
    config = com_cpf.obter_ou_criar()

    for coluna in (
        config.senha_master_cifrada,
        config.senha_operacional_cifrada,
        config.senha_login_cifrada,
        config.cpf_dono_cifrado,
    ):
        assert coluna, "premissa: as quatro cópias existem neste cenário"
        assert SENHA_MASTER_PADRAO not in coluna
        assert SENHA_OPERACIONAL_PADRAO not in coluna
        assert CPF_DO_DONO not in coluna


def test_pode_revelar_diz_se_ha_copia_sem_pedir_cpf(uow, loja_config):
    assert loja_config.pode_revelar(CAMPO_SENHA_MASTER) is True
    assert loja_config.pode_revelar(CAMPO_CPF_DONO) is False, "CPF ainda não cadastrado"
    assert loja_config.pode_revelar("senha_do_wifi") is False


def test_a_chave_de_exibicao_e_criada_uma_vez_so(uow, loja_config):
    """Uma chave por instalação: recriá-la a cada leitura tornaria ilegível
    tudo o que já estava guardado."""
    from gestor_comercial.repository.preferencia_repository import CHAVE_DE_EXIBICAO

    loja_config.obter_ou_criar()
    primeira = uow.preferencias.obter(CHAVE_DE_EXIBICAO)

    loja_config.definir_ou_alterar_cpf_dono(None, CPF_DO_DONO)
    loja_config.alterar_senha_master(CPF_DO_DONO, "778899")

    assert uow.preferencias.obter(CHAVE_DE_EXIBICAO) == primeira
    assert loja_config.revelar(CAMPO_SENHA_LOGIN, CPF_DO_DONO) == SENHA_LOGIN_PADRAO
