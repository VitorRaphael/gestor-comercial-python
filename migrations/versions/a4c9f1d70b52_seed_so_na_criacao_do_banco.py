"""o seed passa a rodar so na criacao do banco

Revision ID: a4c9f1d70b52
Revises: f8d1a6c40b27
Create Date: 2026-09-09 00:00:00.000003

Defeito relatado pelo Vitor: excluir um operador de turno na tela Funcionários
não persistia — no boot seguinte ele estava de volta na lista.

A causa não era a exclusão. `FuncionarioService.excluir` sempre apagou a linha
e sempre deu `commit`. Quem trazia o registro de volta era o `run_seed()`, que
roda a **cada** abertura do programa (`main.py`) logo depois das migrações:
cada `seed_*` é idempotente por nome, e idempotente é o mesmo que restaurador —
o registro apagado deixa de existir, o seed do boot seguinte conclui que
"falta" e o cria de novo. Não era só dos turnos: produto e categoria excluídos
no Cardápio voltavam pelo mesmo caminho.

Esta revisão cria a tabela `preferencias` (chave → valor, ver
`domain/preferencia.py`), onde mora a marca `bootstrap_concluido` que o
`run_seed()` passa a consultar antes de povoar qualquer coisa.

## Por que o banco que já existe recebe a marca aqui

Um banco que já existe **já foi povoado** — é a definição de já existir. Se
esta migração não marcasse nada, o primeiro boot depois da atualização rodaria
o seed uma última vez e ressuscitaria, uma última vez, exatamente o que o Vitor
apagou. Marcar aqui é o que faz a correção valer já na primeira abertura, e não
na segunda.

"Já existe" é decidido por dado que só o seed cria: mesas, usuários ou produtos.
Um `.db` criado e nunca povoado (as tabelas existem, vazias) não é marcado, e o
boot seguinte o povoa normalmente.

O que se perde, e é de propósito: numa instalação que estivesse parada entre
a migração `d3f8a1c4e6b9` e o seed seguinte (os dois `Usuario` de turno
criados, os dois `Funcionario` correspondentes ainda não), o cadastro
automático deles não acontece mais — restam o cadastro manual pela tela de
Funcionários. É uma janela que só existe DENTRO de um boot (migrações e seed
rodam em sequência, no mesmo `main()`), então um banco salvo entre duas
aberturas não fica nela. E o inverso — recriar o que foi apagado de propósito —
é o defeito que esta revisão existe para fechar: na dúvida entre repovoar e
respeitar a exclusão, respeitar a exclusão.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4c9f1d70b52'
down_revision: Union[str, Sequence[str], None] = 'f8d1a6c40b27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Cópia congelada de `repository/preferencia_repository.py`. Migração aplicada
# meses depois não pode depender de o código do app ainda ter aquela constante
# com aquele valor.
BOOTSTRAP_CONCLUIDO = "bootstrap_concluido"
SIM = "sim"

# As tabelas que provam, pela simples existência de uma linha, que este banco
# já passou por um boot completo.
#
# `usuarios` ficou de fora de propósito, e não por esquecimento: as migrações
# `d3f8a1c4e6b9`, `f4b2c8e1a7d5` e `d23a4f888a77` inserem `Usuario` por conta
# própria — a `f4b2c8e1a7d5` cria os dois operadores de turno em TODO banco,
# inclusive num recém-criado. Um banco novo chega aqui já com dois usuários, e
# usá-los como sinal marcaria o bootstrap como concluído antes de ele
# acontecer: o `run_seed()` sairia na primeira linha e a instalação nasceria
# sem as 60 mesas e sem o cardápio.
#
# `mesas` e `produtos` não são tocadas por migração nenhuma (conferido em todo
# o histórico de `migrations/versions/`): quem as preenche é só o seed, e é por
# isso que elas — e não a contagem de usuários — respondem "este banco já foi
# povoado".
TABELAS_DE_POVOAMENTO = ("mesas", "produtos")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "preferencias",
        sa.Column("chave", sa.String(length=60), nullable=False),
        sa.Column("valor", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("chave"),
    )

    conexao = op.get_bind()
    ja_povoado = any(
        (conexao.execute(sa.text(f"SELECT 1 FROM {tabela} LIMIT 1")).first() is not None)
        for tabela in TABELAS_DE_POVOAMENTO
    )
    if ja_povoado:
        conexao.execute(
            sa.text("INSERT INTO preferencias (chave, valor) VALUES (:chave, :valor)"),
            {"chave": BOOTSTRAP_CONCLUIDO, "valor": SIM},
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Derrubar a tabela devolve o comportamento antigo por inteiro: sem a marca,
    # `run_seed()` volta a povoar a cada boot. É a simetria certa — a versão
    # anterior do app não sabe ler esta tabela e não deve encontrá-la.
    op.drop_table("preferencias")
