"""Comanda de produção, recibo do cliente e fechamento de caixa no papel (§3.12).

Porte de RoteamentoImpressaoService.java + ImpressaoService.java. No Java eram
dois services e a impressão era simulada com `log.info`: nada chegava na
cozinha. Aqui o roteamento (agrupar os itens por impressora da categoria)
continua sendo a regra central, mas o cupom sai de verdade pela camada
`hardware/`.

Este service é o único lugar que sabe **o que** cada cupom mostra. Ele não sabe
contar coluna (isso é do `formatador_cupom`) nem falar ESC/POS (isso é do
`hardware/impressora_escpos`). O que ele guarda são as três regras que custam
dinheiro se estiverem erradas:

1. Item de categoria sem impressora não pode sumir — vai pra padrão, e se não
   houver padrão vira aviso na tela, não silêncio.
2. `impresso_em` é marcado no clique de "Enviar Pedido", não no sucesso do
   papel: persistência do pedido (o item sair de "Pendentes" e virar venda de
   verdade) é a regra principal, e não pode depender de impressora ligada.
   DIVERGÊNCIA de uma versão anterior deste service, que só marcava o que
   saiu no papel — isso deixava o item preso em "Pendentes" para sempre
   sempre que a categoria não tinha impressora configurada, travando o PDV
   por causa de um problema de hardware/cadastro. Falha de impressão agora é
   só o `ResultadoImpressao.sucesso=False` que vira aviso âmbar na tela; quem
   quer repapelar usa "2ª via" (`reimprimir_comanda`), que não olha
   `impresso_em` e não depende do pedido ainda estar pendente.
3. Impressora quebrada não derruba a venda (RNF inegociável de §2): o cliente
   paga e vai embora mesmo que a cozinha tenha que ouvir o pedido gritado.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from gestor_comercial.core.resilience import logger_do_app
from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import FormaPagamento, StatusCaixa
from gestor_comercial.domain.fila_impressao import ItemFilaImpressao
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.hardware.impressora_escpos import (
    BlocoTexto,
    Documento,
    DriverImpressora,
    ErroDeImpressao,
    ParametrosImpressora,
    documento_de_json,
    documento_para_json,
)
from gestor_comercial.hardware.impressora_escpos import abrir_driver as abrir_driver_escpos
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services import formatador_cupom as cupom
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.caixa_service import (
    FORMAS_MAQUININHA,
    CaixaService,
    ItemVendidoPorProduto,
    ResumoCaixa,
    ResumoCancelamentos,
)
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import RecursoNaoEncontradoError
from gestor_comercial.services.transacao import transacional

# Assinatura da fábrica de driver que o `ImpressaoService` aceita. Existe para
# a costura de teste ter nome: a suíte injeta um driver falso e exercita todo o
# roteamento sem impressora, sem `escpos` e sem arquivo em disco.
AbridorDeDriver = Callable[..., AbstractContextManager[DriverImpressora]]

# Nome do grupo cujos itens não têm para onde ir. Aparece na tela do operador
# junto com o motivo, para ele saber qual categoria configurar.
GRUPO_SEM_IMPRESSORA = "SEM IMPRESSORA DEFINIDA"

# Teto de espera da thread de impressão, com folga sobre os 3 s do driver.
# A folga é proposital: no caso normal quem responde primeiro é a mensagem
# específica do `hardware/` ("sem papel", "cabo solto"), que diz ao operador o
# que fazer. Este teto é o último recurso, para o driver que não devolve nunca.
TEMPO_MAXIMO_DE_IMPRESSAO = 6.0

# Como a thread de impressão é esperada. Recebe a thread e o teto em segundos.
EsperaDeThread = Callable[[threading.Thread, float], None]


def _aguardar_simples(thread: threading.Thread, teto_s: float) -> None:
    """Espera bloqueante — o padrão para a suíte e para uso sem interface."""
    thread.join(teto_s)


# Rótulos escritos por extenso e acentuados: o cupom é lido pelo cliente, não
# pelo programador. Um `.value.capitalize()` daria "Consumo_interno".
ROTULO_FORMA_PAGAMENTO = {
    FormaPagamento.DINHEIRO: "Dinheiro",
    FormaPagamento.CREDITO: "Cartão de crédito",
    FormaPagamento.DEBITO: "Cartão de débito",
    FormaPagamento.PIX: "PIX",
    FormaPagamento.CONSUMO_INTERNO: "Consumo interno",
}


@dataclass(frozen=True)
class ResultadoImpressao:
    """O que aconteceu com um cupom, para a tela contar ao operador.

    Nunca é exceção: mesmo a falha vem por aqui, com `sucesso=False` e a
    mensagem já pronta para aparecer na barra de avisos.
    """

    impressora_nome: str
    quantidade_itens: int
    sucesso: bool
    erro: str | None = None


@dataclass
class _GrupoDeImpressao:
    """Os itens de uma comanda que saem juntos, no mesmo cupom.

    `impressora=None` é o grupo órfão: itens sem destino nenhum. `motivos`
    guarda, por categoria, por que cada um ficou órfão — é o texto que vira
    instrução acionável na tela.
    """

    impressora: Impressora | None
    itens: list[ItemComanda] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)


@transacional
class ImpressaoService:
    """Roteia e imprime comanda de produção, recibo do cliente e fechamento (§3.12)."""

    def __init__(
        self,
        uow: UnitOfWork,
        auth: AuthService,
        abrir_driver: AbridorDeDriver = abrir_driver_escpos,
        aguardar: EsperaDeThread = _aguardar_simples,
    ) -> None:
        self.uow = uow
        self.auth = auth
        # `aguardar` é como a thread de impressão é esperada (Fase 3). O padrão
        # é `join()` puro, que serve para a suíte e para qualquer uso sem Qt; a
        # UI injeta uma espera que mantém a tela repintando, para o operador
        # nunca ver a janela branca de "Não Está Respondendo". A escolha mora
        # aqui, e não dentro do service, porque `services/` não importa Qt.
        self._aguardar = aguardar
        # `abrir_driver` injetável é a costura de teste: a suíte passa um driver
        # falso e exercita todo o roteamento sem impressora, sem escpos e sem
        # arquivo em disco.
        self._abrir_driver = abrir_driver
        # ComandaService e CaixaService são construídos aqui, e não recebidos no
        # __init__, porque a conta de dinheiro do cupom (total da comanda, saldo
        # esperado do caixa) já está escrita neles — refazer a soma aqui criaria
        # uma segunda verdade sobre o mesmo valor. Ambos compartilham o mesmo
        # UnitOfWork, então continua tudo na mesma Session.
        self._comandas = ComandaService(uow, auth)
        self._caixas = CaixaService(uow, auth)

    # ------------------------------------------------------------------
    # Comanda de produção (porte de RoteamentoImpressaoService.java)
    # ------------------------------------------------------------------

    def imprimir_comanda(self, comanda_id: int) -> list[ResultadoImpressao]:
        """Via de acréscimo: manda pra produção só o que a cozinha ainda não viu.

        Lista vazia significa "não havia nada novo" — é o caso normal de quem
        clica em Imprimir duas vezes seguidas, não um erro.
        """
        comanda = self._buscar_comanda(comanda_id)
        itens = self.uow.itens.listar_nao_impressos_por_comanda(comanda.id)
        if not itens:
            return []

        agora = datetime.now()
        resultados = self._imprimir_grupos(comanda, itens, agora, segunda_via=False)

        # `impresso_em` marca TODOS os itens do lote, sucesso ou não: a
        # confirmação do pedido (sair de "Pendentes") não pode ficar refém de
        # impressora configurada/ligada. O item que não imprimiu já aparece
        # em `resultados` com `sucesso=False` — a tela mostra isso como aviso
        # âmbar (AvisoDeImpressao), nunca como bloqueio do lançamento.
        for item in itens:
            item.impresso_em = agora
            self.uow.itens.salvar(item)
        self.uow.commit()  # commit único, depois de todos os grupos
        return resultados

    def reimprimir_comanda(self, comanda_id: int) -> list[ResultadoImpressao]:
        """2ª via: repete a comanda inteira e não mexe em `impresso_em`.

        É a ação de quando o cupom rasgou, borrou ou se perdeu na cozinha —
        o que já foi enviado continua marcado como enviado.
        """
        comanda = self._buscar_comanda(comanda_id)
        itens = [
            item for item in self.uow.itens.listar_por_comanda(comanda.id) if not item.cancelado
        ]
        if not itens:
            return []

        resultados = self._imprimir_grupos(comanda, itens, datetime.now(), segunda_via=True)
        return resultados

    # ------------------------------------------------------------------
    # Recibo do cliente
    # ------------------------------------------------------------------

    def imprimir_recibo(self, comanda_id: int) -> ResultadoImpressao:
        """Recibo do cliente, sempre na impressora padrão (a do balcão)."""
        comanda = self._buscar_comanda(comanda_id)
        itens = [
            item for item in self.uow.itens.listar_por_comanda(comanda.id) if not item.cancelado
        ]

        padrao = self.uow.impressoras.buscar_padrao()
        if padrao is None:
            return self._sem_impressora_padrao("o recibo do cliente", len(itens))

        documento = self._documento_recibo(comanda, itens, padrao, datetime.now())
        return self._enviar(padrao, documento, len(itens), "Recibo do cliente")

    # ------------------------------------------------------------------
    # Pré-conta (fechamento para conferência)
    # ------------------------------------------------------------------

    def imprimir_pre_conta(self, comanda_id: int) -> ResultadoImpressao:
        """Extrato de conferência: o garçom leva até a mesa, cliente confere e paga.

        Diferente de `imprimir_recibo` (que mostra o que já foi pago e o que
        falta), este cupom não lista pagamento nenhum — a comanda em
        EM_CONFERENCIA ainda não recebeu baixa. Sempre na impressora padrão,
        igual ao recibo: é o cupom do cliente, não o da cozinha.
        """
        comanda = self._buscar_comanda(comanda_id)
        itens = [
            item for item in self.uow.itens.listar_por_comanda(comanda.id) if not item.cancelado
        ]

        padrao = self.uow.impressoras.buscar_padrao()
        if padrao is None:
            return self._sem_impressora_padrao("a pré-conta", len(itens))

        documento = self._documento_pre_conta(comanda, itens, padrao, datetime.now())
        return self._enviar(padrao, documento, len(itens), "Pré-conta")

    # ------------------------------------------------------------------
    # Fechamento de caixa
    # ------------------------------------------------------------------

    def imprimir_fechamento_caixa(self, caixa_id: int) -> ResultadoImpressao:
        """Relatório de conferência da gaveta, na impressora padrão."""
        self.auth.usuario_atual()
        caixa = self._caixas.buscar(caixa_id)

        padrao = self.uow.impressoras.buscar_padrao()
        if padrao is None:
            return self._sem_impressora_padrao("o fechamento de caixa", 0)

        # Toda a conta vem pronta de CaixaService.resumo: abertura, totais por
        # forma, movimentos da gaveta, saldo esperado e diferença. Recalcular
        # qualquer uma delas aqui criaria um relatório que diverge da tela.
        resumo = self._caixas.resumo(caixa.id)
        resumo_vendas = self._caixas.resumo_vendas(caixa.id)
        resumo_cancelamentos = self._caixas.resumo_cancelamentos(caixa.id)
        documento = self._documento_fechamento(
            caixa, resumo, resumo_vendas, resumo_cancelamentos, padrao, datetime.now()
        )
        return self._enviar(padrao, documento, 0, "Fechamento de caixa")

    # ------------------------------------------------------------------
    # Teste de impressora
    # ------------------------------------------------------------------

    def imprimir_teste(self, impressora_id: int) -> ResultadoImpressao:
        """Cupom de conferência da tela de Impressoras: cabo, papel e largura."""
        self.auth.usuario_atual()
        impressora = self.uow.impressoras.buscar_por_id(impressora_id)
        if impressora is None:
            raise RecursoNaoEncontradoError(f"Impressora não encontrada (código {impressora_id}).")

        # Impressora desativada não é barrada aqui de propósito: o teste existe
        # justamente para o gerente conferir o cabo antes de reativá-la.
        documento = self._documento_teste(impressora, datetime.now())
        return self._enviar(impressora, documento, 0, "Teste de impressora")

    # ------------------------------------------------------------------
    # Roteamento (porte de RoteamentoImpressaoService.rotear)
    # ------------------------------------------------------------------

    def _imprimir_grupos(
        self,
        comanda: Comanda,
        itens: list[ItemComanda],
        agora: datetime,
        segunda_via: bool,
    ) -> list[ResultadoImpressao]:
        """Imprime um cupom por impressora e devolve um resultado por grupo.

        Quem chama decide o que fazer com o resultado — `imprimir_comanda`
        confirma o pedido de qualquer jeito e só usa isto pra montar o aviso
        na tela; nenhum item fica esperando o papel sair para virar venda.
        """
        resultados: list[ResultadoImpressao] = []

        for grupo in self._agrupar_por_impressora(itens):
            if grupo.impressora is None:
                resultados.append(
                    ResultadoImpressao(
                        impressora_nome=GRUPO_SEM_IMPRESSORA,
                        quantidade_itens=len(grupo.itens),
                        sucesso=False,
                        erro=self._erro_do_grupo_orfao(grupo),
                    )
                )
                continue

            documento = self._documento_producao(comanda, grupo, agora, segunda_via)
            resultados.append(
                self._enviar(
                    grupo.impressora,
                    documento,
                    len(grupo.itens),
                    f"Comanda {self._destino_da_comanda(comanda)}",
                )
            )

        return resultados

    def _agrupar_por_impressora(self, itens: list[ItemComanda]) -> list[_GrupoDeImpressao]:
        """Agrupa por `item.produto.categoria.impressora`, na ordem de lançamento.

        O dict comum do Python preserva a ordem de inserção, que é a mesma razão
        pela qual o Java usava LinkedHashMap: a cozinha lê o cupom na sequência
        em que o atendente digitou.
        """
        padrao = self.uow.impressoras.buscar_padrao()
        grupos: dict[int | None, _GrupoDeImpressao] = {}

        for item in itens:
            impressora, motivo = self._destino_do_item(item, padrao)
            chave = None if impressora is None else impressora.id
            grupo = grupos.get(chave)
            if grupo is None:
                grupo = _GrupoDeImpressao(impressora=impressora)
                grupos[chave] = grupo
            grupo.itens.append(item)
            if motivo is not None and motivo not in grupo.motivos:
                grupo.motivos.append(motivo)

        return list(grupos.values())

    @staticmethod
    def _destino_do_item(
        item: ItemComanda, padrao: Impressora | None
    ) -> tuple[Impressora | None, str | None]:
        """Descobre em qual impressora este item sai, e por que ficou sem uma.

        DIVERGÊNCIA do Java: lá o item de categoria sem impressora ia pro grupo
        SEM_IMPRESSORA_DEFINIDA, que só era logado — ou seja, o pedido nunca
        chegava na cozinha e ninguém ficava sabendo. Aqui ele cai na impressora
        padrão, e só vira aviso na tela quando nem padrão existe: comida que
        ninguém faz é pior do que um aviso.
        """
        categoria = getattr(item.produto, "categoria", None)
        nome_categoria = getattr(categoria, "nome", None) or "sem categoria"
        impressora = getattr(categoria, "impressora", None)

        # Impressora desativada pelo gerente também cai no fallback: ele desligou
        # aquele destino, não a comanda.
        if impressora is not None and impressora.ativa:
            return impressora, None
        if padrao is not None:
            return padrao, None
        if impressora is None:
            return None, f"a categoria '{nome_categoria}' não tem impressora associada"
        return None, (
            f"a impressora '{impressora.nome}' da categoria '{nome_categoria}' está desativada"
        )

    @staticmethod
    def _erro_do_grupo_orfao(grupo: _GrupoDeImpressao) -> str:
        motivos = "; ".join(grupo.motivos) or "estes itens não têm impressora"
        return (
            f"{len(grupo.itens)} item(ns) não foram impressos porque {motivos}. "
            "Associe uma impressora a essas categorias no Cardápio, ou marque uma "
            "impressora como padrão na tela de Impressoras."
        )

    # ------------------------------------------------------------------
    # Envio (a única fronteira com o hardware)
    # ------------------------------------------------------------------

    def _enviar(
        self,
        impressora: Impressora,
        documento: Documento,
        quantidade_itens: int,
        descricao: str = "Cupom",
    ) -> ResultadoImpressao:
        """Manda o cupom pro papel e transforma qualquer falha em resultado.

        Fronteira única com o hardware, e por isso o lugar certo para as duas
        garantias da Fase 3: **a UI não congela** e **o cupom não se perde**.

        A conversa com o periférico roda numa thread (`_falar_com_o_periferico`),
        e o que falhou é guardado em `fila_impressao_pendente` para o operador
        reimprimir depois. Nada disso muda o contrato de quem chama: continua
        devolvendo um `ResultadoImpressao` síncrono, e continua sem levantar.
        """
        erro = self._falar_com_o_periferico(impressora, documento)
        if erro is None:
            return ResultadoImpressao(impressora.nome, quantidade_itens, True)

        # O cupom não sai no papel, mas não some: fica na fila. É a metade que
        # faltava do RNF de §2 — antes disto, recuperar o pedido dependia de o
        # operador achar a comanda e clicar "2ª via" à mão, no meio do pico.
        self._guardar_na_fila(impressora, documento, descricao, erro)
        return ResultadoImpressao(impressora.nome, quantidade_itens, False, erro)

    def _falar_com_o_periferico(
        self, impressora: Impressora, documento: Documento
    ) -> str | None:
        """Abre o driver e imprime **fora da thread da UI**. Devolve o erro, ou `None`.

        Aqui mora a resolução do conflito registrado em `Mitigação de Falhas.md`
        §1.4. A Fase 4 da remasterização proibiu, por escrito, mandar a impressão
        para outra thread: o app inteiro vive sobre um único `UnitOfWork`, e
        `Session` não é thread-safe — trocaríamos 3 segundos de tela congelada
        por corrupção silenciosa do banco do food truck. A proibição continua
        valendo na íntegra.

        O que atravessa para a thread não é a impressão inteira: é só a metade
        que fala com o cabo. Montar o documento (que lê comanda, itens, produtos)
        já aconteceu, na thread da UI. O que vai daqui para lá são duas coisas
        imutáveis e sem vínculo nenhum com o SQLAlchemy: o `ParametrosImpressora`
        (retrato dos dados de conexão, tirado na linha abaixo) e o `Documento`,
        que é `list[BlocoTexto]` — `frozen=True`, só str e bool.

        **Nenhuma `Session` cruza fronteira de thread.** Quem espera é o
        chamador, via `self._aguardar`: a suíte e qualquer uso sem Qt usam o
        `join()` simples; a UI injeta uma espera que mantém a tela repintando
        (ver `ui/widgets/aviso_impressao.py`).
        """
        parametros = ParametrosImpressora.de(impressora)
        nome = impressora.nome
        recado: list[str | None] = [None]

        def trabalho() -> None:
            try:
                with self._abrir_driver(parametros) as driver:
                    driver.imprimir(documento)
            except ErroDeImpressao as erro:
                recado[0] = str(erro)
            except Exception as erro:  # noqa: BLE001 - último cinto de segurança do RNF
                # `hardware/` promete só levantar ErroDeImpressao, mas se um dia
                # escapar outra coisa dali a venda não pode cair junto. Mensagem
                # diferente de propósito: "erro inesperado" é o sinal de que a
                # falha é nossa, não do cabo da impressora.
                recado[0] = f"Erro inesperado ao imprimir em '{nome}': {erro}"

        # `daemon=True`: se o driver travar apesar de todos os timeouts da camada
        # `hardware/`, o processo ainda tem que conseguir fechar quando o dono do
        # food truck clicar no X. Uma thread pendurada não pode segurar o PDV.
        thread = threading.Thread(target=trabalho, name="impressao", daemon=True)
        thread.start()
        self._aguardar(thread, TEMPO_MAXIMO_DE_IMPRESSAO)

        if thread.is_alive():
            # Folga proposital sobre os 3 s do driver: assim, no caso normal, quem
            # responde é a mensagem específica do `hardware/` ("sem papel", "cabo
            # solto"), que diz ao operador o que fazer. Esta aqui é o último
            # recurso, para o driver que não devolve nunca.
            return (
                f"A impressora '{nome}' não respondeu em "
                f"{TEMPO_MAXIMO_DE_IMPRESSAO:.0f} segundos. Verifique se ela está "
                "ligada e conectada; o cupom ficou salvo na fila."
            )
        return recado[0]

    def _guardar_na_fila(
        self, impressora: Impressora, documento: Documento, descricao: str, erro: str
    ) -> None:
        """Salva o cupom que não saiu, para a 2ª via não depender de memória humana.

        **Nunca levanta.** Falhar ao guardar o cupom não pode virar o segundo
        problema em cima do primeiro: a venda já está commitada e o cliente já
        foi embora. No pior caso o operador perde a fila, que é onde ele já
        estava antes desta fase existir.
        """
        try:
            self.uow.fila_impressao.salvar(
                ItemFilaImpressao(
                    impressora_id=impressora.id,
                    documento=documento_para_json(documento),
                    descricao=descricao[:120],
                    ultimo_erro=erro[:400],
                )
            )
            self.uow.fila_impressao.podar_excedente()
            # `commit` aqui, e não no fim da operação: dos cinco caminhos de
            # impressão só `imprimir_comanda` commita, e o cupom guardado não
            # pode depender de qual botão o operador apertou. É o registro de
            # que algo não saiu no papel — ele tem que sobreviver inclusive a um
            # rollback da operação que o gerou.
            self.uow.commit()
        except Exception:  # noqa: BLE001
            logger_do_app().exception("Não foi possível guardar o cupom na fila")

    # ------------------------------------------------------------------
    # Fila de contingência (Fase 3)
    # ------------------------------------------------------------------

    def listar_fila(self) -> list[ItemFilaImpressao]:
        """Os cupons que não saíram, do mais antigo para o mais novo."""
        return self.uow.fila_impressao.listar_pendentes()

    def reimprimir_da_fila(self, item_id: int) -> ResultadoImpressao:
        """Tenta de novo um cupom guardado. Só sai da fila se sair no papel.

        O item **não** é removido antes da tentativa: se a impressora continuar
        muda, o cupom tem que continuar lá. O que sobe é `tentativas`, para a
        tela poder mostrar quantas vezes já se tentou.
        """
        item = self.uow.fila_impressao.buscar_por_id(item_id)
        if item is None:
            raise RecursoNaoEncontradoError(f"Cupom {item_id} não está mais na fila.")

        impressora = self.uow.impressoras.buscar_por_id(item.impressora_id)
        if impressora is None:
            raise RecursoNaoEncontradoError(
                "A impressora deste cupom não existe mais no cadastro. "
                "Cadastre-a de novo, ou descarte o cupom."
            )

        documento = documento_de_json(item.documento)
        erro = self._falar_com_o_periferico(impressora, documento)
        if erro is not None:
            item.tentativas += 1
            item.ultimo_erro = erro[:400]
            self.uow.fila_impressao.salvar(item)
            return ResultadoImpressao(impressora.nome, 0, False, erro)

        self.uow.fila_impressao.remover(item)
        return ResultadoImpressao(impressora.nome, 0, True)

    def descartar_da_fila(self, item_id: int) -> None:
        """Joga fora um cupom que não interessa mais (o cliente já foi, o dia virou)."""
        item = self.uow.fila_impressao.buscar_por_id(item_id)
        if item is not None:
            self.uow.fila_impressao.remover(item)

    # ------------------------------------------------------------------
    # Montagem dos documentos
    # ------------------------------------------------------------------

    def _documento_producao(
        self,
        comanda: Comanda,
        grupo: _GrupoDeImpressao,
        agora: datetime,
        segunda_via: bool,
    ) -> Documento:
        """Cupom da cozinha: o que produzir, para qual mesa, em que ordem."""
        impressora = grupo.impressora
        largura = cupom.largura_util(impressora.colunas)

        # O nome da impressora é texto de tamanho livre como qualquer outro
        # (`impressoras.nome` aceita 80 caracteres e a bobina pode ter 20), e é
        # logo a primeira linha do cupom — a que diz para qual praça o pedido
        # vai. Sem quebrar, a impressora corta o excedente e o cabeçalho mente.
        documento: Documento = [
            BlocoTexto(linha, negrito=True, centralizado=True)
            for linha in cupom.quebrar(impressora.nome.upper(), largura)
        ]
        if segunda_via:
            documento.append(BlocoTexto("2ª VIA", negrito=True, centralizado=True))

        # Mesa em dobro: é a única informação que a cozinha precisa ler de longe,
        # de dentro do vapor da chapa, sem chegar perto do cupom.
        documento.append(
            BlocoTexto(self._destino_da_comanda(comanda), dobro=True, centralizado=True)
        )
        documento.append(
            BlocoTexto(cupom.duas_colunas(f"Comanda {comanda.id}", cupom.hora(agora), largura))
        )
        # Passa pelo `quebrar` como qualquer outro texto de tamanho livre:
        # `funcionarios.nome` aceita 120 caracteres e a bobina tem 32.
        for linha in cupom.quebrar(f"Atendente: {self._nome_do_atendente(comanda)}", largura):
            documento.append(BlocoTexto(linha))
        documento.append(BlocoTexto(cupom.separador(largura)))

        # Consolida itens idênticos (mesmo produto e mesma observação) antes de
        # renderizar: "1x Coca" + "1x Coca" na mesma comanda vira "2x Coca" no
        # papel, e não duas linhas repetidas confundindo a cozinha.
        agrupados = cupom.agrupar_itens_producao(
            [
                (item.produto.id, item.produto.nome, item.quantidade, item.observacao)
                for item in grupo.itens
            ]
        )
        descricoes = {item.produto.id: item.produto.descricao for item in grupo.itens}

        for produto_id, nome, quantidade, observacao in agrupados:
            for linha in cupom.linha_de_item(quantidade, nome, largura):
                # Nome do item em negrito: é o que a cozinha procura primeiro.
                documento.append(BlocoTexto(linha, negrito=True))
            for linha in cupom.linha_secundaria(descricoes.get(produto_id), largura):
                documento.append(BlocoTexto(linha))
            # "[!]" chama atenção do cozinheiro pra uma instrução que muda o
            # preparo padrão — negrito exclusivo desta linha, é o que não pode
            # passar batido no meio da correria. Descrição e observação nunca
            # imprimem nada quando vazias: `linha_secundaria` devolve lista
            # vazia, sem placeholder e sem linha em branco no papel.
            for linha in cupom.linha_secundaria(observacao, largura, prefixo="[!] OBS: "):
                documento.append(BlocoTexto(linha, negrito=True))

        documento.append(BlocoTexto(cupom.separador(largura)))
        total_itens = sum(quantidade for _, _, quantidade, _ in agrupados)
        documento.append(
            BlocoTexto(cupom.duas_colunas("TOTAL DE ITENS", str(total_itens), largura))
        )
        documento.append(BlocoTexto(cupom.separador(largura)))
        return documento

    def _documento_recibo(
        self,
        comanda: Comanda,
        itens: list[ItemComanda],
        impressora: Impressora,
        agora: datetime,
    ) -> Documento:
        """Recibo do cliente: o que ele levou, quanto deu e como pagou."""
        largura = cupom.largura_util(impressora.colunas)
        total = self._comandas.calcular_total(comanda.id)
        pagos_por_forma, troco, total_pago = self._pagamentos_da_comanda(comanda.id)

        documento: Documento = [
            BlocoTexto("RECIBO", negrito=True, centralizado=True),
            BlocoTexto(
                f"Comanda {comanda.id} - {self._destino_da_comanda(comanda)}",
                centralizado=True,
            ),
            BlocoTexto(cupom.data_hora(agora), centralizado=True),
            BlocoTexto(cupom.separador(largura)),
        ]

        for item in itens:
            valor = dinheiro(item.preco_unit_congelado) * item.quantidade
            for linha in cupom.linha_de_item(
                item.quantidade, item.produto.nome, largura, valor=valor
            ):
                documento.append(BlocoTexto(linha))
            for linha in cupom.linha_secundaria(item.observacao, largura):
                documento.append(BlocoTexto(linha))

        documento.append(BlocoTexto(cupom.separador(largura)))
        documento.append(
            BlocoTexto(
                cupom.duas_colunas("TOTAL", f"R$ {cupom.moeda(total)}", largura, preenchimento="."),
                negrito=True,
            )
        )

        if pagos_por_forma:
            documento.append(BlocoTexto(cupom.separador(largura, titulo="PAGAMENTO")))
            for forma, valor in pagos_por_forma.items():
                rotulo = ROTULO_FORMA_PAGAMENTO.get(forma, forma.value)
                documento.append(BlocoTexto(cupom.linha_de_valor(rotulo, valor, largura)))
            if troco > ZERO:
                documento.append(BlocoTexto(cupom.linha_de_valor("Troco", troco, largura)))

        restante = dinheiro(max(total - total_pago, ZERO))
        if restante > ZERO:
            # Comanda fechada por gerente com saldo em aberto (§3.7): o cupom
            # tem que mostrar o que ficou faltando, senão vira o único registro
            # de uma venda que parece paga.
            documento.append(
                BlocoTexto(cupom.linha_de_valor("A RECEBER", restante, largura), negrito=True)
            )

        documento.append(BlocoTexto(cupom.separador(largura)))
        for linha in cupom.quebrar(f"Atendente: {self._nome_do_atendente(comanda)}", largura):
            documento.append(BlocoTexto(linha))
        # O rodapé também é quebrado: na bobina de 20 colunas — largura válida no
        # cadastro — nenhuma das duas frases cabe inteira, e texto estourado sai
        # cortado pela impressora, não continuado na linha de baixo.
        for texto in ("Não é documento fiscal", "Obrigado e volte sempre!"):
            for linha in cupom.quebrar(texto, largura):
                documento.append(BlocoTexto(linha, centralizado=True))
        return documento

    def _documento_pre_conta(
        self,
        comanda: Comanda,
        itens: list[ItemComanda],
        impressora: Impressora,
        agora: datetime,
    ) -> Documento:
        """Extrato de conferência: itens, subtotal, taxa/desconto e total a pagar.

        Sem seção de pagamento — a conta ainda não foi quitada. O rodapé
        avisa explicitamente que isto não substitui o recibo/pagamento, para
        o cliente não confundir a pré-conta com prova de quitação.
        """
        largura = cupom.largura_util(impressora.colunas)
        subtotal = self._comandas.calcular_total(comanda.id)
        total_a_pagar = self._comandas.calcular_total_a_pagar(comanda.id)

        documento: Documento = [
            BlocoTexto("CONFERÊNCIA", negrito=True, centralizado=True),
            BlocoTexto(
                f"Comanda {comanda.id} - {self._destino_da_comanda(comanda)}",
                centralizado=True,
            ),
            BlocoTexto(
                f"Aberta em: {cupom.data_hora(comanda.aberta_em)}"
                if comanda.aberta_em
                else "",
            ),
        ]
        if comanda.em_conferencia_em is not None:
            documento.append(
                BlocoTexto(f"Fechada em: {cupom.data_hora(comanda.em_conferencia_em)}")
            )
        documento.append(BlocoTexto(cupom.separador(largura)))

        for item in itens:
            valor = dinheiro(item.preco_unit_congelado) * item.quantidade
            for linha in cupom.linha_de_item(
                item.quantidade, item.produto.nome, largura, valor=valor
            ):
                documento.append(BlocoTexto(linha))
            for linha in cupom.linha_secundaria(item.observacao, largura):
                documento.append(BlocoTexto(linha))

        documento.append(BlocoTexto(cupom.separador(largura)))
        documento.append(BlocoTexto(cupom.linha_de_valor("Subtotal", subtotal, largura)))

        if comanda.taxa_servico_percentual:
            valor_taxa = dinheiro(total_a_pagar - subtotal + dinheiro(comanda.valor_desconto or ZERO))
            rotulo = f"Taxa de serviço ({cupom.moeda(comanda.taxa_servico_percentual)}%)"
            documento.append(BlocoTexto(cupom.linha_de_valor(rotulo, valor_taxa, largura)))
        if comanda.valor_desconto:
            documento.append(BlocoTexto(cupom.linha_de_valor("Desconto", -dinheiro(comanda.valor_desconto), largura)))

        documento.append(
            BlocoTexto(
                cupom.duas_colunas(
                    "TOTAL A PAGAR", f"R$ {cupom.moeda(total_a_pagar)}", largura, preenchimento="."
                ),
                negrito=True,
            )
        )

        documento.append(BlocoTexto(cupom.separador(largura)))
        for linha in cupom.quebrar(f"Atendente: {self._nome_do_atendente(comanda)}", largura):
            documento.append(BlocoTexto(linha))
        for texto in ("Conferência - Não é documento fiscal", "Pague na mesa ou no caixa"):
            for linha in cupom.quebrar(texto, largura):
                documento.append(BlocoTexto(linha, centralizado=True))
        return documento

    def _documento_fechamento(
        self,
        caixa: Caixa,
        resumo: ResumoCaixa,
        resumo_vendas: list[ItemVendidoPorProduto],
        resumo_cancelamentos: ResumoCancelamentos,
        impressora: Impressora,
        agora: datetime,
    ) -> Documento:
        """Relatório de conferência da gaveta, com os números do `CaixaService`."""
        largura = cupom.largura_util(impressora.colunas)

        documento: Documento = [BlocoTexto("FECHAMENTO DE CAIXA", negrito=True, centralizado=True)]
        if caixa.numero_sequencial_dia is not None and caixa.fechado_em is not None:
            # Identificação oficial do fechamento (§ sequência diária): indexada
            # por `fechado_em`, é o número que a contabilidade usa pra achar
            # este turno depois — não existe enquanto o caixa está aberto.
            documento.append(
                BlocoTexto(self._caixas.titulo_fechamento(caixa.id), centralizado=True)
            )
        documento.append(BlocoTexto(f"Caixa {caixa.id}", centralizado=True))
        documento.extend([
            BlocoTexto(cupom.duas_colunas("Aberto em", cupom.data_hora(caixa.aberto_em), largura)),
            BlocoTexto(
                cupom.duas_colunas(
                    "Fechado em",
                    cupom.data_hora(caixa.fechado_em) if caixa.fechado_em else "em aberto",
                    largura,
                )
            ),
            BlocoTexto(cupom.separador(largura)),
            BlocoTexto(cupom.linha_de_valor("Valor de abertura", resumo.valor_abertura, largura)),
            BlocoTexto(cupom.separador(largura, titulo="VENDAS")),
            BlocoTexto(cupom.linha_de_valor("Dinheiro", resumo.total_dinheiro, largura)),
        ])

        # `resumo` já traz o total da maquininha somado; a quebra por bandeira é
        # detalhe que só existe aqui, porque é o que o gerente confere contra o
        # extrato da máquina no fim da noite.
        detalhe = self._detalhe_da_maquininha(caixa.id)
        for rotulo, valor in detalhe:
            documento.append(BlocoTexto(cupom.linha_de_valor(rotulo, valor, largura)))
        if len(detalhe) != 1:
            # Com uma forma só de cartão, a linha dela já É o total da
            # maquininha, e repetir o mesmo número confunde quem está conferindo.
            documento.append(
                BlocoTexto(cupom.linha_de_valor("Maquininha", resumo.total_maquininha, largura))
            )
        documento.append(
            BlocoTexto(
                cupom.linha_de_valor("Consumo interno", resumo.total_consumo_interno, largura)
            )
        )
        documento.append(
            BlocoTexto(
                cupom.linha_de_valor(
                    "Total em vendas",
                    dinheiro(
                        resumo.total_dinheiro
                        + resumo.total_maquininha
                        + resumo.total_consumo_interno
                    ),
                    largura,
                )
            )
        )

        documento.append(BlocoTexto(cupom.separador(largura, titulo="GAVETA")))
        documento.append(BlocoTexto(cupom.linha_de_valor("Reforços", resumo.reforcos, largura)))
        documento.append(BlocoTexto(cupom.linha_de_valor("Sangrias", resumo.sangrias, largura)))
        documento.append(BlocoTexto(cupom.linha_de_valor("Despesas", resumo.despesas, largura)))

        documento.append(BlocoTexto(cupom.separador(largura)))
        documento.append(
            BlocoTexto(
                cupom.duas_colunas(
                    "SALDO ESPERADO",
                    f"R$ {cupom.moeda(resumo.saldo_esperado)}",
                    largura,
                    preenchimento=".",
                ),
                negrito=True,
            )
        )

        if resumo.valor_contado_dinheiro is None:
            # Caixa ainda aberto: o relatório serve de conferência parcial, e a
            # linha de assinatura é onde o gerente anota o que contou na mão.
            documento.append(
                BlocoTexto(cupom.duas_colunas("Valor contado (Dinheiro)", "_" * 10, largura))
            )
            documento.append(
                BlocoTexto(cupom.duas_colunas("Valor contado (Maquininha)", "_" * 10, largura))
            )
        else:
            documento.append(
                BlocoTexto(
                    cupom.linha_de_valor(
                        "Valor contado (Dinheiro)", resumo.valor_contado_dinheiro, largura
                    )
                )
            )
            documento.append(
                BlocoTexto(
                    cupom.linha_de_valor(
                        "Diferença (Dinheiro)",
                        ZERO if resumo.diferenca_dinheiro is None else resumo.diferenca_dinheiro,
                        largura,
                    ),
                    negrito=True,
                )
            )
            documento.append(
                BlocoTexto(
                    cupom.linha_de_valor(
                        "Valor contado (Maquininha)", resumo.valor_contado_maquininha, largura
                    )
                )
            )
            documento.append(
                BlocoTexto(
                    cupom.linha_de_valor(
                        "Diferença (Maquininha)",
                        ZERO if resumo.diferenca_maquininha is None else resumo.diferenca_maquininha,
                        largura,
                    ),
                    negrito=True,
                )
            )
        # As duas anotações do turno, na ordem em que aconteceram. A de abertura
        # é a que explica o fundo de troco declarado ("fundo recebido do
        # cofre"), e é justamente na conferência da gaveta que alguém precisa
        # dela — sem esta linha, ela ficaria gravada e nunca lida.
        if caixa.observacao_abertura:
            for linha in cupom.linha_secundaria(
                caixa.observacao_abertura, largura, prefixo="Obs. abertura: "
            ):
                documento.append(BlocoTexto(linha))
        if caixa.observacao_fechamento:
            for linha in cupom.linha_secundaria(
                caixa.observacao_fechamento, largura, prefixo="Obs: "
            ):
                documento.append(BlocoTexto(linha))

        documento.extend(self._secao_vendas(resumo_vendas, largura))
        documento.extend(self._secao_cancelamentos(resumo_cancelamentos, largura))

        documento.append(BlocoTexto(cupom.separador(largura)))
        situacao = "FECHADO" if caixa.status is StatusCaixa.FECHADO else "ABERTO"
        documento.append(BlocoTexto(cupom.duas_colunas("Situação", situacao, largura)))
        # Os dois operadores do turno: quem declarou o fundo de troco pode não
        # ser quem conferiu a gaveta no fim, e o histórico depende de mostrar
        # os dois nomes, não só quem está segurando a impressão agora.
        if caixa.aberto_por is not None:
            for linha in cupom.quebrar(f"Aberto por: {caixa.aberto_por.nome}", largura):
                documento.append(BlocoTexto(linha))
        if caixa.fechado_por is not None:
            for linha in cupom.quebrar(f"Fechado por: {caixa.fechado_por.nome}", largura):
                documento.append(BlocoTexto(linha))
        documento.append(
            BlocoTexto(cupom.duas_colunas("Impresso em", cupom.data_hora(agora), largura))
        )
        for linha in cupom.quebrar(
            f"Conferido por: {self.auth.usuario_atual().nome}", largura
        ):
            documento.append(BlocoTexto(linha))
        return documento

    @staticmethod
    def _secao_vendas(itens: list[ItemVendidoPorProduto], largura: int) -> Documento:
        """'ITENS VENDIDOS NO TURNO': quantidade, preço unitário praticado e subtotal por produto."""
        documento: Documento = [
            BlocoTexto(cupom.separador(largura, titulo="ITENS VENDIDOS NO TURNO"))
        ]

        if not itens:
            for linha in cupom.quebrar("Nenhum item vendido neste turno.", largura):
                documento.append(BlocoTexto(linha))
            return documento

        for item in itens:
            for linha in cupom.linha_de_venda(
                item.quantidade, item.produto_nome, item.valor_unitario, largura
            ):
                documento.append(BlocoTexto(linha))

        return documento

    @staticmethod
    def _secao_cancelamentos(resumo: ResumoCancelamentos, largura: int) -> Documento:
        """'ITENS CANCELADOS NO TURNO': totalizador, consolidado por produto e log cronológico.

        Os três níveis da auditoria de estornos (§ Auditoria de Itens
        Cancelados): quanto sumiu no total, o que sumiu por produto, e quem
        autorizou cada ocorrência — nesta ordem, do resumo pro detalhe.
        """
        documento: Documento = [
            BlocoTexto(cupom.separador(largura, titulo="ITENS CANCELADOS NO TURNO"))
        ]

        if resumo.quantidade_total == 0:
            for linha in cupom.quebrar("Nenhum item cancelado neste turno.", largura):
                documento.append(BlocoTexto(linha))
            return documento

        documento.append(
            BlocoTexto(
                cupom.duas_colunas("Qtd cancelada", f"{resumo.quantidade_total} un", largura)
            )
        )
        documento.append(
            BlocoTexto(cupom.linha_de_valor("Valor cancelado", resumo.valor_total, largura), negrito=True)
        )

        documento.append(BlocoTexto(cupom.separador(largura, titulo="Por produto")))
        for produto in resumo.por_produto:
            for linha in cupom.linha_de_item(
                produto.quantidade, produto.produto_nome, largura, valor=produto.valor
            ):
                documento.append(BlocoTexto(linha))

        documento.append(BlocoTexto(cupom.separador(largura, titulo="Detalhado")))
        for ocorrencia in resumo.detalhado:
            documento.append(
                BlocoTexto(cupom.duas_colunas(cupom.hora(ocorrencia.quando), ocorrencia.origem, largura))
            )
            for linha in cupom.linha_de_item(ocorrencia.quantidade, ocorrencia.produto_nome, largura):
                documento.append(BlocoTexto(linha))
            for linha in cupom.linha_secundaria(
                f"Autorizado por: {ocorrencia.autorizado_por}", largura
            ):
                documento.append(BlocoTexto(linha))
            for linha in cupom.linha_secundaria(ocorrencia.motivo, largura, prefixo="Motivo: "):
                documento.append(BlocoTexto(linha))

        return documento

    def _documento_teste(self, impressora: Impressora, agora: datetime) -> Documento:
        """Cupom de teste: prova cabo, papel, acento e largura de uma vez só."""
        largura = cupom.largura_util(impressora.colunas)
        tipo = getattr(impressora.tipo_conexao, "value", impressora.tipo_conexao)

        documento: Documento = [BlocoTexto("TESTE DE IMPRESSÃO", negrito=True, centralizado=True)]
        # Mesmo motivo do cupom de produção: nome comprido estouraria a bobina.
        for linha in cupom.quebrar(impressora.nome, largura):
            documento.append(BlocoTexto(linha, centralizado=True))

        documento.extend([
            BlocoTexto(cupom.separador(largura)),
            BlocoTexto(cupom.duas_colunas("Conexão", str(tipo), largura)),
            BlocoTexto(cupom.duas_colunas("Largura", f"{largura} colunas", largura)),
            BlocoTexto(cupom.duas_colunas("Data", cupom.data_hora(agora), largura)),
            BlocoTexto(cupom.separador(largura)),
            BlocoTexto("Texto normal: ação, pão, café."),
            BlocoTexto("Texto em negrito", negrito=True),
            BlocoTexto("MESA 12", dobro=True, centralizado=True),
            BlocoTexto(cupom.separador(largura)),
            BlocoTexto(cupom.regua(largura)),
        ])
        # A instrução também é quebrada: numa bobina de 32 colunas a frase tem
        # quase o triplo da largura, e sair cortada justamente no cupom que
        # ensina a conferir a largura seria irônico demais.
        for linha in cupom.quebrar(
            f"Se a régua acima ocupou uma linha só, a largura de {largura} "
            "colunas está correta para esta bobina.",
            largura,
        ):
            documento.append(BlocoTexto(linha))
        documento.append(BlocoTexto(cupom.separador(largura)))
        return documento

    # ------------------------------------------------------------------
    # Apoio
    # ------------------------------------------------------------------

    def _buscar_comanda(self, comanda_id: int) -> Comanda:
        """Exige sessão antes de tocar no banco e devolve a comanda pedida.

        As duas únicas exceções que sobem deste service saem daqui:
        NaoAutorizadoError (ninguém logado) e RecursoNaoEncontradoError (id que
        não existe). Falha de impressora vira `ResultadoImpressao`.
        """
        self.auth.usuario_atual()
        return self._comandas.buscar(comanda_id)

    @staticmethod
    def _sem_impressora_padrao(o_que: str, quantidade_itens: int) -> ResultadoImpressao:
        return ResultadoImpressao(
            impressora_nome=GRUPO_SEM_IMPRESSORA,
            quantidade_itens=quantidade_itens,
            sucesso=False,
            erro=(
                f"Nenhuma impressora está marcada como padrão, então {o_que} não saiu. "
                "Abra a tela de Impressoras e use 'Definir como padrão'."
            ),
        )

    def _pagamentos_da_comanda(
        self, comanda_id: int
    ) -> tuple[dict[FormaPagamento, Decimal], Decimal, Decimal]:
        """Soma os pagamentos por forma, o troco devolvido e o total recebido.

        Uma varredura só na lista que o repository já devolve ordenada: o
        recibo mostra as formas na ordem em que o cliente pagou.
        """
        por_forma: dict[FormaPagamento, Decimal] = {}
        troco = ZERO
        total = ZERO
        for pagamento in self.uow.pagamentos.listar_por_comanda(comanda_id):
            valor = dinheiro(pagamento.valor)
            por_forma[pagamento.forma] = dinheiro(por_forma.get(pagamento.forma, ZERO) + valor)
            total += valor
            if pagamento.troco is not None:
                troco += dinheiro(pagamento.troco)
        return por_forma, dinheiro(troco), dinheiro(total)

    def _detalhe_da_maquininha(self, caixa_id: int) -> list[tuple[str, Decimal]]:
        """Crédito, débito e PIX separados — só as formas que tiveram movimento."""
        detalhe: list[tuple[str, Decimal]] = []
        for forma in FORMAS_MAQUININHA:
            total = ZERO
            for pagamento in self.uow.pagamentos.listar_por_caixa(caixa_id, formas=[forma]):
                total += dinheiro(pagamento.valor)
            if total > ZERO:
                detalhe.append((ROTULO_FORMA_PAGAMENTO.get(forma, forma.value), dinheiro(total)))
        return detalhe

    @staticmethod
    def _destino_da_comanda(comanda: Comanda) -> str:
        """'MESA 12' ou 'BALCÃO' — para onde o pedido vai."""
        mesa = getattr(comanda, "mesa", None)
        if mesa is None:
            return "BALCÃO"
        return f"MESA {mesa.numero}"

    def _nome_do_atendente(self, comanda: Comanda) -> str:
        """Quem abriu a comanda; na falta dele, quem está operando agora."""
        funcionario = getattr(comanda, "funcionario", None)
        if funcionario is not None:
            return funcionario.nome
        return self.auth.usuario_atual().nome
