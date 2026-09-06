"""Recebimento da conta e a dívida de consumo interno dos funcionários.

Porte de PagamentoService.java e QuitacaoConsumoService.java (§3.7 e §3.8). No
Java eram dois services; aqui viraram um só porque a dívida de consumo interno
não é uma entidade própria — ela É a soma dos pagamentos na forma
CONSUMO_INTERNO. Separá-los criaria um service cujo único trabalho seria ler a
tabela do outro.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from gestor_comercial.domain.enums import FormaPagamento, StatusComanda
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.domain.quitacao_consumo import QuitacaoConsumo
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import RegraDeNegocioError
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.transacao import transacional


@dataclass(frozen=True)
class ResumoPagamento:
    """O que a tela de pagamento mostra depois de receber um valor."""

    comanda_id: int
    total_conta: Decimal
    total_pago: Decimal
    restante: Decimal
    troco: Decimal | None
    comanda_fechada: bool


@dataclass(frozen=True)
class SaldoDevedor:
    """Uma linha da lista de funcionários que devem consumo interno."""

    funcionario_id: int
    nome: str
    saldo: Decimal


@dataclass(frozen=True)
class ExtratoConsumo:
    """Extrato completo de um funcionário: o que consumiu e o que já pagou."""

    funcionario_id: int
    nome: str
    saldo: Decimal
    consumos: list[Pagamento]
    quitacoes: list[QuitacaoConsumo]


@transacional
class PagamentoService:
    """Pagamento parcial/múltiplo, troco e quitação de consumo interno (§3.7, §3.8)."""

    def __init__(
        self,
        uow: UnitOfWork,
        auth: AuthService,
        comandas: ComandaService,
        funcionarios: FuncionarioService,
    ) -> None:
        self.uow = uow
        self.auth = auth
        self.comandas = comandas
        self.funcionarios = funcionarios

    # ------------------------------------------------------------------
    # Recebimento (porte de PagamentoService.registrar)
    # ------------------------------------------------------------------

    def registrar(
        self,
        comanda_id: int,
        forma: FormaPagamento,
        valor_recebido: Decimal,
        pin_gerente: str | None = None,
        funcionario_consumo_id: int | None = None,
    ) -> ResumoPagamento:
        """Lança um pagamento na comanda e fecha a conta se ela ficar quitada."""
        # DIVERGÊNCIA do Java: lá o endpoint aceitava pagamento sem sessão. Num
        # caixa físico, todo dinheiro recebido tem que ter um responsável.
        self.auth.usuario_atual()

        comanda = self.comandas.buscar(comanda_id)
        if comanda.status is StatusComanda.ABERTA:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} ainda está aberta. "
                "Feche para conferência (emita a pré-conta) antes de receber o pagamento."
            )
        if comanda.status is not StatusComanda.EM_CONFERENCIA:
            situacao = (
                "já foi fechada" if comanda.status is StatusComanda.FECHADA else "foi cancelada"
            )
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} {situacao} e não aceita mais pagamento."
            )

        if not isinstance(forma, FormaPagamento):
            raise RegraDeNegocioError(
                "Selecione a forma de pagamento: dinheiro, crédito, débito, PIX ou consumo interno."
            )

        recebido = self._valor_monetario(valor_recebido, "valor do pagamento")
        if recebido <= ZERO:
            raise RegraDeNegocioError("O valor do pagamento deve ser maior que zero.")

        consumidor = None
        if forma is FormaPagamento.CONSUMO_INTERNO:
            consumidor = self._autorizar_consumo_interno(pin_gerente, funcionario_consumo_id)

        total_conta = self.comandas.calcular_total_a_pagar(comanda_id)
        if total_conta <= ZERO:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} não tem nenhum item lançado. "
                "Lance os itens antes de receber o pagamento."
            )

        restante = dinheiro(total_conta - self.calcular_total_pago(comanda_id))
        if restante <= ZERO:
            raise RegraDeNegocioError(f"A comanda {comanda_id} já está quitada.")

        if recebido > restante:
            if forma is not FormaPagamento.DINHEIRO:
                raise RegraDeNegocioError(
                    f"O valor de R$ {recebido} passa do que falta receber (R$ {restante}). "
                    "Só pagamento em dinheiro gera troco."
                )
            # Só o que faltava entra na conta; o excedente sai da gaveta como
            # troco e não pode ser contado como venda.
            valor_lancado = restante
            troco = dinheiro(recebido - restante)
        else:
            valor_lancado = recebido
            troco = None

        pagamento = Pagamento(
            comanda_id=comanda.id,
            forma=forma,
            valor=valor_lancado,
            troco=troco,
            valor_quitado=ZERO,
            registrado_em=datetime.now(),
            funcionario_consumo_id=None if consumidor is None else consumidor.id,
        )
        self.uow.pagamentos.salvar(pagamento)

        if consumidor is not None:
            # `Funcionario.saldo_devedor` é cache: a verdade é a soma dos
            # pagamentos (calcular_saldo_devedor). Ele existe para a lista de
            # funcionários não varrer a tabela de pagamentos linha a linha.
            consumidor.saldo_devedor = dinheiro(
                dinheiro(consumidor.saldo_devedor) + valor_lancado
            )
            self.uow.funcionarios.salvar(consumidor)

        total_pago = self.calcular_total_pago(comanda_id)
        restante_final = dinheiro(total_conta - total_pago)
        comanda_fechada = restante_final <= ZERO
        if comanda_fechada:
            self.comandas.fechar(comanda_id)

        self.uow.commit()
        return ResumoPagamento(
            comanda_id=comanda.id,
            total_conta=total_conta,
            total_pago=total_pago,
            restante=restante_final,
            troco=troco,
            comanda_fechada=comanda_fechada,
        )

    # ------------------------------------------------------------------
    # Consultas da comanda
    # ------------------------------------------------------------------

    def listar_por_comanda(self, comanda_id: int) -> list[Pagamento]:
        self.comandas.buscar(comanda_id)
        return self.uow.pagamentos.listar_por_comanda(comanda_id)

    def calcular_total_pago(self, comanda_id: int) -> Decimal:
        self.comandas.buscar(comanda_id)
        total = ZERO
        for pagamento in self.uow.pagamentos.listar_por_comanda(comanda_id):
            total += dinheiro(pagamento.valor)
        return dinheiro(total)

    def calcular_restante(self, comanda_id: int) -> Decimal:
        restante = self.comandas.calcular_total_a_pagar(comanda_id) - self.calcular_total_pago(comanda_id)
        # Nunca negativo: se um item for cancelado depois da conta já paga, a
        # tela precisa dizer "nada a receber", não mostrar um valor negativo.
        return dinheiro(max(restante, ZERO))

    # ------------------------------------------------------------------
    # Consumo interno e quitação (porte de QuitacaoConsumoService.java)
    # ------------------------------------------------------------------

    def calcular_saldo_devedor(self, funcionario_id: int) -> Decimal:
        """Fonte da verdade da dívida: o que foi consumido menos o que já foi quitado."""
        self.auth.exigir_gerente()  # §3.1/§3.8: dívida de um funcionário não é leitura livre
        self.funcionarios.buscar(funcionario_id)
        return self._somar_pendente(
            self.uow.pagamentos.listar_consumos_do_funcionario(funcionario_id)
        )

    def listar_funcionarios_com_saldo(self) -> list[SaldoDevedor]:
        self.auth.exigir_gerente()  # §3.1/§3.8
        # DIVERGÊNCIA do Java: lá a lista saía de `listarAtivos`, então desativar
        # um funcionário fazia a dívida dele sumir da tela sem ter sido paga.
        # Aqui aparece quem deve, ativo ou não.
        saldos: list[SaldoDevedor] = []
        for funcionario in self.uow.funcionarios.listar_todos():
            saldo = self._somar_pendente(
                self.uow.pagamentos.listar_consumos_do_funcionario(funcionario.id)
            )
            if saldo > ZERO:
                saldos.append(SaldoDevedor(funcionario.id, funcionario.nome, saldo))
        saldos.sort(key=lambda linha: linha.nome)
        return saldos

    def listar_consumos(self, funcionario_id: int) -> ExtratoConsumo:
        self.auth.exigir_gerente()  # §3.1/§3.8
        funcionario = self.funcionarios.buscar(funcionario_id)
        consumos = self.uow.pagamentos.listar_consumos_do_funcionario(funcionario_id)
        return ExtratoConsumo(
            funcionario_id=funcionario.id,
            nome=funcionario.nome,
            saldo=self._somar_pendente(consumos),
            consumos=consumos,
            quitacoes=self.uow.quitacoes.listar_por_funcionario(funcionario_id),
        )

    def quitar(self, funcionario_id: int, valor: Decimal, pin_gerente: str) -> Decimal:
        """Abate a dívida do mais antigo para o mais novo e devolve o saldo que sobrou."""
        funcionario = self.funcionarios.buscar(funcionario_id)
        gerente = self.auth.validar_pin_gerente(pin_gerente)

        montante = self._valor_monetario(valor, "valor da quitação")
        if montante <= ZERO:
            raise RegraDeNegocioError("O valor a quitar deve ser maior que zero.")

        consumos = self.uow.pagamentos.listar_consumos_do_funcionario(funcionario_id)
        saldo_devedor = self._somar_pendente(consumos)
        if saldo_devedor <= ZERO:
            raise RegraDeNegocioError(f"{funcionario.nome} não tem consumo em aberto para dar baixa.")
        if montante > saldo_devedor:
            raise RegraDeNegocioError(
                f"O valor a quitar (R$ {montante}) passa do consumo em aberto de R$ {saldo_devedor}."
            )

        # FIFO (§3.8): o consumo mais antigo é abatido primeiro, para o extrato
        # ser lido de cima para baixo como uma fila de dívida sendo paga.
        a_aplicar = montante
        for consumo in consumos:
            if a_aplicar <= ZERO:
                break
            pendente = self._pendente(consumo)
            if pendente <= ZERO:
                continue
            aplicado = min(pendente, a_aplicar)
            consumo.valor_quitado = dinheiro(dinheiro(consumo.valor_quitado) + aplicado)
            self.uow.pagamentos.salvar(consumo)
            a_aplicar = dinheiro(a_aplicar - aplicado)

        self.uow.quitacoes.salvar(
            QuitacaoConsumo(
                valor_quitado=montante,
                quitado_em=datetime.now(),
                funcionario_id=funcionario.id,
                autorizado_por_id=gerente.id,
            )
        )

        novo_saldo = self._somar_pendente(
            self.uow.pagamentos.listar_consumos_do_funcionario(funcionario_id)
        )
        funcionario.saldo_devedor = novo_saldo
        self.uow.funcionarios.salvar(funcionario)
        self.uow.commit()
        return novo_saldo

    # ------------------------------------------------------------------
    # Apoio
    # ------------------------------------------------------------------

    def _autorizar_consumo_interno(
        self, pin_gerente: str | None, funcionario_consumo_id: int | None
    ) -> Funcionario:
        """Consumo interno vira dívida de alguém, então precisa de gerente e de dono (§3.7)."""
        if not isinstance(pin_gerente, str) or not pin_gerente.strip():
            raise RegraDeNegocioError(
                "Consumo interno precisa do PIN do gerente para ser autorizado."
            )
        if funcionario_consumo_id is None:
            raise RegraDeNegocioError("Informe qual funcionário está consumindo.")

        self.auth.validar_pin_gerente(pin_gerente)
        funcionario = self.funcionarios.buscar(funcionario_consumo_id)
        if not funcionario.ativo:
            raise RegraDeNegocioError(
                f"O funcionário {funcionario.nome} está desativado e não pode lançar consumo interno."
            )
        return funcionario

    @staticmethod
    def _pendente(consumo: Pagamento) -> Decimal:
        return dinheiro(dinheiro(consumo.valor) - dinheiro(consumo.valor_quitado))

    @classmethod
    def _somar_pendente(cls, consumos: Iterable[Pagamento]) -> Decimal:
        total = ZERO
        for consumo in consumos:
            total += cls._pendente(consumo)
        return dinheiro(total)

    @staticmethod
    def _valor_monetario(valor: Decimal | int | str | None, rotulo: str) -> Decimal:
        if valor is None:
            raise RegraDeNegocioError(f"Informe o {rotulo}.")
        try:
            return dinheiro(valor)
        except ValueError:
            # float não é convertido aqui de propósito: `dinheiro()` levanta
            # TypeError, e passar float é erro de programação da tela, não do
            # operador — tem que estourar no teste, não virar aviso na venda.
            raise RegraDeNegocioError(
                f"{rotulo.capitalize()} inválido. Informe um valor em reais, como 50.00."
            ) from None
