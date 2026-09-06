from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import StatusComanda
from gestor_comercial.repository.base import Base


class Comanda(Base):
    __tablename__ = "comandas"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[StatusComanda] = mapped_column(Enum(StatusComanda), default=StatusComanda.ABERTA, nullable=False)
    aberta_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Marca a transição ABERTA -> EM_CONFERENCIA (pré-conta emitida, itens
    # travados). `fechada_em` continua sendo só o instante da quitação final.
    em_conferencia_em: Mapped[datetime | None] = mapped_column(DateTime)
    # Decididos no momento do fechamento p/ conferência (§ Fechamento de
    # Comanda) e congelados aqui pelo mesmo motivo do preço do item: se o
    # percentual padrão mudar depois, a conta já emitida não pode mudar junto.
    taxa_servico_percentual: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    valor_desconto: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime)
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime)
    motivo_cancelamento: Mapped[str | None] = mapped_column(String(500))
    mesa_id: Mapped[int | None] = mapped_column(ForeignKey("mesas.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False, index=True)
    cancelado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    atendente_id: Mapped[int | None] = mapped_column(ForeignKey("funcionarios.id"), index=True)
    caixa_id: Mapped[int] = mapped_column(ForeignKey("caixas.id"), nullable=False, index=True)

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
