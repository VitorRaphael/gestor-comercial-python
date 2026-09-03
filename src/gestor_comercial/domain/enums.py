import enum


class PerfilUsuario(enum.Enum):
    """Perfis de quem loga no sistema (§3.1). Funcionário de atendimento
    (garçom, cozinha) não tem perfil nenhum — não loga, ver `Funcionario`."""

    ADMIN = "ADMIN"
    GERENTE = "GERENTE"
    OPERADOR_CAIXA = "OPERADOR_CAIXA"


class StatusMesa(enum.Enum):
    LIVRE = "LIVRE"
    OCUPADA = "OCUPADA"


class StatusComanda(enum.Enum):
    ABERTA = "ABERTA"
    EM_CONFERENCIA = "EM_CONFERENCIA"
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


class TipoConexaoImpressora(enum.Enum):
    """Como o cupom chega até a impressora térmica (§3.12).

    Os quatro primeiros são os drivers do python-escpos. ARQUIVO é uma
    DIVERGÊNCIA do Java: grava o cupom num .txt em vez de mandar pra porta,
    e é o que permite testar o fluxo inteiro antes de a impressora física
    chegar no food truck.
    """

    USB = "USB"
    SERIAL = "SERIAL"
    REDE = "REDE"
    WINDOWS = "WINDOWS"
    ARQUIVO = "ARQUIVO"
