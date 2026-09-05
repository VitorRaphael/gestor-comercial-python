from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class Funcionario(Base):
    """Colaborador de atendimento (garçom, cozinha, ...), sem login (§3.11).
    Só serve para vincular quem atendeu a comanda e para registrar consumo
    interno. Não confundir com `Usuario` (login/PIN)."""

    __tablename__ = "funcionarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(60))
    telefone: Mapped[str | None] = mapped_column(String(30))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    saldo_devedor: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    turno_horario: Mapped[str | None] = mapped_column(String(60))

    comandas_atendidas: Mapped[list["Comanda"]] = relationship(back_populates="atendente")
    quitacoes: Mapped[list["QuitacaoConsumo"]] = relationship(
        foreign_keys="QuitacaoConsumo.funcionario_id", back_populates="funcionario"
    )
    pagamentos_consumo: Mapped[list["Pagamento"]] = relationship(back_populates="funcionario_consumo")
