import pytest

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.services.exceptions import RegraDeNegocioError


def test_criar_sem_cargo_continua_permitido(funcionarios, gerente):
    funcionario = funcionarios.criar("Bruno")
    assert funcionario.cargo is None


def test_criar_aceita_uma_das_opcoes_fixas_do_seletor(funcionarios, gerente):
    """Os cinco textos estão escritos à mão de propósito: é o CONTRATO com o
    banco, não uma cópia do enum. Iterar `CargoFuncionario` aqui faria o teste
    aceitar qualquer renomeação em silêncio — e renomear um valor é mudança de
    dado gravado, que precisa de migração junto (foi o caso de "Atendente" →
    "Entregador", em `a7f3c2e5d918`)."""
    for cargo in ("Gerente", "Caixa", "Garçom", "Cozinha", "Entregador"):
        funcionario = funcionarios.criar(f"Pessoa {cargo}", cargo)
        assert funcionario.cargo == cargo


def test_criar_recusa_cargo_fora_das_opcoes_fixas(funcionarios, gerente):
    with pytest.raises(RegraDeNegocioError):
        funcionarios.criar("Fulano", "Cargo Inventado")


def test_editar_recusa_cargo_fora_das_opcoes_fixas(funcionarios, gerente, funcionario):
    with pytest.raises(RegraDeNegocioError):
        funcionarios.editar(funcionario.id, funcionario.nome, "Cargo Inventado")


# ---------------------------------------------------------------------------
# Turno / horário
# ---------------------------------------------------------------------------


def test_criar_grava_o_turno_informado(funcionarios, gerente):
    funcionario = funcionarios.criar("Caixa Turno - Noite", "Caixa", None, "T2 · Noite · 18h–00h")

    assert funcionario.turno_horario == "T2 · Noite · 18h–00h"


def test_editar_troca_o_horario_do_turno(funcionarios, gerente):
    """O defeito relatado: o turno nascia no seed do primeiro boot e não havia
    caminho nenhum para corrigir a faixa quando a escala mudasse."""
    pessoa = funcionarios.criar("Caixa Turno - Noite", "Caixa", None, "T2 · Noite · 16h–00h")

    atualizado = funcionarios.editar(
        pessoa.id, pessoa.nome, "Caixa", None, "T2 · Noite · 18h–00h"
    )

    assert atualizado.turno_horario == "T2 · Noite · 18h–00h"


def test_turno_em_branco_vira_none(funcionarios, gerente):
    """`None`, e não `""`: é o que o painel de detalhe conta para desenhar o
    travessão, e a linha da lista para não mostrar uma etiqueta vazia."""
    pessoa = funcionarios.criar("Bruno", "Caixa", None, "   ")

    assert pessoa.turno_horario is None


def test_turno_maior_que_a_coluna_e_recusado(funcionarios, gerente):
    """`funcionarios.turno_horario` é `String(60)`. Sem esta trava o banco
    truncaria em silêncio e o horário voltaria cortado na tela seguinte."""
    with pytest.raises(RegraDeNegocioError):
        funcionarios.criar("Bruno", "Caixa", None, "T" * 61)


# ---------------------------------------------------------------------------
# Renomear leva o login de mesmo nome junto
# ---------------------------------------------------------------------------


@pytest.fixture
def turno_da_noite(auth, funcionarios, gerente):
    """O par como o seed cria: o funcionário e o login com o mesmo nome."""
    login = auth.criar_usuario("Caixa Turno - Noite", PerfilUsuario.GERENTE)
    pessoa = funcionarios.criar("Caixa Turno - Noite", "Caixa", None, "T2 · Noite · 17h–01h")
    return pessoa, login


def test_renomear_o_funcionario_renomeia_o_login_do_par(uow, funcionarios, turno_da_noite):
    """O defeito relatado: o nome editado em Funcionários não chegava ao
    dropdown do login nem ao cabeçalho, que leem o `Usuario`."""
    pessoa, login = turno_da_noite

    funcionarios.editar(pessoa.id, "Caixa", "Caixa", None, pessoa.turno_horario)

    uow.session.expire_all()
    assert uow.usuarios.buscar_por_id(login.id).nome == "Caixa"
    assert uow.funcionarios.buscar_por_id(pessoa.id).nome == "Caixa"


def test_depois_de_renomeado_o_par_continua_casando(funcionarios, turno_da_noite):
    """`listar_operadores_caixa` (e a exclusão) acham o login pelo nome do
    funcionário: renomear só um lado tirava o turno do filtro dos relatórios."""
    pessoa, login = turno_da_noite

    funcionarios.editar(pessoa.id, "Caixa", "Caixa", None, pessoa.turno_horario)

    assert [u.id for u in funcionarios.listar_operadores_caixa()] == [login.id]


def test_nome_de_outro_login_e_recusado_sem_mudar_nada(uow, auth, funcionarios, turno_da_noite):
    """Dois operadores com o mesmo nome no dropdown não se distinguem, e o par
    por nome passaria a achar qualquer um dos dois. A recusa não deixa nenhum
    dos dois lados meio editado."""
    pessoa, login = turno_da_noite
    auth.criar_usuario("Caixa Turno - Manhã", PerfilUsuario.GERENTE)

    with pytest.raises(RegraDeNegocioError, match="Já existe um operador"):
        funcionarios.editar(pessoa.id, "Caixa Turno - Manhã", "Caixa", None, "outro turno")

    assert not uow.session.dirty
    uow.session.expire_all()
    assert uow.funcionarios.buscar_por_id(pessoa.id).nome == "Caixa Turno - Noite"
    assert uow.funcionarios.buscar_por_id(pessoa.id).turno_horario == "T2 · Noite · 17h–01h"
    assert uow.usuarios.buscar_por_id(login.id).nome == "Caixa Turno - Noite"


def test_editar_sem_mudar_o_nome_nao_toca_no_login(uow, funcionarios, turno_da_noite):
    pessoa, login = turno_da_noite

    funcionarios.editar(pessoa.id, pessoa.nome, "Caixa", None, "T2 · Noite · 18h–02h")

    assert uow.usuarios.buscar_por_id(login.id).nome == "Caixa Turno - Noite"


def test_funcionario_sem_login_so_renomeia_o_cadastro(uow, auth, funcionarios, gerente):
    """Garçom não loga: não há par, e nenhum login pode mudar de nome por causa dele."""
    pessoa = funcionarios.criar("Ana", "Garçom")
    nomes_antes = sorted(u.nome for u in auth.listar_ativos())

    funcionarios.editar(pessoa.id, "Ana Beatriz", "Garçom")

    assert sorted(u.nome for u in auth.listar_ativos()) == nomes_antes

