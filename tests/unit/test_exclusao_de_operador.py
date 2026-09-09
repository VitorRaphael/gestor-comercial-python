"""Excluir um operador de turno tira o cadastro E aposenta o login dele.

Metade do defeito relatado pelo Vitor era o seed repovoando (ver
`test_seed_do_primeiro_boot.py`). A outra metade é esta: `Funcionario` e
`Usuario` são tabelas separadas (§3.11) e a tela de Funcionários sempre mexeu
só na primeira, então o nome excluído continuava aparecendo no dropdown da tela
de login — a exclusão que "não pegou".

O par é casado por **nome**, a mesma convenção que `listar_operadores_caixa` já
usava por não haver FK entre as duas tabelas.

O login é **desativado**, nunca apagado: `usuarios.id` é chave estrangeira de
`caixas.aberto_por_id`, `comandas.usuario_id` e `movimentos_caixa.usuario_id`,
e apagar a linha arrancaria o nome de todo turno e toda venda que aquele
operador registrou. Desativar preserva o histórico e some da tela de login, que
lista só ativos.

E há uma trava que não pode ser atropelada por este caminho: sem nenhum gerente
ativo ninguém mais autoriza cancelamento nem abre caixa, e não existe tela de
recuperação. Por isso a checagem acontece ANTES de qualquer escrita — descobrir
a trava no meio deixaria o funcionário excluído e o login de pé, que é meia
exclusão.
"""

from __future__ import annotations

import pytest

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.services.exceptions import RegraDeNegocioError

NOME_DO_TURNO = "Caixa Turno - Manhã"


@pytest.fixture
def turno(uow, auth, funcionarios, gerente):
    """Um operador de turno como o app o tem: cadastro em Funcionários E login.

    O `gerente` da fixture existe só para haver um segundo gerente ativo — sem
    ele, a trava do último gerente barraria a exclusão e os testes mediriam
    outra coisa.
    """
    login = auth.criar_usuario(NOME_DO_TURNO, PerfilUsuario.GERENTE)
    cadastro = funcionarios.criar(NOME_DO_TURNO, "Caixa")
    return cadastro, login


def test_excluir_tira_o_cadastro_da_tela_de_funcionarios(funcionarios, turno):
    cadastro, _ = turno

    funcionarios.excluir(cadastro.id)

    assert all(f.nome != NOME_DO_TURNO for f in funcionarios.listar_todos())


def test_excluir_tira_o_operador_da_tela_de_login(auth, funcionarios, turno):
    """O sintoma que o Vitor via: o nome continuava no dropdown."""
    cadastro, _ = turno

    funcionarios.excluir(cadastro.id)

    assert all(u.nome != NOME_DO_TURNO for u in auth.listar_ativos())


def test_o_login_e_desativado_e_nao_apagado(auth, uow, funcionarios, turno):
    """O histórico de vendas daquele operador aponta para `usuarios.id`."""
    cadastro, login = turno

    funcionarios.excluir(cadastro.id)

    ainda_existe = uow.usuarios.buscar_por_id(login.id)
    assert ainda_existe is not None, "apagar arrancaria o nome de todo turno gravado"
    assert ainda_existe.ativo is False


def test_a_exclusao_persiste_no_banco(uow, funcionarios, turno):
    """Commit de verdade, e não só a Session em memória: expira tudo e relê."""
    cadastro, login = turno

    funcionarios.excluir(cadastro.id)
    uow.session.expire_all()

    assert uow.funcionarios.buscar_por_id(cadastro.id) is None
    assert uow.usuarios.buscar_por_id(login.id).ativo is False


def test_funcionario_sem_login_de_mesmo_nome_e_excluido_normalmente(funcionarios, gerente):
    """O caso comum: garçom, cozinha, entregador — não logam e não têm par."""
    garcom = funcionarios.criar("Maria", "Garçom")

    funcionarios.excluir(garcom.id)

    assert all(f.nome != "Maria" for f in funcionarios.listar_todos())


def test_o_ultimo_gerente_ativo_barra_a_exclusao_inteira(auth, funcionarios):
    """Sem outro gerente, o login não pode ser aposentado — e então nada é
    apagado. É a diferença entre recusar e deixar meia exclusão para trás."""
    unico = auth.criar_usuario(NOME_DO_TURNO, PerfilUsuario.GERENTE)
    auth.login_como(unico.id, "26407200")
    cadastro = funcionarios.criar(NOME_DO_TURNO, "Caixa")

    with pytest.raises(RegraDeNegocioError, match="último gerente ativo"):
        funcionarios.excluir(cadastro.id)

    assert any(f.nome == NOME_DO_TURNO for f in funcionarios.listar_todos()), (
        "recusar tem que ser tudo-ou-nada: o cadastro não pode ter sumido"
    )
    assert any(u.nome == NOME_DO_TURNO for u in auth.listar_ativos())


def test_login_ja_inativo_nao_impede_a_exclusao(auth, uow, funcionarios, gerente):
    """Um operador desativado antes de ser excluído: não há o que aposentar, e
    a trava do último gerente não se aplica a quem já está fora."""
    login = auth.criar_usuario(NOME_DO_TURNO, PerfilUsuario.GERENTE)
    auth.desativar_usuario(login.id)
    cadastro = funcionarios.criar(NOME_DO_TURNO, "Caixa")

    funcionarios.excluir(cadastro.id)

    assert uow.funcionarios.buscar_por_id(cadastro.id) is None


def test_funcionario_com_historico_continua_barrado(
    uow, auth, funcionarios, mesa, caixa_aberto, turno
):
    """A regra antiga não pode ter afrouxado: quem já atendeu não some, para
    não destruir registro de venda. E o login dele não pode ser aposentado
    junto de uma exclusão que nem aconteceu."""
    from gestor_comercial.services.comanda_service import ComandaService

    cadastro, login = turno
    comandas = ComandaService(uow, auth)
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.definir_atendente(comanda.id, cadastro.id)

    with pytest.raises(RegraDeNegocioError, match="histórico"):
        funcionarios.excluir(cadastro.id)

    assert login.ativo is True


def test_motivo_para_nao_desativar_devolve_none_quando_pode(auth, gerente):
    outro = auth.criar_usuario("Segundo Gerente", PerfilUsuario.GERENTE)

    assert auth.motivo_para_nao_desativar(outro) is None


def test_motivo_para_nao_desativar_ignora_quem_nao_e_gerente(auth, gerente, atendente):
    """A trava é sobre gerente: um operador de caixa comum nunca é o último."""
    assert auth.motivo_para_nao_desativar(atendente) is None
