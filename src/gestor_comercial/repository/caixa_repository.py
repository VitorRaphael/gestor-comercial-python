import calendar
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.enums import StatusCaixa
from gestor_comercial.repository.base import Repository


class CaixaRepository(Repository[Caixa]):
    modelo = Caixa

    def buscar_aberto(self) -> Caixa | None:
        stmt = select(Caixa).where(Caixa.status == StatusCaixa.ABERTO).order_by(Caixa.id)
        return self.session.scalars(stmt).first()

    def buscar_ultimo_fechado(self) -> Caixa | None:
        stmt = (
            select(Caixa)
            .where(Caixa.status == StatusCaixa.FECHADO)
            .order_by(Caixa.fechado_em.desc(), Caixa.id.desc())
        )
        return self.session.scalars(stmt).first()

    def contar_fechados_no_dia(self, dia: date) -> int:
        """Quantos fechamentos já existem no dia CIVIL de `dia` (§ sequência diária).

        Usado por `CaixaService.fechar` para calcular o próximo `numero_sequencial_dia`
        — indexado por `fechado_em`, nunca por `aberto_em`.
        """
        inicio = datetime(dia.year, dia.month, dia.day)
        fim = inicio + timedelta(days=1)
        stmt = select(func.count()).select_from(Caixa).where(
            Caixa.status == StatusCaixa.FECHADO,
            Caixa.fechado_em >= inicio,
            Caixa.fechado_em < fim,
        )
        return self.session.scalar(stmt) or 0

    def listar_historico(
        self,
        *,
        inicio: date | None = None,
        fim: date | None = None,
        funcionario_id: int | None = None,
    ) -> list[Caixa]:
        """Fechamentos para a tela de Histórico, do mais recente para o mais antigo.

        `inicio`/`fim` filtram pela data de `fechado_em` (mesmo eixo da sequência
        diária), inclusive nas duas pontas. `funcionario_id` casa com quem abriu
        OU quem fechou, porque o gerente que está conferindo pode não lembrar de
        qual das duas pontas do turno era o funcionário que procura.
        """
        stmt = select(Caixa).where(Caixa.status == StatusCaixa.FECHADO)
        if inicio is not None:
            stmt = stmt.where(Caixa.fechado_em >= datetime(inicio.year, inicio.month, inicio.day))
        if fim is not None:
            limite = datetime(fim.year, fim.month, fim.day) + timedelta(days=1)
            stmt = stmt.where(Caixa.fechado_em < limite)
        if funcionario_id is not None:
            stmt = stmt.where(
                (Caixa.aberto_por_id == funcionario_id) | (Caixa.fechado_por_id == funcionario_id)
            )
        stmt = stmt.order_by(Caixa.fechado_em.desc(), Caixa.id.desc())
        return list(self.session.scalars(stmt))

    def listar_por_mes_abertura(self, ano: int, mes: int) -> list[Caixa]:
        """Fechamentos cuja COMPETÊNCIA é o mês civil `ano`/`mes`.

        Divergência intencional de `listar_historico`: aqui o eixo é
        `aberto_em`, não `fechado_em`. Um caixa aberto às 23h de um dia e
        fechado de madrugada no dia seguinte pertence, para efeito contábil
        da tela de Relatórios, ao dia (e ao mês) em que foi ABERTO — é a regra
        de "virada de noite" do food truck. `numero_sequencial_dia` continua
        indexado por `fechado_em` (não muda aqui): é uma numeração diferente,
        para um propósito diferente (identificar qual fechamento é qual no
        dia em que a gaveta foi de fato conferida).
        """
        inicio, fim = _intervalo_do_mes(ano, mes)
        limite = datetime(fim.year, fim.month, fim.day) + timedelta(days=1)
        stmt = (
            select(Caixa)
            .where(
                Caixa.status == StatusCaixa.FECHADO,
                Caixa.aberto_em >= datetime(inicio.year, inicio.month, inicio.day),
                Caixa.aberto_em < limite,
            )
            .order_by(Caixa.aberto_em.desc(), Caixa.id.desc())
        )
        return list(self.session.scalars(stmt))


def _intervalo_do_mes(ano: int, mes: int) -> tuple[date, date]:
    """`startOfMonth`/`endOfMonth` do mês civil `ano`/`mes`."""
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, 1), date(ano, mes, ultimo_dia)
