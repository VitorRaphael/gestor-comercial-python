from decimal import Decimal

from sqlalchemy import Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import StatusCaixa
from gestor_comercial.repository.base import Base


class Caixa(Base):
    __tablename__ = "caixas"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[StatusCaixa] = mapped_column(Enum(StatusCaixa), default=StatusCaixa.ABERTO, nullable=False)
    valor_abertura: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    valor_contado: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    observacao_fechamento: Mapped[str | None] = mapped_column(String(500))

    comandas: Mapped[list["Comanda"]] = relationship(back_populates="caixa")
    movimentos: Mapped[list["MovimentoCaixa"]] = relationship(back_populates="caixa")
