"""A migração `a4c9f1d70b52` só marca como povoado o banco que JÁ foi povoado.

A marca `bootstrap_concluido` é o que faz o `run_seed()` parar de repovoar a
cada boot. Num banco recém-criado ela não pode existir — senão a instalação
nasce sem as 60 mesas e sem o cardápio. Num banco que já rodava, ela precisa
existir já na primeira abertura depois da atualização — senão o seed roda mais
uma vez e ressuscita, uma última vez, exatamente o que o Vitor apagou.

Os dois lados são testados aqui porque a diferença entre eles é uma linha de
`SELECT`, e errar de qualquer um dos lados é um defeito grave e silencioso.

O terceiro teste é o que essa linha de `SELECT` custou a acertar: as migrações
`d3f8a1c4e6b9`, `f4b2c8e1a7d5` e `d23a4f888a77` inserem `Usuario` por conta
própria, e a `f4b2c8e1a7d5` faz isso em TODO banco. Um banco novo, portanto,
chega aqui com dois usuários e zero mesas — e usar `usuarios` como sinal de
"já povoado" marcaria o bootstrap antes de ele acontecer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

import gestor_comercial

REVISAO_ANTERIOR = "f8d1a6c40b27"
REVISAO = "a4c9f1d70b52"


def _config(arquivo: Path):
    from alembic.config import Config

    raiz = Path(gestor_comercial.__file__).resolve().parents[2]
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{arquivo}")
    return config


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um banco na revisão ANTERIOR à que está sendo testada."""
    from alembic import command

    arquivo = tmp_path / "loja.db"
    monkeypatch.setenv("GESTOR_COMERCIAL_DB", str(arquivo))
    command.upgrade(_config(arquivo), REVISAO_ANTERIOR)
    return arquivo


def _subir(arquivo: Path) -> None:
    from alembic import command

    command.upgrade(_config(arquivo), REVISAO)


def _marca(arquivo: Path) -> str | None:
    engine = sa.create_engine(f"sqlite:///{arquivo}")
    with engine.connect() as conexao:
        return conexao.execute(
            sa.text("SELECT valor FROM preferencias WHERE chave = 'bootstrap_concluido'")
        ).scalar()


def test_banco_recem_criado_nao_e_marcado(banco):
    """Sem mesa e sem produto, este banco nunca foi povoado: o seed do primeiro
    boot precisa rodar normalmente depois desta migração."""
    _subir(banco)

    assert _marca(banco) is None, (
        "marcar um banco vazio faz a instalação nascer sem mesas e sem cardápio"
    )


def test_banco_ja_povoado_e_marcado(banco):
    """Uma linha em `mesas` basta: quem tem mesa já passou por um boot completo."""
    engine = sa.create_engine(f"sqlite:///{banco}")
    with engine.begin() as conexao:
        conexao.execute(sa.text("INSERT INTO mesas (numero, status) VALUES (1, 'LIVRE')"))

    _subir(banco)

    assert _marca(banco) == "sim", (
        "sem a marca, o primeiro boot depois da atualização repovoa o que foi apagado"
    )


def test_produto_tambem_conta_como_banco_povoado(banco):
    engine = sa.create_engine(f"sqlite:///{banco}")
    with engine.begin() as conexao:
        conexao.execute(sa.text("INSERT INTO categorias (nome, ativo) VALUES ('Lanches', 1)"))
        conexao.execute(
            sa.text(
                "INSERT INTO produtos (nome, preco, custo, ativo, is_combo, categoria_id) "
                "VALUES ('X Burguer', 13, 0, 1, 0, 1)"
            )
        )

    _subir(banco)

    assert _marca(banco) == "sim"


def test_os_usuarios_criados_por_migracao_nao_contam_como_povoamento(banco):
    """O caso que quase passou despercebido.

    `f4b2c8e1a7d5` cria "Caixa Turno - Manhã" e "Caixa Turno - Noite" em todo
    banco, inclusive num recém-criado — então quando esta migração roda, um
    banco novo já tem dois usuários. Se `usuarios` fosse o sinal, a marca
    entraria e o `run_seed()` nunca povoaria a instalação.
    """
    engine = sa.create_engine(f"sqlite:///{banco}")
    with engine.connect() as conexao:
        usuarios = conexao.execute(sa.text("SELECT COUNT(*) FROM usuarios")).scalar()
        mesas = conexao.execute(sa.text("SELECT COUNT(*) FROM mesas")).scalar()
    assert usuarios == 2, "premissa: as migrações criam os dois operadores sozinhas"
    assert mesas == 0, "premissa: mesa nenhuma vem de migração"

    _subir(banco)

    assert _marca(banco) is None


def test_a_ida_e_volta_derruba_a_tabela(banco):
    """Descer a revisão devolve o comportamento antigo por inteiro — é o que
    permite despromover a versão na máquina do balcão se algo der errado."""
    from alembic import command

    _subir(banco)
    command.downgrade(_config(banco), REVISAO_ANTERIOR)

    engine = sa.create_engine(f"sqlite:///{banco}")
    with engine.connect() as conexao:
        tabelas = {
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type = 'table'")
            )
        }
    assert "preferencias" not in tabelas
