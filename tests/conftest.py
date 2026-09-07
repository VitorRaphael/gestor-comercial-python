import contextlib
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import gestor_comercial.domain  # noqa: F401 - importar o pacote já registra os mappers
from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.domain.produto import Produto
from gestor_comercial.hardware.impressora_escpos import BlocoTexto, ErroDeImpressao
from gestor_comercial.repository.base import Base
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.loja_config_service import (
    SENHA_LOGIN_PADRAO,
    SENHA_MASTER_PADRAO,
    SENHA_OPERACIONAL_PADRAO,
)

# Sem PIN pessoal por Usuario (§3.13, cascata unificada): não existe mais "o
# PIN da Maria" — só os 3 segredos da loja. Estas constantes continuam
# existindo (e com os mesmos nomes) só para minimizar o diff nos testes que
# já chamavam `auth.login(PIN_X)`/`auth.criar_usuario(nome, PIN_X, perfil)":
# qualquer uma autentica em `login_como` (Nível 1 basta), não representam
# mais o PIN de ninguém específico.
PIN_GERENTE = SENHA_MASTER_PADRAO
PIN_ATENDENTE = SENHA_LOGIN_PADRAO
PIN_OPERACIONAL = SENHA_OPERACIONAL_PADRAO
PIN_MASTER = SENHA_MASTER_PADRAO
PIN_LOGIN = SENHA_LOGIN_PADRAO


@pytest.fixture
def escudo_isolado():
    """Devolve `sys.excepthook`, `sys.stderr` e o logger do app ao estado original.

    Sem isto um teste de escudo contaminaria todo o resto da suíte: o
    `excepthook` é global do interpretador, e o espelho do `stderr` faria o
    pytest capturar saída duas vezes. Mora aqui, e não ao lado de um dos dois
    arquivos, porque `tests/unit/test_resiliencia.py` e `tests/ui/test_caos.py`
    precisam do mesmo isolamento — ver `Mitigação de Falhas.md` §4.
    """
    import logging
    import sys

    from gestor_comercial.core import resilience

    hook_original = sys.excepthook
    stderr_original = sys.stderr
    logger = logging.getLogger(resilience.NOME_LOGGER)
    handlers_originais = list(logger.handlers)
    logger.handlers.clear()
    yield
    logger.handlers.clear()
    logger.handlers.extend(handlers_originais)
    sys.excepthook = hook_original
    sys.stderr = stderr_original


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db_session:
        yield db_session


@pytest.fixture
def uow(session):
    return UnitOfWork(session=session)


@pytest.fixture
def auth(uow):
    return AuthService(uow)


@pytest.fixture
def funcionarios(uow, auth):
    return FuncionarioService(uow, auth)


@pytest.fixture
def gerente(uow, auth):
    """Gerente (Usuario) já cadastrado e logado — o estado normal do app em operação."""
    usuario = auth.criar_usuario("Gerente", PerfilUsuario.GERENTE)
    auth.login_como(usuario.id, PIN_GERENTE)
    return usuario


@pytest.fixture
def atendente(uow, auth, gerente):
    """Usuario operador de caixa (era ATENDENTE) — continua logando, só perfil renomeado."""
    return auth.criar_usuario("Atendente", PerfilUsuario.OPERADOR_CAIXA)


@pytest.fixture
def funcionario(funcionarios, gerente):
    """Funcionario de atendimento (garçom), sem login — para vincular a `Comanda.atendente_id`."""
    return funcionarios.criar("Garçom", "Garçom")


@pytest.fixture
def mesa(uow):
    return uow.mesas.salvar(Mesa(numero=1))


@pytest.fixture
def categoria(uow):
    return uow.categorias.salvar(Categoria(nome="Lanches"))


@pytest.fixture
def produto(uow, categoria):
    return uow.produtos.salvar(
        Produto(nome="X-Burger", preco=Decimal("10.00"), categoria_id=categoria.id)
    )


@pytest.fixture
def caixa_aberto(uow):
    return uow.caixas.salvar(
        Caixa(valor_abertura=Decimal("100.00"), aberto_em=datetime(2026, 8, 20, 8, 0))
    )


# ----------------------------------------------------------------------
# Impressão (§3.12)
# ----------------------------------------------------------------------


class FabricaDeDriverFalso:
    """Faz as vezes de `hardware.abrir_driver`, guardando o que foi impresso.

    É a costura de teste que o contrato da Fase 4 previu no `ImpressaoService`:
    com ela a suíte exercita roteamento, fallback, marcação de `impresso_em` e
    recuperação de falha sem hardware, sem `python-escpos` e sem escrever
    arquivo nenhum.

    `falhar_em` recebe nomes de impressora que devem estourar `ErroDeImpressao`
    — é como o hardware avisa "cabo solto" sem derrubar a venda. `falhar_sempre`
    é o atalho para o caso de nenhuma impressora do cadastro responder.
    """

    def __init__(self, falhar_em=(), falhar_sempre=False):
        self.falhar_em = set(falhar_em)
        self.falhar_sempre = falhar_sempre
        self.enviados: list[tuple[str, list[BlocoTexto]]] = []

    @contextlib.contextmanager
    def __call__(self, impressora):
        if self.falhar_sempre or impressora.nome in self.falhar_em:
            raise ErroDeImpressao(f"Impressora '{impressora.nome}' não encontrada. Cheque o cabo.")
        yield _DriverFalso(self, impressora.nome)

    def texto_de(self, nome: str) -> str:
        """Todo o texto que saiu naquela impressora, para procurar com `in`."""
        return "\n".join(
            "\n".join(bloco.texto for bloco in documento)
            for impressora, documento in self.enviados
            if impressora == nome
        )

    def blocos_de(self, nome: str) -> list[BlocoTexto]:
        """Os blocos crus, para conferir estilo (negrito, dobro, centralizado)."""
        return [
            bloco
            for impressora, documento in self.enviados
            for bloco in documento
            if impressora == nome
        ]

    def cupons_de(self, nome: str) -> int:
        """Quantos cupons separados saíram naquela impressora."""
        return sum(1 for impressora, _ in self.enviados if impressora == nome)

    @property
    def impressoras_usadas(self) -> list[str]:
        return [nome for nome, _ in self.enviados]


class _DriverFalso:
    def __init__(self, fabrica: FabricaDeDriverFalso, nome: str) -> None:
        self._fabrica = fabrica
        self._nome = nome

    def imprimir(self, documento) -> None:
        self._fabrica.enviados.append((self._nome, list(documento)))


@pytest.fixture
def driver():
    return FabricaDeDriverFalso()


@pytest.fixture
def driver_que_falha():
    """Nenhuma impressora responde — o cenário do RNF de §2."""
    return FabricaDeDriverFalso(falhar_sempre=True)


@pytest.fixture
def impressora(uow):
    """Impressora padrão de 58mm, do jeito que sai do cadastro (tipo ARQUIVO)."""
    return uow.impressoras.salvar(
        Impressora(nome="Cozinha", colunas=32, ativa=True, padrao=True)
    )
