from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class Produto(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    preco: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    custo: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(500))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_combo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"), nullable=False, index=True)
    imagem_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # A subdivisão do produto dentro da categoria (§9.9). `NULL` é o estado
    # normal e legítimo: produto ainda não classificado aparece no grupo "Sem
    # subcategoria" do Cardápio, que é a fila de trabalho de quem organiza.
    #
    # `ondelete="SET NULL"`: apagar a subcategoria devolve os produtos ao estado
    # de não classificados, em vez de levar item de cardápio junto. Excluir uma
    # ETIQUETA nunca pode apagar o que ela etiquetava — e essa é justamente a
    # diferença para `categoria_id`, que é `NOT NULL` porque produto sem
    # categoria não tem impressora e não sairia em cupom nenhum.
    #
    # NUNCA entra no roteamento de impressão: quem decide a impressora é
    # `produto.categoria.impressora`, e só (ver `impressao_service`
    # `_destino_do_item`). A regra está trancada por
    # `tests/unit/test_impressao_service.py`.
    subcategoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("subcategorias.id", ondelete="SET NULL"), nullable=True, index=True
    )

    categoria: Mapped["Categoria"] = relationship(back_populates="produtos")
    subcategoria: Mapped["Subcategoria | None"] = relationship(back_populates="produtos")
    itens_comanda: Mapped[list["ItemComanda"]] = relationship(back_populates="produto")
    componentes: Mapped[list["ComboItem"]] = relationship(
        foreign_keys="ComboItem.combo_id", back_populates="combo"
    )
