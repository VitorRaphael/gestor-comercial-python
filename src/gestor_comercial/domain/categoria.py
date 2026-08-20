from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    impressora_id: Mapped[int | None] = mapped_column(ForeignKey("impressoras.id"))

    impressora: Mapped["Impressora | None"] = relationship(back_populates="categorias")
    produtos: Mapped[list["Produto"]] = relationship(back_populates="categoria")
