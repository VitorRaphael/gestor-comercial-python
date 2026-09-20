from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, text
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
    # A taxa em REAIS, gravada à parte no mesmo commit que congela o percentual
    # (§9.23). É o número que o fechamento do dia soma para dizer quanto da
    # venda foi taxa de serviço — sem ela, o relatório teria de refazer a conta
    # de cada comanda a partir dos itens. Zero enquanto a comanda está aberta,
    # zero se a taxa não foi cobrada, e volta a zero no `reabrir`.
    #
    # `server_default` além do `default`: o banco criado por `create_all` (a
    # suíte) tem que ter o mesmo schema do criado pela migração `e4b8c2a6d913`,
    # onde a coluna nasceu com `DEFAULT 0` — senão um INSERT por fora do ORM
    # passaria num e estouraria no outro.
    valor_taxa_servico: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    valor_desconto: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    # O repasse da taxa de serviço ao atendente (§9.25). O VALOR não tem coluna
    # própria: a comissão É a taxa (`valor_taxa_servico`), e uma segunda cópia
    # do mesmo número acabaria divergindo dele. O que o sistema não sabe deduzir
    # — e por isso é gravado — é se o dinheiro já foi para a mão do garçom.
    #
    # Só faz sentido com `atendente_id` e taxa maior que zero; sem um dos dois,
    # não há comissão e a tela de pagamento nem mostra o card.
    comissao_paga: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
    comissao_paga_em: Mapped[datetime | None] = mapped_column(DateTime)
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
