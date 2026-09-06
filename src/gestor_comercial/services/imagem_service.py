"""Pipeline de compressão de foto de produto do cardápio.

Só Qt nativo (`QImage`) — sem Pillow como dependência nova, PySide6 já dá
conta e o hardware do food truck (Celeron + 4GB) não sobra RAM pra biblioteca
extra. Regras (ver TAREFA original):

- Nunca guarda o arquivo original pesado em lugar nenhum, nem base64 no banco.
- Miniatura final em disco: máx 120x120px, JPEG, meta de 15-25KB por arquivo.
- Só o NOME do arquivo salvo é o que entra em `Produto.imagem_path` — a pasta
  (`<dir_dados>/uploads/thumbnails/`) é sempre resolvida em runtime a partir
  de `DB_PATH`, nunca gravada no banco. Isso permite mover a pasta de dados
  inteira (troca de máquina, backup) sem quebrar os caminhos das fotos.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from gestor_comercial.repository.base import DB_PATH

TAMANHO_MAXIMO_PX = 120
# Degrau de qualidade tentado em ordem até o arquivo caber no teto de tamanho,
# ou até acabarem as opções (aí fica com o menor arquivo que conseguiu gerar).
_DEGRAUS_QUALIDADE = (72, 60, 50, 40)
TAMANHO_MAXIMO_BYTES = 25 * 1024


def pasta_thumbnails() -> Path:
    """Pasta de miniaturas, ao lado do banco (mesmo diretório de dados)."""
    pasta = DB_PATH.parent / "uploads" / "thumbnails"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def processar_imagem_produto(caminho_original: str) -> str:
    """Redimensiona, comprime e salva a miniatura de uma foto de produto.

    Recebe o caminho do arquivo escolhido pelo usuário (ex: via
    `QFileDialog.getOpenFileName`), devolve o NOME do arquivo já salvo em
    `pasta_thumbnails()` (não o caminho completo — ver módulo).

    Levanta `ValueError` se o arquivo não puder ser lido como imagem (formato
    inválido/corrompido), pra a tela mostrar uma mensagem amigável.
    """
    imagem = QImage(caminho_original)
    if imagem.isNull():
        raise ValueError(f"Não foi possível abrir '{caminho_original}' como imagem.")

    imagem_redimensionada = imagem.scaled(
        TAMANHO_MAXIMO_PX,
        TAMANHO_MAXIMO_PX,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    destino = pasta_thumbnails() / f"{uuid.uuid4().hex}.jpg"

    qualidade_usada = _DEGRAUS_QUALIDADE[-1]
    for qualidade in _DEGRAUS_QUALIDADE:
        if not imagem_redimensionada.save(str(destino), "JPG", qualidade):
            raise ValueError(f"Falha ao salvar a miniatura em '{destino}'.")
        qualidade_usada = qualidade
        if destino.stat().st_size <= TAMANHO_MAXIMO_BYTES:
            break
        # Continua tentando o próximo degrau; o save seguinte sobrescreve.

    return destino.name


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
