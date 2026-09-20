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
from decimal import ROUND_UP, Decimal

from gestor_comercial.domain.enums import FormaPagamento, StatusComanda
from gestor_comercial.domain.funcionario import Funcionario
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.domain.quitacao_consumo import QuitacaoConsumo
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.dinheiro import CENTAVOS, ZERO, dinheiro
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
class LinhaDaConta:
    """Uma linha da lista de consumo na tela de pagamento (§9.25)."""

    quantidade: int
    descricao: str
    valor: Decimal


@dataclass(frozen=True)
class ComissaoDaConta:
    """O card "Comissão de [garçom]" da tela de pagamento (§9.25).

    O valor É a taxa de serviço daquela conta: a comissão do garçom é o serviço
    que o cliente pagou, e não um segundo número guardado em outro lugar.
    """

    funcionario_id: int
    nome: str
    valor: Decimal
    paga: bool


@dataclass(frozen=True)
class ContaParaPagamento:
    """O instantâneo que a tela "Receber Pagamento" mostra (§9.25).

    Imutável e montado de uma vez, pela lição do §9.4: a tela redesenha a cada
    pagamento parcial e a cada troca de forma, e todo commit expira as
    instâncias do SQLAlchemy — ler a comanda na hora de pintar levaria a tela
    ao banco a cada repintura.
    """

    comanda_id: int
    mesa_numero: int | None
    atendente_nome: str | None
    itens: list[LinhaDaConta]
    subtotal: Decimal
    # `None` quando a conta foi fechada sem taxa (loja sem taxa, §9.23).
    taxa_percentual: Decimal | None
    valor_taxa: Decimal
    total: Decimal
    total_pago: Decimal
    restante: Decimal
    # `None` quando não há comissão a repassar: sem atendente vinculado ou sem
    # taxa na conta.
    comissao: ComissaoDaConta | None

    @property
    def origem(self) -> str:
        """"Mesa 12" ou "Balcão" — como a tela e o cupom chamam a conta."""
        return "Balcão" if self.mesa_numero is None else f"Mesa {self.mesa_numero}"

    def por_pessoa(self, pessoas: int) -> Decimal:
        """O "Por pessoa (N)" do rodapé da lista — só conta de dividir.

        Arredonda para cima nos centavos: com R$ 10,00 entre 3, três vezes
        R$ 3,33 deixam um centavo na mesa. O programa prefere a conta que
        FECHA — quem paga por último não fica devendo um centavo ao caixa.
        """
        if pessoas <= 1:
            return self.total
        return dinheiro((self.total / pessoas).quantize(CENTAVOS, rounding=ROUND_UP))


@dataclass(frozen=True)
class ComissaoPendente:
    """Uma linha da lista de repasses a acertar, agrupada por garçom (§9.25)."""

    funcionario_id: int
    nome: str
    quantidade: int
    valor: Decimal


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
        caixas: CaixaService | None = None,
    ) -> None:
        self.uow = uow
        self.auth = auth
        self.comandas = comandas
        self.funcionarios = funcionarios
        # O caixa entra por causa do repasse de comissão (§9.25), que sai da
        # gaveta. Opcional para quem só recebe pagamento não precisar montar um
        # `CaixaService` — e construído aqui, no mesmo `UnitOfWork`, quando não
        # vem pronto: dois services do mesmo banco continuam na mesma Session.
        self.caixas = caixas if caixas is not None else CaixaService(uow, auth)

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
        comissao_paga: bool = False,
    ) -> ResumoPagamento:
        """Lança um pagamento na comanda e fecha a conta se ela ficar quitada.

        `comissao_paga` é a resposta do card do garçom (§9.25) e só vale no
        pagamento que FECHA a conta: é ali que o repasse acontece, e é por isso
        que ele entra no mesmo commit do fechamento — comissão marcada como paga
        com a conta não fechada seria um repasse sobre uma venda que ainda pode
        mudar. O padrão é `False`, o conservador: o dinheiro fica na gaveta e a
        comissão entra na lista de pendentes.
        """
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
            # Depois do `fechar` (que faz o próprio commit) e ANTES do commit
            # desta operação: a marca da comissão e a saída da gaveta viajam
            # juntas, porque marcada sem saída faz o turno sobrar dinheiro e
            # saída sem marca paga o garçom duas vezes.
            self._aplicar_comissao(comanda, paga=comissao_paga)

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
    # A conta na tela de pagamento (§9.25)
    # ------------------------------------------------------------------

    def conta_para_pagamento(self, comanda_id: int) -> ContaParaPagamento:
        """O instantâneo completo da conta, para a tela "Receber Pagamento".

        Uma chamada por recarga da tela: itens, totais, o que já foi pago e o
        card da comissão. Não grava nada.
        """
        comanda = self.comandas.buscar(comanda_id)
        itens = [
            LinhaDaConta(
                quantidade=item.quantidade,
                descricao=item.produto.nome,
                valor=dinheiro(dinheiro(item.preco_unit_congelado) * item.quantidade),
            )
            for item in self.uow.itens.listar_por_comanda(comanda_id)
            if not item.cancelado
        ]
        subtotal = self.comandas.calcular_total(comanda_id)
        total = self.comandas.calcular_total_a_pagar(comanda_id)
        pago = self.calcular_total_pago(comanda_id)
        return ContaParaPagamento(
            comanda_id=comanda.id,
            mesa_numero=comanda.mesa.numero if comanda.mesa else None,
            atendente_nome=comanda.atendente.nome if comanda.atendente else None,
            itens=itens,
            subtotal=subtotal,
            taxa_percentual=comanda.taxa_servico_percentual,
            valor_taxa=dinheiro(comanda.valor_taxa_servico or ZERO),
            total=total,
            total_pago=pago,
            restante=dinheiro(max(total - pago, ZERO)),
            comissao=self._comissao_de(comanda),
        )

    @staticmethod
    def _comissao_de(comanda) -> ComissaoDaConta | None:
        """A comissão daquela conta, ou `None` quando não há o que repassar.

        Sem atendente vinculado não há a quem pagar; sem taxa não há o que
        pagar. Nos dois casos a tela não mostra o card, e a conta não entra na
        lista de pendentes.
        """
        valor = dinheiro(comanda.valor_taxa_servico or ZERO)
        if comanda.atendente is None or valor <= ZERO:
            return None
        return ComissaoDaConta(
            funcionario_id=comanda.atendente.id,
            nome=comanda.atendente.nome,
            valor=valor,
            paga=bool(comanda.comissao_paga),
        )

    def _aplicar_comissao(self, comanda, *, paga: bool) -> None:
        """Marca a comissão da conta e, quando for o caso, tira o dinheiro da gaveta.

        **Sem commit**: quem chama fecha a transação, para a marca e o movimento
        irem juntos.

        A saída da gaveta só acontece quando a conta entrou em DINHEIRO — é a
        regra do Vitor: "caso o pagamento tenha sido em dinheiro e saia
        diretamente do caixa para o garçom". Conta paga no cartão ou no PIX não
        tem esse dinheiro na gaveta; a comissão é marcada como paga do mesmo
        jeito (o gerente acertou por fora), e o fechamento do turno não muda.
        """
        comissao = self._comissao_de(comanda)
        if comissao is None or comanda.comissao_paga == paga:
            return
        comanda.comissao_paga = paga
        comanda.comissao_paga_em = datetime.now() if paga else None
        self.uow.comandas.salvar(comanda)
        if paga and self._recebeu_em_dinheiro(comanda.id):
            origem = "Balcão" if comanda.mesa is None else f"Mesa {comanda.mesa.numero}"
            self.caixas.registrar_repasse_comissao(
                comissao.valor, f"Comissão de {comissao.nome} · {origem} · comanda {comanda.id}"
            )

    def _recebeu_em_dinheiro(self, comanda_id: int) -> bool:
        return any(
            pagamento.forma is FormaPagamento.DINHEIRO
            for pagamento in self.uow.pagamentos.listar_por_comanda(comanda_id)
        )

    def definir_comissao(self, comanda_id: int, paga: bool) -> None:
        """Marca (ou desmarca) o repasse de uma conta já fechada, num commit só.

        É por aqui que a lista de pendentes é acertada depois, fora do momento
        do pagamento. Desmarcar existe para o erro de clique: a marca volta a
        `False` e a conta reaparece na lista — mas o movimento de gaveta que já
        saiu NÃO é desfeito, porque dinheiro que saiu da gaveta saiu (quem
        precisa desfazer registra um reforço, que é o caminho auditável).
        """
        if not isinstance(paga, bool):
            raise RegraDeNegocioError("Informe se a comissão foi paga (sim ou não).")
        comanda = self.comandas.buscar(comanda_id)
        if comanda.status is not StatusComanda.FECHADA:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} ainda não foi paga: a comissão é acertada no recebimento."
            )
        self._aplicar_comissao(comanda, paga=paga)
        self.uow.commit()

    def listar_comissoes_pendentes(self) -> list[ComissaoPendente]:
        """Quanto o salão deve de comissão, por garçom — do maior para o menor.

        A lista que o §9.25 pediu para o gerente acertar no fim do turno. Uma
        consulta só (o atendente vem junto), somada em memória: agrupar no SQL
        traria o nome por `GROUP BY` e o arredondamento do SQLite junto.
        """
        por_funcionario: dict[int, ComissaoPendente] = {}
        for comanda in self.uow.comandas.listar_comissoes_pendentes():
            comissao = self._comissao_de(comanda)
            if comissao is None:
                continue
            atual = por_funcionario.get(comissao.funcionario_id)
            if atual is None:
                por_funcionario[comissao.funcionario_id] = ComissaoPendente(
                    funcionario_id=comissao.funcionario_id,
                    nome=comissao.nome,
                    quantidade=1,
                    valor=comissao.valor,
                )
            else:
                por_funcionario[comissao.funcionario_id] = ComissaoPendente(
                    funcionario_id=atual.funcionario_id,
                    nome=atual.nome,
                    quantidade=atual.quantidade + 1,
                    valor=dinheiro(atual.valor + comissao.valor),
                )
        return sorted(por_funcionario.values(), key=lambda linha: linha.valor, reverse=True)

    def comissao_pendente_de(self, funcionario_id: int) -> Decimal:
        """Quanto falta repassar a UM garçom. Zero quando não há nada pendente."""
        for pendente in self.listar_comissoes_pendentes():
            if pendente.funcionario_id == funcionario_id:
                return pendente.valor
        return ZERO

    def pagar_comissoes_do_funcionario(self, funcionario_id: int) -> Decimal:
        """Acerta de uma vez tudo o que está pendente para aquele garçom.

        Devolve o total repassado. Um movimento de gaveta SÓ pela parte que
        entrou em dinheiro, e um só para o acerto inteiro: o gerente paga uma
        vez, e uma linha por comanda encheria a lista de movimentos do turno
        sem dizer nada que a comanda já não diga.
        """
        self.auth.exigir_gerente()
        funcionario = self.funcionarios.buscar(funcionario_id)
        total = ZERO
        em_dinheiro = ZERO
        contas = 0
        for comanda in self.uow.comandas.listar_comissoes_pendentes():
            if comanda.atendente_id != funcionario_id:
                continue
            valor = dinheiro(comanda.valor_taxa_servico or ZERO)
            comanda.comissao_paga = True
            comanda.comissao_paga_em = datetime.now()
            self.uow.comandas.salvar(comanda)
            total += valor
            contas += 1
            if self._recebeu_em_dinheiro(comanda.id):
                em_dinheiro += valor
        if contas == 0:
            raise RegraDeNegocioError(f"{funcionario.nome} não tem comissão pendente.")
        if em_dinheiro > ZERO:
            self.caixas.registrar_repasse_comissao(
                em_dinheiro, f"Comissão de {funcionario.nome} · {contas} conta(s)"
            )
        self.uow.commit()
        return dinheiro(total)

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
