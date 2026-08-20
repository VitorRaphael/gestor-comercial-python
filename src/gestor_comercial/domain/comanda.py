from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import StatusComanda
from gestor_comercial.repository.base import Base


class Comanda(Base):
    __tablename__ = "comandas"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[StatusComanda] = mapped_column(Enum(StatusComanda), default=StatusComanda.ABERTA, nullable=False)
    aberta_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime)
    mesa_id: Mapped[int | None] = mapped_column(ForeignKey("mesas.id"))
    funcionario_id: Mapped[int] = mapped_column(ForeignKey("funcionarios.id"), nullable=False)
    caixa_id: Mapped[int] = mapped_column(ForeignKey("caixas.id"), nullable=False)

    mesa: Mapped["Mesa | None"] = relationship(back_populates="comandas")
    funcionario: Mapped["Funcionario"] = relationship(back_populates="comandas")
    caixa: Mapped["Caixa"] = relationship(back_populates="comandas")
    itens: Mapped[list["ItemComanda"]] = relationship(back_populates="comanda")
    pagamentos: Mapped[list["Pagamento"]] = relationship(back_populates="comanda")
