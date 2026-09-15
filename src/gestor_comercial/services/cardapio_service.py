"""Cardápio: categorias, produtos, combos e impressoras.

Porte de CategoriaService.java, ProdutoService.java, ComboItemService.java e
ImpressoraService.java (§3.2, §3.3 e §3.12 da arquitetura). Produto tem
`imagem_path` opcional: nome do arquivo da miniatura já processada (ver
`gestor_comercial.services.imagem_service`), nunca o caminho absoluto nem o
arquivo original — a compressão acontece na UI antes de chamar este service.

`Subcategoria` é a subdivisão de catálogo DENTRO da categoria — "Lanches" →
"Artesanal", "Podrão", "Combos" (§9.9). Ela tem CRUD próprio porque precisa
poder nascer VAZIA, esperando os itens: o gerente planeja a organização antes
de classificar. Desde o §9.13 ela também tem `ativo`, e desativá-la tira os
produtos dela do balcão — a mesma regra da categoria, um nível abaixo. O que
continua valendo é a REGRA DE OURO: quem manda no roteamento do cupom é a
categoria, via `produto.categoria.impressora`, e este service não tem um único
caminho em que a subcategoria toque em impressora.

Cadastrar, editar, desativar e excluir são ações administrativas (§3.1) e
exigem gerente. Listar e buscar não exigem: o atendente precisa do cardápio
aberto na tela o tempo todo para lançar item na comanda.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.combo_item import ComboItem
from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.domain.impressora import (
    BAUDRATE_PADRAO,
    COLUNAS_PADRAO,
    PORTA_REDE_PADRAO,
    Impressora,
)
from gestor_comercial.domain.produto import Produto
from gestor_comercial.domain.subcategoria import Subcategoria
from gestor_comercial.repository.base import DB_PATH
from gestor_comercial.repository.unit_of_work import UnitOfWork
from gestor_comercial.services.auth_service import AuthService
from gestor_comercial.services.dinheiro import ZERO, dinheiro
from gestor_comercial.services.exceptions import RecursoNaoEncontradoError, RegraDeNegocioError
from gestor_comercial.services.texto import chave_de_agrupamento
from gestor_comercial.services.transacao import transacional

# Abaixo de 20 colunas não cabe nem o nome do item; acima de 96 não existe
# bobina térmica comum. É uma cerca contra digitação errada, não uma regra fiscal.
COLUNAS_MINIMAS = 20
COLUNAS_MAXIMAS = 96
PORTA_REDE_MAXIMA = 65535

# Aceita 04b8 ou 0x04b8 — é como o id aparece no Gerenciador de Dispositivos
# do Windows e em etiqueta de impressora, e o gerente não tem que saber qual dos dois.
_ID_USB = re.compile(r"(0[xX])?[0-9a-fA-F]{1,4}")

# Caracteres que o Windows recusa em nome de arquivo. Espaço entra junto porque
# o caminho do cupom acaba indo parar em linha de comando na hora de depurar.
_CARACTERES_PROIBIDOS_EM_ARQUIVO = re.compile(r'[<>:"/\\|?*\s]+')


def margem_percentual(preco: Decimal | None, custo: Decimal | None) -> float:
    """Quanto do preço sobra depois do custo, em pontos percentuais.

    `(preço − custo) / preço × 100`. Morava na tela do Cardápio como função
    solta (§9.11): é a definição de margem do catálogo, e a barra de cada
    produto e a média do topo têm que sair da MESMA conta — duas cópias
    divergiriam na primeira vez que alguém mudasse uma.

    Devolve `float` e não `Decimal` de propósito: não é dinheiro, é uma razão
    que só vira comprimento de barra e um "68%" arredondado na tela, e nunca
    entra em soma de caixa. Custo acima do preço dá margem negativa, que é a
    informação certa (vende no prejuízo); preço ausente ou zero dá 0, porque
    não existe margem de quem não tem preço.
    """
    if preco is None or preco <= 0:
        return 0.0
    return float((preco - (custo or ZERO)) / preco * 100)


@dataclass(frozen=True, slots=True)
class ResumoCardapio:
    """Os números do topo da tela do Cardápio, calculados num lugar só (§9.11).

    Existe para a tela não fazer conta de negócio: ela recebia as listas cruas e
    calculava margem e média sozinha, e buscava as subcategorias uma categoria
    por vez para contá-las — quinze consultas para produzir um número.
    """

    categorias: int
    categorias_ativas: int
    subcategorias: int
    produtos: int
    # Média dos preços do cardápio, em dinheiro (2 casas, meio centavo sobe).
    preco_medio: Decimal
    # Média das margens de cada produto — a margem típica de um item, e não a
    # margem do cardápio somado, que um único produto caro dominaria.
    margem_media: float


def contagem(total: int, singular: str) -> str:
    """"1 produto" / "3 produtos" — o plural regular, que é o de toda palavra
    que estas frases contam (produto, subcategoria, combo, componente)."""
    return f"{total} {singular}" + ("" if total == 1 else "s")


def quantidades_do_conteudo(produtos: int, subcategorias: int) -> str:
    """"3 produtos e 2 subcategorias" — as parcelas que existirem, e só elas.

    Saiu de dentro de `conteudo_da_categoria` quando o cartão de exclusão
    (§9.18) passou a dizer a MESMA contagem com outro começo ("Esta categoria
    contém 3 produtos e 2 subcategorias."). Duas montagens da mesma contagem
    divergiriam no primeiro "1 produtos".
    """
    partes = []
    if produtos:
        partes.append(contagem(produtos, "produto"))
    if subcategorias:
        partes.append(contagem(subcategorias, "subcategoria"))
    return " e ".join(partes)


def conteudo_da_categoria(produtos: int, subcategorias: int) -> str:
    """"ela tem 3 produtos e 2 subcategorias" — o que barra a exclusão simples.

    Função de módulo pelo mesmo motivo de `produtos_vinculados`: a TELA diz esta
    frase no aviso antes de tentar, e a recusa do service a repete. Quem
    insistir e for barrado tem que ler a mesma coisa que leu no aviso, senão
    parecem dois problemas diferentes.
    """
    return "ela tem " + quantidades_do_conteudo(produtos, subcategorias)


def produtos_vinculados(total: int) -> str:
    """"existe 1 produto vinculado" / "existem 3 produtos vinculados".

    Função de módulo, e não texto solto dentro da recusa, porque a TELA diz a
    mesma frase antes de chamar o service (o aviso do modal de exclusão, §9.13):
    a mensagem que o gerente lê ao ser barrado e a que ele leu ao ser avisado
    têm que ser a mesma, senão parecem dois problemas diferentes.
    """
    if total == 1:
        return "existe 1 produto vinculado a ela"
    return f"existem {total} produtos vinculados a ela"


@dataclass(frozen=True, slots=True)
class ResultadoCascata:
    """O que a exclusão em cascata de uma subcategoria fez, em números (§9.13).

    Devolvido, e não só registrado, porque a tela precisa DIZER o que aconteceu:
    "excluí 2 e arquivei 1" é a única forma de o gerente entender por que o
    cardápio encolheu menos do que ele esperava — e por que o relatório do mês
    passado continua fechando.
    """

    excluidos: int
    arquivados: int
    # O grupo (categoria) não pôde sair do banco e ficou marcado (§9.14).
    # Sempre `False` na cascata de subcategoria, que nunca precisa disso: a FK
    # do produto para a subdivisão é anulável, a da categoria não é.
    grupo_arquivado: bool = False


@dataclass(frozen=True, slots=True)
class VinculosDoProduto:
    """O que prende um produto ao banco — a pergunta que a tela faz ANTES de
    oferecer a exclusão (§9.18).

    São as mesmas três perguntas de `_tem_historico`, com a resposta em números
    em vez de um sim/não: o cartão de exclusão precisa DIZER o que vai
    acontecer ("ele também sai da composição de 2 combos"), e um `bool` só
    diria que alguma coisa vai acontecer.
    """

    vendido: bool
    # Em quantos combos ele entra como componente. Cada par (combo, componente)
    # é único (`associar_componente` recusa o repetido), então linhas = combos.
    combos_que_o_contem: int
    # Quantos componentes ele tem, se ele mesmo for um combo.
    componentes: int

    @property
    def tem_historico(self) -> bool:
        return self.vendido or bool(self.combos_que_o_contem) or bool(self.componentes)


@transacional
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
        nome_limpo = self._texto_obrigatorio(nome, "Informe o nome da categoria.")
        self._exigir_nome_de_categoria_livre(nome_limpo, categoria_id=None)

        categoria = Categoria(nome=nome_limpo, ativo=True)
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def listar_categorias(self) -> list[Categoria]:
        """Os grupos que a tela do Cardápio administra — sem os arquivados (§9.14)."""
        return self.uow.categorias.listar_do_cardapio()

    def listar_categorias_ativas(self) -> list[Categoria]:
        return self.uow.categorias.listar_ativas()

    def buscar_categoria(self, categoria_id: int) -> Categoria:
        categoria = self.uow.categorias.buscar_por_id(categoria_id)
        if categoria is None:
            raise RecursoNaoEncontradoError(f"Categoria não encontrada (código {categoria_id}).")
        return categoria

    def editar_categoria(self, categoria_id: int, nome: str) -> Categoria:
        self.auth.exigir_gerente()
        categoria = self._categoria_viva(categoria_id)
        nome_limpo = self._texto_obrigatorio(nome, "Informe o nome da categoria.")
        self._exigir_nome_de_categoria_livre(nome_limpo, categoria.id)

        categoria.nome = nome_limpo
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def desativar_categoria(self, categoria_id: int) -> Categoria:
        self.auth.exigir_gerente()
        categoria = self._categoria_viva(categoria_id)
        if not categoria.ativo:
            raise RegraDeNegocioError(f"A categoria '{categoria.nome}' já está desativada.")

        categoria.ativo = False
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def ativar_categoria(self, categoria_id: int) -> Categoria:
        self.auth.exigir_gerente()
        categoria = self._categoria_viva(categoria_id)
        if categoria.ativo:
            raise RegraDeNegocioError(f"A categoria '{categoria.nome}' já está ativa.")

        categoria.ativo = True
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def _categoria_viva(self, categoria_id: int) -> Categoria:
        """A categoria, desde que não tenha sido excluída (§9.14).

        Arquivada não volta, e não é só simetria com `ativar_produto`: a linha
        dela existe unicamente para segurar a FK dos produtos já vendidos, e
        reativá-la traria de volta um grupo cujos itens continuam arquivados —
        uma categoria vazia com nome de lápide.
        """
        categoria = self.buscar_categoria(categoria_id)
        if categoria.arquivado:
            raise RecursoNaoEncontradoError(
                f"A categoria '{categoria.nome}' foi excluída do cardápio."
            )
        return categoria

    def excluir_categoria(self, categoria_id: int) -> None:
        """Apaga a categoria VAZIA. Com conteúdo dentro, recusa com o número.

        "Vazia" aqui é mais estrito que na subcategoria: nem produto, nem
        subdivisão. Apagar as subdivisões junto sempre foi a regra (§9.9, o
        `cascade` da relação), mas fazê-lo em silêncio quando o gerente clicou
        em "Excluir" na CATEGORIA desmancharia, sem perguntar, a organização de
        um grupo inteiro — e refazê-la é trabalho manual.

        Quem tem conteúdo sai por `excluir_categoria_em_cascata`, atrás da
        Senha Master.
        """
        self.auth.exigir_gerente()
        categoria = self._categoria_viva(categoria_id)
        produtos = len(self.uow.produtos.listar_da_categoria(categoria.id))
        subcategorias = len(self.uow.subcategorias.listar_da_categoria(categoria.id))
        if produtos or subcategorias:
            raise RegraDeNegocioError(
                f"Não é possível excluir a categoria '{categoria.nome}': "
                f"{conteudo_da_categoria(produtos, subcategorias)}. "
                "Mova ou exclua o que está dentro primeiro."
            )

        self.uow.categorias.remover(categoria)
        self.uow.commit()

    def excluir_categoria_em_cascata(self, categoria_id: int) -> ResultadoCascata:
        """Apaga a categoria, as subdivisões e os produtos — com a Senha Master.

        A credencial é conferida pela TELA, na hora (`PinPadDialog.para_exclusao`,
        Nível 3), pela razão do §9.10 e do §9.13: `exigir_gerente()` é satisfeito
        pela SESSÃO, e quem abriu o turno de manhã autorizaria a cascata clicada
        à tarde.

        O critério dos PRODUTOS é o mesmo do §9.13: quem nunca foi vendido (nem
        está preso a um combo) sai do banco; quem tem histórico é arquivado,
        porque apagá-lo arrancaria junto o item da comanda, o total do turno e o
        cupom que já saiu na bobina.

        **A diferença para a subcategoria está na própria categoria.** A FK
        `produtos.subcategoria_id` é anulável, então a subdivisão sempre sai do
        banco; `produtos.categoria_id` é **NOT NULL**, e um produto arquivado
        precisa continuar apontando para alguma categoria. Por isso:

        * se nenhum produto precisou ser guardado, a categoria é **apagada de
          verdade** — e as subdivisões vão junto pelo `cascade` da relação;
        * se algum precisou, a categoria **fica marcada** (`arquivado`), some de
          todas as telas, e as subdivisões são apagadas na mão (uma subdivisão
          de categoria invisível não é alcançável por tela nenhuma, o mesmo
          argumento do §9.9). Os produtos guardados perdem a subdivisão pelo
          `ondelete="SET NULL"` e mantêm a categoria, que é o que a FK exige.

        Tudo num commit só: metade dos produtos apagados e a categoria de pé é
        um estado que ninguém pediu e que a tela não sabe mostrar.
        """
        self.auth.exigir_gerente()
        categoria = self._categoria_viva(categoria_id)
        excluidos = arquivados = guardados = 0
        for produto in self.uow.produtos.listar_da_categoria(categoria.id):
            if not (produto.arquivado or self._tem_historico(produto)):
                self.uow.produtos.remover(produto)
                excluidos += 1
                continue
            guardados += 1
            # Já arquivado (uma cascata de subcategoria anterior o marcou) não
            # conta de novo: o número que a tela mostra é o do que ESTA cascata
            # fez. Ele conta, isso sim, para a categoria ter que ficar.
            if not produto.arquivado:
                produto.arquivado = True
                produto.ativo = False
                self.uow.produtos.salvar(produto)
                arquivados += 1

        if guardados:
            for subcategoria in self.uow.subcategorias.listar_da_categoria(categoria.id):
                self.uow.subcategorias.remover(subcategoria)
            categoria.arquivado = True
            categoria.ativo = False
            categoria.nome = self._nome_de_categoria_arquivada(categoria)
            self.uow.categorias.salvar(categoria)
        else:
            self.uow.categorias.remover(categoria)
        self.uow.commit()
        return ResultadoCascata(
            excluidos=excluidos, arquivados=arquivados, grupo_arquivado=bool(guardados)
        )

    @staticmethod
    def _nome_de_categoria_arquivada(categoria: Categoria) -> str:
        """Libera o nome para o gerente poder recriar o grupo no minuto seguinte.

        `categorias.nome` é `UNIQUE` no banco. Sem renomear, excluir "Lanches"
        e cadastrar "Lanches" de novo — que é exatamente o que se faz ao
        reorganizar um cardápio — esbarraria numa linha que ninguém vê, com um
        erro que ninguém entende.

        O sufixo leva o `id`, então é único por construção mesmo que o mesmo
        nome seja excluído duas vezes. O corte a 80 é o da coluna: nome longo
        perde o fim do nome, e não o marcador, que é o que dá a unicidade.
        """
        marcador = f" [excluída #{categoria.id}]"
        return categoria.nome[: 80 - len(marcador)] + marcador

    def associar_impressora(self, categoria_id: int, impressora_id: int) -> Categoria:
        self.auth.exigir_gerente()
        categoria = self._categoria_viva(categoria_id)
        impressora = self.buscar_impressora(impressora_id)

        categoria.impressora = impressora
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def desassociar_impressora(self, categoria_id: int) -> Categoria:
        self.auth.exigir_gerente()
        categoria = self._categoria_viva(categoria_id)

        categoria.impressora = None
        self.uow.categorias.salvar(categoria)
        self.uow.commit()
        return categoria

    def listar_categorias_da_impressora(self, impressora_id: int) -> list[Categoria]:
        """Categorias hoje vinculadas a esta impressora (para a tela Impressoras)."""
        return [
            categoria
            for categoria in self.uow.categorias.listar_do_cardapio()
            if categoria.impressora_id == impressora_id
        ]

    # ------------------------------------------------------------------
    # Subcategorias (§9.9)
    # ------------------------------------------------------------------

    def criar_subcategoria(self, categoria_id: int, nome: str) -> Subcategoria:
        """Cria uma subdivisão da categoria — inclusive VAZIA, sem produto ainda.

        Poder nascer vazia é a razão de a subcategoria ter deixado de ser uma
        coluna de texto no produto (§9.9): o gerente planeja a organização
        primeiro e classifica os itens depois, e não o contrário.
        """
        self.auth.exigir_gerente()
        categoria = self._categoria_viva(categoria_id)
        nome_limpo = self._texto_obrigatorio(nome, "Informe o nome da subcategoria.")
        self._exigir_nome_de_subcategoria_livre(categoria.id, nome_limpo, subcategoria_id=None)

        subcategoria = Subcategoria(nome=nome_limpo, categoria_id=categoria.id)
        self.uow.subcategorias.salvar(subcategoria)
        self.uow.commit()
        return subcategoria

    def listar_subcategorias(self, categoria_id: int) -> list[Subcategoria]:
        """As subdivisões desta categoria, em ordem alfabética.

        Não exige gerente, pelo mesmo motivo de `listar_produtos`: é leitura de
        catálogo, e a tela do Cardápio fica aberta o turno inteiro.
        """
        return self.uow.subcategorias.listar_da_categoria(categoria_id)

    def listar_todas_as_subcategorias(self) -> list[Subcategoria]:
        """As subdivisões do cardápio inteiro, por categoria e depois por nome.

        É a leitura da árvore do Cardápio, que mostra as subdivisões das quinze
        categorias de uma vez: pedir uma categoria por vez eram quinze consultas
        a cada recarga da tela — o N+1 do §3.6 (§9.11).
        """
        return self.uow.subcategorias.listar_todos()

    def buscar_subcategoria(self, subcategoria_id: int) -> Subcategoria:
        subcategoria = self.uow.subcategorias.buscar_por_id(subcategoria_id)
        if subcategoria is None:
            raise RecursoNaoEncontradoError(
                f"Subcategoria não encontrada (código {subcategoria_id})."
            )
        return subcategoria

    def editar_subcategoria(self, subcategoria_id: int, nome: str) -> Subcategoria:
        """Renomeia a subdivisão — e, com ela, o grupo inteiro de uma vez.

        É o que a coluna de texto não conseguia fazer: lá, renomear exigiria
        reescrever a string em cada produto, e uma reescrita em massa que falha
        no meio deixa metade do cardápio num grupo e metade no outro. Aqui o
        nome mora num lugar só, então não existe "metade".
        """
        self.auth.exigir_gerente()
        subcategoria = self.buscar_subcategoria(subcategoria_id)
        nome_limpo = self._texto_obrigatorio(nome, "Informe o nome da subcategoria.")
        self._exigir_nome_de_subcategoria_livre(
            subcategoria.categoria_id, nome_limpo, subcategoria.id
        )

        subcategoria.nome = nome_limpo
        self.uow.subcategorias.salvar(subcategoria)
        self.uow.commit()
        return subcategoria

    def desativar_subcategoria(self, subcategoria_id: int) -> Subcategoria:
        """Tira do balcão os produtos desta subdivisão, sem mexer no cadastro.

        Mesma forma de `desativar_categoria`, e mesmo alcance: quem aplica a
        regra é a consulta de lançamento (`ProdutoRepository._vendavel`), então
        um item de subdivisão desativada some do "Adicionar item" e continua no
        Cardápio, inteiro, esperando a subdivisão voltar.

        Recusar quando já está desativada não é preciosismo: é o que faz um
        duplo clique no botão do rodapé não virar dois commits e uma recarga a
        mais na máquina do food truck.
        """
        self.auth.exigir_gerente()
        subcategoria = self.buscar_subcategoria(subcategoria_id)
        if not subcategoria.ativo:
            raise RegraDeNegocioError(
                f"A subcategoria '{subcategoria.nome}' já está desativada."
            )

        subcategoria.ativo = False
        self.uow.subcategorias.salvar(subcategoria)
        self.uow.commit()
        return subcategoria

    def ativar_subcategoria(self, subcategoria_id: int) -> Subcategoria:
        """Devolve ao balcão os produtos desta subdivisão.

        Devolve os que ESTÃO à venda: um produto desativado individualmente
        (`ativo=False`) continua fora, e é assim que tem que ser — reativar o
        grupo não pode desfazer, calado, a decisão que alguém tomou item a item.
        """
        self.auth.exigir_gerente()
        subcategoria = self.buscar_subcategoria(subcategoria_id)
        if subcategoria.ativo:
            raise RegraDeNegocioError(f"A subcategoria '{subcategoria.nome}' já está ativa.")

        subcategoria.ativo = True
        self.uow.subcategorias.salvar(subcategoria)
        self.uow.commit()
        return subcategoria

    def excluir_subcategoria(self, subcategoria_id: int) -> None:
        """Apaga a subdivisão VAZIA. Com produto dentro, recusa com o número.

        Mudou no §9.13, e a mudança é uma decisão do Vitor sobre risco, não uma
        correção: antes a exclusão sempre passava e os produtos voltavam para
        "Sem subcategoria" (o `ondelete="SET NULL"`). Isso não perdia nada, mas
        também não perguntava nada — um clique em "Excluir" desmanchava, calado,
        a classificação de dezenas de itens, e refazê-la é trabalho manual.

        Agora a etiqueta com itens dentro exige uma decisão explícita sobre os
        itens: ou o gerente os move antes, ou usa
        `excluir_subcategoria_em_cascata` com a Senha Master. O
        `ondelete="SET NULL"` continua de pé no banco como cinto — ele é quem
        garante que, por qualquer caminho que a linha saia, produto nenhum fica
        apontando para uma subdivisão que não existe mais.
        """
        self.auth.exigir_gerente()
        subcategoria = self.buscar_subcategoria(subcategoria_id)
        vinculados = self.uow.produtos.listar_da_subcategoria(subcategoria.id)
        if vinculados:
            raise RegraDeNegocioError(
                f"Não é possível excluir a subcategoria '{subcategoria.nome}': "
                f"{produtos_vinculados(len(vinculados))}. "
                "Mova ou exclua os produtos primeiro."
            )

        self.uow.subcategorias.remover(subcategoria)
        self.uow.commit()

    def excluir_subcategoria_em_cascata(self, subcategoria_id: int) -> ResultadoCascata:
        """Apaga a subdivisão E os produtos dela — o caminho da Senha Master.

        A credencial é conferida pela TELA, na hora
        (`PinPadDialog.para_exclusao`, Nível 3), e não aqui: é a convenção do
        §9.10, e o motivo é o mesmo — `exigir_gerente()` é satisfeito pela
        SESSÃO, então quem abriu o turno de manhã autorizaria qualquer cascata
        clicada à tarde. Este método continua exigindo gerente porque é uma
        operação administrativa como todas as outras.

        **Nem todo produto pode sair do banco, e é o histórico que decide.** Um
        produto que já apareceu numa comanda tem `itens_comanda` apontando para
        ele: apagar a linha arrancaria junto o item da venda, o total do turno e
        o cupom que já saiu na bobina. Esses são ARQUIVADOS
        (`Produto.arquivado`) — somem de todas as telas e o passado continua
        fechando. O resto é apagado de verdade.

        Combo é o outro caso de não apagar: um produto que é combo, ou é
        componente de um, tem `combo_itens` apontando para ele, e apagá-lo
        desmontaria a composição de outro item do cardápio que ninguém mandou
        excluir. Arquiva também, pelo mesmo critério — a regra é "quem tem
        vínculo fica marcado".

        Tudo num commit só: metade dos produtos apagados e a subcategoria de pé
        é um estado que ninguém pediu e que a tela não sabe mostrar.
        """
        self.auth.exigir_gerente()
        subcategoria = self.buscar_subcategoria(subcategoria_id)
        excluidos = arquivados = 0
        for produto in self.uow.produtos.listar_da_subcategoria(subcategoria.id):
            if self._tem_historico(produto):
                # Já arquivado (uma cascata anterior deixou a marca e a FK caiu
                # para NULL, ou alguém o reclassificou) não conta de novo: o
                # número que a tela mostra é o do que ESTA cascata fez.
                if not produto.arquivado:
                    produto.arquivado = True
                    # Sair do balcão junto: `arquivado` é lido pelas telas, mas
                    # `ativo` é o que `ComandaService.lancar_item` confere, e um
                    # produto excluído não pode ser lançável por caminho nenhum.
                    produto.ativo = False
                    self.uow.produtos.salvar(produto)
                    arquivados += 1
                continue
            self.uow.produtos.remover(produto)
            excluidos += 1

        self.uow.subcategorias.remover(subcategoria)
        self.uow.commit()
        return ResultadoCascata(excluidos=excluidos, arquivados=arquivados)

    def _tem_historico(self, produto: Produto) -> bool:
        """O produto está preso a alguma linha que não pode ser reescrita?

        As mesmas três perguntas de `excluir_produto`, num lugar só: lá elas
        viram mensagem de recusa, aqui viram a escolha entre apagar e arquivar.
        Duas cópias divergiriam, e a divergência apareceria como
        "FOREIGN KEY constraint failed" no meio de uma cascata.

        Desde o §9.18 a resposta sai de `_vinculos`, que o cartão de exclusão
        do produto também lê: a tela que decide entre "Excluir produto" e
        "Excluir com Senha Master" e a cascata que decide entre apagar e
        arquivar olham para a MESMA definição de histórico.
        """
        return self._vinculos(produto.id).tem_historico

    def _vinculos(self, produto_id: int) -> VinculosDoProduto:
        """Duas consultas: a venda (um EXISTS) e as linhas de combo do produto,
        contadas pelos dois lados de uma vez."""
        linhas = self.uow.combo_itens.listar_vinculos_do_produto(produto_id)
        return VinculosDoProduto(
            vendido=self.uow.itens.existe_com_produto(produto_id),
            combos_que_o_contem=sum(1 for linha in linhas if linha.produto_id == produto_id),
            componentes=sum(1 for linha in linhas if linha.combo_id == produto_id),
        )


    def contar_conteudo_da_categoria(self, categoria_id: int) -> tuple[int, int]:
        """Quantos produtos e quantas subdivisões a categoria tem dentro.

        É o par que a tela precisa ANTES de tentar excluir, para escolher entre
        a confirmação simples e o aviso com a saída pela Senha Master — e para
        dizê-lo com a mesma frase que a recusa do service usaria.
        """
        return (
            len(self.uow.produtos.listar_da_categoria(categoria_id)),
            len(self.uow.subcategorias.listar_da_categoria(categoria_id)),
        )

    def contar_produtos_da_subcategoria(self, subcategoria_id: int) -> int:
        """Quantos produtos estão presos a esta subdivisão.

        É o número que a tela precisa ANTES de tentar excluir, para escolher
        entre a confirmação simples e o aviso com a saída pela Senha Master —
        e para dizê-lo com a mesma frase que a recusa do service usaria.
        Conta o arquivado junto, como `excluir_subcategoria`: a linha dele
        continua apontando para cá.
        """
        return len(self.uow.produtos.listar_da_subcategoria(subcategoria_id))

    def contagem_de_produtos_por_subcategoria(self) -> dict[int, int]:
        """Quantos produtos em cada subdivisão — uma consulta para a árvore toda."""
        return self.uow.subcategorias.contar_produtos()

    def resumo_do_cardapio(self) -> ResumoCardapio:
        """Os quatro números do topo do Cardápio, em três consultas fixas.

        Produto desativado entra na conta, como já entrava: o topo descreve o
        catálogo cadastrado, e é a mesma população que a árvore conta ao lado de
        cada categoria. Só fica fora da média quem não tem preço — nenhum hoje,
        porque o cadastro recusa preço zero, mas um dado antigo não pode puxar a
        média para baixo nem dividir por zero.
        """
        categorias = self.uow.categorias.listar_do_cardapio()
        # Sem os arquivados: o topo descreve o catálogo que está NA TELA, e um
        # "108 itens cadastrados" contando o que nenhuma lista mostra seria o
        # KPI discordando da lista logo abaixo dele.
        produtos = self.uow.produtos.listar_do_cardapio()
        subcategorias = self.uow.subcategorias.listar_todos()

        precificados = [p for p in produtos if p.preco is not None and p.preco > 0]
        if precificados:
            preco_medio = dinheiro(sum((p.preco for p in precificados), ZERO) / len(precificados))
            margem_media = sum(margem_percentual(p.preco, p.custo) for p in precificados) / len(
                precificados
            )
        else:
            preco_medio, margem_media = ZERO, 0.0

        return ResumoCardapio(
            categorias=len(categorias),
            categorias_ativas=sum(1 for c in categorias if c.ativo),
            subcategorias=len(subcategorias),
            produtos=len(produtos),
            preco_medio=preco_medio,
            margem_media=margem_media,
        )

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
        imagem_path: str | None = None,
        subcategoria_id: int | None = None,
    ) -> Produto:
        self.auth.exigir_gerente()
        nome_limpo = self._texto_obrigatorio(nome, "Informe o nome do produto.")
        preco_final = self._preco_valido(preco)
        custo_final = self._custo_valido(custo)
        categoria = self._categoria_viva(categoria_id)

        produto = Produto(
            nome=nome_limpo,
            preco=preco_final,
            custo=custo_final,
            descricao=self._descricao_limpa(descricao),
            categoria_id=categoria.id,
            ativo=True,
            is_combo=bool(is_combo),
            imagem_path=self._imagem_path_limpo(imagem_path),
            subcategoria_id=self._subcategoria_da_categoria(subcategoria_id, categoria.id),
        )
        self.uow.produtos.salvar(produto)
        self.uow.commit()
        return produto

    def listar_produtos_para_lancamento(self) -> list[Produto]:
        """O cardápio vendável com categoria e subcategoria já carregadas (§9.4)."""
        return self.uow.produtos.listar_para_lancamento()

    def listar_produtos(self) -> list[Produto]:
        """O catálogo que a tela do Cardápio administra — sem os arquivados (§9.13)."""
        return self.uow.produtos.listar_do_cardapio()

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
        imagem_path: str | None = None,
        subcategoria_id: int | None = None,
    ) -> Produto:
        self.auth.exigir_gerente()
        produto = self.buscar_produto(produto_id)
        nome_limpo = self._texto_obrigatorio(nome, "Informe o nome do produto.")
        preco_final = self._preco_valido(preco)
        custo_final = self._custo_valido(custo)
        categoria = self._categoria_viva(categoria_id)

        # Mudar o preço aqui não mexe em venda passada: o ItemComanda guarda o
        # preço congelado do momento do lançamento (§3.6).
        produto.nome = nome_limpo
        produto.preco = preco_final
        produto.custo = custo_final
        produto.categoria_id = categoria.id
        produto.descricao = self._descricao_limpa(descricao)
        # Substituição total, igual ao resto do formulário: a tela sempre manda
        # o estado atual da imagem (inclusive None, quando o gerente remove).
        produto.imagem_path = self._imagem_path_limpo(imagem_path)
        # Mesma regra de substituição total, e a conferência olha para a
        # categoria de DESTINO: trocar a categoria de um produto sem trocar a
        # subcategoria o deixaria apontando para uma subdivisão de outra
        # categoria — visível em árvore nenhuma, porque a navegação entra pela
        # categoria. Aqui isso é recusado com mensagem, não gravado calado.
        produto.subcategoria_id = self._subcategoria_da_categoria(subcategoria_id, categoria.id)
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

    def ativar_produto(self, produto_id: int) -> Produto:
        self.auth.exigir_gerente()
        produto = self.buscar_produto(produto_id)
        # Arquivado (§9.13) não volta: a linha só continua no banco para o
        # relatório e o cupom que já saíram. Sem esta recusa, o único caminho
        # que ainda enxerga um arquivado — um instantâneo de tela aberta antes
        # da cascata — o traria de volta ao balcão calado.
        if produto.arquivado:
            raise RegraDeNegocioError(
                f"O produto '{produto.nome}' foi excluído do cardápio e não pode ser reativado."
            )
        if produto.ativo:
            raise RegraDeNegocioError(f"O produto '{produto.nome}' já está ativo.")

        produto.ativo = True
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

    def vinculos_do_produto(self, produto_id: int) -> VinculosDoProduto:
        """O que a tela precisa saber ANTES de oferecer a exclusão (§9.18).

        Sem vínculo nenhum, o cartão é o da confirmação simples e o botão chama
        `excluir_produto`; com qualquer um, o cartão pede a Senha Master e o
        botão chama `arquivar_produto`. É o mesmo par do `contar_*` da categoria
        e da subcategoria.
        """
        produto = self.buscar_produto(produto_id)
        return self._vinculos(produto.id)

    def arquivar_produto(self, produto_id: int) -> Produto:
        """Exclui o produto que tem histórico — o caminho da Senha Master (§9.18).

        Até o §9.17 a exclusão de um produto já vendido era só RECUSADA
        ("Desative-o"), e a desativação deixava o item no Cardápio para sempre,
        com selo. Decisão do Vitor: com a Senha Master do dono, conferida pela
        TELA na hora (`PinPadDialog.para_exclusao`, a convenção do §9.10), ele
        sai de verdade da operação:

        * **arquivado**, e não apagado — a venda passada aponta para esta linha
          (`itens_comanda.produto_id`), e apagá-la arrancaria o item da
          comanda, o total do turno e o cupom que já saiu na bobina. É a mesma
          marca das cascatas do §9.13/§9.14, e pelo mesmo motivo `ativo` desce
          junto: `lancar_item` confere os dois, e `arquivado` sozinho o
          deixaria lançável por um instantâneo de tela antigo;
        * **desamarrado dos combos antes**, e é aqui que ele difere das
          cascatas. Pedido explícito do Vitor: um arquivado continuando dentro
          da composição de um combo vivo seria uma referência ativa para um
          item que não existe mais na operação. Saem as linhas dos dois lados —
          ele como componente de outros combos e, se ele mesmo é combo, a
          composição dele — e todo combo que ficar sem componente volta a ser
          produto comum, a regra de `remover_componente`.

        `combo_itens` não é histórico na V1: impressão e estoque não o leem (a
        baixa de estoque é backlog da V2, §9.15), e a venda de um combo grava o
        próprio combo na comanda. Desfazer a composição não reescreve nada que
        já saiu.

        Tudo num commit só: o produto desamarrado e ainda no cardápio é um
        estado que ninguém pediu.
        """
        self.auth.exigir_gerente()
        produto = self.buscar_produto(produto_id)
        if produto.arquivado:
            raise RegraDeNegocioError(f"O produto '{produto.nome}' já foi excluído do cardápio.")

        combos_afetados: set[int] = set()
        for linha in self.uow.combo_itens.listar_vinculos_do_produto(produto.id):
            combos_afetados.add(linha.combo_id)
            self.uow.combo_itens.remover(linha)
        for combo_id in combos_afetados:
            self._desfazer_combo_sem_componentes(combo_id)

        produto.arquivado = True
        produto.ativo = False
        self.uow.produtos.salvar(produto)
        self.uow.commit()
        return produto

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
        self._desfazer_combo_sem_componentes(combo_id)
        self.uow.commit()

    def _desfazer_combo_sem_componentes(self, combo_id: int) -> None:
        """Combo sem nenhum componente é só um produto comum: volta a ser um, e
        com isso pode inclusive virar componente de outro combo.

        `existe_como_combo` (um EXISTS) e não `listar_por_combo`: a pergunta é
        só "sobrou alguém?", e a listagem carrega produto e categoria de cada
        componente para a tela de composição (§9.15) — pagaria duas consultas
        para responder um sim/não.

        Não faz commit: é passo de quem chama (`remover_componente` e
        `arquivar_produto`), e cada um fecha a própria transação.
        """
        if self.uow.combo_itens.existe_como_combo(combo_id):
            return
        combo = self.uow.produtos.buscar_por_id(combo_id)
        if combo is not None:
            combo.is_combo = False
            self.uow.produtos.salvar(combo)

    def alterar_quantidade_componente(self, combo_item_id: int, quantidade: int) -> ComboItem:
        """Troca quantas unidades do componente o combo entrega (§9.15).

        Existe por causa do stepper da tela de composição. Antes dele, mudar a
        quantidade era remover o componente e associá-lo de novo — dois commits,
        e entre eles um combo com um item a menos (e, se era o único, um combo
        que tinha deixado de ser combo).

        As mesmas travas de `associar_componente` para o que ela aceita:
        gerente, inteiro, maior que zero. Não há teto: o service nunca teve um,
        e o limite de 99 é do stepper — a tela não pode montar um valor que o
        service recuse, mas o service não precisa conhecer a tela.
        """
        self.auth.exigir_gerente()
        quantidade_final = self._quantidade_valida(quantidade)
        item = self.uow.combo_itens.buscar_por_id(combo_item_id)
        if item is None:
            raise RecursoNaoEncontradoError(
                f"Item de combo não encontrado (código {combo_item_id})."
            )

        item.quantidade = quantidade_final
        self.uow.combo_itens.salvar(item)
        self.uow.commit()
        return item

    def listar_componentes(self, combo_id: int) -> list[ComboItem]:
        """Os componentes do combo, na ordem em que foram associados.

        Produto e categoria de cada um já vêm carregados: a tela de composição
        monta um instantâneo deles na abertura, e sem isso cada linha custaria
        duas consultas a mais (ver `ComboItemRepository.listar_por_combo`).
        """
        self.buscar_produto(combo_id)
        return self.uow.combo_itens.listar_por_combo(combo_id)

    # ------------------------------------------------------------------
    # Impressoras (porte de ImpressoraService.java, §3.12)
    # ------------------------------------------------------------------

    def criar_impressora(
        self,
        nome: str,
        tipo_conexao: TipoConexaoImpressora | str = TipoConexaoImpressora.ARQUIVO,
        *,
        vendor_id: str | None = None,
        product_id: str | None = None,
        porta_serial: str | None = None,
        baudrate: int | str | None = None,
        host: str | None = None,
        porta_rede: int | str | None = None,
        nome_fila: str | None = None,
        caminho_arquivo: str | None = None,
        colunas: int | str | None = None,
        ativa: bool = True,
        padrao: bool | None = None,
    ) -> Impressora:
        """Cadastra uma impressora; só o nome é obrigatório.

        Todo parâmetro de conexão é keyword com default para que a chamada
        antiga `criar_impressora("Cozinha")` continue valendo. Sem informar
        nada sai uma impressora ARQUIVO, que grava o cupom num .txt — dá pra
        rodar o food truck inteiro antes de a impressora física chegar.

        `ativa` e `padrao` são o que o cartão de cadastro (§9.19) chama de
        "Situação" e "Uso da impressão". `padrao=None` é o comportamento de
        sempre: vira a padrão só se não houver outra ativa. `True`/`False` é a
        escolha explícita da tela, e vale inclusive para tirar a marca que a
        regra automática daria. Impressora que nasce desligada NUNCA é a padrão,
        pedida ou não — ver `_aplicar_uso`.
        """
        self.auth.exigir_gerente()
        nome_limpo = self._texto_obrigatorio(nome, "Informe o nome da impressora.")
        self._exigir_nome_de_impressora_livre(nome_limpo, impressora_id=None)

        impressora = Impressora(nome=nome_limpo, ativa=bool(ativa), padrao=False)
        impressora.colunas = self._colunas_validas(colunas, COLUNAS_PADRAO)
        self._aplicar_conexao(
            impressora,
            tipo_conexao,
            vendor_id=vendor_id,
            product_id=product_id,
            porta_serial=porta_serial,
            baudrate=baudrate,
            host=host,
            porta_rede=porta_rede,
            nome_fila=nome_fila,
            caminho_arquivo=caminho_arquivo,
        )
        if padrao is None:
            # Sem padrão ativa, item de categoria sem impressora não tem pra onde
            # ir e o recibo do cliente não sai. Marcar a primeira (ou a próxima,
            # se a antiga foi apagada/desativada) faz o dia da instalação
            # funcionar sem depender de mais um clique do gerente.
            padrao = self.uow.impressoras.buscar_padrao() is None
        self._aplicar_uso(impressora, padrao)

        self.uow.impressoras.salvar(impressora)
        self.uow.commit()
        return impressora

    def editar_impressora(
        self,
        impressora_id: int,
        nome: str,
        tipo_conexao: TipoConexaoImpressora | str = TipoConexaoImpressora.ARQUIVO,
        *,
        vendor_id: str | None = None,
        product_id: str | None = None,
        porta_serial: str | None = None,
        baudrate: int | str | None = None,
        host: str | None = None,
        porta_rede: int | str | None = None,
        nome_fila: str | None = None,
        caminho_arquivo: str | None = None,
        colunas: int | str | None = None,
        ativa: bool | None = None,
        padrao: bool | None = None,
    ) -> Impressora:
        """Grava o formulário inteiro de uma impressora já cadastrada.

        É substituição, não remendo: o que não vier no parâmetro do tipo de
        conexão escolhido fica NULL. `colunas=None`, `ativa=None` e
        `padrao=None` são a exceção — significam "não mexe", porque são campos
        que a tela pode simplesmente não estar editando.

        `padrao=True` tira a marca da antiga padrão no MESMO commit (a escolha
        "Recibo do cliente" do cartão, §9.19): gravar a impressora e só depois
        chamar `definir_padrao` deixaria uma janela em que duas estão marcadas,
        ou nenhuma, se a segunda chamada falhasse.
        """
        self.auth.exigir_gerente()
        impressora = self.buscar_impressora(impressora_id)
        nome_limpo = self._texto_obrigatorio(nome, "Informe o nome da impressora.")
        self._exigir_nome_de_impressora_livre(nome_limpo, impressora.id)

        impressora.nome = nome_limpo
        impressora.colunas = self._colunas_validas(colunas, impressora.colunas)
        self._aplicar_conexao(
            impressora,
            tipo_conexao,
            vendor_id=vendor_id,
            product_id=product_id,
            porta_serial=porta_serial,
            baudrate=baudrate,
            host=host,
            porta_rede=porta_rede,
            nome_fila=nome_fila,
            caminho_arquivo=caminho_arquivo,
        )
        if ativa is not None:
            impressora.ativa = bool(ativa)
        self._aplicar_uso(impressora, impressora.padrao if padrao is None else padrao)

        self.uow.impressoras.salvar(impressora)
        self.uow.commit()
        return impressora

    def excluir_impressora(self, impressora_id: int) -> None:
        self.auth.exigir_gerente()
        impressora = self.buscar_impressora(impressora_id)
        # Apagar deixaria as categorias apontando pro vazio, e os itens delas
        # passariam a cair no fallback sem ninguém perceber. Trocar a impressora
        # dessas categorias é decisão do gerente, não nossa.
        if self.uow.categorias.existe_com_impressora(impressora.id):
            raise RegraDeNegocioError(
                f"Não é possível excluir a impressora '{impressora.nome}': "
                "há categorias do cardápio apontando pra ela. Troque a impressora "
                "dessas categorias no Cardápio antes, ou apenas desative esta."
            )

        era_padrao = bool(impressora.padrao)
        self.uow.impressoras.remover(impressora)
        # Mesma invariante que `criar_impressora` e `editar_impressora` mantêm:
        # sempre que houver impressora ativa, uma delas é a padrão. Excluir a
        # padrão sem eleger outra deixaria o recibo, o fechamento de caixa e o
        # fallback de categoria sem impressora fora do ar — em silêncio, e sem
        # nada na tela ligando o efeito à exclusão que acabou de acontecer.
        if era_padrao:
            for candidata in self.uow.impressoras.listar_ativas():
                candidata.padrao = True
                self.uow.impressoras.salvar(candidata)
                break
        self.uow.commit()

    def definir_padrao(self, impressora_id: int) -> Impressora:
        """Elege a impressora do recibo, do fechamento e do fallback (§3.12)."""
        self.auth.exigir_gerente()
        impressora = self.buscar_impressora(impressora_id)
        if not impressora.ativa:
            raise RegraDeNegocioError(
                f"A impressora '{impressora.nome}' está desativada. "
                "Ative-a antes de defini-la como padrão."
            )

        self._aplicar_uso(impressora, True)
        self.uow.impressoras.salvar(impressora)
        self.uow.commit()
        return impressora

    def listar_impressoras(self) -> list[Impressora]:
        return self.uow.impressoras.listar_todos()

    def listar_impressoras_ativas(self) -> list[Impressora]:
        return self.uow.impressoras.listar_ativas()

    def buscar_impressora(self, impressora_id: int) -> Impressora:
        impressora = self.uow.impressoras.buscar_por_id(impressora_id)
        if impressora is None:
            raise RecursoNaoEncontradoError(f"Impressora não encontrada (código {impressora_id}).")
        return impressora

    # ------------------------------------------------------------------
    # Validações
    # ------------------------------------------------------------------

    def _aplicar_conexao(
        self,
        impressora: Impressora,
        tipo_conexao: TipoConexaoImpressora | str,
        *,
        vendor_id: str | None,
        product_id: str | None,
        porta_serial: str | None,
        baudrate: int | str | None,
        host: str | None,
        porta_rede: int | str | None,
        nome_fila: str | None,
        caminho_arquivo: str | None,
    ) -> None:
        """Valida os parâmetros do tipo escolhido e escreve só os que ele usa."""
        tipo = self._tipo_de_conexao_valido(tipo_conexao)

        # Limpa tudo antes de preencher: trocar de USB pra REDE tem que apagar o
        # vendor_id antigo, senão a linha guarda parâmetro que ninguém mais usa
        # e a tela de cadastro exibe lixo de uma configuração morta.
        impressora.tipo_conexao = tipo
        impressora.vendor_id = None
        impressora.product_id = None
        impressora.porta_serial = None
        impressora.baudrate = None
        impressora.host = None
        impressora.porta_rede = None
        impressora.nome_fila = None
        impressora.caminho_arquivo = None

        if tipo is TipoConexaoImpressora.USB:
            impressora.vendor_id = self._id_usb(vendor_id, "vendor id")
            impressora.product_id = self._id_usb(product_id, "product id")
        elif tipo is TipoConexaoImpressora.SERIAL:
            impressora.porta_serial = self._texto_obrigatorio(
                porta_serial, "Informe a porta serial da impressora (ex: COM3)."
            )
            impressora.baudrate = self._inteiro_positivo(
                baudrate,
                BAUDRATE_PADRAO,
                "A velocidade da porta serial (baudrate) deve ser um número "
                "maior que zero. O valor mais comum é 9600.",
            )
        elif tipo is TipoConexaoImpressora.REDE:
            impressora.host = self._texto_obrigatorio(
                host, "Informe o endereço de rede da impressora (ex: 192.168.0.50)."
            )
            impressora.porta_rede = self._porta_de_rede_valida(porta_rede)
        elif tipo is TipoConexaoImpressora.WINDOWS:
            impressora.nome_fila = self._texto_obrigatorio(
                nome_fila,
                "Informe o nome da impressora exatamente como ele aparece em "
                "Dispositivos e Impressoras do Windows.",
            )
        else:
            # ARQUIVO: sem caminho informado a gente escolhe um, senão o modo de
            # teste exigiria justamente a configuração que ele existe pra evitar.
            impressora.caminho_arquivo = self._caminho_de_arquivo(
                caminho_arquivo, impressora.nome
            )

    def _aplicar_uso(self, impressora: Impressora, padrao: bool) -> None:
        """Marca (ou desmarca) a impressora como a do recibo, sem commit.

        Um lugar só para as duas regras da marca, que antes moravam em três
        métodos:

        * **desligada nunca é a padrão**, pedida ou não. O fallback mandaria
          cupom para um destino que o próprio gerente desativou; zerar a marca
          deixa isso visível na tela em vez de virar armadilha na hora do
          movimento. Vale para o cadastro que nasce desligado (§9.19) e para a
          edição que desliga;
        * **só uma marcada**: duas ao mesmo tempo fariam o recibo sair em uma e
          o fechamento em outra, dependendo da ordem do banco. As outras perdem
          a marca aqui, antes do commit de quem chamou — então a troca é atômica.

        Compara por identidade (`is not`) e não por id: no cadastro a impressora
        ainda não foi gravada e não tem id, e `None != outra.id` derrubaria a
        marca de todo mundo, inclusive dela mesma numa segunda passada.
        """
        marcar = bool(padrao) and bool(impressora.ativa)
        if marcar:
            for outra in self.uow.impressoras.listar_todos():
                if outra is not impressora and outra.padrao:
                    outra.padrao = False
                    self.uow.impressoras.salvar(outra)
        impressora.padrao = marcar

    def _exigir_nome_de_impressora_livre(self, nome: str, impressora_id: int | None) -> None:
        existente = self.uow.impressoras.buscar_por_nome(nome)
        if existente is not None and existente.id != impressora_id:
            raise RegraDeNegocioError(f"Já existe uma impressora com o nome '{nome}'.")

    @staticmethod
    def _tipo_de_conexao_valido(
        tipo_conexao: TipoConexaoImpressora | str | None,
    ) -> TipoConexaoImpressora:
        if isinstance(tipo_conexao, TipoConexaoImpressora):
            return tipo_conexao
        opcoes = ", ".join(tipo.value for tipo in TipoConexaoImpressora)
        # A tela entrega o texto do combo box; aceitar str aqui evita repetir a
        # conversão em cada view.
        if isinstance(tipo_conexao, str):
            try:
                return TipoConexaoImpressora(tipo_conexao.strip().upper())
            except ValueError as erro:
                raise RegraDeNegocioError(
                    f"Tipo de conexão '{tipo_conexao}' não existe. Escolha um destes: {opcoes}."
                ) from erro
        raise RegraDeNegocioError(f"Escolha o tipo de conexão da impressora: {opcoes}.")

    @staticmethod
    def _texto_obrigatorio(valor: str | None, mensagem: str) -> str:
        texto = valor.strip() if isinstance(valor, str) else ""
        if not texto:
            raise RegraDeNegocioError(mensagem)
        return texto

    @staticmethod
    def _id_usb(valor: str | None, campo: str) -> str:
        texto = valor.strip() if isinstance(valor, str) else ""
        if not texto:
            raise RegraDeNegocioError(
                f"Informe o {campo} da impressora USB (ex: 0x04b8). Ele aparece no "
                "Gerenciador de Dispositivos do Windows, em Detalhes > Ids de hardware."
            )
        if not _ID_USB.fullmatch(texto):
            raise RegraDeNegocioError(
                f"O {campo} '{texto}' não é válido. Use o número hexadecimal da "
                "impressora, no formato 0x04b8."
            )
        # Grava sempre como 0xXXXX: o driver converte com int(valor, 16) e não
        # pode depender de o gerente ter digitado o prefixo.
        return f"0x{int(texto, 16):04x}"

    @staticmethod
    def _inteiro_positivo(valor: int | str | None, padrao: int, mensagem: str) -> int:
        if isinstance(valor, str):
            # QLineEdit devolve texto; converter aqui evita espalhar int() pelas views.
            texto = valor.strip()
            if not texto:
                return padrao
            if not texto.isdigit():
                raise RegraDeNegocioError(mensagem)
            valor = int(texto)
        if valor is None:
            return padrao
        # bool é subclasse de int em Python: sem este isinstance, baudrate=True
        # entraria como 1.
        if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
            raise RegraDeNegocioError(mensagem)
        return valor

    def _porta_de_rede_valida(self, porta_rede: int | str | None) -> int:
        mensagem = (
            "A porta de rede da impressora deve ser um número entre 1 e "
            f"{PORTA_REDE_MAXIMA}. Quase toda impressora térmica usa {PORTA_REDE_PADRAO}."
        )
        porta = self._inteiro_positivo(porta_rede, PORTA_REDE_PADRAO, mensagem)
        if porta > PORTA_REDE_MAXIMA:
            raise RegraDeNegocioError(mensagem)
        return porta

    def _colunas_validas(self, colunas: int | str | None, padrao: int) -> int:
        mensagem = (
            "A largura da bobina deve ficar entre "
            f"{COLUNAS_MINIMAS} e {COLUNAS_MAXIMAS} colunas. "
            "Use 32 para bobina de 58mm e 48 para bobina de 80mm."
        )
        valor = self._inteiro_positivo(colunas, padrao, mensagem)
        if valor < COLUNAS_MINIMAS or valor > COLUNAS_MAXIMAS:
            raise RegraDeNegocioError(mensagem)
        return valor

    @staticmethod
    def _caminho_de_arquivo(caminho_arquivo: str | None, nome_impressora: str) -> str:
        if isinstance(caminho_arquivo, str) and caminho_arquivo.strip():
            return caminho_arquivo.strip()
        # O .txt cai ao lado do banco — inclusive quando GESTOR_COMERCIAL_DB
        # aponta pra outro lugar —, então os cupons de teste ficam junto do
        # resto dos dados do food truck em vez de espalhados pelo disco.
        arquivo = _CARACTERES_PROIBIDOS_EM_ARQUIVO.sub("_", nome_impressora).strip("_")
        return str(DB_PATH.parent / "cupons" / f"{arquivo or 'impressora'}.txt")

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
    def _descricao_limpa(descricao: str | None) -> str | None:
        if not isinstance(descricao, str):
            return None
        return descricao.strip() or None

    def _subcategoria_da_categoria(
        self, subcategoria_id: int | None, categoria_id: int
    ) -> int | None:
        """Confere que a subdivisão escolhida é DESTA categoria, ou recusa.

        `None` é o estado normal e não erro nenhum: produto sem subcategoria
        aparece no grupo "Sem subcategoria", que é a fila de quem organiza.

        O que não pode passar é um produto de "Lanches" apontando para uma
        subdivisão de "Porções". Isso não é hipótese de laboratório: acontece
        quando o gerente escolhe a subcategoria e DEPOIS troca a categoria no
        mesmo formulário. Gravado, o produto ficaria num grupo que a árvore de
        "Lanches" não desenha e a de "Porções" também não — invisível nas duas.
        """
        if subcategoria_id is None:
            return None
        subcategoria = self.buscar_subcategoria(subcategoria_id)
        if subcategoria.categoria_id != categoria_id:
            raise RegraDeNegocioError(
                f"A subcategoria '{subcategoria.nome}' não pertence a esta categoria. "
                "Escolha uma subcategoria da categoria selecionada."
            )
        return subcategoria.id

    def _exigir_nome_de_subcategoria_livre(
        self, categoria_id: int, nome: str, subcategoria_id: int | None
    ) -> None:
        """Duas subdivisões da MESMA categoria não podem ter o mesmo nome.

        A comparação ignora acento, caixa e espaço repetido (a mesma
        `chave_de_agrupamento` da busca do cardápio), e não é rigor de purista:
        "Podrão" e "podrao" lado a lado na árvore seriam dois grupos que o
        gerente lê como um só, e ele passaria itens para um enquanto procura no
        outro. O `UniqueConstraint` do banco pega só o par idêntico — esta
        checagem é a que enxerga o quase-igual, e é a que produz mensagem em vez
        de estouro de integridade na tela.

        Entre CATEGORIAS o mesmo nome é livre: "Podrão" em Lanches e "Podrão" em
        Porções são duas subdivisões independentes.
        """
        chave = chave_de_agrupamento(nome)
        for existente in self.uow.subcategorias.listar_da_categoria(categoria_id):
            if existente.id != subcategoria_id and chave_de_agrupamento(existente.nome) == chave:
                raise RegraDeNegocioError(
                    f"Já existe a subcategoria '{existente.nome}' nesta categoria."
                )

    @staticmethod
    def _imagem_path_limpo(imagem_path: str | None) -> str | None:
        # Só o nome do arquivo é aceito aqui (ver imagem_service): a pasta é
        # sempre resolvida em runtime, então nada com "/" ou "\" pode entrar
        # no banco por engano.
        if not isinstance(imagem_path, str):
            return None
        texto = imagem_path.strip()
        return texto or None

    @staticmethod
    def _quantidade_valida(quantidade: int) -> int:
        # bool é subclasse de int em Python: sem este isinstance, associar um
        # componente com quantidade=True passaria como quantidade 1.
        if isinstance(quantidade, bool) or not isinstance(quantidade, int):
            raise RegraDeNegocioError("A quantidade do item do combo deve ser um número inteiro.")
        if quantidade <= 0:
            raise RegraDeNegocioError("A quantidade do item do combo deve ser maior que zero.")
        return quantidade
