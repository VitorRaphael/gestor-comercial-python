from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class QuitacaoConsumo(Base):
    __tablename__ = "quitacoes_consumo"

    id: Mapped[int] = mapped_column(primary_key=True)
    valor_quitado: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quitado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    funcionario_id: Mapped[int] = mapped_column(ForeignKey("funcionarios.id"), nullable=False)
    autorizado_por_id: Mapped[int] = mapped_column(ForeignKey("funcionarios.id"), nullable=False)

    funcionario: Mapped["Funcionario"] = relationship(
        foreign_keys=[funcionario_id], back_populates="quitacoes"
    )
    autorizado_por: Mapped["Funcionario"] = relationship(foreign_keys=[autorizado_por_id])
