"""A regra da busca de produto: substring tolerante a acento e caixa.

Filtra ignorando acento e caixa (`"agua"` acha `"Água Mineral"`), palavra por
palavra. Quem usa é o cartão "Adicionar item" (`adicionar_item_dialog.py`), nos
dois modos dele: o lançamento na comanda e o componente de combo (§9.15).

A busca enxerga também a **subcategoria** (§9.8/§9.9): digitar "artesanal"
lista todos os lanches dessa subcategoria, mesmo que a palavra não apareça no
nome de nenhum deles.

Até o §9.15 este módulo tinha também o `BuscaProdutoWidget`, a busca em texto
corrido (campo + `QListWidget` com ícone) do formulário antigo de componente de
combo. Esse formulário virou o modo componente do cartão, o widget ficou sem
ninguém que o usasse e foi apagado — mantê-lo seria uma segunda busca de
produto no app esperando alguém reaproveitá-la por engano.
"""

from __future__ import annotations

from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.texto import sem_acento as _normalizar


def nome_da_subcategoria(produto: object) -> str:
    """O nome da subcategoria do produto, ou `""` quando não há.

    Recebe `object` porque atende duas formas do mesmo dado: o `Produto` do
    SQLAlchemy, onde `subcategoria` é a **relação** e o nome mora dentro dela,
    e o `_LinhaProduto` do modal "Adicionar item", que é um instantâneo sem
    banco atrás e guarda o nome direto como `str`. O `getattr` com padrão cobre
    ainda um terceiro caso — objeto sem o atributo, como as bancadas e os
    testes de busca —, que responde vazio em vez de estourar.
    """
    subcategoria = getattr(produto, "subcategoria", None)
    if subcategoria is None:
        return ""
    if isinstance(subcategoria, str):
        return subcategoria
    return getattr(subcategoria, "nome", "") or ""


def _texto_buscavel(produto: object) -> str:
    """Nome + subcategoria, que é o que a digitação tem permissão de casar.

    Categoria e preço ficam de FORA de propósito. Quem quer filtrar por
    categoria tem as pílulas ao lado da busca, e um preço no meio do texto
    buscável faria digitar "12" trazer o cardápio inteiro pelo "R$ 12,00" de
    dez itens — busca que traz tudo é busca que não serve.
    """
    return f"{produto.nome} {nome_da_subcategoria(produto)}"


def filtrar_produtos(produtos: list[Produto], termo: str) -> list[Produto]:
    """Filtra por substring tolerante a acento/caixa, palavra por palavra.

    Cada palavra do termo digitado precisa aparecer em algum lugar do nome ou
    da subcategoria — por isso `"coca cola k"` restringe para `"Coca-Cola KS"`
    mas já não casa mais com `"Coca-Cola Lata"`, e `"artesanal"` traz os
    lanches dessa subcategoria mesmo sem a palavra estar no nome de nenhum.
    """
    tokens = [_normalizar(t) for t in termo.split() if t]
    if not tokens:
        return list(produtos)
    return [
        produto
        for produto in produtos
        if all(token in _normalizar(_texto_buscavel(produto)) for token in tokens)
    ]
