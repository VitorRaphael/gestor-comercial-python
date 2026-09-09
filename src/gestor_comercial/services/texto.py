"""Comparação de texto tolerante a acento e caixa — a forma "sem enfeite".

Existe pelo mesmo motivo de `services/dinheiro.py`: é uma regra pequena, sem
Qt e sem banco, que **duas camadas** precisam responder igual.

* a **busca** do cardápio (`ui/widgets/busca_produto.py`) compara o que foi
  digitado com o nome do produto: `"agua"` tem que achar `"Água Mineral"`;
* o **sub-modelo** (§9.8, `CardapioService._subcategoria_canonica`) compara o
  que foi digitado com os sub-modelos que a categoria já tem, para "podrao" não
  virar um segundo grupo ao lado de "Podrão".

Se as duas tivessem cópias próprias, o dia em que uma passasse a ignorar hífen
(ou `ç`, ou espaço duplo) e a outra não, o sub-modelo agrupado numa tela
apareceria separado na outra — e sem erro nenhum na tela para explicar.

Mora em `services/` e não em `ui/` porque a camada de serviço não pode importar
a de tela; o contrário é o caminho normal do projeto.
"""

from __future__ import annotations

import unicodedata


def sem_acento(texto: str) -> str:
    """Casefold + remove diacríticos, para comparação tolerante a acento.

    `NFKD` separa a letra do acento e o filtro descarta as marcas de
    combinação: `"Ação"` vira `"acao"`. O `casefold` é mais agressivo que o
    `lower` de propósito — é o que a documentação do Python indica para
    comparação, e não só para exibição.
    """
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def chave_de_agrupamento(texto: str) -> str:
    """A forma canônica de um rótulo digitado à mão, para dizer se dois são o mesmo.

    Além do acento e da caixa, colapsa espaço repetido e apara as pontas:
    `"  Lanche   Artesanal "` e `"lanche artesanal"` respondem a mesma chave.

    Serve para COMPARAR, nunca para gravar nem para mostrar: o que vai para o
    banco e para a tela é o texto que o gerente escreveu (ou o que a categoria
    já usava), com acento e maiúscula no lugar.
    """
    return sem_acento(" ".join(texto.split()))
