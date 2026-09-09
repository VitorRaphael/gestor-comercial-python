"""Busca instantânea (typeahead) de produtos, para lançar item em mesa ou
comanda de balcão sem rolar o cardápio inteiro — porte do requisito de busca
rápida do PDV do food truck.

Filtra a cada tecla, ignora acento e caixa (`"agua"` acha `"Água Mineral"`) e
é operável 100% pelo teclado: `↑`/`↓` navegam, `Enter` confirma o item
destacado, `Esc` limpa a busca (ou fecha, se já estiver vazia) — o operador
não pode depender do mouse com as mãos ocupadas no caixa.

A busca enxerga também a **subcategoria** (§9.8/§9.9): digitar "artesanal"
lista todos os lanches dessa subcategoria, mesmo que a palavra não apareça no
nome de nenhum deles.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import nao_deixa_escapar
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.texto import sem_acento as _normalizar
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.thumbnail_cache import obter_pixmap

_TAMANHO_MINIATURA = 40


def nome_da_subcategoria(produto: object) -> str:
    """O nome da subcategoria do produto, ou `""` quando não há.

    Recebe `object` porque atende duas formas do mesmo dado: o `Produto` do
    SQLAlchemy, onde `subcategoria` é a **relação** e o nome mora dentro dela,
    e o `_LinhaProduto` do modal "Adicionar item", que é um instantâneo sem
    banco atrás e guarda o nome direto como `str`. O `getattr` com padrão cobre
    ainda um terceiro caso — objeto sem o atributo, como as bancadas e os
    testes de busca —, que responde vazio em vez de estourar.
    """
    subcategoria = getattr(produto, "subcategoria", None)
    if subcategoria is None:
        return ""
    if isinstance(subcategoria, str):
        return subcategoria
    return getattr(subcategoria, "nome", "") or ""


def _texto_buscavel(produto: object) -> str:
    """Nome + subcategoria, que é o que a digitação tem permissão de casar.

    Categoria e preço ficam de FORA de propósito. Quem quer filtrar por
    categoria tem as pílulas ao lado da busca, e um preço no meio do texto
    buscável faria digitar "12" trazer o cardápio inteiro pelo "R$ 12,00" de
    dez itens — busca que traz tudo é busca que não serve.
    """
    return f"{produto.nome} {nome_da_subcategoria(produto)}"


def filtrar_produtos(produtos: list[Produto], termo: str) -> list[Produto]:
    """Filtra por substring tolerante a acento/caixa, palavra por palavra.

    Cada palavra do termo digitado precisa aparecer em algum lugar do nome ou
    da subcategoria — por isso `"coca cola k"` restringe para `"Coca-Cola KS"`
    mas já não casa mais com `"Coca-Cola Lata"`, e `"artesanal"` traz os
    lanches dessa subcategoria mesmo sem a palavra estar no nome de nenhum.
    """
    tokens = [_normalizar(t) for t in termo.split() if t]
    if not tokens:
        return list(produtos)
    return [
        produto
        for produto in produtos
        if all(token in _normalizar(_texto_buscavel(produto)) for token in tokens)
    ]


class BuscaProdutoWidget(QWidget):
    """Campo de busca + lista de resultados filtrada em tempo real.

    Emite `produto_selecionado(produto_id)` ao confirmar um item (Enter na
    lista ou duplo clique) e `busca_cancelada` quando o Esc é pressionado com
    o campo já vazio (sinal para quem o hospeda fechar a busca).
    """

    produto_selecionado = Signal(int)
    busca_cancelada = Signal()

    def __init__(self, produtos: list[Produto], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._produtos_ativos = produtos

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._campo_busca = QLineEdit()
        self._campo_busca.setPlaceholderText("🔎  Buscar produto…")
        self._campo_busca.textChanged.connect(self._filtrar)
        self._campo_busca.installEventFilter(self)
        layout.addWidget(self._campo_busca)

        self._lista_resultados = QListWidget()
        self._lista_resultados.setIconSize(QSize(_TAMANHO_MINIATURA, _TAMANHO_MINIATURA))
        self._lista_resultados.itemActivated.connect(self._item_ativado)
        layout.addWidget(self._lista_resultados)

        self._filtrar("")
        self._campo_busca.setFocus()

    @nao_deixa_escapar(retorno=False)
    def eventFilter(self, obj: QWidget, evento: QEvent) -> bool:
        if obj is self._campo_busca and evento.type() == QEvent.Type.KeyPress:
            tecla = evento.key()
            if tecla == Qt.Key.Key_Down:
                self._mover_selecao(1)
                return True
            if tecla == Qt.Key.Key_Up:
                self._mover_selecao(-1)
                return True
            if tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._confirmar_selecionado()
                return True
            if tecla == Qt.Key.Key_Escape:
                self._tratar_escape()
                return True
        return super().eventFilter(obj, evento)

    def foco_busca(self) -> None:
        self._campo_busca.setFocus()
        self._campo_busca.selectAll()

    def confirmar_selecionado(self) -> None:
        """Lança o item destacado na lista — equivalente a Enter/duplo clique.

        Existe para quem hospeda o widget oferecer um botão explícito a quem
        não sabe (ou não quer usar) o atalho de teclado/duplo clique.
        """
        self._confirmar_selecionado()

    def _tratar_escape(self) -> None:
        # Primeiro Esc só limpa a busca (regra 4); campo já vazio é o sinal
        # para quem hospeda o widget fechar a tela de busca de vez.
        if self._campo_busca.text():
            self._campo_busca.clear()
        else:
            self.busca_cancelada.emit()

    def _mover_selecao(self, delta: int) -> None:
        total = self._lista_resultados.count()
        if total == 0:
            return
        atual = self._lista_resultados.currentRow()
        novo = 0 if atual == -1 else max(0, min(total - 1, atual + delta))
        self._lista_resultados.setCurrentRow(novo)

    def _confirmar_selecionado(self) -> None:
        item = self._lista_resultados.currentItem()
        if item is None and self._lista_resultados.count() > 0:
            item = self._lista_resultados.item(0)
        if item is None:
            return
        self._item_ativado(item)

    def _item_ativado(self, item: QListWidgetItem) -> None:
        produto_id = item.data(Qt.ItemDataRole.UserRole)
        self._campo_busca.clear()
        self.produto_selecionado.emit(produto_id)

    def _filtrar(self, termo: str) -> None:
        self._lista_resultados.clear()
        for produto in filtrar_produtos(self._produtos_ativos, termo):
            # A subcategoria entra colada na categoria, como um caminho: quem
            # busca "artesanal" e recebe três lanches precisa VER por que eles
            # vieram, senão o filtro parece ter trazido item errado.
            setor = produto.categoria.nome
            sub = nome_da_subcategoria(produto)
            if sub:
                setor = f"{setor} · {sub}"
            texto = f"{produto.nome} — {formatar_reais(produto.preco)} — {setor}"
            if produto.is_combo:
                texto += "  [COMBO]"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, produto.id)
            # Pixmap já vem cacheado (ver thumbnail_cache) — digitar rápido na
            # busca não reprocessa nada, só troca o texto/ícone já prontos.
            pixmap = obter_pixmap(produto.imagem_path, _TAMANHO_MINIATURA, produto.nome)
            item.setIcon(QIcon(pixmap))
            self._lista_resultados.addItem(item)
        if self._lista_resultados.count() > 0:
            self._lista_resultados.setCurrentRow(0)
