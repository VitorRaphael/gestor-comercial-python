from sqlalchemy import exists, select

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.repository.base import Repository


class ItemComandaRepository(Repository[ItemComanda]):
    modelo = ItemComanda

    def listar_cancelados_por_caixa(self, caixa_id: int) -> list[ItemComanda]:
        """Itens cancelados de qualquer comanda deste caixa, na ordem em que foram cancelados.

        Usado pela auditoria de cancelamentos do fechamento (§3.9.2): junta com
        `Comanda` porque `ItemComanda` não guarda `caixa_id` diretamente — quem
        pertence a um caixa é a comanda, o item só herda isso por tabela.
        """
        stmt = (
            select(ItemComanda)
            .join(Comanda, ItemComanda.comanda_id == Comanda.id)
            .where(Comanda.caixa_id == caixa_id, ItemComanda.cancelado.is_(True))
            .order_by(ItemComanda.cancelado_em)
        )
        return list(self.session.scalars(stmt))

    def listar_vendidos_por_caixa(self, caixa_id: int) -> list[ItemComanda]:
        """Itens não cancelados de qualquer comanda deste caixa, na ordem de lançamento.

        Espelha `listar_cancelados_por_caixa`: mesmo join com `Comanda` porque
        `ItemComanda` não guarda `caixa_id` diretamente. Usado pela seção
        "ITENS VENDIDOS NO TURNO" do fechamento — só o que efetivamente vendeu,
        por isso o filtro oposto ao de cancelados.
        """
        stmt = (
            select(ItemComanda)
            .join(Comanda, ItemComanda.comanda_id == Comanda.id)
            .where(Comanda.caixa_id == caixa_id, ItemComanda.cancelado.is_(False))
            .order_by(ItemComanda.id)
        )
        return list(self.session.scalars(stmt))

    def listar_por_comanda(self, comanda_id: int) -> list[ItemComanda]:
        stmt = select(ItemComanda).where(ItemComanda.comanda_id == comanda_id).order_by(ItemComanda.id)
        return list(self.session.scalars(stmt))

    def listar_nao_impressos_por_comanda(self, comanda_id: int) -> list[ItemComanda]:
        """Itens que ainda não foram pra produção — a via de acréscimo (§3.12).

        A ordem é a de lançamento (id crescente) porque o cupom da cozinha
        precisa sair na mesma sequência em que o atendente digitou.
        """
        stmt = (
            select(ItemComanda)
            .where(
                ItemComanda.comanda_id == comanda_id,
                ItemComanda.cancelado.is_(False),
                ItemComanda.impresso_em.is_(None),
            )
            .order_by(ItemComanda.id)
        )
        return list(self.session.scalars(stmt))

    def existe_na_comanda(self, comanda_id: int) -> bool:
        return bool(self.session.scalar(select(exists().where(ItemComanda.comanda_id == comanda_id))))

    def existe_com_produto(self, produto_id: int) -> bool:
        return bool(self.session.scalar(select(exists().where(ItemComanda.produto_id == produto_id))))
