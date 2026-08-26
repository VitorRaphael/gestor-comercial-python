from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
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
    aberto_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime)
    # Ordem do fechamento no dia CIVIL de `fechado_em` (não de `aberto_em`), para
    # um turno que vira a madrugada contar como fechamento do dia em que a
    # gaveta foi realmente conferida. Só ganha valor em `CaixaService.fechar`,
    # e nunca muda depois — fechar de novo o mesmo caixa já é bloqueado, então
    # este número é imutável assim que gravado (§ histórico auditável).
    numero_sequencial_dia: Mapped[int | None] = mapped_column(Integer)
    aberto_por_id: Mapped[int | None] = mapped_column(ForeignKey("funcionarios.id"))
    fechado_por_id: Mapped[int | None] = mapped_column(ForeignKey("funcionarios.id"))

    comandas: Mapped[list["Comanda"]] = relationship(back_populates="caixa")
    movimentos: Mapped[list["MovimentoCaixa"]] = relationship(back_populates="caixa")
    aberto_por: Mapped["Funcionario | None"] = relationship(
        foreign_keys=[aberto_por_id], back_populates="caixas_abertos"
    )
    fechado_por: Mapped["Funcionario | None"] = relationship(
        foreign_keys=[fechado_por_id], back_populates="caixas_fechados"
    )
