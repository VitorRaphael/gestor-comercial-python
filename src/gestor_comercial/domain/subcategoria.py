from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.repository.base import Base


class Subcategoria(Base):
    """A subdivisão de uma categoria do cardápio — "Lanches" → "Podrão" (§9.9).

    Nasceu como uma COLUNA DE TEXTO no produto (§9.8) e virou entidade quando o
    Vitor pediu a tela de cadastro: texto no produto não permite criar uma
    subcategoria **vazia**, esperando os itens. E não era só isso —
    renomear "Podrão" exigiria varrer e reescrever todo produto que carregasse
    aquela string, e uma reescrita em massa que falha no meio deixa metade do
    cardápio num grupo e metade no outro.

    Não tem `ativo`, ao contrário de `Categoria`, e é de propósito: categoria
    desativada some do balcão junto com os produtos dela (é uma regra de
    venda), enquanto subcategoria é só organização de catálogo — desativar não
    significaria nada que excluir já não signifique. Excluir é seguro porque os
    produtos apenas voltam a ficar sem subcategoria (ver `ondelete="SET NULL"`
    em `Produto.subcategoria_id`), sem perder venda nem histórico.

    O nome é único DENTRO da categoria, e não no cardápio inteiro: "Podrão" em
    Lanches e "Podrão" em Porções são duas subdivisões independentes, cada uma
    com a impressora da categoria dela.
    """

    __tablename__ = "subcategorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categorias.id"), nullable=False, index=True
    )

    __table_args__ = (
        # O banco também recusa o par repetido, e não só o service: a checagem
        # do service compara ignorando acento e caixa (ver
        # `CardapioService._exigir_nome_de_subcategoria_livre`), o que é mais
        # rígido do que isto — mas quem grava sem passar pelo service (uma
        # migração, um script) não pode conseguir criar o par exato duas vezes.
        UniqueConstraint("categoria_id", "nome", name="uq_subcategoria_por_categoria"),
        Index("idx_subcategorias_categoria_nome", "categoria_id", "nome"),
    )

    categoria: Mapped["Categoria"] = relationship(back_populates="subcategorias")
    produtos: Mapped[list["Produto"]] = relationship(back_populates="subcategoria")
