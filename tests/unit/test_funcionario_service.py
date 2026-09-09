import pytest

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
