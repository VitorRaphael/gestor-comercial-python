from decimal import Decimal

from sqlalchemy import Boolean, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import PerfilFuncionario
from gestor_comercial.repository.base import Base


class Funcionario(Base):
    __tablename__ = "funcionarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    perfil: Mapped[PerfilFuncionario] = mapped_column(Enum(PerfilFuncionario), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    saldo_devedor: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)

    comandas: Mapped[list["Comanda"]] = relationship(
        foreign_keys="Comanda.funcionario_id", back_populates="funcionario"
    )
    quitacoes: Mapped[list["QuitacaoConsumo"]] = relationship(
        foreign_keys="QuitacaoConsumo.funcionario_id", back_populates="funcionario"
    )
    movimentos_caixa: Mapped[list["MovimentoCaixa"]] = relationship(back_populates="funcionario")
    pagamentos_consumo: Mapped[list["Pagamento"]] = relationship(back_populates="funcionario_consumo")
