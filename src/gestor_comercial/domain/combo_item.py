from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class ComboItem(Base):
    __tablename__ = "combo_itens"

    id: Mapped[int] = mapped_column(primary_key=True)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    combo_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)

    combo: Mapped["Produto"] = relationship(foreign_keys=[combo_id], back_populates="componentes")
    produto: Mapped["Produto"] = relationship(foreign_keys=[produto_id])
