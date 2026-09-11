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
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen, QPixmap

from gestor_comercial.services.imagem_service import resolver_caminho_thumbnail
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token

LIMITE_ENTRADAS = 200

# Os dois recortes que o app pede hoje. `CARTAO` é o retângulo arredondado que
# o Cardápio e a tabela da comanda sempre usaram; `CIRCULO` entrou com o modal
# "Adicionar item", cujo mockup pede avatar redondo com DUAS letras (o cartão
# desenha uma). A diferença mora aqui, e não no chamador, para continuar
# valendo o que o §3.10 estabeleceu: quem desenha a miniatura de produto é este
# módulo, e o desenho e a chave do cache saem do mesmo lugar.
FORMATO_CARTAO = "cartao"
FORMATO_CIRCULO = "circulo"

_LETRAS_POR_FORMATO = {FORMATO_CARTAO: 1, FORMATO_CIRCULO: 2}

# Chave = (imagem_path ou None, tamanho, sigla, formato) -> QPixmap já escalado.
#
# A sigla entra na chave por causa do §3.10: o placeholder é DESENHADO com as
# primeiras letras do produto, mas a chave só tinha caminho e tamanho — e o
# caminho de todo produto sem foto é o mesmo `None`. Resultado: o primeiro
# produto sem foto a ser desenhado emprestava a inicial dele para todos os
# outros, e a Coca-Cola aparecia com um "X" no cardápio. O formato entra pela
# mesma razão: o mesmo produto, no mesmo tamanho, sai redondo num lugar e
# quadrado no outro — são dois desenhos, e portanto duas entradas.
_cache: "OrderedDict[tuple[str | None, int, str, str], QPixmap]" = OrderedDict()

# Paleta com que os placeholders do cache foram pintados. O `ThemeController`
# devolve sempre o mesmo dicionário de módulo por tema (`TEMA_CLARO`/
# `TEMA_ESCURO`), então comparar por identidade basta para saber que o tema
# virou. Guardar isto aqui evita assinar o sinal `mudou` do controlador — que é
# singleton e viveria o processo inteiro segurando a conexão (§3.14).
_tema_do_cache: dict[str, str] | None = None


def obter_pixmap(
    imagem_path: str | None,
    tamanho: int,
    nome_produto: str = "",
    formato: str = FORMATO_CARTAO,
) -> QPixmap:
    """`QPixmap` quadrado de `tamanho`x`tamanho` para uma foto de produto.

    Sem `imagem_path` (ou arquivo ausente em disco), devolve um placeholder
    vetorial leve gerado sob demanda — não bate no disco nem lança exceção.

    `formato` escolhe o recorte: `FORMATO_CARTAO` (padrão, retângulo
    arredondado) ou `FORMATO_CIRCULO` (avatar redondo do modal de lançamento).
    O recorte é feito UMA vez, na hora de entrar no cache — quem pinta a linha
    da lista recebe o pixmap pronto e não gasta `QPainterPath` por repaint, que
    é o que o Celeron do food truck não tem para dar.
    """
    _descartar_se_o_tema_virou()
    sigla = _sigla(nome_produto, formato)
    chave = (imagem_path, tamanho, sigla, formato)
    pixmap_cacheado = _cache.get(chave)
    if pixmap_cacheado is not None:
        _cache.move_to_end(chave)
        return pixmap_cacheado

    caminho = resolver_caminho_thumbnail(imagem_path)
    if caminho is None:
        pixmap = _gerar_placeholder(tamanho, sigla, formato)
    else:
        pixmap_disco = QPixmap(str(caminho))
        if pixmap_disco.isNull():
            pixmap = _gerar_placeholder(tamanho, sigla, formato)
        else:
            pixmap = pixmap_disco.scaled(
                tamanho,
                tamanho,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            if formato == FORMATO_CIRCULO:
                pixmap = _recortar_em_circulo(pixmap, tamanho)

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


def _sigla(nome_produto: str, formato: str = FORMATO_CARTAO) -> str:
    """As letras que o placeholder desenha — e que por isso entram na chave.

    Uma para o cartão, duas para o círculo. São os primeiros caracteres do
    nome, não as iniciais das palavras: "Anel de Cebola" vira "AN", e não "AC",
    porque no modal a sigla serve para o olho voltar ao lugar certo da lista
    ordenada alfabeticamente — e a lista é ordenada pelo nome inteiro.
    """
    letras = _LETRAS_POR_FORMATO.get(formato, 1)
    return (nome_produto or "?").strip()[:letras].upper() or "?"


def _recortar_em_circulo(pixmap: QPixmap, tamanho: int) -> QPixmap:
    """Devolve a foto recortada num círculo, com o resto transparente."""
    recortado = QPixmap(tamanho, tamanho)
    recortado.fill(Qt.GlobalColor.transparent)

    painter = QPainter(recortado)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    caminho = QPainterPath()
    caminho.addEllipse(QRectF(0, 0, tamanho, tamanho))
    painter.setClipPath(caminho)
    # `KeepAspectRatioByExpanding` pode devolver um lado maior que `tamanho`;
    # centralizar evita que o recorte pegue só o canto esquerdo da foto.
    painter.drawPixmap(
        (tamanho - pixmap.width()) // 2,
        (tamanho - pixmap.height()) // 2,
        pixmap,
    )
    painter.end()
    return recortado


def _gerar_placeholder(tamanho: int, sigla: str, formato: str = FORMATO_CARTAO) -> QPixmap:
    """Placeholder: fundo `superficie_2`, borda `borda_card`, sigla do produto.

    Letras iniciais em vez de ícone de prato/garfo desenhado à mão: menos
    código de vetor pra manter e já ajuda a diferenciar produtos na lista mesmo
    sem foto (ex.: "X" de X-Burger, "CO" de Coca-Cola).
    """
    tokens = ThemeController.instancia().tokens_atuais
    pixmap = QPixmap(tamanho, tamanho)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    margem = 1.0
    retangulo = QRectF(margem, margem, tamanho - 2 * margem, tamanho - 2 * margem)

    # `cor_do_token`, e não `QColor` direto: no tema escuro `borda_card` é
    # `rgba(255, 255, 255, 0.08)`, grafia que o `QColor` não entende — a borda
    # saía preta opaca em vez do contorno claro sutil que o token descreve.
    painter.setBrush(cor_do_token(tokens.get("superficie_2", "#1C1C1A")))
    painter.setPen(QPen(cor_do_token(tokens.get("borda_card", "#242220")), 1))
    if formato == FORMATO_CIRCULO:
        painter.drawEllipse(retangulo)
    else:
        raio = max(4, tamanho // 8)
        painter.drawRoundedRect(retangulo, raio, raio)

    fonte = QFont()
    # Duas letras num círculo do mesmo lado precisam de corpo menor que uma
    # letra sozinha, senão a sigla encosta na borda.
    proporcao = 0.34 if formato == FORMATO_CIRCULO else 0.45
    fonte.setPixelSize(max(9, int(tamanho * proporcao)))
    fonte.setBold(True)
    painter.setFont(fonte)
    painter.setPen(cor_do_token(tokens.get("texto_fraquissimo", "#71717A")))
    painter.drawText(retangulo, Qt.AlignmentFlag.AlignCenter, sigla)

    painter.end()
    return pixmap
