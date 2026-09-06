"""Cache em memória de `QPixmap` das fotos de produto do cardápio.

Evita reler e reescalar do disco a cada repaint de lista/tabela (busca de
produto, comanda aberta, dashboard mensal) — a miniatura já sai pronta no
tamanho pedido. Simples de propósito: dict + `OrderedDict` para LRU manual,
sem thread, sem invalidação automática por mtime. Se o gerente troca a foto
de um produto, quem grava a nova imagem (ver `_ProdutoDialog`) já usa um nome
de arquivo novo (uuid4), então a entrada velha do cache simplesmente nunca
mais é lida — não precisa invalidar nada.

Vive num hardware fraco (Celeron + 4GB): o limite de entradas existe pra não
deixar a memória crescer sem fim numa tela que fica horas aberta (comanda).
Chame `limpar()` ao fechar uma tela pesada de imagens se quiser liberar RAM
antes da hora — não há nenhum ciclo de vida automático além do LRU.
"""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap

from gestor_comercial.services.imagem_service import resolver_caminho_thumbnail
from gestor_comercial.ui.theme.controller import ThemeController

LIMITE_ENTRADAS = 200

# Chave = (imagem_path ou None, tamanho, inicial) -> QPixmap já escalado.
#
# A inicial entra na chave por causa do §3.10: o placeholder é DESENHADO com a
# primeira letra do produto, mas a chave só tinha caminho e tamanho — e o
# caminho de todo produto sem foto é o mesmo `None`. Resultado: o primeiro
# produto sem foto a ser desenhado emprestava a inicial dele para todos os
# outros, e a Coca-Cola aparecia com um "X" no cardápio.
_cache: "OrderedDict[tuple[str | None, int, str], QPixmap]" = OrderedDict()

# Paleta com que os placeholders do cache foram pintados. O `ThemeController`
# devolve sempre o mesmo dicionário de módulo por tema (`TEMA_CLARO`/
# `TEMA_ESCURO`), então comparar por identidade basta para saber que o tema
# virou. Guardar isto aqui evita assinar o sinal `mudou` do controlador — que é
# singleton e viveria o processo inteiro segurando a conexão (§3.14).
_tema_do_cache: dict[str, str] | None = None


def obter_pixmap(imagem_path: str | None, tamanho: int, nome_produto: str = "") -> QPixmap:
    """`QPixmap` quadrado de `tamanho`x`tamanho` para uma foto de produto.

    Sem `imagem_path` (ou arquivo ausente em disco), devolve um placeholder
    vetorial leve gerado sob demanda — não bate no disco nem lança exceção.
    """
    _descartar_se_o_tema_virou()
    chave = (imagem_path, tamanho, _inicial(nome_produto))
    pixmap_cacheado = _cache.get(chave)
    if pixmap_cacheado is not None:
        _cache.move_to_end(chave)
        return pixmap_cacheado

    caminho = resolver_caminho_thumbnail(imagem_path)
    if caminho is None:
        pixmap = _gerar_placeholder(tamanho, nome_produto)
    else:
        pixmap_disco = QPixmap(str(caminho))
        if pixmap_disco.isNull():
            pixmap = _gerar_placeholder(tamanho, nome_produto)
        else:
            pixmap = pixmap_disco.scaled(
                tamanho,
                tamanho,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )

    _cache[chave] = pixmap
    _cache.move_to_end(chave)
    if len(_cache) > LIMITE_ENTRADAS:
        _cache.popitem(last=False)
    return pixmap


def limpar() -> None:
    """Esvazia o cache inteiro. Chamar ao fechar uma tela, se quiser liberar RAM já."""
    _cache.clear()


def _descartar_se_o_tema_virou() -> None:
    """Joga fora os placeholders pintados com a paleta anterior.

    O placeholder usa `superficie_2`, `borda_card` e `texto_fraquissimo` do
    tema; a foto de verdade não depende de tema nenhum. Sem esta checagem, o
    cardápio ficava com os quadrados escuros no meio do tema claro até alguém
    reiniciar o app — o §3.10 registrou isso junto com o bug da chave.

    Custa uma comparação de identidade por miniatura pedida. Fica aqui, e não
    num assinante de `ThemeController.mudou`, porque o preço de assinar é uma
    conexão permanente a um singleton, sem ninguém para desfazê-la.
    """
    global _tema_do_cache
    tokens_atuais = ThemeController.instancia().tokens_atuais
    if _tema_do_cache is tokens_atuais:
        return
    if _tema_do_cache is not None:
        _cache.clear()
    _tema_do_cache = tokens_atuais


def _inicial(nome_produto: str) -> str:
    """A letra que o placeholder desenha — e que por isso precisa entrar na chave."""
    return (nome_produto or "?").strip()[:1].upper() or "?"


def _gerar_placeholder(tamanho: int, nome_produto: str) -> QPixmap:
    """Placeholder: fundo `superficie_2`, borda `borda_card`, 1ª letra do produto.

    Letra inicial em vez de ícone de prato/garfo desenhado à mão: menos código
    de vetor pra manter e já ajuda a diferenciar produtos na lista mesmo sem
    foto (ex.: "X" de X-Burger, "C" de Coca-Cola).
    """
    tokens = ThemeController.instancia().tokens_atuais
    pixmap = QPixmap(tamanho, tamanho)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    raio = max(4, tamanho // 8)
    margem = 1.0
    retangulo = QRectF(margem, margem, tamanho - 2 * margem, tamanho - 2 * margem)

    painter.setBrush(QColor(tokens.get("superficie_2", "#1C1C1A")))
    painter.setPen(QPen(QColor(tokens.get("borda_card", "#242220")), 1))
    painter.drawRoundedRect(retangulo, raio, raio)

    letra = _inicial(nome_produto)
    fonte = QFont()
    fonte.setPixelSize(max(10, int(tamanho * 0.45)))
    fonte.setBold(True)
    painter.setFont(fonte)
    painter.setPen(QColor(tokens.get("texto_fraquissimo", "#71717A")))
    painter.drawText(retangulo, Qt.AlignmentFlag.AlignCenter, letra)

    painter.end()
    return pixmap
