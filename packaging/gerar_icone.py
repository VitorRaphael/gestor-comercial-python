"""Converte o ícone oficial (PNG) em `resources/icons/app_icon.ico` multi-resolução.

Roda na máquina de dev, uma vez por troca de ícone:

    .venv\\Scripts\\python.exe packaging\\gerar_icone.py [caminho\\do\\icone.png]

Sem argumento, procura nesta ordem: `packaging/app_icon_fonte.png` (a fonte
versionada), `NovoÍconeAPP.png` ou `icone.png` na raiz do repositório, e
`NovoÍconeAPP.png` em Downloads. Uma fonte achada fora de `packaging/` é copiada
para lá, para a próxima geração não depender de um arquivo solto em Downloads.
O `.ico` é versionado: o Pillow só é necessário aqui, nunca na máquina do food
truck.

## Os cantos brancos

A arte oficial é um quadrado arredondado desenhado sobre fundo BRANCO, sem
transparência. Convertida do jeito que veio, a barra de tarefas escura do
Windows mostraria quatro quinas brancas em volta do ícone. O fundo é removido
assim:

1. marca-se como "fora" a região clara ligada aos quatro cantos da imagem
   (preenchimento por conectividade, então o dourado e o creme de DENTRO do
   ícone, que também são claros, nunca são alcançados — a moldura escura os
   separa do fundo);
2. dentro dessa região, cada pixel vira a cor da moldura com a transparência
   que o separa do branco. É o "cor para alfa" dos editores de imagem: o anel
   suavizado entre o branco e a moldura sai como moldura semitransparente, e
   não como um halo cinza-claro.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
FONTE_VERSIONADA = RAIZ / "packaging" / "app_icon_fonte.png"
SAIDA = RAIZ / "resources" / "icons" / "app_icon.ico"

TAMANHOS = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# Brilho (0-255) acima do qual um pixel ligado ao canto conta como fundo. A
# moldura da arte tem brilho ~55; o branco, 255.
LIMIAR_DO_FUNDO = 128
BRANCO_COM_RUIDO = 250


def localizar_fonte(argumento: str | None) -> Path:
    candidatos = [Path(argumento)] if argumento else [
        FONTE_VERSIONADA,
        RAIZ / "NovoÍconeAPP.png",
        RAIZ / "icone.png",
        Path.home() / "Downloads" / "NovoÍconeAPP.png",
    ]
    for candidato in candidatos:
        if candidato.is_file():
            return candidato
    raise SystemExit("Ícone não encontrado. Procurado em:\n  " + "\n  ".join(map(str, candidatos)))


def _cor_da_moldura(brilho: Image.Image, rgb: Image.Image) -> tuple[int, int, int]:
    """A cor do primeiro pixel escuro vindo de cada borda, na linha/coluna do meio."""
    largura, altura = rgb.size
    amostras = []
    for passos in (
        ((x, altura // 2) for x in range(largura)),
        ((x, altura // 2) for x in reversed(range(largura))),
        ((largura // 2, y) for y in range(altura)),
        ((largura // 2, y) for y in reversed(range(altura))),
    ):
        for ponto in passos:
            if brilho.getpixel(ponto) < LIMIAR_DO_FUNDO:
                # alguns pixels para dentro, fora do anel suavizado
                amostras.append(ponto)
                break
    if not amostras:
        raise SystemExit("Não achei a moldura do ícone: a imagem é toda clara?")
    cores = [rgb.getpixel(_para_dentro(p, largura, altura, 4)) for p in amostras]
    return tuple(sum(c[i] for c in cores) // len(cores) for i in range(3))  # type: ignore[return-value]


def _para_dentro(ponto: tuple[int, int], largura: int, altura: int, passos: int) -> tuple[int, int]:
    x, y = ponto
    dx = passos if x < largura // 2 else -passos if x > largura // 2 else 0
    dy = passos if y < altura // 2 else -passos if y > altura // 2 else 0
    return x + dx, y + dy


def remover_fundo_branco(imagem: Image.Image) -> Image.Image:
    rgb = imagem.convert("RGB")
    brilho = rgb.convert("L")
    largura, altura = rgb.size
    moldura = _cor_da_moldura(brilho, rgb)
    brilho_da_moldura = round(0.299 * moldura[0] + 0.587 * moldura[1] + 0.114 * moldura[2])

    # 255 = claro, 0 = escuro; o fundo ligado aos cantos vira 128.
    mapa = brilho.point(lambda v: 255 if v >= LIMIAR_DO_FUNDO else 0)
    for canto in ((0, 0), (largura - 1, 0), (0, altura - 1), (largura - 1, altura - 1)):
        if mapa.getpixel(canto) == 255:
            ImageDraw.floodfill(mapa, canto, 128)
    fora = mapa.point(lambda v: 255 if v == 128 else 0)

    # Acima de BRANCO_COM_RUIDO é fundo puro: a arte tem pixels 250-254 espalhados
    # no branco, que virariam cantos com alfa 1-3 em vez de transparentes.
    escala = 255 / max(1, 255 - brilho_da_moldura)
    alfa_do_fundo = brilho.point(
        lambda v: 0 if v >= BRANCO_COM_RUIDO else max(0, min(255, round((255 - v) * escala)))
    )
    alfa = Image.composite(alfa_do_fundo, Image.new("L", rgb.size, 255), fora)
    cor = Image.composite(Image.new("RGB", rgb.size, moldura), rgb, fora)

    resultado = cor.convert("RGBA")
    resultado.putalpha(alfa)
    return resultado


def gerar(fonte: Path) -> Path:
    if fonte.resolve() != FONTE_VERSIONADA.resolve():
        FONTE_VERSIONADA.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fonte, FONTE_VERSIONADA)
    imagem = remover_fundo_branco(Image.open(FONTE_VERSIONADA))
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    imagem.save(SAIDA, format="ICO", sizes=TAMANHOS)
    return SAIDA


if __name__ == "__main__":
    fonte = localizar_fonte(sys.argv[1] if len(sys.argv) > 1 else None)
    saida = gerar(fonte)
    with Image.open(saida) as ico:
        tamanhos = sorted(ico.info.get("sizes", []))
    print(f"Fonte: {fonte}")
    print(f"Ícone: {saida} ({saida.stat().st_size // 1024} KB) — tamanhos {tamanhos}")
