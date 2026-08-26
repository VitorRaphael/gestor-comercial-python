"""Caixa do dia: abertura, movimentos da gaveta, conferência e fechamento.

Porte de CaixaService.java e MovimentoCaixaService.java (§3.9 e §3.10). Os dois
services do Java viraram um só aqui porque `registrar` já dependia de
`buscarAberto`: separá-los criaria duas classes que só existem uma para a outra.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.enums import (
    FormaPagamento,
    StatusCaixa,
    StatusComanda,
    TipoMovimento,
)
from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import (
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)

FORMAS_MAQUININHA = (FormaPagamento.CREDITO, FormaPagamento.DEBITO, FormaPagamento.PIX)

# Divergência intencional do Java: lá qualquer um registrava qualquer movimento.
# Sangria e despesa tiram dinheiro da gaveta, então passam pelo gerente; reforço
# não trava a operação do balcão.
TIPOS_QUE_EXIGEM_GERENTE = (TipoMovimento.SANGRIA, TipoMovimento.DESPESA)
TIPOS_QUE_SAEM_DA_GAVETA = (TipoMovimento.SANGRIA, TipoMovimento.DESPESA)


@dataclass(frozen=True)
class ResumoCaixa:
    """Fotografia do caixa para a tela de conferência e fechamento."""

    caixa_id: int
    valor_abertura: Decimal
    total_dinheiro: Decimal
    total_maquininha: Decimal
    total_consumo_interno: Decimal
    reforcos: Decimal
    sangrias: Decimal
    despesas: Decimal
    saldo_esperado: Decimal
    valor_contado: Decimal | None
    diferenca: Decimal | None


class CaixaService:
    """Abertura/fechamento do caixa, movimentos da gaveta e conferência (§3.9, §3.10)."""

    def __init__(self, uow: UnitOfWork, auth: AuthService) -> None:
        self.uow = uow
        self.auth = auth

    # ------------------------------------------------------------------
    # Abertura e fechamento
    # ------------------------------------------------------------------

    def abrir(self, valor_abertura: Decimal) -> Caixa:
        # §3.1: o Java já documentava "atendente tentando abrir o caixa" como
        # acesso negado — quem declara o fundo de troco é quem responde por ele.
        gerente = self.auth.exigir_gerente()
        valor = self._valor_monetario(valor_abertura, "valor de abertura")
        if valor < ZERO:
            raise RegraDeNegocioError("O valor de abertura não pode ser negativo.")
        if self.uow.caixas.buscar_aberto() is not None:
            raise RegraDeNegocioError(
                "Já existe um caixa aberto. Feche o caixa atual antes de abrir outro."
            )

        caixa = Caixa(
            status=StatusCaixa.ABERTO,
            valor_abertura=valor,
            aberto_em=datetime.now(),
            aberto_por_id=gerente.id,
        )
        self.uow.caixas.salvar(caixa)
        self.uow.commit()
        return caixa

    def fechar(self, caixa_id: int, valor_contado: Decimal, observacao: str | None = None) -> Caixa:
        gerente = self.auth.exigir_gerente()
        caixa = self.buscar(caixa_id)
        if caixa.status is StatusCaixa.FECHADO:
            raise RegraDeNegocioError(f"O caixa {caixa_id} já está fechado.")

        valor = self._valor_monetario(valor_contado, "valor contado")
        if valor < ZERO:
            raise RegraDeNegocioError("O valor contado não pode ser negativo.")

        # Divergência intencional do Java: fechar com mesa em aberto some com a
        # venda — a comanda fica presa num caixa que já foi conferido e o
        # dinheiro dela nunca entra em nenhum fechamento. Só conta quem tem
        # item: uma comanda ABERTA e vazia é o mesmo rascunho que
        # ComandaService.listar_abertas() já esconde (criada ao tocar na mesa
        # e desistir) — bloquear o fechamento por causa dela deixaria o
        # gerente sem como achá-la em tela nenhuma pra resolver.
        abertas = [
            comanda
            for comanda in self.uow.comandas.listar_por_caixa(caixa_id)
            if comanda.status is StatusComanda.ABERTA and self.uow.itens.existe_na_comanda(comanda.id)
        ]
        if abertas:
            pendencia = (
                "1 comanda aberta" if len(abertas) == 1 else f"{len(abertas)} comandas abertas"
            )
            raise RegraDeNegocioError(
                f"Ainda há {pendencia} neste caixa. "
                "Receba ou cancele antes de fechar o caixa."
            )

        fechado_em = datetime.now()
        # Regra da virada de madrugada: indexado por `fechado_em.date()`, nunca
        # por `aberto_em` — um caixa aberto às 17h e fechado 01h do dia
        # seguinte é o 1º fechamento do dia seguinte, não do dia da abertura.
        # Contado ANTES de sujar `caixa` — mudar o status/fechado_em primeiro
        # faria o autoflush do SQLAlchemy incluir este próprio caixa na
        # contagem antes de ele ter, de fato, um número. Calculado dentro da
        # mesma transação do commit do fechamento (app single-user/single-
        # processo, sem escrita concorrente possível) e nunca mais recalculado:
        # fechar de novo o mesmo caixa já é bloqueado acima, então este número
        # é imutável a partir daqui.
        numero_sequencial_dia = self.uow.caixas.contar_fechados_no_dia(fechado_em.date()) + 1

        caixa.status = StatusCaixa.FECHADO
        caixa.fechado_em = fechado_em
        caixa.valor_contado = valor
        caixa.observacao_fechamento = self._texto_ou_nulo(observacao)
        caixa.fechado_por_id = gerente.id
        caixa.numero_sequencial_dia = numero_sequencial_dia
        self.uow.caixas.salvar(caixa)
        self.uow.commit()
        return caixa

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def buscar(self, caixa_id: int) -> Caixa:
        caixa = self.uow.caixas.buscar_por_id(caixa_id)
        if caixa is None:
            raise RecursoNaoEncontradoError(f"Caixa não encontrado (código {caixa_id}).")
        return caixa

    def buscar_aberto(self) -> Caixa:
        caixa = self.uow.caixas.buscar_aberto()
        if caixa is None:
            raise RegraDeNegocioError(
                "Não há nenhum caixa aberto no momento. Abra o caixa para começar o dia."
            )
        return caixa

    def buscar_ultimo_fechado(self) -> Caixa:
        caixa = self.uow.caixas.buscar_ultimo_fechado()
        if caixa is None:
            raise RegraDeNegocioError("Nenhum caixa foi fechado ainda.")
        return caixa

    # ------------------------------------------------------------------
    # Histórico de fechamentos
    # ------------------------------------------------------------------

    def listar_historico(
        self,
        *,
        inicio: date | None = None,
        fim: date | None = None,
        funcionario_id: int | None = None,
    ) -> list[Caixa]:
        """Fechamentos passados para a tela de Histórico, do mais recente pro mais antigo."""
        return self.uow.caixas.listar_historico(inicio=inicio, fim=fim, funcionario_id=funcionario_id)

    def titulo_fechamento(self, caixa_id: int) -> str:
        """'3º Fechamento do dia 26/08/2026' — identificação oficial do fechamento (§ sequência diária)."""
        caixa = self.buscar(caixa_id)
        if caixa.numero_sequencial_dia is None or caixa.fechado_em is None:
            raise RegraDeNegocioError(f"O caixa {caixa_id} ainda não foi fechado.")
        return f"{caixa.numero_sequencial_dia}º Fechamento do dia {caixa.fechado_em:%d/%m/%Y}"

    def totais_por_forma(self, caixa_id: int) -> dict[FormaPagamento, Decimal]:
        """Quanto entrou em cada forma de pagamento — só as que tiveram venda."""
        self.buscar(caixa_id)
        totais: dict[FormaPagamento, Decimal] = {}
        for forma in FormaPagamento:
            total = self._somar(self._pagamentos(caixa_id, forma))
            if total > ZERO:
                totais[forma] = total
        return totais

    # ------------------------------------------------------------------
    # Movimentos da gaveta (§3.10)
    # ------------------------------------------------------------------

    def registrar_movimento(
        self, tipo: TipoMovimento, valor: Decimal, descricao: str | None = None
    ) -> MovimentoCaixa:
        if not isinstance(tipo, TipoMovimento):
            raise RegraDeNegocioError("Selecione o tipo do movimento: sangria, reforço ou despesa.")
        if tipo is TipoMovimento.CONSUMO_FUNCIONARIO:
            # Consumo interno já é rastreado inteiro por PagamentoService.registrar
            # (forma=CONSUMO_INTERNO): cria o Pagamento, soma em saldo_devedor e
            # nunca mexe na gaveta, porque nunca foi dinheiro. Um MovimentoCaixa
            # manual deste tipo descontaria a mesma dívida uma segunda vez.
            raise RegraDeNegocioError(
                "Consumo de funcionário é registrado como pagamento da comanda "
                "(forma Consumo Interno), não como movimento de caixa."
            )
        if tipo in TIPOS_QUE_EXIGEM_GERENTE:
            funcionario = self.auth.exigir_gerente()
        else:
            funcionario = self.auth.usuario_atual()

        montante = self._valor_monetario(valor, "valor do movimento")
        if montante <= ZERO:
            raise RegraDeNegocioError("O valor do movimento deve ser maior que zero.")

        caixa = self.buscar_aberto()
        movimento = MovimentoCaixa(
            tipo=tipo,
            valor=montante,
            descricao=self._texto_ou_nulo(descricao),
            registrado_em=datetime.now(),
            caixa_id=caixa.id,
            funcionario_id=funcionario.id,
        )
        self.uow.movimentos.salvar(movimento)
        self.uow.commit()
        return movimento

    def listar_movimentos(self, caixa_id: int) -> list[MovimentoCaixa]:
        self.buscar(caixa_id)
        return self.uow.movimentos.listar_por_caixa(caixa_id)

    # ------------------------------------------------------------------
    # Conferência
    # ------------------------------------------------------------------

    def calcular_saldo_esperado(self, caixa_id: int) -> Decimal:
        """Quanto tem que estar dentro da gaveta agora (§3.9)."""
        caixa = self.buscar(caixa_id)
        saldo = dinheiro(caixa.valor_abertura)

        for movimento in self.uow.movimentos.listar_por_caixa(caixa_id):
            if movimento.tipo is TipoMovimento.REFORCO:
                saldo += dinheiro(movimento.valor)
            elif movimento.tipo in TIPOS_QUE_SAEM_DA_GAVETA:
                saldo -= dinheiro(movimento.valor)
            else:
                raise RegraDeNegocioError(
                    f"Tipo de movimento não previsto no cálculo do caixa: {movimento.tipo.value}."
                )

        # `Pagamento.valor` é o que foi lançado na conta, já líquido: numa conta
        # de 36 paga com nota de 50, valor=36 e troco=14. A gaveta recebeu 50 e
        # devolveu 14, ou seja, +36 — descontar o troco aqui tiraria ele duas vezes.
        saldo += self._somar(self._pagamentos(caixa_id, FormaPagamento.DINHEIRO))
        return dinheiro(saldo)

    def calcular_vendas_maquininha(self, caixa_id: int) -> Decimal:
        self.buscar(caixa_id)
        return self._somar(self._pagamentos(caixa_id, *FORMAS_MAQUININHA))

    def resumo(self, caixa_id: int) -> ResumoCaixa:
        caixa = self.buscar(caixa_id)

        reforcos = sangrias = despesas = ZERO
        for movimento in self.uow.movimentos.listar_por_caixa(caixa_id):
            if movimento.tipo is TipoMovimento.REFORCO:
                reforcos += dinheiro(movimento.valor)
            elif movimento.tipo is TipoMovimento.SANGRIA:
                sangrias += dinheiro(movimento.valor)
            elif movimento.tipo is TipoMovimento.DESPESA:
                despesas += dinheiro(movimento.valor)

        valor_contado = None if caixa.valor_contado is None else dinheiro(caixa.valor_contado)
        saldo_esperado = self.calcular_saldo_esperado(caixa_id)

        return ResumoCaixa(
            caixa_id=caixa.id,
            valor_abertura=dinheiro(caixa.valor_abertura),
            total_dinheiro=self._somar(self._pagamentos(caixa_id, FormaPagamento.DINHEIRO)),
            total_maquininha=self._somar(self._pagamentos(caixa_id, *FORMAS_MAQUININHA)),
            # Consumo interno é venda que nunca virou dinheiro na gaveta: fica em
            # linha própria pra explicar a diferença entre o que foi vendido e o
            # que dá pra contar na hora do fechamento.
            total_consumo_interno=self._somar(
                self._pagamentos(caixa_id, FormaPagamento.CONSUMO_INTERNO)
            ),
            reforcos=reforcos,
            sangrias=sangrias,
            despesas=despesas,
            saldo_esperado=saldo_esperado,
            valor_contado=valor_contado,
            diferenca=None if valor_contado is None else dinheiro(valor_contado - saldo_esperado),
        )

    # ------------------------------------------------------------------

    def _pagamentos(self, caixa_id: int, *formas: FormaPagamento) -> list[Pagamento]:
        return self.uow.pagamentos.listar_por_caixa(caixa_id, formas=list(formas))

    @staticmethod
    def _somar(pagamentos: Iterable[Pagamento]) -> Decimal:
        total = ZERO
        for pagamento in pagamentos:
            total += dinheiro(pagamento.valor)
        return dinheiro(total)

    @staticmethod
    def _valor_monetario(valor: Decimal | int | str | None, rotulo: str) -> Decimal:
        if valor is None:
            raise RegraDeNegocioError(f"Informe o {rotulo}.")
        try:
            return dinheiro(valor)
        except ValueError:
            # float não é tratado aqui de propósito: `dinheiro()` levanta
            # TypeError e isso é erro de programação da tela, não do operador.
            raise RegraDeNegocioError(
                f"{rotulo.capitalize()} inválido. Informe um valor em reais, como 50.00."
            ) from None

    @staticmethod
    def _texto_ou_nulo(texto: str | None) -> str | None:
        if not isinstance(texto, str):
            return None
        limpo = texto.strip()
        return limpo or None
