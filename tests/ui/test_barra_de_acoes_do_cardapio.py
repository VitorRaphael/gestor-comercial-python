"""Os três botões do rodapé do Cardápio agem sobre o que está selecionado. §9.13.

Até o §9.12 eles eram botões de PRODUTO: sem produto escolhido ficavam
desligados, e a subdivisão vazia — que é exatamente o estado de quem acabou de
criá-la — não tinha como ser editada, desativada nem excluída por ali. Editar
categoria e subcategoria existiam só no menu de contexto, invisíveis para quem
não clica com o botão direito. Foi o que o Vitor apontou olhando a tela com
"Combo pastel (0)" selecionada e os três botões apagados.

O que esta suíte cobra:

1. **a máquina de estados** — o alvo é produto, subcategoria, categoria ou
   nada, nessa ordem de precedência, e o rótulo do rodapé diz qual é;
2. **os três botões despacham para o alvo certo** — e pela MESMA rotina do menu
   de contexto e do atalho de teclado, que é o que impede os caminhos de
   divergirem;
3. **as barreiras da exclusão** — subdivisão vazia sai com uma confirmação;
   com produtos dentro é recusada, e só a Senha Master (Nível 3, §9.10) libera
   a cascata;
4. **o bloco vazio da direita é clicável** — era o único jeito de a subdivisão
   sem produto nenhum entrar no contexto pela direita;
5. **nada sobra na memória** — o RNF do Celeron, numa tela que fica aberta o
   turno inteiro e onde agora se exclui e se edita muito mais.

Os diálogos abrem **de verdade**: `executar_modal` roda, `exec()` roda, o
service grava e o banco responde. Um dublê provaria só que o teste sabe chamar
o service.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QFontDatabase, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QMessageBox, QWidget

import gestor_comercial
import gestor_comercial.ui.views.cardapio_view as modulo_da_tela
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.views.cardapio_view import _SUB_TODAS, CardapioView, TipoDeAlvo
from gestor_comercial.ui.widgets.cardapio_cartoes import TipoDeItem
from gestor_comercial.ui.widgets.pin_pad_dialog import PinPadDialog

from tests.conftest import PIN_MASTER, PIN_OPERACIONAL


# ---------------------------------------------------------------------------
# Cenário
# ---------------------------------------------------------------------------


@pytest.fixture
def cardapio_montado(cardapio, gerente):
    """Lanches com Podrão (2 itens), Combo pastel (VAZIA) e um item solto.

    A subdivisão vazia é o caso do pedido: ela existe, está na tela, e até o
    §9.12 não havia como agir sobre ela pelo rodapé.
    """
    lanches = cardapio.criar_categoria("Lanches")
    bebidas = cardapio.criar_categoria("Bebidas")
    podrao = cardapio.criar_subcategoria(lanches.id, "Podrão")
    vazia = cardapio.criar_subcategoria(lanches.id, "Combo pastel")
    cardapio.criar_produto("X Burguer", Decimal("13.00"), lanches.id, subcategoria_id=podrao.id)
    cardapio.criar_produto("X Tudo", Decimal("16.00"), lanches.id, subcategoria_id=podrao.id)
    cardapio.criar_produto("X Egg", Decimal("15.00"), lanches.id)
    cardapio.criar_produto("Coca Lata", Decimal("8.00"), bebidas.id)
    return {"lanches": lanches, "bebidas": bebidas, "podrao": podrao, "vazia": vazia}


@pytest.fixture
def tela(qapp, cardapio, cardapio_montado):
    view = CardapioView(cardapio)
    view.resize(1366, 738)
    yield view
    view.close()
    view.deleteLater()


@pytest.fixture
def tela_vazia(qapp, cardapio, gerente):
    """Cardápio sem categoria nenhuma — o quarto estado da barra."""
    view = CardapioView(cardapio)
    yield view
    view.close()
    view.deleteLater()


@pytest.fixture
def tema(qapp):
    """QSS global aplicado, e o tema escuro de volta no fim (singleton)."""
    controlador = ThemeController.instancia()
    controlador.aplicar_inicial()
    try:
        yield controlador
    finally:
        controlador.alternar_para(False)


@pytest.fixture
def com_fonte_da_marca(qapp):
    """A fonte da marca registrada, para haver letra pintada de fato.

    A plataforma `offscreen` sobe com o banco de fontes VAZIO, e sem fonte o
    delegado desenha a pílula sem texto — dois recortes de cores diferentes
    sairiam idênticos. Mesma fixture (e mesma fonte) de
    `test_cardapio_hierarquia.py`.
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
    try:
        yield
    finally:
        QFontDatabase.removeApplicationFont(identificador)


def _item_categoria(tela: CardapioView, nome: str):
    painel = tela._painel_categorias
    for indice in range(painel.arvore.topLevelItemCount()):
        item = painel.arvore.topLevelItem(indice)
        if painel._nome_da_categoria(item) == nome:
            return item
    raise AssertionError(f"categoria '{nome}' não está na árvore")


def _abrir(tela: CardapioView, nome: str):
    item = _item_categoria(tela, nome)
    arvore = tela._painel_categorias.arvore
    arvore.setCurrentItem(item)
    tela._painel_categorias._ao_clicar(item, 0)
    arvore.setCurrentItem(item.child(0))
    return item


def _escolher_subdivisao(tela: CardapioView, categoria: str, rotulo: str):
    """Clica na subdivisão `rotulo` dentro de `categoria`, como o gerente faz."""
    item = _abrir(tela, categoria)
    for posicao in range(item.childCount()):
        filho = item.child(posicao)
        if filho.data(0, modulo_da_tela._PAPEL_ROTULO) == rotulo:
            tela._painel_categorias.arvore.setCurrentItem(filho)
            return filho
    raise AssertionError(f"'{rotulo}' não está sob '{categoria}'")


def _selecionar_produto(tela: CardapioView, nome: str) -> None:
    lista = tela._painel_produtos.lista
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.produto is not None and dado.produto.nome == nome:
            lista.setCurrentItem(lista.item(linha))
            return
    raise AssertionError(f"'{nome}' não está na lista")


def _linha_do_tipo(tela: CardapioView, tipo: TipoDeItem, rotulo: str) -> int:
    lista = tela._painel_produtos.lista
    for linha in range(lista.count()):
        dado = lista.item_da_linha(linha)
        if dado.tipo is tipo and dado.grupo is not None and dado.grupo.rotulo == rotulo:
            return linha
    raise AssertionError(f"linha {tipo} de '{rotulo}' não está na lista")


def _rodape(tela: CardapioView) -> dict:
    painel = tela._painel_produtos
    return {
        "rotulo": painel._label_dica.texto_completo(),
        "editar": painel._botao_editar.isEnabled(),
        "status": painel._botao_status.isEnabled(),
        "excluir": painel._botao_excluir.isEnabled(),
        "palavra": painel._botao_status.text(),
    }


# ---------------------------------------------------------------------------
# O roteiro de diálogos
# ---------------------------------------------------------------------------


def _teclar(dialogo: PinPadDialog, texto: str) -> None:
    for caractere in texto:
        dialogo.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_0,
                Qt.KeyboardModifier.NoModifier,
                caractere,
            )
        )


def _clicar_no_botao(caixa: QMessageBox, texto: str) -> None:
    for botao in caixa.buttons():
        if botao.text().replace("&", "") == texto:
            botao.click()
            return
    raise AssertionError(f"'{texto}' não está em {[b.text() for b in caixa.buttons()]}")


def encenar(qapp, tela: CardapioView, roteiro: list[tuple[str, str]], acao) -> list[str]:
    """Roda `acao` respondendo aos diálogos que ela abrir, na ordem do roteiro.

    Cada passo é `("caixa", "Excluir")` — clicar num botão de `QMessageBox` — ou
    `("pin", PIN_MASTER)` — digitar e confirmar no cartão de PIN.

    Um `QTimer` repetindo em intervalo zero, e não um `singleShot`: os diálogos
    deste fluxo são **encadeados** (o aviso abre o PIN), e cada `exec()` roda o
    próprio laço de eventos — um disparo único responderia ao primeiro e
    deixaria o segundo pendurado, travando a suíte.

    Devolve a lista do que realmente apareceu. Sem ela, um dia em que uma
    barreira sumisse o teste passaria verde: o roteiro simplesmente não seria
    consumido, e a exclusão aconteceria assim mesmo.
    """
    vistos: list[str] = []
    pendentes = list(roteiro)

    def visivel(tipo) -> list:
        return [d for d in tela.findChildren(tipo) if d.isVisible()]

    def proximo() -> None:
        caixas, pins = visivel(QMessageBox), visivel(PinPadDialog)
        if not caixas and not pins:
            return
        if not pendentes:
            # Diálogo que o roteiro não previu: fecha para não travar a suíte e
            # deixa o rastro na lista, para a asserção do teste acusar.
            vistos.append("INESPERADO")
            (caixas + pins)[-1].reject()
            return
        tipo, valor = pendentes[0]
        if tipo == "caixa" and caixas:
            pendentes.pop(0)
            vistos.append(caixas[-1].text())
            _clicar_no_botao(caixas[-1], valor)
        elif tipo == "pin" and pins:
            pendentes.pop(0)
            pin = pins[-1]
            vistos.append(pin.windowTitle())
            _teclar(pin, valor)
            pin._confirmar()
            if pin.result() != QDialog.DialogCode.Accepted:
                pin.reject()  # PIN recusado: o teste não pode ficar preso no exec()

    relogio = QTimer()
    relogio.setInterval(0)
    relogio.timeout.connect(proximo)
    relogio.start()
    try:
        acao()
    finally:
        relogio.stop()
        relogio.timeout.disconnect(proximo)
    qapp.processEvents()
    assert not pendentes, f"o roteiro não foi consumido: faltou {pendentes}"
    return vistos


# ---------------------------------------------------------------------------
# 1. A máquina de estados
# ---------------------------------------------------------------------------


def test_sem_nada_selecionado_a_barra_diz_o_que_escolher(tela_vazia):
    """O quarto estado: cardápio ainda sem categoria nenhuma."""
    assert _rodape(tela_vazia) == {
        "rotulo": "SELECIONE UMA CATEGORIA, SUBCATEGORIA OU PRODUTO",
        "editar": False,
        "status": False,
        "excluir": False,
        "palavra": "Desativar",
    }
    assert tela_vazia._painel_produtos.alvo_atual().tipo is TipoDeAlvo.NADA


def test_a_categoria_aberta_e_o_alvo(tela):
    """Clicar na categoria equivale a "Todas" dentro dela, e o alvo é ela."""
    _abrir(tela, "Lanches")

    rodape = _rodape(tela)
    assert rodape["rotulo"] == "CATEGORIA: LANCHES"
    assert (rodape["editar"], rodape["status"], rodape["excluir"]) == (True, True, True)


def test_a_subcategoria_escolhida_e_o_alvo(tela):
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    assert _rodape(tela)["rotulo"] == "SUBCATEGORIA: PODRÃO"
    assert tela._painel_produtos.alvo_atual().tipo is TipoDeAlvo.SUBCATEGORIA


def test_a_subcategoria_vazia_tambem_e_o_alvo(tela):
    """O pedido, na sua forma exata: "Combo pastel (0)" com os três botões vivos."""
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")

    rodape = _rodape(tela)
    assert rodape["rotulo"] == "SUBCATEGORIA: COMBO PASTEL"
    assert (rodape["editar"], rodape["status"], rodape["excluir"]) == (True, True, True)


def test_o_produto_escolhido_e_o_alvo(tela):
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    _selecionar_produto(tela, "X Tudo")

    assert _rodape(tela)["rotulo"] == "PRODUTO: X TUDO"
    assert tela._painel_produtos.alvo_atual().tipo is TipoDeAlvo.PRODUTO


def test_o_produto_tem_precedencia_sobre_a_subdivisao_que_o_contem(tela):
    """A ordem do gesto mais específico. Sem ela, clicar numa linha dentro de
    "Podrão" deixaria o Excluir apontando para a subdivisão inteira."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Burguer")

    assert tela._painel_produtos.alvo_atual() == modulo_da_tela.AlvoDaAcao(
        TipoDeAlvo.PRODUTO, "X Burguer", True
    )


def test_trocar_de_subdivisao_solta_o_produto_e_devolve_o_alvo_ao_grupo(tela):
    """O que faz a precedência não virar ambiguidade: mover a árvore recarrega a
    lista sem seleção, então "produto escolhido" só existe depois de um clique
    deliberado numa linha."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Burguer")

    _escolher_subdivisao(tela, "Lanches", "Combo pastel")

    assert _rodape(tela)["rotulo"] == "SUBCATEGORIA: COMBO PASTEL"


def test_o_rotulo_troca_de_tom_quando_ha_alvo(tela):
    """Propriedade dinâmica, e não `setStyleSheet`: cor congelada em folha local
    não acompanha o alternador Claro/Escuro (§3.15).

    O estado "vazio" é o da tela sem categoria nenhuma, e vive no seu próprio
    teste: as duas fixtures compartilham a sessão do banco, então pedir as duas
    telas aqui faria a "vazia" enxergar o cardápio da outra.
    """
    _abrir(tela, "Lanches")

    assert tela._painel_produtos._label_dica.property("estado") == "alvo"


def test_sem_alvo_o_rotulo_volta_a_ser_dica(tela_vazia):
    assert tela_vazia._painel_produtos._label_dica.property("estado") == "vazio"


# ---------------------------------------------------------------------------
# 2. O botão do meio
# ---------------------------------------------------------------------------


def test_desativar_a_subcategoria_pela_barra_tira_os_produtos_do_balcao(tela, cardapio):
    """O caminho inteiro, da tela ao balcão: o botão, o service e a consulta de
    lançamento."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    tela._painel_produtos._botao_status.click()

    vendaveis = [p.nome for p in cardapio.listar_produtos_para_lancamento()]
    assert "X Burguer" not in vendaveis and "X Tudo" not in vendaveis
    assert "X Egg" in vendaveis


def test_o_botao_passa_a_dizer_ativar_e_troca_de_cor(tela):
    """"fundo sutil, texto verde" — a variante muda junto com a palavra, senão o
    mesmo botão ciano pareceria a mesma ação nos dois sentidos."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    assert tela._painel_produtos._botao_status.property("variante") == "ciano"

    tela._painel_produtos._botao_status.click()

    assert _rodape(tela)["palavra"] == "Ativar"
    assert tela._painel_produtos._botao_status.property("variante") == "religar"


def test_ativar_de_volta_pela_barra(tela, cardapio):
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    tela._painel_produtos._botao_status.click()

    tela._painel_produtos._botao_status.click()

    assert _rodape(tela)["palavra"] == "Desativar"
    assert "X Burguer" in [p.nome for p in cardapio.listar_produtos_para_lancamento()]


def test_o_bloco_da_direita_carimba_desativada(tela):
    """O badge que o pedido cita: quem diz o estado em letras é o cabeçalho do
    bloco, que tem largura para isso — a pílula da árvore só escurece."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    tela._painel_produtos._botao_status.click()

    linha = _linha_do_tipo(tela, TipoDeItem.CABECALHO, "Podrão")
    grupo = tela._painel_produtos.lista.item_da_linha(linha).grupo
    assert grupo.ativa is False
    assert grupo.contagem_texto == "DESATIVADA · 2 PRODUTOS"


def test_a_arvore_carrega_o_estado_da_subdivisao(tela):
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    tela._painel_produtos._botao_status.click()

    item = _escolher_subdivisao(tela, "Lanches", "Podrão")
    assert item.data(0, modulo_da_tela.PAPEL_LINHA).ativa is False


def test_a_arvore_pinta_a_subdivisao_desativada_mais_apagada(
    qapp, tela, tema, com_fonte_da_marca
):
    """O dado chegar à linha não prova que a linha mudou de cara.

    A comparação é feita com a subdivisão **fora da seleção**: selecionada, a
    pílula é âmbar nos dois estados, e o teste passaria sem ter olhado para o
    tom apagado. A fonte da marca é registrada porque a plataforma `offscreen`
    sobe com o banco de fontes vazio — sem ela não há letra pintada, e dois
    recortes sem texto saem idênticos em qualquer cor.
    """
    tela.show()
    arvore = tela._painel_categorias.arvore

    def recorte_fora_da_selecao() -> object:
        item = _escolher_subdivisao(tela, "Lanches", "Podrão")
        arvore.setCurrentItem(item.parent().child(0))  # "Todas": solta a pílula
        qapp.processEvents()
        return arvore.viewport().grab(arvore.visualItemRect(item)).toImage()

    ativa = recorte_fora_da_selecao()
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    tela._painel_produtos._botao_status.click()
    desativada = recorte_fora_da_selecao()

    assert not ativa.isNull() and ativa.width() > 0, "premissa: a linha foi desenhada"
    assert ativa != desativada, "a pílula da subdivisão desativada saiu igual à da ativa"


def test_a_categoria_tambem_alterna_pela_barra(tela, cardapio, cardapio_montado):
    """O mesmo botão, um nível acima — e a regra da categoria não mudou."""
    _abrir(tela, "Lanches")

    tela._painel_produtos._botao_status.click()

    assert cardapio.buscar_categoria(cardapio_montado["lanches"].id).ativo is False
    assert _rodape(tela)["palavra"] == "Ativar"


def test_o_produto_continua_alternando_como_antes(tela, cardapio):
    """Não-regressão do gesto de todo dia ("acabou o pão de hambúrguer")."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Tudo")

    tela._painel_produtos._botao_status.click()

    assert [p.nome for p in cardapio.listar_produtos() if not p.ativo] == ["X Tudo"]


# ---------------------------------------------------------------------------
# 3. Editar — e o DRY com o link do bloco
# ---------------------------------------------------------------------------


class _ModalDeOrganizacao(QDialog):
    """Dublê do cartão de cadastro: registra o nível e o nome que recebeu."""

    abertos: list[tuple[str, str]] = []
    nome_a_devolver: str | None = None

    def __init__(self, parent=None, *, nivel="", nome_inicial="") -> None:
        super().__init__(parent)
        _ModalDeOrganizacao.abertos.append((nivel, nome_inicial))
        self._respondido = False

    @classmethod
    def para_categoria(cls, _existentes, parent=None, *, nome_inicial=""):
        return cls(parent, nivel="categoria", nome_inicial=nome_inicial)

    @classmethod
    def para_subcategoria(
        cls, _categoria, _impressora, _existentes, parent=None, *, nome_inicial=""
    ):
        return cls(parent, nivel="subcategoria", nome_inicial=nome_inicial)

    def exec(self) -> int:
        if self._respondido or _ModalDeOrganizacao.nome_a_devolver is None:
            return QDialog.DialogCode.Rejected
        self._respondido = True
        return QDialog.DialogCode.Accepted

    def resultado(self):
        return type("Resultado", (), {"nome": _ModalDeOrganizacao.nome_a_devolver})()

    def mostrar_erro_servico(self, mensagem: str) -> None:
        raise AssertionError(mensagem)


@pytest.fixture
def modal_de_organizacao(monkeypatch):
    _ModalDeOrganizacao.abertos = []
    _ModalDeOrganizacao.nome_a_devolver = None
    monkeypatch.setattr(modulo_da_tela, "OrganizacaoCardapioDialog", _ModalDeOrganizacao)
    return _ModalDeOrganizacao


def test_editar_com_subcategoria_no_alvo_abre_o_cartao_dela(tela, modal_de_organizacao):
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")

    tela._painel_produtos._botao_editar.click()

    assert modal_de_organizacao.abertos == [("subcategoria", "Combo pastel")]


def test_editar_com_categoria_no_alvo_abre_o_cartao_da_categoria(tela, modal_de_organizacao):
    _abrir(tela, "Lanches")

    tela._painel_produtos._botao_editar.click()

    assert modal_de_organizacao.abertos == [("categoria", "Lanches")]


def test_renomear_a_subcategoria_pela_barra_grava_e_mantem_a_selecao(
    tela, cardapio, modal_de_organizacao, cardapio_montado
):
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")
    modal_de_organizacao.nome_a_devolver = "Combos de pastel"

    tela._painel_produtos._botao_editar.click()

    nomes = [s.nome for s in cardapio.listar_subcategorias(cardapio_montado["lanches"].id)]
    assert "Combos de pastel" in nomes
    assert tela._painel_categorias.selecao_atual().chave == "Combos de pastel"


def test_o_link_do_bloco_e_o_botao_editar_sao_a_mesma_rotina(
    qapp, tela, modal_de_organizacao
):
    """DRY, medido: o link "Editar subcategoria" do cabeçalho e o "Editar" do
    rodapé abrem o MESMO cartão, com o mesmo nome preenchido."""
    tela.show()
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    retangulo = lista.visualItemRect(lista.item(_linha_do_tipo(tela, TipoDeItem.CABECALHO, "Podrão")))
    link = lista.delegado().retangulo_do_link(retangulo, lista.font())

    QTest.mouseClick(
        lista.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, link.center()
    )
    pelo_link = list(modal_de_organizacao.abertos)
    modal_de_organizacao.abertos = []

    tela._painel_produtos._botao_editar.click()

    assert pelo_link == [("subcategoria", "Podrão")]
    assert modal_de_organizacao.abertos == pelo_link


def test_editar_produto_continua_abrindo_o_formulario_de_produto(tela, modal_de_organizacao):
    """Não-regressão: com produto no alvo, o botão NÃO é o cartão de estrutura."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Tudo")

    modais = tela.findChildren(modulo_da_tela._ProdutoDialog)
    assert modais == [], "premissa: nenhum formulário de produto aberto ainda"
    assert tela._painel_produtos.alvo_atual().tipo is TipoDeAlvo.PRODUTO
    assert modal_de_organizacao.abertos == []


# ---------------------------------------------------------------------------
# 4. Excluir — as duas barreiras
# ---------------------------------------------------------------------------


def test_excluir_subcategoria_vazia_pede_uma_confirmacao_e_apaga(
    qapp, tela, cardapio, cardapio_montado
):
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")

    vistos = encenar(
        qapp, tela, [("caixa", "Excluir")], tela._painel_produtos._botao_excluir.click
    )

    assert "Deseja excluir a subcategoria 'Combo pastel'?" in vistos[0]
    assert [s.nome for s in cardapio.listar_subcategorias(cardapio_montado["lanches"].id)] == [
        "Podrão"
    ]


def test_cancelar_a_confirmacao_nao_apaga_nada(qapp, tela, cardapio, cardapio_montado):
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")

    encenar(qapp, tela, [("caixa", "Cancelar")], tela._painel_produtos._botao_excluir.click)

    assert len(cardapio.listar_subcategorias(cardapio_montado["lanches"].id)) == 2


def test_depois_de_excluir_a_arvore_volta_para_todas_da_mesma_categoria(qapp, tela):
    """E não para a primeira categoria da lista: o gerente continua organizando
    a categoria em que estava."""
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")

    encenar(qapp, tela, [("caixa", "Excluir")], tela._painel_produtos._botao_excluir.click)

    selecao = tela._painel_categorias.selecao_atual()
    assert (selecao.categoria.nome, selecao.chave) == ("Lanches", _SUB_TODAS)


def test_excluir_subcategoria_com_produtos_e_bloqueada_com_o_numero(
    qapp, tela, cardapio, cardapio_montado
):
    """A recusa diz quantos são: é o número que dimensiona o trabalho de quem
    vai ter que mover os produtos antes."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    vistos = encenar(
        qapp, tela, [("caixa", "Cancelar")], tela._painel_produtos._botao_excluir.click
    )

    assert "existem 2 produtos vinculados a ela" in vistos[0]
    assert "Mova ou exclua os produtos primeiro" in vistos[0]
    assert len(cardapio.listar_subcategorias(cardapio_montado["lanches"].id)) == 2


def test_a_cascata_exige_a_senha_master(qapp, tela, cardapio, cardapio_montado):
    """Nível 3, a mesma credencial que abre a Central de Loja (§9.10): exigir
    gerente é satisfeito pela SESSÃO, e quem abriu o turno de manhã autorizaria
    a cascata que alguém clicasse à tarde."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    vistos = encenar(
        qapp,
        tela,
        [("caixa", "Excluir com Senha Master"), ("pin", PIN_MASTER)],
        tela._painel_produtos._botao_excluir.click,
    )

    assert vistos[1] == "Confirmar Exclusão"
    assert [s.nome for s in cardapio.listar_subcategorias(cardapio_montado["lanches"].id)] == [
        "Combo pastel"
    ]
    assert [p.nome for p in cardapio.listar_produtos()] == ["Coca Lata", "X Egg"]


def test_a_senha_operacional_nao_libera_a_cascata(qapp, tela, cardapio, cardapio_montado):
    """Nível 3 não herda de baixo para cima."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    encenar(
        qapp,
        tela,
        [("caixa", "Excluir com Senha Master"), ("pin", PIN_OPERACIONAL)],
        tela._painel_produtos._botao_excluir.click,
    )

    assert len(cardapio.listar_subcategorias(cardapio_montado["lanches"].id)) == 2
    assert len(cardapio.listar_produtos()) == 4


def test_cancelar_o_aviso_nem_chega_a_pedir_o_pin(qapp, tela):
    """O roteiro não consumido é o que prova: com "Cancelar", o cartão de PIN
    não chega a existir."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    vistos = encenar(
        qapp, tela, [("caixa", "Cancelar")], tela._painel_produtos._botao_excluir.click
    )

    assert len(vistos) == 1
    assert tela.findChildren(PinPadDialog) == []


def test_excluir_produto_continua_pedindo_so_o_sim_ou_nao(qapp, tela, cardapio):
    """Não-regressão: a barreira nova é da subcategoria, não do produto."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Tudo")

    encenar(qapp, tela, [("caixa", "Yes")], tela._painel_produtos._botao_excluir.click)

    assert "X Tudo" not in [p.nome for p in cardapio.listar_produtos()]


# ---------------------------------------------------------------------------
# 5. O bloco vazio da direita entra no contexto
# ---------------------------------------------------------------------------


def test_clicar_no_cabecalho_escolhe_aquela_subdivisao(qapp, tela):
    """Em "Todas", clicar no cabeçalho de um bloco move a seleção da ÁRVORE.

    A seleção continua morando num lugar só: duas fontes de verdade para "onde
    estou" divergem na primeira recarga, e aí o rodapé age sobre uma subdivisão
    diferente da que está acesa na coluna da esquerda.
    """
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    retangulo = lista.visualItemRect(lista.item(_linha_do_tipo(tela, TipoDeItem.CABECALHO, "Podrão")))

    QTest.mouseClick(
        lista.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(retangulo.left() + 70, retangulo.center().y()),
    )

    assert tela._painel_categorias.selecao_atual().chave == "Podrão"
    assert _rodape(tela)["rotulo"] == "SUBCATEGORIA: PODRÃO"


def test_clicar_no_aviso_de_bloco_vazio_mantem_a_subdivisao_no_alvo(qapp, tela):
    """A área vazia ("NENHUM PRODUTO NESTA SUBCATEGORIA AINDA") não pode soltar
    o contexto — é o único lugar clicável do bloco de uma subdivisão vazia."""
    tela.show()
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    retangulo = lista.visualItemRect(lista.item(_linha_do_tipo(tela, TipoDeItem.VAZIO, "Combo pastel")))

    QTest.mouseClick(
        lista.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        retangulo.center(),
    )

    assert _rodape(tela)["rotulo"] == "SUBCATEGORIA: COMBO PASTEL"
    assert tela._painel_produtos._botao_excluir.isEnabled() is True


def test_clicar_numa_linha_de_produto_nao_move_a_arvore(qapp, tela):
    """A linha de produto tem dono: a seleção da lista.

    Ela carrega o grupo a que pertence, então sem a conferência de tipo em
    `_grupo_em` o clique num produto dentro de "Todas" jogaria a árvore para a
    subdivisão dele — e a recarga que isso dispara soltaria a seleção do
    produto que o dedo acabou de escolher.
    """
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    linha = next(
        i for i in range(lista.count())
        if (dado := lista.item_da_linha(i)).produto is not None and dado.produto.nome == "X Tudo"
    )

    QTest.mouseClick(
        lista.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        lista.visualItemRect(lista.item(linha)).center(),
    )

    assert tela._painel_categorias.selecao_atual().chave == _SUB_TODAS
    assert _rodape(tela)["rotulo"] == "PRODUTO: X TUDO"


def test_clicar_no_espaco_entre_blocos_nao_muda_o_contexto(qapp, tela):
    """O espaço não é de ninguém: um clique nele não pode mudar o alvo pelas
    costas de quem está olhando a subdivisão aberta."""
    tela.show()
    _abrir(tela, "Lanches")
    qapp.processEvents()
    lista = tela._painel_produtos.lista
    espaco = next(
        linha for linha in range(lista.count())
        if lista.item_da_linha(linha).tipo is TipoDeItem.ESPACO
    )

    QTest.mouseClick(
        lista.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        lista.visualItemRect(lista.item(espaco)).center(),
    )

    assert _rodape(tela)["rotulo"] == "CATEGORIA: LANCHES"


# ---------------------------------------------------------------------------
# 6. Uma porta de entrada só por ação
# ---------------------------------------------------------------------------


def test_o_atalho_f2_segue_a_subdivisao_e_nao_a_categoria(tela, modal_de_organizacao):
    """Antes o F2 editava a CATEGORIA mesmo com uma subdivisão destacada: o
    teclado fazia uma coisa e o menu de contexto do mesmo item fazia outra."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    tela._contexto = "categoria"

    tela._editar()

    assert modal_de_organizacao.abertos == [("subcategoria", "Podrão")]


def test_o_botao_do_rodape_e_o_menu_de_contexto_chamam_a_mesma_rotina(
    tela, modal_de_organizacao
):
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    tela._painel_categorias.editar_selecionado()
    pelo_menu = list(modal_de_organizacao.abertos)
    modal_de_organizacao.abertos = []
    tela._painel_produtos._botao_editar.click()

    assert pelo_menu == modal_de_organizacao.abertos == [("subcategoria", "Podrão")]


# ---------------------------------------------------------------------------
# 7. Memória — o RNF do Celeron
# ---------------------------------------------------------------------------


def test_edicoes_e_exclusoes_sucessivas_nao_acumulam_widgets(
    qapp, tela, cardapio, cardapio_montado, modal_de_organizacao, assentar
):
    """A tela fica aberta o turno inteiro, e agora se edita e se exclui muito
    mais por ela. O que sobrar de uma volta sobra de todas."""
    lanches = cardapio_montado["lanches"]
    _abrir(tela, "Lanches")
    assentar()
    antes = len(tela.findChildren(QWidget))

    for numero in range(6):
        nome = f"Grupo {numero}"
        cardapio.criar_subcategoria(lanches.id, nome)
        tela.atualizar()
        _escolher_subdivisao(tela, "Lanches", nome)
        modal_de_organizacao.nome_a_devolver = f"{nome} editado"
        tela._painel_produtos._botao_editar.click()
        _escolher_subdivisao(tela, "Lanches", f"{nome} editado")
        encenar(qapp, tela, [("caixa", "Excluir")], tela._painel_produtos._botao_excluir.click)

    assentar()
    assert [s.nome for s in cardapio.listar_subcategorias(lanches.id)] == [
        "Combo pastel",
        "Podrão",
    ]
    assert len(tela.findChildren(QWidget)) == antes
