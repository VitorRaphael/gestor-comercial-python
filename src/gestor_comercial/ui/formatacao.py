"""Como o dinheiro aparece na tela — o único lugar do sistema que decide isso.

Ver `REMASTERIZACAO-V1.md` §3.8. Antes deste módulo existiam **dez** cópias de
`_formatar_reais` espalhadas pelas views: nove idênticas e uma divergente, em
`mesas_view.py`. A mesma quantia aparecia como `R$ 1234,50` em nove telas e
`R$ 1.234,50` na tela de Mesas — divergência visível para o usuário final.

O formato vencedor é o **com separador de milhar** (decisão do Vitor,
2026-09-06). Três motivos:

1. É o correto em português.
2. É o que o cupom impresso já usava (`services/formatador_cupom.moeda`), então
   tela e papel passam a dizer a mesma coisa. `test_formatacao.py` tranca essa
   igualdade — se um dos dois mudar sozinho, a suíte acusa.
3. Num turno bom o food truck passa de mil reais, então `R$ 1234,50` era o caso
   comum, não a exceção.

O arredondamento não é decidido aqui: todo valor passa por `dinheiro()` antes de
virar texto, a mesma função que o resto do sistema usa para somar, comparar e
gravar. Sem isso a tela arredondaria com o padrão do Python (meio para o par) e
o cupom com o critério do balcão (meio para cima) — um centavo de diferença
entre o que o pai do Vitor lê na tela e o que ele entrega impresso.

Não copie estas funções para dentro de uma view. Importe daqui: é essa regra
que impede a divergência de voltar.
"""

from __future__ import annotations

from decimal import Decimal

from gestor_comercial.services.dinheiro import ZERO, dinheiro

SIMBOLO = "R$"

# Diferença de caixa igual a zero não é "R$ 0,00": é "não houve diferença". O
# travessão diz isso sem o operador precisar comparar o número com zero.
SEM_DIFERENCA = "—"


def formatar_reais(valor: Decimal | int | str) -> str:
    """`Decimal("1234.5")` vira `'R$ 1.234,50'`.

    Valor negativo leva o sinal **antes** do símbolo (`'-R$ 12,00'`), como já
    fazia `formatar_reais_com_sinal` e como já saía das telas que montam o sinal
    à mão (o `-` das sangrias e despesas no Caixa). Antes desta unificação a
    mesma tela conseguia mostrar `R$ -12,00` numa linha e `-R$ 12,00` na de
    baixo.
    """
    numero = dinheiro(valor)
    sinal = "-" if numero < ZERO else ""
    return f"{sinal}{SIMBOLO} {_separar_milhares(abs(numero))}"


def formatar_reais_com_sinal(valor: Decimal | int | str) -> str:
    """Igual a `formatar_reais`, mas zero vira `'—'` em vez de `'R$ 0,00'`.

    Existe para as **diferenças de fechamento** (Dashboard e Histórico), onde
    zero é a notícia boa e merece leitura diferente de um valor apurado.
    """
    if dinheiro(valor) == ZERO:
        return SEM_DIFERENCA
    return formatar_reais(valor)


def _separar_milhares(valor: Decimal) -> str:
    """`Decimal("1234.50")` vira `'1.234,50'` — sem símbolo e sem sinal.

    `f"{valor:,.2f}"` formata no padrão americano (`'1,234.50'`). A troca em
    três passos, usando `X` como casa de passagem, existe porque um
    `replace(",", ".")` seguido de `replace(".", ",")` desfaria o próprio
    trabalho e devolveria `'1,234,50'`.
    """
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
