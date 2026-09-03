"""Gera resources/icons/app.ico a partir da paleta do QSS (base.qss).

Roda uma vez, na máquina de dev: `.venv\\Scripts\\python.exe packaging\\gerar_icone.py`
O resultado (app.ico) é versionado — não precisa do Pillow na máquina do
cliente final, só para gerar o ícone aqui.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "resources" / "icons" / "app.ico"

FUNDO = "#0b0d16"
BORDA = "#2a2f47"
ACENTO = "#f5b942"
TEXTO = "#f3f4f8"

TAMANHO = 256


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    candidatos = [
        "segoeuib.ttf",
        "arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for nome in candidatos:
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def gerar() -> None:
    img = Image.new("RGBA", (TAMANHO, TAMANHO), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margem = 8
    raio = 48
    draw.rounded_rectangle(
        [margem, margem, TAMANHO - margem, TAMANHO - margem],
        radius=raio,
        fill=FUNDO,
        outline=BORDA,
        width=6,
    )

    # "GC" (Gestor Comercial) centralizado, em dourado -- mesma cor de destaque
    # usada nos botões primários e no foco de campos no QSS.
    texto = "GC"
    fonte = _fonte(120)
    bbox = draw.textbbox((0, 0), texto, font=fonte)
    largura = bbox[2] - bbox[0]
    altura = bbox[3] - bbox[1]
    pos = ((TAMANHO - largura) / 2 - bbox[0], (TAMANHO - altura) / 2 - bbox[1])
    draw.text(pos, texto, font=fonte, fill=ACENTO)

    # Sublinhado curto, remete ao "cursor piscando" da tela de PIN.
    linha_y = int(TAMANHO * 0.74)
    draw.rounded_rectangle(
        [TAMANHO * 0.32, linha_y, TAMANHO * 0.68, linha_y + 10],
        radius=5,
        fill=TEXTO,
    )

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    tamanhos = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(SAIDA, format="ICO", sizes=tamanhos)
    print(f"Ícone gerado em {SAIDA}")


if __name__ == "__main__":
    gerar()
