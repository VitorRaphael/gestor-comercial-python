from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import StatusComanda
from gestor_comercial.repository.base import Repository


class ComandaRepository(Repository[Comanda]):
    modelo = Comanda

    def buscar_aberta_por_mesa(self, mesa_id: int) -> Comanda | None:
        """A comanda "em uso" da mesa: ainda lançando itens, ou já em conferência.

        Inclui EM_CONFERENCIA de propósito — sem isso, reabrir a tela de uma
        mesa cuja pré-conta já foi emitida não encontraria "existente" em
        `abrir_por_mesa` e criaria uma segunda comanda por cima da primeira,
        ainda não paga.
        """
        stmt = select(Comanda).where(
            Comanda.mesa_id == mesa_id,
            Comanda.status.in_([StatusComanda.ABERTA, StatusComanda.EM_CONFERENCIA]),
        )
        return self.session.scalars(stmt).first()

    def listar_por_status(self, status: StatusComanda) -> list[Comanda]:
        stmt = select(Comanda).where(Comanda.status == status).order_by(Comanda.id)
        return list(self.session.scalars(stmt))

    def listar_balcao_abertas(self) -> list[Comanda]:
        stmt = (
            select(Comanda)
            .where(Comanda.mesa_id.is_(None), Comanda.status == StatusComanda.ABERTA)
            .order_by(Comanda.id)
        )
        return list(self.session.scalars(stmt))

    def listar_por_caixa(self, caixa_id: int) -> list[Comanda]:
        stmt = select(Comanda).where(Comanda.caixa_id == caixa_id).order_by(Comanda.id)
        return list(self.session.scalars(stmt))

    def contar_por_caixa_e_status(self, caixa_id: int, status: StatusComanda) -> int:
        """Quantas comandas do caixa estão neste status — sem trazer nenhuma delas.

        Os resumos financeiros só querem a CONTAGEM de comandas fechadas do
        turno. Carregar as centenas de comandas do caixa como objetos ORM só
        para chamar `len()` gastava memória e tempo à toa numa máquina fraca —
        e no Dashboard Mensal isso acontecia uma vez por turno do mês (§3.6).
        """
        stmt = (
            select(func.count())
            .select_from(Comanda)
            .where(Comanda.caixa_id == caixa_id, Comanda.status == status)
        )
        return self.session.scalar(stmt) or 0

    def listar_abertas_por_mesa(self) -> dict[int, Comanda]:
        """A comanda "em uso" de cada mesa ocupada, indexada por `mesa_id`.

        É o que a grade da tela principal precisa (`mesas_view`), numa consulta
        só. Antes, a tela lia `mesa.comandas` de cada mesa ocupada e procurava a
        aberta em Python — o que carrega **todo o histórico daquela mesa**, mês
        após mês, para achar uma linha. Era o custo que crescia sem teto com as
        semanas de operação, e na tela mais usada do PDV (§3.6).

        Mesmo critério de `buscar_aberta_por_mesa`: ABERTA ou EM_CONFERENCIA.
        Comandas de balcão (sem mesa) ficam de fora — a grade só mostra mesas.
        `atendente` e `usuario` vêm carregados porque a grade escreve o nome de
        quem atende em cada card.
        """
        stmt = (
            select(Comanda)
            .where(
                Comanda.mesa_id.is_not(None),
                Comanda.status.in_([StatusComanda.ABERTA, StatusComanda.EM_CONFERENCIA]),
            )
            .order_by(Comanda.id)
            .options(selectinload(Comanda.atendente), selectinload(Comanda.usuario))
        )
        # Se por algum motivo houver mais de uma comanda em uso na mesma mesa,
        # a de id menor (a mais antiga) vence — mesma escolha do `.first()` de
        # `buscar_aberta_por_mesa`, para as duas telas concordarem.
        abertas: dict[int, Comanda] = {}
        for comanda in self.session.scalars(stmt):
            abertas.setdefault(comanda.mesa_id, comanda)
        return abertas
