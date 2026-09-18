"""bobina e letra grossa da impressora

Revision ID: b9d2f5a31c47
Revises: c7b4e0f12a86
Create Date: 2026-09-17 00:00:00.000000

Pedido do Vitor (§9.22): o cartão de impressora ganhou "Colunas por linha" e
"Espessura da letra", e a bobina passou a ser gravada em vez de deduzida.

**`bobina_mm`** (`NOT NULL DEFAULT 80`). Até aqui a bobina não existia no banco:
o cartão do §9.19 a lia das colunas, e até 40 colunas era 58mm. Com as colunas
num seletor próprio, "58mm + 48 col." é uma escolha que o gerente pode gravar,
e deduzida ela reabriria como 80mm. Decisão do Vitor, perguntada antes de
começar: gravar. As linhas que já existem recebem a MESMA regra de antes
(`colunas <= 40` → 58, senão 80), então a tela reabre cada impressora
exatamente como abria. A regra mora também em
`domain.impressora.bobina_mm_das_colunas`, e um teste confere que o `CASE` daqui
e a função de lá não divergem.

**`letra_grossa`** (`NOT NULL DEFAULT 0`). Toda impressora que já existe imprime
em letra fina, que é o que ela sempre fez: não há dado a chutar.

**`colunas`** já existe desde a `06b890e91ef1` (`NOT NULL DEFAULT 48`). O pedido
mandava acrescentá-la de forma defensiva, e é o que o laço abaixo faz: se ela
estiver lá, passa reto. Só faltaria num banco mexido à mão, e sem ela o
preenchimento da bobina não teria de onde ler.

## Atômica de verdade — e por que precisou de um `BEGIN`

O Alembic trata o DDL do SQLite como **não-transacional**
(`transactional_ddl = False`), e o `sqlite3` do Python só abre transação sozinho
antes de INSERT/UPDATE/DELETE. O `ALTER TABLE` que chega primeiro roda em
autocommit. Medido numa sonda: com uma queda depois do `ADD COLUMN`, a coluna
FICA no arquivo e a `alembic_version` continua na revisão anterior — foi
exatamente o que aconteceu com a `f8d1a6c40b27` na máquina do Vitor.

O SQLite, porém, desfaz `ALTER TABLE` dentro de transação. Por isso o
`upgrade()` abre ela mesmo um `BEGIN` quando não há transação aberta (com
transação já aberta, por uma revisão anterior no mesmo `upgrade head`, ela já
está dentro de uma e não pode abrir outra). As colunas, o preenchimento e a
troca da `alembic_version` passam a ser um commit só: queda no meio, nada muda,
e o boot seguinte refaz do zero. O teste derruba o preenchimento com um
gatilho (`RAISE(ABORT)`) e confere que a tabela voltou intacta.

O `if` de cada coluna continua lá mesmo assim: é o cinto para o banco que
ganhou a coluna à mão. E o preenchimento roda SEMPRE, não só quando a coluna é
criada agora. Isso é seguro porque o app não grava nada antes de a migração
terminar (`main.py` roda o `upgrade` antes de abrir a janela). E é necessário:
numa coluna posta à mão, todas as linhas estariam no default 80.

**O que esta migração NÃO faz**, a regra de ouro das irmãs: não toca em
`categorias.impressora_id`. O roteamento continua saindo de
`produto.categoria.impressora`, e nenhuma impressora precisa ser reconfigurada.
"""
from typing import Sequence, Union
import sqlite3

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9d2f5a31c47'
down_revision: Union[str, Sequence[str], None] = 'c7b4e0f12a86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABELA = "impressoras"

# Até quantas colunas uma impressora é lida como bobina de 58mm. É o
# `TETO_COLUNAS_58MM` do domain, copiado e não importado: uma migração tem que
# continuar fazendo amanhã o que fez hoje, mesmo que a regra do app mude.
TETO_COLUNAS_58MM = 40

COLUNAS_NOVAS = (
    ("colunas", sa.Integer(), "48"),
    ("bobina_mm", sa.Integer(), "80"),
    ("letra_grossa", sa.Boolean(), "0"),
)


def _colunas_existentes() -> set[str]:
    inspetor = sa.inspect(op.get_bind())
    return {coluna["name"] for coluna in inspetor.get_columns(TABELA)}


def _abrir_transacao() -> None:
    """`BEGIN` explícito, para o `ALTER TABLE` entrar na transação. Ver o cabeçalho."""
    if context.is_offline_mode():  # pragma: no cover - o app só migra conectado
        return
    conexao = op.get_bind()
    dbapi = conexao.connection.dbapi_connection
    if isinstance(dbapi, sqlite3.Connection) and not dbapi.in_transaction:
        conexao.exec_driver_sql("BEGIN")


def upgrade() -> None:
    """Upgrade schema."""
    _abrir_transacao()
    existentes = _colunas_existentes()
    for nome, tipo, padrao in COLUNAS_NOVAS:
        if nome not in existentes:
            # `server_default`, e não só o `default` do ORM: o
            # `ADD COLUMN NOT NULL` do SQLite exige um default para preencher
            # as linhas que já estão lá.
            op.add_column(
                TABELA,
                sa.Column(nome, tipo, nullable=False, server_default=sa.text(padrao)),
            )
    op.execute(
        f"UPDATE {TABELA} SET bobina_mm = CASE WHEN colunas <= {TETO_COLUNAS_58MM} "
        "THEN 58 ELSE 80 END"
    )
    # Cinto, como na `a3e6b91c4d05`: coluna nascida de outro caminho pode ter
    # NULL, e impressora sem espessura não passa pelo `bool()` do driver igual.
    op.execute(f"UPDATE {TABELA} SET letra_grossa = 0 WHERE letra_grossa IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    # `DROP COLUMN` nativo (SQLite 3.35+), pelo motivo da `a3e6b91c4d05`: o
    # `batch_alter_table` recriaria `impressoras` com `categorias` apontando para
    # ela e o `foreign_keys=ON` ligado. `colunas` NÃO sai: ela é da `06b890e91ef1`.
    #
    # Voltar perde a bobina e a espessura. A bobina volta a ser deduzida das
    # colunas (o §9.19), e toda impressora volta a imprimir em letra fina.
    existentes = _colunas_existentes()
    for nome in ("letra_grossa", "bobina_mm"):
        if nome in existentes:
            op.execute(f"ALTER TABLE {TABELA} DROP COLUMN {nome}")
