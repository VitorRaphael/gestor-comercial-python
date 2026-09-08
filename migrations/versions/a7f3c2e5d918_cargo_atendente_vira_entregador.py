"""o cargo "Atendente" vira "Entregador"

Revision ID: a7f3c2e5d918
Revises: e5a1c9b73d24
Create Date: 2026-09-08 00:00:00.000001

Pedido do Vitor junto com o modal novo de Funcionários (§9.5): a grade de
cargos do cadastro passou a listar Gerente, Caixa, Garçom, Cozinha e
**Entregador**. "Atendente" saiu porque não descrevia função nenhuma do food
truck — todo mundo ali atende. Quem leva o pedido do delivery, sim.

`funcionarios.cargo` é `String`, não `Enum` de banco, então o schema não muda:
o que muda é o DADO. Sem esta migração, um funcionário já gravado como
"Atendente" continuaria aparecendo na lista, mas o modal de edição abriria com
**nenhum** cargo marcado (o texto não bate com card nenhum) e
`FuncionarioService._validar_cargo` recusaria o valor antigo se ele voltasse —
o cargo sumiria do cadastro na primeira edição, sem ninguém pedir.

Nenhum `Funcionario` do `seed.py` usa "Atendente" (o bootstrap só cria
Caixas), então na máquina do food truck esta migração provavelmente não vai
tocar em linha nenhuma. Ela existe para o caso de já haver um cadastro feito
à mão — e porque uma migração que não acha o que renomear custa um UPDATE
vazio, enquanto o cadastro perdido custa o operador ter que descobrir sozinho
o que aconteceu.

O `downgrade` desfaz na mesma medida: devolve "Entregador" para "Atendente".
Ele reverte cargos que possam ter sido criados JÁ como Entregador depois desta
migração — não há como distinguir os dois casos, e a alternativa (não desfazer
nada) deixaria o banco num estado que a versão anterior do código recusa.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a7f3c2e5d918'
down_revision: Union[str, Sequence[str], None] = 'e5a1c9b73d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CARGO_ANTIGO = "Atendente"
CARGO_NOVO = "Entregador"


def _renomear(de: str, para: str) -> None:
    op.execute(
        f"UPDATE funcionarios SET cargo = '{para}' WHERE cargo = '{de}'"  # noqa: S608
    )


def upgrade() -> None:
    _renomear(CARGO_ANTIGO, CARGO_NOVO)


def downgrade() -> None:
    _renomear(CARGO_NOVO, CARGO_ANTIGO)
