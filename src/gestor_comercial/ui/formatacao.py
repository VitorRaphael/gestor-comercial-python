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


def formatar_para_campo(valor: Decimal | None) -> str:
    """`Decimal("12.5")` vira `'12,50'` — sem símbolo e sem separador de milhar.

    É o que entra num `QLineEdit` que o usuário vai **editar** (preço e custo do
    produto, valor da quitação de consumo): "R$" e ponto de milhar teriam que
    ser removidos de novo na hora de ler o campo de volta. `None` vira campo
    vazio, que é como o cadastro de produto novo abre.

    Passa por `dinheiro()` como todo o resto do módulo: sem isso o campo
    arredondaria meio-para-o-par e o rótulo ao lado, meio-para-cima.
    """
    if valor is None:
        return ""
    return f"{dinheiro(valor):.2f}".replace(".", ",")


def safe_decimal(texto: str | None, padrao: Decimal | None = ZERO) -> Decimal | None:
    """Lê o que o operador digitou num campo de valor. **Nunca levanta.**

    É a função inversa de `formatar_para_campo`, e mora no mesmo módulo pelo
    mesmo motivo do §3.8: se "como o dinheiro vira texto" tem um dono só, "como
    o texto vira dinheiro" também precisa ter — senão a divergência volta pela
    outra ponta.

    Antes desta função, as 8 conversões de campo do projeto eram
    `Decimal(campo.text().strip().replace(",", "."))` copiado à mão, cada uma
    com o seu `except InvalidOperation` no chamador. Todas estavam corretas; o
    problema era o padrão, não as cópias: o nono campo que alguém somasse ia
    esquecer o `try`, e aí um espaço a mais derrubaria o clique. É o mesmo
    defeito que o §3.8 matou nas dez cópias de `_formatar_reais`, um turno antes
    de acontecer.

    Aceita o que o operador de balcão realmente digita:

    - `"12,50"` e `"12.50"` → `Decimal("12.50")`. Vírgula e ponto valem como
      separador decimal quando aparecem sozinhos: o teclado numérico manda um ou
      outro conforme o layout do Windows, e o operador não deveria ter que saber
      qual.
    - `"1.234,56"` → `Decimal("1234.56")`. Com os dois presentes, o ponto é
      milhar — é o formato que `formatar_reais` mostra na tela ao lado.
    - `"R$ 12,50"`, `" 12,50 "`, espaço fino de milhar → o símbolo e os espaços
      são descartados.
    - `""`, `None`, `"-"`, `"abc"`, `"1,2,3"` → devolve `padrao`.

    **`padrao=None` é o modo dos campos obrigatórios**: aí a função devolve
    `None` para o chamador poder marcar o campo em vermelho em vez de gravar um
    zero que o operador não digitou. Num fechamento de caixa, a diferença entre
    "contei zero" e "não consegui ler o que ele contou" é dinheiro.
    """
    if texto is None:
        return padrao
    if isinstance(texto, Decimal):
        texto = str(texto)

    limpo = str(texto).strip()
    for lixo in (SIMBOLO, " ", " ", " "):
        limpo = limpo.replace(lixo, "")
    if not limpo or limpo in ("-", "+", ",", "."):
        return padrao

    if "," in limpo and "." in limpo:
        # Com os dois, o último a aparecer é o decimal e o outro é milhar. Testar
        # a posição em vez de assumir o padrão brasileiro faz `"1,234.56"`
        # (formato americano, que aparece em valor copiado de planilha) ser lido
        # certo em vez de virar erro.
        if limpo.rfind(",") > limpo.rfind("."):
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            limpo = limpo.replace(",", "")
    else:
        limpo = limpo.replace(",", ".")

    try:
        return dinheiro(limpo)
    except (ValueError, TypeError, ArithmeticError):
        # `dinheiro()` recusa o que não é número, o que é infinito e o que passa
        # do teto de NUMERIC(10,2). Nenhum desses pode virar exceção na tela.
        return padrao


def _separar_milhares(valor: Decimal) -> str:
    """`Decimal("1234.50")` vira `'1.234,50'` — sem símbolo e sem sinal.

    `f"{valor:,.2f}"` formata no padrão americano (`'1,234.50'`). A troca em
    três passos, usando `X` como casa de passagem, existe porque um
    `replace(",", ".")` seguido de `replace(".", ",")` desfaria o próprio
    trabalho e devolveria `'1,234,50'`.
    """
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
