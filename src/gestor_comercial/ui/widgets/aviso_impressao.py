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

from collections.abc import Callable, Sequence
from typing import TypeVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from gestor_comercial.services.impressao_service import GRUPO_SEM_IMPRESSORA, ResultadoImpressao
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade


T = TypeVar("T")


def executar_impressao(acao: Callable[[], T]) -> T:
    """Roda a impressão na própria thread da UI, com ampulheta no cursor.

    DECISÃO DE ARQUITETURA: isto NÃO vai para uma QThread, mesmo que congele a
    tela por até 3 segundos (o timeout do driver). O app inteiro roda sobre um
    único `UnitOfWork`/`Session` do SQLAlchemy por processo, e `Session` não é
    thread-safe: mandar a impressão para outra thread trocaria um congelamento
    de 3 segundos por corrupção silenciosa do banco do food truck. A ampulheta
    é o que o operador precisa ver para saber que o clique foi registrado.
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
    return f"{resultado.impressora_nome}: falhou — {erro}"
