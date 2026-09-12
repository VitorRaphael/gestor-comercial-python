from sqlalchemy import exists, or_, select
from sqlalchemy.orm import selectinload

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.produto import Produto
from gestor_comercial.domain.subcategoria import Subcategoria
from gestor_comercial.repository.base import Repository


def _vendavel():
    """As condições de "este produto pode ser lançado numa comanda" (§9.13).

    Uma função, e não a mesma lista de filtros copiada nas duas consultas de
    venda: `listar_ativos_de_categoria_ativa` e `listar_para_lancamento`
    respondem a mesma pergunta para telas diferentes, e no dia em que as duas
    divergissem o produto apareceria na busca de uma tela e não na da outra —
    que é como o atendente conclui que o cardápio "sumiu".

    São quatro condições, e cada uma é um jeito diferente de o produto estar
    fora do balcão:

    * `produto.ativo` — "acabou o pão" (o gesto de todo dia);
    * `produto.arquivado` — excluído em cascata, mas com histórico de venda a
      preservar (§9.13);
    * `categoria.ativo` — a regra que já existia;
    * `subcategoria.ativo` — a mesma regra, um nível abaixo. Produto SEM
      subdivisão passa: `NULL` aqui é o estado normal de quem ainda não foi
      classificado, e não pode custar a venda dele.
    """
    return (
        Produto.ativo.is_(True),
        Produto.arquivado.is_(False),
        Categoria.ativo.is_(True),
        or_(Produto.subcategoria_id.is_(None), Subcategoria.ativo.is_(True)),
    )


class ProdutoRepository(Repository[Produto]):
    modelo = Produto

    def listar_todos(self) -> list[Produto]:
        return list(self.session.scalars(select(Produto).order_by(Produto.nome)))

    def listar_do_cardapio(self) -> list[Produto]:
        """O catálogo que a tela de Cardápio administra — sem os arquivados.

        Separado de `listar_todos` de propósito: o arquivado tem que continuar
        alcançável por quem olha para o PASSADO (o ranking mensal casa a foto
        do produto pelo nome, `CaixaService._com_imagem_atual`), e sumir de
        quem olha para o cardápio de hoje. Uma consulta só filtrando para os
        dois tiraria a foto de um item que a venda dele já registrou.
        """
        stmt = select(Produto).where(Produto.arquivado.is_(False)).order_by(Produto.nome)
        return list(self.session.scalars(stmt))

    def listar_ativos(self) -> list[Produto]:
        stmt = select(Produto).where(Produto.ativo.is_(True)).order_by(Produto.nome)
        return list(self.session.scalars(stmt))

    def existe_com_categoria(self, categoria_id: int) -> bool:
        return bool(self.session.scalar(select(exists().where(Produto.categoria_id == categoria_id))))

    def listar_ativos_de_categoria_ativa(self) -> list[Produto]:
        """Produtos que o atendente pode vender (ver `_vendavel`).

        O `outerjoin` na subcategoria, e não `join`: produto sem subdivisão é a
        maioria do cardápio em organização, e um `INNER JOIN` o teria apagado
        do balcão inteiro sem ninguém pedir isso.
        """
        stmt = (
            select(Produto)
            .join(Categoria, Produto.categoria_id == Categoria.id)
            .outerjoin(Subcategoria, Produto.subcategoria_id == Subcategoria.id)
            .where(*_vendavel())
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
            .outerjoin(Subcategoria, Produto.subcategoria_id == Subcategoria.id)
            .where(*_vendavel())
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

    def listar_da_subcategoria(self, subcategoria_id: int) -> list[Produto]:
        """Os produtos de uma subdivisão — quem a exclusão em cascata vai pegar.

        Traz os arquivados junto (sem filtro de `arquivado`): eles continuam
        apontando para a subcategoria, e o `ondelete="SET NULL"` os soltaria de
        qualquer jeito. A cascata precisa vê-los para não tentar apagar duas
        vezes o que já está marcado.
        """
        stmt = (
            select(Produto)
            .where(Produto.subcategoria_id == subcategoria_id)
            .order_by(Produto.nome)
        )
        return list(self.session.scalars(stmt))
