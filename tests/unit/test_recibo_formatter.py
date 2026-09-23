"""O layout do cupom do cliente em colunas (`services/recibo_formatter.py`, §9.30).

Puro como o `formatador_cupom`: sem banco, sem relógio, sem impressora. O que
estes testes trancam é o que o papel mostraria errado — linha que passa da
bobina, coluna que desalinha, valor cortado, TOTAL que não cabe na escala.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.services import recibo_formatter as recibo
from gestor_comercial.services.recibo_formatter import DadosDaLoja, ItemDoRecibo

AGORA = datetime(2026, 9, 22, 20, 15)
LARGURAS = (32, 48, 64, 80)

ITENS = [
    ItemDoRecibo(12, "X-Burger Duplo Especial com Bacon e Cheddar", Decimal("32.90"), 2, "sem cebola"),
    ItemDoRecibo(7, "Coca-Cola Lata", Decimal("7.00"), 12),
    ItemDoRecibo(113, "Batata", Decimal("1234.50"), 1),
]


def _textos(documento):
    return [bloco.texto for bloco in documento]


def _largura_no_papel(bloco, escala):
    return len(bloco.texto) * (escala if bloco.ampliado else 1)


# ----------------------------------------------------------------------
# Tabela de itens
# ----------------------------------------------------------------------


@pytest.mark.parametrize("largura", LARGURAS)
def test_nenhuma_linha_da_tabela_passa_da_bobina(largura):
    for linha in _textos(recibo.tabela_de_itens(ITENS, largura)):
        assert len(linha) <= largura, linha


@pytest.mark.parametrize("largura", [48, 64, 80])
def test_a_tabela_larga_tem_as_cinco_colunas_numa_linha(largura):
    linhas = _textos(recibo.tabela_de_itens(ITENS, largura))

    cabecalho = linhas[1]
    for rotulo in ("CÓDIGO", "DESCRIÇÃO", "PREÇO", "QTD", "TOTAL"):
        assert rotulo in cabecalho
    # O TOTAL de cada item termina exatamente na última coluna, como o rótulo.
    coca = next(linha for linha in linhas if linha.startswith("7 "))
    assert len(coca) == largura == len(cabecalho)
    assert coca.split()[-3:] == ["7,00", "12", "84,00"]


@pytest.mark.parametrize("largura", [48, 64, 80])
def test_as_colunas_numericas_ficam_alinhadas_entre_os_itens(largura):
    """O fim do PREÇO, da QTD e do TOTAL cai na mesma coluna em todo item."""
    linhas = [
        linha
        for linha in _textos(recibo.tabela_de_itens(ITENS, largura))
        if linha[:1].isdigit()
    ]
    fins = {tuple(_fins_dos_numeros(linha)) for linha in linhas}
    assert len(fins) == 1, linhas


def _fins_dos_numeros(linha):
    fins, posicao = [], len(linha)
    for palavra in reversed(linha.split()[-3:]):
        fim = linha.rindex(palavra, 0, posicao) + len(palavra)
        fins.append(fim)
        posicao = linha.rindex(palavra, 0, posicao)
    return fins


def test_valor_grande_alarga_a_coluna_em_vez_de_ser_cortado():
    linhas = _textos(recibo.tabela_de_itens(ITENS, 48))

    assert any(linha.endswith("1.234,50") and "1.234,50" in linha.split()[-3] for linha in linhas)


def test_descricao_comprida_quebra_dentro_da_coluna():
    linhas = _textos(recibo.tabela_de_itens(ITENS, 48))

    inicio = next(i for i, linha in enumerate(linhas) if linha.startswith("12 "))
    continuacao = linhas[inicio + 1]
    recuo = len(continuacao) - len(continuacao.lstrip())
    assert recuo == len("CÓDIGO ")
    assert "Bacon" in " ".join(linhas[inicio : inicio + 3])


def test_na_bobina_estreita_a_tabela_empilha_com_numeros_alinhados():
    """32 colunas com um valor de R$ 1.234,50: a descrição teria menos de 12
    letras numa linha só, então cada item vira duas linhas."""
    linhas = _textos(recibo.tabela_de_itens(ITENS, 32))

    assert linhas[1].startswith("CÓD DESCRIÇÃO")
    assert linhas[2].split() == ["PREÇO", "QTD", "TOTAL"] and len(linhas[2]) == 32
    numeros = [linha for linha in linhas if linha.split()[-1:] and linha.split()[-1][0].isdigit() and linha.startswith(" ")]
    assert ["7,00", "12", "84,00"] in [linha.split() for linha in numeros]
    assert all(len(linha) == 32 for linha in numeros)


def test_a_observacao_fica_pendurada_no_item():
    linhas = _textos(recibo.tabela_de_itens(ITENS, 48))

    assert "  Obs: sem cebola" in linhas


def test_a_tabela_fica_entre_tracejados():
    linhas = _textos(recibo.tabela_de_itens(ITENS, 48))

    assert linhas[0] == "-" * 48 and linhas[2] == "-" * 48 and linhas[-1] == "-" * 48


def test_o_codigo_e_o_rotulo_curto_quando_o_longo_aperta_a_descricao():
    """Em 40 colunas, "CÓDIGO" roubaria da descrição; "CÓD" devolve 3 letras."""
    linhas = _textos(recibo.tabela_de_itens(ITENS[1:2], 40))

    assert linhas[1].startswith("CÓDIGO ") or linhas[1].startswith("CÓD ")
    assert len(linhas[1]) == 40


# ----------------------------------------------------------------------
# Cabeçalho
# ----------------------------------------------------------------------


def test_o_cabecalho_tem_loja_contato_comanda_e_data():
    loja = DadosDaLoja("Solvix Lanches", "(11) 98765-4321", "Campinas", "sp")
    documento = recibo.cabecalho(loja, "RECIBO", 57, AGORA, 48, 2)
    textos = _textos(documento)

    assert documento[0].ampliado and documento[0].negrito and textos[0] == "SOLVIX LANCHES"
    assert "Tel: (11) 98765-4321" in textos
    assert "Campinas/SP" in textos
    assert "RECIBO" in textos
    comanda = next(texto for texto in textos if texto.startswith("COMANDA Nº 57"))
    assert comanda.endswith("22/09/2026 20:15") and len(comanda) == 48


def test_loja_sem_dados_nao_imprime_linha_vazia_nem_sem_nome():
    """Sem nome cadastrado, quem vai para o destaque é o título do cupom."""
    documento = recibo.cabecalho(DadosDaLoja(), "RECIBO", 1, AGORA, 48, 3)
    textos = _textos(documento)

    assert documento[0].ampliado and textos[0] == "RECIBO"
    assert textos.count("RECIBO") == 1
    assert not any(texto.startswith("Tel") for texto in textos)
    assert "" not in textos


@pytest.mark.parametrize("escala", [2, 3, 4])
@pytest.mark.parametrize("largura", [32, 48])
def test_o_nome_da_loja_ampliado_quebra_na_largura_da_escala(largura, escala):
    loja = DadosDaLoja("Lanchonete do Seu Raphael e Filhos")
    for bloco in recibo.cabecalho(loja, "RECIBO", 1, AGORA, largura, escala):
        assert _largura_no_papel(bloco, escala) <= largura, bloco.texto


@pytest.mark.parametrize(
    ("cidade", "uf", "esperado"),
    [("Campinas", "sp", "Campinas/SP"), ("Campinas", None, "Campinas"), (None, "mg", "MG"), ("  ", "", "")],
)
def test_cidade_e_uf(cidade, uf, esperado):
    assert DadosDaLoja(cidade=cidade, uf=uf).cidade_uf() == esperado


# ----------------------------------------------------------------------
# Total e rodapé
# ----------------------------------------------------------------------


def test_o_total_cabe_numa_linha_ampliada_quando_da():
    documento = recibo.total_em_destaque("TOTAL", Decimal("46"), 48, 2)

    assert len(documento) == 1 and documento[0].ampliado and documento[0].negrito
    assert documento[0].texto.startswith("TOTAL") and documento[0].texto.endswith("R$ 46,00")
    assert len(documento[0].texto) == 24


@pytest.mark.parametrize("escala", [2, 3, 4])
@pytest.mark.parametrize("largura", LARGURAS)
@pytest.mark.parametrize("valor", ["46", "1373.30", "12345.67"])
def test_o_total_nunca_passa_da_bobina_no_papel(largura, escala, valor):
    documento = recibo.total_em_destaque("TOTAL A PAGAR", Decimal(valor), largura, escala)

    for bloco in documento:
        assert _largura_no_papel(bloco, escala) <= largura, (bloco.texto, bloco.ampliado)
    # O valor aparece inteiro, em algum tamanho: cortado, o total mentiria.
    assert any("R$" in bloco.texto for bloco in documento)


def test_o_total_que_nao_cabe_nem_sozinho_sai_no_tamanho_normal():
    """58mm em 4x: 8 caracteres. "R$ 1.373,30" tem 11 — sai em negrito normal."""
    documento = recibo.total_em_destaque("TOTAL", Decimal("1373.30"), 32, 4)

    assert documento[0].texto == "TOTAL" and documento[0].ampliado
    assert documento[-1].texto == "R$ 1.373,30" and not documento[-1].ampliado


def test_o_rodape_tem_operador_local_permanencia_e_aviso():
    textos = _textos(recibo.rodape("Maria", "MESA 12", "1h 05min", 48, "Volte sempre!"))

    assert "OPERADOR(A): Maria" in textos
    # Local e permanência dividem a linha (§9.32): "onde" e "por quanto tempo"
    # são a mesma informação, e juntas economizam uma linha de bobina.
    local_e_tempo = next(t for t in textos if t.startswith("LOCAL: MESA 12"))
    assert local_e_tempo.endswith("Permanência: 1h 05min")
    assert len(local_e_tempo) == 48
    assert "NÃO É DOCUMENTO FISCAL" in textos
    assert textos[-1] == "Volte sempre!"


def test_local_e_permanencia_empilham_quando_nao_cabem_na_mesma_linha():
    """Bobina estreita não pode cortar o local para caber a permanência (§9.32).

    `duas_colunas` nunca corta o valor da direita — numa bobina de 20 colunas a
    linha única estouraria a largura e a IMPRESSORA cortaria, no meio do tempo.
    Empilhado, cada informação sai inteira.
    """
    textos = _textos(recibo.rodape("Maria", "MESA 12", "785h 28min", 20))

    assert "LOCAL: MESA 12" in textos
    assert "Permanência: 785h" in textos and "28min" in textos
    assert all(len(texto) <= 20 for texto in textos)


def test_sem_permanencia_a_linha_nao_sai():
    textos = _textos(recibo.rodape("Maria", "BALCÃO", None, 48))

    assert not any("Permanência" in texto for texto in textos)
    assert "LOCAL: BALCÃO" in textos


@pytest.mark.parametrize(
    ("minutos", "esperado"),
    [(0, "0min"), (45, "45min"), (60, "1h 00min"), (85, "1h 25min"), (61 * 10, "10h 10min")],
)
def test_permanencia(minutos, esperado):
    inicio = datetime(2026, 9, 22, 18, 0)
    fim = datetime.fromtimestamp(inicio.timestamp() + minutos * 60 + 59)

    assert recibo.permanencia(inicio, fim) == esperado


def test_permanencia_sem_inicio_ou_com_relogio_para_tras():
    assert recibo.permanencia(None, AGORA) is None
    assert recibo.permanencia(AGORA, datetime(2026, 9, 22, 20, 0)) is None


def test_o_total_do_item_segue_o_arredondamento_do_sistema():
    """O unitário arredonda ANTES (3,335 → 3,34), como o recibo antigo fazia:
    o total da linha é o que o cliente confere multiplicando o preço impresso."""
    item = ItemDoRecibo(1, "Suco", Decimal("3.335"), 3)

    assert item.total == Decimal("10.02")
