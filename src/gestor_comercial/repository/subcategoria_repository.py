from sqlalchemy import exists, func, select

from gestor_comercial.domain.produto import Produto
from gestor_comercial.domain.subcategoria import Subcategoria
from gestor_comercial.repository.base import Repository


class SubcategoriaRepository(Repository[Subcategoria]):
    modelo = Subcategoria

    def listar_todos(self) -> list[Subcategoria]:
        return list(
            self.session.scalars(
                select(Subcategoria).order_by(Subcategoria.categoria_id, Subcategoria.nome)
            )
        )

    def listar_da_categoria(self, categoria_id: int) -> list[Subcategoria]:
        """As subdivisões de uma categoria, em ordem alfabética.

        É a consulta que monta a árvore do Cardápio e o seletor do cadastro de
        produto, e sai do índice `idx_subcategorias_categoria_nome` — as duas
        colunas dele são exatamente o filtro e a ordenação.
        """
        stmt = (
            select(Subcategoria)
            .where(Subcategoria.categoria_id == categoria_id)
            .order_by(Subcategoria.nome)
        )
        return list(self.session.scalars(stmt))

    def existe_com_produto(self, subcategoria_id: int) -> bool:
        return bool(
            self.session.scalar(
                select(exists().where(Produto.subcategoria_id == subcategoria_id))
            )
        )

    def contar_produtos(self) -> dict[int, int]:
        """Quantos produtos há em cada subcategoria, numa consulta só.

        A árvore mostra a contagem ao lado de cada subdivisão das 15 categorias.
        Perguntar uma por uma seriam 13 consultas a cada refresh da tela — é o
        N+1 do §3.6 nascendo numa tela nova, e o `GROUP BY` o evita antes de
        existir.

        Subcategoria sem produto nenhum não aparece no resultado (é um `GROUP
        BY` sobre `produtos`), e quem lê trata a ausência como zero — que é a
        contagem certa e o estado normal de uma subdivisão recém-criada.
        """
        stmt = (
            select(Produto.subcategoria_id, func.count(Produto.id))
            .where(Produto.subcategoria_id.is_not(None))
            .group_by(Produto.subcategoria_id)
        )
        return {sub_id: total for sub_id, total in self.session.execute(stmt)}
