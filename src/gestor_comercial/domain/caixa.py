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
    valor_contado_dinheiro: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    valor_contado_maquininha: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    observacao_fechamento: Mapped[str | None] = mapped_column(String(500))
    aberto_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime)
    # Ordem do fechamento no dia CIVIL de `fechado_em` (não de `aberto_em`), para
    # um turno que vira a madrugada contar como fechamento do dia em que a
    # gaveta foi realmente conferida. Só ganha valor em `CaixaService.fechar`,
    # e nunca muda depois — fechar de novo o mesmo caixa já é bloqueado, então
    # este número é imutável assim que gravado (§ histórico auditável).
    numero_sequencial_dia: Mapped[int | None] = mapped_column(Integer)
    aberto_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fechado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    # Snapshot do mix de vendas do turno, congelado em `CaixaService.fechar` a
    # partir de `resumo_vendas` — JSON de {produto_nome, quantidade,
    # valor_unitario, valor_total}. Existe para o Dashboard Mensal poder somar
    # o ranking de produtos lendo só a tabela de fechamentos, sem tocar
    # `item_comanda` de novo: numa máquina fraca, ler N linhas de texto já
    # pronto é mais barato do que re-agregar item por item todo mês. NULL em
    # caixa fechado antes desta coluna existir — não há como voltar no tempo
    # e recalcular o mix de um turno já encerrado.
    resumo_produtos_json: Mapped[str | None] = mapped_column(String)

    comandas: Mapped[list["Comanda"]] = relationship(back_populates="caixa")
    movimentos: Mapped[list["MovimentoCaixa"]] = relationship(back_populates="caixa")
    aberto_por: Mapped["Usuario | None"] = relationship(
        foreign_keys=[aberto_por_id], back_populates="caixas_abertos"
    )
    fechado_por: Mapped["Usuario | None"] = relationship(
        foreign_keys=[fechado_por_id], back_populates="caixas_fechados"
    )
