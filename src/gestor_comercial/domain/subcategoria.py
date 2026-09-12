from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
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

    Ganhou `ativo` no §9.13, e isto **reverte a decisão escrita aqui no §9.9**
    ("subcategoria é só organização, desativar não significaria nada"). O que
    mudou foi o significado pedido: desativar uma subcategoria agora é uma
    REGRA DE VENDA, igual à da categoria — os produtos dela somem do balcão (do
    "Adicionar item" e de qualquer listagem de lançamento) sem sair do cadastro
    e sem perder histórico. É o gesto de "hoje não tem podrão" sem precisar
    desativar item por item.

    Quem aplica a regra é a consulta de lançamento
    (`ProdutoRepository.listar_para_lancamento`), no mesmo lugar e da mesma
    forma que `Categoria.ativo` — duas regras iguais escritas em dois lugares
    diferentes divergiriam na primeira manutenção.

    O que **não** mudou: a impressora continua saindo de
    `produto.categoria.impressora` e só (§9.8), então desativar uma subdivisão
    não reconfigura bobina nenhuma — ela apenas deixa de ter item para mandar.

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
    # `default=True` e `NOT NULL`, como em `Categoria.ativo`: subdivisão nasce
    # vendendo, e a migração `a3e6b91c4d05` liga as que já existem — um `NULL`
    # aqui sumiria com produto do balcão sem ninguém ter pedido isso.
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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
