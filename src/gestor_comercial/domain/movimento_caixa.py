from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import TipoMovimento
from gestor_comercial.repository.base import Base


class MovimentoCaixa(Base):
    __tablename__ = "movimentos_caixa"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoMovimento] = mapped_column(Enum(TipoMovimento), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(500))
    registrado_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    caixa_id: Mapped[int] = mapped_column(ForeignKey("caixas.id"), nullable=False)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)

    caixa: Mapped["Caixa"] = relationship(back_populates="movimentos")
    usuario: Mapped["Usuario"] = relationship(back_populates="movimentos_caixa")
