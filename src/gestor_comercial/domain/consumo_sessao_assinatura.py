from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class ConsumoSessaoAssinatura(Base):
    """A assinatura manuscrita de uma retirada de consumo interno.

    Uma linha por `Pagamento` CONSUMO_INTERNO: a retirada em si continua sendo o
    pagamento (é ele que entra no caixa e na dívida do funcionário); esta tabela
    só guarda a prova de quem pegou. O traço fica como JSON de coordenadas
    (`services/assinatura.py`), não como imagem — algumas centenas de bytes por
    assinatura, redesenhados com `QPainterPath` na hora de mostrar.

    Nada aqui é apagado na baixa do consumo: a sessão quitada vira histórico
    pelo `valor_quitado` do pagamento, com o traço intacto.
    """

    __tablename__ = "consumo_sessao_assinaturas"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_funcionario: Mapped[int] = mapped_column(ForeignKey("funcionarios.id"), nullable=False, index=True)
    id_sessao: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    data_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valor_total_sessao: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    traco_json: Mapped[str] = mapped_column(Text, nullable=False)
    id_pagamento: Mapped[int] = mapped_column(ForeignKey("pagamentos.id"), nullable=False, unique=True)

    pagamento: Mapped["Pagamento"] = relationship(back_populates="assinatura")
