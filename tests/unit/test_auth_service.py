import base64
from decimal import Decimal

import pytest

from gestor_comercial.domain.enums import PerfilFuncionario
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.repository import seed
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from tests.conftest import PIN_ATENDENTE, PIN_GERENTE

PIN_OUTRO_GERENTE = "333333"
PIN_LIVRE = "444444"


# ----------------------------------------------------------------------
# services/dinheiro.py
# ----------------------------------------------------------------------


def test_dinheiro_arredonda_meio_pra_cima():
    assert dinheiro(Decimal("2.345")) == Decimal("2.35")
    assert dinheiro(Decimal("10.005")) == Decimal("10.01")
    assert dinheiro(Decimal("2.344")) == Decimal("2.34")


def test_dinheiro_sempre_com_duas_casas():
    assert dinheiro(Decimal("7")).as_tuple().exponent == -2
    assert dinheiro(7) == Decimal("7.00")
    assert dinheiro("3.1") == Decimal("3.10")


def test_dinheiro_recusa_float():
    with pytest.raises(TypeError):
        dinheiro(1.5)


def test_dinheiro_recusa_texto_invalido():
    with pytest.raises(ValueError):
        dinheiro("dez reais")


def test_zero_e_decimal_com_duas_casas():
    assert ZERO == Decimal("0.00")
    assert ZERO.as_tuple().exponent == -2


# ----------------------------------------------------------------------
# Hash do PIN
# ----------------------------------------------------------------------


def test_gerar_salt_produz_16_bytes_diferentes_a_cada_chamada():
    salt = AuthService.gerar_salt()
    assert len(base64.b64decode(salt)) == 16
    assert salt != AuthService.gerar_salt()


def test_hash_pin_e_deterministico_para_o_mesmo_salt():
    salt = AuthService.gerar_salt()
    assert AuthService.hash_pin("1234", salt) == AuthService.hash_pin("1234", salt)
    assert AuthService.hash_pin("1234", salt) != AuthService.hash_pin("1235", salt)


def test_hash_pin_muda_com_o_salt():
    assert AuthService.hash_pin("1234", AuthService.gerar_salt()) != AuthService.hash_pin(
        "1234", AuthService.gerar_salt()
    )


def test_confere_pin_aceita_o_certo_e_recusa_o_errado():
    salt = AuthService.gerar_salt()
    esperado = AuthService.hash_pin("9876", salt)
    assert AuthService.confere_pin("9876", salt, esperado) is True
    assert AuthService.confere_pin("9875", salt, esperado) is False


def test_confere_pin_nao_quebra_com_salt_corrompido():
    assert AuthService.confere_pin("1234", "salt-invalido!!", "qualquer") is False


def test_hash_bate_bit_a_bit_com_o_seed():
    """Se este teste cair, o 'Gerente' criado no primeiro boot não consegue logar."""
    salt_do_seed = seed.gerar_salt()
    assert AuthService.hash_pin(seed.ADMIN_PIN_PADRAO, salt_do_seed) == seed.hash_pin(
        seed.ADMIN_PIN_PADRAO, salt_do_seed
    )

    salt_do_service = AuthService.gerar_salt()
    assert AuthService.confere_pin(
        seed.ADMIN_PIN_PADRAO,
        salt_do_service,
        seed.hash_pin(seed.ADMIN_PIN_PADRAO, salt_do_service),
    )


def test_funcionario_do_seed_consegue_logar(uow, auth):
    salt = seed.gerar_salt()
    uow.funcionarios.salvar(
        Funcionario(
            nome=seed.ADMIN_NOME,
            pin_hash=seed.hash_pin(seed.ADMIN_PIN_PADRAO, salt),
            salt=salt,
            perfil=PerfilFuncionario.GERENTE,
        )
    )
    logado = auth.login(seed.ADMIN_PIN_PADRAO)
    assert logado.nome == seed.ADMIN_NOME


# ----------------------------------------------------------------------
# Sessão
# ----------------------------------------------------------------------


def test_login_guarda_o_funcionario_na_sessao(auth, gerente):
    assert auth.usuario_logado is gerente
    assert auth.usuario_atual() is gerente


def test_login_com_pin_invalido_nao_abre_sessao(auth, gerente):
    auth.logout()
    with pytest.raises(NaoAutorizadoError):
        auth.login("999999")
    assert auth.usuario_logado is None


def test_login_com_funcionario_desativado_e_negado(auth, gerente, atendente):
    auth.desativar_funcionario(atendente.id)
    with pytest.raises(NaoAutorizadoError):
        auth.login(PIN_ATENDENTE)


def test_logout_limpa_a_sessao(auth, gerente):
    auth.logout()
    assert auth.usuario_logado is None
    with pytest.raises(NaoAutorizadoError):
        auth.usuario_atual()


def test_usuario_atual_sem_ninguem_logado(auth):
    with pytest.raises(NaoAutorizadoError):
        auth.usuario_atual()


def test_exigir_gerente_passa_com_gerente_logado(auth, gerente):
    assert auth.exigir_gerente() is gerente


def test_exigir_gerente_bloqueia_atendente_logado(auth, gerente, atendente):
    auth.logout()
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        auth.exigir_gerente()


def test_exigir_gerente_sem_ninguem_logado(auth):
    with pytest.raises(NaoAutorizadoError):
        auth.exigir_gerente()


# ----------------------------------------------------------------------
# Funcionários
# ----------------------------------------------------------------------


def test_criar_funcionario_grava_ativo_com_hash_conferivel(auth, uow):
    funcionario = auth.criar_funcionario("Maria", "5678", PerfilFuncionario.ATENDENTE)

    assert funcionario.id is not None
    assert funcionario.nome == "Maria"
    assert funcionario.ativo is True
    assert funcionario.perfil is PerfilFuncionario.ATENDENTE
    assert funcionario.saldo_devedor == Decimal("0.00")
    assert AuthService.confere_pin("5678", funcionario.salt, funcionario.pin_hash)
    # o PIN em claro não pode sobrar em lugar nenhum
    assert "5678" not in funcionario.pin_hash


def test_criar_funcionario_nao_deixa_sessao_logada(auth):
    auth.criar_funcionario("Maria", "5678", PerfilFuncionario.ATENDENTE)
    assert auth.usuario_logado is None


def test_criar_funcionario_com_nome_vazio(auth):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_funcionario("   ", "5678", PerfilFuncionario.ATENDENTE)


def test_criar_funcionario_com_pin_nao_numerico(auth):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_funcionario("Maria", "12a4", PerfilFuncionario.ATENDENTE)


def test_criar_funcionario_com_pin_curto_demais(auth):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_funcionario("Maria", "123", PerfilFuncionario.ATENDENTE)


def test_criar_funcionario_com_pin_longo_demais(auth):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_funcionario("Maria", "123456789", PerfilFuncionario.ATENDENTE)


def test_criar_funcionario_com_perfil_invalido(auth):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_funcionario("Maria", "5678", "GERENTE")


def test_criar_funcionario_com_pin_de_outro_ativo(auth, gerente):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_funcionario("Maria", PIN_GERENTE, PerfilFuncionario.ATENDENTE)


def test_pin_de_funcionario_desativado_pode_ser_reaproveitado(auth, gerente):
    antigo = auth.criar_funcionario("Antigo", PIN_LIVRE, PerfilFuncionario.ATENDENTE)
    auth.desativar_funcionario(antigo.id)

    novo = auth.criar_funcionario("Novo", PIN_LIVRE, PerfilFuncionario.ATENDENTE)
    assert novo.id != antigo.id
    assert auth.autenticar_por_pin(PIN_LIVRE) is novo


def test_listar_ativos_ignora_desativados(auth, gerente, atendente):
    assert {f.nome for f in auth.listar_ativos()} == {"Gerente", "Atendente"}

    auth.desativar_funcionario(atendente.id)
    assert [f.nome for f in auth.listar_ativos()] == ["Gerente"]


def test_buscar_funcionario_por_id(auth, gerente):
    assert auth.buscar_funcionario(gerente.id) is gerente


def test_buscar_funcionario_inexistente(auth):
    with pytest.raises(RecursoNaoEncontradoError):
        auth.buscar_funcionario(9999)


def test_desativar_funcionario_marca_como_inativo(auth, gerente, atendente):
    desativado = auth.desativar_funcionario(atendente.id)
    assert desativado.ativo is False


def test_desativar_funcionario_ja_desativado(auth, gerente, atendente):
    auth.desativar_funcionario(atendente.id)
    with pytest.raises(RegraDeNegocioError):
        auth.desativar_funcionario(atendente.id)


def test_desativar_ultimo_gerente_ativo_e_bloqueado(auth, gerente, atendente):
    with pytest.raises(RegraDeNegocioError):
        auth.desativar_funcionario(gerente.id)
    assert gerente.ativo is True


def test_desativar_gerente_e_permitido_se_sobrar_outro(auth, gerente):
    auth.criar_funcionario("Segundo Gerente", PIN_OUTRO_GERENTE, PerfilFuncionario.GERENTE)

    desativado = auth.desativar_funcionario(gerente.id)
    assert desativado.ativo is False
    assert [f.nome for f in auth.listar_ativos()] == ["Segundo Gerente"]


def test_desativar_funcionario_inexistente(auth, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        auth.desativar_funcionario(9999)


def test_criar_funcionario_sem_gerente_logado_e_bloqueado(auth, gerente):
    auth.logout()
    with pytest.raises(NaoAutorizadoError):
        auth.criar_funcionario("Fantoche", "999999", PerfilFuncionario.GERENTE)


def test_criar_funcionario_com_atendente_logado_e_bloqueado(auth, gerente, atendente):
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        auth.criar_funcionario("Fantoche", "999999", PerfilFuncionario.GERENTE)


def test_criar_primeiro_funcionario_do_sistema_nao_exige_gerente(auth):
    # Bootstrap: o seed (ou o primeiro cadastro manual) não tem quem autorizar.
    funcionario = auth.criar_funcionario("Gerente", "111111", PerfilFuncionario.GERENTE)
    assert funcionario.perfil is PerfilFuncionario.GERENTE


def test_desativar_funcionario_com_atendente_logado_e_bloqueado(auth, gerente, atendente):
    auth.login(PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        auth.desativar_funcionario(gerente.id)
    assert gerente.ativo is True


def test_autenticar_por_pin_nao_mexe_na_sessao(auth, gerente, atendente):
    encontrado = auth.autenticar_por_pin(PIN_ATENDENTE)
    assert encontrado is atendente
    assert auth.usuario_logado is gerente


def test_autenticar_por_pin_invalido(auth, gerente):
    with pytest.raises(NaoAutorizadoError):
        auth.autenticar_por_pin("000000")


def test_autenticar_por_pin_vazio(auth, gerente):
    with pytest.raises(NaoAutorizadoError):
        auth.autenticar_por_pin("")


def test_validar_pin_gerente_devolve_quem_autorizou_sem_trocar_a_sessao(auth, gerente, atendente):
    auth.logout()
    auth.login(PIN_ATENDENTE)

    autorizador = auth.validar_pin_gerente(PIN_GERENTE)
    assert autorizador is gerente
    assert auth.usuario_logado is atendente


def test_validar_pin_gerente_com_pin_de_atendente(auth, gerente, atendente):
    with pytest.raises(AcessoNegadoError):
        auth.validar_pin_gerente(PIN_ATENDENTE)


def test_validar_pin_gerente_com_pin_inexistente(auth, gerente):
    with pytest.raises(NaoAutorizadoError):
        auth.validar_pin_gerente("000000")


def test_validar_pin_gerente_de_gerente_desativado(auth, gerente):
    segundo = auth.criar_funcionario(
        "Segundo Gerente", PIN_OUTRO_GERENTE, PerfilFuncionario.GERENTE
    )
    auth.desativar_funcionario(segundo.id)

    with pytest.raises(NaoAutorizadoError):
        auth.validar_pin_gerente(PIN_OUTRO_GERENTE)


def test_regra_bloqueada_nao_deixa_lixo_gravado(auth, gerente, uow):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_funcionario("Clone", PIN_GERENTE, PerfilFuncionario.ATENDENTE)

    uow.rollback()
    assert [f.nome for f in auth.listar_ativos()] == ["Gerente"]
