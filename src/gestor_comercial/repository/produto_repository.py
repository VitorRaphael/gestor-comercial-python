from sqlalchemy import exists, select
from sqlalchemy.orm import selectinload

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.produto import Produto
from gestor_comercial.repository.base import Repository


class ProdutoRepository(Repository[Produto]):
    modelo = Produto

    def listar_todos(self) -> list[Produto]:
        return list(self.session.scalars(select(Produto).order_by(Produto.nome)))

    def listar_ativos(self) -> list[Produto]:
        stmt = select(Produto).where(Produto.ativo.is_(True)).order_by(Produto.nome)
        return list(self.session.scalars(stmt))

    def existe_com_categoria(self, categoria_id: int) -> bool:
        return bool(self.session.scalar(select(exists().where(Produto.categoria_id == categoria_id))))

    def listar_ativos_de_categoria_ativa(self) -> list[Produto]:
        """Produtos que o atendente pode vender: desativar a categoria some com os produtos dela."""
        stmt = (
            select(Produto)
            .join(Categoria, Produto.categoria_id == Categoria.id)
            .where(Produto.ativo.is_(True), Categoria.ativo.is_(True))
            .order_by(Produto.nome)
        )
        return list(self.session.scalars(stmt))

    def listar_para_lancamento(self) -> list[Produto]:
        """Como `listar_ativos_de_categoria_ativa`, mas com categoria e
        subcategoria já carregadas.

        Serve o modal "Adicionar item", que monta um instantâneo de cada produto
        (nome, preço, categoria, subcategoria) na abertura e depois não toca
        mais no SQLAlchemy — é o que mantém a digitação sem banco (§9.4).

        Os dois `selectinload` são o que o §9.4 tinha deixado registrado como
        possível e não feito: sem eles, montar o instantâneo do cardápio real
        custava 128 consultas (uma por categoria de cada produto), e a
        subcategoria dobraria a conta. Com eles são **3** — a dos produtos e uma
        por relação, independentemente do tamanho do cardápio.

        É um método separado, e não o `selectinload` colado no
        `listar_ativos_de_categoria_ativa`, porque as outras telas que chamam
        aquele não leem as relações: pagariam o carregamento sem usar.
        """
        stmt = (
            select(Produto)
            .join(Categoria, Produto.categoria_id == Categoria.id)
            .where(Produto.ativo.is_(True), Categoria.ativo.is_(True))
            .options(selectinload(Produto.categoria), selectinload(Produto.subcategoria))
            .order_by(Produto.nome)
        )
        return list(self.session.scalars(stmt))

    def existe_com_subcategoria(self, subcategoria_id: int) -> bool:
        return bool(
            self.session.scalar(
                select(exists().where(Produto.subcategoria_id == subcategoria_id))
            )
        )
