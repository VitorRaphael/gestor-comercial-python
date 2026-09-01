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
class LinhaConferenciaPagamento:
    """Uma linha do 'Cabeçalho Financeiro' do comprovante de fechamento.

    `esperado` é o que o sistema registrou como vendido naquela forma;
    `conferido` é o que foi de fato contado na conferência. Hoje só o
    Dinheiro tem contagem manual própria (a da gaveta) — Cartão/PIX não têm
    uma conferência independente no sistema, então `conferido` é igual a
    `esperado` para elas e a diferença sai sempre zero. É uma limitação
    conhecida, não um bug: se um dia existir conferência de maquininha por
    forma, é aqui que ela entra.
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
        # Congela o mix de vendas AGORA: é o único momento em que "o que foi
        # vendido neste turno" é uma pergunta estável. Depois de fechado, o
        # Dashboard Mensal só lê esta string — nunca mais volta em item_comanda.
        resumo_produtos_json = _serializar_resumo_produtos(self.resumo_vendas(caixa_id))

        caixa.status = StatusCaixa.FECHADO
        caixa.fechado_em = fechado_em
        caixa.valor_contado = valor
        caixa.observacao_fechamento = self._texto_ou_nulo(observacao)
        caixa.fechado_por_id = gerente.id
        caixa.numero_sequencial_dia = numero_sequencial_dia
        caixa.resumo_produtos_json = resumo_produtos_json
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
        """Quanto entrou em cada forma de pagamento — só as que tiveram venda."""
        self.buscar(caixa_id)
        totais: dict[FormaPagamento, Decimal] = {}
        for forma in FormaPagamento:
            total = self._somar(self._pagamentos(caixa_id, forma))
            if total > ZERO:
                totais[forma] = total
        return totais

    def conferencia_pagamentos(self, caixa_id: int) -> list[LinhaConferenciaPagamento]:
        """Cabeçalho financeiro do comprovante: esperado x conferido x diferença.

        Só o Dinheiro tem contagem manual própria (a da gaveta). A diferença
        apurada em `resumo().diferenca` é toda atribuída à linha de Dinheiro
        porque abertura, reforços, sangrias e despesas já entram exatas no
        cálculo do saldo esperado — qualquer sobra/falta na gaveta só pode
        vir do dinheiro em espécie que foi contado à mão. Cartão/PIX não têm
        conferência manual independente hoje: `conferido` repete `esperado`
        e a diferença sai zero.
        """
        resumo = self.resumo(caixa_id)
        conferido_fechado = resumo.valor_contado is not None

        linhas: list[LinhaConferenciaPagamento] = []
        dinheiro_conferido = (
            dinheiro(resumo.total_dinheiro + (resumo.diferenca or ZERO))
            if conferido_fechado
            else None
        )
        linhas.append(
            LinhaConferenciaPagamento(
                forma=FormaPagamento.DINHEIRO,
                rotulo="Dinheiro",
                esperado=resumo.total_dinheiro,
                conferido=dinheiro_conferido,
                diferenca=resumo.diferenca,
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
            dinheiro(sum((linha.conferido for linha in linhas), ZERO)) if conferido_fechado else None
        )
        linhas.append(
            LinhaConferenciaPagamento(
                forma=None,
                rotulo="Total",
                esperado=esperado_total,
                conferido=conferido_total,
                diferenca=resumo.diferenca,
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

    # ------------------------------------------------------------------
    # Dashboard Consolidado Mensal
    # ------------------------------------------------------------------

    def resumo_mensal(self, ano: int, mes: int) -> ResumoMensal:
        """Acumulado do mês civil (`startOfMonth`–`endOfMonth`), a partir dos
        fechamentos já registrados.

        Financeiro e cancelamentos vêm de `resumo`/`totais_por_forma` (tabelas
        `Caixa`/`Pagamento`/`MovimentoCaixa`) e `resumo_cancelamentos`. O
        ranking de produtos é o único que tocaria `item_comanda` — e por isso
        lê exclusivamente `Caixa.resumo_produtos_json`, o snapshot congelado
        por `fechar()`: nunca reabre a tabela de itens vendidos aqui. Um
        fechamento anterior a essa coluna existir (`resumo_produtos_json`
        None) simplesmente não contribui pro ranking do mês.
        """
        inicio, fim = _intervalo_do_mes(ano, mes)
        caixas = self.listar_historico(inicio=inicio, fim=fim)

        faturamento = ZERO
        por_forma: dict[FormaPagamento, Decimal] = {}
        cancelamentos_qtd = 0
        cancelamentos_valor = ZERO
        ranking: dict[str, ItemRankingMensal] = {}
        comandas_pagas = 0

        for caixa in caixas:
            resumo = self.resumo(caixa.id)
            faturamento += resumo.total_dinheiro + resumo.total_maquininha + resumo.total_consumo_interno

            for forma, valor in self.totais_por_forma(caixa.id).items():
                por_forma[forma] = por_forma.get(forma, ZERO) + valor

            cancelamentos = self.resumo_cancelamentos(caixa.id)
            cancelamentos_qtd += cancelamentos.quantidade_total
            cancelamentos_valor += cancelamentos.valor_total

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

            comandas_pagas += sum(
                1
                for comanda in self.uow.comandas.listar_por_caixa(caixa.id)
                if comanda.status is StatusComanda.FECHADA
            )

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

        return ResumoMensal(
            ano=ano,
            mes=mes,
            faturamento_bruto=faturamento,
            formas_pagamento=formas_pagamento,
            turnos_fechados=len(caixas),
            ticket_medio=ticket_medio,
            cancelamentos_quantidade=cancelamentos_qtd,
            cancelamentos_valor=dinheiro(cancelamentos_valor),
            ranking_produtos=ranking_produtos,
        )

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
