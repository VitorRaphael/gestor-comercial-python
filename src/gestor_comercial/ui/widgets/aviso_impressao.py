"""Como o resultado de uma impressão chega ao operador do food truck (§3.12).

Quatro pontos da interface mostram a mesma coisa — a comanda, o caixa, a tela
de Impressoras e a janela principal depois do pagamento — e todos obedecem ao
mesmo RNF inegociável: falha de impressora é AVISO, nunca exceção, e nunca
aborta a venda. Concentrar aqui o texto, a cor e o cursor de espera evita que
um dos quatro esqueça a regra.

As três cores (apagado, verde, âmbar) moram no QSS global, em
`QLabel#avisoImpressao[tom=...]`. Aqui só se troca o `tom`. É o que o §3.15
pediu: com `setStyleSheet` inline, a cor era resolvida na construção e o widget
ficava com a paleta do boot para sempre, porque stylesheet por widget vence o
QSS global — alternar Claro/Escuro repintava o app menos esta linha.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import TypeVar

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from gestor_comercial.services.impressao_service import GRUPO_SEM_IMPRESSORA, ResultadoImpressao
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade


T = TypeVar("T")

# Fatia da espera entre um `processEvents` e o seguinte. Curta o bastante
# para a janela repintar sem engasgo, longa o bastante para a espera não
# virar laço ocupado num Celeron — o RNF de otimização vale aqui também.
FATIA_DE_ESPERA_S = 0.05

# Já existe uma espera bombeando eventos nesta thread? Ver `aguardar_repintando`.
_esperando = False


def executar_impressao(acao: Callable[[], T]) -> T:
    """Roda a ação de impressão na thread da UI, com ampulheta no cursor.

    DECISÃO DE ARQUITETURA (Fase 4 da remasterização, **mantida**): a *ação*
    continua rodando aqui, na thread da UI. O app inteiro vive sobre um único
    `UnitOfWork`/`Session` do SQLAlchemy, e `Session` não é thread-safe —
    mandar tudo isto para outra thread trocaria um congelamento de segundos por
    corrupção silenciosa do banco do food truck.

    O que mudou na Fase 3 de `Mitigação de Falhas.md` foi só a **outra metade**:
    dentro do service, a conversa com o cabo da impressora saiu daqui e virou
    uma thread própria (`ImpressaoService._falar_com_o_periferico`). O que
    atravessa para lá é imutável e sem vínculo com o banco. Montar o documento —
    que é o que toca a `Session` — continua acontecendo nesta thread.

    Quem espera aquela thread é `aguardar_repintando`, injetado no service.
    """
    if QApplication.instance() is None:
        # Sem QApplication (import de módulo, smoke test) não existe cursor
        # para trocar — mas a ação em si continua valendo.
        return acao()

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        return acao()
    finally:
        # `finally` e não depois da chamada: se a ação estourar uma exceção de
        # negócio, o operador não pode ficar com a ampulheta presa na tela.
        QApplication.restoreOverrideCursor()


def aguardar_repintando(thread: threading.Thread, teto_s: float) -> None:
    """Espera a thread de impressão **sem** a janela do PDV congelar.

    É a metade de UI da Fase 3, e o motivo de ela existir é específico do
    Windows: uma thread principal parada em `join()` para de responder ao
    gerenciador de janelas, e depois de ~5 segundos o próprio sistema desenha
    por cima do PDV um retângulo branco com "Não Está Respondendo" no título.
    Para quem está no balcão, isso é indistinguível do programa ter travado —
    e a reação natural é fechar no X, no meio de uma venda.

    A saída é esperar em fatias curtas, processando os eventos do Qt entre
    elas, para a janela continuar se repintando.

    Processar eventos no meio de uma espera é reentrar no laço principal, e isso
    tem um risco conhecido: o operador clica de novo e dispara uma segunda
    impressão por cima da primeira, ainda em curso. As duas defesas são:

    1. **`ExcludeUserInputEvents`** — o Qt segura clique e tecla vindos do
       sistema até a espera acabar, em vez de descartá-los. O operador não perde
       o toque; ele só espera a vez.
    2. **`_esperando`** — a trava que impede o aninhamento de crescer. A bandeira
       acima vale para a entrada que vem do gerenciador de janelas, mas evento
       *postado* por código (um `QTimer` de atualização, por exemplo) atravessa
       assim mesmo; se esse evento disparar outra impressão, cairíamos aqui
       dentro de novo, e cada nível empilharia mais um `processEvents`. Da
       segunda espera em diante o bombeamento é desligado e sobra o `join()`
       puro: pior para a repintura, e é o certo — a tela já está sendo repintada
       pela espera de fora, e o que não pode é a pilha crescer sem fim.
    """
    if QApplication.instance() is None:
        thread.join(teto_s)
        return

    global _esperando
    if _esperando:
        thread.join(teto_s)
        return

    _esperando = True
    try:
        limite = time.monotonic() + teto_s
        while thread.is_alive() and time.monotonic() < limite:
            thread.join(FATIA_DE_ESPERA_S)
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
    finally:
        _esperando = False


class AvisoDeImpressao(QLabel):
    """Linha de status que conta o que saiu — ou não — no papel.

    Verde quando tudo imprimiu, âmbar quando algum cupom falhou. Âmbar e não
    vermelho de propósito: vermelho é a cor de erro que interrompe a operação
    (`_label_erro` das views), e impressão que falha não interrompe nada.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self.setObjectName("avisoImpressao")
        self.setWordWrap(True)
        self.limpar()

    def limpar(self) -> None:
        self._pintar("")
        self.setText("")

    def mostrar(self, resultados: Sequence[ResultadoImpressao], *, vazio: str = "") -> None:
        """Mostra um cupom por linha; `vazio` é o texto de 'não havia o que imprimir'."""
        if not resultados:
            self._pintar("")
            self.setText(vazio)
            return

        houve_falha = any(not resultado.sucesso for resultado in resultados)
        self._pintar("aviso" if houve_falha else "sucesso")
        self.setText("\n".join(_mensagem(resultado) for resultado in resultados))

    def mostrar_um(self, resultado: ResultadoImpressao, *, contexto: str = "") -> None:
        """Um cupom só.

        `contexto` diz qual documento era. Faz falta quando o recibo do cliente
        e o fechamento de caixa saem na mesma impressora dos pedidos: sem ele, a
        linha "Balcão: cupom enviado" não conta qual papel acabou de sair.
        """
        mensagem = _mensagem(resultado)
        self._pintar("sucesso" if resultado.sucesso else "aviso")
        self.setText(f"{contexto} — {mensagem}" if contexto else mensagem)

    def mostrar_falha(self, mensagem: str) -> None:
        """Aviso de algo que nem chegou a virar `ResultadoImpressao`.

        É o caso do recibo disparado depois do pagamento: o dinheiro já entrou,
        então nem uma exceção de negócio pode virar caixa de erro na cara do
        operador — vira esta linha âmbar e a vida continua.
        """
        self._pintar("aviso")
        self.setText(mensagem)

    def _pintar(self, tom: str) -> None:
        """`""` (apagado), `"sucesso"` (verde) ou `"aviso"` (âmbar) — ver o QSS."""
        aplicar_propriedade(self, "tom", tom)


def _mensagem(resultado: ResultadoImpressao) -> str:
    """Vira `ResultadoImpressao` em uma frase que o operador entende de relance."""
    quantidade = resultado.quantidade_itens

    if resultado.sucesso:
        if quantidade == 0:
            # Recibo, fechamento e teste não têm item para contar.
            return f"{resultado.impressora_nome}: cupom enviado"
        if quantidade == 1:
            return f"{resultado.impressora_nome}: 1 item enviado"
        return f"{resultado.impressora_nome}: {quantidade} itens enviados"

    erro = resultado.erro or "falha desconhecida na impressora."
    if resultado.impressora_nome == GRUPO_SEM_IMPRESSORA:
        # Este grupo não tem impressora para citar, e o rótulo genérico só
        # empurraria para o fim da linha o motivo — que é justamente o que diz
        # ao operador qual categoria configurar.
        if quantidade == 0:
            return erro
        rotulo = "1 item" if quantidade == 1 else f"{quantidade} itens"
        return f"{rotulo} sem impressora: {erro}"
    # Só o cupom que TEVE impressora de destino vai para a fila — o grupo órfão
    # acima não tem para onde ser reenviado, e prometer reimpressão ali mandaria
    # o operador procurar na fila uma linha que não existe. Ver Fase 3.
    return f"{resultado.impressora_nome}: falhou — {erro} {AVISO_DE_FILA}"


# O texto que fecha toda falha de impressora com destino conhecido. Fica numa
# constante porque é promessa ao operador: se a fila deixar de existir, esta
# linha tem que sair junto, e uma constante é o que faz as duas se acharem.
AVISO_DE_FILA = "O cupom ficou salvo na fila para reimpressão."
