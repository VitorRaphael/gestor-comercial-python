from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String
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
    # Sub-modelo (§9.8): camada PURAMENTE organizacional dentro da categoria —
    # "Lanches" se subdivide em "Artesanal", "Podrão", "Combos". É texto livre e
    # não uma tabela própria de propósito: sub-modelo não tem impressora, não
    # tem status e não tem regra. Ele agrupa o catálogo para o gerente achar o
    # item na hora de editar e para o operador diferenciar variações na hora de
    # lançar. Uma FK exigiria CRUD, tela e tratamento de órfão para não guardar
    # dado nenhum além do próprio nome.
    #
    # NUNCA entra no roteamento de impressão: quem decide a impressora é
    # `produto.categoria.impressora`, e só (ver `impressao_service`
    # `_destino_do_item`). A regra está trancada por
    # `tests/unit/test_impressao_service.py`.
    #
    # `String(80)` é o mesmo teto de `Categoria.nome` — nomeia a mesma coisa,
    # um grupo do cardápio. `NULL` é o estado normal: produto sem sub-modelo é
    # a maioria do cardápio, e continua funcionando como sempre funcionou.
    subcategoria: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # O índice é COMPOSTO porque toda consulta de sub-modelo acontece DENTRO de
    # uma categoria (as sugestões do cadastro, as pílulas de filtro do
    # Cardápio). `categoria_id` sozinho já tem o índice do `index=True` acima;
    # este acrescenta a segunda coluna para o SQLite responder "quais
    # sub-modelos existem em Lanches" varrendo o índice, sem tocar na tabela.
    __table_args__ = (Index("idx_produtos_categoria_sub", "categoria_id", "subcategoria"),)

    categoria: Mapped["Categoria"] = relationship(back_populates="produtos")
    itens_comanda: Mapped[list["ItemComanda"]] = relationship(back_populates="produto")
    componentes: Mapped[list["ComboItem"]] = relationship(
        foreign_keys="ComboItem.combo_id", back_populates="combo"
    )
