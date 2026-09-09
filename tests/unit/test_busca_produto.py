"""Filtragem da busca instantânea (typeahead) de produtos: substring
tolerante a acento/caixa, palavra por palavra (ver
`ui/widgets/busca_produto.py`)."""

from types import SimpleNamespace

from gestor_comercial.ui.widgets.busca_produto import filtrar_produtos


def _produto(nome: str, subcategoria: str | None = None):
    return SimpleNamespace(nome=nome, subcategoria=subcategoria)


def _nomes(resultado) -> list[str]:
    return [produto.nome for produto in resultado]


def test_termo_vazio_retorna_todos_os_produtos():
    produtos = [_produto("Coca-Cola Lata"), _produto("Água Mineral")]

    assert filtrar_produtos(produtos, "") == produtos


def test_filtra_por_substring_case_insensitive():
    produtos = [_produto("Coca-Cola Lata"), _produto("Água Mineral")]

    assert _nomes(filtrar_produtos(produtos, "COCA")) == ["Coca-Cola Lata"]


def test_filtra_ignorando_acentuacao():
    produtos = [_produto("Água Mineral"), _produto("Coca-Cola Lata")]

    assert _nomes(filtrar_produtos(produtos, "agua")) == ["Água Mineral"]


def test_multiplas_palavras_refinam_o_resultado():
    produtos = [
        _produto("Coca-Cola Lata"),
        _produto("Coca-Cola KS"),
        _produto("Coca-Cola 2L"),
    ]

    resultado_amplo = filtrar_produtos(produtos, "coca co")
    assert _nomes(resultado_amplo) == ["Coca-Cola Lata", "Coca-Cola KS", "Coca-Cola 2L"]

    resultado_refinado = filtrar_produtos(produtos, "coca cola k")
    assert _nomes(resultado_refinado) == ["Coca-Cola KS"]


def test_termo_sem_correspondencia_retorna_lista_vazia():
    produtos = [_produto("Coca-Cola Lata")]

    assert filtrar_produtos(produtos, "pizza") == []


# ---------------------------------------------------------------------------
# Sub-modelo (§9.8)
# ---------------------------------------------------------------------------


def test_a_busca_acha_pelo_submodelo():
    """O pedido do §9.8: digitar "artesanal" lista os lanches desse sub-modelo,
    mesmo que a palavra não apareça no nome de nenhum deles."""
    produtos = [
        _produto("X Missão Impossível", "Artesanal"),
        _produto("X Scooby", "Artesanal"),
        _produto("X Burguer", "Podrão"),
    ]

    achados = _nomes(filtrar_produtos(produtos, "artesanal"))

    assert achados == ["X Missão Impossível", "X Scooby"]


def test_o_submodelo_tambem_ignora_acento_e_caixa():
    produtos = [_produto("X Burguer", "Podrão"), _produto("X Scooby", "Artesanal")]

    assert _nomes(filtrar_produtos(produtos, "PODRAO")) == ["X Burguer"]


def test_nome_e_submodelo_valem_na_mesma_busca():
    """Cada palavra pode casar num campo diferente: "podrao burguer" acha o
    item cujo sub-modelo é Podrão E cujo nome tem Burguer."""
    produtos = [
        _produto("X Burguer", "Podrão"),
        _produto("X Scooby", "Podrão"),
        _produto("X Burguer Artesanal", "Artesanal"),
    ]

    assert _nomes(filtrar_produtos(produtos, "podrao burguer")) == ["X Burguer"]


def test_produto_sem_submodelo_continua_achavel_pelo_nome():
    """A garantia do "não quebrou nada": o cardápio inteiro de hoje está sem
    sub-modelo, e a busca dele é a de sempre."""
    produtos = [_produto("Coca-Cola Lata"), _produto("Água Mineral")]

    assert _nomes(filtrar_produtos(produtos, "agua")) == ["Água Mineral"]


def test_objeto_sem_o_atributo_submodelo_nao_quebra_a_busca():
    """`filtrar_produtos` serve o `Produto` do banco e o `_LinhaProduto` do
    modal de lançamento. Um terceiro chamador que não tenha o campo (uma
    bancada, um teste) não pode derrubar a busca do balcão."""
    produtos = [SimpleNamespace(nome="Coca-Cola Lata")]

    assert _nomes(filtrar_produtos(produtos, "coca")) == ["Coca-Cola Lata"]
