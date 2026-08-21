from collections.abc import Sequence

from sqlalchemy import select

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import FormaPagamento
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.repository.base import Repository


class PagamentoRepository(Repository[Pagamento]):
    modelo = Pagamento

    def listar_por_comanda(self, comanda_id: int) -> list[Pagamento]:
        stmt = select(Pagamento).where(Pagamento.comanda_id == comanda_id).order_by(Pagamento.id)
        return list(self.session.scalars(stmt))

    def listar_consumos_do_funcionario(self, funcionario_id: int) -> list[Pagamento]:
        """Consumos internos do funcionário, do mais antigo pro mais novo.

        A ordem importa: a quitação abate FIFO (§3.8), então esta lista é a
        fila de dívida na ordem em que ela vai ser paga.
        """
        stmt = (
            select(Pagamento)
            .where(
                Pagamento.forma == FormaPagamento.CONSUMO_INTERNO,
                Pagamento.funcionario_consumo_id == funcionario_id,
            )
            .order_by(Pagamento.registrado_em, Pagamento.id)
        )
        return list(self.session.scalars(stmt))

    def listar_por_caixa(
        self, caixa_id: int, formas: Sequence[FormaPagamento] | None = None
    ) -> list[Pagamento]:
        """Pagamentos do caixa, alcançados pela comanda a que pertencem.

        O Java filtrava por `dataHora >= caixa.dataAbertura`, o que erra se
        dois caixas se sobrepõem. Aqui o vínculo é explícito via
        `Comanda.caixa_id`, então não há ambiguidade.
        """
        stmt = (
            select(Pagamento)
            .join(Comanda, Pagamento.comanda_id == Comanda.id)
            .where(Comanda.caixa_id == caixa_id)
        )
        if formas is not None:
            stmt = stmt.where(Pagamento.forma.in_(list(formas)))
        return list(self.session.scalars(stmt.order_by(Pagamento.id)))
