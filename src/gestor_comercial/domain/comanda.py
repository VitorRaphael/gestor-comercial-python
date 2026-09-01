from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import StatusComanda
from gestor_comercial.repository.base import Base


class Comanda(Base):
    __tablename__ = "comandas"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[StatusComanda] = mapped_column(Enum(StatusComanda), default=StatusComanda.ABERTA, nullable=False)
    aberta_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime)
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime)
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(500))
    mesa_id: Mapped[int | None] = mapped_column(ForeignKey("mesas.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
    cancelado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    atendente_id: Mapped[int | None] = mapped_column(ForeignKey("funcionarios.id"))
    caixa_id: Mapped[int] = mapped_column(ForeignKey("caixas.id"), nullable=False)

    mesa: Mapped["Mesa | None"] = relationship(back_populates="comandas")
    usuario: Mapped["Usuario"] = relationship(
        foreign_keys=[usuario_id], back_populates="comandas"
    )
    cancelado_por: Mapped["Usuario | None"] = relationship(
        foreign_keys=[cancelado_por_id], back_populates="comandas_canceladas"
    )
    atendente: Mapped["Funcionario | None"] = relationship(
        foreign_keys=[atendente_id], back_populates="comandas_atendidas"
    )
    caixa: Mapped["Caixa"] = relationship(back_populates="comandas")
    itens: Mapped[list["ItemComanda"]] = relationship(back_populates="comanda")
    pagamentos: Mapped[list["Pagamento"]] = relationship(back_populates="comanda")
