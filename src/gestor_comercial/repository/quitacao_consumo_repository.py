from sqlalchemy import select

from gestor_comercial.domain.quitacao_consumo import QuitacaoConsumo
from gestor_comercial.repository.base import Repository


class QuitacaoConsumoRepository(Repository[QuitacaoConsumo]):
    modelo = QuitacaoConsumo

    def listar_por_funcionario(self, funcionario_id: int) -> list[QuitacaoConsumo]:
        stmt = (
            select(QuitacaoConsumo)
            .where(QuitacaoConsumo.funcionario_id == funcionario_id)
            .order_by(QuitacaoConsumo.quitado_em.desc(), QuitacaoConsumo.id.desc())
        )
        return list(self.session.scalars(stmt))
