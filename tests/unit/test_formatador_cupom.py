"""Testes da aritmética de colunas do cupom (`services/formatador_cupom.py`).

Funções puras, então o teste é sempre o mesmo formato: entra texto e largura,
sai a linha exata que iria pro papel. Nenhum destes testes precisa de banco,
de impressora ou de fixture.
"""

from datetime import datetime
from decimal import Decimal

from gestor_comercial.services import formatador_cupom as cupom


def test_moeda_no_padrao_brasileiro():
    assert cupom.moeda(Decimal("1234.5")) == "1.234,50"
    assert cupom.moeda(Decimal("0")) == "0,00"
    assert cupom.moeda(Decimal("-5")) == "-5,00"


def test_duas_colunas_encosta_o_valor_na_direita():
    linha = cupom.duas_colunas("Dinheiro", "50,00", 32)

    assert len(linha) == 32
    assert linha.startswith("Dinheiro")
    assert linha.endswith("50,00")


def test_duas_colunas_corta_o_rotulo_e_nunca_o_valor():
    linha = cupom.duas_colunas("Cartão de crédito da maquininha", "1.234,50", 20)

    assert len(linha) == 20
    assert linha.endswith("1.234,50")


def test_linha_de_item_poe_o_preco_na_primeira_linha():
    linhas = cupom.linha_de_item(2, "X-Burger", 32, valor=Decimal("20"))

    assert linhas == ["2x X-Burger                20,00"]


def test_linha_de_item_quebra_nome_grande_sem_perder_o_preco():
    linhas = cupom.linha_de_item(
        1, "Combo Especial da Casa com Fritas Grandes", 32, valor=Decimal("39.90")
    )

    assert linhas[0].endswith("39,90")
    assert all(len(linha) <= 32 for linha in linhas)
    assert len(linhas) > 1


def test_linha_de_item_sem_preco_e_o_cupom_da_cozinha():
    assert cupom.linha_de_item(3, "Coca-Cola", 32) == ["3x Coca-Cola"]


def test_linha_secundaria_recua_e_ignora_texto_vazio():
    assert cupom.linha_secundaria("sem cebola", 32, prefixo="obs: ") == ["  obs: sem cebola"]
    assert cupom.linha_secundaria(None, 32) == []
    assert cupom.linha_secundaria("   ", 32) == []


def test_quebrar_respeita_a_largura():
    linhas = cupom.quebrar("um dois tres quatro cinco seis sete oito", 20)

    assert all(len(linha) <= 20 for linha in linhas)
    assert " ".join(linhas) == "um dois tres quatro cinco seis sete oito"


def test_separador_com_e_sem_titulo():
    assert cupom.separador(10) == "----------"

    titulado = cupom.separador(20, titulo="TOTAL")
    assert len(titulado) == 20
    assert " TOTAL " in titulado


def test_centralizar_sem_sujar_a_direita():
    linha = cupom.centralizar("RECIBO", 20)

    assert linha == "       RECIBO"
    assert linha.strip() == "RECIBO"


def test_largura_util_tem_piso_de_seguranca():
    # Cadastro torto (NULL, zero, texto) não pode derrubar a impressão.
    assert cupom.largura_util(48) == 48
    assert cupom.largura_util(None) == cupom.LARGURA_MINIMA
    assert cupom.largura_util(0) == cupom.LARGURA_MINIMA


def test_regua_tem_uma_coluna_por_caractere():
    assert cupom.regua(12) == "123456789012"


def test_datas_no_formato_brasileiro():
    momento = datetime(2026, 8, 21, 19, 42)

    assert cupom.data_hora(momento) == "21/08/2026 19:42"
    assert cupom.data(momento) == "21/08/2026"
    assert cupom.hora(momento) == "19:42"


def test_truncar_normaliza_espacos_e_corta_sem_reticencias():
    # Caractere gasto com "..." é caractere a menos do nome do produto.
    assert cupom.truncar("  X-Burger   Especial  ", 12) == "X-Burger Esp"
    assert cupom.truncar("X-Burger", 32) == "X-Burger"


def test_quebrar_texto_em_branco_nao_gera_linha():
    # Quem monta o cupom faz extend(): observação vazia não pode virar linha em branco.
    assert cupom.quebrar("", 32) == []
    assert cupom.quebrar("   ", 32) == []


def test_quebrar_parte_palavra_maior_que_a_bobina():
    linhas = cupom.quebrar("Xisburguerdacasaespecialissimo", 10)

    assert all(len(linha) <= 10 for linha in linhas)
    assert "".join(linhas) == "Xisburguerdacasaespecialissimo"


def test_quebrar_recua_todas_as_linhas():
    linhas = cupom.quebrar("um dois tres quatro cinco", 12, recuo=cupom.RECUO)

    assert len(linhas) > 1
    assert all(linha.startswith(cupom.RECUO) for linha in linhas)
    assert all(len(linha) <= 12 for linha in linhas)


def test_linha_de_valor_com_pontilhado_tem_respiro_depois_do_rotulo():
    linha = cupom.linha_de_valor("Dinheiro", Decimal("50"), 20, preenchimento=".")

    assert linha == "Dinheiro ..... 50,00"


def test_moeda_aceita_texto_e_inteiro():
    assert cupom.moeda("12") == "12,00"
    assert cupom.moeda(7) == "7,00"


def test_moeda_arredonda_meio_centavo_pra_cima_como_o_resto_do_sistema():
    assert cupom.moeda(Decimal("2.345")) == "2,35"


def test_centralizar_corta_o_que_nao_cabe():
    assert cupom.centralizar("RECIBO DO CLIENTE FINAL", 10) == "RECIBO DO"


def test_separador_com_titulo_maior_que_a_bobina_nao_estoura():
    assert len(cupom.separador(10, titulo="PAGAMENTO EM DINHEIRO")) == 10


def test_separador_aceita_outro_caractere():
    assert cupom.separador(5, caractere="=") == "====="


def test_largura_util_com_valor_ilegivel():
    assert cupom.largura_util("quarenta e oito") == cupom.LARGURA_MINIMA


def test_duas_colunas_prefere_estourar_a_largura_a_perder_o_valor():
    """O valor é o que o cliente confere; o rótulo é quem cede espaço."""
    linha = cupom.duas_colunas("TOTAL", "1.234.567,89", 10)

    assert linha.endswith("1.234.567,89")
