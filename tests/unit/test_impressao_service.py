"""Testes do roteamento e da impressão (`services/impressao_service.py`).

A impressora é substituída por uma fábrica de driver falso injetada no
construtor — a mesma costura que o contrato da Fase 4 previu. Assim a suíte
exercita roteamento, fallback, marcação de `impresso_em` e recuperação de falha
sem nenhum hardware, sem `python-escpos` e sem escrever arquivo.

`FabricaDeDriverFalso` mora no `conftest.py` porque também serve às telas e a
qualquer teste futuro que precise ver o que foi pro papel.
"""

import contextlib
from datetime import datetime
from decimal import Decimal

import pytest

from gestor_comercial.domain.comanda import Comanda
from gestor_comercial.domain.enums import (
    FormaPagamento,
    PerfilUsuario,
    StatusCaixa,
    StatusComanda,
    TipoMovimento,
)
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.domain.item_comanda import ItemComanda
from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.domain.pagamento import Pagamento
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services import formatador_cupom as cupom
from gestor_comercial.services.caixa_service import CaixaService
from gestor_comercial.services.comanda_service import ComandaService
from gestor_comercial.services.dinheiro import dinheiro
from gestor_comercial.services.exceptions import (
    NaoAutorizadoError,
    RecursoNaoEncontradoError,
)
from gestor_comercial.services.funcionario_service import FuncionarioService
from gestor_comercial.services.impressao_service import (
    GRUPO_SEM_IMPRESSORA,
    ImpressaoService,
)
from gestor_comercial.services.pagamento_service import PagamentoService
from tests.conftest import PIN_ATENDENTE, FabricaDeDriverFalso


@pytest.fixture
def impressao(uow, auth, driver):
    return ImpressaoService(uow, auth, abrir_driver=driver)


def nova_impressora(uow, nome, padrao=False, ativa=True, colunas=32):
    return uow.impressoras.salvar(
        Impressora(nome=nome, colunas=colunas, ativa=ativa, padrao=padrao)
    )


def nova_categoria_com_produto(uow, nome_categoria, nome_produto, preco, impressora=None):
    from gestor_comercial.domain.categoria import Categoria

    categoria = uow.categorias.salvar(
        Categoria(nome=nome_categoria, impressora_id=None if impressora is None else impressora.id)
    )
    return uow.produtos.salvar(
        Produto(nome=nome_produto, preco=dinheiro(preco), categoria_id=categoria.id)
    )


def nova_comanda(uow, caixa, usuario, mesa=None):
    return uow.comandas.salvar(
        Comanda(
            status=StatusComanda.ABERTA,
            aberta_em=datetime(2026, 8, 21, 19, 30),
            mesa_id=None if mesa is None else mesa.id,
            usuario_id=usuario.id,
            caixa_id=caixa.id,
        )
    )


def novo_item(uow, comanda, produto, quantidade=1, observacao=None, cancelado=False):
    return uow.itens.salvar(
        ItemComanda(
            quantidade=quantidade,
            preco_unit_congelado=produto.preco,
            observacao=observacao,
            cancelado=cancelado,
            comanda_id=comanda.id,
            produto_id=produto.id,
        )
    )


# ----------------------------------------------------------------------
# Roteamento
# ----------------------------------------------------------------------


def test_agrupa_por_impressora_da_categoria(uow, impressao, driver, gerente, caixa_aberto, mesa):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    bar = nova_impressora(uow, "Bar")
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    bebida = nova_categoria_com_produto(uow, "Bebidas", "Coca-Cola", "6.00", bar)
    comanda = nova_comanda(uow, caixa_aberto, gerente, mesa)
    novo_item(uow, comanda, lanche, quantidade=2)
    novo_item(uow, comanda, bebida)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert [r.impressora_nome for r in resultados] == ["Cozinha", "Bar"]
    assert all(r.sucesso for r in resultados)
    assert "2x X-Burger" in driver.texto_de("Cozinha")
    assert "1x Coca-Cola" in driver.texto_de("Bar")
    # Item de uma impressora não pode vazar para o cupom da outra.
    assert "Coca-Cola" not in driver.texto_de("Cozinha")


def test_categoria_sem_impressora_cai_na_padrao(uow, impressao, driver, gerente, caixa_aberto):
    balcao = nova_impressora(uow, "Balcão", padrao=True)
    doce = nova_categoria_com_produto(uow, "Sobremesas", "Pudim", "8.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, doce)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert [r.impressora_nome for r in resultados] == [balcao.nome]
    assert resultados[0].sucesso
    assert "1x Pudim" in driver.texto_de("Balcão")


def test_impressora_desativada_da_categoria_cai_na_padrao(
    uow, impressao, driver, gerente, caixa_aberto
):
    nova_impressora(uow, "Balcão", padrao=True)
    desligada = nova_impressora(uow, "Chapa", ativa=False)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Salada", "18.00", desligada)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert [r.impressora_nome for r in resultados] == ["Balcão"]
    assert driver.impressoras_usadas == ["Balcão"]


def test_sem_padrao_o_grupo_orfao_falha_e_os_outros_imprimem(
    uow, impressao, driver, gerente, caixa_aberto
):
    cozinha = nova_impressora(uow, "Cozinha")  # nenhuma padrão cadastrada
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    bebida = nova_categoria_com_produto(uow, "Bebidas", "Suco", "9.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item_lanche = novo_item(uow, comanda, lanche)
    item_bebida = novo_item(uow, comanda, bebida)

    resultados = impressao.imprimir_comanda(comanda.id)

    por_nome = {r.impressora_nome: r for r in resultados}
    assert por_nome["Cozinha"].sucesso is True
    orfao = por_nome[GRUPO_SEM_IMPRESSORA]
    assert orfao.sucesso is False
    assert "Bebidas" in orfao.erro
    assert "Cardápio" in orfao.erro
    # O pedido inteiro fica confirmado — o órfão não fica preso em
    # "Pendentes" só porque a categoria dele ainda não tem impressora.
    assert item_lanche.impresso_em is not None
    assert item_bebida.impresso_em is not None


def test_o_aviso_do_grupo_orfao_diz_qual_e_o_caso(uow, impressao, gerente, caixa_aberto):
    """Categoria sem impressora e categoria com impressora desligada são
    problemas diferentes, e o operador resolve cada um num lugar."""
    desligada = nova_impressora(uow, "Chapa", ativa=False)  # e nenhuma padrão
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Salada", "18.00", desligada)
    bebida = nova_categoria_com_produto(uow, "Bebidas", "Suco", "9.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    novo_item(uow, comanda, bebida)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert [r.impressora_nome for r in resultados] == [GRUPO_SEM_IMPRESSORA]
    erro = resultados[0].erro
    assert "'Chapa' da categoria 'Lanches' está desativada" in erro
    assert "'Bebidas' não tem impressora associada" in erro
    assert resultados[0].quantidade_itens == 2


def test_ordem_de_lancamento_e_preservada(uow, impressao, driver, gerente, caixa_aberto):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    bar = nova_impressora(uow, "Bar")
    bebida = nova_categoria_com_produto(uow, "Bebidas", "Suco", "9.00", bar)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, bebida)  # lançado primeiro
    novo_item(uow, comanda, lanche)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert [r.impressora_nome for r in resultados] == ["Bar", "Cozinha"]


def test_ordem_dos_itens_dentro_do_cupom_e_a_de_lancamento(
    uow, impressao, driver, gerente, caixa_aberto
):
    """A cozinha monta o pedido de cima pra baixo, na sequência que foi digitada."""
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    entrada = nova_categoria_com_produto(uow, "Entradas", "Fritas", "12.00", cozinha)
    principal = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    sobremesa = nova_categoria_com_produto(uow, "Doces", "Pudim", "8.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, entrada)
    novo_item(uow, comanda, principal)
    novo_item(uow, comanda, sobremesa)

    impressao.imprimir_comanda(comanda.id)
    texto = driver.texto_de("Cozinha")

    assert texto.index("1x Fritas") < texto.index("1x X-Burger") < texto.index("1x Pudim")


def test_itens_da_mesma_impressora_saem_num_cupom_so(
    uow, impressao, driver, gerente, caixa_aberto
):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    porcao = nova_categoria_com_produto(uow, "Porções", "Fritas", "12.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    novo_item(uow, comanda, porcao)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert len(resultados) == 1
    assert resultados[0].quantidade_itens == 2
    assert driver.cupons_de("Cozinha") == 1


def test_fallback_na_mesma_impressora_nao_gera_um_segundo_cupom(
    uow, impressao, driver, gerente, caixa_aberto
):
    """DIVERGÊNCIA do Java: lá o agrupamento era por categoria, e a categoria
    sem impressora virava um cupom separado que sairia no mesmo rolo de papel.
    Aqui o agrupamento é pela impressora resolvida, então dá um cupom só."""
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    sem_destino = nova_categoria_com_produto(uow, "Sobremesas", "Pudim", "8.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    novo_item(uow, comanda, sem_destino)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert [(r.impressora_nome, r.quantidade_itens) for r in resultados] == [("Cozinha", 2)]
    assert driver.cupons_de("Cozinha") == 1


def test_impressora_padrao_desativada_nao_recebe_o_fallback(
    uow, impressao, driver, gerente, caixa_aberto
):
    """A marca de padrão numa impressora desligada não pode atrair cupom."""
    nova_impressora(uow, "Balcão", padrao=True, ativa=False)
    sem_destino = nova_categoria_com_produto(uow, "Sobremesas", "Pudim", "8.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item = novo_item(uow, comanda, sem_destino)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert [r.impressora_nome for r in resultados] == [GRUPO_SEM_IMPRESSORA]
    assert resultados[0].sucesso is False
    assert driver.enviados == []
    # Pedido confirmado mesmo sem nenhuma impressora elegível — o cliente não
    # fica esperando o gerente configurar hardware pra fechar a mesa.
    assert item.impresso_em is not None


def test_item_de_outra_comanda_nao_entra_no_cupom(uow, impressao, driver, gerente, caixa_aberto):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    minha = nova_comanda(uow, caixa_aberto, gerente)
    outra = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, minha, lanche, quantidade=1)
    item_alheio = novo_item(uow, outra, lanche, quantidade=7)

    resultados = impressao.imprimir_comanda(minha.id)

    assert resultados[0].quantidade_itens == 1
    assert "7x" not in driver.texto_de("Cozinha")
    assert item_alheio.impresso_em is None


def test_mesa_sai_em_dobro_para_a_cozinha_ler_de_longe(
    uow, impressao, driver, gerente, caixa_aberto, mesa
):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente, mesa)
    novo_item(uow, comanda, lanche)

    impressao.imprimir_comanda(comanda.id)

    em_dobro = [bloco.texto for bloco in driver.blocos_de("Cozinha") if bloco.dobro]
    assert em_dobro == [f"MESA {mesa.numero}"]


# ----------------------------------------------------------------------
# Via de acréscimo e 2ª via
# ----------------------------------------------------------------------


def test_so_imprime_o_que_ainda_nao_foi_impresso(uow, impressao, driver, gerente, caixa_aberto):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    assert len(impressao.imprimir_comanda(comanda.id)) == 1
    # Segundo clique sem item novo: lista vazia, e não erro.
    assert impressao.imprimir_comanda(comanda.id) == []

    novo_item(uow, comanda, lanche, quantidade=3)
    resultados = impressao.imprimir_comanda(comanda.id)

    assert [r.quantidade_itens for r in resultados] == [1]
    assert driver.texto_de("Cozinha").count("3x X-Burger") == 1


def test_item_cancelado_nao_vai_para_a_producao(uow, impressao, driver, gerente, caixa_aberto):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    novo_item(uow, comanda, lanche, quantidade=9, cancelado=True)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert resultados[0].quantidade_itens == 1
    assert "9x" not in driver.texto_de("Cozinha")


def test_comanda_sem_nenhum_item_devolve_lista_vazia(uow, impressao, driver, gerente, caixa_aberto):
    nova_impressora(uow, "Cozinha", padrao=True)
    comanda = nova_comanda(uow, caixa_aberto, gerente)

    assert impressao.imprimir_comanda(comanda.id) == []
    assert driver.enviados == []


def test_quantidade_itens_conta_linhas_e_nao_unidades(uow, impressao, gerente, caixa_aberto):
    """É o número que a tela mostra: "Cozinha: 2 itens enviados"."""
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche, quantidade=3)
    novo_item(uow, comanda, lanche, quantidade=5)

    assert impressao.imprimir_comanda(comanda.id)[0].quantidade_itens == 2


def test_impresso_em_grava_a_mesma_hora_que_saiu_no_cupom(
    uow, impressao, driver, gerente, caixa_aberto
):
    """Um `datetime.now()` só por impressão: o papel e o banco contam a mesma hora."""
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item = novo_item(uow, comanda, lanche)

    impressao.imprimir_comanda(comanda.id)

    assert isinstance(item.impresso_em, datetime)
    assert cupom.hora(item.impresso_em) in driver.texto_de("Cozinha")


def test_via_de_acrescimo_nao_se_anuncia_como_segunda_via(
    uow, impressao, driver, gerente, caixa_aberto
):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    impressao.imprimir_comanda(comanda.id)

    assert "2ª VIA" not in driver.texto_de("Cozinha")


def test_listar_nao_impressos_ignora_cancelado_e_ja_impresso(uow, gerente, caixa_aberto):
    """Contrato do `ItemComandaRepository`, exercitado sem passar pelo service."""
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo = novo_item(uow, comanda, lanche)
    ja_impresso = novo_item(uow, comanda, lanche)
    ja_impresso.impresso_em = datetime(2026, 8, 21, 19, 0)
    uow.itens.salvar(ja_impresso)
    novo_item(uow, comanda, lanche, cancelado=True)

    assert [i.id for i in uow.itens.listar_nao_impressos_por_comanda(comanda.id)] == [novo.id]


def test_a_marcacao_dos_grupos_e_um_commit_so(uow, impressao, gerente, caixa_aberto, monkeypatch):
    """Dois cupons impressos, uma gravação só — não um commit por grupo."""
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    bar = nova_impressora(uow, "Bar")
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    bebida = nova_categoria_com_produto(uow, "Bebidas", "Suco", "9.00", bar)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    novo_item(uow, comanda, bebida)
    commits = []
    monkeypatch.setattr(uow, "commit", lambda: commits.append(1))

    impressao.imprimir_comanda(comanda.id)

    assert len(commits) == 1


def test_impressao_que_falha_inteira_ainda_assim_confirma_o_pedido(
    uow, auth, driver_que_falha, gerente, caixa_aberto, monkeypatch
):
    """Nenhum cupom saiu no papel, mas o pedido não pode ficar refém disso —
    persistência é a regra principal, impressão é só o aviso secundário."""
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item = novo_item(uow, comanda, lanche)
    commits = []
    monkeypatch.setattr(uow, "commit", lambda: commits.append(1))

    resultados = impressao.imprimir_comanda(comanda.id)

    assert resultados[0].sucesso is False
    # Dois commits desde a Fase 3, e o segundo é novo de propósito: o primeiro
    # guarda o cupom na fila de contingência, o segundo confirma o pedido. São
    # fatos independentes — o cupom que não saiu tem que sobreviver mesmo que a
    # operação que o gerou seja desfeita depois. A garantia original continua
    # valendo: é UM commit do pedido, e não um por grupo de impressão (o teste
    # acima, com impressão bem-sucedida, tranca o caso sem fila).
    assert len(commits) == 2
    assert item.impresso_em is not None


def test_reimprimir_leva_o_que_ja_saiu_e_o_que_ainda_nao(
    uow, impressao, driver, gerente, caixa_aberto
):
    """A 2ª via é a comanda inteira: é o cupom que rasgou ou sumiu na cozinha."""
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    refri = nova_categoria_com_produto(uow, "Bebidas", "Coca-Cola", "6.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    ja_impresso = novo_item(uow, comanda, lanche)
    impressao.imprimir_comanda(comanda.id)
    ainda_nao = novo_item(uow, comanda, refri, quantidade=2)

    resultados = impressao.reimprimir_comanda(comanda.id)
    segunda_via = driver.texto_de("Cozinha").split("2ª VIA")[-1]

    assert resultados[0].quantidade_itens == 2
    assert "1x X-Burger" in segunda_via and "2x Coca-Cola" in segunda_via
    # A 2ª via não conta como envio: o item novo continua esperando a via de acréscimo.
    assert ja_impresso.impresso_em is not None
    assert ainda_nao.impresso_em is None


def test_reimprimir_ignora_item_cancelado(uow, impressao, driver, gerente, caixa_aberto):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    novo_item(uow, comanda, lanche, quantidade=9, cancelado=True)

    resultados = impressao.reimprimir_comanda(comanda.id)

    assert resultados[0].quantidade_itens == 1
    assert "9x" not in driver.texto_de("Cozinha")


def test_reimprimir_comanda_sem_item_devolve_lista_vazia(
    uow, impressao, driver, gerente, caixa_aberto
):
    nova_impressora(uow, "Cozinha", padrao=True)
    comanda = nova_comanda(uow, caixa_aberto, gerente)

    assert impressao.reimprimir_comanda(comanda.id) == []
    assert driver.enviados == []


def test_reimprimir_comanda_inexistente(impressao, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        impressao.reimprimir_comanda(9999)


def test_reimprimir_repete_tudo_sem_mexer_em_impresso_em(
    uow, impressao, driver, gerente, caixa_aberto
):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item = novo_item(uow, comanda, lanche)
    impressao.imprimir_comanda(comanda.id)
    marcado_em = item.impresso_em

    resultados = impressao.reimprimir_comanda(comanda.id)

    assert resultados[0].sucesso
    assert resultados[0].quantidade_itens == 1
    assert item.impresso_em == marcado_em
    assert "2ª VIA" in driver.texto_de("Cozinha")


def test_cupom_de_producao_mostra_mesa_comanda_atendente_e_observacao(
    uow, impressao, driver, gerente, caixa_aberto, mesa
):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    lanche.descricao = "Pão, hambúrguer 180g e queijo"
    uow.produtos.salvar(lanche)
    comanda = nova_comanda(uow, caixa_aberto, gerente, mesa)
    novo_item(uow, comanda, lanche, quantidade=2, observacao="sem cebola")

    impressao.imprimir_comanda(comanda.id)
    texto = driver.texto_de("Cozinha")

    assert "COZINHA" in texto
    assert f"MESA {mesa.numero}" in texto
    assert f"Comanda {comanda.id}" in texto
    assert f"Atendente: {gerente.nome}" in texto
    assert "[!] OBS: sem cebola" in texto
    assert "Pão, hambúrguer 180g e queijo" in texto


def test_comanda_de_balcao_sai_como_balcao(uow, impressao, driver, gerente, caixa_aberto):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    impressao.imprimir_comanda(comanda.id)

    assert "BALCÃO" in driver.texto_de("Cozinha")


# ----------------------------------------------------------------------
# Falha de impressora não derruba a venda (RNF inegociável)
# ----------------------------------------------------------------------


def test_falha_vira_resultado_e_nao_excecao(uow, auth, gerente, caixa_aberto):
    driver = FabricaDeDriverFalso(falhar_em={"Cozinha"})
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item = novo_item(uow, comanda, lanche)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert resultados[0].sucesso is False
    assert "cabo" in resultados[0].erro
    # Marcou mesmo assim: falha de impressora não pode travar o pedido em
    # "Pendentes" — quem quer repapelar usa "2ª via" (reimprimir_comanda).
    assert item.impresso_em is not None


def test_erro_inesperado_do_driver_tambem_nao_derruba_a_venda(uow, auth, gerente, caixa_aberto):
    """Se um dia escapar de `hardware/` algo que não é ErroDeImpressao."""

    @contextlib.contextmanager
    def driver_quebrado(impressora):
        raise OSError("porta USB sumiu no meio do expediente")
        yield  # pragma: no cover - inalcançável, só faz do bloco um gerador

    impressao = ImpressaoService(uow, auth, abrir_driver=driver_quebrado)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item = novo_item(uow, comanda, lanche)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert resultados[0].sucesso is False
    assert "inesperado" in resultados[0].erro
    # Erro de hardware não é motivo pra deixar a venda em rascunho.
    assert item.impresso_em is not None


def test_grupo_que_falha_nao_impede_o_grupo_que_funciona(uow, auth, gerente, caixa_aberto):
    driver = FabricaDeDriverFalso(falhar_em={"Bar"})
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    bar = nova_impressora(uow, "Bar")
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    bebida = nova_categoria_com_produto(uow, "Bebidas", "Suco", "9.00", bar)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item_lanche = novo_item(uow, comanda, lanche)
    item_bebida = novo_item(uow, comanda, bebida)

    resultados = impressao.imprimir_comanda(comanda.id)

    por_nome = {r.impressora_nome: r.sucesso for r in resultados}
    assert por_nome == {"Cozinha": True, "Bar": False}
    # Os dois confirmam — o grupo que falhou só carrega o aviso no resultado.
    assert item_lanche.impresso_em is not None
    assert item_bebida.impresso_em is not None


def test_falha_no_recibo_nao_aborta_o_pagamento(uow, auth, driver_que_falha, gerente, caixa_aberto):
    """O cliente já pagou: o cupom que não sai vira aviso, nunca exceção."""
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    resultado = impressao.imprimir_recibo(comanda.id)

    assert resultado.sucesso is False
    assert resultado.impressora_nome == "Balcão"
    assert "cabo" in resultado.erro


def test_falha_no_fechamento_nao_aborta_o_fechamento_do_caixa(
    uow, auth, driver_que_falha, gerente, caixa_aberto
):
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    nova_impressora(uow, "Balcão", padrao=True)

    resultado = impressao.imprimir_fechamento_caixa(caixa_aberto.id)

    assert resultado.sucesso is False
    assert resultado.erro


def test_falha_no_teste_de_impressora_vira_resultado(uow, auth, driver_que_falha, gerente):
    """É justamente o caso que a tela de Impressoras quer diagnosticar."""
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)

    resultado = impressao.imprimir_teste(cozinha.id)

    assert resultado.sucesso is False
    assert "Cozinha" in resultado.erro


# ----------------------------------------------------------------------
# Recibo do cliente
# ----------------------------------------------------------------------


def test_recibo_mostra_itens_total_forma_e_troco(uow, impressao, driver, gerente, caixa_aberto):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", None)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche, quantidade=2)
    uow.pagamentos.salvar(
        Pagamento(
            forma=FormaPagamento.DINHEIRO,
            valor=dinheiro("40.00"),
            troco=dinheiro("10.00"),
            registrado_em=datetime(2026, 8, 21, 20, 0),
            comanda_id=comanda.id,
        )
    )

    resultado = impressao.imprimir_recibo(comanda.id)
    texto = driver.texto_de("Balcão")

    assert resultado.sucesso
    # `quantidade_itens` conta linhas da comanda, não unidades vendidas: é o
    # número que a tela mostra como "1 item enviado".
    assert resultado.quantidade_itens == 1
    assert "2x X-Burger" in texto
    assert "40,00" in texto
    assert "Dinheiro" in texto
    assert "Troco" in texto
    assert "Não é documento fiscal" in texto


def test_recibo_soma_pagamentos_da_mesma_forma(uow, impressao, driver, gerente, caixa_aberto):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", None)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche, quantidade=2)
    for valor in ("15.00", "10.00"):
        uow.pagamentos.salvar(
            Pagamento(
                forma=FormaPagamento.PIX,
                valor=dinheiro(valor),
                registrado_em=datetime(2026, 8, 21, 20, 0),
                comanda_id=comanda.id,
            )
        )

    impressao.imprimir_recibo(comanda.id)
    texto = driver.texto_de("Balcão")

    assert "PIX" in texto
    assert "25,00" in texto
    # Conta de 40 com 25 pagos: o cupom não pode parecer quitado.
    assert "A RECEBER" in texto


def test_recibo_ignora_item_cancelado(uow, impressao, driver, gerente, caixa_aberto):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    novo_item(uow, comanda, lanche, quantidade=9, cancelado=True)

    resultado = impressao.imprimir_recibo(comanda.id)
    texto = driver.texto_de("Balcão")

    assert resultado.quantidade_itens == 1
    assert "9x" not in texto
    # Item cancelado também não pode aparecer no total (§3.6).
    assert "20,00" in texto and "180,00" not in texto


def test_recibo_quitado_nao_fala_em_a_receber(uow, impressao, driver, gerente, caixa_aberto):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche, quantidade=2)
    uow.pagamentos.salvar(
        Pagamento(
            forma=FormaPagamento.CREDITO,
            valor=dinheiro("40.00"),
            registrado_em=datetime(2026, 8, 21, 20, 0),
            comanda_id=comanda.id,
        )
    )

    impressao.imprimir_recibo(comanda.id)
    texto = driver.texto_de("Balcão")

    assert "Cartão de crédito" in texto
    assert "A RECEBER" not in texto
    # Sem troco no cartão, a linha nem aparece.
    assert "Troco" not in texto


def test_recibo_de_comanda_inexistente(impressao, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        impressao.imprimir_recibo(9999)


def test_recibo_sem_impressora_padrao(uow, impressao, gerente, caixa_aberto):
    nova_impressora(uow, "Cozinha")  # existe, mas não é padrão
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", None)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    resultado = impressao.imprimir_recibo(comanda.id)

    assert resultado.sucesso is False
    assert resultado.impressora_nome == GRUPO_SEM_IMPRESSORA
    assert "padrão" in resultado.erro


# ----------------------------------------------------------------------
# Fechamento de caixa
# ----------------------------------------------------------------------


def test_fechamento_usa_os_numeros_do_caixa_service(
    uow, impressao, driver, gerente, caixa_aberto
):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", None)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    uow.pagamentos.salvar(
        Pagamento(
            forma=FormaPagamento.DINHEIRO,
            valor=dinheiro("20.00"),
            registrado_em=datetime(2026, 8, 21, 20, 0),
            comanda_id=comanda.id,
        )
    )
    uow.pagamentos.salvar(
        Pagamento(
            forma=FormaPagamento.PIX,
            valor=dinheiro("30.00"),
            registrado_em=datetime(2026, 8, 21, 20, 5),
            comanda_id=comanda.id,
        )
    )
    uow.movimentos.salvar(
        MovimentoCaixa(
            tipo=TipoMovimento.SANGRIA,
            valor=dinheiro("50.00"),
            registrado_em=datetime(2026, 8, 21, 21, 0),
            caixa_id=caixa_aberto.id,
            usuario_id=gerente.id,
        )
    )

    resultado = impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    texto = driver.texto_de("Balcão")

    assert resultado.sucesso
    assert "FECHAMENTO DE CAIXA" in texto
    assert "Valor de abertura" in texto and "100,00" in texto
    assert "Sangrias" in texto and "50,00" in texto
    assert "PIX" in texto and "30,00" in texto
    # abertura 100 + dinheiro 20 - sangria 50 = 70,00 (conta do CaixaService)
    assert "70,00" in texto


def test_fechamento_de_caixa_inexistente(uow, impressao, gerente):
    nova_impressora(uow, "Balcão", padrao=True)

    with pytest.raises(RecursoNaoEncontradoError):
        impressao.imprimir_fechamento_caixa(9999)


def test_fechamento_sem_impressora_padrao(uow, impressao, gerente, caixa_aberto):
    nova_impressora(uow, "Cozinha")  # existe, mas ninguém é padrão

    resultado = impressao.imprimir_fechamento_caixa(caixa_aberto.id)

    assert resultado.sucesso is False
    assert resultado.impressora_nome == GRUPO_SEM_IMPRESSORA
    assert "padrão" in resultado.erro


def test_fechamento_de_caixa_aberto_deixa_linha_para_anotar(
    uow, impressao, driver, gerente, caixa_aberto
):
    """Conferência de meio de turno: o gerente conta a gaveta e anota na mão."""
    nova_impressora(uow, "Balcão", padrao=True)

    impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    texto = driver.texto_de("Balcão")

    assert "Valor contado" in texto
    assert "_____" in texto
    assert "ABERTO" in texto
    assert "em aberto" in texto  # ainda não tem hora de fechamento
    assert "Diferença" not in texto


def test_fechamento_de_caixa_fechado_mostra_contado_e_diferenca(
    uow, impressao, driver, gerente, caixa_aberto
):
    uow.movimentos.salvar(
        MovimentoCaixa(
            tipo=TipoMovimento.SANGRIA,
            valor=dinheiro("50.00"),
            registrado_em=datetime(2026, 8, 21, 21, 0),
            caixa_id=caixa_aberto.id,
            usuario_id=gerente.id,
        )
    )
    caixa_aberto.status = StatusCaixa.FECHADO
    caixa_aberto.fechado_em = datetime(2026, 8, 21, 23, 0)
    caixa_aberto.valor_contado_dinheiro = dinheiro("90.00")
    caixa_aberto.valor_contado_maquininha = dinheiro("0.00")
    uow.caixas.salvar(caixa_aberto)
    nova_impressora(uow, "Balcão", padrao=True)

    impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    texto = driver.texto_de("Balcão")

    assert "FECHADO" in texto
    assert "21/08/2026 23:00" in texto
    # abertura 100 - sangria 50 = 50 esperado; contado 90 => sobra de 40.
    assert "50,00" in texto and "90,00" in texto
    assert "Diferença" in texto and "40,00" in texto


def test_fechamento_separa_as_bandeiras_da_maquininha(
    uow, impressao, driver, gerente, caixa_aberto
):
    """O gerente confere linha a linha contra o extrato da máquina."""
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche, quantidade=3)
    for forma, valor in (
        (FormaPagamento.CREDITO, "10.00"),
        (FormaPagamento.DEBITO, "20.00"),
        (FormaPagamento.PIX, "30.00"),
    ):
        uow.pagamentos.salvar(
            Pagamento(
                forma=forma,
                valor=dinheiro(valor),
                registrado_em=datetime(2026, 8, 21, 20, 0),
                comanda_id=comanda.id,
            )
        )

    impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    texto = driver.texto_de("Balcão")

    assert "Cartão de crédito" in texto and "10,00" in texto
    assert "Cartão de débito" in texto and "20,00" in texto
    assert "PIX" in texto and "30,00" in texto
    assert "Maquininha" in texto and "60,00" in texto
    # Cartão não entra na gaveta: o saldo esperado continua sendo só a abertura.
    assert "SALDO ESPERADO" in texto and "100,00" in texto


# ----------------------------------------------------------------------
# Auditoria de itens cancelados no cupom de fechamento
# ----------------------------------------------------------------------


def item_cancelado(uow, comanda, produto, gerente, *, quantidade=1, cancelado_em, motivo="Erro de lançamento"):
    return uow.itens.salvar(
        ItemComanda(
            quantidade=quantidade,
            preco_unit_congelado=produto.preco,
            cancelado=True,
            cancelado_em=cancelado_em,
            motivo_cancelamento=motivo,
            cancelado_por_id=gerente.id,
            comanda_id=comanda.id,
            produto_id=produto.id,
        )
    )


def test_fechamento_sem_venda_mostra_indicacao(uow, impressao, driver, gerente, caixa_aberto):
    nova_impressora(uow, "Balcão", padrao=True)

    impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    texto = driver.texto_de("Balcão")

    assert "ITENS VENDIDOS NO TURNO" in texto
    assert "Nenhum item vendido" in texto


def test_fechamento_mostra_quantidade_unitario_e_subtotal_por_produto(
    uow, impressao, driver, gerente, caixa_aberto, mesa
):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger Especial", "28.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente, mesa)
    novo_item(uow, comanda, lanche, quantidade=8)

    impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    texto = driver.texto_de("Balcão")

    assert "ITENS VENDIDOS NO TURNO" in texto
    assert "8x X-Burger Especial" in texto
    assert "28,00" in texto
    assert "224,00" in texto


def test_fechamento_sem_cancelamento_mostra_indicacao(uow, impressao, driver, gerente, caixa_aberto):
    nova_impressora(uow, "Balcão", padrao=True)

    impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    texto = driver.texto_de("Balcão")

    assert "ITENS CANCELADOS NO TURNO" in texto
    assert "Nenhum item cancelado" in texto


def test_fechamento_mostra_auditoria_de_cancelamentos(
    uow, impressao, driver, gerente, caixa_aberto, mesa
):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger Especial", "28.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente, mesa)
    item_cancelado(
        uow, comanda, lanche, gerente,
        quantidade=2,
        cancelado_em=datetime(2026, 8, 21, 19, 42),
        motivo="Desistência do cliente",
    )

    impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    texto = driver.texto_de("Balcão")

    assert "ITENS CANCELADOS NO TURNO" in texto
    assert "Qtd cancelada" in texto and "2 un" in texto
    assert "Valor cancelado" in texto and "56,00" in texto
    assert "X-Burger Especial" in texto
    assert "19:42" in texto
    assert "MESA 01" in texto.upper()
    assert "Gerente" in texto
    assert "Desistência do cliente" in texto


# ----------------------------------------------------------------------
# Teste de impressora e exceções que sobem
# ----------------------------------------------------------------------


def test_imprimir_teste_mostra_conexao_e_regua(uow, impressao, driver, gerente):
    impressora = nova_impressora(uow, "Cozinha", padrao=True, colunas=32)

    resultado = impressao.imprimir_teste(impressora.id)
    texto = driver.texto_de("Cozinha")

    assert resultado.sucesso
    assert resultado.quantidade_itens == 0
    assert "TESTE DE IMPRESSÃO" in texto
    assert "ARQUIVO" in texto  # tipo de conexão padrão do cadastro
    assert "32 colunas" in texto


def test_imprimir_teste_funciona_em_impressora_desativada(uow, impressao, driver, gerente):
    """O teste existe pra conferir o cabo ANTES de reativar a impressora."""
    desligada = nova_impressora(uow, "Chapa", ativa=False)

    resultado = impressao.imprimir_teste(desligada.id)

    assert resultado.sucesso
    assert "TESTE DE IMPRESSÃO" in driver.texto_de("Chapa")


def test_imprimir_teste_de_impressora_inexistente(impressao, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        impressao.imprimir_teste(9999)


def test_comanda_inexistente(impressao, gerente):
    with pytest.raises(RecursoNaoEncontradoError):
        impressao.imprimir_comanda(9999)


def test_sem_ninguem_logado(uow, auth, driver, gerente, caixa_aberto):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)
    auth.logout()

    with pytest.raises(NaoAutorizadoError):
        impressao.imprimir_comanda(comanda.id)
    with pytest.raises(NaoAutorizadoError):
        impressao.imprimir_recibo(comanda.id)
    with pytest.raises(NaoAutorizadoError):
        impressao.imprimir_fechamento_caixa(caixa_aberto.id)
    with pytest.raises(NaoAutorizadoError):
        impressao.imprimir_teste(cozinha.id)


def blocos_que_estouraram(driver, colunas):
    """Blocos maiores que a bobina — em dobro cada caractere ocupa 2 colunas."""
    return [
        bloco.texto
        for _, documento in driver.enviados
        for bloco in documento
        if len(bloco.texto) > (colunas // 2 if bloco.dobro else colunas)
    ]


def test_a_largura_da_bobina_e_respeitada(uow, impressao, driver, gerente, caixa_aberto, mesa):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True, colunas=32)
    lanche = nova_categoria_com_produto(
        uow, "Lanches", "Combo Especial da Casa com Fritas Grandes e Refrigerante", "39.90", cozinha
    )
    comanda = nova_comanda(uow, caixa_aberto, gerente, mesa)
    novo_item(uow, comanda, lanche, observacao="sem cebola, sem tomate, capricha no bacon")

    impressao.imprimir_comanda(comanda.id)

    for _, documento in driver.enviados:
        for bloco in documento:
            # Bloco em dobro ocupa 2 colunas por caractere.
            limite = 16 if bloco.dobro else 32
            assert len(bloco.texto) <= limite, bloco.texto


def test_nome_comprido_de_impressora_nao_estoura_a_bobina(
    uow, impressao, driver, gerente, caixa_aberto, mesa
):
    """`impressoras.nome` aceita 80 caracteres e a bobina pode ter 20. O nome é
    a primeira linha do cupom — a que diz para qual praça o pedido vai — e sem
    quebrar sai cortado pela impressora, com o cabeçalho mentindo."""
    cozinha = nova_impressora(
        uow, "Impressora da Cozinha Quente do Food Truck", padrao=True, colunas=32
    )
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente, mesa)
    novo_item(uow, comanda, lanche)

    impressao.imprimir_comanda(comanda.id)
    impressao.imprimir_teste(cozinha.id)

    assert blocos_que_estouraram(driver, 32) == []


def test_a_largura_da_bobina_e_respeitada_no_recibo(
    uow, impressao, driver, gerente, caixa_aberto, mesa
):
    """Quem quebra linha é o `formatador_cupom`; o driver não deveria precisar."""
    nova_impressora(uow, "Balcão", padrao=True, colunas=32)
    lanche = nova_categoria_com_produto(
        uow, "Lanches", "Combo Especial da Casa com Fritas Grandes e Refrigerante", "39.90"
    )
    comanda = nova_comanda(uow, caixa_aberto, gerente, mesa)
    novo_item(uow, comanda, lanche, quantidade=12, observacao="sem cebola, capricha no bacon")
    uow.pagamentos.salvar(
        Pagamento(
            forma=FormaPagamento.DINHEIRO,
            valor=dinheiro("478.80"),
            troco=dinheiro("21.20"),
            registrado_em=datetime(2026, 8, 21, 20, 0),
            comanda_id=comanda.id,
        )
    )

    impressao.imprimir_recibo(comanda.id)

    assert blocos_que_estouraram(driver, 32) == []


def test_a_largura_da_bobina_e_respeitada_no_fechamento(
    uow, impressao, driver, gerente, caixa_aberto
):
    nova_impressora(uow, "Balcão", padrao=True, colunas=32)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    uow.pagamentos.salvar(
        Pagamento(
            forma=FormaPagamento.CREDITO,
            valor=dinheiro("12345.67"),
            registrado_em=datetime(2026, 8, 21, 20, 0),
            comanda_id=comanda.id,
        )
    )
    caixa_aberto.status = StatusCaixa.FECHADO
    caixa_aberto.fechado_em = datetime(2026, 8, 21, 23, 0)
    caixa_aberto.valor_contado_dinheiro = dinheiro("100.00")
    caixa_aberto.valor_contado_maquininha = dinheiro("0.00")
    caixa_aberto.observacao_fechamento = (
        "faltou trocado no fim da noite, o Vitor completou do bolso e anotou no caderno"
    )
    uow.caixas.salvar(caixa_aberto)

    impressao.imprimir_fechamento_caixa(caixa_aberto.id)

    assert blocos_que_estouraram(driver, 32) == []


# ----------------------------------------------------------------------
# Fluxo real: os cupons montados pelos services de verdade, sem linha na mão
# ----------------------------------------------------------------------


def test_da_comanda_ao_recibo_pelo_caminho_de_verdade(
    uow, auth, driver, gerente, caixa_aberto, mesa
):
    nova_impressora(uow, "Balcão", padrao=True)
    cozinha = nova_impressora(uow, "Cozinha")
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comandas = ComandaService(uow, auth)
    funcionarios = FuncionarioService(uow, auth)
    pagamentos = PagamentoService(uow, auth, comandas, funcionarios)
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)

    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, lanche.id, 2, "sem cebola")
    envios = impressao.imprimir_comanda(comanda.id)
    comandas.fechar_para_conferencia(comanda.id)
    resumo = pagamentos.registrar(comanda.id, FormaPagamento.DINHEIRO, dinheiro("50.00"))
    recibo = impressao.imprimir_recibo(comanda.id)

    assert [(r.impressora_nome, r.sucesso) for r in envios] == [("Cozinha", True)]
    assert "2x X-Burger" in driver.texto_de("Cozinha")
    assert "[!] OBS: sem cebola" in driver.texto_de("Cozinha")

    assert resumo.troco == dinheiro("10.00")
    assert recibo.sucesso
    cupom_do_cliente = driver.texto_de("Balcão")
    assert "TOTAL" in cupom_do_cliente and "40,00" in cupom_do_cliente
    assert "Dinheiro" in cupom_do_cliente
    assert "Troco" in cupom_do_cliente and "10,00" in cupom_do_cliente
    # Conta paga e nada de novo lançado: não há mais via de acréscimo.
    assert impressao.imprimir_comanda(comanda.id) == []


def test_pre_conta_impressa_pelo_caminho_de_verdade(
    uow, auth, driver, gerente, caixa_aberto, mesa
):
    """§ Fechamento de Comanda: pré-conta não lista pagamento, mostra total a pagar."""
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comandas = ComandaService(uow, auth)
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)

    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, lanche.id, 2)
    comandas.fechar_para_conferencia(comanda.id, taxa_servico_percentual=Decimal("10"))

    resultado = impressao.imprimir_pre_conta(comanda.id)

    assert resultado.sucesso
    cupom = driver.texto_de("Balcão")
    assert "CONFERÊNCIA" in cupom
    assert "2x X-Burger" in cupom
    assert "TOTAL A PAGAR" in cupom and "44,00" in cupom
    assert "Taxa de serviço" in cupom
    assert "documento fiscal" in cupom.replace("\n", " ")
    assert "Dinheiro" not in cupom


def test_o_fechamento_impresso_bate_com_o_que_o_caixa_service_calcula(
    uow, auth, driver, gerente, caixa_aberto, mesa
):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comandas = ComandaService(uow, auth)
    funcionarios = FuncionarioService(uow, auth)
    pagamentos = PagamentoService(uow, auth, comandas, funcionarios)
    caixas = CaixaService(uow, auth)
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)

    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.lancar_item(comanda.id, lanche.id, 2)
    comandas.fechar_para_conferencia(comanda.id)
    pagamentos.registrar(comanda.id, FormaPagamento.DINHEIRO, dinheiro("40.00"))
    caixas.registrar_movimento(TipoMovimento.SANGRIA, dinheiro("50.00"))
    fechado = caixas.fechar(caixa_aberto.id, dinheiro("85.00"), dinheiro("0.00"))

    impressao.imprimir_fechamento_caixa(fechado.id)
    resumo = caixas.resumo(fechado.id)
    texto = driver.texto_de("Balcão")

    # abertura 100 + venda em dinheiro 40 - sangria 50 = 90 esperado.
    assert resumo.saldo_esperado == dinheiro("90.00")
    assert resumo.diferenca_dinheiro == dinheiro("-5.00")
    assert "90,00" in texto
    assert "85,00" in texto
    # Falta de dinheiro sai com sinal, senão o cupom parece bater.
    assert "-5,00" in texto


def test_nome_comprido_de_funcionario_nao_estoura_a_bobina(
    uow, auth, driver, gerente, caixa_aberto, mesa
):
    """Nome de gente é comprido, e `funcionarios.nome` aceita até 120 caracteres.
    As linhas "Atendente:" e "Conferido por:" precisam passar pelo formatador
    igual ao nome do produto, senão saem quebradas torto no papel."""
    atendente = auth.criar_usuario(
        "Ana Carolina Rodrigues do Nascimento", PerfilUsuario.OPERADOR_CAIXA
    )
    cozinha = nova_impressora(uow, "Cozinha", padrao=True, colunas=32)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, atendente, mesa)
    novo_item(uow, comanda, lanche)
    impressao = ImpressaoService(uow, auth, abrir_driver=driver)
    auth.login_como(atendente.id, PIN_ATENDENTE)

    impressao.imprimir_comanda(comanda.id)
    impressao.imprimir_recibo(comanda.id)
    impressao.imprimir_fechamento_caixa(caixa_aberto.id)

    assert blocos_que_estouraram(driver, 32) == []


def test_o_recibo_cabe_na_menor_bobina_aceita_no_cadastro(
    uow, impressao, driver, gerente, caixa_aberto
):
    """20 colunas é largura válida no cadastro (COLUNAS_MINIMAS), então o
    recibo tem que caber nela — inclusive as duas linhas de rodapé, que o
    próprio código promete não deixar quebrar no meio."""
    nova_impressora(uow, "Balcão", padrao=True, colunas=20)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00")
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    impressao.imprimir_recibo(comanda.id)

    assert blocos_que_estouraram(driver, 20) == []


def test_decimal_do_recibo_nunca_vira_float(uow, impressao, driver, gerente, caixa_aberto):
    nova_impressora(uow, "Balcão", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "19.99", None)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche, quantidade=3)

    impressao.imprimir_recibo(comanda.id)

    # 3 x 19,99 = 59,97 — sem centavo perdido em ponto flutuante.
    assert "59,97" in driver.texto_de("Balcão")
    assert dinheiro(Decimal("19.99")) * 3 == Decimal("59.97")
