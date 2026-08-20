from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class Impressora(Base):
    __tablename__ = "impressoras"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)

    categorias: Mapped[list["Categoria"]] = relationship(back_populates="impressora")
