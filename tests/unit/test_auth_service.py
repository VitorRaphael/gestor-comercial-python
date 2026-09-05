import base64
from decimal import Decimal

import pytest

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from tests.conftest import PIN_ATENDENTE, PIN_GERENTE, PIN_LOGIN, PIN_MASTER, PIN_OPERACIONAL

PIN_OUTRO_GERENTE = PIN_MASTER
PIN_INVALIDO = "000000"


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


# ----------------------------------------------------------------------
# Cascata de 3 níveis (§3.13) — validar_pin_nivel
# ----------------------------------------------------------------------


def test_validar_pin_nivel_1_aceita_qualquer_um_dos_tres(auth):
    assert auth.validar_pin_nivel(PIN_LOGIN, nivel_minimo=1) is True
    assert auth.validar_pin_nivel(PIN_OPERACIONAL, nivel_minimo=1) is True
    assert auth.validar_pin_nivel(PIN_MASTER, nivel_minimo=1) is True


def test_validar_pin_nivel_2_recusa_a_de_login_mas_aceita_operacional_e_master(auth):
    # PIN_LOGIN (padrão de fábrica) é igual a PIN_OPERACIONAL por decisão de
    # produto (mesmo valor "26407200" nos dois, ver `LojaConfigService`) —
    # pra testar a recusa do Nível 1 no Nível 2 é preciso primeiro trocar a
    # Senha de Login pra um valor distinto dela.
    auth.loja_config.alterar_senha_login(PIN_OPERACIONAL, "999999")

    assert auth.validar_pin_nivel("999999", nivel_minimo=2) is False
    assert auth.validar_pin_nivel(PIN_OPERACIONAL, nivel_minimo=2) is True
    assert auth.validar_pin_nivel(PIN_MASTER, nivel_minimo=2) is True


def test_validar_pin_nivel_3_so_aceita_a_master(auth):
    auth.loja_config.alterar_senha_login(PIN_OPERACIONAL, "999999")

    assert auth.validar_pin_nivel("999999", nivel_minimo=3) is False
    assert auth.validar_pin_nivel(PIN_OPERACIONAL, nivel_minimo=3) is False
    assert auth.validar_pin_nivel(PIN_MASTER, nivel_minimo=3) is True


def test_validar_pin_nivel_recusa_pin_invalido(auth):
    assert auth.validar_pin_nivel(PIN_INVALIDO, nivel_minimo=1) is False


def test_validar_pin_nivel_recusa_vazio_ou_nao_string(auth):
    assert auth.validar_pin_nivel("", nivel_minimo=1) is False
    assert auth.validar_pin_nivel(None, nivel_minimo=1) is False  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Sessão / login_como
# ----------------------------------------------------------------------


def test_login_guarda_o_funcionario_na_sessao(auth, gerente):
    assert auth.usuario_logado is gerente
    assert auth.usuario_atual() is gerente


def test_login_como_aceita_qualquer_nivel_da_cascata(auth, gerente):
    for pin in (PIN_LOGIN, PIN_OPERACIONAL, PIN_MASTER):
        auth.logout()
        logado = auth.login_como(gerente.id, pin)
        assert logado is gerente


def test_login_com_pin_invalido_nao_abre_sessao(auth, gerente):
    auth.logout()
    with pytest.raises(NaoAutorizadoError):
        auth.login_como(gerente.id, PIN_INVALIDO)
    assert auth.usuario_logado is None


def test_login_com_funcionario_desativado_e_negado(auth, gerente, atendente):
    auth.desativar_usuario(atendente.id)
    with pytest.raises(NaoAutorizadoError):
        auth.login_como(atendente.id, PIN_ATENDENTE)


def test_login_como_operador_selecionado_nao_depende_de_pin_pessoal(auth, gerente, atendente):
    """Dois usuários ativos autenticam com o MESMO PIN da loja — quem é
    escolhido vem do `usuario_id`, não do PIN (§3.13, fim do PIN pessoal)."""
    auth.logout()
    logado_gerente = auth.login_como(gerente.id, PIN_MASTER)
    assert logado_gerente is gerente

    auth.logout()
    logado_atendente = auth.login_como(atendente.id, PIN_MASTER)
    assert logado_atendente is atendente


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
    auth.login_como(atendente.id, PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        auth.exigir_gerente()


def test_exigir_gerente_sem_ninguem_logado(auth):
    with pytest.raises(NaoAutorizadoError):
        auth.exigir_gerente()


# ----------------------------------------------------------------------
# Usuários de login — sem PIN pessoal (§3.13)
# ----------------------------------------------------------------------


def test_criar_usuario_grava_ativo_sem_pin_proprio(auth, uow):
    usuario = auth.criar_usuario("Maria", PerfilUsuario.OPERADOR_CAIXA)

    assert usuario.id is not None
    assert usuario.nome == "Maria"
    assert usuario.ativo is True
    assert usuario.perfil is PerfilUsuario.OPERADOR_CAIXA
    assert not hasattr(usuario, "pin_hash")
    assert not hasattr(usuario, "salt")


def test_criar_funcionario_nao_deixa_sessao_logada(auth):
    auth.criar_usuario("Maria", PerfilUsuario.OPERADOR_CAIXA)
    assert auth.usuario_logado is None


def test_criar_funcionario_com_nome_vazio(auth):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_usuario("   ", PerfilUsuario.OPERADOR_CAIXA)


def test_criar_funcionario_com_perfil_invalido(auth):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_usuario("Maria", "GERENTE")


def test_dois_usuarios_ativos_podem_compartilhar_a_senha_da_loja(auth, gerente):
    """Sem PIN pessoal não há mais "PIN já em uso": os dois autenticam com a
    mesma Senha de Login/Operacional/Master da loja normalmente."""
    outro = auth.criar_usuario("Maria", PerfilUsuario.OPERADOR_CAIXA)
    assert outro.id != gerente.id

    auth.logout()
    assert auth.login_como(gerente.id, PIN_MASTER) is gerente
    auth.logout()
    assert auth.login_como(outro.id, PIN_MASTER) is outro


def test_listar_ativos_ignora_desativados(auth, gerente, atendente):
    assert {f.nome for f in auth.listar_ativos()} == {"Gerente", "Atendente"}

    auth.desativar_usuario(atendente.id)
    assert [f.nome for f in auth.listar_ativos()] == ["Gerente"]


def test_buscar_funcionario_por_id(auth, gerente):
    assert auth.buscar_usuario(gerente.id) is gerente


def test_buscar_funcionario_inexistente(auth):
    with pytest.raises(RecursoNaoEncontradoError):
        auth.buscar_usuario(9999)


def test_desativar_funcionario_marca_como_inativo(auth, gerente, atendente):
    desativado = auth.desativar_usuario(atendente.id)
    assert desativado.ativo is False


def test_desativar_funcionario_ja_desativado(auth, gerente, atendente):
    auth.desativar_usuario(atendente.id)
    with pytest.raises(RegraDeNegocioError):
        auth.desativar_usuario(atendente.id)


def test_desativar_ultimo_gerente_ativo_e_bloqueado(auth, gerente, atendente):
    with pytest.raises(RegraDeNegocioError):
        auth.desativar_usuario(gerente.id)
    assert gerente.ativo is True


def test_desativar_gerente_e_permitido_se_sobrar_outro(auth, gerente):
    auth.criar_usuario("Segundo Gerente", PerfilUsuario.GERENTE)

    desativado = auth.desativar_usuario(gerente.id)
    assert desativado.ativo is False
    assert [f.nome for f in auth.listar_ativos()] == ["Segundo Gerente"]


def test_desativar_funcionario_inexistente(auth, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        auth.desativar_usuario(9999)


def test_criar_funcionario_sem_gerente_logado_e_bloqueado(auth, gerente):
    auth.logout()
    with pytest.raises(NaoAutorizadoError):
        auth.criar_usuario("Fantoche", PerfilUsuario.GERENTE)


def test_criar_funcionario_com_atendente_logado_e_bloqueado(auth, gerente, atendente):
    auth.login_como(atendente.id, PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        auth.criar_usuario("Fantoche", PerfilUsuario.GERENTE)


def test_criar_primeiro_funcionario_do_sistema_nao_exige_gerente(auth):
    # Bootstrap: o seed (ou o primeiro cadastro manual) não tem quem autorizar.
    funcionario = auth.criar_usuario("Gerente", PerfilUsuario.GERENTE)
    assert funcionario.perfil is PerfilUsuario.GERENTE


def test_desativar_funcionario_com_atendente_logado_e_bloqueado(auth, gerente, atendente):
    auth.login_como(atendente.id, PIN_ATENDENTE)
    with pytest.raises(AcessoNegadoError):
        auth.desativar_usuario(gerente.id)
    assert gerente.ativo is True


# ----------------------------------------------------------------------
# validar_pin_gerente / validar_pin_dono (Nível 2 e Nível 3, §3.13)
# ----------------------------------------------------------------------


def test_validar_pin_gerente_devolve_quem_esta_operando_sem_trocar_a_sessao(auth, gerente, atendente):
    auth.logout()
    auth.login_como(atendente.id, PIN_ATENDENTE)

    autorizador = auth.validar_pin_gerente(PIN_OPERACIONAL)
    assert autorizador is atendente
    assert auth.usuario_logado is atendente


def test_validar_pin_gerente_aceita_a_master_tambem(auth, gerente, atendente):
    auth.logout()
    auth.login_como(atendente.id, PIN_ATENDENTE)
    assert auth.validar_pin_gerente(PIN_MASTER) is atendente


def test_validar_pin_gerente_recusa_a_de_login(auth, gerente):
    # Mesmo motivo do teste de `validar_pin_nivel` acima: PIN_LOGIN e
    # PIN_OPERACIONAL são o mesmo valor de fábrica, então a Senha de Login
    # precisa ser trocada pra um valor distinto antes de testar a recusa.
    auth.loja_config.alterar_senha_login(PIN_OPERACIONAL, "999999")
    with pytest.raises(NaoAutorizadoError):
        auth.validar_pin_gerente("999999")


def test_validar_pin_gerente_com_pin_inexistente(auth, gerente):
    with pytest.raises(NaoAutorizadoError):
        auth.validar_pin_gerente(PIN_INVALIDO)


def test_validar_pin_dono_so_aceita_a_master(auth, gerente):
    assert auth.validar_pin_dono(PIN_MASTER) is gerente
    with pytest.raises(NaoAutorizadoError):
        auth.validar_pin_dono(PIN_OPERACIONAL)
    with pytest.raises(NaoAutorizadoError):
        auth.validar_pin_dono(PIN_LOGIN)


def test_regra_bloqueada_nao_deixa_lixo_gravado(auth, gerente, uow):
    with pytest.raises(RegraDeNegocioError):
        auth.criar_usuario("   ", PerfilUsuario.OPERADOR_CAIXA)

    uow.rollback()
    assert [f.nome for f in auth.listar_ativos()] == ["Gerente"]
