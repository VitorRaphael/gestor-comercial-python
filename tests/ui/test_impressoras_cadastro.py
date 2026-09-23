"""A tela de Impressoras cadastrando e editando pelo cartão, com o banco de verdade. §9.19.

`test_impressora_dialog.py` prova o cartão sozinho, com uma função `salvar` de
mentira. Aqui a função é a da view, e do outro lado está o `CardapioService`:
é onde se vê que o que o gerente escolhe no cartão é o que fica gravado, que a
troca de impressora de recibo acontece, que o erro do service volta para dentro
do cartão aberto e que a lista recarregada volta com a impressora gravada
selecionada.

O fluxo é o real: `executar_modal` → `exec()`. O gesto do gerente entra por um
`QTimer.singleShot` que roda dentro do laço do `exec()`.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest

from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.hardware.descoberta_local import DestinoLocal
from gestor_comercial.services.cardapio_service import CardapioService
from gestor_comercial.services.impressao_service import ImpressaoService
from gestor_comercial.ui.views.impressoras_view import ImpressorasView
from gestor_comercial.ui.widgets.impressora_dialog import Bobina, Conexao, ImpressoraDialog

DESTINOS = [DestinoLocal("EPSON TM-T20", "WINDOWS", "Impressora do Windows · USB001")]


@pytest.fixture
def pedidos_de_lista(monkeypatch) -> list[int]:
    """A porta do service trocada por uma lista fixa — a suíte não pergunta ao
    spooler desta máquina. Conta as chamadas, para provar que o cartão a usa."""
    chamadas: list[int] = []

    def listar() -> list[DestinoLocal]:
        chamadas.append(1)
        return list(DESTINOS)

    monkeypatch.setattr(ImpressaoService, "listar_destinos_locais", staticmethod(listar))
    return chamadas


@pytest.fixture
def tela(qapp, uow, auth, gerente, pedidos_de_lista):
    cardapio = CardapioService(uow, auth)
    view = ImpressorasView(cardapio, ImpressaoService(uow, auth))
    view.resize(1366, 738)
    view.show()
    yield view, cardapio
    view.deleteLater()


TETO_DO_GESTO_MS = 3000


def _encenar(
    view: ImpressorasView,
    abrir: Callable[[], None],
    gesto: Callable[[ImpressoraDialog], None],
) -> list[str]:
    """Abre o cartão pelo caminho real e faz o gesto do gerente lá dentro.

    O gesto é agendado para dentro do laço do `exec()`, e espera a lista do
    Windows chegar antes de agir, como o gerente que olha a tela antes de
    clicar. Devolve os erros do gesto, porque uma exceção dentro do laço do
    `exec()` não sobe até o teste.

    **Tem teto.** Um cartão que não fecha — o service recusando um salvar que o
    teste esperava aceito — prenderia o `exec()` para sempre, e a suíte
    travaria em vez de reprovar. Foi o que a checagem por mutação encontrou
    (a view editando pelo caminho de criar deixou a suíte parada por horas), e
    é a mesma armadilha do `encenar()` do Cardápio (§9.14). O vigia é filho da
    tela e é parado na volta, para não disparar dentro do teste seguinte.
    """
    erros: list[str] = []

    def cartao_aberto() -> ImpressoraDialog | None:
        return next((c for c in view.findChildren(ImpressoraDialog) if c.isVisible()), None)

    def agir() -> None:
        cartao = cartao_aberto()
        if cartao is None or cartao._estado_da_busca == "procurando":
            QTimer.singleShot(10, agir)
            return
        try:
            gesto(cartao)
        except Exception as erro:  # pragma: no cover - só aparece quando o teste quebra
            erros.append(repr(erro))
            cartao.reject()

    def vigiar() -> None:
        cartao = cartao_aberto()
        if cartao is not None:
            erros.append(f"o cartão continuou aberto depois de {TETO_DO_GESTO_MS}ms")
            cartao.reject()

    vigia = QTimer(view)
    vigia.setSingleShot(True)
    vigia.setInterval(TETO_DO_GESTO_MS)
    vigia.timeout.connect(vigiar)
    vigia.start()
    QTimer.singleShot(0, agir)
    try:
        abrir()
    finally:
        vigia.stop()
        vigia.timeout.disconnect(vigiar)
        vigia.deleteLater()
    return erros


def _clicar(widget) -> None:
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


def test_cadastrar_pelo_cartao_grava_e_seleciona_a_nova(qapp, tela, pedidos_de_lista):
    view, cardapio = tela
    cardapio.criar_impressora("Balcão")
    view.atualizar()

    def cadastrar(cartao: ImpressoraDialog) -> None:
        cartao._campo_nome.setText("Cozinha")
        _clicar(cartao._cards[Conexao.LOCAL])
        cartao._campo_local.setCurrentIndex(1)  # EPSON TM-T20, depois do cabeçalho
        _clicar(cartao._botoes_bobina[Bobina.MM58])
        _clicar(cartao._botao_confirmar)

    erros = _encenar(view, view._criar, cadastrar)

    assert erros == []
    assert pedidos_de_lista == [1], "o cartão não pediu a lista pela porta do service"
    nova = next(i for i in cardapio.listar_impressoras() if i.nome == "Cozinha")
    assert (nova.tipo_conexao, nova.nome_fila, nova.colunas) == (TipoConexaoImpressora.WINDOWS, "EPSON TM-T20", 32)
    assert (nova.ativa, nova.padrao) == (True, False)
    assert view._impressora_selecionada().id == nova.id
    assert view._label_erro.text() == ""


def test_recibo_do_cliente_no_cadastro_troca_a_impressora_padrao(qapp, tela):
    view, cardapio = tela
    balcao = cardapio.criar_impressora("Balcão")
    view.atualizar()

    def cadastrar_recibo(cartao: ImpressoraDialog) -> None:
        assert cartao._uso.currentIndex() == 1, "premissa: com padrão ativa, abre em Produção"
        cartao._campo_nome.setText("Caixa 01")
        cartao._uso.setCurrentIndex(0)
        cartao._uso.activated.emit(0)
        _clicar(cartao._botao_confirmar)

    erros = _encenar(view, view._criar, cadastrar_recibo)

    assert erros == []
    assert [i.nome for i in cardapio.listar_impressoras() if i.padrao] == ["Caixa 01"]
    assert balcao.padrao is False


def test_editar_para_uma_porta_com_grava_serial(qapp, tela):
    view, cardapio = tela
    cardapio.criar_impressora("Balcão", TipoConexaoImpressora.WINDOWS, nome_fila="EPSON TM-T20")
    view.atualizar()
    view._tabela.selectRow(0)

    def trocar_para_com(cartao: ImpressoraDialog) -> None:
        assert cartao._conexao is Conexao.LOCAL
        cartao._campo_local.setEditText("com5")
        _clicar(cartao._situacao)
        _clicar(cartao._botao_confirmar)

    erros = _encenar(view, view._editar, trocar_para_com)

    assert erros == []
    balcao = cardapio.listar_impressoras()[0]
    assert (balcao.tipo_conexao, balcao.porta_serial, balcao.nome_fila) == (TipoConexaoImpressora.SERIAL, "COM5", None)
    assert (balcao.ativa, balcao.padrao) == (False, False)
    assert view._impressora_selecionada().id == balcao.id


def test_abrir_e_salvar_sem_mexer_nao_muda_o_cadastro(qapp, tela):
    """A não-regressão pelo caminho inteiro: tela → cartão → service → banco.
    Com a combinação que a dedução de antes não devolveria (42 colunas numa
    bobina de 58mm) e a escala 4x, do §9.22 e do §9.30."""
    view, cardapio = tela
    cardapio.criar_impressora(
        "Balcão",
        TipoConexaoImpressora.SERIAL,
        porta_serial="COM3",
        baudrate=19200,
        colunas=42,
        bobina_mm=58,
        escala_fonte=4,
    )
    view.atualizar()
    view._tabela.selectRow(0)
    antes = _retrato(cardapio.listar_impressoras()[0])

    erros = _encenar(view, view._editar, lambda cartao: _clicar(cartao._botao_confirmar))

    assert erros == []
    assert _retrato(cardapio.listar_impressoras()[0]) == antes


def test_o_erro_do_service_volta_para_o_cartao_aberto(qapp, tela, uow):
    """O nome ficou ocupado DEPOIS de o cartão abrir (a conferência da tela não
    viu): o service recusa, o cartão continua aberto dizendo por quê, e cancelar
    não grava nada."""
    view, cardapio = tela
    view.atualizar()
    visto: dict[str, object] = {}

    def salvar_nome_tomado(cartao: ImpressoraDialog) -> None:
        cartao._campo_nome.setText("Cozinha")
        uow.impressoras.salvar(Impressora(nome="Cozinha", colunas=48, ativa=True, padrao=False))
        _clicar(cartao._botao_confirmar)
        visto["aberto"] = cartao.isVisible()
        visto["erro"] = cartao._erro_servico.text()
        visto["nome"] = cartao._campo_nome.text()
        _clicar(cartao._botao_cancelar)

    erros = _encenar(view, view._criar, salvar_nome_tomado)

    assert erros == []
    assert visto == {
        "aberto": True,
        "erro": "Já existe uma impressora com o nome 'Cozinha'.",
        "nome": "Cozinha",
    }
    assert [i.nome for i in cardapio.listar_impressoras()] == ["Cozinha"]
    assert view._label_erro.text() == ""


def test_editar_a_unica_de_recibo_avisa_ao_tirar_o_recibo(qapp, tela):
    """A tela conta a impressora EM EDIÇÃO fora da pergunta "há outra de
    recibo?". Contá-la dentro faria o aviso nunca aparecer justamente no caso em
    que ele existe: tirar o recibo da única impressora que o recebe."""
    view, cardapio = tela
    cardapio.criar_impressora("Balcão")
    cardapio.criar_impressora("Cozinha")
    view.atualizar()
    view._tabela.selectRow(0)
    visto: dict[str, object] = {}

    def tirar_o_recibo(cartao: ImpressoraDialog) -> None:
        cartao._uso.setCurrentIndex(1)
        cartao._uso.activated.emit(1)
        visto["status"] = cartao._status.text()
        _clicar(cartao._botao_cancelar)

    erros = _encenar(view, view._editar, tirar_o_recibo)

    assert erros == []
    assert visto == {"status": "Sem impressora de recibo"}


def test_o_cartao_nao_fica_pendurado_na_tela(qapp, tela, assentar):
    view, cardapio = tela
    view.atualizar()

    for _ in range(10):
        _encenar(view, view._criar, lambda cartao: _clicar(cartao._botao_cancelar))
    assentar()

    assert view.findChildren(ImpressoraDialog) == []


def _retrato(impressora: Impressora) -> dict[str, object]:
    return {
        coluna: getattr(impressora, coluna)
        for coluna in (
            "nome",
            "tipo_conexao",
            "vendor_id",
            "product_id",
            "porta_serial",
            "baudrate",
            "host",
            "porta_rede",
            "nome_fila",
            "caminho_arquivo",
            "colunas",
            "bobina_mm",
            "escala_fonte",
            "ativa",
            "padrao",
        )
    }


def test_o_formato_escolhido_no_cartao_e_o_que_fica_gravado_e_o_que_reabre(qapp, tela):
    """§9.22/§9.30 pelo caminho real: cadastrar "58mm + 48 col. + fonte 3x",
    ver o banco, e reabrir a edição com os mesmos três botões acesos."""
    view, cardapio = tela
    view.atualizar()

    def cadastrar(cartao: ImpressoraDialog) -> None:
        cartao._campo_nome.setText("Caixa 01")
        _clicar(cartao._botoes_bobina[Bobina.MM58])
        _clicar(cartao._botoes_colunas[48])
        _clicar(cartao._botoes_escala[3])
        _clicar(cartao._botao_confirmar)

    assert _encenar(view, view._criar, cadastrar) == []
    gravada = next(i for i in cardapio.listar_impressoras() if i.nome == "Caixa 01")
    assert (gravada.colunas, gravada.bobina_mm, gravada.escala_fonte) == (48, 58, 3)

    visto: dict[str, object] = {}

    def conferir(cartao: ImpressoraDialog) -> None:
        visto["bobina"] = cartao._bobina
        visto["colunas"] = [c for c, b in cartao._botoes_colunas.items() if b.property("selecionada")]
        visto["escala"] = [e for e, b in cartao._botoes_escala.items() if b.property("selecionada")]
        visto["resumo"] = cartao._resumo.texto_completo()
        _clicar(cartao._botao_cancelar)

    view._selecionar_por_id(gravada.id)
    assert _encenar(view, view._editar, conferir) == []
    assert visto == {
        "bobina": Bobina.MM58,
        "colunas": [48],
        "escala": [3],
        "resumo": "Caixa 01 · Arquivo · 58mm · 48 col. · fonte 3x",
    }
