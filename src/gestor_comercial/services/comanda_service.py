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
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import (
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)


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

        funcionario = self.auth.usuario_atual()
        comanda = Comanda(
            status=StatusComanda.ABERTA,
            aberta_em=datetime.now(),
            mesa_id=mesa_id,
            funcionario_id=funcionario.id,
            caixa_id=caixa.id,
        )
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

    def calcular_total(self, comanda_id: int) -> Decimal:
        """Soma dos itens não cancelados, pelo preço congelado no lançamento."""
        self.buscar(comanda_id)
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

        self._ocupar_mesa(comanda)
        self.uow.commit()
        return item

    def remover_item(self, item_id: int) -> None:
        """Apaga o item de vez — usado para erro de digitação, antes de imprimir."""
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
    # Fechamento e cancelamento (porte de ComandaService.fechar / cancelar)
    # ------------------------------------------------------------------

    def fechar(self, comanda_id: int, pin_gerente: str | None = None) -> Comanda:
        """Fecha a comanda. Exige que ela esteja quitada, a menos que um gerente
        autorize fechar com saldo em aberto (venda fiada, brinde, erro de conta)."""
        comanda = self.buscar(comanda_id)
        if comanda.status is StatusComanda.FECHADA:
            raise RegraDeNegocioError(f"A comanda {comanda_id} já está fechada.")
        if comanda.status is not StatusComanda.ABERTA:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} foi cancelada e não pode ser fechada."
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
        total = self.calcular_total(comanda_id)
        pago = ZERO
        for pagamento in self.uow.pagamentos.listar_por_comanda(comanda_id):
            pago += dinheiro(pagamento.valor)
        return dinheiro(max(total - dinheiro(pago), ZERO))

    def cancelar(self, comanda_id: int, motivo: str, pin_gerente: str) -> Comanda:
        comanda = self.buscar(comanda_id)
        if comanda.status is StatusComanda.CANCELADA:
            raise RegraDeNegocioError(f"A comanda {comanda_id} já está cancelada.")
        if comanda.status is not StatusComanda.ABERTA:
            raise RegraDeNegocioError(
                f"A comanda {comanda_id} já foi fechada. Só é possível cancelar comanda aberta."
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
        situacao = "já foi fechada" if comanda.status is StatusComanda.FECHADA else "foi cancelada"
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
