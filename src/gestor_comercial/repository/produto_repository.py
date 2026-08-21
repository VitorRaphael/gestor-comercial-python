from sqlalchemy import exists, select

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

    def listar_por_categoria(self, categoria_id: int) -> list[Produto]:
        stmt = select(Produto).where(Produto.categoria_id == categoria_id).order_by(Produto.nome)
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
