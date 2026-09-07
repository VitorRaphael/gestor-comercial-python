from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
#
# `disable_existing_loggers=False` NÃO é enfeite, e o padrão do Python (`True`)
# é um defeito grave neste projeto. `main.py` roda `alembic upgrade` em TODO
# boot, e este `fileConfig` acontece depois de `instalar_escudo()` já ter ligado
# a caixa-preta. Com o padrão, o `fileConfig` marca `disabled = True` em todo
# logger que já existia e não esteja nomeado no `alembic.ini` — inclusive o
# `gestor_comercial`. Resultado: o arquivo de log ficava com a linha "Boot do
# Gestor Comercial" e **mais nada, pelo turno inteiro**. Exatamente o silêncio
# que a etapa de Mitigação de Falhas existe para acabar.
#
# Medido em 2026-09-07: `disabled` era `False` antes do upgrade e `True` depois.
# Trancado por `tests/unit/test_resiliencia.py::test_migrations_nao_desligam_o_log`.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# `boot_do_app` é posto por `main._aplicar_migrations`. Silencia o progresso das
# migrations quando quem está rodando é o PDV abrindo — aquelas linhas vão para o
# `stderr`, e o espelho do escudo as registraria como ERROR num boot saudável.
# Pela linha de comando (`alembic upgrade`) a bandeira não existe e o progresso
# continua aparecendo normalmente.
if config.attributes.get("boot_do_app"):
    import logging

    logging.getLogger("alembic").setLevel(logging.WARNING)

# add your model's MetaData object here
# for 'autogenerate' support
from gestor_comercial.domain import *  # noqa: F401,F403 - registra os mappers
from gestor_comercial.repository.base import Base, DB_PATH

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # render_as_batch: o SQLite não suporta ALTER COLUMN/DROP COLUMN.
        # O modo batch recria a tabela e copia os dados, que é o que permite
        # evoluir o schema sem perder vendas já registradas.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
