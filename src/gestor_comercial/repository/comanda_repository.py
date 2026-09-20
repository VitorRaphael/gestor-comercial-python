from decimal import Decimal

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

    def fechadas_do_caixa(self, caixa_id: int) -> tuple[int, Decimal]:
        """Quantas comandas o turno fechou e quanto delas foi taxa de serviço.

        Uma consulta de agregação, sem trazer comanda nenhuma: os resumos
        financeiros só querem os dois números. Carregar as centenas de comandas
        do caixa como objetos ORM só para chamar `len()` gastava memória e tempo
        à toa numa máquina fraca — e no Dashboard Mensal isso acontece uma vez
        por turno do mês (§3.6). A soma da taxa (§9.23) entrou NA MESMA
        consulta que já existia para a contagem, e não numa segunda, pelo mesmo
        motivo.

        Só FECHADA: é a venda concluída. Comanda em conferência ainda pode ser
        reaberta (e perder a taxa), e o fechamento do caixa já recusa turno com
        conta em aberto.
        """
        stmt = select(
            func.count(), func.coalesce(func.sum(Comanda.valor_taxa_servico), 0)
        ).where(Comanda.caixa_id == caixa_id, Comanda.status == StatusComanda.FECHADA)
        quantidade, taxa = self.session.execute(stmt).one()
        # A soma volta do SQLite como `float` (ou o `0` do `coalesce`); `str`
        # antes do `Decimal` para a dízima binária não entrar na conta, e quem
        # arredonda nos centavos é o service, com o `dinheiro()` de sempre.
        return int(quantidade or 0), Decimal(str(taxa or 0))

    def listar_comissoes_pendentes(self) -> list[Comanda]:
        """As contas pagas cuja comissão ainda não foi repassada ao garçom (§9.25).

        Só o que pode gerar repasse: conta FECHADA, com taxa de serviço maior que
        zero e com atendente vinculado. Sem atendente não há a quem pagar, e sem
        taxa não há o que pagar. O atendente vem junto (`selectinload`), porque
        quem chama lista por garçom e ler o nome linha a linha seria o N+1 do
        §3.6.
        """
        stmt = (
            select(Comanda)
            .where(
                Comanda.status == StatusComanda.FECHADA,
                Comanda.comissao_paga.is_(False),
                Comanda.atendente_id.is_not(None),
                Comanda.valor_taxa_servico > 0,
            )
            .options(selectinload(Comanda.atendente))
            .order_by(Comanda.fechada_em, Comanda.id)
        )
        return list(self.session.scalars(stmt))

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
