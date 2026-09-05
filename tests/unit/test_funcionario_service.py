import pytest

from gestor_comercial.services.exceptions import RegraDeNegocioError


def test_criar_sem_cargo_continua_permitido(funcionarios, gerente):
    funcionario = funcionarios.criar("Bruno")
    assert funcionario.cargo is None


def test_criar_aceita_uma_das_opcoes_fixas_do_dropdown(funcionarios, gerente):
    for cargo in ("Gerente", "Caixa", "Garçom", "Cozinha", "Atendente"):
        funcionario = funcionarios.criar(f"Pessoa {cargo}", cargo)
        assert funcionario.cargo == cargo


def test_criar_recusa_cargo_fora_das_opcoes_fixas(funcionarios, gerente):
    with pytest.raises(RegraDeNegocioError):
        funcionarios.criar("Fulano", "Cargo Inventado")


def test_editar_recusa_cargo_fora_das_opcoes_fixas(funcionarios, gerente, funcionario):
    with pytest.raises(RegraDeNegocioError):
        funcionarios.editar(funcionario.id, funcionario.nome, "Cargo Inventado")
