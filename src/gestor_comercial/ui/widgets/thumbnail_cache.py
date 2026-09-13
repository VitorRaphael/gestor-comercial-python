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
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen, QPixmap

from gestor_comercial.services.imagem_service import ler_quadrado_central, resolver_caminho_thumbnail
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.cores import cor_do_token

# 200, e não 100: o cardápio real tem 113 produtos, e o Cardápio (36px) e o
# modal de lançamento (40px) são duas entradas por produto. Com 100, rolar a
# lista inteira despejaria o que acabou de ser pintado e voltaria ao disco a
# cada repintura — o Celeron pagaria em CPU o que se economizou de RAM. E a RAM
# é pouca: a 36px um pixmap tem 36x36x4 = 5,2 KB, e o cache cheio fica perto de
# 1 MB (a 80px, a prévia do cadastro, ~5 MB no pior caso teórico).
LIMITE_ENTRADAS = 200

# Raio dos cantos do recorte em cartão — o mesmo na foto e no placeholder, para
# produto com e sem foto terem a mesma silhueta na lista. 8px é o do pedido; o
# teto de um quarto do lado é para miniatura pequena (28px no ranking do
# dashboard) não virar um círculo.
RAIO_CARTAO_MAXIMO_PX = 8.0

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
    """`QPixmap` de EXATAMENTE `tamanho`x`tamanho` para uma foto de produto.

    Sem `imagem_path` (ou arquivo ausente/ilegível em disco), devolve um
    placeholder vetorial leve gerado sob demanda — não lança exceção.

    O lado exato é contrato, e não detalhe: quem pinta a linha reserva um
    quadrado e desenha o nome logo depois dele. Até 2026-09-13 a foto era só
    ESCALADA (`KeepAspectRatioByExpanding`), sem corte — uma miniatura 120x67
    em disco saía 64x36, e os 28px de sobra eram pintados em cima do nome.
    Agora ela sai de `ler_quadrado_central`, o mesmo enquadramento de quem grava
    a foto nova, e isso conserta também as miniaturas antigas sem regravá-las.

    `formato` escolhe o recorte: `FORMATO_CARTAO` (padrão, retângulo
    arredondado com borda sutil) ou `FORMATO_CIRCULO` (avatar redondo do modal
    de lançamento). O recorte é feito UMA vez, na hora de entrar no cache — quem
    pinta a linha da lista recebe o pixmap pronto e não gasta `QPainterPath` por
    repaint, que é o que o Celeron do food truck não tem para dar.
    """
    _descartar_se_o_tema_virou()
    sigla = _sigla(nome_produto, formato)
    chave = (imagem_path, tamanho, sigla, formato)
    pixmap_cacheado = _cache.get(chave)
    if pixmap_cacheado is not None:
        _cache.move_to_end(chave)
        return pixmap_cacheado

    pixmap = _foto_recortada(resolver_caminho_thumbnail(imagem_path), tamanho, formato)
    if pixmap is None:
        pixmap = _gerar_placeholder(tamanho, sigla, formato)

    _cache[chave] = pixmap
    _cache.move_to_end(chave)
    if len(_cache) > LIMITE_ENTRADAS:
        _cache.popitem(last=False)
    return pixmap


def limpar() -> None:
    """Esvazia o cache inteiro. Chamar ao fechar uma tela, se quiser liberar RAM já."""
    _cache.clear()


def _descartar_se_o_tema_virou() -> None:
    """Joga fora as miniaturas pintadas com a paleta anterior.

    O placeholder usa `superficie_2`, `borda_card` e `texto_fraco` do tema, e a
    foto em cartão ganhou a borda `borda_card` também. Sem esta checagem, o
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


def _foto_recortada(caminho: Path | None, tamanho: int, formato: str) -> QPixmap | None:
    """A foto em disco já no recorte pedido, ou `None` para cair no placeholder.

    Arquivo ilegível vira placeholder calado, como sempre foi: a foto é
    enfeite da linha, e um JPEG corrompido na pasta não pode custar a lista.
    """
    if caminho is None:
        return None
    try:
        quadrada = QPixmap.fromImage(ler_quadrado_central(caminho, tamanho))
    except ValueError:
        return None

    recortado = QPixmap(tamanho, tamanho)
    recortado.fill(Qt.GlobalColor.transparent)
    painter = QPainter(recortado)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    contorno = QPainterPath()
    if formato == FORMATO_CIRCULO:
        contorno.addEllipse(QRectF(0, 0, tamanho, tamanho))
    else:
        contorno.addRoundedRect(_retangulo(tamanho), _raio_cartao(tamanho), _raio_cartao(tamanho))
    painter.setClipPath(contorno)
    painter.drawPixmap(0, 0, quadrada)
    if formato == FORMATO_CARTAO:
        # A borda do placeholder, na foto também: sem ela a foto de fundo
        # branco era um quadrado cru no tema escuro, sem contorno que dissesse
        # onde a miniatura acaba. O círculo do modal fica sem, como era.
        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_caneta_da_borda())
        painter.drawPath(contorno)
    painter.end()
    return recortado


def _retangulo(tamanho: int) -> QRectF:
    """A caixa do recorte em cartão: 1px para dentro, onde a borda assenta."""
    return QRectF(1.0, 1.0, tamanho - 2.0, tamanho - 2.0)


def _raio_cartao(tamanho: int) -> float:
    return min(RAIO_CARTAO_MAXIMO_PX, tamanho / 4.0)


def _caneta_da_borda() -> QPen:
    # `cor_do_token`, e não `QColor` direto: no tema escuro `borda_card` é
    # `rgba(255, 255, 255, 0.08)`, grafia que o `QColor` não entende — a borda
    # saía preta opaca em vez do contorno claro sutil que o token descreve.
    tokens = ThemeController.instancia().tokens_atuais
    return QPen(cor_do_token(tokens.get("borda_card", "#242220")), 1)


def _gerar_placeholder(tamanho: int, sigla: str, formato: str = FORMATO_CARTAO) -> QPixmap:
    """Placeholder: fundo `superficie_2`, borda `borda_card`, sigla do produto.

    Letras iniciais em vez de ícone de prato/garfo desenhado à mão: menos
    código de vetor pra manter e já ajuda a diferenciar produtos na lista mesmo
    sem foto (ex.: "X" de X-Burger, "CO" de Coca-Cola).

    As cores são tokens, e não os hex do pedido cravados: no tema escuro
    `superficie_2` é #1C1C1A (o pedido dizia #1E1E1C, a 2 pontos de distância) e
    `texto_fraco` é exatamente o #A1A1AA pedido — mas cravar os hex deixaria um
    quadrado escuro no meio do tema claro (a armadilha do §3.15).
    """
    tokens = ThemeController.instancia().tokens_atuais
    pixmap = QPixmap(tamanho, tamanho)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    retangulo = _retangulo(tamanho)
    painter.setBrush(cor_do_token(tokens.get("superficie_2", "#1C1C1A")))
    painter.setPen(_caneta_da_borda())
    if formato == FORMATO_CIRCULO:
        painter.drawEllipse(retangulo)
    else:
        painter.drawRoundedRect(retangulo, _raio_cartao(tamanho), _raio_cartao(tamanho))

    fonte = QFont()
    # Duas letras num círculo do mesmo lado precisam de corpo menor que uma
    # letra sozinha, senão a sigla encosta na borda.
    proporcao = 0.34 if formato == FORMATO_CIRCULO else 0.45
    fonte.setPixelSize(max(9, int(tamanho * proporcao)))
    fonte.setBold(True)
    painter.setFont(fonte)
    painter.setPen(cor_do_token(tokens.get("texto_fraco", "#A1A1AA")))
    painter.drawText(retangulo, Qt.AlignmentFlag.AlignCenter, sigla)

    painter.end()
    return pixmap
