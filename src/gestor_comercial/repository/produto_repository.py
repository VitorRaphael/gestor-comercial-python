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

    def listar_subcategorias(self, categoria_id: int) -> list[str]:
        """Os sub-modelos já digitados nesta categoria, sem repetir, em ordem.

        É o que alimenta as sugestões do cadastro de produto e as pílulas de
        filtro do Cardápio (§9.8). Um `DISTINCT` de duas colunas indexadas
        (`idx_produtos_categoria_sub`): o SQLite responde varrendo o índice, sem
        abrir linha de produto nenhuma — importa porque a tela de cadastro
        refaz esta consulta a cada troca de categoria no seletor.

        Produto sem sub-modelo (`NULL`, o estado da maioria do cardápio) não
        vira uma sugestão vazia: o `is_not(None)` o deixa de fora aqui, e quem
        precisa contá-los — a pílula "SEM SUB-MODELO" do Cardápio — descobre
        isso da lista de produtos que já tem na mão.

        Inclui produto desativado de propósito: quem desativou o "X Podrão do
        verão" ainda organiza o cardápio por "Podrão", e a sugestão sumir faria
        o gerente redigitar o nome — que é justamente a divergência de grafia
        que a sugestão existe para evitar.
        """
        stmt = (
            select(Produto.subcategoria)
            .where(Produto.categoria_id == categoria_id, Produto.subcategoria.is_not(None))
            .distinct()
            .order_by(Produto.subcategoria)
        )
        return [subcategoria for subcategoria in self.session.scalars(stmt)]
