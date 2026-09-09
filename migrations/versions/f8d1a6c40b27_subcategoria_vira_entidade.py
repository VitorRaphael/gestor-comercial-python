"""a subcategoria vira entidade, com tabela propria

Revision ID: f8d1a6c40b27
Revises: e2c7b4f9a613
Create Date: 2026-09-09 00:00:00.000002

A revisão anterior (`e2c7b4f9a613`) guardou a subcategoria como TEXTO no
produto. Funcionava para etiquetar, e não para o que o Vitor pediu em seguida
(§9.9): uma **tela de cadastro**. Texto no produto não permite criar uma
subcategoria vazia esperando os itens — ela só passa a existir quando algum
produto carrega a string —, e renomear "Podrão" exigiria varrer e reescrever
todo produto que a carregasse, uma reescrita em massa que, falhando no meio,
deixaria metade do cardápio num grupo e metade no outro.

Então esta revisão faz três coisas, nesta ordem:

1. cria `subcategorias` (id, nome, categoria_id), com o par (categoria, nome)
   único — "Podrão" em Lanches e "Podrão" em Porções são duas subdivisões
   independentes;
2. cria `produtos.subcategoria_id` e **converte o dado que existir**: cada
   valor distinto de `produtos.subcategoria` vira uma linha da tabela nova,
   dentro da categoria em que aparecia, e os produtos passam a apontar para
   ela;
3. só então derruba `produtos.subcategoria` e o índice
   `idx_produtos_categoria_sub`, que era daquele desenho.

**A regra de ouro do §9.8 continua**: nada aqui toca em `categorias` ou
`impressoras`. O roteamento do cupom sai de `produto.categoria.impressora`, e
um produto que muda de subcategoria continua saindo na mesma bobina.

Na prática, na máquina do food truck, o passo 2 não deve encontrar nada: a
revisão anterior entrou hoje e o `seed.py` nunca classificou produto nenhum.
Ele existe porque o banco de lá é a única cópia — e porque a conversão é a
diferença entre "o Vitor perde a classificação que fez" e "não perde".

O `downgrade` desfaz na mesma medida: devolve a coluna de texto preenchida com
o nome da subcategoria apontada, recria o índice antigo e derruba a tabela.
Uma ida e volta preserva o dado, e é isso que permite despromover a versão no
balcão se algo der errado.

## Por que NÃO há `batch_alter_table` aqui

Havia, e derrubou o app do Vitor no arranque. `batch_alter_table` é a receita
padrão do Alembic para SQLite porque o `ALTER TABLE` dele é mínimo — mas ela
funciona **recriando a tabela**: cria uma temporária, copia, `DROP TABLE
produtos`, renomeia. E o projeto liga `PRAGMA foreign_keys=ON` em toda conexão
(§3.5), então esse `DROP TABLE` esbarra nas linhas de `combo_itens` e
`itens_comanda` que apontam para `produtos`:

    sqlite3.IntegrityError: FOREIGN KEY constraint failed
    [SQL: DROP TABLE produtos]

Num banco recém-criado nada disso acontece — `produtos` está vazia e ninguém a
referencia. É por isso que a suíte passava: os testes de migração populavam
`produtos` com meia dúzia de linhas e **nenhuma** linha de `combo_itens`. No
banco do food truck, o seed cria 113 produtos e 8 componentes de combo, e a
migração morria na primeira tentativa.

O SQLite ganhou `ALTER TABLE ... DROP COLUMN` nativo na 3.35 (2021), e o app
embarca a sua própria 3.50 no `.exe`. Nativo, a coluna sai **sem recriar a
tabela**: nada é dropado, nada é copiado, e as FKs das outras tabelas não são
tocadas. `_dropar_coluna` abaixo usa o nativo quando ele existe e cai no
`batch` (com as FKs desligadas em volta) só num SQLite antigo demais —
`tests/unit/test_migracao_subcategoria_entidade.py` exercita os dois caminhos,
para nenhum ficar sem teste.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8d1a6c40b27'
down_revision: Union[str, Sequence[str], None] = 'e2c7b4f9a613'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDICE_ANTIGO = "idx_produtos_categoria_sub"

# `ALTER TABLE ... DROP COLUMN` nativo entrou no SQLite 3.35 (2021).
SQLITE_COM_DROP_COLUMN = (3, 35)


def _colunas_de_produtos() -> set[str]:
    inspetor = sa.inspect(op.get_bind())
    return {coluna["name"] for coluna in inspetor.get_columns("produtos")}


def _tem_drop_column_nativo() -> bool:
    import sqlite3

    maior, menor, *_ = (int(parte) for parte in sqlite3.sqlite_version.split("."))
    return (maior, menor) >= SQLITE_COM_DROP_COLUMN


def _dropar_coluna(tabela: str, coluna: str) -> None:
    """Tira a coluna sem recriar a tabela — ver o cabeçalho deste arquivo.

    O caminho de baixo (`batch_alter_table`) recria a tabela e por isso precisa
    das FKs desligadas: o `DROP TABLE` intermediário esbarraria nas linhas de
    `combo_itens`/`itens_comanda` que apontam para `produtos`. O
    `PRAGMA foreign_keys` é ignorado dentro de uma transação, daí o `commit()`
    antes — e o religar acontece no `finally`, porque um banco que continuasse
    com as FKs desligadas depois da migração aceitaria item órfão em silêncio,
    que é exatamente o que o §3.5 existe para impedir.
    """
    if _tem_drop_column_nativo():
        op.execute(f"ALTER TABLE {tabela} DROP COLUMN {coluna}")
        return

    conexao = op.get_bind()
    conexao.commit()
    conexao.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_column(coluna)
    finally:
        conexao.commit()
        conexao.exec_driver_sql("PRAGMA foreign_keys=ON")


def upgrade() -> None:
    """Upgrade schema."""
    # `if_not_exists` nos três passos de criação: a primeira tentativa desta
    # migração na máquina do Vitor criou a tabela e morreu adiante, e o Alembic
    # assume DDL **não-transacional** no SQLite — nada foi desfeito, e a
    # `alembic_version` ficou na revisão anterior. Sem isto, a segunda tentativa
    # bate em "table subcategorias already exists" e o app não abre nunca mais.
    op.create_table(
        "subcategorias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["categoria_id"], ["categorias.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("categoria_id", "nome", name="uq_subcategoria_por_categoria"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_subcategorias_categoria_id", "subcategorias", ["categoria_id"], if_not_exists=True
    )
    op.create_index(
        "idx_subcategorias_categoria_nome",
        "subcategorias",
        ["categoria_id", "nome"],
        if_not_exists=True,
    )

    if "subcategoria_id" not in _colunas_de_produtos():
        op.add_column("produtos", sa.Column("subcategoria_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_produtos_subcategoria_id", "produtos", ["subcategoria_id"], if_not_exists=True
    )

    if "subcategoria" in _colunas_de_produtos():
        conexao = op.get_bind()
        # Uma linha nova por par (categoria, texto) que exista de verdade nos
        # produtos. `DISTINCT` porque a etiqueta se repetia em cada produto que
        # a usava — é justamente essa repetição que a tabela vem eliminar.
        conexao.execute(
            sa.text(
                "INSERT INTO subcategorias (nome, categoria_id) "
                "SELECT DISTINCT subcategoria, categoria_id FROM produtos "
                "WHERE subcategoria IS NOT NULL AND TRIM(subcategoria) <> ''"
            )
        )
        # O vínculo casa pelo par inteiro, e não só pelo nome: sem
        # `categoria_id` na junção, um "Podrão" de Lanches poderia apontar para
        # o "Podrão" de Porções e o produto trocaria de grupo sozinho.
        conexao.execute(
            sa.text(
                "UPDATE produtos SET subcategoria_id = ("
                "  SELECT s.id FROM subcategorias s"
                "   WHERE s.nome = produtos.subcategoria"
                "     AND s.categoria_id = produtos.categoria_id"
                ") WHERE subcategoria IS NOT NULL AND TRIM(subcategoria) <> ''"
            )
        )

        op.drop_index(INDICE_ANTIGO, table_name="produtos", if_exists=True)
        _dropar_coluna("produtos", "subcategoria")


def downgrade() -> None:
    """Downgrade schema."""
    if "subcategoria" not in _colunas_de_produtos():
        op.add_column("produtos", sa.Column("subcategoria", sa.String(80), nullable=True))

    conexao = op.get_bind()
    conexao.execute(
        sa.text(
            "UPDATE produtos SET subcategoria = ("
            "  SELECT s.nome FROM subcategorias s WHERE s.id = produtos.subcategoria_id"
            ") WHERE subcategoria_id IS NOT NULL"
        )
    )
    op.create_index(
        INDICE_ANTIGO, "produtos", ["categoria_id", "subcategoria"], if_not_exists=True
    )

    op.drop_index("ix_produtos_subcategoria_id", table_name="produtos", if_exists=True)
    _dropar_coluna("produtos", "subcategoria_id")

    op.drop_index("idx_subcategorias_categoria_nome", table_name="subcategorias", if_exists=True)
    op.drop_index("ix_subcategorias_categoria_id", table_name="subcategorias", if_exists=True)
    op.drop_table("subcategorias")
