"""Mesa ocupada é vermelha — e só a mesa ocupada. Ver §9.5.

Até 2026-09-08 a mesa em atendimento era ciano, tratada como "estado normal,
nada a ver aqui". No balcão ela é o contrário disso: é onde está o dinheiro em
aberto do salão, e é o que o pai do Vitor precisa achar de relance numa grade
de sessenta mesas. Virou Vermelho Ferrari (`#DC2626`), o mesmo nos dois temas.

Uma troca de cor não costuma merecer teste. Esta merece por dois motivos que
não são estéticos:

1. **A cor tinha carona.** `mesa_ocupada_borda` era o ciano de três seletores
   que nada têm a ver com mesa — o badge de despesa do Caixa e o link de
   pendências das Impressoras pegavam a cor emprestada. Sem a varredura daqui,
   pintar a mesa de vermelho pintaria de vermelho a despesa do caixa também, e
   ninguém veria até alguém abrir aquela tela.

2. **O fundo tingido mostrou um corte que já existia.** Com o corpo do card na
   cor da superfície, ninguém via que o card ocupado media 110px de conteúdo e
   era desenhado com 96: as duas últimas linhas — o valor em aberto e o nome de
   quem atende — saíam cortadas ao meio pela borda. É o mesmo defeito do §9.1
   ("layout que não corta, espreme"), e cai justamente sobre o dado que a cor
   nova existe para destacar.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtGui import QFontDatabase, QPalette
from PySide6.QtWidgets import QLabel, QWidget

import gestor_comercial
from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.ui.theme import tokens
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.theme.qss_app import construir_qss_app
from gestor_comercial.ui.views.mesas_view import MesasView, _CartaoMesa

VERMELHO_FERRARI = "#DC2626"
# O ciano e o âmbar que a mesa ocupada usava antes, um por tema. Estão aqui
# escritos à mão de propósito: é o que NÃO pode voltar.
CORES_ANTIGAS = ("#22d3ee", "#f59e0b")
SENTINELA = "#010203"

PALETAS = {"escuro": tokens.TEMA_ESCURO, "claro": tokens.TEMA_CLARO}


@pytest.fixture
def tema(qapp):
    """Controlador com o QSS global aplicado, e o tema escuro de volta no fim."""
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield controlador
    finally:
        controlador.alternar_para(False)


# Mesas suficientes para a grade PASSAR da altura do container e o layout
# precisar decidir o que fazer com a sobra. Com uma mesa só, o card ganha toda
# a folga do painel e o corte não acontece — o teste passaria verde sem ter
# olhado o defeito, que é justamente o que o §9.2 manda conferir. O food truck
# tem sessenta; vinte e quatro (três fileiras de oito) já é mais que o dobro do
# que cabe na altura usada aqui.
MESAS_DO_SALAO = 24
ALTURA_DO_PAINEL_PX = 420


@pytest.fixture
def com_metrica_de_texto(qapp):
    """Dá ao Qt uma fonte de verdade antes de a tela ser montada.

    A plataforma `offscreen` sobe com o banco de fontes **vazio**, e sem fonte
    todo texto mede quase nada: um defeito de ALTURA de conteúdo simplesmente
    não acontece aqui, e um teste que o cobrasse passaria verde sem ter olhado
    (o card ocupado mede 93px sem fonte contra 110px com). É o mesmo motivo por
    que `tools/comparar_telas.py` carrega fontes na mão.

    A fonte é a que o **próprio app** registra no boot (`main._registrar_fonte_
    marca`) e que vive no repositório — não uma do sistema, que existiria só
    nesta máquina. Sai do banco no fim para não mudar a medida dos testes
    seguintes.
    """
    caminho = Path(gestor_comercial.__file__).resolve().parents[2] / "resources" / "fonts" / "ArchivoBlack-Regular.ttf"
    if not caminho.exists():  # pragma: no cover - só num checkout incompleto
        pytest.skip(f"fonte da marca ausente em {caminho}")
    identificador = QFontDatabase.addApplicationFont(str(caminho))
    assert identificador != -1, "o Qt recusou a fonte da marca"
    try:
        yield
    finally:
        QFontDatabase.removeApplicationFont(identificador)


@pytest.fixture
def salao(qapp, com_metrica_de_texto, comandas, gerente, produto, caixa_aberto, uow):
    """A tela de Mesas com uma mesa ocupada de verdade — comanda aberta e item
    lançado, para o card ter as quatro linhas (número, tag, valor, atendente)."""
    mesas = [uow.mesas.salvar(Mesa(numero=numero)) for numero in range(1, MESAS_DO_SALAO + 1)]
    comanda = comandas.abrir_por_mesa(mesas[0].id)
    comandas.lancar_item(comanda.id, produto.id, 2)
    view = MesasView(comandas)
    view.resize(1030, ALTURA_DO_PAINEL_PX)
    view.show()
    view.carregar_mesas()
    # Várias voltas: a grade mora numa `QScrollArea`, e a área só decide entre
    # esticar o conteúdo e mostrar a barra de rolagem depois de o layout de
    # dentro se acomodar. Com uma volta só, a medida sai de um estado
    # intermediário — e é dela que sairia um teste que acusa aperto onde não há.
    for _ in range(10):
        qapp.processEvents()
    return view


def _cor(widget: QWidget) -> str:
    """A cor com que o widget vai desenhar o texto, depois do QSS aplicado."""
    return widget.palette().color(QPalette.ColorRole.WindowText).name()


def _por_nome(raiz: QWidget, nome: str) -> QLabel:
    achados = [w for w in raiz.findChildren(QLabel) if w.objectName() == nome]
    assert achados, f"nenhum QLabel #{nome} na tela"
    return achados[0]


def _cartao_ocupado(view: MesasView) -> _CartaoMesa:
    ocupados = [c for c in view.findChildren(_CartaoMesa) if c.property("ocupada") == "true"]
    assert ocupados, "o teste precisa de uma mesa ocupada na grade para valer"
    return ocupados[0]


def _regras(qss: str) -> list[tuple[str, str]]:
    """(seletor, corpo) de cada regra do QSS já interpolado."""
    sem_comentarios = re.sub(r"/\*.*?\*/", "", qss, flags=re.S)
    regras = []
    for bloco in sem_comentarios.split("}"):
        cabeca, chave, corpo = bloco.partition("{")
        if chave:
            regras.append((" ".join(cabeca.split()), corpo))
    return regras


def _seletores_que_leem(chave: str) -> list[str]:
    """Quais regras do QSS consomem um token — descoberto trocando o valor dele
    por uma sentinela e procurando a sentinela no resultado.

    Mais confiável que ler o template de `qss_app.py` com expressão regular: o
    que se quer saber é o que o QSS **montado** faz, e é exatamente isso que a
    sentinela responde.
    """
    paleta = dict(tokens.TEMA_ESCURO)
    paleta[chave] = SENTINELA
    return [seletor for seletor, corpo in _regras(construir_qss_app(paleta)) if SENTINELA in corpo]


# ---------------------------------------------------------------------------
# A cor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome", sorted(PALETAS))
def test_o_vermelho_ferrari_e_o_mesmo_nos_dois_temas(nome):
    """É o único token de status que não muda entre Claro e Escuro, e é de
    propósito: quem procura a mesa cheia de longe procura a mesma cor."""
    assert PALETAS[nome]["mesa_ocupada_borda"] == VERMELHO_FERRARI


@pytest.mark.parametrize("nome", sorted(PALETAS))
def test_nenhum_token_de_mesa_ocupada_guarda_a_cor_antiga(nome):
    paleta = PALETAS[nome]
    antigas = {
        chave: valor
        for chave, valor in paleta.items()
        if chave.startswith("mesa_ocupada_") and valor.lower() in CORES_ANTIGAS
    }
    assert antigas == {}, f"tema {nome} ainda tem o ciano/âmbar de antes: {antigas}"


# ---------------------------------------------------------------------------
# A propagação nas telas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("claro", [False, True], ids=["escuro", "claro"])
def test_o_card_da_mesa_ocupada_pinta_numero_valor_e_tag(qapp, tema, salao, claro):
    """O que a spec chama de "destacar o número da mesa e o valor parcial em
    aberto": os dois deixam de usar `texto` e passam a usar a cor própria do
    card ocupado — sem isso, no tema claro eles sairiam quase pretos sobre o
    pastel avermelhado."""
    tema.alternar_para(claro)
    qapp.processEvents()
    paleta = tema.tokens_atuais
    cartao = _cartao_ocupado(salao)

    assert _cor(_por_nome(cartao, "mesaCartaoNumero")) == paleta["mesa_ocupada_texto"].lower()
    assert _cor(_por_nome(cartao, "mesaCartaoValor")) == paleta["mesa_ocupada_texto"].lower()
    assert _cor(_por_nome(cartao, "mesaCartaoTag")) == paleta["mesa_ocupada_tag"].lower()


@pytest.mark.parametrize("claro", [False, True], ids=["escuro", "claro"])
def test_a_legenda_e_o_painel_de_comandas_seguem_a_mesma_cor(qapp, tema, salao, claro):
    """Os dois pontinhos que a spec pede: o `● OCUPADA` do resumo do salão e o
    da comanda listada no painel da direita. Eles leem o mesmo token do card, e
    é isso que impede a legenda de continuar ciano depois de o card virar
    vermelho."""
    tema.alternar_para(claro)
    qapp.processEvents()
    esperado = tema.tokens_atuais["mesa_ocupada_borda"].lower()

    assert _cor(_por_nome(salao, "painelMiniStatDotOcupada")) == esperado
    assert _cor(_por_nome(salao, "comandaListaPontoOcupada")) == esperado


def test_a_mesa_fechando_continua_ambar(qapp, tema, salao):
    """"Fechando" (comanda em conferência) NÃO entrou nesta mudança: continua no
    âmbar de sempre. Se um dia ela virar vermelha também, os dois estados param
    de se distinguir na grade — que é o que a cor existe para fazer."""
    assert tema.tokens_atuais["mesa_fechando_borda"] != VERMELHO_FERRARI
    assert _cor(_por_nome(salao, "painelMiniStatDotFechando")) == tema.tokens_atuais[
        "mesa_fechando_borda"
    ].lower()


# ---------------------------------------------------------------------------
# A carona — o que NÃO podia virar vermelho junto
# ---------------------------------------------------------------------------


def test_a_cor_da_mesa_ocupada_so_e_lida_por_seletor_de_mesa():
    """A varredura que separa "a cor da mesa ocupada" de "aquele ciano ali".

    O badge de despesa do Caixa e o link de pendências das Impressoras liam
    `mesa_ocupada_borda` porque queriam o ciano, não porque falam de mesa. Hoje
    leem `ciano_metrica`. Se alguém recolar o empréstimo, a próxima mudança de
    cor de mesa arrasta junto uma tela que não tem nada com isso — e é este
    teste que reprova antes.
    """
    fora_do_assunto = [
        seletor
        for seletor in _seletores_que_leem("mesa_ocupada_borda")
        if not re.search(r"mesa|ocupada", seletor, re.IGNORECASE)
    ]

    assert fora_do_assunto == [], (
        "seletores que não falam de mesa lendo a cor da mesa ocupada:\n  "
        + "\n  ".join(fora_do_assunto)
    )


def test_o_badge_de_despesa_e_o_link_de_pendencias_continuam_cianos():
    """O outro lado do teste acima, nomeando os dois que tinham a carona: eles
    não podem ter ficado sem cor nenhuma no caminho."""
    cianos = _seletores_que_leem("ciano_metrica")

    assert any("despesa" in seletor for seletor in cianos), cianos
    assert any("impressorasPendentesLink" in seletor for seletor in cianos), cianos


# ---------------------------------------------------------------------------
# O corte que o fundo tingido revelou
# ---------------------------------------------------------------------------


def test_nenhum_card_de_mesa_e_desenhado_menor_que_o_proprio_conteudo(qapp, salao):
    """O invariável, e não o número: o card ocupado tem quatro linhas contra as
    duas da mesa livre, e enquanto o piso de altura era 96px ele era desenhado
    com 96 medindo 110 — o valor em aberto saía cortado ao meio.

    Medir contra `sizeHint()` em vez de contra `ALTURA_PX` é o que faz este
    teste continuar valendo se a fonte do sistema ou um `font-size` do QSS
    mudar: quem avisa passa a ser a suíte, e não o balcão.
    """
    apertados = [
        f"mesa {c.findChildren(QLabel)[0].text()}: {c.height()}px < {c.sizeHint().height()}px"
        for c in salao.findChildren(_CartaoMesa)
        if c.height() < c.sizeHint().height()
    ]

    assert apertados == [], "card de mesa menor que o conteúdo:\n  " + "\n  ".join(apertados)


def test_o_valor_em_aberto_aparece_inteiro_no_card_ocupado(qapp, salao):
    """A consequência do teste acima, escrita como o pai do Vitor a veria: o
    card da mesa 1 tem que mostrar o total da comanda, e não meio total.

    A medida é a mesma de `test_telas_cabem_na_tela.py` — rótulo menor que o
    próprio `sizeHint` é exatamente como um texto sai cortado ao meio —, e não
    a geometria dentro do card: o Qt recorta o rótulo junto com o pai, então
    ele "cabe" mesmo quando não cabe.
    """
    valor = _por_nome(_cartao_ocupado(salao), "mesaCartaoValor")

    assert valor.text() == "R$ 20,00"
    assert valor.height() >= valor.sizeHint().height(), (
        f"o valor está com {valor.height()}px de {valor.sizeHint().height()}px"
    )


def test_a_grade_mostra_o_atendente_da_mesa_ocupada(qapp, salao, gerente):
    """A quarta linha do card. Este é o teste de CONTEÚDO da fixture — quem
    reprova o piso de altura antigo são os dois acima; aqui se garante que o
    card ocupado realmente tem as quatro linhas, sem as quais aqueles dois
    mediriam um card curto e passariam sem ter olhado nada."""
    nome = _por_nome(_cartao_ocupado(salao), "mesaCartaoNome")

    assert nome.text() == gerente.nome
    assert nome.height() >= nome.sizeHint().height(), (
        f"o atendente está com {nome.height()}px de {nome.sizeHint().height()}px"
    )


def test_o_total_do_salao_bate_com_a_comanda_aberta(qapp, salao):
    """Guarda da fixture: sem item lançado o card não teria valor nenhum e os
    testes de corte passariam sem ter olhado nada."""
    assert salao._label_total_aberto.text() == "R$ 20,00"
    assert sum(r.valor for r in salao._resumos) == Decimal("20.00")
