"""Arredondamento de valores monetários.

Todo dinheiro do sistema passa por aqui antes de ser somado, comparado ou
gravado. Centraliza a única política de arredondamento aceita: 2 casas com
ROUND_HALF_UP — o mesmo critério que o pai do Vitor usa de cabeça no balcão
(meio centavo sobe). ROUND_HALF_EVEN, que é o padrão do Python, arredondaria
2.345 para 2.34 e criaria diferença no fechamento do caixa.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVOS = Decimal("0.01")

# Mesmo teto do NUMERIC(10,2) das colunas monetárias do domain: 8 dígitos
# inteiros + 2 decimais. Sem isso um valor gigante passa por quantize() sem
# erro tratado e o SQLite grava (ou trunca) em silêncio um número que a tela
# nunca poderia ter mostrado corretamente.
LIMITE = Decimal("99999999.99")


def dinheiro(valor: Decimal | int | str) -> Decimal:
    """Devolve `valor` como Decimal de exatamente 2 casas, arredondando meio pra cima."""
    # float é recusado de propósito, não por preciosismo: 0.1 + 0.2 em float dá
    # 0.30000000000000004, e um erro desses só aparece semanas depois, como uma
    # diferença de centavos no fechamento que ninguém consegue explicar.
    if isinstance(valor, float):
        raise TypeError("Valor monetário não pode ser float. Use Decimal, int ou str.")
    if isinstance(valor, Decimal):
        bruto = valor
    elif isinstance(valor, (int, str)):
        try:
            bruto = Decimal(valor)
        except InvalidOperation:
            raise ValueError(f"Valor monetário inválido: {valor!r}") from None
    else:
        raise TypeError(f"Valor monetário inválido: tipo {type(valor).__name__} não é aceito.")

    if not bruto.is_finite():
        raise ValueError(f"Valor monetário inválido: {valor!r}")
    if abs(bruto) > LIMITE:
        raise ValueError(f"Valor monetário fora da faixa aceita (máximo {LIMITE}): {valor!r}")
    try:
        return bruto.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        # bruto passou no teto acima mas ainda assim não coube na precisão do
        # contexto decimal (28 dígitos) — acontece com Decimal("1E+30"), por
        # exemplo, que abs() já compara maior que LIMITE, então na prática
        # este bloco é o cinto de segurança para qualquer caso que escape do
        # teto explícito.
        raise ValueError(f"Valor monetário fora da faixa aceita: {valor!r}") from None


ZERO: Decimal = dinheiro(0)
