"""A fila de contingência da impressora (`Mitigação de Falhas.md`, Fase 3).

O RNF de §2 — impressora quebrada não derruba a venda — já era cumprido antes
desta fase: a falha virava aviso âmbar e o cliente ia embora pago. O que faltava
era a outra metade, e é o que estes testes trancam: **o cupom não se perde**.

Cobrem também o que a Fase 3 mexeu na arquitetura, que é o mais delicado do
projeto inteiro: a impressão saiu da thread da UI sem levar a `Session` junto.
"""

from __future__ import annotations

import contextlib
import threading
import time

import pytest

from gestor_comercial.domain.fila_impressao import ItemFilaImpressao
from gestor_comercial.hardware.impressora_escpos import (
    BlocoTexto,
    ErroDeImpressao,
    ParametrosImpressora,
    documento_de_json,
    documento_para_json,
)
from gestor_comercial.services.exceptions import RecursoNaoEncontradoError
from gestor_comercial.services.impressao_service import ImpressaoService
from tests.unit.test_impressao_service import (
    nova_categoria_com_produto,
    nova_comanda,
    nova_impressora,
    novo_item,
)


@pytest.fixture
def impressao(uow, auth, driver):
    """Mesma fixture de `test_impressao_service.py`: service com driver falso."""
    return ImpressaoService(uow, auth, abrir_driver=driver)


# ----------------------------------------------------------------------
# Serialização do cupom
# ----------------------------------------------------------------------


def test_o_cupom_guardado_volta_igual():
    """Reimprimir tem que sair idêntico ao que teria saído na hora.

    Por isso a fila guarda o documento montado, e não o id da comanda: remontar
    semanas depois pegaria preço novo, item cancelado depois, atendente trocado.
    """
    documento = [
        BlocoTexto("MESA 3", negrito=True, centralizado=True, dobro=True),
        BlocoTexto("2x X-Búrguer — açaí"),
        BlocoTexto(""),
    ]
    assert documento_de_json(documento_para_json(documento)) == documento


@pytest.mark.parametrize("corrompido", ["", "lixo{{{", "null", '{"nao": "e lista"}', "[1, 2]"])
def test_cupom_corrompido_na_fila_nao_derruba_nada(corrompido):
    """Um registro estragado não pode impedir os OUTROS cupons de saírem, nem
    derrubar a tela que lista a fila."""
    assert documento_de_json(corrompido) == []


# ----------------------------------------------------------------------
# O cupom que não saiu vai para a fila
# ----------------------------------------------------------------------


def test_falha_de_impressora_guarda_o_cupom(
    uow, auth, driver_que_falha, gerente, caixa_aberto
):
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert resultados[0].sucesso is False
    fila = impressao.listar_fila()
    assert len(fila) == 1
    assert fila[0].impressora_id == cozinha.id
    assert fila[0].tentativas == 1
    assert "X-Burger" in documento_para_json(documento_de_json(fila[0].documento))
    # O erro do hardware viaja junto: é o que diz ao operador se o problema é
    # papel, cabo ou cadastro.
    assert "cabo" in (fila[0].ultimo_erro or "").lower()


def test_impressao_bem_sucedida_nao_deixa_nada_na_fila(
    uow, impressao, gerente, caixa_aberto
):
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    impressao.imprimir_comanda(comanda.id)

    assert impressao.listar_fila() == []


def test_item_sem_impressora_nenhuma_nao_vai_para_a_fila(
    uow, impressao, gerente, caixa_aberto
):
    """Não há para onde reenviar, e prometer reimpressão mandaria o operador
    procurar na fila uma linha que não existe. O caminho certo continua sendo
    configurar a categoria."""
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", None)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert resultados[0].sucesso is False
    assert impressao.listar_fila() == []


def test_a_descricao_diz_qual_cupom_e(uow, auth, driver_que_falha, gerente, caixa_aberto):
    """O operador escolhe o que reimprimir pelo que reconhece, não por id."""
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    nova_impressora(uow, "Balcão", padrao=True)
    comanda = nova_comanda(uow, caixa_aberto, gerente)

    impressao.imprimir_recibo(comanda.id)

    assert impressao.listar_fila()[0].descricao == "Recibo do cliente"


def test_falha_ao_guardar_na_fila_nao_derruba_a_venda(
    uow, auth, driver_que_falha, gerente, caixa_aberto, monkeypatch
):
    """A venda já está commitada e o cliente já foi embora: perder a fila não
    pode virar o segundo problema em cima do primeiro."""
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    item = novo_item(uow, comanda, lanche)

    def salvar_que_falha(_entidade):
        raise RuntimeError("banco cheio")

    monkeypatch.setattr(uow.fila_impressao, "salvar", salvar_que_falha)

    resultados = impressao.imprimir_comanda(comanda.id)

    assert resultados[0].sucesso is False
    assert item.impresso_em is not None  # o pedido foi confirmado do mesmo jeito


# ----------------------------------------------------------------------
# Reimprimir e descartar
# ----------------------------------------------------------------------


def test_reimprimir_da_fila_tira_o_cupom_quando_sai_no_papel(
    uow, auth, driver, driver_que_falha, gerente, caixa_aberto
):
    falhando = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    falhando.imprimir_comanda(comanda.id)
    item_id = falhando.listar_fila()[0].id

    # A impressora voltou: mesmo banco, driver que funciona.
    funcionando = ImpressaoService(uow, auth, abrir_driver=driver)
    resultado = funcionando.reimprimir_da_fila(item_id)

    assert resultado.sucesso is True
    assert funcionando.listar_fila() == []
    assert "X-Burger" in driver.texto_de("Cozinha")


def test_reimprimir_que_falha_de_novo_mantem_o_cupom_e_conta_a_tentativa(
    uow, auth, driver_que_falha, gerente, caixa_aberto
):
    """Se a impressora continua muda, o cupom continua lá. Tirar da fila uma 2ª
    via que também não saiu perderia o pedido de vez."""
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)
    impressao.imprimir_comanda(comanda.id)
    item_id = impressao.listar_fila()[0].id

    resultado = impressao.reimprimir_da_fila(item_id)

    assert resultado.sucesso is False
    fila = impressao.listar_fila()
    assert len(fila) == 1
    assert fila[0].tentativas == 2


def test_reimprimir_cupom_que_nao_existe_mais(uow, impressao):
    with pytest.raises(RecursoNaoEncontradoError):
        impressao.reimprimir_da_fila(9999)


def test_descartar_tira_o_cupom_da_fila(uow, auth, driver_que_falha, gerente, caixa_aberto):
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_que_falha)
    nova_impressora(uow, "Balcão", padrao=True)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    impressao.imprimir_recibo(comanda.id)
    item_id = impressao.listar_fila()[0].id

    impressao.descartar_da_fila(item_id)

    assert impressao.listar_fila() == []


def test_a_fila_tem_teto(uow):
    """Impressora esquecida desligada por um mês não pode encher o banco de um
    Celeron com milhares de cupons que ninguém vai imprimir."""
    impressora = nova_impressora(uow, "Cozinha")
    for i in range(12):
        uow.fila_impressao.salvar(
            ItemFilaImpressao(
                impressora_id=impressora.id,
                documento=documento_para_json([BlocoTexto(f"cupom {i}")]),
                descricao=f"Cupom {i}",
            )
        )

    descartados = uow.fila_impressao.podar_excedente(manter=5)

    restantes = uow.fila_impressao.listar_pendentes()
    assert descartados == 7
    assert len(restantes) == 5
    # Os que sobram são os MAIS NOVOS: o cupom de ontem já não interessa a
    # ninguém, o do almoço de hoje ainda pode salvar um pedido.
    assert [item.descricao for item in restantes] == [f"Cupom {i}" for i in range(7, 12)]


# ----------------------------------------------------------------------
# A impressão saiu da thread da UI — sem levar a Session junto
# ----------------------------------------------------------------------


def test_o_que_atravessa_para_a_thread_nao_tem_vinculo_com_o_banco(
    uow, auth, gerente, caixa_aberto
):
    """A garantia que sustenta a Fase 3 inteira, e a mais fácil de perder numa
    refatoração distraída.

    A decisão da Fase 4 da remasterização proíbe a `Session` de cruzar fronteira
    de thread — `Session` não é thread-safe, e o preço do erro é corrupção
    silenciosa do banco do food truck. Este teste prova que o driver (que roda na
    outra thread) recebe um `ParametrosImpressora` imutável, e **nunca** a
    entidade `Impressora` do SQLAlchemy.
    """
    recebidos: list[object] = []

    @contextlib.contextmanager
    def espiao(impressora):
        recebidos.append(impressora)

        class _Nada:
            def imprimir(self, documento):
                pass

        yield _Nada()

    impressao = ImpressaoService(uow, auth, abrir_driver=espiao)
    cozinha = nova_impressora(uow, "Cozinha", padrao=True, colunas=32)
    lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
    comanda = nova_comanda(uow, caixa_aberto, gerente)
    novo_item(uow, comanda, lanche)

    impressao.imprimir_comanda(comanda.id)

    assert len(recebidos) == 1
    parametros = recebidos[0]
    assert isinstance(parametros, ParametrosImpressora)
    assert parametros.nome == "Cozinha"
    assert parametros.colunas == 32
    # Retrato imutável: ninguém na outra thread consegue mexer no que veio.
    with pytest.raises(Exception):
        parametros.nome = "outra"  # type: ignore[misc]


def test_a_impressao_roda_em_outra_thread(uow, auth, gerente, caixa_aberto):
    """Se voltar a rodar na thread da UI, a janela volta a congelar."""
    threads: list[str] = []

    @contextlib.contextmanager
    def anotando_a_thread(_impressora):
        class _Driver:
            def imprimir(self, documento):
                threads.append(threading.current_thread().name)

        yield _Driver()

    impressao = ImpressaoService(uow, auth, abrir_driver=anotando_a_thread)
    nova_impressora(uow, "Balcão", padrao=True)
    comanda = nova_comanda(uow, caixa_aberto, gerente)

    impressao.imprimir_recibo(comanda.id)

    assert threads == ["impressao"]
    assert threading.current_thread().name != "impressao"


def test_c2_impressora_que_nao_responde_nao_prende_o_pdv(
    uow, auth, gerente, caixa_aberto
):
    """**C2 do §4.** A porta COM sumiu e o driver ficou pendurado.

    Este é o cenário que a Fase 3 existe para resolver: antes dela, a espera
    acontecia na thread da UI e a janela do PDV congelava junto. Aqui o driver
    trava de propósito e o teste prova as três coisas que importam no balcão: a
    chamada **volta**, a venda conclui, e o cupom fica guardado.
    """
    travar = threading.Event()

    @contextlib.contextmanager
    def driver_pendurado(_impressora):
        class _Driver:
            def imprimir(self, documento):
                travar.wait(30)  # nunca liberado dentro do tempo do teste

        yield _Driver()

    # Teto curto para o teste não demorar 6 s; é o mesmo mecanismo da produção.
    impressao = ImpressaoService(uow, auth, abrir_driver=driver_pendurado)
    import gestor_comercial.services.impressao_service as modulo

    original = modulo.TEMPO_MAXIMO_DE_IMPRESSAO
    modulo.TEMPO_MAXIMO_DE_IMPRESSAO = 0.3
    try:
        cozinha = nova_impressora(uow, "Cozinha", padrao=True)
        lanche = nova_categoria_com_produto(uow, "Lanches", "X-Burger", "20.00", cozinha)
        comanda = nova_comanda(uow, caixa_aberto, gerente)
        item = novo_item(uow, comanda, lanche)

        comeco = time.monotonic()
        resultados = impressao.imprimir_comanda(comanda.id)
        gasto = time.monotonic() - comeco
    finally:
        modulo.TEMPO_MAXIMO_DE_IMPRESSAO = original
        travar.set()

    assert gasto < 5, "a chamada ficou pendurada junto com a impressora"
    assert resultados[0].sucesso is False
    assert "não respondeu" in (resultados[0].erro or "")
    assert item.impresso_em is not None, "a venda tem que concluir mesmo assim"
    assert len(impressao.listar_fila()) == 1
