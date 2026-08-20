from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class ItemComanda(Base):
    __tablename__ = "itens_comanda"

    id: Mapped[int] = mapped_column(primary_key=True)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_unit_congelado: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    observacao: Mapped[str | None] = mapped_column(String(500))
    cancelado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(500))
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)

    comanda: Mapped["Comanda"] = relationship(back_populates="itens")
    produto: Mapped["Produto"] = relationship(back_populates="itens_comanda")
