"""Comandas e seus itens: abertura, lançamento, cancelamento e fechamento.

Porte de ComandaService.java, ItemComandaService.java e da parte de status de
MesaService.java. No Java eram três services separados; aqui comanda e item
vivem no mesmo arquivo porque toda regra de item depende do status da comanda
(§3.5 e §3.6 da arquitetura) e separá-los só criaria uma dependência circular.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import StatusComanda, StatusMesa
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import (
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.transacao import transacional


@transacional
class ComandaService:
    """Abertura, itens, total, fechamento e cancelamento de comanda."""

    def __init__(self, uow: UnitOfWork, auth: AuthService) -> None:
        self.uow = uow
        self.auth = auth

    # ------------------------------------------------------------------
    # Abertura (porte de ComandaService.abrir / abrirBalcao)
    # ------------------------------------------------------------------

    def abrir_por_mesa(self, mesa_id: int) -> Comanda:
        """Abre a comanda da mesa, ou devolve a que já estiver aberta nela."""
        mesa = self.uow.mesas.buscar_por_id(mesa_id)
        if mesa is None:
            raise RecursoNaoEncontradoError(f"Mesa não encontrada (código {mesa_id}).")

        # Idempotência antes da exigência de caixa: devolver uma comanda que já
        # existe não cria nada, e travar isso deixaria a mesa inacessível se o
        # caixa fosse fechado com comanda em aberto.
        existente = self.uow.comandas.buscar_aberta_por_mesa(mesa_id)
        if existente is not None:
            return existente

        return self._criar(mesa_id=mesa_id)

    def abrir_balcao(self) -> Comanda:
        """Abre uma comanda de balcão (sem mesa), reaproveitando uma vazia se houver."""
        # Cada clique em "Balcão" no Java criava uma comanda nova, então uma
        # desistência do cliente deixava lixo aberto na tela. Reaproveitar a
        # vazia mantém a lista de comandas abertas limpa.
        for comanda in self.uow.comandas.listar_balcao_abertas():
            if not self.uow.itens.existe_na_comanda(comanda.id):
                return comanda

        return self._criar(mesa_id=None)

    def _criar(self, mesa_id: int | None) -> Comanda:
        # DIVERGÊNCIA do Java: aqui `Comanda.caixa_id` é NOT NULL, porque é o
        # vínculo que o fechamento de caixa usa para saber quais vendas são
        # dele. Sem caixa aberto não há onde pendurar a venda.
        caixa = self.uow.caixas.buscar_aberto()
        if caixa is None:
            raise RegraDeNegocioError(
                "Não há caixa aberto. Abra o caixa antes de iniciar uma comanda."
            )

        usuario = self.auth.usuario_atual()
        comanda = Comanda(
            status=StatusComanda.ABERTA,
            aberta_em=datetime.now(),
            mesa_id=mesa_id,
            usuario_id=usuario.id,
            caixa_id=caixa.id,
        )
        self.uow.comandas.salvar(comanda)
        self.uow.commit()
        return comanda

    def definir_atendente(self, comanda_id: int, funcionario_id: int | None) -> Comanda:
        """Define/troca qual `Funcionario` (garçom/atendente) atendeu a comanda.

        Independente de quem está logado (`usuario_id`, obrigatório e
        automático) — este é só o vínculo operacional de "quem atendeu",
        opcional e editável a qualquer momento enquanto a comanda existir.
        """
        comanda = self.buscar(comanda_id)
        if funcionario_id is not None:
            funcionario = self.uow.funcionarios.buscar_por_id(funcionario_id)
            if funcionario is None:
                raise RecursoNaoEncontradoError(f"Funcionário não encontrado (código {funcionario_id}).")
            if not funcionario.ativo:
                raise RegraDeNegocioError(
                    f"O funcionário {funcionario.nome} está desativado e não pode ser vinculado."
                )
        comanda.atendente_id = funcionario_id
        self.uow.comandas.salvar(comanda)
        self.uow.commit()
        return comanda

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def buscar(self, comanda_id: int) -> Comanda:
        comanda = self.uow.comandas.buscar_por_id(comanda_id)
        if comanda is None:
            raise RecursoNaoEncontradoError(f"Comanda não encontrada (código {comanda_id}).")
        return comanda

    def listar_abertas(self) -> list[Comanda]:
        """Comandas abertas que já têm item — as que aparecem na tela de atendimento.

        A comanda recém-aberta e ainda vazia fica de fora de propósito: ela é um
        rascunho, não uma venda em andamento.
        """
        return [
            comanda
            for comanda in self.uow.comandas.listar_por_status(StatusComanda.ABERTA)
            if self.uow.itens.existe_na_comanda(comanda.id)
        ]

    def listar_itens(self, comanda_id: int) -> list[ItemComanda]:
        self.buscar(comanda_id)
        return self.uow.itens.listar_por_comanda(comanda_id)

    def listar_mesas(self) -> list[Mesa]:
        """Mesas cadastradas, na ordem do número — usado pelo grid da tela inicial."""
        return self.uow.mesas.listar_todos()

    @staticmethod
    def hora_primeiro_envio(itens: list[ItemComanda]) -> datetime | None:
        """Instante em que a cozinha viu o primeiro item da comanda.

        Usado pela UI (grade de mesas e detalhe da comanda) para não fazer o
        relógio de "tempo de espera" correr enquanto o pedido ainda é
        rascunho — numa mesa grande, lançar todos os itens pode levar
        minutos, e isso não é atraso de cozinha nenhum.
        """
        enviados = [
            item.impresso_em for item in itens if not item.cancelado and item.impresso_em is not None
        ]
        return min(enviados) if enviados else None

    def calcular_total(self, comanda_id: int) -> Decimal:
        """Soma dos itens não cancelados, pelo preço congelado no lançamento.

        Não inclui taxa de serviço nem desconto — isso é `calcular_total_a_pagar`.
        """
        self.buscar(comanda_id)
        return self._calcular_subtotal(comanda_id)

    def calcular_total_a_pagar(self, comanda_id: int) -> Decimal:
        """Subtotal dos itens, com taxa de serviço somada e desconto subtraído.

        Antes da conferência (`taxa_servico_percentual` ainda `None` e
        `valor_desconto` ainda zero, valores padrão da comanda aberta) é igual
        a `calcular_total` — a conta só passa a ter taxa/desconto a partir de
        `fechar_para_conferencia`.
        """
        comanda = self.buscar(comanda_id)
        subtotal = self._calcular_subtotal(comanda_id)
        acrescimo = ZERO
        if comanda.taxa_servico_percentual:
            acrescimo = dinheiro(subtotal * dinheiro(comanda.taxa_servico_percentual) / Decimal("100"))
        desconto = dinheiro(comanda.valor_desconto or ZERO)
        # Nunca negativo: um desconto maior que a conta não pode virar crédito.
        return dinheiro(max(subtotal + acrescimo - desconto, ZERO))

    def _calcular_subtotal(self, comanda_id: int) -> Decimal:
        total = ZERO
        for item in self.uow.itens.listar_por_comanda(comanda_id):
            if not item.cancelado:
                total += dinheiro(item.preco_unit_congelado) * item.quantidade
        return dinheiro(total)

    # ------------------------------------------------------------------
    # Itens (porte de ItemComandaService.java)
    # ------------------------------------------------------------------

    def lancar_item(
        self,
        comanda_id: int,
        produto_id: int,
        quantidade: int,
        observacao: str | None = None,
    ) -> ItemComanda:
        comanda = self.buscar(comanda_id)
        self._exigir_aberta(comanda, "lançar novos itens")

        produto = self.uow.produtos.buscar_por_id(produto_id)
        if produto is None:
            raise RecursoNaoEncontradoError(f"Produto não encontrado (código {produto_id}).")
        if not produto.ativo:
            raise RegraDeNegocioError(
                f"O produto {produto.nome} está desativado e não pode ser vendido."
            )

        if isinstance(quantidade, bool) or not isinstance(quantidade, int):
            raise RegraDeNegocioError("Informe a quantidade em número inteiro.")
        if quantidade <= 0:
            raise RegraDeNegocioError("A quantidade deve ser maior que zero.")

        # A comanda existe desde o clique na mesa (precisa de linha própria
        # pra pendurar item nela), mas pro operador ela só "começa" quando o
        # primeiro item é de fato lançado — é o que marca `aberta_em` (e por
        # tabela o relógio mostrado na tela) e ocupa a mesa (`_ocupar_mesa`).
        primeiro_item = not self.uow.itens.existe_na_comanda(comanda.id)

        item = ItemComanda(
            comanda_id=comanda.id,
            produto_id=produto.id,
            quantidade=quantidade,
            # Preço congelado: se o cardápio subir de preço no meio do
            # atendimento, a conta do cliente continua a que ele viu.
            preco_unit_congelado=dinheiro(produto.preco),
            observacao=self._limpar_texto(observacao),
            cancelado=False,
        )
        self.uow.itens.salvar(item)

        if primeiro_item:
            comanda.aberta_em = datetime.now()
            self.uow.comandas.salvar(comanda)

        self._ocupar_mesa(comanda)
        self.uow.commit()
        return item

    def remover_item(self, item_id: int) -> None:
        """Apaga o item de vez — erro de digitação, só enquanto não foi impresso."""
        self.auth.usuario_atual()
        item = self._buscar_item(item_id)
        comanda = self.buscar(item.comanda_id)
        self._exigir_aberta(comanda, "remover itens")

        # Item cancelado é registro de auditoria (quem cancelou, por quê):
        # apagá-lo destruiria a única prova de que aquele cancelamento existiu.
        if item.cancelado:
            raise RegraDeNegocioError(
                "Este item já foi cancelado e não pode ser removido, para manter o histórico."
            )

        # A partir da Fase 4 "antes de imprimir" deixou de ser promessa da
        # docstring e virou fato verificável (`impresso_em`). Item que já foi
        # para a produção está sendo feito na chapa: apagá-lo aqui sumiria com a
        # venda do banco sem PIN, sem motivo e sem quem autorizou — o caminho
        # perfeito para a comida sair pela janela sem registro nenhum. Quem
        # precisa desfazer isso usa Cancelar, que exige gerente e grava tudo.
        if item.impresso_em is not None:
            raise RegraDeNegocioError(
                "Este item já foi enviado para a produção e não pode ser apagado. "
                "Use Cancelar, que registra quem autorizou e por quê."
            )

        self.uow.itens.remover(item)
        self.uow.commit()

    def cancelar_item(self, item_id: int, motivo: str, pin_gerente: str) -> ItemComanda:
        item = self._buscar_item(item_id)
        comanda = self.buscar(item.comanda_id)
        self._exigir_aberta(comanda, "cancelar itens")

        if item.cancelado:
            raise RegraDeNegocioError("Este item já está cancelado.")

        motivo_limpo = self._exigir_motivo(motivo)
        gerente = self.auth.validar_pin_gerente(pin_gerente)

        item.cancelado = True
        item.cancelado_em = datetime.now()
        item.motivo_cancelamento = motivo_limpo
        item.cancelado_por_id = gerente.id
        self.uow.itens.salvar(item)
        self.uow.commit()
        return item

    # ------------------------------------------------------------------
    # Conferência / pré-conta (fechamento do lançamento de itens)
    # ------------------------------------------------------------------

    def fechar_para_conferencia(
        self,
        comanda_id: int,
        taxa_servico_percentual: Decimal | None = None,
        desconto: Decimal | None = None,
    ) -> Comanda:
        """ABERTA -> EM_CONFERENCIA: trava novos itens e congela taxa/desconto.

        A partir daqui `lancar_item`/`remover_item`/`cancelar_item` recusam a
        comanda (mesmo caminho de `_exigir_aberta` que já barra FECHADA e
        CANCELADA) até que `reabrir` devolva o controle ao garçom. É o ponto
        em que a pré-conta pode ser impressa e o cliente pode pagar direto na
        mesa, sem passar pelo caixa central.
        """
        comanda = self.buscar(comanda_id)
        if comanda.status is not StatusComanda.ABERTA:
            situacao = {
                StatusComanda.EM_CONFERENCIA: "já está em conferência",
                StatusComanda.FECHADA: "já foi fechada",
                StatusComanda.CANCELADA: "foi cancelada",
            }[comanda.status]
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} {situacao} e não pode ser enviada para conferência."
            )

        comanda.taxa_servico_percentual = self._validar_taxa_servico(taxa_servico_percentual)
        comanda.valor_desconto = self._validar_desconto(desconto, comanda_id)
        comanda.status = StatusComanda.EM_CONFERENCIA
        comanda.em_conferencia_em = datetime.now()
        self.uow.comandas.salvar(comanda)
        self.uow.commit()
        return comanda

    def reabrir(self, comanda_id: int, pin_gerente: str) -> Comanda:
        """EM_CONFERENCIA -> ABERTA: volta a aceitar itens (conta fechada errado, cliente pediu mais).

        Exige gerente pelo mesmo motivo de `cancelar_item`: destravar uma
        comanda que já teve a pré-conta emitida ao cliente é uma decisão que
        não pode ficar na mão de qualquer atendente. Taxa e desconto voltam a
        zero — se a conta for fechada de novo, são decididos outra vez.
        """
        comanda = self.buscar(comanda_id)
        if comanda.status is not StatusComanda.EM_CONFERENCIA:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} não está em conferência e não pode ser reaberta."
            )

        self.auth.validar_pin_gerente(pin_gerente)

        comanda.status = StatusComanda.ABERTA
        comanda.em_conferencia_em = None
        comanda.taxa_servico_percentual = None
        comanda.valor_desconto = ZERO
        self.uow.comandas.salvar(comanda)
        self.uow.commit()
        return comanda

    # ------------------------------------------------------------------
    # Fechamento e cancelamento (porte de ComandaService.fechar / cancelar)
    # ------------------------------------------------------------------

    def fechar(self, comanda_id: int, pin_gerente: str | None = None) -> Comanda:
        """Fecha (quita) a comanda que já está em conferência. Exige que ela
        esteja quitada, a menos que um gerente autorize fechar com saldo em
        aberto (venda fiada, brinde, erro de conta)."""
        comanda = self.buscar(comanda_id)
        if comanda.status is StatusComanda.FECHADA:
            raise RegraDeNegocioError(f"A comanda {comanda_id} já está fechada.")
        if comanda.status is StatusComanda.CANCELADA:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} foi cancelada e não pode ser fechada."
            )
        if comanda.status is not StatusComanda.EM_CONFERENCIA:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} ainda está aberta. "
                "Feche para conferência (emita a pré-conta) antes de finalizar o pagamento."
            )

        # Fechar sem receber é a mesma classe de risco que cancelar (§3.7):
        # dinheiro que deveria entrar na gaveta simplesmente some do fechamento
        # do caixa sem deixar rastro. PagamentoService.registrar chama este
        # método sem PIN logo depois de zerar o restante — nesse caso a conta
        # já está paga e não passa por aqui.
        restante = self._restante(comanda_id)
        if restante > ZERO:
            if not pin_gerente:
                raise RegraDeNegocioError(
                    f"A comanda {comanda_id} ainda tem R$ {restante} a receber. "
                    "Registre o pagamento, ou informe o PIN do gerente para fechar mesmo assim."
                )
            self.auth.validar_pin_gerente(pin_gerente)
        else:
            self.auth.usuario_atual()

        comanda.status = StatusComanda.FECHADA
        comanda.fechada_em = datetime.now()
        self.uow.comandas.salvar(comanda)

        # A baixa de estoque que o Java fazia aqui entra só na V2 (§5 do backlog).

        self._liberar_mesa(comanda)
        self.uow.commit()
        return comanda

    def _restante(self, comanda_id: int) -> Decimal:
        total = self.calcular_total_a_pagar(comanda_id)
        pago = ZERO
        for pagamento in self.uow.pagamentos.listar_por_comanda(comanda_id):
            pago += dinheiro(pagamento.valor)
        return dinheiro(max(total - dinheiro(pago), ZERO))

    def _validar_taxa_servico(self, taxa: Decimal | None) -> Decimal | None:
        if taxa is None:
            return None
        try:
            valor = Decimal(taxa)
        except (TypeError, ValueError, ArithmeticError):
            raise RegraDeNegocioError("A taxa de serviço deve ser um percentual numérico, como 10.") from None
        if valor < ZERO or valor > Decimal("100"):
            raise RegraDeNegocioError("A taxa de serviço deve estar entre 0 e 100%.")
        return valor

    def _validar_desconto(self, desconto: Decimal | None, comanda_id: int) -> Decimal:
        if desconto is None:
            return ZERO
        valor = dinheiro(desconto)
        if valor < ZERO:
            raise RegraDeNegocioError("O desconto não pode ser negativo.")
        if valor > self._calcular_subtotal(comanda_id):
            raise RegraDeNegocioError("O desconto não pode ser maior que o total da conta.")
        return valor

    def cancelar(self, comanda_id: int, motivo: str, pin_gerente: str) -> Comanda:
        comanda = self.buscar(comanda_id)
        if comanda.status is StatusComanda.CANCELADA:
            raise RegraDeNegocioError(f"A comanda {comanda_id} já está cancelada.")
        if comanda.status is not StatusComanda.ABERTA:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} não está aberta (está {comanda.status.value}). "
                "Só é possível cancelar comanda aberta."
            )

        motivo_limpo = self._exigir_motivo(motivo)

        # DIVERGÊNCIA do Java: lá dava para cancelar uma comanda já paga, e o
        # dinheiro recebido ficava preso num registro cancelado, sem estorno.
        # Aqui o pagamento tem que ser resolvido antes.
        if self.uow.pagamentos.listar_por_comanda(comanda_id):
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} já tem pagamento registrado e não pode ser cancelada. "
                "Faça o estorno do pagamento antes."
            )

        gerente = self.auth.validar_pin_gerente(pin_gerente)
        agora = datetime.now()

        for item in self.uow.itens.listar_por_comanda(comanda_id):
            if not item.cancelado:
                item.cancelado = True
                item.cancelado_em = agora
                item.motivo_cancelamento = motivo_limpo
                item.cancelado_por_id = gerente.id
                self.uow.itens.salvar(item)

        comanda.status = StatusComanda.CANCELADA
        comanda.cancelada_em = agora
        comanda.motivo_cancelamento = motivo_limpo
        comanda.cancelado_por_id = gerente.id
        self.uow.comandas.salvar(comanda)

        self._liberar_mesa(comanda)
        self.uow.commit()
        return comanda

    # ------------------------------------------------------------------
    # Apoio
    # ------------------------------------------------------------------

    def _buscar_item(self, item_id: int) -> ItemComanda:
        item = self.uow.itens.buscar_por_id(item_id)
        if item is None:
            raise RecursoNaoEncontradoError(f"Item de comanda não encontrado (código {item_id}).")
        return item

    @staticmethod
    def _exigir_aberta(comanda: Comanda, acao: str) -> None:
        if comanda.status is StatusComanda.ABERTA:
            return
        situacao = {
            StatusComanda.EM_CONFERENCIA: "está em conferência (pré-conta já emitida)",
            StatusComanda.FECHADA: "já foi fechada",
            StatusComanda.CANCELADA: "foi cancelada",
        }[comanda.status]
        raise RegraDeNegocioError(f"A comanda {comanda.id} {situacao} e não permite {acao}.")

    @staticmethod
    def _exigir_motivo(motivo: str) -> str:
        limpo = motivo.strip() if isinstance(motivo, str) else ""
        if not limpo:
            raise RegraDeNegocioError("Informe o motivo do cancelamento.")
        return limpo

    @staticmethod
    def _limpar_texto(texto: str | None) -> str | None:
        if not isinstance(texto, str):
            return None
        return texto.strip() or None

    def _ocupar_mesa(self, comanda: Comanda) -> None:
        """Mesa vira OCUPADA no primeiro item lançado (§3.4)."""
        if comanda.mesa_id is None:
            return
        mesa = self.uow.mesas.buscar_por_id(comanda.mesa_id)
        if mesa is not None and mesa.status is StatusMesa.LIVRE:
            mesa.status = StatusMesa.OCUPADA
            self.uow.mesas.salvar(mesa)

    def _liberar_mesa(self, comanda: Comanda) -> None:
        if comanda.mesa_id is None:
            return
        mesa = self.uow.mesas.buscar_por_id(comanda.mesa_id)
        if mesa is not None and mesa.status is not StatusMesa.LIVRE:
            mesa.status = StatusMesa.LIVRE
            self.uow.mesas.salvar(mesa)
