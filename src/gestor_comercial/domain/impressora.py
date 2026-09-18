"""Impressora térmica cadastrada no sistema (§3.12).

Guarda o nome que aparece na tela e os parâmetros de conexão. Cada tipo de
conexão usa um subconjunto das colunas — USB usa vendor_id/product_id, REDE
usa host/porta_rede — e por isso todas elas são anuláveis: quem garante que
o conjunto certo foi preenchido é o `cardapio_service`, não o banco.

`padrao` é a impressora que recebe o recibo do cliente, o fechamento de caixa
e os itens cujas categorias não têm impressora associada (o fallback do
roteamento). No máximo uma impressora fica com essa marca — invariante
mantida pelo service.

`colunas`, `bobina_mm` e `letra_grossa` são o formato do cupom (§9.22). As
colunas decidem a conta do `formatador_cupom` (divisores, preço encostado na
direita, régua); a bobina decide se essas colunas cabem na fonte normal ou se o
driver liga a condensada; a letra grossa liga a ênfase do ESC/POS no cupom
inteiro. A bobina é GRAVADA, e não deduzida das colunas: o gerente pode
escolher uma combinação que a dedução não devolveria.
"""

from sqlalchemy import Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.repository.base import Base

# Ficam no domain porque tanto o service (ao validar o cadastro) quanto o
# hardware (ao abrir o driver) precisam do mesmo número — e hardware/ não
# pode importar services/.
COLUNAS_PADRAO = 48
"""Largura da bobina de 80mm na fonte normal. A de 58mm são 32 colunas."""

COLUNAS_58MM = 32
"""Largura da bobina de 58mm na fonte normal — a sugestão do seletor (§9.19, §9.22)."""

BOBINA_58MM = 58
BOBINA_80MM = 80
BOBINAS_MM = (BOBINA_58MM, BOBINA_80MM)
BOBINA_PADRAO_MM = BOBINA_80MM

TETO_COLUNAS_58MM = 40
"""Até quantas colunas uma impressora sem bobina gravada é lida como de 58mm.

É a regra que o cartão do §9.19 usava para deduzir a bobina, e a que a migração
`b9d2f5a31c47` aplicou às impressoras que já existiam. 42 é o caso ambíguo, e
o §9.19 o pôs na de 80mm.
"""

BAUDRATE_PADRAO = 9600
PORTA_REDE_PADRAO = 9100


def bobina_mm_das_colunas(colunas: int) -> int:
    """A bobina de quem não a informou: a regra de antes de ela ser gravada."""
    return BOBINA_58MM if colunas <= TETO_COLUNAS_58MM else BOBINA_80MM


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
    bobina_mm: Mapped[int] = mapped_column(Integer, default=BOBINA_PADRAO_MM, nullable=False)
    letra_grossa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    padrao: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    categorias: Mapped[list["Categoria"]] = relationship(back_populates="impressora")
