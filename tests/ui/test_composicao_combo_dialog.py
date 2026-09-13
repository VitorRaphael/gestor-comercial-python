"""O cartão "Composição do combo": linhas, stepper, remoção, adição e limpeza. §9.15.

Substituiu uma `QTableWidget` de duas colunas em que mudar a quantidade era
remover e associar de novo. O que estes testes seguram, em ordem:

1. **o que a linha diz** — nome e CATEGORIA do componente (a escolha do Vitor
   no lugar do "Produto principal/Adicional" do mockup, que o banco não tem), e
   o visto âmbar só na linha selecionada;
2. **o stepper grava antes de mostrar** — o número na tela é o do banco, a
   recusa do service não mexe nele, e a lista não é remontada a cada clique;
3. **a remoção** — tira do banco e da tela, destrói a linha na hora, passa a
   seleção para quem ocupou o lugar, e o último componente desfaz o combo;
4. **a adição** — abre o cartão "Adicionar item" no modo componente, sem o que
   o service recusaria de qualquer jeito, e a lista volta com o novo item;
5. **o teclado** — setas, Delete/Backspace e Esc;
6. **o rodapé cabe e a barra de rolagem não desloca nada** — com a fonte da
   marca, que é onde o aperto aparece;
7. **o ciclo de vida** — o RNF do Celeron: escurecedor solto, sinais
   desligados, linhas removidas destruídas, nada preso depois de trinta idas e
   voltas, e o escurecedor de um cartão sobre outro acompanhando os cantos.

Os diálogos abrem com o `CardapioService` de verdade, sobre o banco de memória.
Um dublê provaria só que o teste sabe chamar o service.
"""

from __future__ import annotations

import warnings
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFontDatabase, QImage, QKeyEvent, QPainter, QRegion
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QWidget

import gestor_comercial
import gestor_comercial.ui.widgets.composicao_combo_dialog as modulo
from gestor_comercial.services.exceptions import AcessoNegadoError
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.adicionar_item_dialog import AdicionarItemDialog
from gestor_comercial.ui.widgets.cartao_modal import RAIO_CARTAO_PX, Backdrop
from gestor_comercial.ui.widgets.composicao_combo_dialog import (
    QUANTIDADE_MAXIMA,
    ComposicaoComboDialog,
    LinhaDeComponente,
    LinhaDoCombo,
    texto_do_status,
)
from gestor_comercial.ui.widgets.modais import descartar_modal

from tests.conftest import PIN_ATENDENTE

# ---------------------------------------------------------------------------
# Cenário
# ---------------------------------------------------------------------------


@pytest.fixture
def cenario(cardapio, gerente):
    """Um combo com Batata (Porções, 1) e Coca (Bebidas, 2), e o resto do cardápio
    que o cartão de adição teria de filtrar: um produto livre, outro combo e o
    próprio combo."""
    porcoes = cardapio.criar_categoria("Porções")
    bebidas = cardapio.criar_categoria("Bebidas")
    combos = cardapio.criar_categoria("Combos")
    batata = cardapio.criar_produto("Batata P Simples", Decimal("12.00"), porcoes.id)
    coca = cardapio.criar_produto("Coca Lata", Decimal("6.00"), bebidas.id)
    guaracamp = cardapio.criar_produto("Guaracamp", Decimal("5.00"), bebidas.id)
    combo = cardapio.criar_produto("Combo Fritas + Coca", Decimal("15.00"), combos.id)
    cardapio.associar_componente(combo.id, batata.id, 1)
    cardapio.associar_componente(combo.id, coca.id, 2)
    outro = cardapio.criar_produto("Combo Casal", Decimal("40.00"), combos.id)
    cardapio.associar_componente(outro.id, guaracamp.id, 2)
    return {
        "combo": combo,
        "outro": outro,
        "batata": batata,
        "coca": coca,
        "guaracamp": guaracamp,
        "combos": combos,
    }


@pytest.fixture
def abrir(qapp, cardapio, cenario):
    """Monta o cartão sem `exec()` — e o descarta no fim do teste."""
    criados: list[ComposicaoComboDialog] = []

    def _abrir(produto=None, pai=None):
        alvo = produto or cenario["combo"]
        modal = ComposicaoComboDialog(cardapio, alvo.id, alvo.nome, pai)
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        descartar_modal(modal)


def _tecla(modal: QDialog, tecla: Qt.Key) -> None:
    modal.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


def _nomes(modal: ComposicaoComboDialog) -> list[str]:
    return [linha.linha.nome for linha in modal._linhas]


def _selecionada(modal: ComposicaoComboDialog) -> str | None:
    linha = modal.linha_selecionada()
    return None if linha is None else linha.linha.nome


def _rotulo(pai: QWidget, nome_do_objeto: str) -> str:
    rotulo = next(r for r in pai.findChildren(QLabel) if r.objectName() == nome_do_objeto)
    completo = getattr(rotulo, "texto_completo", None)
    return completo() if completo else rotulo.text()


def _quantidades_no_banco(cardapio, combo) -> list[tuple[str, int]]:
    return [(c.produto.nome, c.quantidade) for c in cardapio.listar_componentes(combo.id)]


# ---------------------------------------------------------------------------
# 1. O que a linha diz
# ---------------------------------------------------------------------------


def test_cada_componente_vira_uma_linha_com_nome_categoria_e_quantidade(abrir):
    """O subtítulo é a CATEGORIA real do componente: o "Produto principal" do
    mockup não existe em `combo_itens`, e o Vitor escolheu não inventá-lo."""
    modal = abrir()

    linhas = [
        (w.linha.nome, _rotulo(w, "comboLinhaCategoria"), w._valor.text()) for w in modal._linhas
    ]

    assert linhas == [("Batata P Simples", "Porções", "1"), ("Coca Lata", "Bebidas", "2")]


def test_o_cabecalho_diz_a_secao_e_o_nome_do_combo(abrir):
    modal = abrir()

    assert _rotulo(modal, "comboDialogSecao") == "COMPOSIÇÃO DO COMBO"
    assert _rotulo(modal, "comboDialogTitulo") == "Combo Fritas + Coca"
    assert _rotulo(modal, "comboDialogContexto") == "ALTERAÇÕES APLICADAS NESTE COMBO"


def test_a_primeira_linha_nasce_selecionada_e_so_ela_tem_o_visto(abrir):
    """O selo âmbar marca a linha que o Remover vai tirar — e é UMA."""
    modal = abrir()

    assert [w._selo.selecionado() for w in modal._linhas] == [True, False]
    assert [w.property("selecionada") for w in modal._linhas] == [True, False]
    assert modal._botao_remover.isEnabled() is True


def test_clicar_numa_linha_move_o_visto_para_ela(qapp, abrir):
    modal = abrir()
    segunda = modal._linhas[1]

    segunda.clicada.emit(segunda.linha.combo_item_id)

    assert [w._selo.selecionado() for w in modal._linhas] == [False, True]


@pytest.mark.parametrize(
    ("total", "esperado"),
    [
        (0, "NENHUM COMPONENTE · ADICIONE O PRIMEIRO"),
        (1, "1 COMPONENTE · SELECIONE UMA LINHA PARA REMOVER"),
        (2, "2 COMPONENTES · SELECIONE UMA LINHA PARA REMOVER"),
    ],
)
def test_o_status_conta_os_componentes(total, esperado):
    assert texto_do_status(total) == esperado


def test_produto_sem_componentes_mostra_o_aviso_e_desliga_o_remover(abrir, cenario):
    modal = abrir(produto=cenario["guaracamp"])

    assert modal._linhas == []
    assert modal._vazio.isHidden() is False
    assert modal._botao_remover.isEnabled() is False
    assert _rotulo(modal, "comboDialogStatus") == "NENHUM COMPONENTE · ADICIONE O PRIMEIRO"


# ---------------------------------------------------------------------------
# 2. O stepper
# ---------------------------------------------------------------------------


def test_o_mais_grava_no_banco_e_troca_so_o_numero(abrir, cardapio, cenario):
    """O clique real no botão: sinal da linha → diálogo → service → número."""
    modal = abrir()
    batata = modal._linhas[0]

    batata._botao_mais.click()

    assert batata._valor.text() == "2"
    assert _quantidades_no_banco(cardapio, cenario["combo"]) == [
        ("Batata P Simples", 2),
        ("Coca Lata", 2),
    ]
    assert modal.alterou is True


def test_o_stepper_nao_remonta_a_lista(abrir, cardapio, monkeypatch):
    """"Sem flickering": a mesma linha continua na tela, e o banco não é relido."""
    modal = abrir()
    antes = list(modal._linhas)
    leituras: list[int] = []
    original = cardapio.listar_componentes
    monkeypatch.setattr(
        cardapio, "listar_componentes", lambda combo_id: leituras.append(combo_id) or original(combo_id)
    )

    modal._linhas[1]._botao_menos.click()
    modal._linhas[1]._botao_mais.click()

    assert modal._linhas == antes
    assert all(a is b for a, b in zip(modal._linhas, antes, strict=True))
    assert leituras == []


def test_o_menos_para_no_um(abrir, cardapio, monkeypatch):
    """Componente com zero unidades não existe — e o botão desliga antes de o
    service precisar recusar."""
    modal = abrir()
    batata = modal._linhas[0]
    chamadas: list[tuple[int, int]] = []
    monkeypatch.setattr(
        cardapio, "alterar_quantidade_componente", lambda *a: chamadas.append(a)
    )

    assert batata._botao_menos.isEnabled() is False
    modal._ao_pedir_passo(batata.linha.combo_item_id, -1)

    assert chamadas == []
    assert batata._valor.text() == "1"


def test_o_mais_para_no_teto(abrir, cardapio, cenario, monkeypatch):
    modal = abrir()
    coca = modal._linhas[1]
    cardapio.alterar_quantidade_componente(coca.linha.combo_item_id, QUANTIDADE_MAXIMA)
    coca.definir_quantidade(QUANTIDADE_MAXIMA)
    chamadas: list[tuple[int, int]] = []
    monkeypatch.setattr(
        cardapio, "alterar_quantidade_componente", lambda *a: chamadas.append(a)
    )

    assert coca._botao_mais.isEnabled() is False
    modal._ao_pedir_passo(coca.linha.combo_item_id, 1)

    assert chamadas == []
    assert coca._valor.text() == str(QUANTIDADE_MAXIMA)


def test_o_teto_do_stepper_e_o_mesmo_do_cartao_de_adicao():
    """As duas portas de entrada da quantidade de um componente."""
    from gestor_comercial.ui.widgets.adicionar_item_dialog import MODOS, ModoDeLancamento

    assert QUANTIDADE_MAXIMA == MODOS[ModoDeLancamento.COMPONENTE].quantidade_maxima == 99


def test_mexer_no_stepper_seleciona_a_linha(abrir):
    """A última linha tocada é a que o Remover tira — e não outra que ficou
    âmbar lá atrás."""
    modal = abrir()

    modal._linhas[1]._botao_menos.click()

    assert _selecionada(modal) == "Coca Lata"


def test_a_recusa_do_service_nao_mexe_no_numero_e_diz_o_motivo(abrir, cardapio, cenario, auth, atendente):
    modal = abrir()
    batata = modal._linhas[0]
    auth.login_como(atendente.id, PIN_ATENDENTE)

    batata._botao_mais.click()

    assert batata._valor.text() == "1"
    assert modal._status.property("estado") == "erro"
    assert modal.alterou is False
    assert _quantidades_no_banco(cardapio, cenario["combo"])[0] == ("Batata P Simples", 1)


# ---------------------------------------------------------------------------
# 3. Remover
# ---------------------------------------------------------------------------


def test_remover_tira_a_selecionada_do_banco_e_da_tela(abrir, cardapio, cenario):
    modal = abrir()

    modal._botao_remover.click()

    assert _nomes(modal) == ["Coca Lata"]
    assert _quantidades_no_banco(cardapio, cenario["combo"]) == [("Coca Lata", 2)]
    assert modal.alterou is True


def test_a_selecao_passa_para_quem_ocupou_o_lugar(abrir):
    """O comportamento da tabela antiga: dá para tirar vários seguidos."""
    modal = abrir()

    modal._botao_remover.click()

    assert _selecionada(modal) == "Coca Lata"
    assert modal._botao_remover.isEnabled() is True


def test_remover_a_do_meio_seleciona_a_de_baixo(abrir, cardapio, cenario):
    """Com duas linhas "quem ocupou o lugar" e "a primeira" coincidem, e a regra
    não é testada de verdade — foi a mutação que mostrou. Com três, remover a do
    meio tem de selecionar a que subiu para o meio, não a do topo."""
    cardapio.associar_componente(cenario["combo"].id, cenario["guaracamp"].id, 1)
    modal = abrir()
    modal._ao_clicar_linha(modal._linhas[1].linha.combo_item_id)

    modal._botao_remover.click()

    assert _nomes(modal) == ["Batata P Simples", "Guaracamp"]
    assert _selecionada(modal) == "Guaracamp"


def test_remover_a_ultima_linha_seleciona_a_de_cima(abrir):
    modal = abrir()
    modal._ao_clicar_linha(modal._linhas[1].linha.combo_item_id)

    modal._botao_remover.click()

    assert _selecionada(modal) == "Batata P Simples"


def test_remover_o_ultimo_componente_desfaz_o_combo_e_mostra_o_aviso(abrir, cardapio, cenario):
    """Quem desfaz é o service, como sempre foi; a tela só tem que contar a
    verdade depois."""
    modal = abrir()

    modal._botao_remover.click()
    modal._botao_remover.click()

    assert modal._linhas == []
    assert modal._vazio.isHidden() is False
    assert modal._botao_remover.isEnabled() is False
    assert cardapio.buscar_produto(cenario["combo"].id).is_combo is False


def test_a_recusa_do_service_ao_remover_mantem_a_linha(abrir, cardapio, cenario, auth, atendente):
    modal = abrir()
    auth.login_como(atendente.id, PIN_ATENDENTE)

    modal._botao_remover.click()

    assert _nomes(modal) == ["Batata P Simples", "Coca Lata"]
    assert modal._status.property("estado") == "erro"


def test_a_linha_removida_sai_do_dialogo_na_hora_e_e_destruida(qapp, assentar, abrir):
    """Duas medidas, porque são duas garantias.

    ANTES de o laço de eventos girar: a linha já não é filha do diálogo. Sem o
    `setParent(None)` ela continuaria lá até o `deleteLater` ser processado, e
    qualquer contagem nesse meio-tempo a veria. A primeira versão deste teste só
    olhava depois de `assentar()` — quando o `deleteLater` já a tinha destruído
    de qualquer jeito — e a mutação que tirava o `setParent` passava.

    DEPOIS: o objeto C++ não existe mais.
    """
    from shiboken6 import isValid

    modal = abrir()
    removida = modal._linhas[0]

    modal._botao_remover.click()

    assert removida not in modal.findChildren(LinhaDoCombo)
    assert removida.parent() is None
    assentar()
    assert not isValid(removida)
    assert len(modal.findChildren(LinhaDoCombo)) == 1


def test_remover_sem_selecao_nao_faz_nada(abrir, cardapio, monkeypatch):
    modal = abrir()
    modal._selecionar(None)
    chamadas: list[int] = []
    monkeypatch.setattr(cardapio, "remover_componente", chamadas.append)

    modal._remover_selecionada()

    assert chamadas == []
    assert modal._botao_remover.isEnabled() is False


# ---------------------------------------------------------------------------
# 4. Adicionar
# ---------------------------------------------------------------------------


@pytest.fixture
def interceptar_adicao(monkeypatch):
    """Troca o `executar_modal` do módulo por um roteiro que opera o cartão de
    adição como o gerente: escolhe o produto, a quantidade e lança."""
    vistos: list[dict] = []

    def _instalar(produto: str | None = None, quantidade: int = 1):
        def falso(modal):
            linhas = [
                modal._lista.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(modal._lista.count())
            ]
            registro = {"modal": type(modal), "nomes": [l.nome for l in linhas]}
            if produto is not None:
                modal._lista.setCurrentRow(registro["nomes"].index(produto))
                modal._definir_quantidade(quantidade)
                modal._lancar_selecionado()
                registro["aviso"] = modal._label_aviso.text()
                registro["estado"] = modal._label_aviso.property("estado")
            registro["titulo"] = modal.windowTitle()
            registro["observacao"] = modal._campo_observacao
            vistos.append(registro)
            modal.reject()
            descartar_modal(modal)
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(modulo, "executar_modal", falso)
        return vistos

    return _instalar


def test_adicionar_abre_o_cartao_no_modo_componente(abrir, interceptar_adicao):
    vistos = interceptar_adicao()
    modal = abrir()

    modal._botao_adicionar.click()

    assert vistos[0]["modal"] is AdicionarItemDialog
    assert vistos[0]["titulo"] == "Adicionar componente"
    assert vistos[0]["observacao"] is None


def test_o_cartao_de_adicao_nao_oferece_o_que_o_service_recusaria(abrir, interceptar_adicao):
    """Fora da lista, de antemão: o próprio combo, quem já é combo e quem já está
    na composição. Sobra o produto livre — que ser componente de OUTRO combo não
    impede."""
    vistos = interceptar_adicao()
    modal = abrir()

    modal._botao_adicionar.click()

    assert vistos[0]["nomes"] == ["Guaracamp"]


def test_produto_virando_combo_nao_se_oferece_como_componente_de_si_mesmo(
    abrir, cardapio, cenario, interceptar_adicao
):
    """O produto que ainda NÃO tem componente não é `is_combo` — o filtro de
    combos não o tira da lista, e só o filtro do próprio id o tira. No cenário
    principal o combo já tem itens e os dois filtros se mascaram; foi a mutação
    que mostrou que este caso não estava coberto."""
    vistos = interceptar_adicao()
    novo = cardapio.criar_produto("Combo Novo", Decimal("20.00"), cenario["combos"].id)
    modal = abrir(produto=novo)

    modal._botao_adicionar.click()

    assert "Combo Novo" not in vistos[0]["nomes"]
    assert {"Batata P Simples", "Coca Lata", "Guaracamp"} <= set(vistos[0]["nomes"])


def test_o_que_foi_adicionado_aparece_ao_voltar(abrir, cardapio, cenario, interceptar_adicao):
    interceptar_adicao(produto="Guaracamp", quantidade=3)
    modal = abrir()
    antes = list(modal._linhas)

    modal._botao_adicionar.click()

    assert [(w.linha.nome, w.linha.quantidade) for w in modal._linhas] == [
        ("Batata P Simples", 1),
        ("Coca Lata", 2),
        ("Guaracamp", 3),
    ]
    # As duas que ficaram são as MESMAS linhas: a recarga não remonta ninguém.
    assert modal._linhas[0] is antes[0] and modal._linhas[1] is antes[1]
    assert _quantidades_no_banco(cardapio, cenario["combo"])[-1] == ("Guaracamp", 3)
    assert modal.alterou is True
    assert _rotulo(modal, "comboDialogStatus").startswith("3 COMPONENTES")


def test_adicionar_avisa_no_proprio_cartao_e_nao_fecha(abrir, interceptar_adicao):
    vistos = interceptar_adicao(produto="Guaracamp")
    modal = abrir()

    modal._botao_adicionar.click()

    assert vistos[0]["estado"] == "sucesso"
    assert vistos[0]["aviso"] == "1× GUARACAMP NO COMBO"


def test_a_recusa_do_service_na_adicao_fica_no_cartao_de_adicao(
    abrir, cardapio, cenario, interceptar_adicao, monkeypatch
):
    """O erro sobe do `_associar` para o cartão de adição, que o mostra sem
    fechar — é o caminho de erro que o modo comanda já tinha."""
    vistos = interceptar_adicao(produto="Guaracamp")
    modal = abrir()

    def recusar(*_args):
        raise AcessoNegadoError("Somente gerente.")

    monkeypatch.setattr(cardapio, "associar_componente", recusar)
    modal._botao_adicionar.click()

    assert vistos[0]["estado"] == "erro"
    assert _nomes(modal) == ["Batata P Simples", "Coca Lata"]
    assert modal.alterou is False


def test_sem_candidato_avisa_e_nao_abre_nada(abrir, cardapio, cenario, interceptar_adicao):
    vistos = interceptar_adicao()
    cardapio.desativar_produto(cenario["guaracamp"].id)
    modal = abrir()

    modal._botao_adicionar.click()

    assert vistos == []
    assert modal._status.property("estado") == "erro"
    assert "Não há outro produto" in _rotulo(modal, "comboDialogStatus")


def test_o_cartao_de_adicao_de_verdade_abre_e_nao_sobra(qapp, assentar, abrir):
    """O caminho real, com `exec()`: o cartão de cima é filho do de baixo e tem
    que ir embora com o `deleteLater` do `executar_modal`."""
    modal = abrir()

    def fechar_o_de_cima():
        for filho in modal.findChildren(AdicionarItemDialog):
            if filho.isVisible():
                filho.reject()

    for _ in range(5):
        QTimer.singleShot(0, fechar_o_de_cima)
        modal._botao_adicionar.click()
    assentar()

    assert modal.findChildren(AdicionarItemDialog) == []
    assert modal.findChildren(Backdrop) == []


# ---------------------------------------------------------------------------
# 5. Teclado
# ---------------------------------------------------------------------------


def test_as_setas_trocam_a_linha_sem_passar_das_pontas(abrir):
    modal = abrir()

    _tecla(modal, Qt.Key.Key_Down)
    assert _selecionada(modal) == "Coca Lata"
    _tecla(modal, Qt.Key.Key_Down)
    assert _selecionada(modal) == "Coca Lata"
    _tecla(modal, Qt.Key.Key_Up)
    _tecla(modal, Qt.Key.Key_Up)
    assert _selecionada(modal) == "Batata P Simples"


@pytest.mark.parametrize("tecla", [Qt.Key.Key_Delete, Qt.Key.Key_Backspace])
def test_delete_e_backspace_removem_a_selecionada(abrir, cardapio, cenario, tecla):
    modal = abrir()
    _tecla(modal, Qt.Key.Key_Down)

    _tecla(modal, tecla)

    assert _nomes(modal) == ["Batata P Simples"]
    assert _quantidades_no_banco(cardapio, cenario["combo"]) == [("Batata P Simples", 1)]


def test_esc_fecha(qapp, abrir):
    modal = abrir()

    _tecla(modal, Qt.Key.Key_Escape)

    assert modal.result() == QDialog.DialogCode.Rejected


def test_enter_nao_fecha_nem_remove(abrir):
    """Não há "confirmar" aqui: tudo já foi gravado. Um Enter solto não pode
    acionar botão nenhum."""
    modal = abrir()

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.result() != QDialog.DialogCode.Accepted
    assert _nomes(modal) == ["Batata P Simples", "Coca Lata"]


def test_nenhum_botao_rouba_o_teclado(abrir):
    """Com o foco num botão, o Espaço "clicaria" o último usado — no stepper,
    uma unidade a mais gravada sem ninguém ver."""
    modal = abrir()

    botoes = modal.findChildren(QPushButton)

    assert botoes and all(b.focusPolicy() == Qt.FocusPolicy.NoFocus for b in botoes)
    assert modal.focusPolicy() == Qt.FocusPolicy.StrongFocus


# ---------------------------------------------------------------------------
# 6. Medidas com a fonte da marca
# ---------------------------------------------------------------------------


@pytest.fixture
def com_fonte_e_tema(qapp):
    """A fonte da marca registrada e o QSS aplicado antes de medir qualquer coisa.

    Sem a fonte, a plataforma `offscreen` mede quase nada e o aperto não
    acontece — o teste passaria verde sem ter olhado (§9.5, §9.12).
    """
    caminho = (
        Path(gestor_comercial.__file__).resolve().parents[2]
        / "resources"
        / "fonts"
        / "ArchivoBlack-Regular.ttf"
    )
    if not caminho.exists():  # pragma: no cover - só num checkout incompleto
        pytest.skip(f"fonte da marca ausente em {caminho}")
    identificador = QFontDatabase.addApplicationFont(str(caminho))
    assert identificador != -1, "o Qt recusou a fonte da marca"
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield
    finally:
        controlador.alternar_para(False)
        QFontDatabase.removeApplicationFont(identificador)


def _mostrar(qapp, modal: QDialog) -> None:
    """Mostra e deixa o layout assentar — duas passadas, porque acomodar a barra
    de rolagem mexe na margem e pede um layout novo."""
    modal.show()
    qapp.processEvents()
    qapp.processEvents()


def test_o_rodape_cabe_no_cartao(qapp, com_fonte_e_tema, abrir):
    """Nenhuma peça do rodapé pode ser desenhada menor do que pede.

    A 600px (o teto do pedido escrito) o "+ Adicionar componente" saía como
    "olonar compone" e o contexto perdia o "COMBO" — ver `LARGURA_CARTAO_PX`.
    """
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = abrir(pai=janela)
    _mostrar(qapp, modal)

    rodape = next(w for w in modal.findChildren(QWidget) if w.objectName() == "comboDialogRodape")
    pecas = [w for w in rodape.findChildren(QWidget) if isinstance(w, (QLabel, QPushButton))]
    assert len(pecas) == 3, "premissa: contexto, Remover e Adicionar"
    apertadas = {
        w.objectName(): (w.width(), w.sizeHint().width())
        for w in pecas
        if w.width() < w.sizeHint().width()
    }

    modal.reject()
    assert not apertadas, f"rodapé espremido (tem, pede): {apertadas}"


def test_o_cartao_cabe_num_monitor_de_768px(qapp, com_fonte_e_tema, abrir):
    """A máquina do food truck: 728px úteis com a barra de tarefas."""
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = abrir(pai=janela)
    _mostrar(qapp, modal)

    altura = modal.height()

    modal.reject()
    assert altura <= 728


def test_nome_comprido_de_combo_nao_empurra_o_fechar(qapp, com_fonte_e_tema, cardapio, cenario, abrir):
    comprido = cardapio.criar_produto("Combo " + "Família Gigante " * 6, Decimal("90"), cenario["combos"].id)
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = abrir(produto=comprido, pai=janela)
    _mostrar(qapp, modal)

    direita_do_fechar = modal._botao_fechar.mapTo(modal, QPoint(modal._botao_fechar.width(), 0)).x()

    modal.reject()
    assert modal.width() == ComposicaoComboDialog.LARGURA_CARTAO_PX
    assert direita_do_fechar <= modal.width()


def test_o_nome_do_combo_no_cartao_de_adicao_nao_empurra_o_fechar(
    qapp, com_fonte_e_tema, cardapio, cenario
):
    """No modo componente o contexto do cartão de adição é o NOME DO COMBO, até
    120 letras. Um `QLabel` comum pediria a largura inteira e jogaria o ✕ para
    fora do cartão de 500px."""
    comprido = "Combo " + "Família Gigante " * 6
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = AdicionarItemDialog.para_componente(
        cardapio.listar_produtos_para_lancamento(), comprido, lambda *_: None, janela
    )
    _mostrar(qapp, modal)

    direita_do_fechar = modal._botao_fechar.mapTo(modal, QPoint(modal._botao_fechar.width(), 0)).x()
    largura = modal.width()

    modal.reject()
    descartar_modal(modal)
    assert largura == AdicionarItemDialog.LARGURA_CARTAO_PX
    assert direita_do_fechar <= largura


def test_a_barra_de_rolagem_nao_desloca_os_steppers(qapp, com_fonte_e_tema, cardapio, cenario, abrir):
    """A partir da quarta linha a barra aparece e come a largura do viewport. Sem
    `_acomodar_barra`, todos os steppers andariam para a esquerda de uma vez —
    o número que o gerente olhava muda de lugar embaixo do dedo."""
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()

    def direita_do_stepper(modal: ComposicaoComboDialog) -> int:
        pilula = modal._linhas[0]._botao_mais.parentWidget()
        return pilula.mapTo(modal, QPoint(pilula.width(), 0)).x()

    poucos = abrir(pai=janela)
    _mostrar(qapp, poucos)
    referencia = direita_do_stepper(poucos)
    assert poucos._rolagem.verticalScrollBar().maximum() == 0, "premissa: dois cabem sem rolar"
    poucos.reject()

    grande = cardapio.criar_produto("Combo Grande", Decimal("50"), cenario["combos"].id)
    for indice in range(5):
        extra = cardapio.criar_produto(f"Extra {indice}", Decimal("1"), cenario["combos"].id)
        cardapio.associar_componente(grande.id, extra.id, 1)
    muitos = abrir(produto=grande, pai=janela)
    _mostrar(qapp, muitos)
    medida = direita_do_stepper(muitos)
    rola = muitos._rolagem.verticalScrollBar().maximum() > 0
    muitos.reject()

    assert rola, "premissa: cinco linhas rolam"
    assert medida == referencia


# ---------------------------------------------------------------------------
# 7. Ciclo de vida — o RNF do Celeron
# ---------------------------------------------------------------------------


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar, cardapio, cenario):
    janela = QWidget()
    janela.show()

    for _ in range(5):
        modal = ComposicaoComboDialog(cardapio, cenario["combo"].id, "Combo", janela)
        modal.show()
        qapp.processEvents()
        assert len(janela.findChildren(Backdrop)) == 1
        modal.reject()
        modal.deleteLater()
    assentar()

    assert janela.findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar, cardapio, cenario):
    """O caminho real do app: aberto com `exec()` e fechado pelo Esc/✕."""
    pai = QWidget()

    for _ in range(30):
        modal = ComposicaoComboDialog(cardapio, cenario["combo"].id, "Combo", pai)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        del modal
    assentar()

    assert pai.findChildren(ComposicaoComboDialog) == []
    assert pai.findChildren(LinhaDoCombo) == []


def test_tirar_e_por_quarenta_vezes_nao_acumula_linhas(qapp, assentar, abrir, cardapio, cenario):
    """Uma tarde reorganizando o combo: a contagem de linhas vivas é a da tela."""
    modal = abrir()

    for _ in range(40):
        primeira = modal._linhas[0].linha
        modal._ao_clicar_linha(primeira.combo_item_id)
        modal._remover_selecionada()
        cardapio.associar_componente(cenario["combo"].id, primeira.produto_id, 1)
        modal._recarregar()
    assentar()

    assert len(modal.findChildren(LinhaDoCombo)) == len(modal._linhas) == 2


def test_fechar_desliga_os_sinais(qapp, abrir, cardapio, monkeypatch):
    """O `unbind` do pedido: depois de fechado, um clique perdido no stepper não
    chega mais ao service."""
    modal = abrir()
    linha = modal._linhas[0]
    chamadas: list[tuple[int, int]] = []
    monkeypatch.setattr(
        cardapio, "alterar_quantidade_componente", lambda *a: chamadas.append(a)
    )

    modal.reject()
    linha._botao_mais.click()
    modal._botao_remover.click()

    assert chamadas == []
    assert modal._backdrop is None
    assert _nomes(modal) == ["Batata P Simples", "Coca Lata"]


def test_soltar_os_recursos_duas_vezes_e_silencioso(qapp, abrir):
    """Sem a trava `_limpo`, cada `disconnect` repetido imprime
    `RuntimeWarning: libpyside: Failed to disconnect` (§9.12). Mede o aviso, e
    não uma exceção, pela lição registrada lá."""
    modal = abrir()
    modal.reject()

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        modal._soltar_recursos()
        modal._linhas[0].soltar()

    assert [str(a.message) for a in avisos] == []


def test_a_recarga_troca_a_linha_quando_o_sqlite_reaproveita_o_id(qapp, assentar, abrir):
    """O SQLite devolve o maior id quando a última linha é apagada: um
    componente removido e outro adicionado em seguida podem ter o mesmo número.
    Casar só pelo id reescreveria o nome da linha antiga em vez de trocá-la."""
    modal = abrir()
    antiga = modal._linhas[1]
    reaproveitado = LinhaDeComponente(
        combo_item_id=antiga.linha.combo_item_id,
        produto_id=antiga.linha.produto_id + 1000,
        nome="Guaracamp",
        categoria="Bebidas",
        quantidade=1,
    )

    modal._sincronizar([modal._linhas[0].linha, reaproveitado])
    assentar()

    assert modal._linhas[1] is not antiga
    assert antiga not in modal.findChildren(LinhaDoCombo)
    assert _nomes(modal) == ["Batata P Simples", "Guaracamp"]


# ---------------------------------------------------------------------------
# A tela do Cardápio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("mexer", "recargas"), [(False, 0), (True, 1)])
def test_gerenciar_combo_abre_a_composicao_e_so_recarrega_se_algo_mudou(
    qapp, cardapio, cenario, monkeypatch, mexer, recargas
):
    """O cartão grava na hora, então não há resultado para a view ler. Abrir,
    conferir e fechar não pode custar a recarga do Cardápio inteiro — e mudar
    alguma coisa tem que custar, senão a lista da direita mostra o combo velho."""
    import gestor_comercial.ui.views.cardapio_view as modulo_da_tela
    from gestor_comercial.ui.views.cardapio_view import CardapioView

    tela = CardapioView(cardapio)
    painel = tela._painel_produtos
    abertos: list[QDialog] = []
    atualizacoes: list[None] = []
    avisos: list[None] = []

    def falso(modal):
        abertos.append(type(modal))
        if mexer:
            modal._linhas[0]._botao_mais.click()
        modal.reject()
        descartar_modal(modal)
        return QDialog.DialogCode.Rejected

    def contar_aviso() -> None:
        avisos.append(None)

    monkeypatch.setattr(modulo_da_tela, "executar_modal", falso)
    monkeypatch.setattr(painel, "produto_atual", lambda: cenario["combo"])
    monkeypatch.setattr(painel, "atualizar", lambda *a, **k: atualizacoes.append(None))
    painel.alterado.connect(contar_aviso)

    painel.gerenciar_combo()

    painel.alterado.disconnect(contar_aviso)
    tela.deleteLater()
    assert abertos == [ComposicaoComboDialog]
    assert len(avisos) == recargas
    # O aviso de alteração recarrega a árvore, e a árvore devolve a seleção ao
    # painel — que recarrega de novo. Por isso "pelo menos uma" quando mudou; o
    # que interessa é o ZERO quando nada mudou.
    assert (len(atualizacoes) > 0) is bool(recargas)


# ---------------------------------------------------------------------------
# O escurecedor de um cartão sobre outro cartão
# ---------------------------------------------------------------------------


def _canto_pintado(backdrop: Backdrop) -> int:
    """O alfa do pixel (1, 1) do escurecedor pintado sobre fundo transparente."""
    backdrop.resize(120, 80)
    imagem = QImage(backdrop.size(), QImage.Format.Format_ARGB32)
    imagem.fill(QColor(0, 0, 0, 0))
    pintor = QPainter(imagem)
    # Sem `DrawWindowBackground`: o fundo da paleta pintaria o canto por baixo e
    # o teste mediria a paleta, não o escurecedor.
    backdrop.render(pintor, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    pintor.end()
    return imagem.pixelColor(1, 1).alpha()


def test_o_escurecedor_sobre_a_janela_principal_e_retangulo_cheio(qapp):
    janela = QWidget()
    dono = QDialog(janela)

    backdrop = modulo.cartao_modal.montar(dono)

    assert backdrop.raio == 0
    assert _canto_pintado(backdrop) == Backdrop.OPACIDADE
    modulo.cartao_modal.descartar(backdrop)


def test_o_escurecedor_sobre_outro_cartao_acompanha_os_cantos(qapp, abrir):
    """O "Adicionar componente" abre por cima da composição, que é translúcida e
    tem cantos de 16px. Um retângulo cheio pintaria de preto os cantos que o
    cartão deixa transparentes — medido antes da correção: alfa 150 no canto,
    o cartão de baixo com quatro quinas escuras atrás do de cima."""
    composicao = abrir()
    de_cima = QDialog(composicao)

    backdrop = modulo.cartao_modal.montar(de_cima)

    assert backdrop.raio == RAIO_CARTAO_PX
    assert _canto_pintado(backdrop) == 0
    modulo.cartao_modal.descartar(backdrop)
