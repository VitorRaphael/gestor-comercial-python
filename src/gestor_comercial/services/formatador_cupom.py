"""Aritmética de colunas do cupom térmico (§3.12).

Existe para separar *o que* imprimir de *como* imprimir. O `impressao_service`
decide que um recibo mostra o total da comanda; este módulo sabe que, numa
bobina de 32 colunas, "TOTAL" à esquerda e "46,00" à direita significa contar
25 espaços no meio.

Todas as funções são puras: entram texto, número e data, sai o texto exato que
vai pro papel. Nada aqui abre banco, fala com impressora ou lê o relógio — o
`datetime` chega sempre por parâmetro. É o que torna cada regra de largura
testável com uma linha de assert, sem hardware e sem fixture.

A bobina não tem tabela, tabulação nem fonte proporcional: alinhar preço à
direita é contar caractere na mão, e é essa contagem que mora aqui.
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from decimal import Decimal

from gestor_comercial.services.dinheiro import ZERO, dinheiro

# Abaixo disso não cabe nem "1x Coca-Cola". `cardapio_service` já barra o
# cadastro fora da faixa 20–96; este piso é o cinto de segurança para uma linha
# antiga (ou um zero digitado direto no banco) não derrubar a impressão inteira.
LARGURA_MINIMA = 20

# Recuo das linhas secundárias (observação e descrição), para elas ficarem
# visualmente penduradas no item a que pertencem quando a cozinha bate o olho.
RECUO = "  "


def largura_util(colunas: int | None) -> int:
    """Largura de trabalho a partir de `Impressora.colunas`, com piso de segurança."""
    try:
        valor = int(colunas)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return LARGURA_MINIMA
    return max(valor, LARGURA_MINIMA)


def truncar(texto: str, largura: int) -> str:
    """Normaliza os espaços de `texto` e corta o que passar de `largura`.

    Corta sem reticências de propósito: caractere gasto com "..." é caractere
    a menos do nome do produto, e o operador prefere ler "X-Burger Duplo Espe"
    a ler "X-Burger Duplo Es...".
    """
    limpo = " ".join(str(texto).split())
    limite = max(int(largura), 1)
    return limpo if len(limpo) <= limite else limpo[:limite]


def quebrar(texto: str, largura: int, recuo: str = "") -> list[str]:
    """Quebra `texto` em linhas de até `largura`, sem partir palavra quando dá.

    Devolve lista vazia para texto em branco, e não `[""]`: quem monta o cupom
    faz `documento.extend(...)` e não deve ganhar uma linha vazia de brinde por
    causa de uma observação que o atendente não preencheu.
    """
    limpo = " ".join(str(texto).split())
    if not limpo:
        return []
    return textwrap.wrap(
        limpo,
        width=max(int(largura), 1),
        initial_indent=recuo,
        subsequent_indent=recuo,
        # Nome de produto sem espaço e maior que a bobina tem que aparecer
        # cortado em duas linhas, não estourar a largura e virar lixo no papel.
        break_long_words=True,
    )


def centralizar(texto: str, largura: int) -> str:
    """Centraliza por espaços à esquerda.

    Numa impressora de verdade quem centraliza é o comando ESC/POS
    (`BlocoTexto(centralizado=True)`); esta função serve para centralizar
    *dentro* de uma linha que a gente mesma monta, como o título de um
    separador. O `rstrip` no fim evita espaço sobrando no `.txt` do modo
    ARQUIVO, sem tirar o recuo da esquerda que é o que centraliza de fato.
    """
    return truncar(texto, largura).center(max(int(largura), 1)).rstrip()


def separador(largura: int, caractere: str = "-", titulo: str | None = None) -> str:
    """Linha divisória, opcionalmente com um título no meio ('--- TOTAL ---')."""
    total = max(int(largura), 1)
    traco = (caractere or "-")[0]
    if not titulo or not str(titulo).strip():
        return traco * total
    rotulo = f" {str(titulo).strip()} "
    return rotulo.center(total, traco)[:total]


def duas_colunas(
    esquerda: str, direita: str, largura: int, preenchimento: str = " "
) -> str:
    """Rótulo à esquerda e valor encostado na borda direita, na mesma linha.

    O valor nunca é cortado — ele é a informação que o cliente confere. Quem
    perde caractere quando não cabe é o rótulo.
    """
    valor = " ".join(str(direita).split())
    # +2 garante espaço para pelo menos um caractere de rótulo e o separador,
    # mesmo se a largura cadastrada for menor que o próprio valor.
    total = max(int(largura), len(valor) + 2)
    espaco_rotulo = total - len(valor) - 1
    rotulo = truncar(esquerda, espaco_rotulo)
    enchimento = (preenchimento or " ")[0]
    if enchimento != " " and rotulo and len(rotulo) < espaco_rotulo:
        # Respiro entre a palavra e os pontinhos: "TOTAL ......" lê melhor que
        # "TOTAL......".
        rotulo = f"{rotulo} "
    return f"{rotulo.ljust(espaco_rotulo, enchimento)[:espaco_rotulo]} {valor}"


def moeda(valor: Decimal | int | str) -> str:
    """Formata no padrão brasileiro: 1234.5 vira '1.234,50'.

    Passa por `dinheiro()` antes de formatar, então segue a mesma política de
    arredondamento do resto do sistema — o cupom nunca mostra um centavo
    diferente do que foi gravado na venda.
    """
    numero = dinheiro(valor)
    inteiro, _, centavos = f"{abs(numero):.2f}".partition(".")
    milhares = f"{int(inteiro):,}".replace(",", ".")
    sinal = "-" if numero < ZERO else ""
    return f"{sinal}{milhares},{centavos}"


def linha_de_valor(
    rotulo: str, valor: Decimal | int | str, largura: int, preenchimento: str = " "
) -> str:
    """Uma linha de dinheiro do cupom: 'Dinheiro' ... '50,00'."""
    return duas_colunas(rotulo, moeda(valor), largura, preenchimento)


def linha_de_item(
    quantidade: int, nome: str, largura: int, valor: Decimal | int | str | None = None
) -> list[str]:
    """'2x X-Burger' com o preço na direita quando houver preço.

    Devolve lista porque nome de produto grande quebra em mais de uma linha; o
    preço fica na primeira, que é onde o olho procura.
    """
    titulo = f"{quantidade}x {nome}".strip()
    if valor is None:
        return quebrar(titulo, largura) or [titulo]

    preco = moeda(valor)
    # O nome quebra numa largura reduzida para o preço caber na mesma linha.
    linhas = quebrar(titulo, max(int(largura) - len(preco) - 1, 1)) or [""]
    linhas[0] = duas_colunas(linhas[0], preco, largura)
    return linhas


def linha_de_venda(
    quantidade: int, nome: str, valor_unitario: Decimal | int | str, largura: int
) -> list[str]:
    """'12x Coca-Cola Lata' com '(un: R$ 7,00) = R$ 84,00' encostado na direita.

    Diferente de `linha_de_item` (que só mostra o total), esta linha existe
    para a seção "ITENS VENDIDOS NO TURNO", onde o operador confere tanto o
    preço praticado quanto o subtotal do produto sem precisar fazer conta.

    Numa bobina larga o nome e o detalhe cabem na mesma linha. Numa bobina
    estreita (32 colunas, a mais comum), truncar o nome pra abrir espaço pro
    detalhe deixaria "X-Burger Espec" ilegível — em vez disso o nome quebra
    inteiro e o detalhe desce pra linha(s) seguinte(s), recuado como uma
    observação de item.
    """
    titulo = f"{quantidade}x {nome}".strip()
    unitario = moeda(valor_unitario)
    subtotal = moeda(dinheiro(dinheiro(valor_unitario) * quantidade))
    detalhe = f"(un: R$ {unitario}) = R$ {subtotal}"

    if len(titulo) + 1 + len(detalhe) <= int(largura):
        return [duas_colunas(titulo, detalhe, largura)]

    linhas = quebrar(titulo, largura) or [titulo]
    linhas.extend(quebrar(detalhe, largura, recuo=RECUO))
    return linhas


def linha_secundaria(texto: str | None, largura: int, prefixo: str = "") -> list[str]:
    """Observação ou descrição pendurada no item, recuada e quebrada na largura.

    Lista vazia quando não há texto: item sem observação não gera linha.
    """
    limpo = texto.strip() if isinstance(texto, str) else ""
    if not limpo:
        return []
    return quebrar(f"{prefixo}{limpo}", largura, recuo=RECUO)


def agrupar_itens_producao(
    itens: list[tuple[int, str, int, str | None]],
) -> list[tuple[int, str, int, str | None]]:
    """Consolida `(produto_id, nome, quantidade, observacao)` repetidos num cupom de produção.

    A chave é `(produto_id, observação normalizada)`, não o nome: nome é texto
    livre de exibição, e dois produtos diferentes que por coincidência tenham
    o mesmo nome cadastrado não podem se fundir numa linha só. A observação
    entra normalizada (sem diferença de espaço/caixa — "Sem cebola" e
    "sem  cebola" são a mesma instrução pra cozinha) e observação diferente
    mantém a linha separada de propósito: "sem gelo" e "com gelo" não podem
    virar uma linha só, senão a cozinha não sabe qual fazer de qual jeito.

    A ordem de saída é a da primeira aparição de cada chave — mesma regra do
    resto do cupom, que segue a ordem em que o atendente lançou os itens.
    """
    grupos: dict[tuple[int, str], list] = {}
    ordem: list[tuple[int, str]] = []
    for produto_id, nome, quantidade, observacao in itens:
        obs_normalizada = " ".join(str(observacao).split()).casefold() if observacao else ""
        chave = (produto_id, obs_normalizada)
        if chave not in grupos:
            grupos[chave] = [produto_id, nome, 0, observacao]
            ordem.append(chave)
        grupos[chave][2] += int(quantidade)

    return [tuple(grupos[chave]) for chave in ordem]


def regua(largura: int) -> str:
    """Régua '1234567890...' para conferir a largura da bobina no cupom de teste.

    Se ela couber em uma linha só, o número de colunas cadastrado bate com o
    papel que está na máquina. Se dobrar, está cadastrado largo demais.
    """
    total = max(int(largura), 1)
    return "".join(str(coluna % 10) for coluna in range(1, total + 1))


def data_hora(momento: datetime) -> str:
    """'21/08/2026 19:42'."""
    return f"{momento:%d/%m/%Y %H:%M}"


def data(momento: datetime) -> str:
    """'21/08/2026'."""
    return f"{momento:%d/%m/%Y}"


def hora(momento: datetime) -> str:
    """'19:42'."""
    return f"{momento:%H:%M}"
