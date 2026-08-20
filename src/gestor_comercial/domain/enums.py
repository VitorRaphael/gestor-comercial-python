import enum


class PerfilFuncionario(enum.Enum):
    ATENDENTE = "ATENDENTE"
    GERENTE = "GERENTE"


class StatusMesa(enum.Enum):
    LIVRE = "LIVRE"
    OCUPADA = "OCUPADA"


class StatusComanda(enum.Enum):
    ABERTA = "ABERTA"
    FECHADA = "FECHADA"
    CANCELADA = "CANCELADA"


class FormaPagamento(enum.Enum):
    CREDITO = "CREDITO"
    DEBITO = "DEBITO"
    DINHEIRO = "DINHEIRO"
    PIX = "PIX"
    CONSUMO_INTERNO = "CONSUMO_INTERNO"


class StatusCaixa(enum.Enum):
    ABERTO = "ABERTO"
    FECHADO = "FECHADO"


class TipoMovimento(enum.Enum):
    SANGRIA = "SANGRIA"
    REFORCO = "REFORCO"
    DESPESA = "DESPESA"
    CONSUMO_FUNCIONARIO = "CONSUMO_FUNCIONARIO"
