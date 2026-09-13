"""Pipeline de compressão de foto de produto do cardápio.

Só Qt nativo (`QImage`/`QImageReader`) — sem Pillow como dependência nova,
PySide6 já dá conta e o hardware do food truck (Celeron + 4GB) não sobra RAM
pra biblioteca extra. Regras (ver TAREFA original):

- Nunca guarda o arquivo original pesado em lugar nenhum, nem base64 no banco.
- Miniatura final em disco: EXATAMENTE 120x120px, recorte central, JPEG, meta
  de 15-25KB por arquivo.
- Só o NOME do arquivo salvo é o que entra em `Produto.imagem_path` — a pasta
  (`<dir_dados>/uploads/thumbnails/`) é sempre resolvida em runtime a partir
  de `DB_PATH`, nunca gravada no banco. Isso permite mover a pasta de dados
  inteira (troca de máquina, backup) sem quebrar os caminhos das fotos.

Por que QUADRADA, e não "cabe em 120x120": a versão anterior guardava a foto
com a proporção original (120x67, 67x120...), e quem pinta a linha do Cardápio
reservou um quadrado. A foto deitada saía mais larga que o quadrado e era
pintada por cima do nome do produto; a em pé passava por cima do divisor da
linha. Medido no banco real em 2026-09-13: 18 das 35 miniaturas não eram
quadradas. O enquadramento é o do `ImageOps.fit` do Pillow — escala até o menor
lado caber, corta o excesso igual dos dois lados — e mora em
`ler_quadrado_central`, que o `thumbnail_cache` também usa para as miniaturas
antigas que já estão em disco com a proporção errada.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QPainter

from gestor_comercial.core.resilience import logger_do_app
from gestor_comercial.repository.base import DB_PATH

TAMANHO_MAXIMO_PX = 120
# Degrau de qualidade tentado em ordem até o arquivo caber no teto de tamanho,
# ou até acabarem as opções (aí fica com o menor arquivo que conseguiu gerar).
_DEGRAUS_QUALIDADE = (72, 60, 50, 40)
TAMANHO_MAXIMO_BYTES = 25 * 1024

# Os formatos homologados, num lugar só: o filtro do seletor de arquivos sai
# daqui, e a conferência de `processar_imagem_produto` também. O filtro sozinho
# NÃO é barreira — no seletor nativo do Windows dá para digitar `*.*` ou colar o
# caminho de um `.avif` no campo de nome, e o arquivo chega aqui do mesmo jeito.
# `.avif`, `.heic`, `.bmp` e `.svg` ficam de fora: os dois primeiros o Qt do
# projeto nem lê ("Unsupported image format"), e os dois últimos lê, mas não são
# foto de produto.
EXTENSOES_ACEITAS = (".png", ".jpg", ".jpeg", ".webp")
FILTRO_DO_SELETOR = "Imagens suportadas ({})".format(" ".join(f"*{e}" for e in EXTENSOES_ACEITAS))
MENSAGEM_FORMATO_INVALIDO = "Formato inválido. Selecione PNG, JPG ou WEBP."


def pasta_thumbnails() -> Path:
    """Pasta de miniaturas, ao lado do banco (mesmo diretório de dados)."""
    pasta = DB_PATH.parent / "uploads" / "thumbnails"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def ler_quadrado_central(caminho: str | Path, lado: int) -> QImage:
    """Lê a imagem já recortada no quadrado central e escalada para `lado`x`lado`.

    Nunca devolve imagem de outro tamanho: é o contrato de que quem pinta
    depende para a foto não sair da caixa dela. Levanta `ValueError` com o
    motivo do Qt se o arquivo não puder ser lido.

    O recorte e a escala são pedidos ao LEITOR (`setClipRect`/`setScaledSize`),
    e não feitos depois sobre a imagem inteira. No JPEG isso decide a memória:
    o decodificador já sai na escala reduzida, e uma foto de celular de 12 MP não
    chega a ocupar os ~48 MB que ela teria aberta por inteiro — numa máquina com
    ~90 MB de teto para o processo inteiro. PNG e WebP não sabem fazer isso, e
    o próprio Qt emula (lê inteira, corta, escala), com o mesmo resultado.

    O quadrado central de uma foto é o mesmo com ou sem a rotação do EXIF, então
    o recorte pode ser calculado sobre o tamanho gravado no arquivo.
    """
    leitor = QImageReader(str(caminho))
    leitor.setAutoTransform(True)
    tamanho = leitor.size()
    if not tamanho.isValid() or tamanho.isEmpty():
        raise ValueError(leitor.errorString())

    menor = min(tamanho.width(), tamanho.height())
    leitor.setClipRect(
        QRect((tamanho.width() - menor) // 2, (tamanho.height() - menor) // 2, menor, menor)
    )
    leitor.setScaledSize(QSize(lado, lado))
    imagem = leitor.read()
    if imagem.isNull():
        raise ValueError(leitor.errorString())
    return imagem


def processar_imagem_produto(caminho_original: str) -> str:
    """Enquadra, comprime e salva a miniatura de uma foto de produto.

    Recebe o caminho do arquivo escolhido pelo usuário (ex: via
    `QFileDialog.getOpenFileName`), devolve o NOME do arquivo já salvo em
    `pasta_thumbnails()` (não o caminho completo — ver módulo).

    Levanta `ValueError(MENSAGEM_FORMATO_INVALIDO)` se o arquivo não for de um
    formato homologado ou não puder ser lido (corrompido, `.avif` renomeado
    para `.jpg`...). O motivo técnico vai para o log do app, e não para a tela:
    "Unsupported image format" não ajuda quem está cadastrando um suco.
    """
    if Path(caminho_original).suffix.lower() not in EXTENSOES_ACEITAS:
        logger_do_app().warning("Foto de produto recusada pela extensão: %s", caminho_original)
        raise ValueError(MENSAGEM_FORMATO_INVALIDO)

    try:
        miniatura = ler_quadrado_central(caminho_original, TAMANHO_MAXIMO_PX)
    except Exception:
        # `Exception`, e não só o `ValueError` de `ler_quadrado_central`: é a
        # porta por onde entra arquivo de fora do programa, e qualquer surpresa
        # do leitor tem que virar a mesma frase na tela, com o rastro no log.
        logger_do_app().exception("Foto de produto ilegível: %s", caminho_original)
        raise ValueError(MENSAGEM_FORMATO_INVALIDO) from None

    miniatura = _sem_transparencia(miniatura)
    destino = pasta_thumbnails() / f"{uuid.uuid4().hex}.jpg"

    for qualidade in _DEGRAUS_QUALIDADE:
        if not miniatura.save(str(destino), "JPG", qualidade):
            raise ValueError(f"Falha ao salvar a miniatura em '{destino}'.")
        if destino.stat().st_size <= TAMANHO_MAXIMO_BYTES:
            break
        # Continua tentando o próximo degrau; o save seguinte sobrescreve.

    return destino.name


def _sem_transparencia(imagem: QImage) -> QImage:
    """Achata a foto sobre branco antes de virar JPEG.

    JPEG não tem canal alfa, e o Qt, ao salvar, descarta o alfa e fica com a
    cor que estava por baixo — que num PNG recortado é (0, 0, 0). O copo de
    suco com fundo transparente virava um copo num quadrado PRETO. Branco é o
    fundo de catálogo de produto, e é o que o PNG mostraria num visualizador.
    """
    if not imagem.hasAlphaChannel():
        return imagem
    chapada = QImage(imagem.size(), QImage.Format.Format_RGB32)
    chapada.fill(Qt.GlobalColor.white)
    pintor = QPainter(chapada)
    pintor.drawImage(0, 0, imagem)
    pintor.end()
    return chapada


def resolver_caminho_thumbnail(imagem_path: str | None) -> Path | None:
    """Caminho absoluto de uma thumbnail a partir do nome salvo no banco.

    Devolve `None` se não houver `imagem_path` ou se o arquivo não existir
    mais em disco (ex: pasta de dados movida/limpa manualmente) — quem chama
    trata isso caindo pro placeholder, nunca estourando exceção.
    """
    if not imagem_path:
        return None
    caminho = pasta_thumbnails() / imagem_path
    return caminho if caminho.is_file() else None


def remover_thumbnail(imagem_path: str | None) -> None:
    """Apaga o arquivo de uma thumbnail do disco, se existir.

    Usado quando o gerente troca ou remove a foto de um produto, pra não
    acumular lixo órfão na pasta de uploads. Silencioso se o arquivo já não
    existir mais.
    """
    caminho = resolver_caminho_thumbnail(imagem_path)
    if caminho is not None:
        caminho.unlink(missing_ok=True)
