"""O cartão "Nova impressora" / "Editar impressora". §9.19.

Um cartão só para os dois modos, e o jeito de ele apodrecer é silencioso: um
`if modo is EDITAR` no meio da montagem e, meses depois, duas telas de novo.
Por isso boa parte daqui é `parametrize` pelos dois modos e pelos cinco tipos de
conexão do banco — o que é igual tem que continuar igual.

O que cobrem, em ordem:

1. **as leituras puras** — IP e porta, o destino local virando USB/SERIAL/
   WINDOWS, a bobina lida das colunas —, sem widget nenhum;
2. **os dois modos** — frases, glifo do botão e o ponto de partida;
3. **a pré-carga** — cada tipo abre no card certo, e abrir e salvar sem mexer
   devolve o MESMO cadastro (a não-regressão que mais importa: ninguém pode
   perder o baudrate ou as 42 colunas por ter aberto a tela);
4. **a interação** — cards, bobina, interruptor e uso;
5. **o veredito** — o que falta, o que está errado e o aviso de recibo;
6. **o salvar** — o erro do service fica no cartão;
7. **a lista do Windows** — em thread, sem bloquear, sem trocar o texto;
8. **o teclado**; 9. **nada espremido**; 10. **o ciclo de vida**.

E o formato do cupom do §9.22/§9.30 (colunas por linha, bobina gravada e
tamanho da fonte — 2x · 3x · 4x, no lugar da espessura), na seção 4b: a bobina reabre como foi GRAVADA, as colunas são
livres em qualquer bobina, trocar de bobina só sugere, e o resumo diz as cinco
coisas a cada clique.
"""

from __future__ import annotations

import threading
import time
import warnings
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QFontDatabase, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QWidget
from shiboken6 import isValid

import gestor_comercial
from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.hardware.descoberta_local import DestinoLocal
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets import impressora_dialog as modulo
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_ARQUIVO_TEXTO,
    GLIFO_COLUNAS,
    GLIFO_IMPRESSORA,
    GLIFO_LETRAS,
    GLIFO_MAIS,
    GLIFO_NEGRITO,
    GLIFO_REDE,
    GLIFO_SINAL,
    GLIFO_USB,
    GLIFO_VISTO,
    RotuloComReticencias,
    _caminho_do_glifo,
)
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.impressora_dialog import (
    COLUNAS_POR_LINHA,
    LIMITE_NOME,
    USO_PRODUCAO,
    USO_RECIBO,
    Bobina,
    Conexao,
    DadosImpressora,
    ImpressoraDialog,
    ModoDoCadastro,
    bobina_da_impressora,
    bobina_das_colunas,
    conexao_do_tipo,
    ler_destino_local,
    ler_endereco_de_rede,
)

DESTINOS = [
    DestinoLocal("EPSON TM-T20", "WINDOWS", "Impressora do Windows · USB001"),
    DestinoLocal("Bematech MP-4200", "WINDOWS", "Impressora do Windows · USB002"),
    DestinoLocal("COM3", "SERIAL", "Porta serial"),
]
CONHECIDOS = {destino.valor.casefold(): destino for destino in DESTINOS}


def _listar() -> list[DestinoLocal]:
    return list(DESTINOS)


def _impressora(tipo: TipoConexaoImpressora = TipoConexaoImpressora.WINDOWS, **campos) -> Impressora:
    """Uma impressora solta, sem banco — o cartão só a lê na construção."""
    padrao = {
        "nome": "Caixa 01",
        "tipo_conexao": tipo,
        "colunas": 48,
        "ativa": True,
        "padrao": True,
    }
    if tipo is TipoConexaoImpressora.WINDOWS and "nome_fila" not in campos:
        padrao["nome_fila"] = "EPSON TM-T20"
    padrao.update(campos)
    return Impressora(**padrao)


@pytest.fixture
def abrir(qapp):
    """Abre o cartão com a lista de destinos FALSA (`_listar`) por padrão.

    Sem isto, cada cartão aberto manda o `ImpressoraDialog` perguntar ao
    Windows de verdade (`ImpressaoService.listar_destinos_locais`) numa thread,
    e o teste espera o spooler responder — o teto é de 3s por espera. Medido
    nesta máquina, a suíte de UI inteira passou de ~2,5 min para mais de 20 só
    por causa disso, e o resultado ainda dependia de quais impressoras estavam
    ligadas no dia. Quem testa o caminho real passa a própria função em
    `listar=`.
    """
    criados: list[ImpressoraDialog] = []

    def _abrir(
        impressora: Impressora | None = None,
        *,
        nomes=("Balcão", "Caixa 01"),
        outra_padrao_ativa: bool = False,
        salvar=None,
        listar=_listar,
        pai: QWidget | None = None,
    ) -> ImpressoraDialog:
        if impressora is None:
            modal = ImpressoraDialog.para_nova(
                list(nomes), pai, ha_padrao_ativa=outra_padrao_ativa, salvar=salvar, listar_destinos=listar
            )
        else:
            modal = ImpressoraDialog.para_editar(
                impressora,
                list(nomes),
                pai,
                outra_padrao_ativa=outra_padrao_ativa,
                salvar=salvar,
                listar_destinos=listar,
            )
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        if isValid(modal):
            modal.reject()
            modal.deleteLater()


def _esperar(qapp, condicao, teto_s: float = 3.0) -> bool:
    limite = time.monotonic() + teto_s
    while not condicao() and time.monotonic() < limite:
        qapp.processEvents()
        time.sleep(0.005)
    return bool(condicao())


def _rotulos(modal: QWidget, nome: str) -> list[str]:
    return [r.text() for r in modal.findChildren(QLabel) if r.objectName() == nome]


def _clicar(widget: QWidget) -> None:
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


def _tecla(alvo: QWidget, tecla: Qt.Key) -> None:
    QApplication.sendEvent(alvo, QKeyEvent(QEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


# ---------------------------------------------------------------------------
# 1. Leituras puras
# ---------------------------------------------------------------------------


def test_rede_com_porta():
    leitura = ler_endereco_de_rede(" 192.168.1.200:9101 ")

    assert leitura.tipo is TipoConexaoImpressora.REDE
    assert leitura.parametros == {"host": "192.168.1.200", "porta_rede": 9101}


def test_rede_sem_porta_usa_a_9100():
    assert ler_endereco_de_rede("10.0.0.7").parametros == {"host": "10.0.0.7", "porta_rede": 9100}


@pytest.mark.parametrize(
    "texto", ["192.168.1", "192.168.1.256", "192.168.001.200", "impressora.local", "192.168.1.2x", ":9100"]
)
def test_ip_que_nao_e_ipv4_e_erro(texto):
    leitura = ler_endereco_de_rede(texto)

    assert leitura.tipo is None
    assert leitura.grave is True
    assert "IP" in leitura.problema


@pytest.mark.parametrize(
    "texto", ["192.168.1.200:0", "192.168.1.200:70000", "192.168.1.200:abc", "192.168.1.200:", "192.168.1.200:-1"]
)
def test_porta_fora_da_faixa_e_erro(texto):
    leitura = ler_endereco_de_rede(texto)

    assert leitura.tipo is None
    assert leitura.grave is True
    assert "Porta" in leitura.problema


def test_rede_vazia_e_pendente_e_nao_erro():
    leitura = ler_endereco_de_rede("   ")

    assert leitura.tipo is None
    assert leitura.grave is False


def test_destino_da_lista_decide_o_tipo_sem_diferenciar_caixa():
    fila = ler_destino_local("epson tm-t20", CONHECIDOS)
    porta = ler_destino_local("COM3", CONHECIDOS)

    assert (fila.tipo, fila.parametros) == (TipoConexaoImpressora.WINDOWS, {"nome_fila": "EPSON TM-T20"})
    assert porta.tipo is TipoConexaoImpressora.SERIAL


@pytest.mark.parametrize(
    ("texto", "tipo", "parametros"),
    [
        ("com7", TipoConexaoImpressora.SERIAL, {"porta_serial": "COM7", "baudrate": None}),
        ("4b8:202", TipoConexaoImpressora.USB, {"vendor_id": "0x04b8", "product_id": "0x0202"}),
        ("0x04B8 : 0x0E15", TipoConexaoImpressora.USB, {"vendor_id": "0x04b8", "product_id": "0x0e15"}),
        ("Elgin i9", TipoConexaoImpressora.WINDOWS, {"nome_fila": "Elgin i9"}),
    ],
)
def test_destino_digitado_e_lido_pelo_formato(texto, tipo, parametros):
    """Fora da lista, o formato decide: COMn é serial, vendor:product é USB
    direto, e o resto é o nome de uma fila — a impressora pode ainda nem estar
    instalada nesta máquina."""
    leitura = ler_destino_local(texto, {})

    assert (leitura.tipo, leitura.parametros) == (tipo, parametros)


def test_destino_vazio_e_pendente():
    leitura = ler_destino_local("", CONHECIDOS)

    assert (leitura.tipo, leitura.grave) == (None, False)


def test_o_baudrate_so_vai_para_a_porta_serial():
    assert ler_destino_local("COM3", {}, 19200).parametros["baudrate"] == 19200
    assert "baudrate" not in ler_destino_local("EPSON TM-T20", {}, 19200).parametros


@pytest.mark.parametrize(
    ("tipo", "card"),
    [
        (TipoConexaoImpressora.ARQUIVO, Conexao.ARQUIVO),
        (TipoConexaoImpressora.REDE, Conexao.REDE),
        (TipoConexaoImpressora.USB, Conexao.LOCAL),
        (TipoConexaoImpressora.SERIAL, Conexao.LOCAL),
        (TipoConexaoImpressora.WINDOWS, Conexao.LOCAL),
    ],
)
def test_cada_tipo_do_banco_tem_um_card(tipo, card):
    assert conexao_do_tipo(tipo) is card


@pytest.mark.parametrize(("colunas", "bobina"), [(32, Bobina.MM58), (40, Bobina.MM58), (42, Bobina.MM80), (48, Bobina.MM80)])
def test_a_bobina_e_lida_das_colunas(colunas, bobina):
    """42 colunas é o caso ambíguo, e o pedido o põe na de 80mm."""
    assert bobina_das_colunas(colunas) is bobina


# ---------------------------------------------------------------------------
# 2. Os dois modos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("modo", "titulo", "subtitulo", "botao", "glifo"),
    [
        ("novo", "Nova impressora", "Cadastre a conexão e o uso desta impressora.", "Cadastrar impressora", GLIFO_MAIS),
        ("editar", "Editar impressora", "Atualize a conexão e o uso desta impressora.", "Salvar alterações", GLIFO_VISTO),
    ],
)
def test_cada_modo_tem_as_proprias_frases(abrir, modo, titulo, subtitulo, botao, glifo):
    modal = abrir(_impressora() if modo == "editar" else None)

    assert _rotulos(modal, "impDialogSecao") == ["SAÍDA E PRODUÇÃO"]
    assert _rotulos(modal, "impDialogTitulo") == [titulo]
    assert _rotulos(modal, "impDialogSubtitulo") == [subtitulo]
    assert modal._botao_confirmar.text() == botao
    assert modal._botao_confirmar._glifo == glifo


def test_o_modo_aceita_o_texto_do_pedido(qapp):
    """`modo="novo"`/`modo="editar"`, como o pedido escreveu."""
    novo = ImpressoraDialog("novo")
    editar = ImpressoraDialog("editar", impressora=_impressora())

    assert (novo._modo, editar._modo) == (ModoDoCadastro.NOVO, ModoDoCadastro.EDITAR)
    for modal in (novo, editar):
        modal.reject()
        modal.deleteLater()


@pytest.mark.parametrize(("modo", "impressora"), [("editar", None), ("novo", "sim")])
def test_modo_e_impressora_tem_que_combinar(qapp, modo, impressora):
    """Editar sem impressora abriria um cartão "Editar" vazio que CADASTRARIA
    uma nova; recusa na construção, antes de existir widget pendurado."""
    with pytest.raises(ValueError):
        ImpressoraDialog(modo, impressora=_impressora() if impressora else None)


def test_o_cadastro_abre_em_arquivo_80mm_e_ativo(abrir):
    """ARQUIVO é o default de `criar_impressora`: é o que imprime sem hardware."""
    modal = abrir()

    assert modal._conexao is Conexao.ARQUIVO
    assert modal._bobina is Bobina.MM80
    assert modal._situacao.interruptor.ligado is True
    assert modal._campo_nome.text() == ""
    # O resto do default de `criar_impressora`: 48 colunas e destaque em 2x.
    assert [c for c, b in modal._botoes_colunas.items() if b.property("selecionada")] == [48]
    assert [e for e, b in modal._botoes_escala.items() if b.property("selecionada")] == [2]
    assert (modal.resultado().colunas, modal.resultado().bobina_mm, modal.resultado().escala_fonte) == (48, 80, 2)


@pytest.mark.parametrize(("ha_padrao", "uso"), [(False, USO_RECIBO), (True, USO_PRODUCAO)])
def test_o_cadastro_abre_no_uso_que_o_service_daria(abrir, ha_padrao, uso):
    """Sem padrão ativa, "Recibo do cliente" — a regra automática do service."""
    modal = abrir(outra_padrao_ativa=ha_padrao)

    assert modal._uso.currentText() == uso


# ---------------------------------------------------------------------------
# 3. A pré-carga
# ---------------------------------------------------------------------------

CADASTROS = {
    "usb": dict(tipo=TipoConexaoImpressora.USB, vendor_id="0x04b8", product_id="0x0202"),
    "serial": dict(tipo=TipoConexaoImpressora.SERIAL, porta_serial="COM3", baudrate=19200),
    "windows": dict(tipo=TipoConexaoImpressora.WINDOWS, nome_fila="EPSON TM-T20"),
    "rede": dict(tipo=TipoConexaoImpressora.REDE, host="192.168.0.50", porta_rede=9101),
    "arquivo": dict(tipo=TipoConexaoImpressora.ARQUIVO, caminho_arquivo=r"C:\cupons\caixa.txt"),
}


@pytest.mark.parametrize(
    ("chave", "card", "texto"),
    [
        ("usb", Conexao.LOCAL, "0x04b8:0x0202"),
        ("serial", Conexao.LOCAL, "COM3"),
        ("windows", Conexao.LOCAL, "EPSON TM-T20"),
        ("rede", Conexao.REDE, "192.168.0.50:9101"),
        ("arquivo", Conexao.ARQUIVO, r"C:\cupons\caixa.txt"),
    ],
)
def test_a_edicao_abre_no_card_e_com_o_campo_certos(abrir, chave, card, texto):
    campos = dict(CADASTROS[chave])
    modal = abrir(_impressora(campos.pop("tipo"), **campos))

    campo = modal._campos[card]
    atual = campo.currentText() if card is Conexao.LOCAL else campo.text()
    assert modal._conexao is card
    assert modal._cards[card].property("selecionado") is True
    assert modal._pilha.currentWidget() is campo
    assert atual == texto


@pytest.mark.parametrize("chave", list(CADASTROS))
@pytest.mark.parametrize(
    ("colunas", "bobina_mm", "escala_fonte"),
    # As quatro do seletor, a 42 que ficou sem botão, e as combinações
    # "cruzadas" que só a bobina GRAVADA devolve (58mm com 48 e com 80).
    [(32, 58, 2), (42, 80, 3), (48, 58, 4), (48, 80, 2), (64, 80, 3), (80, 58, 4), (80, 80, 2)],
)
def test_abrir_e_salvar_sem_mexer_devolve_o_mesmo_cadastro(abrir, qapp, chave, colunas, bobina_mm, escala_fonte):
    """A não-regressão que mais importa. Nenhum dado some por ter aberto a tela:
    nem o baudrate que o mockup não mostra, nem as 42 colunas que o seletor
    não tem, nem a bobina que a dedução de antes chamaria de outra coisa, nem a
    escala da fonte. Roda também com a lista do Windows já carregada, que é o que
    acontece de verdade."""
    campos = dict(CADASTROS[chave])
    tipo = campos.pop("tipo")
    modal = abrir(
        _impressora(tipo, colunas=colunas, bobina_mm=bobina_mm, escala_fonte=escala_fonte, **campos),
        listar=_listar,
    )
    modal.show()
    assert _esperar(qapp, lambda: modal._estado_da_busca == "pronta")

    dados = modal.resultado()

    assert dados.tipo_conexao is tipo
    assert (dados.colunas, dados.bobina_mm, dados.escala_fonte) == (colunas, bobina_mm, escala_fonte)
    assert (dados.nome, dados.ativa, dados.padrao) == ("Caixa 01", True, True)
    for campo, valor in campos.items():
        assert getattr(dados, campo) == valor, campo


def test_a_edicao_de_uma_desligada_abre_desligada_e_em_producao(abrir):
    modal = abrir(_impressora(ativa=False, padrao=False), outra_padrao_ativa=True)

    assert modal._situacao.interruptor.ligado is False
    assert _rotulos(modal, "impDialogSituacaoTexto") == ["Impressora desativada"]
    assert modal._uso.currentText() == USO_PRODUCAO


# ---------------------------------------------------------------------------
# 4. A interação
# ---------------------------------------------------------------------------


def test_clicar_um_card_troca_o_campo_e_o_rotulo(abrir):
    modal = abrir()

    _clicar(modal._cards[Conexao.REDE])

    assert modal._pilha.currentWidget() is modal._campo_rede
    assert modal._rotulo_destino.text() == "IP E PORTA DA IMPRESSORA"
    assert [c for c, card in modal._cards.items() if card.property("selecionado")] == [Conexao.REDE]
    assert modal._cards[Conexao.REDE]._visto.isVisibleTo(modal._cards[Conexao.REDE])
    assert not modal._cards[Conexao.ARQUIVO]._visto.isVisibleTo(modal._cards[Conexao.ARQUIVO])


def test_o_card_usb_se_apresenta_como_porta_usb(abrir):
    modal = abrir()

    _clicar(modal._cards[Conexao.LOCAL])

    assert modal._rotulo_destino.text() == "PORTA USB"
    assert modal._pilha.currentWidget() is modal._campo_local


def test_trocar_de_card_e_voltar_preserva_o_que_foi_digitado(abrir):
    modal = abrir()
    _clicar(modal._cards[Conexao.REDE])
    modal._campo_rede.setText("10.0.0.9")

    _clicar(modal._cards[Conexao.ARQUIVO])
    _clicar(modal._cards[Conexao.REDE])

    assert modal._campo_rede.text() == "10.0.0.9"


def test_so_o_campo_do_card_escolhido_vai_para_o_resultado(abrir):
    """Os três campos guardam o que foi digitado, mas só um é lido: o service
    limpa o resto, e mandar um IP velho junto de uma fila seria lixo no banco."""
    modal = abrir()
    modal._campo_nome.setText("Caixa 02")
    modal._campo_rede.setText("10.0.0.9")
    _clicar(modal._cards[Conexao.LOCAL])
    modal._campo_local.setEditText("EPSON TM-T20")

    dados = modal.resultado()

    assert dados.tipo_conexao is TipoConexaoImpressora.WINDOWS
    assert (dados.host, dados.nome_fila) == (None, "EPSON TM-T20")


def test_58mm_grava_32_colunas(abrir):
    modal = abrir()

    _clicar(modal._botoes_bobina[Bobina.MM58])

    assert (modal.resultado().colunas, modal.resultado().bobina_mm) == (32, 58)
    assert modal._botoes_bobina[Bobina.MM58].property("selecionada") is True
    assert modal._botoes_bobina[Bobina.MM80].property("selecionada") is False
    assert _colunas_acesas(modal) == [32]


def test_trocar_a_bobina_e_voltar_devolve_a_largura_cadastrada(abrir):
    modal = abrir(_impressora(colunas=42))

    _clicar(modal._botoes_bobina[Bobina.MM58])
    assert modal.resultado().colunas == 32
    _clicar(modal._botoes_bobina[Bobina.MM80])

    assert modal.resultado().colunas == 42


def test_desligar_tira_o_recibo_e_religar_devolve(abrir):
    """Impressora desligada nunca é a padrão. A tela mostra isso ANTES de
    salvar: o seletor vai para Produção com o Recibo indisponível, e religar
    devolve a escolha que o gerente tinha feito."""
    modal = abrir(_impressora(padrao=True))

    _clicar(modal._situacao)

    assert modal._situacao.interruptor.ligado is False
    assert modal._uso.currentText() == USO_PRODUCAO
    assert modal._uso.model().item(0).isEnabled() is False
    assert (modal.resultado().ativa, modal.resultado().padrao) == (False, False)

    _clicar(modal._situacao)

    assert modal._uso.currentText() == USO_RECIBO
    assert modal._uso.model().item(0).isEnabled() is True
    assert (modal.resultado().ativa, modal.resultado().padrao) == (True, True)


def test_clicar_no_interruptor_tambem_alterna(abrir):
    """O alvo é o card inteiro, e o interruptor pintado deixa o clique passar."""
    modal = abrir()

    _clicar(modal._situacao.interruptor)

    assert modal.resultado().ativa is False


def test_o_uso_escolhido_vira_padrao(abrir):
    modal = abrir(_impressora(padrao=True))

    modal._uso.setCurrentIndex(1)
    modal._uso.activated.emit(1)

    assert modal.resultado().padrao is False


def test_o_resumo_acompanha_nome_conexao_e_bobina(abrir):
    modal = abrir()

    modal._campo_nome.setText("  Caixa   01 ")
    _clicar(modal._cards[Conexao.LOCAL])
    _clicar(modal._botoes_bobina[Bobina.MM58])

    assert modal._resumo.texto_completo() == "Caixa 01 · USB · 58mm · 32 col. · fonte 2x"
    assert _rotulos(modal, "impDialogResumoRotulo") == ["RESUMO DA CONFIGURAÇÃO"]


def test_o_contador_acompanha_a_digitacao(abrir):
    modal = abrir()

    modal._campo_nome.setText("Caixa 01")

    assert _rotulos(modal, "impDialogContador") == [f"8/{LIMITE_NOME}"]
    assert modal._campo_nome.maxLength() == LIMITE_NOME


def test_editar_um_nome_mais_longo_que_o_teto_nao_o_corta(abrir):
    comprido = "Impressora térmica do balcão principal da loja 2"
    assert len(comprido) > LIMITE_NOME
    modal = abrir(_impressora(nome=comprido), nomes=[comprido])

    assert modal.resultado().nome == comprido


# ---------------------------------------------------------------------------
# 4b. O formato do cupom (§9.22, §9.30): colunas, bobina gravada e escala
# ---------------------------------------------------------------------------


def _colunas_acesas(modal: ImpressoraDialog) -> list[int]:
    return [colunas for colunas, botao in modal._botoes_colunas.items() if botao.property("selecionada")]


def _formato(modal: ImpressoraDialog) -> tuple[int, int, int]:
    dados = modal.resultado()
    return dados.colunas, dados.bobina_mm, dados.escala_fonte


def test_o_seletor_tem_as_quatro_larguras_decididas():
    """32 · 48 · 64 · 80: a resposta do Vitor, com o 64 condensado no meio."""
    assert COLUNAS_POR_LINHA == (32, 48, 64, 80)


def test_cada_botao_de_colunas_mostra_o_numero_e_explica_a_fonte(abrir):
    modal = abrir()

    assert [botao.text() for botao in modal._botoes_colunas.values()] == ["32", "48", "64", "80"]
    assert "condensada" in modal._botoes_colunas[64].toolTip()
    assert "régua do cupom de teste" in modal._botoes_colunas[80].toolTip()


@pytest.mark.parametrize("colunas", COLUNAS_POR_LINHA)
def test_as_colunas_sao_livres_na_bobina_de_58mm(abrir, colunas):
    """A liberdade do pedido: 58mm com 80 colunas é gravado como escolhido."""
    modal = abrir()
    _clicar(modal._botoes_bobina[Bobina.MM58])

    _clicar(modal._botoes_colunas[colunas])

    assert _formato(modal) == (colunas, 58, 2)
    assert _colunas_acesas(modal) == [colunas]
    assert modal._bobina is Bobina.MM58, "escolher colunas não pode mexer na bobina"


def test_80mm_sugere_48_a_quem_vem_da_58(abrir):
    modal = abrir(_impressora(colunas=32, bobina_mm=58))

    _clicar(modal._botoes_bobina[Bobina.MM80])

    assert _formato(modal) == (48, 80, 2)
    assert _colunas_acesas(modal) == [48]


def test_58mm_sugere_32_mesmo_para_quem_escolheu_80(abrir):
    modal = abrir()
    _clicar(modal._botoes_colunas[80])

    _clicar(modal._botoes_bobina[Bobina.MM58])

    assert _formato(modal) == (32, 58, 2)


def test_cada_bobina_lembra_as_colunas_que_tinha(abrir):
    """A sugestão vale na primeira visita. Depois, cada bobina devolve o que o
    gerente tinha escolhido nela: ir e voltar não desfaz escolha nenhuma."""
    modal = abrir()
    _clicar(modal._botoes_colunas[64])
    _clicar(modal._botoes_bobina[Bobina.MM58])
    _clicar(modal._botoes_colunas[48])

    _clicar(modal._botoes_bobina[Bobina.MM80])
    assert _formato(modal)[:2] == (64, 80)

    _clicar(modal._botoes_bobina[Bobina.MM58])
    assert _formato(modal)[:2] == (48, 58)


def test_clicar_a_bobina_ja_escolhida_nao_mexe_nas_colunas(abrir):
    modal = abrir()
    _clicar(modal._botoes_colunas[80])

    _clicar(modal._botoes_bobina[Bobina.MM80])

    assert _formato(modal) == (80, 80, 2)


def test_uma_largura_sem_botao_abre_sem_botao_aceso_e_volta_intacta(abrir):
    """42 colunas (de antes do seletor): nenhum botão acende, o resumo diz a
    verdade, e ir à 58mm e voltar devolve as 42 cadastradas."""
    modal = abrir(_impressora(colunas=42, bobina_mm=80))

    assert _colunas_acesas(modal) == []
    assert "· 42 col. ·" in modal._resumo.texto_completo()

    _clicar(modal._botoes_bobina[Bobina.MM58])
    _clicar(modal._botoes_bobina[Bobina.MM80])

    assert _formato(modal) == (42, 80, 2)


def test_a_edicao_abre_na_bobina_gravada_e_nao_na_deduzida(abrir):
    """O ponto da decisão do Vitor: 58mm com 48 colunas. A regra de antes
    (até 40 colunas é 58mm) reabriria esta impressora como 80mm."""
    modal = abrir(_impressora(colunas=48, bobina_mm=58))

    assert modal._bobina is Bobina.MM58
    assert modal._botoes_bobina[Bobina.MM58].property("selecionada") is True
    assert _colunas_acesas(modal) == [48]
    assert _formato(modal) == (48, 58, 2)


@pytest.mark.parametrize(("bobina_mm", "colunas", "bobina"), [(None, 32, Bobina.MM58), (None, 48, Bobina.MM80), (76, 32, Bobina.MM58)])
def test_sem_bobina_valida_a_bobina_sai_das_colunas(bobina_mm, colunas, bobina):
    """Do banco ela sempre vem (`NOT NULL`). Uma impressora ainda não gravada, ou
    um valor mexido à mão, cai na regra de antes — e não derruba a abertura."""
    assert bobina_da_impressora(_impressora(colunas=colunas, bobina_mm=bobina_mm)) is bobina


def _escalas_acesas(modal: ImpressoraDialog) -> list[int]:
    return [escala for escala, botao in modal._botoes_escala.items() if botao.property("selecionada")]


def test_o_seletor_tem_as_tres_escalas_inteiras():
    """2x · 3x · 4x: o 2,5x pedido não existe no `GS !` do ESC/POS (§9.30)."""
    assert modulo.ESCALAS_FONTE == (2, 3, 4)


def test_cada_botao_de_escala_mostra_o_multiplicador_e_explica(abrir):
    modal = abrir()

    assert [botao.text() for botao in modal._botoes_escala.values()] == ["2x", "3x", "4x"]
    assert all(botao.toolTip() for botao in modal._botoes_escala.values())
    assert all(botao.objectName() == "impDialogEscala" for botao in modal._botoes_escala.values())


def test_a_espessura_saiu_do_cartao(abrir):
    """"Letras finas"/"Letras grossas" não existem mais em lugar nenhum da tela."""
    modal = abrir()
    textos = [w.text() for w in modal.findChildren(QLabel)] + [w.text() for w in modal.findChildren(QPushButton)]

    assert not any("Letras" in texto or "ESPESSURA" in texto for texto in textos)
    assert "TAMANHO DA FONTE" in textos
    assert not hasattr(modulo, "Espessura")


@pytest.mark.parametrize("escala", [2, 3, 4])
def test_a_edicao_abre_na_escala_gravada(abrir, escala):
    modal = abrir(_impressora(escala_fonte=escala))

    assert _escalas_acesas(modal) == [escala]
    assert modal.resultado().escala_fonte == escala


@pytest.mark.parametrize("bruta", [None, 1, 5, 8])
def test_escala_fora_do_seletor_abre_em_2x(abrir, bruta):
    """Impressora ainda não gravada chega com `None` (o default do ORM só vale
    no INSERT); um valor mexido à mão, com um número sem botão. Nos dois casos
    o cartão abre em 2x com o botão aceso, e nunca devolve ao service uma escala
    que ele recusaria."""
    modal = abrir(_impressora(escala_fonte=bruta))

    assert _escalas_acesas(modal) == [2]
    assert modal.resultado().escala_fonte == 2


def test_clicar_na_escala_troca_e_acende_so_ela(abrir):
    modal = abrir()

    _clicar(modal._botoes_escala[4])
    assert modal.resultado().escala_fonte == 4
    assert _escalas_acesas(modal) == [4]

    _clicar(modal._botoes_escala[3])
    assert modal.resultado().escala_fonte == 3
    assert _escalas_acesas(modal) == [3]


def test_o_resumo_do_mockup_sai_letra_por_letra(abrir):
    """O exemplo do pedido, montado clique a clique."""
    modal = abrir()
    modal._campo_nome.setText("Caixa 01")
    _clicar(modal._cards[Conexao.LOCAL])
    _clicar(modal._botoes_colunas[80])
    _clicar(modal._botoes_escala[3])

    assert modal._resumo.texto_completo() == "Caixa 01 · USB · 80mm · 80 col. · fonte 3x"


def test_o_resumo_muda_a_cada_seletor(abrir):
    """Cada seletor, sozinho, muda o resumo na hora — nenhum espera outro gesto."""
    modal = abrir()
    modal._campo_nome.setText("Caixa 01")
    vistos = [modal._resumo.texto_completo()]

    for gesto in (
        lambda: _clicar(modal._botoes_bobina[Bobina.MM58]),
        lambda: _clicar(modal._botoes_colunas[64]),
        lambda: _clicar(modal._botoes_escala[4]),
        lambda: _clicar(modal._cards[Conexao.REDE]),
    ):
        gesto()
        vistos.append(modal._resumo.texto_completo())

    assert vistos == [
        "Caixa 01 · Arquivo · 80mm · 48 col. · fonte 2x",
        "Caixa 01 · Arquivo · 58mm · 32 col. · fonte 2x",
        "Caixa 01 · Arquivo · 58mm · 64 col. · fonte 2x",
        "Caixa 01 · Arquivo · 58mm · 64 col. · fonte 4x",
        "Caixa 01 · Rede · 58mm · 64 col. · fonte 4x",
    ]


def test_o_formato_nao_mexe_no_veredito_nem_no_uso(abrir):
    """Aparência do papel, e só: colunas e escala não ligam nem desligam o
    botão, nem mudam o uso ou a situação."""
    modal = abrir(outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")
    antes = (_veredito(modal), modal.resultado().padrao, modal.resultado().ativa)

    _clicar(modal._botoes_colunas[80])
    _clicar(modal._botoes_escala[4])
    _clicar(modal._botoes_bobina[Bobina.MM58])

    assert (_veredito(modal), modal.resultado().padrao, modal.resultado().ativa) == antes


# ---------------------------------------------------------------------------
# 5. O veredito
# ---------------------------------------------------------------------------


def _veredito(modal: ImpressoraDialog) -> tuple[str, str, bool]:
    return modal._status.text(), modal._status.property("estado"), modal._botao_confirmar.isEnabled()


def test_sem_nome_e_pendente(abrir):
    assert _veredito(abrir()) == ("Falta o nome", "pendente", False)


def test_uma_letra_so_e_pendente(abrir):
    modal = abrir()

    modal._campo_nome.setText("C")

    assert _veredito(modal)[1:] == ("pendente", False)


def test_nome_repetido_desliga_o_botao(abrir):
    modal = abrir(nomes=["Balcão"])

    modal._campo_nome.setText("Balcão")

    assert _veredito(modal) == ("✕  Nome já existente", "erro", False)


def test_nome_com_outra_caixa_passa_porque_o_service_aceita(abrir):
    """`_exigir_nome_de_impressora_livre` compara o nome EXATO. Barrar "balcão"
    aqui seria a tela mentindo sobre uma regra que o service não tem."""
    modal = abrir(nomes=["Balcão"], outra_padrao_ativa=True)

    modal._campo_nome.setText("balcão")

    assert _veredito(modal) == ("", "ok", True)


def test_a_edicao_aceita_o_proprio_nome(abrir):
    modal = abrir(_impressora(nome="Balcão"), nomes=["Balcão", "Cozinha"])

    assert _veredito(modal) == ("", "ok", True)


def test_ip_invalido_desliga_o_botao(abrir):
    modal = abrir(outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")
    _clicar(modal._cards[Conexao.REDE])

    modal._campo_rede.setText("192.168.1.300")

    assert _veredito(modal) == ("✕  IP inválido", "erro", False)


def test_usb_sem_destino_e_pendente(abrir):
    modal = abrir(outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")

    _clicar(modal._cards[Conexao.LOCAL])

    assert _veredito(modal) == ("Escolha a impressora local", "pendente", False)


def test_producao_sem_outra_de_recibo_avisa_mas_deixa_salvar(abrir):
    """O recibo e o fechamento de caixa não imprimiriam — é aviso, não trava: o
    gerente pode estar cadastrando a cozinha antes da impressora do caixa."""
    modal = abrir(outra_padrao_ativa=False)
    modal._campo_nome.setText("Cozinha")

    modal._uso.setCurrentIndex(1)
    modal._uso.activated.emit(1)

    assert _veredito(modal) == ("Sem impressora de recibo", "aviso", True)


def test_com_outra_de_recibo_nao_ha_aviso(abrir):
    modal = abrir(outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")

    assert _veredito(modal) == ("", "ok", True)


def test_desligar_a_unica_de_recibo_avisa(abrir):
    modal = abrir(_impressora(padrao=True), outra_padrao_ativa=False)

    _clicar(modal._situacao)

    assert _veredito(modal)[:2] == ("Sem impressora de recibo", "aviso")


# ---------------------------------------------------------------------------
# 6. O salvar
# ---------------------------------------------------------------------------


def test_salvar_entrega_os_dados_e_fecha(abrir):
    recebidos: list[DadosImpressora] = []

    def salvar(dados: DadosImpressora) -> None:
        recebidos.append(dados)
        return None

    modal = abrir(salvar=salvar, outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")
    _clicar(modal._cards[Conexao.REDE])
    modal._campo_rede.setText("192.168.0.60")

    _clicar(modal._botao_confirmar)

    assert modal.result() == QDialog.DialogCode.Accepted
    assert recebidos == [
        DadosImpressora(
            nome="Cozinha",
            tipo_conexao=TipoConexaoImpressora.REDE,
            colunas=48,
            ativa=True,
            padrao=False,
            host="192.168.0.60",
            porta_rede=9100,
        )
    ]


def test_os_parametros_sao_os_kwargs_do_service():
    dados = DadosImpressora(
        "Cozinha",
        TipoConexaoImpressora.SERIAL,
        32,
        False,
        False,
        bobina_mm=58,
        escala_fonte=3,
        porta_serial="COM3",
        baudrate=9600,
    )

    assert dados.parametros() == {
        "vendor_id": None,
        "product_id": None,
        "porta_serial": "COM3",
        "baudrate": 9600,
        "host": None,
        "porta_rede": None,
        "nome_fila": None,
        "caminho_arquivo": None,
        "colunas": 32,
        "bobina_mm": 58,
        "escala_fonte": 3,
        "ativa": False,
        "padrao": False,
    }


@pytest.mark.parametrize("metodo", ["criar_impressora", "editar_impressora"])
def test_o_service_aceita_cada_parametro_do_cartao(metodo):
    """A view faz `**dados.parametros()`: uma chave que o service não conhece
    só estouraria no clique de Salvar, com `TypeError` — que não está nos
    erros que a view mostra."""
    import inspect

    from gestor_comercial.services.cardapio_service import CardapioService

    aceitos = set(inspect.signature(getattr(CardapioService, metodo)).parameters)
    dados = DadosImpressora("Cozinha", TipoConexaoImpressora.ARQUIVO, 48, True, False)

    assert set(dados.parametros()) - aceitos == set()


def test_o_erro_do_service_fica_no_cartao_sem_perder_nada(abrir):
    modal = abrir(salvar=lambda dados: "Já existe uma impressora com o nome 'Cozinha'.", outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")
    _clicar(modal._botoes_bobina[Bobina.MM58])

    _clicar(modal._botao_confirmar)

    assert modal.result() != QDialog.DialogCode.Accepted
    assert _rotulos(modal, "impDialogResumoRotulo") == ["NÃO FOI POSSÍVEL SALVAR"]
    assert modal._erro_servico.text().startswith("Já existe")
    assert modal._erro_servico.isVisibleTo(modal)
    assert modal._rotulo_resumo.property("estado") == "erro"
    assert (modal._campo_nome.text(), modal._bobina) == ("Cozinha", Bobina.MM58)


def test_mexer_depois_do_erro_apaga_o_erro(abrir):
    modal = abrir(salvar=lambda dados: "Recusado.", outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")
    _clicar(modal._botao_confirmar)

    modal._campo_nome.setText("Cozinha 2")

    assert _rotulos(modal, "impDialogResumoRotulo") == ["RESUMO DA CONFIGURAÇÃO"]
    assert not modal._erro_servico.isVisibleTo(modal)


def test_botao_desligado_nao_chama_o_service(abrir):
    chamadas: list[DadosImpressora] = []
    modal = abrir(salvar=chamadas.append)

    _tecla(modal, Qt.Key.Key_Return)

    assert chamadas == []
    assert modal.result() != QDialog.DialogCode.Accepted


# ---------------------------------------------------------------------------
# 7. A lista do Windows
# ---------------------------------------------------------------------------


def _itens(modal: ImpressoraDialog) -> list[tuple[str, bool]]:
    modelo = modal._campo_local.model()
    return [
        (modal._campo_local.itemText(i), modelo.item(i).isEnabled())
        for i in range(modal._campo_local.count())
    ]


def test_a_lista_chega_com_os_cabecalhos_desligados(abrir, qapp):
    modal = abrir(listar=_listar)
    modal.show()

    assert _esperar(qapp, lambda: modal._estado_da_busca == "pronta")
    assert _itens(modal) == [
        ("IMPRESSORAS DO WINDOWS", False),
        ("EPSON TM-T20", True),
        ("Bematech MP-4200", True),
        ("PORTAS COM", False),
        ("COM3", True),
    ]
    assert modal._campo_local.itemData(4, Qt.ItemDataRole.ToolTipRole) == "Porta serial"
    assert modal._campo_local.lineEdit().placeholderText() == "Escolha a impressora instalada"


def test_a_lista_chegando_nao_troca_o_texto_da_edicao(abrir, qapp):
    """Num combo editável o primeiro `addItem` troca o texto do campo: a edição
    de uma impressora COM3 abriria com o nome da primeira fila no lugar."""
    modal = abrir(_impressora(TipoConexaoImpressora.SERIAL, porta_serial="COM9"), listar=_listar)
    modal.show()

    assert _esperar(qapp, lambda: modal._estado_da_busca == "pronta")
    assert modal._campo_local.currentText() == "COM9"
    assert modal.resultado().porta_serial == "COM9"


def test_escolher_na_lista_da_o_tipo_do_item(abrir, qapp):
    modal = abrir(listar=_listar)
    modal.show()
    assert _esperar(qapp, lambda: modal._estado_da_busca == "pronta")
    _clicar(modal._cards[Conexao.LOCAL])

    modal._campo_local.setCurrentIndex(4)

    assert modal.resultado().tipo_conexao is TipoConexaoImpressora.SERIAL
    modal._campo_local.setCurrentIndex(1)
    assert (modal.resultado().tipo_conexao, modal.resultado().nome_fila) == (
        TipoConexaoImpressora.WINDOWS,
        "EPSON TM-T20",
    )


def test_a_busca_nao_bloqueia_a_tela(abrir, qapp):
    """O spooler pode demorar a responder. Enquanto isso o cartão aparece, diz
    que está procurando e aceita digitação — e a lista entra quando chegar."""
    liberar = threading.Event()

    def listar_devagar() -> list[DestinoLocal]:
        liberar.wait(5)
        return list(DESTINOS)

    modal = abrir(listar=listar_devagar)
    inicio = time.monotonic()
    modal.show()
    qapp.processEvents()

    assert time.monotonic() - inicio < 1.0, "o show() esperou a lista do Windows"
    assert modal._campo_local.lineEdit().placeholderText() == "Procurando impressoras instaladas…"
    modal._campo_nome.setText("Caixa 02")
    assert modal._resumo.texto_completo().startswith("Caixa 02")

    liberar.set()
    assert _esperar(qapp, lambda: modal._estado_da_busca == "pronta")
    assert modal._campo_local.count() == 5
    assert modal._relogio.isActive() is False


def test_lista_que_estoura_vira_lista_vazia(abrir, qapp, caplog):
    def listar_quebrado() -> list[DestinoLocal]:
        raise RuntimeError("spooler parado")

    modal = abrir(listar=listar_quebrado)
    modal.show()

    assert _esperar(qapp, lambda: modal._estado_da_busca == "pronta")
    assert modal._campo_local.count() == 0
    assert "Nenhuma encontrada" in modal._campo_local.lineEdit().placeholderText()
    assert "spooler parado" in caplog.text


def test_busca_que_passa_do_teto_para_de_esperar(abrir, qapp, monkeypatch):
    monkeypatch.setattr(modulo, "TETO_DA_BUSCA_S", 0.05)
    liberar = threading.Event()
    modal = abrir(listar=lambda: liberar.wait(5) and [])
    modal.show()

    assert _esperar(qapp, lambda: modal._estado_da_busca == "esgotou")
    assert modal._relogio.isActive() is False
    assert "Nenhuma encontrada" in modal._campo_local.lineEdit().placeholderText()
    liberar.set()


def test_uma_busca_por_cartao(abrir, qapp):
    """O `showEvent` roda de novo quando a janela é restaurada."""
    chamadas: list[int] = []

    def listar() -> list[DestinoLocal]:
        chamadas.append(1)
        return []

    modal = abrir(listar=listar)
    modal.show()
    assert _esperar(qapp, lambda: modal._estado_da_busca == "pronta")
    modal.hide()
    modal.show()
    qapp.processEvents()

    assert chamadas == [1]


def test_fechar_no_meio_da_busca_nao_deixa_nada_para_tras(abrir, qapp, assentar):
    """A thread só enxerga `_BuscaDeDestinos`, que é Python puro: o cartão pode
    ser destruído enquanto o Windows não responde."""
    liberar = threading.Event()
    terminou = threading.Event()

    def listar_devagar() -> list[DestinoLocal]:
        liberar.wait(5)
        terminou.set()
        return list(DESTINOS)

    modal = abrir(listar=listar_devagar)
    modal.show()
    qapp.processEvents()
    relogio = modal._relogio

    modal.reject()
    assert relogio.isActive() is False
    assert modal._busca is None
    modal.deleteLater()
    assentar()
    liberar.set()
    assert terminou.wait(2)
    assentar()


# ---------------------------------------------------------------------------
# 8. Teclado
# ---------------------------------------------------------------------------


def test_enter_grava_quando_ha_o_que_gravar(abrir):
    modal = abrir(outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.result() == QDialog.DialogCode.Accepted


def test_enter_digitado_no_campo_usb_chega_ao_cartao(abrir, qapp):
    """O Return do `QLineEdit` de dentro do combo sobe até o diálogo."""
    modal = abrir(outra_padrao_ativa=True)
    modal._campo_nome.setText("Cozinha")
    _clicar(modal._cards[Conexao.LOCAL])
    modal._campo_local.setEditText("COM4")

    _tecla(modal._campo_local.lineEdit(), Qt.Key.Key_Return)

    assert modal.result() == QDialog.DialogCode.Accepted


def test_esc_fecha(abrir):
    modal = abrir()

    _tecla(modal, Qt.Key.Key_Escape)

    assert modal.result() == QDialog.DialogCode.Rejected


def test_abre_com_o_foco_no_nome_sem_selecionar(abrir, qapp):
    """O `QDialog` manda um FocusIn "de Tab" depois do `showEvent`, e o
    `QLineEdit` responde selecionando tudo — um nome que some na primeira tecla."""
    janela = QWidget()
    janela.show()
    modal = abrir(_impressora(), pai=janela)
    estado: dict[str, object] = {}

    def ler() -> None:
        # Espera o foco ASSENTAR, em vez de ler num instante fixo: o
        # `QDialog::setVisible` manda um `FocusIn` "de Tab" depois do
        # `showEvent` (§9.19), e sob carga esse evento chega depois dos 30ms do
        # disparo — o teste piscava vermelho na suíte cheia e passava sozinho.
        for _ in range(200):
            if modal._campo_nome.hasFocus():
                break
            qapp.processEvents()
        estado["foco"] = modal._campo_nome.hasFocus()
        estado["selecionado"] = modal._campo_nome.hasSelectedText()
        estado["cursor"] = modal._campo_nome.cursorPosition()
        modal.reject()

    QTimer.singleShot(30, ler)
    modal.exec()

    assert estado == {"foco": True, "selecionado": False, "cursor": len("Caixa 01")}


# ---------------------------------------------------------------------------
# 9. Nada espremido
# ---------------------------------------------------------------------------


@pytest.fixture
def com_fonte(qapp):
    """A fonte da marca registrada e o QSS aplicado — sem os dois, o offscreen
    mede outra coisa e o teste passaria sem ter olhado (§9.5, §9.12)."""
    caminho = Path(gestor_comercial.__file__).resolve().parents[2] / "resources" / "fonts" / "ArchivoBlack-Regular.ttf"
    if not caminho.exists():  # pragma: no cover
        pytest.skip(f"fonte da marca ausente em {caminho}")
    identificador = QFontDatabase.addApplicationFont(str(caminho))
    assert identificador != -1
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield controlador
    finally:
        controlador.alternar_para(False)
        QFontDatabase.removeApplicationFont(identificador)


@pytest.mark.parametrize("claro", [False, True])
@pytest.mark.parametrize("modo", ["novo", "editar"])
@pytest.mark.parametrize("conexao", list(Conexao))
@pytest.mark.parametrize("ativa", [True, False])
def test_nada_fica_espremido(qapp, com_fonte, claro, modo, conexao, ativa):
    """Nenhum rótulo ou botão desenhado menor do que pede, em nenhuma variante.

    `width() < sizeHint().width()` é o que o layout decide quando a soma não
    cabe: o Qt espreme o `QLabel` e o corte aparece. Fica de fora só o resumo,
    que encurta com reticências de propósito. E o cartão inteiro tem que caber
    nos 728px úteis de um monitor de 768px.

    Roda com a impressora DESLIGADA também (§9.22): o §9.19 só media "Impressora
    ativa", e "Impressora desativada" saía cortada no cartão de 600px sem
    nenhum teste ver.
    """
    com_fonte.alternar_para(claro)
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    impressora = _impressora(nome="Impressora do Balcão Norte") if modo == "editar" else None
    modal = ImpressoraDialog(modo, janela, impressora=impressora, nomes_existentes=[], listar_destinos=_listar)
    modal.show()
    assert _esperar(qapp, lambda: modal._estado_da_busca == "pronta")
    _clicar(modal._cards[conexao])
    if not ativa:
        _clicar(modal._situacao)
    modal._campo_nome.setText("C")  # o veredito mais largo que o nome produz
    for _ in range(3):
        qapp.processEvents()
    larguras_escala = [botao.width() for botao in modal._botoes_escala.values()]

    medidas = [
        w
        for w in modal.findChildren(QWidget)
        if isinstance(w, (QLabel, QPushButton))
        and not isinstance(w, RotuloComReticencias)
        and w.isVisibleTo(modal)
        and w.objectName().startswith("impDialog")
    ]
    apertadas = {
        f"{w.objectName()}:{w.text()!r}": (w.width(), w.sizeHint().width())
        for w in medidas
        if w.width() < w.sizeHint().width()
    }
    altura = modal.height()
    assert len(medidas) >= 20, f"premissa: só {len(medidas)} peças medidas"

    modal.reject()
    modal.deleteLater()
    janela.deleteLater()
    assert not apertadas, f"espremido (tem, pede): {apertadas}"
    assert altura <= 728, f"o cartão mede {altura}px de altura"
    # Os três segmentos da escala do mesmo tamanho, como os das colunas.
    assert max(larguras_escala) - min(larguras_escala) <= 1, larguras_escala


@pytest.mark.parametrize("largura", [ImpressoraDialog.LARGURA_CARTAO_PX, 680])
def test_desligar_a_impressora_nao_mexe_na_linha_da_escala(qapp, com_fonte, monkeypatch, largura):
    """O card de Situação pede, como MÍNIMO, a largura da frase mais longa nos
    dois estados. Sem isso, desligar redistribuía a linha e os botões de
    escala andavam debaixo do dedo (160 → 142px, medido a 680px).

    Roda também a 680px porque a 720 a divisão 5:4 da linha já dá à Situação
    292px, 1px acima da frase longa: ali o mínimo não é o que segura, e a
    checagem por mutação mostrou que o teste só a 720 passava sem ele. É com a
    folga acabando (outra fonte, outra escala do Windows, um cartão mais
    estreito) que o mínimo trabalha."""
    monkeypatch.setattr(ImpressoraDialog, "LARGURA_CARTAO_PX", largura)
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = ImpressoraDialog("novo", janela, nomes_existentes=[])
    modal.show()
    for _ in range(3):
        qapp.processEvents()

    def geometria() -> list[tuple[int, int]]:
        pecas = [*modal._botoes_escala.values(), modal._situacao]
        return [(peca.x(), peca.width()) for peca in pecas]

    ligada = geometria()
    _clicar(modal._situacao)
    for _ in range(3):
        qapp.processEvents()
    desligada = geometria()

    modal.reject()
    modal.deleteLater()
    janela.deleteLater()
    assert desligada == ligada


# O erro mais longo que o service devolve a este cartão (`_id_usb`, ~140
# caracteres): quebra em duas linhas no cartão de 720px.
_ERRO_MAIS_LONGO = (
    "Informe o Product ID da impressora USB (ex: 0x04b8). Ele aparece no "
    "Gerenciador de Dispositivos do Windows, em Detalhes > Ids de hardware."
)


def test_o_erro_do_service_nao_empurra_o_cartao_para_fora(qapp, com_fonte):
    """Com seis faixas no corpo, o erro do service (que quebra linha) é o que
    mais cresce o cartão. Tem que caber nos 728px úteis mesmo assim."""
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = ImpressoraDialog("novo", janela, nomes_existentes=[])
    modal.show()
    modal.mostrar_erro_servico(_ERRO_MAIS_LONGO)
    for _ in range(3):
        qapp.processEvents()
    rotulo = modal._erro_servico
    altura, linhas = modal.height(), rotulo.height() // rotulo.fontMetrics().lineSpacing()

    modal.reject()
    modal.deleteLater()
    janela.deleteLater()
    assert linhas >= 2, "premissa: o erro tem que quebrar linha para o teste valer"
    assert altura <= 728, f"o cartão mede {altura}px de altura com o erro aceso"


def test_o_erro_longo_aparece_inteiro_e_o_cartao_volta_ao_tamanho(qapp, com_fonte):
    """Dois defeitos do cartão do §9.19, medidos no HEAD antes de corrigir:

    * o rótulo do erro ficava com a altura de UMA linha (20px, pedia 48) e a
      mensagem longa saía cortada — justo a linha que existe para não cortar;
    * depois de o erro sumir, o cartão continuava da altura com o erro, com um
      vão em branco no lugar dele.
    """
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = ImpressoraDialog("novo", janela, nomes_existentes=[])
    modal.show()
    for _ in range(3):
        qapp.processEvents()
    sem_erro = modal.height()

    modal.mostrar_erro_servico(_ERRO_MAIS_LONGO)
    for _ in range(3):
        qapp.processEvents()
    rotulo = modal._erro_servico
    tem, pede = rotulo.height(), rotulo.heightForWidth(rotulo.width())
    com_erro = modal.height()

    modal._campo_nome.setText("Cozinha")  # qualquer mudança apaga o erro
    for _ in range(3):
        qapp.processEvents()
    depois = modal.height()

    modal.reject()
    modal.deleteLater()
    janela.deleteLater()
    assert tem >= pede, f"o erro tem {tem}px e pede {pede}px: sai cortado"
    assert com_erro > sem_erro
    assert depois == sem_erro, f"o cartão ficou com {depois}px, e sem o erro mede {sem_erro}px"


# ---------------------------------------------------------------------------
# 10. Ciclo de vida
# ---------------------------------------------------------------------------


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar):
    janela = QWidget()
    janela.show()

    for _ in range(5):
        modal = ImpressoraDialog.para_nova([], janela, ha_padrao_ativa=True)
        modal.show()
        qapp.processEvents()
        assert len(janela.findChildren(Backdrop)) == 1
        modal.reject()
        modal.deleteLater()
    assentar()

    assert janela.findChildren(Backdrop) == []


@pytest.mark.parametrize("modo", ["novo", "editar"])
def test_trinta_aberturas_nao_deixam_nada_preso(qapp, assentar, modo):
    """O caminho real do app: `exec()` com a busca rodando, fechado pelo botão."""
    pai = QWidget()
    assentar()
    widgets_antes = len(QApplication.allWidgets())

    for _ in range(30):
        modal = ImpressoraDialog(
            modo, pai, impressora=_impressora() if modo == "editar" else None, listar_destinos=_listar
        )
        QTimer.singleShot(20, modal.reject)
        modal.exec()
        modal.deleteLater()
        del modal
    assentar()

    assert pai.findChildren(ImpressoraDialog) == []
    assert len(QApplication.allWidgets()) == widgets_antes


def test_fechar_desliga_os_sinais(abrir):
    """O `unbind` explícito do pedido: depois de fechado, digitar, clicar num
    card ou no interruptor não mexe em mais nada."""
    modal = abrir()
    modal._campo_nome.setText("Caixa")
    cartao_rede = modal._cards[Conexao.REDE]
    botao_80 = modal._botoes_colunas[80]
    escala_4 = modal._botoes_escala[4]

    modal.reject()
    modal._campo_nome.setText("Outro nome")
    cartao_rede.clicado.emit()
    modal._situacao.clicado.emit()
    botao_80.clicked.emit()
    escala_4.clicked.emit()

    assert _rotulos(modal, "impDialogContador") == [f"5/{LIMITE_NOME}"]
    assert modal._conexao is Conexao.ARQUIVO
    assert modal._situacao.interruptor.ligado is True
    assert (modal._colunas, modal._escala) == (48, 2)
    assert modal._backdrop is None
    assert modal._cards == {} and modal._botoes_bobina == {}
    assert modal._botoes_colunas == {} and modal._botoes_escala == {}


def test_fechar_para_o_relogio_da_busca(abrir, qapp):
    liberar = threading.Event()
    modal = abrir(listar=lambda: liberar.wait(5) and [])
    modal.show()
    qapp.processEvents()
    assert modal._relogio.isActive() is True, "premissa: a busca estava em curso"

    modal.reject()

    assert modal._relogio.isActive() is False
    liberar.set()


def test_soltar_os_recursos_duas_vezes_e_silencioso(abrir):
    """Mede o AVISO: nesta versão do PySide6 o segundo `disconnect` devolve
    `False` e imprime `RuntimeWarning` em vez de levantar (§9.12)."""
    modal = abrir()
    modal.reject()

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        modal._soltar_recursos()

    assert [str(aviso.message) for aviso in avisos] == []


# ---------------------------------------------------------------------------
# 11. Glifos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "glifo",
    [GLIFO_IMPRESSORA, GLIFO_ARQUIVO_TEXTO, GLIFO_USB, GLIFO_REDE, GLIFO_SINAL, GLIFO_COLUNAS, GLIFO_LETRAS, GLIFO_NEGRITO],
)
def test_os_glifos_novos_sao_desenhados_dentro_da_grade(glifo):
    """Um nome de glifo sem ramo no `_caminho_do_glifo` desenha NADA, calado."""
    caminho = _caminho_do_glifo(glifo)
    caixa = caminho.boundingRect()

    assert not caminho.isEmpty()
    assert caixa.left() >= 0 and caixa.top() >= 0 and caixa.right() <= 24 and caixa.bottom() <= 24
