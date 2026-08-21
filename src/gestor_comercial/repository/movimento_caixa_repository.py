from sqlalchemy import select

from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.repository.base import Repository


class MovimentoCaixaRepository(Repository[MovimentoCaixa]):
    modelo = MovimentoCaixa

    def listar_por_caixa(self, caixa_id: int) -> list[MovimentoCaixa]:
        stmt = (
            select(MovimentoCaixa)
            .where(MovimentoCaixa.caixa_id == caixa_id)
            .order_by(MovimentoCaixa.registrado_em, MovimentoCaixa.id)
        )
        return list(self.session.scalars(stmt))
