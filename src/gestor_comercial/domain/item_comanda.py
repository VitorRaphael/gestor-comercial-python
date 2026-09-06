from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class ItemComanda(Base):
    __tablename__ = "itens_comanda"

    id: Mapped[int] = mapped_column(primary_key=True)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_unit_congelado: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    observacao: Mapped[str | None] = mapped_column(String(500))
    cancelado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime)
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(500))
    # NULL = a cozinha ainda não recebeu este item. É o que separa a via de
    # acréscimo (§3.12), que imprime só o que é novo, da 2ª via, que repete
    # a comanda inteira e não mexe nesta coluna.
    impresso_em: Mapped[datetime | None] = mapped_column(DateTime)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id"), nullable=False, index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False, index=True)
    cancelado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)

    comanda: Mapped["Comanda"] = relationship(back_populates="itens")
    produto: Mapped["Produto"] = relationship(back_populates="itens_comanda")
    cancelado_por: Mapped["Usuario | None"] = relationship(
        foreign_keys=[cancelado_por_id], back_populates="itens_cancelados"
    )
