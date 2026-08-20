from sqlalchemy import Enum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import StatusMesa
from gestor_comercial.repository.base import Base


class Mesa(Base):
    __tablename__ = "mesas"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    status: Mapped[StatusMesa] = mapped_column(Enum(StatusMesa), default=StatusMesa.LIVRE, nullable=False)

    comandas: Mapped[list["Comanda"]] = relationship(back_populates="mesa")
