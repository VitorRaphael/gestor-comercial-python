"""O formato do traço da assinatura manuscrita do consumo interno.

Sem Qt de propósito: o service valida o que vai gravar sem depender da tela, e
o teste de unidade roda sem `QApplication`.

O traço é gravado como JSON pequeno::

    {"v": 1, "w": 520, "h": 180, "tracos": [[[x, y], [x, y], ...], ...]}

`w`/`h` são o tamanho da área em que a pessoa assinou; os pontos são inteiros
nesse espaço. Quem redesenha escala do (w, h) original para o quadro que tiver,
então a assinatura aparece igual num quadro maior ou menor. Cada lista de
`tracos` é uma "caneta abaixada" — do press ao release do mouse.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from gestor_comercial.services.exceptions import RegraDeNegocioError

VERSAO_FORMATO = 1

# Teto de pontos por assinatura. Uma assinatura de verdade tem algumas
# centenas; o teto só impede que um arraste esquecido engorde o banco.
LIMITE_PONTOS = 5000

Ponto = tuple[int, int]


@dataclass(frozen=True)
class Assinatura:
    largura: int
    altura: int
    tracos: tuple[tuple[Ponto, ...], ...]

    @property
    def vazia(self) -> bool:
        return not any(self.tracos)

    def para_json(self) -> str:
        return json.dumps(
            {
                "v": VERSAO_FORMATO,
                "w": self.largura,
                "h": self.altura,
                "tracos": [[list(ponto) for ponto in traco] for traco in self.tracos],
            },
            separators=(",", ":"),
        )


def ler_assinatura(texto: str | None) -> Assinatura:
    """Lê e valida o JSON do traço; recusa com mensagem para o operador."""
    if not isinstance(texto, str) or not texto.strip():
        raise RegraDeNegocioError("O consumo interno precisa da assinatura do colaborador.")
    try:
        dados = json.loads(texto)
        largura = int(dados["w"])
        altura = int(dados["h"])
        tracos = tuple(
            tuple((int(x), int(y)) for x, y in traco) for traco in dados["tracos"]
        )
    except (ValueError, TypeError, KeyError):
        raise RegraDeNegocioError("A assinatura recebida está corrompida. Peça para assinar de novo.") from None

    if largura <= 0 or altura <= 0:
        raise RegraDeNegocioError("A assinatura recebida está corrompida. Peça para assinar de novo.")
    tracos = tuple(traco for traco in tracos if traco)
    if not tracos:
        raise RegraDeNegocioError("O consumo interno precisa da assinatura do colaborador.")
    if sum(len(traco) for traco in tracos) > LIMITE_PONTOS:
        raise RegraDeNegocioError("A assinatura ficou grande demais. Limpe e assine de novo.")
    return Assinatura(largura, altura, tracos)
