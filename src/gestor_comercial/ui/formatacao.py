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

from collections import Counter
from decimal import Decimal

from gestor_comercial.services.dinheiro import LIMITE, ZERO, dinheiro

SIMBOLO = "R$"

# O campo de dinheiro digitado (§9.20) guarda só dígitos e UMA vírgula. A vírgula
# é a mesma que `formatar_para_campo` escreve, então o texto do campo nunca
# precisa ser convertido de volta para ser mostrado.
SEPARADOR_DECIMAL = ","
CASAS_DECIMAIS = 2
# O teto de dígitos inteiros sai do teto do banco, pelo motivo do numpad do §9.6:
# um campo que deixa montar 999.999.999 entrega ao service um valor que
# `dinheiro()` recusa com ValueError.
DIGITOS_INTEIROS = len(str(int(LIMITE)))

# ASCII de propósito, e não `str.isdigit()`: "²" e "١" (dígito arábico) são
# dígitos para o Python e não são para `Decimal` nem para o operador.
_DIGITOS = frozenset("0123456789")
_SEPARADORES = frozenset(",.")

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


def sanitizar_edicao_moeda(anterior: str, novo: str, cursor: int) -> tuple[str, int]:
    """O que um campo de dinheiro guarda depois de uma edição. **Nunca levanta.**

    É a regra do `ValidadorMoeda` (§9.20), fora do Qt para poder ser testada
    tecla a tecla. `anterior` é o texto antes da edição, `novo` é o texto que o
    `QLineEdit` montou com ela (tecla, Ctrl+V, menu de contexto, arrastar, ou
    `setText`) e `cursor` é onde o cursor ficou. Devolve o texto aceito e o
    cursor ajustado a ele.

    O texto devolvido é sempre **canônico**: até 8 dígitos inteiros, no máximo
    uma vírgula e até 2 casas depois dela (`""`, `","` e `"12,"` são estados
    legítimos de quem ainda está digitando). Canônico entra e sai igual — é o
    ponto fixo que impede o validador de reescrever o próprio resultado de novo.

    O que a edição TROUXE é separado do que já estava, e é isso que decide:

    - **Letra, espaço, sinal e símbolo são descartados.** Digitar "a" não muda
      nada; colar "R$ 15,90 kg" deixa "15,90".
    - **Ponto vale como vírgula**, porque o teclado numérico manda um ou outro
      conforme o layout do Windows.
    - **A vírgula que já estava vence.** Um segundo separador digitado é
      recusado — inclusive o ponto depois da vírgula: sem esta regra "12,5" +
      "." seria lido como milhar e viraria 125.
    - **Colagem com milhar é lida como a `safe_decimal` lê**: o separador cujo
      tipo aparece uma vez só, e por último, é o decimal ("1.234,56" e
      "1,234.56" viram "1234,56"); o que se repete é milhar ("1.234.567").
    - **Casa e dígito além do teto: sai o que a edição trouxe.** A 3ª casa
      digitada é recusada, e uma vírgula digitada antes de três dígitos que já
      estavam também — aceitá-la apagaria dígitos que o operador não tocou.
    - **Lixo puro sobre uma seleção não apaga o valor.** Selecionar "12,50" e
      colar "abc" deixa "12,50", e não campo vazio.
    """
    cursor = max(0, min(cursor, len(novo)))
    inicio, fim = _trecho_inserido(anterior, novo, cursor)

    mantidos = [i for i, caractere in enumerate(novo) if caractere in _DIGITOS or caractere in _SEPARADORES]
    decimal = _separador_decimal(novo, mantidos, inicio, fim)
    mantidos = [i for i in mantidos if novo[i] in _DIGITOS or i == decimal]

    if decimal is not None and inicio <= decimal < fim:
        casas_que_ja_estavam = sum(1 for i in mantidos if i > decimal and not inicio <= i < fim)
        if casas_que_ja_estavam > CASAS_DECIMAIS:
            mantidos.remove(decimal)
            decimal = None
    if decimal is not None:
        mantidos = _cortar_excesso(mantidos, [i for i in mantidos if i > decimal], CASAS_DECIMAIS, inicio, fim)
    inteiros = [i for i in mantidos if decimal is None or i < decimal]
    mantidos = _cortar_excesso(mantidos, inteiros, DIGITOS_INTEIROS, inicio, fim)

    trouxe_algo = any(inicio <= i < fim for i in mantidos)
    substituiu_algo = len(anterior) - inicio > len(novo) - fim
    if fim > inicio and not trouxe_algo and substituiu_algo:
        # Uma chamada só de profundidade: com `novo == anterior` o trecho
        # inserido é vazio, e esta condição não tem como valer de novo.
        return sanitizar_edicao_moeda(anterior, anterior, inicio)

    texto = "".join(SEPARADOR_DECIMAL if i == decimal else novo[i] for i in mantidos)
    return texto, sum(1 for i in mantidos if i < cursor)


def _trecho_inserido(anterior: str, novo: str, cursor: int) -> tuple[int, int]:
    """Onde está, em `novo`, o que a edição acabou de trazer: `novo[inicio:fim]`.

    Numa edição do `QLineEdit` o cursor fica logo depois do que entrou, então o
    que está à direita dele já estava no texto. Isso resolve a ambiguidade que
    uma comparação só de prefixo e sufixo não resolve: digitar "5" entre o "5"
    e o "0" de "12,50" é inserir no índice 3, e não no 4.
    """
    depois_do_cursor = len(novo) - cursor
    if depois_do_cursor <= len(anterior) and anterior.endswith(novo[cursor:]):
        fim = cursor
        cabeca_anterior = len(anterior) - depois_do_cursor
    else:
        # Cursor que não marca o fim de uma inserção (chamada fora do fluxo de
        # edição): o maior sufixo comum faz o papel dele.
        comum = _tamanho_do_sufixo_comum(anterior, novo)
        fim = len(novo) - comum
        cabeca_anterior = len(anterior) - comum
    return _tamanho_do_prefixo_comum(anterior[:cabeca_anterior], novo[:fim]), fim


def _separador_decimal(novo: str, mantidos: list[int], inicio: int, fim: int) -> int | None:
    separadores = [i for i in mantidos if novo[i] in _SEPARADORES]
    ja_estavam = [i for i in separadores if not inicio <= i < fim]
    if ja_estavam:
        return ja_estavam[0]
    # Contagem por tipo num passo só: comparar cada separador com todos os
    # outros seria quadrático, e um Ctrl+V de 32 mil vírgulas travaria a tela.
    ocorrencias = Counter(novo[i] for i in separadores)
    unicos = [i for i in separadores if ocorrencias[novo[i]] == 1]
    return unicos[-1] if unicos else None


def _cortar_excesso(mantidos: list[int], grupo: list[int], teto: int, inicio: int, fim: int) -> list[int]:
    """Tira de `grupo` o que passa do `teto`, começando pelo que a edição trouxe.

    Da direita para a esquerda, porque é a ordem em que se digita: a tecla a
    mais é a última. O que já estava só sai se ainda sobrar, e isso só acontece
    com texto que chegou fora do formato.
    """
    excesso = len(grupo) - teto
    if excesso <= 0:
        return mantidos
    trazidos = [i for i in reversed(grupo) if inicio <= i < fim]
    ja_estavam = [i for i in reversed(grupo) if not inicio <= i < fim]
    fora = set((trazidos + ja_estavam)[:excesso])
    return [i for i in mantidos if i not in fora]


def _tamanho_do_prefixo_comum(a: str, b: str) -> int:
    limite = min(len(a), len(b))
    tamanho = 0
    while tamanho < limite and a[tamanho] == b[tamanho]:
        tamanho += 1
    return tamanho


def _tamanho_do_sufixo_comum(a: str, b: str) -> int:
    limite = min(len(a), len(b))
    tamanho = 0
    while tamanho < limite and a[-1 - tamanho] == b[-1 - tamanho]:
        tamanho += 1
    return tamanho


def _separar_milhares(valor: Decimal) -> str:
    """`Decimal("1234.50")` vira `'1.234,50'` — sem símbolo e sem sinal.

    `f"{valor:,.2f}"` formata no padrão americano (`'1,234.50'`). A troca em
    três passos, usando `X` como casa de passagem, existe porque um
    `replace(",", ".")` seguido de `replace(".", ",")` desfaria o próprio
    trabalho e devolveria `'1,234,50'`.
    """
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
