from __future__ import annotations

from sqlalchemy.orm import Session

from gestor_comercial.repository.base import SessionLocal
from gestor_comercial.repository.caixa_repository import CaixaRepository
from gestor_comercial.repository.categoria_repository import CategoriaRepository
from gestor_comercial.repository.combo_item_repository import ComboItemRepository
from gestor_comercial.repository.comanda_repository import ComandaRepository
from gestor_comercial.repository.funcionario_repository import FuncionarioRepository
from gestor_comercial.repository.impressora_repository import ImpressoraRepository
from gestor_comercial.repository.item_comanda_repository import ItemComandaRepository
from gestor_comercial.repository.loja_config_repository import LojaConfigRepository
from gestor_comercial.repository.mesa_repository import MesaRepository
from gestor_comercial.repository.movimento_caixa_repository import MovimentoCaixaRepository
from gestor_comercial.repository.pagamento_repository import PagamentoRepository
from gestor_comercial.repository.produto_repository import ProdutoRepository
from gestor_comercial.repository.quitacao_consumo_repository import QuitacaoConsumoRepository
from gestor_comercial.repository.usuario_repository import UsuarioRepository


class UnitOfWork:
    """Agrupa todos os repositories em cima de uma única Session.

    Existe por causa de operações que mexem em mais de uma entidade de uma vez
    — registrar pagamento fecha a comanda e libera a mesa. Ou as três coisas
    são gravadas, ou nenhuma é: `commit()` no fim do service, `rollback()` se
    qualquer regra estourar.

    O app desktop cria **um** UnitOfWork no boot e ele vive o processo inteiro:
    é um único usuário numa única máquina, então a Session serve de cache e
    evita reabrir conexão a cada clique (RNF de desempenho).
    """

    def __init__(self, session: Session | None = None) -> None:
        self._session_propria = session is None
        self.session = session if session is not None else SessionLocal()

        self.usuarios = UsuarioRepository(self.session)
        self.funcionarios = FuncionarioRepository(self.session)
        self.mesas = MesaRepository(self.session)
        self.comandas = ComandaRepository(self.session)
        self.itens = ItemComandaRepository(self.session)
        self.produtos = ProdutoRepository(self.session)
        self.categorias = CategoriaRepository(self.session)
        self.combo_itens = ComboItemRepository(self.session)
        self.pagamentos = PagamentoRepository(self.session)
        self.caixas = CaixaRepository(self.session)
        self.movimentos = MovimentoCaixaRepository(self.session)
        self.quitacoes = QuitacaoConsumoRepository(self.session)
        self.impressoras = ImpressoraRepository(self.session)
        self.loja_config = LojaConfigRepository(self.session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def fechar(self) -> None:
        if self._session_propria:
            self.session.close()

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.rollback()
        self.fechar()
