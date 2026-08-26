"""Filtragem da busca instantânea (typeahead) de produtos: substring
tolerante a acento/caixa, palavra por palavra (ver
`ui/widgets/busca_produto.py`)."""

from types import SimpleNamespace

from gestor_comercial.ui.widgets.busca_produto import filtrar_produtos


def _produto(nome: str):
    return SimpleNamespace(nome=nome)


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
