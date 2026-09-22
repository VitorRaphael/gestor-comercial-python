"""A tela da mesa: itens à esquerda, resumo e ações à direita (§9.27).

Substitui a `ComandaView`, que era uma fileira de seis pílulas no cabeçalho
("+ Item", "2ª via", "Fechar conta", "Reabrir", "Receber pagamento", "Cancelar
comanda" — todas com o mesmo peso, a destrutiva ao lado da de receber), a linha
"Atendeu:" com um combo, duas tabelas e uma barra de TOTAL solta no pé. O
mockup do Vitor (padrão "Solvix POS") reorganiza a mesma tela em peças:

* **cabeçalho** — quem está operando, "Mesa 12", "Comanda #N · aberta há 42
  min", e "← Mesas" / "+ Adicionar item";
* **faixa** — o garçom responsável (`SeletorDeGarcom`) e a esteira
  Atendimento → Produção → Conferência → Pagamento (`EsteiraDeStatus`);
* **coluna esquerda** — "Aguardando envio", com o "Enviar à produção", e
  "Itens em produção" (`CartaoDeItens`, o mesmo cartão duas vezes);
* **coluna direita** — o `ComandaResumoWidget` e o `PainelAcoesWidget`.

Regra de negócio nenhuma mudou: cada botão chama o MESMO método de service que
chamava na tela antiga, com as mesmas travas (PIN de gerente para cancelar
item enviado, cancelar e reabrir a comanda; aviso de pendências ao sair).

## Uma leitura do banco por recarga

`atualizar()` pede ao service um `PainelDaComanda` — instantâneo imutável com
itens, totais, garçom e etapa — e todas as peças pintam a partir dele. A tela
antiga lia a `Comanda` do SQLAlchemy, uma consulta por item para o nome do
produto e a lista inteira de funcionários, a cada item lançado.

## Ciclo de vida (o RNF do Celeron)

A tela é montada uma vez, no boot, como as outras (§3.2): trocar de mesa é
`carregar_comanda()`, que troca os dados. As linhas de item são recicladas pelo
`CartaoDeItens`, e as que sobram numa troca de mesa são destruídas na hora
(`deleteLater()` depois de desligadas pelo nome). Os sinais dos botões são
ligados uma vez, na montagem — nenhum `lambda` por recarga capturando item.
O relógio do "aberta há" só corre com a tela visível e não lê o banco.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QHideEvent, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.comanda_service import ComandaService, LinhaDoPainel, PainelDaComanda
from gestor_comercial.services.exceptions import (
    AcessoNegadoError,
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
    RegraDeNegocioError,
)
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.rotulo_identidade import rotulo_do_operador
from gestor_comercial.ui.views.cancelamento_dialog import CancelamentoDialog
from gestor_comercial.ui.widgets.adicionar_item_dialog import AdicionarItemDialog
from gestor_comercial.ui.widgets.aviso_impressao import AvisoDeImpressao, executar_impressao
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_ENVIAR,
    GLIFO_MAIS,
    GLIFO_PANELA,
    GLIFO_RELOGIO,
    BotaoComGlifo,
)
from gestor_comercial.ui.widgets.comanda_resumo import ComandaResumoWidget
from gestor_comercial.ui.widgets.esteira_de_status import EsteiraDeStatus
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.itens_da_comanda import CartaoDeItens
from gestor_comercial.ui.widgets.layout_utils import rolagem_vertical
from gestor_comercial.ui.widgets.modais import executar_modal
from gestor_comercial.ui.widgets.painel_acoes import PainelAcoesWidget
from gestor_comercial.ui.widgets.seletor_de_garcom import SEM_GARCOM, OpcaoDeGarcom, SeletorDeGarcom

_ERROS_SERVICE = (RegraDeNegocioError, RecursoNaoEncontradoError, NaoAutorizadoError, AcessoNegadoError)

_NADA_NOVO_PARA_IMPRIMIR = (
    "Nada novo para a produção: todos os itens desta comanda já foram enviados."
)

# A coluna do resumo e das ações tem largura fixa: são botões e três números,
# e esticá-los num monitor largo só afastaria o rótulo do valor. Quem absorve a
# largura da janela é a coluna dos itens, onde o nome do produto precisa dela.
LARGURA_COLUNA_DIREITA_PX = 372

# O "aberta há" muda de minuto em minuto; meio minuto de atraso é o pior caso.
INTERVALO_RELOGIO_MS = 30_000

# A linha de mensagem quebra em vez de empurrar os botões do cabeçalho.
LARGURA_MAXIMA_MENSAGEM_PX = 460

# O dobro do raio das duas pílulas do cabeçalho (18px) — ver `_montar_cabecalho`.
ALTURA_BOTAO_CABECALHO_PX = 36

# A partir de um dia inteiro, "aberta há 26h40" é conta que o operador não faz
# de cabeça: vira a data e a hora em que a comanda abriu.
UM_DIA = timedelta(days=1)


def tempo_desde(inicio: datetime, agora: datetime) -> str:
    """Quanto tempo passou, do jeito que se fala no balcão: "agora", "42 min", "1h05".

    Recebe `agora` em vez de ler o relógio: quem mostra decide o instante, e o
    teste não depende da hora em que roda. Relógio do Windows voltando (horário
    de verão, acerto manual) dá "agora", e não um tempo negativo.
    """
    minutos = int((agora - inicio).total_seconds() // 60)
    if minutos < 1:
        return "agora"
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60}h{minutos % 60:02d}"


def texto_de_abertura(aberta_em: datetime, agora: datetime) -> str:
    """O pedaço do subtítulo que diz desde quando a comanda está aberta."""
    if agora - aberta_em >= UM_DIA:
        return f"aberta desde {aberta_em:%d/%m} às {aberta_em:%H:%M}"
    tempo = tempo_desde(aberta_em, agora)
    return "aberta agora" if tempo == "agora" else f"aberta há {tempo}"


class MesaDetalheView(QWidget):
    """A comanda de uma mesa (ou do balcão): itens, totais e as ações da conta."""

    voltar = Signal()
    pagamento_solicitado = Signal(int)
    comanda_cancelada = Signal(int)

    def __init__(
        self,
        comanda_service: ComandaService,
        cardapio_service: CardapioService,
        impressao_service: ImpressaoService,
        funcionario_service: FuncionarioService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._comanda_service = comanda_service
        self._cardapio_service = cardapio_service
        self._impressao_service = impressao_service
        self._funcionario_service = funcionario_service
        self._comanda_id: int | None = None
        self._painel: PainelDaComanda | None = None

        # Parent `self`: o relógio morre com a tela, e só corre com ela visível
        # (showEvent/hideEvent).
        self._relogio = QTimer(self)
        self._relogio.setInterval(INTERVALO_RELOGIO_MS)
        self._relogio.timeout.connect(self._mostrar_tempo)

        self._montar_layout()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _montar_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(self._montar_cabecalho())
        layout.addWidget(self._montar_faixa())

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        corpo.addWidget(rolagem_vertical(self._montar_coluna_itens(), "mesaDetRolagem"), 1)
        direita = rolagem_vertical(self._montar_coluna_resumo(), "mesaDetRolagem")
        direita.setFixedWidth(LARGURA_COLUNA_DIREITA_PX)
        corpo.addWidget(direita)
        layout.addLayout(corpo, 1)

        # Atalhos do envio em lote. Quem os mantém vivos é o parent (`self`),
        # não o atributo: o lado C++ pertence à tela e morre com ela (§3.13).
        self._atalho_enviar_ctrl_enter = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._atalho_enviar_ctrl_enter.activated.connect(self._imprimir_producao)
        self._atalho_enviar_f5 = QShortcut(QKeySequence("F5"), self)
        self._atalho_enviar_f5.activated.connect(self._imprimir_producao)

    def _montar_cabecalho(self) -> QHBoxLayout:
        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(10)
        bloco = QVBoxLayout()
        bloco.setSpacing(2)
        self._sobrescrito = QLabel("")
        self._sobrescrito.setObjectName("mesaDetSobrescrito")
        bloco.addWidget(self._sobrescrito)
        self._titulo = QLabel("")
        self._titulo.setObjectName("mesaDetTitulo")
        bloco.addWidget(self._titulo)
        self._subtitulo = QLabel("")
        self._subtitulo.setObjectName("mesaDetSubtitulo")
        bloco.addWidget(self._subtitulo)
        cabecalho.addLayout(bloco)
        cabecalho.addStretch()

        # A linha de mensagem e o aviso de impressão moram no cabeçalho, no vão
        # entre o título e os botões. Numa linha própria entre a faixa e as
        # colunas, os dois rótulos VAZIOS ocupavam ~70px de altura o tempo todo
        # — e a 1366x738 era essa altura que faltava para a coluna das ações
        # caber sem rolagem (medido na renderização).
        mensagens = QVBoxLayout()
        mensagens.setSpacing(2)
        self._label_erro = QLabel("")
        self._label_erro.setObjectName("labelErro")
        self._label_erro.setWordWrap(True)
        self._label_erro.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._label_erro.setMaximumWidth(LARGURA_MAXIMA_MENSAGEM_PX)
        mensagens.addWidget(self._label_erro, 0, Qt.AlignmentFlag.AlignRight)
        self._aviso_impressao = AvisoDeImpressao()
        self._aviso_impressao.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._aviso_impressao.setMaximumWidth(LARGURA_MAXIMA_MENSAGEM_PX)
        mensagens.addWidget(self._aviso_impressao, 0, Qt.AlignmentFlag.AlignRight)
        cabecalho.addLayout(mensagens)
        cabecalho.addSpacing(6)

        self._botao_voltar = QPushButton("← Mesas")
        self._botao_voltar.setProperty("variante", "pilula-voltar")
        self._botao_voltar.setToolTip("Voltar para a grade de mesas.")
        self._botao_voltar.setCursor(Qt.CursorShape.PointingHandCursor)
        # A pílula tem raio de 18px e, na altura natural (~31px), o Qt IGNORA
        # raio maior que meia altura e desenha o botão quadrado (a armadilha do
        # §9.15, vista de novo na renderização). 36px é o dobro do raio, e a
        # mesma altura do "Adicionar item" ao lado.
        self._botao_voltar.setFixedHeight(ALTURA_BOTAO_CABECALHO_PX)
        self._botao_voltar.clicked.connect(self._voltar_clicado)
        cabecalho.addWidget(self._botao_voltar, 0, Qt.AlignmentFlag.AlignVCenter)

        self._botao_add_item = BotaoComGlifo(
            "Adicionar item", GLIFO_MAIS, "acento_texto", "pilula_disabled_texto", centrado=True
        )
        self._botao_add_item.setObjectName("mesaDetBotaoAdicionar")
        self._botao_add_item.setFixedHeight(ALTURA_BOTAO_CABECALHO_PX)
        self._botao_add_item.setToolTip("Busca no cardápio e lança na comanda.")
        self._botao_add_item.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_add_item.clicked.connect(self._abrir_modal_adicionar_item)
        cabecalho.addWidget(self._botao_add_item, 0, Qt.AlignmentFlag.AlignVCenter)
        return cabecalho

    def _montar_faixa(self) -> QFrame:
        faixa = QFrame()
        faixa.setObjectName("mesaDetFaixa")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(16, 10, 18, 10)
        linha.setSpacing(16)
        self._seletor_garcom = SeletorDeGarcom(self._opcoes_de_garcom)
        self._seletor_garcom.garcom_escolhido.connect(self._ao_escolher_garcom)
        linha.addWidget(self._seletor_garcom)
        linha.addStretch()
        self._esteira = EsteiraDeStatus()
        linha.addWidget(self._esteira)
        return faixa

    def _montar_coluna_itens(self) -> QWidget:
        coluna = QWidget()
        coluna.setObjectName("mesaDetColuna")
        dentro = QVBoxLayout(coluna)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.setSpacing(14)

        self._cartao_pendentes = CartaoDeItens(
            glifo=GLIFO_RELOGIO,
            titulo="Aguardando envio",
            subtitulo="Revise os itens antes de enviar para a cozinha.",
            vazio="Nenhum item esperando envio.",
            rotulo_acao="Remover",
            # Item que a cozinha ainda não viu é rascunho, sem rastro a
            # preservar: sai direto, sem PIN e sem confirmação.
            dica_acao="Remover da lista (ainda não foi enviado à produção).",
            destaque=True,
        )
        self._botao_enviar = BotaoComGlifo(
            "Enviar à produção",
            GLIFO_ENVIAR,
            "mesa_detalhe_enviar_texto",
            "pilula_disabled_texto",
            centrado=True,
        )
        self._botao_enviar.setObjectName("mesaDetBotaoEnviar")
        self._botao_enviar.setToolTip(
            "Manda para a produção todos os itens pendentes desta comanda. (Ctrl+Enter ou F5)"
        )
        self._botao_enviar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._botao_enviar.clicked.connect(self._imprimir_producao)
        self._cartao_pendentes.adicionar_ao_cabecalho(self._botao_enviar)
        self._cartao_pendentes.acao_pedida.connect(self._remover_linha)
        dentro.addWidget(self._cartao_pendentes)

        self._cartao_enviados = CartaoDeItens(
            glifo=GLIFO_PANELA,
            titulo="Itens em produção",
            subtitulo="Já enviados e registrados na comanda.",
            vazio="Nada foi enviado para a produção ainda.",
            rotulo_acao="Cancelar",
            # Já foi para a chapa: a partir daqui é registro de auditoria, e
            # a única saída é cancelar com PIN de gerente e motivo (§3.6).
            dica_acao="Solicitar cancelamento. Já foi enviado à produção — exige senha do gerente.",
        )
        self._pilula_unidades = QLabel("")
        self._pilula_unidades.setObjectName("mesaDetPilula")
        self._cartao_enviados.adicionar_ao_cabecalho(self._pilula_unidades)
        self._cartao_enviados.acao_pedida.connect(self._cancelar_linha)
        dentro.addWidget(self._cartao_enviados)
        dentro.addStretch()
        return coluna

    def _montar_coluna_resumo(self) -> QWidget:
        coluna = QWidget()
        coluna.setObjectName("mesaDetColuna")
        dentro = QVBoxLayout(coluna)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.setSpacing(14)
        self._resumo = ComandaResumoWidget()
        dentro.addWidget(self._resumo)
        self._acoes = PainelAcoesWidget()
        self._acoes.fechar_conferencia.connect(self._gerar_conta)
        self._acoes.receber_pagamento.connect(self._solicitar_pagamento)
        self._acoes.reabrir.connect(self._reabrir_comanda)
        self._acoes.cancelar_comanda.connect(self._cancelar_comanda)
        dentro.addWidget(self._acoes)
        dentro.addStretch()
        return coluna

    # ------------------------------------------------------------------
    # Carregamento
    # ------------------------------------------------------------------

    def carregar_comanda(self, comanda: Comanda) -> None:
        """Abre a tela para uma comanda — o ponto de entrada da grade de mesas."""
        self._comanda_id = comanda.id
        self.atualizar()

    @property
    def painel(self) -> PainelDaComanda | None:
        """O instantâneo que está na tela agora."""
        return self._painel

    def atualizar(self) -> None:
        if self._comanda_id is None:
            return
        self._label_erro.setText("")
        # Qualquer mudança na comanda — outra mesa, item novo, item cancelado —
        # envelhece o aviso do último cupom. Mantê-lo faria o operador achar
        # que a cozinha já viu o item que ele acabou de lançar.
        self._aviso_impressao.limpar()
        painel = self._comanda_service.painel_da_comanda(self._comanda_id)
        self._painel = painel

        self._sobrescrito.setText(rotulo_do_operador(self._comanda_service.auth.usuario_logado))
        self._titulo.setText(painel.origem)
        self._mostrar_tempo()
        self._seletor_garcom.mostrar(painel.atendente_id, painel.atendente_nome, painel.atendente_cargo)
        self._esteira.mostrar(painel.etapa)

        self._cartao_pendentes.mostrar(painel.pendentes, acao_ligada=painel.aberta)
        self._cartao_enviados.mostrar(painel.enviados, acao_ligada=painel.aberta)
        self._pilula_unidades.setText(f"{painel.unidades_enviadas} un.")
        self._pilula_unidades.setVisible(bool(painel.enviados))
        self._resumo.mostrar(painel)
        self._acoes.mostrar(painel)

        self._botao_add_item.setEnabled(painel.aberta)
        # Envio só com algo pendente na comanda aberta — a fechada não recebe
        # mais item.
        self._botao_enviar.setEnabled(painel.aberta and bool(painel.pendentes))

    def _mostrar_tempo(self) -> None:
        """O "Comanda #N · aberta há 42 min" do cabeçalho. Não lê o banco."""
        if self._painel is None:
            return
        self._subtitulo.setText(
            f"Comanda #{self._painel.comanda_id} · {texto_de_abertura(self._painel.aberta_em, datetime.now())}"
        )

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        self._mostrar_tempo()
        self._relogio.start()

    @nao_deixa_escapar()
    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 (override Qt)
        self._relogio.stop()
        super().hideEvent(event)

    # ------------------------------------------------------------------
    # Garçom
    # ------------------------------------------------------------------

    def _opcoes_de_garcom(self) -> list[OpcaoDeGarcom]:
        """Quem pode atender (§3.11): os funcionários ativos, e o já vinculado
        mesmo que tenha sido desativado depois — senão o nome dele sumiria da
        comanda só por abrir a lista."""
        opcoes: list[OpcaoDeGarcom] = [(None, SEM_GARCOM)]
        ativos = self._funcionario_service.listar_ativos()
        painel = self._painel
        if painel is not None and painel.atendente_id is not None:
            if all(funcionario.id != painel.atendente_id for funcionario in ativos):
                opcoes.append((painel.atendente_id, painel.atendente_nome or ""))
        opcoes.extend((funcionario.id, funcionario.nome) for funcionario in ativos)
        return opcoes

    def _ao_escolher_garcom(self, funcionario_id: int | None) -> None:
        if self._painel is None:
            return
        if funcionario_id == self._painel.atendente_id:
            # Escolheu quem já estava: nada a gravar, só devolve o cartão ao
            # item único do instantâneo.
            self._seletor_garcom.mostrar(
                self._painel.atendente_id, self._painel.atendente_nome, self._painel.atendente_cargo
            )
            return
        try:
            self._comanda_service.definir_atendente(self._painel.comanda_id, funcionario_id)
        except _ERROS_SERVICE as erro:
            self.atualizar()
            self._mostrar_mensagem(str(erro), sucesso=False)
            return
        self.atualizar()

    # ------------------------------------------------------------------
    # Itens
    # ------------------------------------------------------------------

    def _mostrar_mensagem(self, texto: str, *, sucesso: bool) -> None:
        """A mesma linha serve para confirmar e para reclamar.

        Verde ou vermelho vem do QSS global (`QLabel#labelErro[tom="sucesso"]`),
        não de um `setStyleSheet` daqui: assim a linha acompanha a troca de tema
        como o resto da tela (§3.15).
        """
        aplicar_propriedade(self._label_erro, "tom", "sucesso" if sucesso else "erro")
        self._label_erro.setText(texto)

    def _remover_linha(self, linha: LinhaDoPainel) -> None:
        """Remove um item que ainda não foi para a produção — sem PIN, é rascunho."""
        try:
            for item_id in linha.item_ids:
                self._comanda_service.remover_item(item_id)
        except _ERROS_SERVICE as erro:
            self._mostrar_mensagem(str(erro), sucesso=False)
            return
        self.atualizar()
        self._mostrar_mensagem(f"{linha.nome} removido com sucesso.", sucesso=True)

    def _cancelar_linha(self, linha: LinhaDoPainel) -> None:
        """Cancela uma linha já enviada: PIN de gerente e motivo, item por item.

        A linha agrupa lançamentos do mesmo produto e preço, mas o cancelamento
        continua sendo gravado em cada `ItemComanda` por baixo — é registro de
        auditoria (§3.6).
        """
        quantos = len(linha.item_ids)
        titulo = f"Cancelar item — {linha.nome}" if quantos == 1 else f"Cancelar {quantos}x {linha.nome}"
        modal = CancelamentoDialog(titulo, self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        motivo, pin_gerente = modal.resultado()

        gerente_nome = "gerente"
        try:
            for item_id in linha.item_ids:
                item_cancelado = self._comanda_service.cancelar_item(item_id, motivo, pin_gerente)
                if item_cancelado.cancelado_por:
                    gerente_nome = item_cancelado.cancelado_por.nome
        except _ERROS_SERVICE as erro:
            self._mostrar_mensagem(str(erro), sucesso=False)
            return
        self.atualizar()
        self._mostrar_mensagem(f"Cancelamento de {linha.nome} autorizado por {gerente_nome}.", sucesso=True)

    def _abrir_modal_adicionar_item(self) -> None:
        if self._painel is None:
            return
        # `listar_produtos_para_lancamento` traz categoria e subcategoria já
        # carregadas: o modal monta o instantâneo delas na abertura e depois
        # não toca mais no SQLAlchemy (§9.4).
        produtos = self._cardapio_service.listar_produtos_para_lancamento()
        if not produtos:
            self._mostrar_mensagem("Não há produtos ativos no cardápio.", sucesso=False)
            return
        modal = AdicionarItemDialog(produtos, self._painel.origem, self._lancar_item_do_modal, self)
        executar_modal(modal)
        # O modal já lança cada item na hora (fluxo rápido de PDV); ao fechar,
        # só falta a tela conferir o que ficou nela.
        self.atualizar()

    def _lancar_item_do_modal(self, produto_id: int, quantidade: int, observacao: str | None) -> None:
        """Lança um item vindo do modal e atualiza a tela atrás dele.

        Repassa erro de regra de negócio para o modal exibir (ex.: comanda
        fechada entre um lançamento e outro) — quem decide fechar a tela
        continua sendo o operador.
        """
        assert self._comanda_id is not None
        self._comanda_service.lancar_item(self._comanda_id, produto_id, quantidade, observacao)
        self.atualizar()

    # ------------------------------------------------------------------
    # Impressão
    # ------------------------------------------------------------------

    def _imprimir_producao(self) -> bool:
        """Via de acréscimo: manda para a cozinha só o que ela ainda não viu.

        Devolve se o pedido foi registrado — é o que o "Enviar e Sair" pergunta
        antes de deixar o operador sair da mesa.
        """
        if self._comanda_id is None:
            return False
        comanda_id = self._comanda_id
        self._label_erro.setText("")
        try:
            resultados = executar_impressao(lambda: self._impressao_service.imprimir_comanda(comanda_id))
        except _ERROS_SERVICE as erro:
            # Impressora com defeito não passa por aqui: volta dentro de
            # `resultados` com sucesso=False. Aqui só chega comanda inexistente
            # ou sessão perdida, que são erro de verdade.
            self._mostrar_mensagem(str(erro), sucesso=False)
            return False
        # A impressão marca `impresso_em`: a recarga passa os itens de
        # "Aguardando envio" para "Itens em produção". Ela limpa a linha de
        # mensagem, então a confirmação só pode ser escrita depois.
        self.atualizar()
        if resultados:
            # O pedido já está confirmado (o service marca `impresso_em` do lote
            # inteiro, com ou sem impressora): a mensagem é sempre positiva, e
            # falta de papel é só o aviso âmbar logo abaixo.
            houve_falha = any(not resultado.sucesso for resultado in resultados)
            texto = (
                "Pedido registrado com sucesso! (Aviso: alguns itens não possuem "
                "impressora configurada — veja o detalhe abaixo.)"
                if houve_falha
                else "Pedido enviado para a produção com sucesso!"
            )
            self._mostrar_mensagem(texto, sucesso=True)
        self._aviso_impressao.mostrar(resultados, vazio=_NADA_NOVO_PARA_IMPRIMIR)
        return True

    # ------------------------------------------------------------------
    # Conta
    # ------------------------------------------------------------------

    def _gerar_conta(self) -> None:
        """"Gerar Conta": trava os itens e imprime a pré-conta, sem modal.

        O cartão de confirmação (§9.23) saiu: o clique já é a intenção, e o
        operador via o mesmo total que está no resumo ao lado. Quem grava o
        status continua sendo o `fechar_para_conferencia` do service.
        """
        if self._comanda_id is None:
            return
        comanda_id = self._comanda_id
        self._label_erro.setText("")
        try:
            self._comanda_service.fechar_para_conferencia(comanda_id)
        except _ERROS_SERVICE as erro:
            self._mostrar_mensagem(str(erro), sucesso=False)
            return

        try:
            resultado = executar_impressao(lambda: self._impressao_service.imprimir_pre_conta(comanda_id))
        except _ERROS_SERVICE as erro:
            self.atualizar()
            self._mostrar_mensagem(str(erro), sucesso=False)
            return

        self.atualizar()
        self._aviso_impressao.mostrar([resultado])
        if resultado.sucesso:
            self._mostrar_mensagem("Conta gerada. Pré-conta impressa — leve até a mesa.", sucesso=True)

    def _reabrir_comanda(self) -> None:
        """Volta a comanda para ABERTA, com PIN de gerente — a pré-conta já foi emitida."""
        if self._comanda_id is None:
            return
        modal = CancelamentoDialog(f"Reabrir comanda {self._comanda_id}", self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        _motivo, pin_gerente = modal.resultado()

        self._label_erro.setText("")
        try:
            self._comanda_service.reabrir(self._comanda_id, pin_gerente)
        except _ERROS_SERVICE as erro:
            self._mostrar_mensagem(str(erro), sucesso=False)
            return
        self.atualizar()
        self._mostrar_mensagem("Comanda reaberta. Itens liberados novamente.", sucesso=True)

    def _solicitar_pagamento(self) -> None:
        """"Fechar Mesa": vai ao pagamento, com ou sem pré-conta emitida.

        O `PagamentoService` só recebe conta em conferência — é o que impede
        item novo entrar numa conta sendo paga. Se o operador pulou o "Gerar
        Conta", a tela faz a mesma transição por baixo, sem imprimir. Item
        ainda não enviado à cozinha passa antes pelo aviso de pendências: a
        conferência trava a comanda, e ele ficaria preso sem ir para a chapa.
        """
        if self._comanda_id is None or self._painel is None:
            return
        if not self._painel.aberta:
            self.pagamento_solicitado.emit(self._comanda_id)
            return
        self.tentar_sair(self._conferir_e_ir_ao_pagamento)

    def _conferir_e_ir_ao_pagamento(self) -> None:
        assert self._comanda_id is not None
        comanda_id = self._comanda_id
        self._label_erro.setText("")
        try:
            self._comanda_service.fechar_para_conferencia(comanda_id)
        except _ERROS_SERVICE as erro:
            self.atualizar()
            self._mostrar_mensagem(str(erro), sucesso=False)
            return
        self.atualizar()
        self.pagamento_solicitado.emit(comanda_id)

    def _cancelar_comanda(self) -> None:
        if self._comanda_id is None:
            return
        comanda_id = self._comanda_id
        modal = CancelamentoDialog(f"Cancelar comanda {comanda_id}", self)
        if executar_modal(modal) != QDialog.DialogCode.Accepted:
            return
        motivo, pin_gerente = modal.resultado()

        self._label_erro.setText("")
        try:
            self._comanda_service.cancelar(comanda_id, motivo, pin_gerente)
        except _ERROS_SERVICE as erro:
            self._mostrar_mensagem(str(erro), sucesso=False)
            return
        self.atualizar()
        self.comanda_cancelada.emit(comanda_id)

    # ------------------------------------------------------------------
    # Saída
    # ------------------------------------------------------------------

    def _voltar_clicado(self) -> None:
        self.tentar_sair(self.voltar.emit)

    def possui_itens_pendentes(self) -> bool:
        return self._painel is not None and bool(self._painel.pendentes)

    def tentar_sair(self, ao_sair: Callable[[], None]) -> None:
        """Ponto único de saída da comanda (§ requisito 4).

        `ao_sair` só é chamado se não houver pendência, ou se o operador
        resolveu a pendência explicitamente (enviar ou descartar) — nunca
        silenciosamente. Usado tanto pelo botão "← Mesas" quanto por qualquer
        navegação externa (`MainWindow`, sidebar, logout) que tente tirar o
        operador desta tela.
        """
        if not self.possui_itens_pendentes():
            ao_sair()
            return
        self._abrir_modal_saida_com_pendencias(ao_sair)

    def _abrir_modal_saida_com_pendencias(self, ao_sair: Callable[[], None]) -> None:
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Itens pendentes")
        caixa.setText("Existem itens pendentes que não foram enviados. O que deseja fazer?")
        caixa.setIcon(QMessageBox.Icon.Warning)

        botao_enviar = caixa.addButton("Enviar e Sair", QMessageBox.ButtonRole.AcceptRole)
        botao_descartar = caixa.addButton("Descartar Pendências e Sair", QMessageBox.ButtonRole.DestructiveRole)
        botao_continuar = caixa.addButton("Continuar Editando", QMessageBox.ButtonRole.RejectRole)
        caixa.setDefaultButton(botao_enviar)
        caixa.setEscapeButton(botao_continuar)
        botao_enviar.setProperty("variante", "sucesso")
        botao_descartar.setProperty("variante", "perigo")
        botao_continuar.setProperty("variante", "secundario")

        executar_modal(caixa)
        clicado = caixa.clickedButton()

        if clicado is botao_enviar:
            # Sai só se o pedido foi registrado. A tela antiga decidia pela
            # linha de mensagem VAZIA — e o envio que dá certo escreve "Pedido
            # enviado… com sucesso!" nela, então o operador nunca saía (§9.27).
            if self._imprimir_producao():
                ao_sair()
        elif clicado is botao_descartar:
            self._descartar_pendencias(ao_sair)
        # botao_continuar (ou fechar a caixa): permanece na mesa atual.

    def _descartar_pendencias(self, ao_sair: Callable[[], None]) -> None:
        assert self._comanda_id is not None
        # Relê do banco em vez de confiar no instantâneo da tela: o que se
        # apaga tem que ser o pendente de AGORA.
        for linha in self._comanda_service.painel_da_comanda(self._comanda_id).pendentes:
            for item_id in linha.item_ids:
                self._comanda_service.remover_item(item_id)
        ao_sair()
