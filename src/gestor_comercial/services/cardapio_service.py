"""Cardápio: categorias, produtos, combos e impressoras.

Porte de CategoriaService.java, ProdutoService.java, ComboItemService.java e
ImpressoraService.java (§3.2 e §3.3 da arquitetura). A foto do produto ficou
de fora: não existe `foto_url` nesta versão — é um app desktop, o cardápio é
lido de uma lista, não de uma vitrine com imagem.

Cadastrar, editar, desativar e excluir são ações administrativas (§3.1) e
exigem gerente. Listar e buscar não exigem: o atendente precisa do cardápio
aberto na tela o tempo todo para lançar item na comanda.
"""

from __future__ import annotations

from decimal import Decimal

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.combo_item import ComboItem
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.domain.produto import Produto
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import RecursoNaoEncontradoError, RegraDeNegocioError


class CardapioService:
    """CRUD de categoria, produto, combo e impressora."""

    def __init__(self, uow: UnitOfWork, auth: AuthService) -> None:
        self.uow = uow
        self.auth = auth

    # ------------------------------------------------------------------
    # Categorias (porte de CategoriaService.java)
    # ------------------------------------------------------------------

    def criar_categoria(self, nome: str) -> Categoria:
        self.auth.exigir_gerente()
        nome_limpo = self._nome_obrigatorio(nome, "Informe o nome da categoria.")
        self._exigir_nome_de_categoria_livre(nome_limpo, categoria_id=None)

        categoria = Categoria(nome=nome_limpo, ativo=True)
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def listar_categorias(self) -> list[Categoria]:
        return self.uow.categorias.listar_todos()

    def listar_categorias_ativas(self) -> list[Categoria]:
        return self.uow.categorias.listar_ativas()

    def buscar_categoria(self, categoria_id: int) -> Categoria:
        categoria = self.uow.categorias.buscar_por_id(categoria_id)
        if categoria is None:
            raise RecursoNaoEncontradoError(f"Categoria não encontrada (código {categoria_id}).")
        return categoria

    def editar_categoria(self, categoria_id: int, nome: str) -> Categoria:
        self.auth.exigir_gerente()
        categoria = self.buscar_categoria(categoria_id)
        nome_limpo = self._nome_obrigatorio(nome, "Informe o nome da categoria.")
        self._exigir_nome_de_categoria_livre(nome_limpo, categoria.id)

        categoria.nome = nome_limpo
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def desativar_categoria(self, categoria_id: int) -> Categoria:
        self.auth.exigir_gerente()
        categoria = self.buscar_categoria(categoria_id)
        if not categoria.ativo:
            raise RegraDeNegocioError(f"A categoria '{categoria.nome}' já está desativada.")

        categoria.ativo = False
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def excluir_categoria(self, categoria_id: int) -> None:
        self.auth.exigir_gerente()
        categoria = self.buscar_categoria(categoria_id)
        # Apagar a categoria com produto dentro deixaria o produto órfão e
        # quebraria o histórico de venda dele. Desativar é o caminho certo.
        if self.uow.produtos.existe_com_categoria(categoria.id):
            raise RegraDeNegocioError(
                f"Não é possível excluir a categoria '{categoria.nome}': "
                "há produtos vinculados a ela. Desative a categoria ou "
                "mude esses produtos de categoria antes."
            )

        self.uow.categorias.remover(categoria)
        self.uow.commit()

    def associar_impressora(self, categoria_id: int, impressora_id: int) -> Categoria:
        self.auth.exigir_gerente()
        categoria = self.buscar_categoria(categoria_id)
        impressora = self.buscar_impressora(impressora_id)

        categoria.impressora = impressora
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    # ------------------------------------------------------------------
    # Produtos (porte de ProdutoService.java)
    # ------------------------------------------------------------------

    def criar_produto(
        self,
        nome: str,
        preco: Decimal,
        categoria_id: int,
        custo: Decimal = ZERO,
        descricao: str | None = None,
        is_combo: bool = False,
    ) -> Produto:
        self.auth.exigir_gerente()
        nome_limpo = self._nome_obrigatorio(nome, "Informe o nome do produto.")
        preco_final = self._preco_valido(preco)
        custo_final = self._custo_valido(custo)
        categoria = self.buscar_categoria(categoria_id)

        produto = Produto(
            nome=nome_limpo,
            preco=preco_final,
            custo=custo_final,
            descricao=self._descricao_limpa(descricao),
            categoria_id=categoria.id,
            ativo=True,
            is_combo=bool(is_combo),
        )
        self.uow.produtos.salvar(produto)
        self.uow.commit()
        return produto

    def listar_produtos(self) -> list[Produto]:
        return self.uow.produtos.listar_todos()

    def listar_produtos_ativos(self) -> list[Produto]:
        return self.uow.produtos.listar_ativos_de_categoria_ativa()

    def buscar_produto(self, produto_id: int) -> Produto:
        produto = self.uow.produtos.buscar_por_id(produto_id)
        if produto is None:
            raise RecursoNaoEncontradoError(f"Produto não encontrado (código {produto_id}).")
        return produto

    def atualizar_produto(
        self,
        produto_id: int,
        nome: str,
        preco: Decimal,
        custo: Decimal,
        categoria_id: int,
        descricao: str | None = None,
    ) -> Produto:
        self.auth.exigir_gerente()
        produto = self.buscar_produto(produto_id)
        nome_limpo = self._nome_obrigatorio(nome, "Informe o nome do produto.")
        preco_final = self._preco_valido(preco)
        custo_final = self._custo_valido(custo)
        categoria = self.buscar_categoria(categoria_id)

        # Mudar o preço aqui não mexe em venda passada: o ItemComanda guarda o
        # preço congelado do momento do lançamento (§3.6).
        produto.nome = nome_limpo
        produto.preco = preco_final
        produto.custo = custo_final
        produto.categoria_id = categoria.id
        produto.descricao = self._descricao_limpa(descricao)
        self.uow.produtos.salvar(produto)
        self.uow.commit()
        return produto

    def desativar_produto(self, produto_id: int) -> Produto:
        self.auth.exigir_gerente()
        produto = self.buscar_produto(produto_id)
        if not produto.ativo:
            raise RegraDeNegocioError(f"O produto '{produto.nome}' já está desativado.")

        produto.ativo = False
        self.uow.produtos.salvar(produto)
        self.uow.commit()
        return produto

    def excluir_produto(self, produto_id: int) -> None:
        self.auth.exigir_gerente()
        produto = self.buscar_produto(produto_id)
        # Excluir de verdade só vale para produto que nunca existiu na prática.
        # Se ele já apareceu numa comanda ou dentro de um combo, apagar
        # arrancaria a linha do histórico junto — nesses casos, desative.
        if self.uow.itens.existe_com_produto(produto.id):
            raise RegraDeNegocioError(
                f"Não é possível excluir o produto '{produto.nome}': "
                "ele já foi vendido em alguma comanda. Desative-o."
            )
        if self.uow.combo_itens.existe_como_combo(
            produto.id
        ) or self.uow.combo_itens.existe_como_componente(produto.id):
            raise RegraDeNegocioError(
                f"Não é possível excluir o produto '{produto.nome}': "
                "ele está vinculado a um combo. Desfaça o combo antes."
            )

        self.uow.produtos.remover(produto)
        self.uow.commit()

    # ------------------------------------------------------------------
    # Combos (porte de ComboItemService.java, §3.3)
    # ------------------------------------------------------------------

    def associar_componente(self, combo_id: int, produto_id: int, quantidade: int) -> ComboItem:
        self.auth.exigir_gerente()
        if combo_id == produto_id:
            raise RegraDeNegocioError("Um combo não pode conter ele mesmo como item.")
        quantidade_final = self._quantidade_valida(quantidade)
        combo = self.buscar_produto(combo_id)
        componente = self.buscar_produto(produto_id)

        # §3.3 permite um único nível de composição, e ele tem duas portas de
        # entrada: pôr um combo dentro de outro, ou transformar em combo um
        # produto que já é componente de alguém. O Java fechava só a primeira.
        if componente.is_combo or self.uow.combo_itens.existe_como_combo(componente.id):
            raise RegraDeNegocioError(
                f"'{componente.nome}' já é um combo e não pode entrar dentro de outro combo."
            )
        if self.uow.combo_itens.existe_como_componente(combo.id):
            raise RegraDeNegocioError(
                f"'{combo.nome}' é item de outro combo, então não pode virar um combo também."
            )
        # Divergência intencional do Java, que criava duas linhas iguais em
        # silêncio: o mesmo componente duas vezes vira baixa de estoque
        # dobrada na V2 e confunde quem monta o combo na tela.
        if self.uow.combo_itens.buscar_por_combo_e_produto(combo.id, componente.id) is not None:
            raise RegraDeNegocioError(
                f"'{componente.nome}' já faz parte do combo '{combo.nome}'. "
                "Remova o item do combo antes de associar de novo."
            )

        item = ComboItem(combo_id=combo.id, produto_id=componente.id, quantidade=quantidade_final)
        self.uow.combo_itens.salvar(item)
        if not combo.is_combo:
            combo.is_combo = True
            self.uow.produtos.salvar(combo)
        self.uow.commit()
        return item

    def remover_componente(self, combo_item_id: int) -> None:
        self.auth.exigir_gerente()
        item = self.uow.combo_itens.buscar_por_id(combo_item_id)
        if item is None:
            raise RecursoNaoEncontradoError(
                f"Item de combo não encontrado (código {combo_item_id})."
            )

        combo_id = item.combo_id
        self.uow.combo_itens.remover(item)
        # Combo sem nenhum componente é só um produto comum: volta a ser um, e
        # com isso pode inclusive virar componente de outro combo.
        if not self.uow.combo_itens.listar_por_combo(combo_id):
            combo = self.uow.produtos.buscar_por_id(combo_id)
            if combo is not None:
                combo.is_combo = False
                self.uow.produtos.salvar(combo)
        self.uow.commit()

    def listar_componentes(self, combo_id: int) -> list[ComboItem]:
        self.buscar_produto(combo_id)
        return self.uow.combo_itens.listar_por_combo(combo_id)

    # ------------------------------------------------------------------
    # Impressoras (porte de ImpressoraService.java)
    # ------------------------------------------------------------------

    def criar_impressora(self, nome: str) -> Impressora:
        self.auth.exigir_gerente()
        nome_limpo = self._nome_obrigatorio(nome, "Informe o nome da impressora.")
        if self.uow.impressoras.buscar_por_nome(nome_limpo) is not None:
            raise RegraDeNegocioError(f"Já existe uma impressora com o nome '{nome_limpo}'.")

        impressora = Impressora(nome=nome_limpo)
        self.uow.impressoras.salvar(impressora)
        self.uow.commit()
        return impressora

    def listar_impressoras(self) -> list[Impressora]:
        return self.uow.impressoras.listar_todos()

    def buscar_impressora(self, impressora_id: int) -> Impressora:
        impressora = self.uow.impressoras.buscar_por_id(impressora_id)
        if impressora is None:
            raise RecursoNaoEncontradoError(f"Impressora não encontrada (código {impressora_id}).")
        return impressora

    # ------------------------------------------------------------------
    # Validações
    # ------------------------------------------------------------------

    def _exigir_nome_de_categoria_livre(self, nome: str, categoria_id: int | None) -> None:
        existente = self.uow.categorias.buscar_por_nome(nome)
        if existente is not None and existente.id != categoria_id:
            raise RegraDeNegocioError(f"Já existe uma categoria com o nome '{nome}'.")

    def _preco_valido(self, preco: Decimal) -> Decimal:
        valor = self._valor_monetario(preco, "preço")
        if valor <= ZERO:
            raise RegraDeNegocioError("O preço do produto deve ser maior que zero.")
        return valor

    def _custo_valido(self, custo: Decimal) -> Decimal:
        valor = self._valor_monetario(custo, "custo")
        if valor < ZERO:
            raise RegraDeNegocioError("O custo do produto não pode ser negativo.")
        return valor

    @staticmethod
    def _valor_monetario(valor: Decimal | None, campo: str) -> Decimal:
        if valor is None:
            raise RegraDeNegocioError(f"Informe o {campo}.")
        try:
            return dinheiro(valor)
        except ValueError as erro:
            # float não é tratado aqui de propósito: `dinheiro()` levanta
            # TypeError nesse caso, e é erro de programação da tela (esqueceu
            # de converter pra Decimal), não erro de digitação do operador —
            # mesmo critério de caixa_service.py e pagamento_service.py.
            raise RegraDeNegocioError(
                f"O {campo} informado não é um valor válido. Digite algo como 12.50."
            ) from erro

    @staticmethod
    def _nome_obrigatorio(nome: str, mensagem: str) -> str:
        nome_limpo = nome.strip() if isinstance(nome, str) else ""
        if not nome_limpo:
            raise RegraDeNegocioError(mensagem)
        return nome_limpo

    @staticmethod
    def _descricao_limpa(descricao: str | None) -> str | None:
        if not isinstance(descricao, str):
            return None
        return descricao.strip() or None

    @staticmethod
    def _quantidade_valida(quantidade: int) -> int:
        # bool é subclasse de int em Python: sem este isinstance, associar um
        # componente com quantidade=True passaria como quantidade 1.
        if isinstance(quantidade, bool) or not isinstance(quantidade, int):
            raise RegraDeNegocioError("A quantidade do item do combo deve ser um número inteiro.")
        if quantidade <= 0:
            raise RegraDeNegocioError("A quantidade do item do combo deve ser maior que zero.")
        return quantidade
