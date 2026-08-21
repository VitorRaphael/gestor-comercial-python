"""Erros de negócio da aplicação.

Porte direto do pacote `exception` do Gestor Comercial Java. Lá cada uma
virava um status HTTP; aqui, num app desktop, cada uma vira um tipo de
diálogo diferente na UI — mas a separação continua valendo, porque
"produto não encontrado" e "PIN não é de gerente" pedem respostas
diferentes na tela.
"""


class GestorComercialError(Exception):
    """Raiz de todo erro previsto. A UI pode capturar só esta e mostrar a mensagem."""


class RegraDeNegocioError(GestorComercialError):
    """Operação viola uma regra do negócio (lançar item em comanda fechada, abrir caixa com outro aberto)."""


class RecursoNaoEncontradoError(GestorComercialError):
    """Entidade buscada por id não existe."""


class NaoAutorizadoError(GestorComercialError):
    """PIN inválido ou nenhum funcionário logado."""


class AcessoNegadoError(GestorComercialError):
    """Funcionário existe e o PIN confere, mas o perfil não permite a ação."""
