"""Impressora térmica cadastrada no sistema (§3.12).

Guarda o nome que aparece na tela e os parâmetros de conexão. Cada tipo de
conexão usa um subconjunto das colunas — USB usa vendor_id/product_id, REDE
usa host/porta_rede — e por isso todas elas são anuláveis: quem garante que
o conjunto certo foi preenchido é o `cardapio_service`, não o banco.

`padrao` é a impressora que recebe o recibo do cliente, o fechamento de caixa
e os itens cujas categorias não têm impressora associada (o fallback do
roteamento). No máximo uma impressora fica com essa marca — invariante
mantida pelo service.
"""

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.repository.base import Base

# Ficam no domain porque tanto o service (ao validar o cadastro) quanto o
# hardware (ao abrir o driver) precisam do mesmo número — e hardware/ não
# pode importar services/.
COLUNAS_PADRAO = 48
"""Largura da bobina de 80mm. A de 58mm são 32 colunas."""

BAUDRATE_PADRAO = 9600
PORTA_REDE_PADRAO = 9100


class Impressora(Base):
    __tablename__ = "impressoras"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    tipo_conexao: Mapped[TipoConexaoImpressora] = mapped_column(
        Enum(TipoConexaoImpressora), default=TipoConexaoImpressora.ARQUIVO, nullable=False
    )
    vendor_id: Mapped[str | None] = mapped_column(String(10))
    product_id: Mapped[str | None] = mapped_column(String(10))
    porta_serial: Mapped[str | None] = mapped_column(String(60))
    baudrate: Mapped[int | None] = mapped_column(Integer)
    host: Mapped[str | None] = mapped_column(String(60))
    porta_rede: Mapped[int | None] = mapped_column(Integer)
    nome_fila: Mapped[str | None] = mapped_column(String(120))
    caminho_arquivo: Mapped[str | None] = mapped_column(String(255))
    colunas: Mapped[int] = mapped_column(Integer, default=COLUNAS_PADRAO, nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    padrao: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    categorias: Mapped[list["Categoria"]] = relationship(back_populates="impressora")
