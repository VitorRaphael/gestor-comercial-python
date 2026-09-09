"""O seed povoa o banco novo e **nunca** repovoa o que o usuário apagou.

Defeito relatado pelo Vitor: excluir um operador de turno na tela Funcionários
não persistia — no boot seguinte ele estava de volta.

A exclusão sempre funcionou (`FuncionarioService.excluir` apaga a linha e
commita). Quem trazia o registro de volta era o `run_seed()`, chamado a cada
abertura do programa em `main.py`: cada `seed_*` é idempotente por nome, e
idempotente é o mesmo que **restaurador** — o registro apagado deixa de
existir, o seed do boot seguinte conclui que "falta" e o cria de novo.

Estes testes exercitam o `run_seed()` de verdade, contra um arquivo `.db` de
verdade, porque é a função inteira (e não cada `seed_*`) que ganhou a marca de
bootstrap. O primeiro teste é o de premissa: sem ele, um `run_seed()` que não
povoasse nada passaria em todos os outros sem ter olhado.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import gestor_comercial.domain  # noqa: F401 - importar o pacote registra os mappers
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.preferencia import Preferencia
from gestor_comercial.domain.produto import Produto
from gestor_comercial.repository import seed
from gestor_comercial.repository.base import Base
from gestor_comercial.repository.preferencia_repository import BOOTSTRAP_CONCLUIDO


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um arquivo `.db` vazio, com o `run_seed()` apontado para ele.

    `seed.py` importa `SessionLocal` no topo, então a variável de ambiente
    `GESTOR_COMERCIAL_DB` (lida na importação de `repository.base`) chegaria
    tarde demais: quem é trocado aqui é o `SessionLocal` do módulo do seed.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'gestor.db'}")
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    monkeypatch.setattr(seed, "SessionLocal", fabrica)
    return fabrica


def test_o_primeiro_boot_povoa_o_banco(banco):
    """Premissa: um `run_seed()` que não povoa nada passaria calado no resto."""
    seed.run_seed()

    with banco() as sessao:
        assert sessao.query(Mesa).count() == seed.TOTAL_MESAS
        assert sessao.query(Produto).count() > 100, "o cardápio real do food truck"
        assert sessao.query(Funcionario).count() == 2, "os dois operadores de turno"


def test_o_primeiro_boot_deixa_a_marca_de_bootstrap(banco):
    seed.run_seed()

    with banco() as sessao:
        marca = sessao.get(Preferencia, BOOTSTRAP_CONCLUIDO)
        assert marca is not None, (
            "sem a marca, o boot seguinte volta a povoar — que é o defeito inteiro"
        )


def test_o_turno_excluido_nao_volta_no_boot_seguinte(banco):
    """O defeito relatado, reproduzido: excluir, "reabrir o programa", conferir.

    É a exclusão FÍSICA da linha, como `FuncionarioService.excluir` faz — não a
    desativação. Antes da marca, o `seed_funcionarios_turno` não achava o nome,
    concluía que faltava e recriava.
    """
    seed.run_seed()

    with banco() as sessao:
        turno = sessao.query(Funcionario).filter_by(nome=seed.NOME_CAIXA_MANHA).one()
        sessao.delete(turno)
        sessao.commit()

    seed.run_seed()  # o boot seguinte

    with banco() as sessao:
        nomes = [f.nome for f in sessao.query(Funcionario).all()]
        assert seed.NOME_CAIXA_MANHA not in nomes, (
            f"o turno excluído ressuscitou no boot seguinte: {nomes}"
        )
        assert seed.NOME_CAIXA_NOITE in nomes, "o outro turno não podia sumir junto"


def test_o_produto_excluido_no_cardapio_tambem_nao_volta(banco):
    """O mesmo defeito na outra tela — e é por isso que a marca é do `run_seed()`
    inteiro, e não um `if` dentro de `seed_funcionarios_turno`.

    O Cardápio exclui produto e categoria (`CardapioService.excluir_produto`), e
    `seed_cardapio` os recriava pelo mesmo caminho: pula o nome que existe,
    recria o que "falta".
    """
    seed.run_seed()

    with banco() as sessao:
        produto = sessao.query(Produto).filter_by(nome="X Burguer").one()
        sessao.delete(produto)
        sessao.commit()

    seed.run_seed()

    with banco() as sessao:
        assert sessao.query(Produto).filter_by(nome="X Burguer").first() is None


def test_a_mesa_excluida_tambem_nao_volta(banco):
    """Nenhuma tela apaga mesa hoje, e é justamente esse o ponto: quando alguma
    apagar, o repovoamento não vai voltar junto."""
    seed.run_seed()

    with banco() as sessao:
        sessao.delete(sessao.query(Mesa).filter_by(numero=7).one())
        sessao.commit()

    seed.run_seed()

    with banco() as sessao:
        assert sessao.query(Mesa).filter_by(numero=7).first() is None
        assert sessao.query(Mesa).count() == seed.TOTAL_MESAS - 1


def test_boots_repetidos_nao_duplicam_nada(banco):
    """Cinco aberturas seguidas, sem exclusão nenhuma: o banco tem que ficar
    idêntico ao do primeiro boot."""
    seed.run_seed()
    with banco() as sessao:
        contagem = (
            sessao.query(Mesa).count(),
            sessao.query(Produto).count(),
            sessao.query(Funcionario).count(),
        )

    for _ in range(4):
        seed.run_seed()

    with banco() as sessao:
        assert contagem == (
            sessao.query(Mesa).count(),
            sessao.query(Produto).count(),
            sessao.query(Funcionario).count(),
        )


def test_a_marca_e_o_que_decide_e_nao_a_contagem_de_linhas(banco):
    """Um banco marcado e VAZIO continua vazio.

    Este é o teste que separa a correção certa da tentadora: "só povoa se as
    tabelas estiverem vazias" faria o defeito voltar inteiro no dia em que
    alguém apagasse o último registro de alguma delas.
    """
    seed.run_seed()

    with banco() as sessao:
        sessao.query(Funcionario).delete()
        sessao.commit()

    seed.run_seed()

    with banco() as sessao:
        assert sessao.query(Funcionario).count() == 0


def test_bootstrap_ja_rodou_le_a_marca(banco):
    with banco() as sessao:
        assert seed.bootstrap_ja_rodou(sessao) is False

    seed.run_seed()

    with banco() as sessao:
        assert seed.bootstrap_ja_rodou(sessao) is True
