"""O layout do cupom do cliente — recibo e pré-conta — em colunas (§9.30).

Antes, recibo e pré-conta montavam cada um o próprio cabeçalho, a lista
"2x X-Burger ....... 46,00" e o rodapé, dentro do `impressao_service`. Os dois
são o MESMO cupom com um miolo diferente (a pré-conta mostra subtotal e
desconto; o recibo, os pagamentos), e este módulo é a parte comum:

* **cabeçalho** — nome da loja em destaque, telefone, cidade/UF, número da
  comanda e data/hora;
* **tabela de itens** — `CÓDIGO | DESCRIÇÃO | PREÇO | QTD | TOTAL` entre
  tracejados, com as colunas numéricas encostadas na direita;
* **total em destaque** e **rodapé** — operador, local, permanência e o aviso
  `NÃO É DOCUMENTO FISCAL`.

Tudo aqui é puro, como no `formatador_cupom`: entram dados já lidos e a data
por parâmetro, sai `Documento`. Nada abre banco nem lê o relógio, e é isso que
deixa cada largura testável com um assert. Custo: uma passada pelos itens,
algumas strings por linha — nada que o Celeron perceba.

## A escala (§9.30)

Só as linhas de DESTAQUE saem ampliadas (`BlocoTexto(ampliado=True)`): o nome
da loja e o TOTAL. A tabela fica na fonte normal, porque em 3x uma bobina de 48
colunas só teria 16 e cinco colunas não cabem em 16. Quem sabe a escala é a
impressora (`Impressora.escala_fonte`); este módulo só precisa dela para
QUEBRAR a linha ampliada na largura que ela vai ter no papel.

## A tabela em duas larguras

Com 40 colunas ou mais, uma linha por item com as cinco colunas lado a lado.
Abaixo disso (a bobina de 58mm, 32 colunas), a descrição ficaria com seis
letras; aí cada item vira DUAS linhas — código e descrição em cima, preço,
quantidade e total embaixo, nas mesmas colunas do cabeçalho. As colunas
continuam alinhadas, só empilhadas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from gestor_comercial.hardware.impressora_escpos import BlocoTexto, Documento
from gestor_comercial.services import formatador_cupom as cupom
from gestor_comercial.services.dinheiro import dinheiro

AVISO_FISCAL = "NÃO É DOCUMENTO FISCAL"

# Abaixo disto a descrição, numa linha só com as outras quatro colunas, fica
# curta demais para ler um nome de produto — e a tabela passa a empilhar.
LARGURA_MINIMA_DA_DESCRICAO = 12

ROTULO_CODIGO = "CÓDIGO"
ROTULO_CODIGO_CURTO = "CÓD"
ROTULO_DESCRICAO = "DESCRIÇÃO"
ROTULO_PRECO = "PREÇO"
ROTULO_QTD = "QTD"
ROTULO_TOTAL = "TOTAL"


@dataclass(frozen=True, slots=True)
class DadosDaLoja:
    """O que a loja cadastrou em Configurações. Campo vazio não imprime linha."""

    nome: str | None = None
    telefone: str | None = None
    cidade: str | None = None
    uf: str | None = None

    @classmethod
    def de(cls, config: object | None) -> "DadosDaLoja":
        """Lido da `LojaConfig` (ou de nada: banco sem a linha única ainda)."""
        if config is None:
            return cls()
        return cls(
            getattr(config, "nome_loja", None),
            getattr(config, "telefone", None),
            getattr(config, "cidade", None),
            getattr(config, "uf", None),
        )

    def cidade_uf(self) -> str:
        cidade = " ".join((self.cidade or "").split())
        uf = (self.uf or "").strip().upper()
        if cidade and uf:
            return f"{cidade}/{uf}"
        return cidade or uf


@dataclass(frozen=True, slots=True)
class ItemDoRecibo:
    """Uma linha da tabela, já sem vínculo com o SQLAlchemy.

    `codigo` é o id do produto: o cadastro não tem código próprio, e o id é o
    número que já identifica o produto em todo o sistema.
    """

    codigo: int
    descricao: str
    preco_unitario: Decimal
    quantidade: int
    observacao: str | None = None

    @property
    def total(self) -> Decimal:
        return dinheiro(dinheiro(self.preco_unitario) * self.quantidade)


@dataclass(frozen=True, slots=True)
class _Colunas:
    """As larguras de uma tabela, calculadas uma vez para todos os itens."""

    codigo: int
    descricao: int
    preco: int
    qtd: int
    total: int
    rotulo_codigo: str
    empilhada: bool


def largura_ampliada(largura: int, escala: int) -> int:
    """Quantos caracteres cabem numa linha ampliada: a largura dividida pela escala."""
    return max(int(largura) // max(int(escala), 1), 1)


def permanencia(inicio: datetime | None, fim: datetime) -> str | None:
    """'45min' ou '1h 05min'. `None` sem início, ou com o relógio andando para trás."""
    if inicio is None or fim < inicio:
        return None
    minutos = int((fim - inicio).total_seconds() // 60)
    horas, resto = divmod(minutos, 60)
    return f"{horas}h {resto:02d}min" if horas else f"{resto}min"


# ---------------------------------------------------------------------------
# Cabeçalho
# ---------------------------------------------------------------------------


def cabecalho(
    loja: DadosDaLoja,
    titulo: str,
    numero_comanda: int,
    agora: datetime,
    largura: int,
    escala: int,
    subtitulo: str | None = None,
) -> Documento:
    """Loja, contato, tipo do cupom, número da comanda e data/hora.

    `subtitulo` é o título do relatório ("RELATÓRIO DE CONSUMO", §9.32),
    centralizado abaixo do tipo do cupom. Opcional porque a pré-conta e o
    recibo não são o mesmo documento, e nem todo cupom quer essa linha.

    O nome da loja é a linha ampliada. Loja sem nome cadastrado não imprime
    "SEM NOME": quem sobe para o destaque é o título do cupom (RECIBO).
    """
    documento: Documento = []
    nome = " ".join((loja.nome or "").split())
    destaque = nome.upper() if nome else titulo
    for linha in cupom.quebrar(destaque, largura_ampliada(largura, escala)):
        documento.append(BlocoTexto(linha, negrito=True, centralizado=True, ampliado=True))
    if loja.telefone and loja.telefone.strip():
        for linha in cupom.quebrar(f"Tel: {loja.telefone.strip()}", largura):
            documento.append(BlocoTexto(linha, centralizado=True))
    if loja.cidade_uf():
        for linha in cupom.quebrar(loja.cidade_uf(), largura):
            documento.append(BlocoTexto(linha, centralizado=True))
    if nome:
        documento.append(BlocoTexto(titulo, negrito=True, centralizado=True))
    if subtitulo:
        for linha in cupom.quebrar(subtitulo, largura):
            documento.append(BlocoTexto(linha, negrito=True, centralizado=True))
    documento.append(BlocoTexto(cupom.separador(largura)))
    documento.append(
        BlocoTexto(
            cupom.duas_colunas(f"COMANDA Nº {numero_comanda}", cupom.data_hora(agora), largura),
            negrito=True,
        )
    )
    return documento


# ---------------------------------------------------------------------------
# Tabela de itens
# ---------------------------------------------------------------------------


def _colunas(itens: Sequence[ItemDoRecibo], largura: int) -> _Colunas:
    """As larguras vêm dos DADOS, não de um número fixo: um total de R$ 1.234,56
    alarga a coluna TOTAL para todos, e nenhum valor é cortado."""
    codigo = max([len(ROTULO_CODIGO_CURTO), *(len(str(i.codigo)) for i in itens)])
    preco = max([len(ROTULO_PRECO), *(len(cupom.moeda(i.preco_unitario)) for i in itens)])
    qtd = max([len(ROTULO_QTD), *(len(str(i.quantidade)) for i in itens)])
    total = max([len(ROTULO_TOTAL), *(len(cupom.moeda(i.total)) for i in itens)])

    # Linha única: código, descrição e três números, com um espaço entre cada.
    numeros = preco + 1 + qtd + 1 + total
    for rotulo in (ROTULO_CODIGO, ROTULO_CODIGO_CURTO):
        largura_codigo = max(codigo, len(rotulo))
        descricao = largura - largura_codigo - 1 - 1 - numeros
        if descricao >= LARGURA_MINIMA_DA_DESCRICAO:
            return _Colunas(largura_codigo, descricao, preco, qtd, total, rotulo, False)

    # Empilhada: a descrição tem a linha de cima inteira depois do código.
    return _Colunas(
        codigo,
        max(largura - codigo - 1, 1),
        preco,
        qtd,
        total,
        ROTULO_CODIGO_CURTO,
        True,
    )


def _numeros(preco: str, qtd: str, total: str, c: _Colunas) -> str:
    return f"{preco.rjust(c.preco)} {qtd.rjust(c.qtd)} {total.rjust(c.total)}"


def tabela_de_itens(itens: Sequence[ItemDoRecibo], largura: int) -> Documento:
    """Cabeçalho de colunas e uma (ou duas) linhas por item, entre tracejados."""
    c = _colunas(itens, largura)
    documento: Documento = [BlocoTexto(cupom.separador(largura))]

    if c.empilhada:
        documento.append(
            BlocoTexto(f"{c.rotulo_codigo.ljust(c.codigo)} {ROTULO_DESCRICAO}"[:largura], negrito=True)
        )
        documento.append(
            BlocoTexto(
                _numeros(ROTULO_PRECO, ROTULO_QTD, ROTULO_TOTAL, c).rjust(largura), negrito=True
            )
        )
    else:
        documento.append(
            BlocoTexto(
                f"{c.rotulo_codigo.ljust(c.codigo)} {ROTULO_DESCRICAO.ljust(c.descricao)[: c.descricao]} "
                + _numeros(ROTULO_PRECO, ROTULO_QTD, ROTULO_TOTAL, c),
                negrito=True,
            )
        )
    documento.append(BlocoTexto(cupom.separador(largura)))

    recuo = " " * (c.codigo + 1)
    for item in itens:
        descricao = cupom.quebrar(item.descricao, c.descricao) or [""]
        numeros = _numeros(
            cupom.moeda(item.preco_unitario), str(item.quantidade), cupom.moeda(item.total), c
        )
        primeira = f"{str(item.codigo).ljust(c.codigo)} {descricao[0]}"
        if c.empilhada:
            documento.append(BlocoTexto(primeira))
            documento.extend(BlocoTexto(f"{recuo}{resto}") for resto in descricao[1:])
            documento.append(BlocoTexto(numeros.rjust(largura)))
        else:
            documento.append(BlocoTexto(f"{primeira.ljust(c.codigo + 1 + c.descricao)} {numeros}"))
            documento.extend(BlocoTexto(f"{recuo}{resto}") for resto in descricao[1:])
        for linha in cupom.linha_secundaria(item.observacao, largura, prefixo="Obs: "):
            documento.append(BlocoTexto(linha))

    documento.append(BlocoTexto(cupom.separador(largura)))
    return documento


# ---------------------------------------------------------------------------
# Total e rodapé
# ---------------------------------------------------------------------------


def total_em_destaque(
    rotulo: str,
    valor: Decimal,
    largura: int,
    escala: int,
    preenchimento: str = " ",
) -> Documento:
    """'TOTAL  R$ 46,00' ampliado; se não couber na largura ampliada, em duas.

    Na bobina de 58mm em 4x cabem 8 caracteres: "TOTAL" numa linha e
    "R$ 46,00" na outra. Um valor que nem assim cabe (R$ 1.234,56 em 8) sai em
    negrito no tamanho normal — cortado pela impressora, o total mentiria.
    """
    valor_texto = f"R$ {cupom.moeda(valor)}"
    estreita = largura_ampliada(largura, escala)
    if len(rotulo) + 1 + len(valor_texto) <= estreita:
        # Os pontinhos (§9.32) só entram na linha que CABE inteira. Nas duas
        # linhas do fallback abaixo não há um vão entre rótulo e valor para
        # preencher — eles estão em linhas diferentes —, e uma fileira de
        # pontos sozinha seria ruído.
        return [
            BlocoTexto(
                cupom.duas_colunas(rotulo, valor_texto, estreita, preenchimento),
                negrito=True,
                ampliado=True,
            )
        ]
    documento: Documento = [
        BlocoTexto(linha, negrito=True, centralizado=True, ampliado=True)
        for linha in cupom.quebrar(rotulo, estreita)
    ]
    if len(valor_texto) <= estreita:
        documento.append(BlocoTexto(valor_texto, negrito=True, centralizado=True, ampliado=True))
    else:
        documento.append(BlocoTexto(valor_texto, negrito=True, centralizado=True))
    return documento


def rodape(
    operador: str,
    local: str,
    tempo: str | None,
    largura: int,
    despedida: str | None = None,
) -> Documento:
    """Operador, local, permanência (quando houver) e o aviso fiscal."""
    documento: Documento = [BlocoTexto(cupom.separador(largura))]
    linhas = [f"OPERADOR(A): {operador}"]
    # LOCAL e permanência dividem a linha (§9.32): são a mesma informação
    # ("onde e por quanto tempo") e juntas economizam uma linha de bobina. Se o
    # local for comprido a ponto de não sobrar vão, `duas_colunas` encurta o
    # local e preserva o tempo — mas aqui quem pode ser comprido é o nome do
    # operador, que por isso ficou na linha dele.
    for texto in linhas:
        # `funcionarios.nome` aceita 120 caracteres e a bobina pode ter 32.
        documento.extend(BlocoTexto(linha) for linha in cupom.quebrar(texto, largura))

    # A linha do local NÃO passa por `quebrar`: ela já vem montada em duas
    # colunas, e `quebrar` normaliza espaços — os espaços que alinham
    # "Permanência" na direita virariam um espaço só. `duas_colunas` já
    # respeita a largura e já encurta o local quando falta vão, então não há
    # nada a quebrar aqui.
    if tempo:
        # `duas_colunas_ou_empilhado` porque o local é texto livre: numa bobina
        # de 20 colunas "LOCAL: MESA 12" e "Permanência: 785h 28min" não cabem
        # juntos, e o par empilha em vez de estourar a largura.
        documento.extend(
            BlocoTexto(linha)
            for linha in cupom.duas_colunas_ou_empilhado(
                f"LOCAL: {local}", f"Permanência: {tempo}", largura
            )
        )
    else:
        documento.extend(
            BlocoTexto(linha) for linha in cupom.quebrar(f"LOCAL: {local}", largura)
        )
    documento.append(BlocoTexto(cupom.separador(largura)))
    for linha in cupom.quebrar(AVISO_FISCAL, largura):
        documento.append(BlocoTexto(linha, negrito=True, centralizado=True))
    if despedida:
        for linha in cupom.quebrar(despedida, largura):
            documento.append(BlocoTexto(linha, centralizado=True))
    return documento
