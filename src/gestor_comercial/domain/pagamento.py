from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import FormaPagamento
from gestor_comercial.repository.base import Base


class Pagamento(Base):
    __tablename__ = "pagamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    forma: Mapped[FormaPagamento] = mapped_column(Enum(FormaPagamento), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    troco: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    valor_quitado: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    registrado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id"), nullable=False)
    funcionario_consumo_id: Mapped[int | None] = mapped_column(ForeignKey("funcionarios.id"))

    comanda: Mapped["Comanda"] = relationship(back_populates="pagamentos")
    funcionario_consumo: Mapped["Funcionario | None"] = relationship(back_populates="pagamentos_consumo")
