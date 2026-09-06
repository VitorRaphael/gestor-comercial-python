"""Caixa do dia: abertura, movimentos da gaveta, conferência e fechamento.

Porte de CaixaService.java e MovimentoCaixaService.java (§3.9 e §3.10). Os dois
services do Java viraram um só aqui porque `registrar` já dependia de
`buscarAberto`: separá-los criaria duas classes que só existem uma para a outra.
"""

from __future__ import annotations

import calendar
import json
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
    TurnoAnteriorPendenteError,
)
from gestor_comercial.services.transacao import transacional

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
    valor_contado_dinheiro: Decimal | None
    diferenca_dinheiro: Decimal | None
    valor_contado_maquininha: Decimal | None
    diferenca_maquininha: Decimal | None
    quantidade_comandas: int


@dataclass(frozen=True)
class ItemCanceladoDetalhe:
    """Uma ocorrência individual de cancelamento (§ Auditoria de Itens Cancelados).

    Nível 3 do relatório: o log cronológico linha a linha.
    """

    item_id: int
    quando: datetime
    origem: str
    quantidade: int
    produto_nome: str
    valor: Decimal
    autorizado_por: str
    motivo: str | None


@dataclass(frozen=True)
class CancelamentoPorProduto:
    """Nível 2 do relatório: total cancelado de um produto no turno."""

    produto_nome: str
    quantidade: int
    valor: Decimal


@dataclass(frozen=True)
class ItemVendidoPorProduto:
    """Total vendido de um produto no turno, para a seção 'ITENS VENDIDOS NO TURNO'."""

    produto_nome: str
    quantidade: int
    valor_unitario: Decimal
    valor_total: Decimal


@dataclass(frozen=True)
class ResumoCancelamentos:
    """Fotografia dos itens cancelados de um caixa, nos três níveis do relatório."""

    caixa_id: int
    quantidade_total: int
    valor_total: Decimal
    por_produto: list[CancelamentoPorProduto]
    detalhado: list[ItemCanceladoDetalhe]


@dataclass(frozen=True)
class TotaisCancelamento:
    """Só os dois números de cancelamento de um período — quantos itens e quanto valor.

    O Dashboard Mensal não mostra o detalhe dos cancelamentos, mostra o
    totalizador. Existe separado de `ResumoCancelamentos` para o mês poder ser
    somado sem montar o relatório detalhado de cada turno (§3.6).
    """

    quantidade: int
    valor: Decimal


@dataclass(frozen=True)
class LinhaConferenciaPagamento:
    """Uma linha do 'Cabeçalho Financeiro' do comprovante de fechamento.

    `esperado` é o que o sistema registrou como vendido naquela forma;
    `conferido` é o que foi de fato contado na conferência. Dinheiro e
    Maquininha (num único valor consolidado) têm contagem manual própria;
    a conferência de maquininha não é quebrada por bandeira/forma, então
    Crédito/Débito/PIX individualmente sempre têm `conferido` igual a
    `esperado` e diferença zero — a diferença real de maquininha só aparece
    agregada na linha "Total". É uma limitação conhecida, não um bug: se um
    dia existir conferência de maquininha por forma, é aqui que ela entra.
    """

    forma: FormaPagamento | None  # None só na linha "Total".
    rotulo: str
    esperado: Decimal
    conferido: Decimal | None
    diferenca: Decimal | None


@dataclass(frozen=True)
class GrupoVendaCategoria:
    """Itens vendidos de uma categoria no turno, com totalizador do grupo."""

    categoria_nome: str
    quantidade_total: int
    valor_total: Decimal
    itens: list[ItemVendidoPorProduto]


@dataclass(frozen=True)
class TotalPorFormaMensal:
    """Uma linha do breakdown de formas de pagamento do Dashboard Mensal."""

    forma: FormaPagamento
    valor: Decimal
    percentual: Decimal


@dataclass(frozen=True)
class ItemRankingMensal:
    """Uma linha do mix de vendas do mês, ordenado por faturamento decrescente."""

    produto_nome: str
    quantidade: int
    valor_total: Decimal
    # Não faz parte do snapshot congelado (`resumo_produtos_json`, indexado só
    # por nome — o produto pode ter sido renomeado/excluído desde o
    # fechamento). Resolvido à parte em `resumo_mensal`, por nome, contra o
    # cadastro ATUAL de produtos — melhor esforço só para a miniatura da UI,
    # nunca para o valor faturado. `None` cai no placeholder normalmente.
    imagem_path: str | None = None


@dataclass(frozen=True)
class ResumoMensal:
    """Dashboard Consolidado Mensal: acumulado dos fechamentos de um mês civil."""

    ano: int
    mes: int
    faturamento_bruto: Decimal
    formas_pagamento: list[TotalPorFormaMensal]
    turnos_fechados: int
    ticket_medio: Decimal
    cancelamentos_quantidade: int
    cancelamentos_valor: Decimal
    ranking_produtos: list[ItemRankingMensal]


@dataclass(frozen=True)
class FechamentoGaveta:
    """Seção "Fechamento da Gaveta (Turno)" ao final do Histórico Diário e do
    Dashboard Mensal (§3.14): identifica o turno, o total faturado e a
    quebra/sobra apurada na conferência."""

    caixa_id: int
    identificacao: str
    total_faturado: Decimal
    saldo_apurado: Decimal
    diferenca: Decimal | None


@dataclass(frozen=True)
class ItemRankingAtendente:
    """Uma linha da seção "Performance por Atendente" (§3.14): quanto cada
    vendedor faturou no período e qual a fatia dele no total. "Balcão"
    agrupa comandas sem `atendente_id` definido."""

    atendente_nome: str
    valor_total: Decimal
    percentual: Decimal


@transacional
class CaixaService:
    """Abertura/fechamento do caixa, movimentos da gaveta e conferência (§3.9, §3.10)."""

    def __init__(self, uow: UnitOfWork, auth: AuthService) -> None:
        self.uow = uow
        self.auth = auth

    # ------------------------------------------------------------------
    # Abertura e fechamento
    # ------------------------------------------------------------------

    def abrir(
        self,
        valor_abertura: Decimal,
        senha_fechamento_cego: str | None = None,
    ) -> Caixa:
        # §3.1: o Java já documentava "atendente tentando abrir o caixa" como
        # acesso negado — quem declara o fundo de troco é quem responde por ele.
        gerente = self.auth.exigir_gerente()
        valor = self._valor_monetario(valor_abertura, "valor de abertura")
        if valor < ZERO:
            raise RegraDeNegocioError("O valor de abertura não pode ser negativo.")

        pendente = self.uow.caixas.buscar_aberto()
        if pendente is not None:
            # §3.13: trava contra esquecimento de fechamento. Sem a senha, a
            # UI mostra o aviso impeditivo e pede a senha; com ela (Master ou
            # Operacional — qualquer uma prova que quem está abrindo é
            # autorizado), o turno esquecido é fechado às cegas antes de abrir
            # o novo, sem exigir contagem real de gaveta que ninguém fez.
            if not senha_fechamento_cego:
                raise TurnoAnteriorPendenteError(
                    "Turno anterior não fechado. Deseja realizar o fechamento cego agora?"
                )
            if not (
                self.auth.loja_config.senha_master_confere(senha_fechamento_cego)
                or self.auth.loja_config.senha_operacional_confere(senha_fechamento_cego)
            ):
                raise RegraDeNegocioError(
                    "Senha incorreta para o fechamento cego do turno anterior."
                )
            self.fechar(
                pendente.id,
                valor_contado_dinheiro=ZERO,
                valor_contado_maquininha=ZERO,
                observacao="Fechamento cego (turno anterior não conferido pelo operador).",
                ignorar_comandas_abertas=True,
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

    def fechar(
        self,
        caixa_id: int,
        valor_contado_dinheiro: Decimal,
        valor_contado_maquininha: Decimal,
        observacao: str | None = None,
        ignorar_comandas_abertas: bool = False,
    ) -> Caixa:
        gerente = self.auth.exigir_gerente()
        caixa = self.buscar(caixa_id)
        if caixa.status is StatusCaixa.FECHADO:
            raise RegraDeNegocioError(f"O caixa {caixa_id} já está fechado.")

        valor_dinheiro = self._valor_monetario(valor_contado_dinheiro, "valor contado em dinheiro")
        if valor_dinheiro < ZERO:
            raise RegraDeNegocioError("O valor contado em dinheiro não pode ser negativo.")
        valor_maquininha = self._valor_monetario(
            valor_contado_maquininha, "valor contado na maquininha"
        )
        if valor_maquininha < ZERO:
            raise RegraDeNegocioError("O valor contado na maquininha não pode ser negativo.")

        # Divergência intencional do Java: fechar com mesa em aberto some com a
        # venda — a comanda fica presa num caixa que já foi conferido e o
        # dinheiro dela nunca entra em nenhum fechamento. Só conta quem tem
        # item: uma comanda ABERTA e vazia é o mesmo rascunho que
        # ComandaService.listar_abertas() já esconde (criada ao tocar na mesa
        # e desistir) — bloquear o fechamento por causa dela deixaria o
        # gerente sem como achá-la em tela nenhuma pra resolver.
        # EM_CONFERENCIA entra na mesma trava: pré-conta emitida não é
        # pagamento recebido, e o dinheiro dela some do fechamento do mesmo
        # jeito que uma comanda ABERTA esquecida.
        abertas = [
            comanda
            for comanda in self.uow.comandas.listar_por_caixa(caixa_id)
            if comanda.status in (StatusComanda.ABERTA, StatusComanda.EM_CONFERENCIA)
            and self.uow.itens.existe_na_comanda(comanda.id)
        ]
        if abertas and not ignorar_comandas_abertas:
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
        # Congela o mix de vendas AGORA: é o único momento em que "o que foi
        # vendido neste turno" é uma pergunta estável. Depois de fechado, o
        # Dashboard Mensal só lê esta string — nunca mais volta em item_comanda.
        resumo_produtos_json = _serializar_resumo_produtos(self.resumo_vendas(caixa_id))

        caixa.status = StatusCaixa.FECHADO
        caixa.fechado_em = fechado_em
        caixa.valor_contado_dinheiro = valor_dinheiro
        caixa.valor_contado_maquininha = valor_maquininha
        caixa.observacao_fechamento = self._texto_ou_nulo(observacao)
        caixa.fechado_por_id = gerente.id
        caixa.numero_sequencial_dia = numero_sequencial_dia
        caixa.resumo_produtos_json = resumo_produtos_json
        self.uow.caixas.salvar(caixa)
        self.uow.commit()
        self._proteger_o_turno_fechado()
        return caixa

    def _proteger_o_turno_fechado(self) -> None:
        """Consolida o WAL e guarda uma cópia do banco — DEPOIS do commit.

        O fechamento de caixa é o marco natural do dia: é quando o turno vira
        histórico e passa a ser a base de todo relatório. Se o banco se perder
        depois disso, o que volta é o backup daqui.

        Depende de `journal_mode=WAL` (§8): o backup usa `VACUUM INTO`, que
        grava um `.db` único já consolidado, em vez de uma cópia de arquivo que
        deixaria o `-wal` para trás. Ver `repository/backup.py`.

        Nada aqui pode derrubar o fechamento — a venda já está commitada e o
        gerente já contou a gaveta. Disco cheio, pendrive removido ou pasta sem
        permissão viram silêncio, não uma exceção que faria o `@transacional`
        desfazer o que já foi gravado.

        Trabalha sobre o banco da PRÓPRIA Session, não sobre o engine global:
        é o que faz a suíte (banco de memória) não escrever backup nenhum na
        pasta de dados de verdade.
        """
        from gestor_comercial.repository import backup

        backup.consolidar_wal(self.uow.session)
        try:
            backup.fazer_backup(origem=self.uow.session)
            backup.limpar_backups_antigos(origem=self.uow.session)
        except Exception:
            return

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
        usuario_id: int | None = None,
    ) -> list[Caixa]:
        """Fechamentos passados para a tela de Histórico, do mais recente pro mais antigo."""
        return self.uow.caixas.listar_historico(inicio=inicio, fim=fim, usuario_id=usuario_id)

    def listar_historico_mensal(self, ano: int, mes: int) -> list[Caixa]:
        """Fechamentos cuja COMPETÊNCIA (§ virada de noite) é o mês `ano`/`mes`.

        Diferente de `listar_historico`: aqui o eixo é `aberto_em`, não
        `fechado_em` — um caixa aberto às 23h e fechado de madrugada no dia
        seguinte é reportado no dia (e mês) em que foi aberto. Usado pela
        aba "Histórico Diário" da tela de Relatórios.
        """
        return self.uow.caixas.listar_por_mes_abertura(ano, mes)

    def titulo_fechamento(self, caixa_id: int) -> str:
        """'3º Fechamento do dia 26/08/2026' — identificação oficial do fechamento (§ sequência diária)."""
        caixa = self.buscar(caixa_id)
        if caixa.numero_sequencial_dia is None or caixa.fechado_em is None:
            raise RegraDeNegocioError(f"O caixa {caixa_id} ainda não foi fechado.")
        return f"{caixa.numero_sequencial_dia}º Fechamento do dia {caixa.fechado_em:%d/%m/%Y}"

    def totais_por_forma(self, caixa_id: int) -> dict[FormaPagamento, Decimal]:
        """Quanto entrou em cada forma de pagamento — só as que tiveram venda.

        Uma consulta só, separada por forma em memória: eram 5 idas ao banco
        (uma por forma) para ler as mesmas linhas (§3.6). A ordem das chaves
        continua sendo a de `FormaPagamento`, que é o que o comprovante imprime.
        """
        self.buscar(caixa_id)
        pagamentos = self.uow.pagamentos.listar_por_caixa(caixa_id)
        totais: dict[FormaPagamento, Decimal] = {}
        for forma in FormaPagamento:
            total = self._somar(self._da_forma(pagamentos, forma))
            if total > ZERO:
                totais[forma] = total
        return totais

    def conferencia_pagamentos(self, caixa_id: int) -> list[LinhaConferenciaPagamento]:
        """Cabeçalho financeiro do comprovante: esperado x conferido x diferença.

        Dinheiro e Maquininha têm cada um sua própria contagem manual
        (gaveta e extrato da maquininha, respectivamente). A diferença de
        Dinheiro (`resumo().diferenca_dinheiro`) vai na linha de Dinheiro, e a
        diferença de Maquininha (`resumo().diferenca_maquininha`) só aparece
        agregada na linha "Total" — a conferência de maquininha hoje é feita
        num único valor contado (o extrato consolidado), não por bandeira/
        forma, então Crédito/Débito/PIX individualmente continuam com
        `conferido` igual a `esperado` e diferença zero: é uma limitação
        conhecida, não um bug — se um dia existir conferência de maquininha
        por forma, é aqui que ela entra.
        """
        resumo = self.resumo(caixa_id)
        conferido_fechado = resumo.valor_contado_dinheiro is not None

        linhas: list[LinhaConferenciaPagamento] = []
        dinheiro_conferido = (
            dinheiro(resumo.total_dinheiro + (resumo.diferenca_dinheiro or ZERO))
            if conferido_fechado
            else None
        )
        linhas.append(
            LinhaConferenciaPagamento(
                forma=FormaPagamento.DINHEIRO,
                rotulo="Dinheiro",
                esperado=resumo.total_dinheiro,
                conferido=dinheiro_conferido,
                diferenca=resumo.diferenca_dinheiro,
            )
        )

        totais_forma = self.totais_por_forma(caixa_id)
        for forma, rotulo in ((FormaPagamento.CREDITO, "Cartão Crédito"),
                               (FormaPagamento.DEBITO, "Cartão Débito"),
                               (FormaPagamento.PIX, "PIX")):
            valor = totais_forma.get(forma, ZERO)
            linhas.append(
                LinhaConferenciaPagamento(
                    forma=forma,
                    rotulo=rotulo,
                    esperado=valor,
                    conferido=valor if conferido_fechado else None,
                    diferenca=ZERO if conferido_fechado else None,
                )
            )

        esperado_total = dinheiro(sum((linha.esperado for linha in linhas), ZERO))
        conferido_total = (
            dinheiro(sum((linha.conferido for linha in linhas), ZERO) + (resumo.diferenca_maquininha or ZERO))
            if conferido_fechado
            else None
        )
        diferenca_total = (
            None
            if resumo.diferenca_dinheiro is None
            else dinheiro(resumo.diferenca_dinheiro + (resumo.diferenca_maquininha or ZERO))
        )
        linhas.append(
            LinhaConferenciaPagamento(
                forma=None,
                rotulo="Total",
                esperado=esperado_total,
                conferido=conferido_total,
                diferenca=diferenca_total,
            )
        )
        return linhas

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
            usuario = self.auth.exigir_gerente()
        else:
            usuario = self.auth.usuario_atual()

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
            usuario_id=usuario.id,
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
        return self._saldo_esperado(
            caixa,
            self.uow.movimentos.listar_por_caixa(caixa_id),
            self._pagamentos(caixa_id, FormaPagamento.DINHEIRO),
        )

    def _saldo_esperado(
        self,
        caixa: Caixa,
        movimentos: list[MovimentoCaixa],
        pagamentos_em_dinheiro: list[Pagamento],
    ) -> Decimal:
        """A conta da gaveta em cima de listas JÁ carregadas.

        Separado de `calcular_saldo_esperado` só para `resumo` poder reaproveitar
        os movimentos e os pagamentos que ele mesmo acabou de ler, em vez de
        buscar tudo de novo (§3.6). A regra é a mesma; quem muda é só a origem
        dos dados.
        """
        saldo = dinheiro(caixa.valor_abertura)
        for movimento in movimentos:
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
        saldo += self._somar(pagamentos_em_dinheiro)
        return dinheiro(saldo)

    def calcular_vendas_maquininha(self, caixa_id: int) -> Decimal:
        self.buscar(caixa_id)
        return self._somar(self._pagamentos(caixa_id, *FORMAS_MAQUININHA))

    def resumo(self, caixa_id: int) -> ResumoCaixa:
        caixa = self.buscar(caixa_id)

        # Movimentos e pagamentos do turno lidos UMA vez e separados aqui
        # (§3.6). Antes, cada linha do resumo abria a sua própria consulta —
        # movimentos duas vezes, pagamentos em dinheiro duas vezes — e o
        # Dashboard Mensal repetia isso para cada turno do mês.
        movimentos = self.uow.movimentos.listar_por_caixa(caixa_id)
        pagamentos = self.uow.pagamentos.listar_por_caixa(caixa_id)

        reforcos = sangrias = despesas = ZERO
        for movimento in movimentos:
            if movimento.tipo is TipoMovimento.REFORCO:
                reforcos += dinheiro(movimento.valor)
            elif movimento.tipo is TipoMovimento.SANGRIA:
                sangrias += dinheiro(movimento.valor)
            elif movimento.tipo is TipoMovimento.DESPESA:
                despesas += dinheiro(movimento.valor)

        em_dinheiro = self._da_forma(pagamentos, FormaPagamento.DINHEIRO)
        valor_contado_dinheiro = (
            None if caixa.valor_contado_dinheiro is None else dinheiro(caixa.valor_contado_dinheiro)
        )
        valor_contado_maquininha = (
            None
            if caixa.valor_contado_maquininha is None
            else dinheiro(caixa.valor_contado_maquininha)
        )
        saldo_esperado = self._saldo_esperado(caixa, movimentos, em_dinheiro)
        total_maquininha = self._somar(self._da_forma(pagamentos, *FORMAS_MAQUININHA))

        return ResumoCaixa(
            caixa_id=caixa.id,
            valor_abertura=dinheiro(caixa.valor_abertura),
            total_dinheiro=self._somar(em_dinheiro),
            total_maquininha=total_maquininha,
            # Consumo interno é venda que nunca virou dinheiro na gaveta: fica em
            # linha própria pra explicar a diferença entre o que foi vendido e o
            # que dá pra contar na hora do fechamento.
            total_consumo_interno=self._somar(
                self._da_forma(pagamentos, FormaPagamento.CONSUMO_INTERNO)
            ),
            reforcos=reforcos,
            sangrias=sangrias,
            despesas=despesas,
            saldo_esperado=saldo_esperado,
            valor_contado_dinheiro=valor_contado_dinheiro,
            diferenca_dinheiro=(
                None
                if valor_contado_dinheiro is None
                else dinheiro(valor_contado_dinheiro - saldo_esperado)
            ),
            valor_contado_maquininha=valor_contado_maquininha,
            diferenca_maquininha=(
                None
                if valor_contado_maquininha is None
                else dinheiro(valor_contado_maquininha - total_maquininha)
            ),
            # Comandas efetivamente fechadas (pagas) no turno — mesma métrica
            # que o dashboard financeiro mostra como "COMANDAS" ao lado do
            # saldo esperado. Comandas ainda abertas/em conferência não contam
            # porque não representam venda concluída.
            quantidade_comandas=self.uow.comandas.contar_por_caixa_e_status(
                caixa_id, StatusComanda.FECHADA
            ),
        )

    # ------------------------------------------------------------------
    # Itens vendidos no turno
    # ------------------------------------------------------------------

    def resumo_vendas(self, caixa_id: int) -> list[ItemVendidoPorProduto]:
        """Itens vendidos no turno, consolidados por produto e preço praticado.

        Chave é (produto, preço unitário congelado) e não só produto: se o
        preço mudou no meio do turno, misturar as duas vendas numa linha só
        mostraria um "valor unitário" que não corresponde a nenhuma venda real.
        """
        self.buscar(caixa_id)
        itens = self.uow.itens.listar_vendidos_por_caixa(caixa_id)

        por_produto: dict[tuple[int, Decimal], ItemVendidoPorProduto] = {}
        for item in itens:
            preco_unit = dinheiro(item.preco_unit_congelado)
            chave = (item.produto_id, preco_unit)
            valor = dinheiro(preco_unit * item.quantidade)

            acumulado = por_produto.get(chave)
            if acumulado is None:
                por_produto[chave] = ItemVendidoPorProduto(
                    produto_nome=item.produto.nome,
                    quantidade=item.quantidade,
                    valor_unitario=preco_unit,
                    valor_total=valor,
                )
            else:
                por_produto[chave] = ItemVendidoPorProduto(
                    produto_nome=acumulado.produto_nome,
                    quantidade=acumulado.quantidade + item.quantidade,
                    valor_unitario=preco_unit,
                    valor_total=dinheiro(acumulado.valor_total + valor),
                )

        return list(por_produto.values())

    def resumo_vendas_por_categoria(self, caixa_id: int) -> list[GrupoVendaCategoria]:
        """Itens vendidos no turno, agrupados por Categoria, para o comprovante digital.

        Mesma consolidação de `resumo_vendas` (chave produto + preço
        congelado), só que organizada em grupos por `Produto.categoria` para
        a seção 'Produtos Vendidos' do comprovante. Categorias e produtos
        saem em ordem alfabética — não há regra de negócio de destaque de
        categoria, só previsibilidade na tela e no TXT exportado.
        """
        self.buscar(caixa_id)
        itens = self.uow.itens.listar_vendidos_por_caixa(caixa_id)

        por_categoria: dict[str, dict[tuple[int, Decimal], ItemVendidoPorProduto]] = {}
        for item in itens:
            categoria_nome = item.produto.categoria.nome
            preco_unit = dinheiro(item.preco_unit_congelado)
            chave = (item.produto_id, preco_unit)
            valor = dinheiro(preco_unit * item.quantidade)

            grupo = por_categoria.setdefault(categoria_nome, {})
            acumulado = grupo.get(chave)
            if acumulado is None:
                grupo[chave] = ItemVendidoPorProduto(
                    produto_nome=item.produto.nome,
                    quantidade=item.quantidade,
                    valor_unitario=preco_unit,
                    valor_total=valor,
                )
            else:
                grupo[chave] = ItemVendidoPorProduto(
                    produto_nome=acumulado.produto_nome,
                    quantidade=acumulado.quantidade + item.quantidade,
                    valor_unitario=preco_unit,
                    valor_total=dinheiro(acumulado.valor_total + valor),
                )

        grupos: list[GrupoVendaCategoria] = []
        for categoria_nome in sorted(por_categoria):
            itens_categoria = sorted(por_categoria[categoria_nome].values(), key=lambda i: i.produto_nome)
            grupos.append(
                GrupoVendaCategoria(
                    categoria_nome=categoria_nome,
                    quantidade_total=sum(i.quantidade for i in itens_categoria),
                    valor_total=dinheiro(sum((i.valor_total for i in itens_categoria), ZERO)),
                    itens=itens_categoria,
                )
            )
        return grupos

    # ------------------------------------------------------------------
    # Auditoria de itens cancelados (§ Auditoria de Itens Cancelados)
    # ------------------------------------------------------------------

    def resumo_cancelamentos(self, caixa_id: int) -> ResumoCancelamentos:
        """Itens cancelados no turno, nos três níveis: totalizador, por produto e detalhado.

        Só considera itens de comandas deste caixa, o que já garante o
        intervalo `aberto_em`–`fechado_em`: uma comanda só existe dentro do
        caixa em que foi aberta (`Comanda.caixa_id`), então não há como um
        cancelamento de outro turno vazar para aqui.
        """
        self.buscar(caixa_id)
        itens = self.uow.itens.listar_cancelados_por_caixa(caixa_id)

        quantidade_total = 0
        valor_total = ZERO
        por_produto: dict[int, CancelamentoPorProduto] = {}
        detalhado: list[ItemCanceladoDetalhe] = []

        for item in itens:
            valor = dinheiro(dinheiro(item.preco_unit_congelado) * item.quantidade)
            quantidade_total += item.quantidade
            valor_total += valor

            acumulado = por_produto.get(item.produto_id)
            if acumulado is None:
                por_produto[item.produto_id] = CancelamentoPorProduto(
                    produto_nome=item.produto.nome, quantidade=item.quantidade, valor=valor
                )
            else:
                por_produto[item.produto_id] = CancelamentoPorProduto(
                    produto_nome=acumulado.produto_nome,
                    quantidade=acumulado.quantidade + item.quantidade,
                    valor=dinheiro(acumulado.valor + valor),
                )

            detalhado.append(
                ItemCanceladoDetalhe(
                    item_id=item.id,
                    quando=item.cancelado_em,
                    origem=self._origem_da_comanda(item.comanda),
                    quantidade=item.quantidade,
                    produto_nome=item.produto.nome,
                    valor=valor,
                    autorizado_por=item.cancelado_por.nome if item.cancelado_por else "—",
                    motivo=item.motivo_cancelamento,
                )
            )

        return ResumoCancelamentos(
            caixa_id=caixa_id,
            quantidade_total=quantidade_total,
            valor_total=dinheiro(valor_total),
            por_produto=list(por_produto.values()),
            detalhado=detalhado,
        )

    def totais_de_cancelamento(self, caixa_ids: Iterable[int]) -> TotaisCancelamento:
        """Quantos itens e quanto valor foram cancelados no conjunto de turnos.

        Mesma conta que `resumo_cancelamentos` faz para o totalizador, só que
        para vários caixas de uma vez e sem montar as listas por produto e
        detalhada — que o Dashboard Mensal não usa (§3.6). Os valores batem
        exatamente: cada item é arredondado individualmente, como lá, e somar
        parcelas já com 2 casas não introduz arredondamento nenhum.
        """
        quantidade = 0
        valor = ZERO
        for item in self.uow.itens.listar_cancelados_por_caixas(caixa_ids):
            quantidade += item.quantidade
            valor += dinheiro(dinheiro(item.preco_unit_congelado) * item.quantidade)
        return TotaisCancelamento(quantidade=quantidade, valor=dinheiro(valor))

    # ------------------------------------------------------------------
    # Dashboard Consolidado Mensal
    # ------------------------------------------------------------------

    def resumo_mensal(self, ano: int, mes: int, usuario_id: int | None = None) -> ResumoMensal:
        """Acumulado do mês civil (`startOfMonth`–`endOfMonth`), a partir dos
        fechamentos já registrados.

        Financeiro e cancelamentos vêm de `resumo`/`totais_por_forma` (tabelas
        `Caixa`/`Pagamento`/`MovimentoCaixa`) e `totais_de_cancelamento`. O
        ranking de produtos é o único que tocaria `item_comanda` — e por isso
        lê exclusivamente `Caixa.resumo_produtos_json`, o snapshot congelado
        por `fechar()`: nunca reabre a tabela de itens vendidos aqui. Um
        fechamento anterior a essa coluna existir (`resumo_produtos_json`
        None) simplesmente não contribui pro ranking do mês.
        """
        inicio, fim = _intervalo_do_mes(ano, mes)
        caixas = self.listar_historico(inicio=inicio, fim=fim, usuario_id=usuario_id)

        faturamento = ZERO
        # Semeia com todas as formas em ZERO: o Dashboard Mensal precisa
        # listar PIX/Consumo interno mesmo sem venda no mês — diferente de
        # `totais_por_forma` (usado no comprovante de um único caixa), que
        # omite de propósito as formas sem movimento.
        por_forma: dict[FormaPagamento, Decimal] = {forma: ZERO for forma in FormaPagamento}
        # Cancelamentos do mês inteiro numa consulta só, fora do laço (§3.6).
        cancelamentos = self.totais_de_cancelamento(caixa.id for caixa in caixas)
        ranking: dict[str, ItemRankingMensal] = {}
        comandas_pagas = 0

        for caixa in caixas:
            resumo = self.resumo(caixa.id)
            faturamento += resumo.total_dinheiro + resumo.total_maquininha + resumo.total_consumo_interno

            for forma, valor in self.totais_por_forma(caixa.id).items():
                por_forma[forma] = por_forma.get(forma, ZERO) + valor

            for vendido in _desserializar_resumo_produtos(caixa.resumo_produtos_json):
                atual = ranking.get(vendido.produto_nome)
                if atual is None:
                    ranking[vendido.produto_nome] = vendido
                else:
                    ranking[vendido.produto_nome] = ItemRankingMensal(
                        produto_nome=atual.produto_nome,
                        quantidade=atual.quantidade + vendido.quantidade,
                        valor_total=dinheiro(atual.valor_total + vendido.valor_total),
                    )

            # `resumo` já contou as comandas fechadas do turno; contar de novo
            # aqui era uma consulta idêntica por turno do mês (§3.6).
            comandas_pagas += resumo.quantidade_comandas

        faturamento = dinheiro(faturamento)
        formas_pagamento = [
            TotalPorFormaMensal(
                forma=forma,
                valor=valor,
                percentual=dinheiro((valor / faturamento) * 100) if faturamento > ZERO else ZERO,
            )
            for forma, valor in por_forma.items()
        ]
        ticket_medio = dinheiro(faturamento / comandas_pagas) if comandas_pagas > 0 else ZERO
        ranking_produtos = sorted(ranking.values(), key=lambda item: item.valor_total, reverse=True)
        ranking_produtos = self._com_imagem_atual(ranking_produtos)

        return ResumoMensal(
            ano=ano,
            mes=mes,
            faturamento_bruto=faturamento,
            formas_pagamento=formas_pagamento,
            turnos_fechados=len(caixas),
            ticket_medio=ticket_medio,
            cancelamentos_quantidade=cancelamentos.quantidade,
            cancelamentos_valor=cancelamentos.valor,
            ranking_produtos=ranking_produtos,
        )

    def _com_imagem_atual(self, ranking: list[ItemRankingMensal]) -> list[ItemRankingMensal]:
        """Preenche `imagem_path` casando por nome contra o cadastro atual.

        Melhor esforço, não fonte de verdade: um produto renomeado ou
        excluído depois do fechamento simplesmente fica sem foto no ranking
        (cai no placeholder da UI), o número de faturamento não é afetado.
        """
        if not ranking:
            return ranking
        imagem_por_nome = {produto.nome: produto.imagem_path for produto in self.uow.produtos.listar_todos()}
        return [
            ItemRankingMensal(
                produto_nome=item.produto_nome,
                quantidade=item.quantidade,
                valor_total=item.valor_total,
                imagem_path=imagem_por_nome.get(item.produto_nome),
            )
            for item in ranking
        ]

    def listar_fechamentos_do_mes_civil(
        self, ano: int, mes: int, usuario_id: int | None = None
    ) -> list[Caixa]:
        """Os mesmos fechamentos que `resumo_mensal(ano, mes, usuario_id)` agrega
        internamente (eixo `fechado_em`) — exposto para quem, como o
        Dashboard Mensal, precisa dos ids dos turnos além dos totais já
        prontos, para alimentar `ranking_por_atendente`/
        `fechamento_da_gaveta_do_periodo` sem duplicar o cálculo do intervalo."""
        inicio, fim = _intervalo_do_mes(ano, mes)
        return self.listar_historico(inicio=inicio, fim=fim, usuario_id=usuario_id)

    # ------------------------------------------------------------------
    # Fechamento da Gaveta e Performance por Atendente (§3.14)
    # ------------------------------------------------------------------

    def identificacao_turno(self, caixa: Caixa) -> str:
        """"Caixa Turno - Noite" etc. (§3.1): o turno é identificado pelo
        PERÍODO em que foi aberto, não por quem operou — é o nome que
        pertence à operação/gaveta, não ao CPF de um funcionário específico.
        Período deriva da hora de `aberto_em` (heurística simples: sem
        cadastro de escala no sistema, é a única informação que já existe
        pra todo turno, aberto ou fechado)."""
        return f"Caixa Turno - {periodo_do_turno(caixa.aberto_em)}"

    def fechamento_da_gaveta(self, caixa_id: int) -> FechamentoGaveta:
        """Fotografia enxuta de um turno já fechado, para a seção "Fechamento
        da Gaveta" no rodapé do Histórico Diário/Dashboard Mensal."""
        caixa = self.buscar(caixa_id)
        resumo = self.resumo(caixa_id)

        if caixa.numero_sequencial_dia is not None and caixa.fechado_em is not None:
            identificacao = (
                f"{self.identificacao_turno(caixa)} · T{caixa.numero_sequencial_dia}"
                f" — {caixa.fechado_em:%d/%m/%Y}"
            )
        else:
            identificacao = self.identificacao_turno(caixa)

        saldo_apurado = ZERO
        if resumo.valor_contado_dinheiro is not None:
            saldo_apurado += resumo.valor_contado_dinheiro
        if resumo.valor_contado_maquininha is not None:
            saldo_apurado += resumo.valor_contado_maquininha

        diferenca = None
        if resumo.diferenca_dinheiro is not None and resumo.diferenca_maquininha is not None:
            diferenca = dinheiro(resumo.diferenca_dinheiro + resumo.diferenca_maquininha)

        return FechamentoGaveta(
            caixa_id=caixa_id,
            identificacao=identificacao,
            total_faturado=_faturamento_total_de(resumo),
            saldo_apurado=dinheiro(saldo_apurado),
            diferenca=diferenca,
        )

    def fechamento_da_gaveta_do_periodo(self, caixa_ids: Iterable[int]) -> FechamentoGaveta:
        """Agrega `fechamento_da_gaveta` de todos os turnos de um período
        (mês do Histórico Diário ou do Dashboard Mensal) numa única linha —
        évita a pergunta "qual dos N turnos listados é O fechamento da
        seção?" quando o período tem mais de um turno."""
        ids = list(caixa_ids)
        total_faturado = ZERO
        saldo_apurado = ZERO
        diferenca_acumulada = ZERO
        diferenca_valida = bool(ids)

        gavetas = [self.fechamento_da_gaveta(caixa_id) for caixa_id in ids]
        for gaveta in gavetas:
            total_faturado += gaveta.total_faturado
            saldo_apurado += gaveta.saldo_apurado
            if gaveta.diferenca is None:
                diferenca_valida = False
            else:
                diferenca_acumulada += gaveta.diferenca

        if not ids:
            identificacao = "Nenhum turno fechado no período"
        elif len(ids) == 1:
            # Reaproveita a gaveta que o laço acabou de montar: recalculá-la
            # aqui refazia o `resumo()` inteiro do turno de graça (§3.6).
            identificacao = gavetas[0].identificacao
        else:
            identificacao = f"{len(ids)} turnos fechados no período"

        return FechamentoGaveta(
            caixa_id=ids[0] if len(ids) == 1 else 0,
            identificacao=identificacao,
            total_faturado=dinheiro(total_faturado),
            saldo_apurado=dinheiro(saldo_apurado),
            diferenca=dinheiro(diferenca_acumulada) if diferenca_valida else None,
        )

    def ranking_por_atendente(self, caixa_ids: Iterable[int]) -> list[ItemRankingAtendente]:
        """Vendas do período agrupadas por quem atendeu a comanda
        (`Comanda.atendente_id`), para a seção "Performance por Atendente".

        Uma comanda sem atendente definido (venda direta de balcão, sem
        vincular ninguém) entra no grupo "Balcão" em vez de ser descartada —
        senão a soma dos grupos nunca bateria com o faturamento total do
        período. A base de cada comanda é a soma de TODOS os pagamentos dela
        (qualquer forma, inclusive consumo interno), a mesma definição de
        "faturado" usada em `resumo`/`_faturamento_total_de`.
        """
        totais: dict[str, Decimal] = {}
        # Uma consulta para o período inteiro, com comanda e atendente já
        # carregados (§3.6). Antes era um turno por vez, e o ORM ia buscar a
        # comanda de cada pagamento sob demanda: só esta seção respondia por
        # mais de mil consultas num mês cheio.
        for pagamento in self.uow.pagamentos.listar_por_caixas_com_atendente(caixa_ids):
            atendente = pagamento.comanda.atendente
            nome = atendente.nome if atendente is not None else "Balcão"
            totais[nome] = totais.get(nome, ZERO) + dinheiro(pagamento.valor)

        faturamento_total = dinheiro(sum(totais.values(), ZERO))
        itens = [
            ItemRankingAtendente(
                atendente_nome=nome,
                valor_total=dinheiro(valor),
                percentual=(
                    dinheiro((valor / faturamento_total) * 100) if faturamento_total > ZERO else ZERO
                ),
            )
            for nome, valor in totais.items()
        ]
        return sorted(itens, key=lambda item: item.valor_total, reverse=True)

    @staticmethod
    def _origem_da_comanda(comanda) -> str:
        """'Mesa 04' ou 'Balcão #12' — de onde veio o item cancelado."""
        mesa = getattr(comanda, "mesa", None)
        if mesa is None:
            return f"Balcão #{comanda.id}"
        return f"Mesa {mesa.numero:02d}"

    # ------------------------------------------------------------------

    def _pagamentos(self, caixa_id: int, *formas: FormaPagamento) -> list[Pagamento]:
        return self.uow.pagamentos.listar_por_caixa(caixa_id, formas=list(formas))

    @staticmethod
    def _da_forma(pagamentos: list[Pagamento], *formas: FormaPagamento) -> list[Pagamento]:
        """Filtra em memória a mesma lista que `_pagamentos` filtraria no banco.

        Para quem já tem os pagamentos do turno na mão, separar por forma aqui
        custa nada e economiza uma ida ao banco por forma (§3.6). A ordem é a
        mesma da consulta original (`Pagamento.id`), porque a lista de entrada
        já vem ordenada assim.
        """
        return [pagamento for pagamento in pagamentos if pagamento.forma in formas]

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


def periodo_do_turno(momento: datetime) -> str:
    """Manhã (05h-11h59) / Tarde (12h-17h59) / Noite (18h-04h59) — heurística
    de food truck (sem cadastro de escala), usada por `identificacao_turno`."""
    hora = momento.hour
    if 5 <= hora < 12:
        return "Manhã"
    if 12 <= hora < 18:
        return "Tarde"
    return "Noite"


def _faturamento_total_de(resumo: ResumoCaixa) -> Decimal:
    """Mesma regra da linha "Total" de `conferencia_pagamentos` — duplicada
    aqui (e em `historico_caixa_view._faturamento_total`) de propósito: são
    duas camadas diferentes (service/view) que não devem depender uma da
    outra só por essa conta de uma linha."""
    return resumo.total_dinheiro + resumo.total_maquininha + resumo.total_consumo_interno


def _intervalo_do_mes(ano: int, mes: int) -> tuple[date, date]:
    """`startOfMonth`/`endOfMonth` do mês civil, para filtrar `listar_historico`."""
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, 1), date(ano, mes, ultimo_dia)


def _serializar_resumo_produtos(itens: list[ItemVendidoPorProduto]) -> str:
    """`Caixa.resumo_produtos_json` no fechamento — `Decimal` vira `str` porque
    `json` não serializa `Decimal` nativamente, e `str` preserva a casa
    decimal exata (float arredondaria o centavo)."""
    return json.dumps(
        [
            {
                "produto_nome": item.produto_nome,
                "quantidade": item.quantidade,
                "valor_total": str(item.valor_total),
            }
            for item in itens
        ]
    )


def _desserializar_resumo_produtos(bruto: str | None) -> list[ItemRankingMensal]:
    """Lê de volta o snapshot gravado por `_serializar_resumo_produtos`.

    `None`/vazio/JSON corrompido viram lista vazia — um fechamento sem
    snapshot (anterior a esta coluna, ou dado sujo) só fica fora do ranking
    daquele mês, nunca derruba o dashboard inteiro.
    """
    if not bruto:
        return []
    try:
        dados = json.loads(bruto)
    except (TypeError, ValueError):
        return []
    itens = []
    for linha in dados:
        try:
            itens.append(
                ItemRankingMensal(
                    produto_nome=linha["produto_nome"],
                    quantidade=linha["quantidade"],
                    valor_total=dinheiro(linha["valor_total"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return itens
