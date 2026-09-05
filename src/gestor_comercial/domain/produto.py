from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class Produto(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    preco: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    custo: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(500))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_combo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False)
    imagem_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    categoria: Mapped["Categoria"] = relationship(back_populates="produtos")
    itens_comanda: Mapped[list["ItemComanda"]] = relationship(back_populates="produto")
    componentes: Mapped[list["ComboItem"]] = relationship(
        foreign_keys="ComboItem.combo_id", back_populates="combo"
    )
