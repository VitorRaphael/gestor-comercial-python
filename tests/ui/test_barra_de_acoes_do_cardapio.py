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
   com produtos dentro, só a Senha Master (Nível 3, §9.10) libera a cascata.
   Desde o §9.18 as duas saem do MESMO cartão (`ConfirmacaoExclusaoDialog`), o
   PIN abre por cima dele, e o produto ganhou o mesmo par — apagado num clique
   sem histórico, arquivado com a Senha Master com histórico;
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
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.confirmacao_exclusao_dialog import ConfirmacaoExclusaoDialog
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
    """A categoria aberta em "Todas" — o estado, não o gesto: numa já aberta o
    clique a recolheria (§9.17)."""
    item = _item_categoria(tela, nome)
    arvore = tela._painel_categorias.arvore
    arvore.setCurrentItem(item)
    if not item.isExpanded():
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


def _leitura_do_cartao(cartao: ConfirmacaoExclusaoDialog) -> str:
    """Tudo o que o gerente lê no cartão, numa linha — é contra isto que os
    testes conferem a frase, o nível e o botão."""
    return " | ".join(
        (
            cartao._secao.text(),
            cartao._titulo.text(),
            cartao._nome.text(),
            cartao._aviso_titulo.text(),
            cartao._aviso_texto.text(),
            cartao._botao_confirmar.text(),
        )
    )


def encenar(qapp, tela: CardapioView, roteiro: list[tuple[str, str]], acao) -> list[str]:
    """Roda `acao` respondendo aos diálogos que ela abrir, na ordem do roteiro.

    Cada passo é um de:

    * `("cartao", "confirmar")` / `("cartao", "cancelar")` — clicar no botão
      vermelho ou no Cancelar do cartão de exclusão (§9.18);
    * `("pin", PIN_MASTER)` — digitar e confirmar no cartão de PIN;
    * `("pin", "fechar")` — desistir do PIN pelo ✕.

    Um `QTimer` repetindo em intervalo zero, e não um `singleShot`: os diálogos
    deste fluxo são **encadeados** (o cartão abre o PIN), e cada `exec()` roda o
    próprio laço de eventos — um disparo único responderia ao primeiro e
    deixaria o segundo pendurado, travando a suíte.

    **O clique no cartão é agendado, e não feito dentro do relógio.** Desde o
    §9.18 o PIN abre POR CIMA do cartão, dentro do clique: clicar de dentro de
    `proximo` poria o `exec()` do PIN dentro do disparo do relógio, e o Qt não
    dispara de novo um timer cujo disparo ainda não terminou — o relógio pararia
    com o PIN aberto. `clique_pendente` segura o relógio até o clique sair.

    Devolve a lista do que realmente apareceu. Sem ela, um dia em que uma
    barreira sumisse o teste passaria verde: o roteiro simplesmente não seria
    consumido, e a exclusão aconteceria assim mesmo. Um `QMessageBox` também é
    procurado: se algum voltar a aparecer, é fechado e acusado como INESPERADO.
    """
    vistos: list[str] = []
    pendentes = list(roteiro)
    # Quantas voltas do relógio um diálogo aberto pode ficar sem casar com o
    # passo esperado antes de ser fechado à força. Sem este teto o helper
    # TRAVA — e travou (§9.14): uma mutação que tirava o aviso fazia o PIN abrir
    # onde o roteiro esperava outro diálogo, e o relógio girava para sempre
    # dentro do `exec()`. Um teste que pendura a suíte é pior que um que falha.
    TETO_DE_ESPERA = 200
    parado = 0
    clique_pendente = False

    def visivel(tipo) -> list:
        return [d for d in tela.findChildren(tipo) if d.isVisible()]

    def soltar(dialogo) -> None:
        vistos.append("INESPERADO")
        dialogo.reject()

    def agendar(botao) -> None:
        nonlocal clique_pendente
        clique_pendente = True

        def clicar() -> None:
            nonlocal clique_pendente
            clique_pendente = False
            botao.click()

        QTimer.singleShot(0, clicar)

    def proximo() -> None:
        nonlocal parado
        if clique_pendente:
            return
        caixas = visivel(QMessageBox)
        cartoes, pins = visivel(ConfirmacaoExclusaoDialog), visivel(PinPadDialog)
        # O PIN por último: aberto por cima do cartão, é ele que está na frente.
        abertos = caixas + cartoes + pins
        if not abertos:
            parado = 0
            return
        if caixas or not pendentes:
            # Diálogo que o roteiro não previu: fecha e deixa o rastro na lista,
            # para a asserção do teste acusar.
            soltar(abertos[-1] if not caixas else caixas[-1])
            return
        tipo, valor = pendentes[0]
        if tipo == "pin" and pins:
            parado = 0
            pendentes.pop(0)
            pin = pins[-1]
            vistos.append(pin.windowTitle())
            if valor == "fechar":
                pin._botao_fechar.click()
                return
            _teclar(pin, valor)
            pin._confirmar()
            if pin.result() != QDialog.DialogCode.Accepted:
                pin.reject()  # PIN recusado: o teste não pode ficar preso no exec()
        elif tipo == "cartao" and cartoes and not pins:
            parado = 0
            pendentes.pop(0)
            cartao = cartoes[-1]
            vistos.append(_leitura_do_cartao(cartao))
            agendar(cartao._botao_confirmar if valor == "confirmar" else cartao._botao_cancelar)
        else:
            # Há diálogo na tela, mas de um tipo que o roteiro não esperava
            # agora. Espera um pouco (ele pode estar nascendo) e desiste.
            parado += 1
            if parado >= TETO_DE_ESPERA:
                parado = 0
                soltar(abertos[-1])

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
        qapp, tela, [("cartao", "confirmar")], tela._painel_produtos._botao_excluir.click
    )

    assert vistos[0] == (
        "AÇÃO PERMANENTE | Excluir subcategoria | Combo pastel | "
        "Deseja excluir esta subcategoria? | "
        "Ela não tem nenhum produto dentro — nada mais é afetado. | Excluir subcategoria"
    )
    assert [s.nome for s in cardapio.listar_subcategorias(cardapio_montado["lanches"].id)] == [
        "Podrão"
    ]


def test_cancelar_a_confirmacao_nao_apaga_nada(qapp, tela, cardapio, cardapio_montado):
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")

    encenar(qapp, tela, [("cartao", "cancelar")], tela._painel_produtos._botao_excluir.click)

    assert len(cardapio.listar_subcategorias(cardapio_montado["lanches"].id)) == 2


def test_depois_de_excluir_a_arvore_volta_para_todas_da_mesma_categoria(qapp, tela):
    """E não para a primeira categoria da lista: o gerente continua organizando
    a categoria em que estava (o "preservar o nó pai" do pedido do §9.18)."""
    _escolher_subdivisao(tela, "Lanches", "Combo pastel")

    encenar(qapp, tela, [("cartao", "confirmar")], tela._painel_produtos._botao_excluir.click)

    selecao = tela._painel_categorias.selecao_atual()
    assert (selecao.categoria.nome, selecao.chave) == ("Lanches", _SUB_TODAS)


def test_subcategoria_com_produtos_diz_o_numero_e_oferece_a_senha_master(
    qapp, tela, cardapio, cardapio_montado
):
    """O número dimensiona o que vai sair, e o botão diz o que ele pede.

    É a regra do §9.13, reafirmada pelo Vitor no §9.18 contra o bloqueio rígido
    da Foto 3: a subdivisão cheia NÃO fica com o botão apagado."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    vistos = encenar(
        qapp, tela, [("cartao", "cancelar")], tela._painel_produtos._botao_excluir.click
    )

    assert vistos[0].startswith("EXCLUSÃO PROTEGIDA | Excluir subcategoria | Podrão | ")
    assert "Esta subcategoria contém 2 produtos." in vistos[0]
    assert vistos[0].endswith("| Excluir com Senha Master")
    assert len(cardapio.listar_subcategorias(cardapio_montado["lanches"].id)) == 2


def test_a_cascata_exige_a_senha_master(qapp, tela, cardapio, cardapio_montado):
    """Nível 3, a mesma credencial que abre a Central de Loja (§9.10): exigir
    gerente é satisfeito pela SESSÃO, e quem abriu o turno de manhã autorizaria
    a cascata que alguém clicasse à tarde."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    vistos = encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_MASTER)],
        tela._painel_produtos._botao_excluir.click,
    )

    assert vistos[1] == "Confirmar Exclusão"
    assert [s.nome for s in cardapio.listar_subcategorias(cardapio_montado["lanches"].id)] == [
        "Combo pastel"
    ]
    assert [p.nome for p in cardapio.listar_produtos()] == ["Coca Lata", "X Egg"]


def test_a_senha_operacional_nao_libera_a_cascata_e_devolve_ao_cartao(
    qapp, tela, cardapio, cardapio_montado
):
    """Nível 3 não herda de baixo para cima — e a recusa não fecha o cartão: o
    PIN abriu POR CIMA dele (§9.18), e o gerente volta a ver o que ia sair."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    vistos = encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_OPERACIONAL), ("cartao", "cancelar")],
        tela._painel_produtos._botao_excluir.click,
    )

    assert vistos[2] == vistos[0], "o cartão que volta é o mesmo, com o mesmo aviso"
    assert len(cardapio.listar_subcategorias(cardapio_montado["lanches"].id)) == 2
    assert len(cardapio.listar_produtos()) == 4


def test_desistir_do_pin_e_tentar_de_novo_no_mesmo_cartao(
    qapp, tela, cardapio, cardapio_montado
):
    """O ganho de o PIN abrir sobre o cartão: errar ou fechar o PIN não custa o
    gesto inteiro. Com os `QMessageBox` de antes, fechar o PIN encerrava tudo e
    o gerente recomeçava do botão Excluir."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    vistos = encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", "fechar"), ("cartao", "confirmar"), ("pin", PIN_MASTER)],
        tela._painel_produtos._botao_excluir.click,
    )

    assert vistos[1] == vistos[3] == "Confirmar Exclusão"
    assert [s.nome for s in cardapio.listar_subcategorias(cardapio_montado["lanches"].id)] == [
        "Combo pastel"
    ]


def test_o_pin_da_tela_nasce_filho_do_cartao(qapp, tela, cardapio):
    """É o parent que põe o escurecedor do PIN sobre o CARTÃO e o centraliza
    nele. Filho da tela, o PIN escureceria a janela inteira por trás de um
    cartão aceso — dois modais disputando a frente. Achado por mutação: a
    suíte do cartão testa com uma barreira de mentira, e nada prendia a da
    view."""
    cartao = ConfirmacaoExclusaoDialog.para_categoria("Lanches", 1, 0, lambda _c: True, tela)
    pais: list = []

    def olhar_e_fechar() -> None:
        pin = next(p for p in tela.findChildren(PinPadDialog) if p.isVisible())
        pais.append(pin.parentWidget())
        pin.reject()

    QTimer.singleShot(0, olhar_e_fechar)
    passou = modulo_da_tela._pedir_senha_master(cardapio.auth, "a categoria 'Lanches'", cartao)

    assert passou is False
    assert pais == [cartao]
    cartao.deleteLater()


def test_cancelar_o_cartao_nem_chega_a_pedir_o_pin(qapp, tela):
    """O roteiro não consumido é o que prova: com "Cancelar", o cartão de PIN
    não chega a existir."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")

    vistos = encenar(
        qapp, tela, [("cartao", "cancelar")], tela._painel_produtos._botao_excluir.click
    )

    assert len(vistos) == 1
    assert tela.findChildren(PinPadDialog) == []


# ---------------------------------------------------------------------------
# 4b. Excluir o PRODUTO — apagado num clique, ou arquivado com a Senha Master
# ---------------------------------------------------------------------------


def _vender(uow, gerente, caixa_aberto, produto_id: int) -> None:
    from datetime import datetime

    from gestor_comercial.domain.comanda import Comanda
    from gestor_comercial.domain.item_comanda import ItemComanda

    comanda = uow.comandas.salvar(
        Comanda(
            aberta_em=datetime(2026, 9, 14, 12, 0),
            usuario_id=gerente.id,
            caixa_id=caixa_aberto.id,
        )
    )
    uow.itens.salvar(
        ItemComanda(
            quantidade=1,
            preco_unit_congelado=Decimal("16.00"),
            comanda_id=comanda.id,
            produto_id=produto_id,
        )
    )


def _id_do_produto(cardapio, nome: str) -> int:
    return next(p.id for p in cardapio.listar_produtos() if p.nome == nome)


def test_produto_sem_historico_sai_com_a_confirmacao_simples(qapp, tela, cardapio, uow):
    """A Foto 2: sem venda e sem combo, um clique no cartão e a linha sai do
    banco — o DELETE físico, pelo `excluir_produto` de sempre."""
    produto_id = _id_do_produto(cardapio, "X Tudo")
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Tudo")

    vistos = encenar(
        qapp, tela, [("cartao", "confirmar")], tela._painel_produtos._botao_excluir.click
    )

    assert vistos == [
        "AÇÃO PERMANENTE | Excluir produto | X Tudo | "
        "Deseja excluir este produto permanentemente? | "
        "Esta ação não pode ser desfeita. | Excluir produto"
    ]
    assert uow.produtos.buscar_por_id(produto_id) is None


def test_produto_vendido_pede_a_senha_master_e_e_arquivado(
    qapp, tela, cardapio, uow, gerente, caixa_aberto
):
    """Até o §9.17 este gesto terminava num "Desative-o" DEPOIS do "Sim". Agora
    o cartão sabe antes, e a linha fica no banco para a venda passada."""
    produto_id = _id_do_produto(cardapio, "X Tudo")
    _vender(uow, gerente, caixa_aberto, produto_id)
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Tudo")

    vistos = encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_MASTER)],
        tela._painel_produtos._botao_excluir.click,
    )

    assert vistos[0].startswith("EXCLUSÃO PROTEGIDA | Excluir produto | X Tudo | ")
    assert "Este produto tem vendas registradas." in vistos[0]
    assert vistos[1] == "Confirmar Exclusão"
    guardado = uow.produtos.buscar_por_id(produto_id)
    assert (guardado.arquivado, guardado.ativo) == (True, False)
    assert "X Tudo" not in [p.nome for p in cardapio.listar_produtos()]
    # Nenhuma recusa do service chegou à linha vermelha da tela.
    assert tela._label_erro.text() == ""


def test_produto_vendido_com_a_senha_operacional_fica_onde_esta(
    qapp, tela, cardapio, uow, gerente, caixa_aberto
):
    produto_id = _id_do_produto(cardapio, "X Tudo")
    _vender(uow, gerente, caixa_aberto, produto_id)
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Tudo")

    encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_OPERACIONAL), ("cartao", "cancelar")],
        tela._painel_produtos._botao_excluir.click,
    )

    assert uow.produtos.buscar_por_id(produto_id).arquivado is False
    assert "X Tudo" in [p.nome for p in cardapio.listar_produtos()]


def test_componente_de_combo_avisa_e_sai_da_composicao(qapp, tela, cardapio, uow):
    """Arquivar um componente mexe num combo que ninguém mandou excluir — e o
    cartão diz isso antes de a Senha Master ser digitada."""
    lanches = next(c for c in cardapio.listar_categorias() if c.nome == "Lanches")
    combo = cardapio.criar_produto("Combo X", Decimal("25.00"), lanches.id)
    x_tudo_id = _id_do_produto(cardapio, "X Tudo")
    cardapio.associar_componente(combo.id, x_tudo_id, 1)
    tela.atualizar()
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Tudo")

    vistos = encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_MASTER)],
        tela._painel_produtos._botao_excluir.click,
    )

    assert "Este produto faz parte de 1 combo." in vistos[0]
    assert "Ele sai da composição de 1 combo." in vistos[0]
    assert cardapio.listar_componentes(combo.id) == []
    assert uow.produtos.buscar_por_id(x_tudo_id).arquivado is True


def test_a_selecao_volta_para_a_subdivisao_do_produto_excluido(qapp, tela, cardapio):
    """O nó pai fica: excluir um produto não leva o gerente para outra
    categoria nem para outra subdivisão."""
    _escolher_subdivisao(tela, "Lanches", "Podrão")
    _selecionar_produto(tela, "X Tudo")

    encenar(qapp, tela, [("cartao", "confirmar")], tela._painel_produtos._botao_excluir.click)

    selecao = tela._painel_categorias.selecao_atual()
    assert (selecao.categoria.nome, selecao.chave) == ("Lanches", "Podrão")
    assert _rodape(tela)["rotulo"] == "SUBCATEGORIA: PODRÃO"


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
# 6b. Excluir a CATEGORIA — as mesmas duas barreiras, um nível acima (§9.14)
# ---------------------------------------------------------------------------


def test_categoria_vazia_sai_com_uma_confirmacao(qapp, tela, cardapio):
    """"Vazia" aqui é mais estrito: nem produto, nem subdivisão."""
    vazia = cardapio.criar_categoria("Sobremesas")
    tela.atualizar()
    _abrir(tela, "Sobremesas")

    vistos = encenar(
        qapp, tela, [("cartao", "confirmar")], tela._painel_produtos._botao_excluir.click
    )

    assert vistos[0].startswith("AÇÃO PERMANENTE | Excluir categoria | Sobremesas | ")
    assert "Deseja excluir esta categoria?" in vistos[0]
    assert vazia.nome not in [c.nome for c in cardapio.listar_categorias()]


def test_categoria_com_conteudo_avisa_e_exige_a_senha_master(qapp, tela, cardapio):
    """O aviso soma as duas parcelas: é o tamanho do que vai sair."""
    _abrir(tela, "Lanches")

    vistos = encenar(
        qapp, tela, [("cartao", "cancelar")], tela._painel_produtos._botao_excluir.click
    )

    assert vistos[0].startswith("EXCLUSÃO PROTEGIDA | Excluir categoria | Lanches | ")
    assert "Esta categoria contém 3 produtos e 2 subcategorias." in vistos[0]
    assert vistos[0].endswith("| Excluir com Senha Master")
    assert [c.nome for c in cardapio.listar_categorias()] == ["Bebidas", "Lanches"]


def test_a_senha_master_apaga_a_categoria_inteira(qapp, tela, cardapio):
    """Nada foi vendido neste cenário: sai tudo do banco, de verdade."""
    _abrir(tela, "Lanches")

    vistos = encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_MASTER)],
        tela._painel_produtos._botao_excluir.click,
    )

    assert vistos[1] == "Confirmar Exclusão"
    assert [c.nome for c in cardapio.listar_categorias()] == ["Bebidas"]
    assert [p.nome for p in cardapio.listar_produtos()] == ["Coca Lata"]
    assert cardapio.listar_todas_as_subcategorias() == []


def test_a_senha_operacional_nao_apaga_a_categoria(qapp, tela, cardapio):
    _abrir(tela, "Lanches")

    encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_OPERACIONAL), ("cartao", "cancelar")],
        tela._painel_produtos._botao_excluir.click,
    )

    assert [c.nome for c in cardapio.listar_categorias()] == ["Bebidas", "Lanches"]


def test_depois_de_excluir_a_categoria_a_arvore_recomeca(qapp, tela, cardapio):
    """Não há "mesmo lugar" para onde voltar: a categoria em que o gerente
    estava deixou de existir."""
    _abrir(tela, "Lanches")

    encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_MASTER)],
        tela._painel_produtos._botao_excluir.click,
    )

    selecao = tela._painel_categorias.selecao_atual()
    assert selecao.categoria is not None and selecao.categoria.nome == "Bebidas"
    assert _rodape(tela)["rotulo"] == "CATEGORIA: BEBIDAS"


def test_a_categoria_guardada_some_da_arvore(qapp, tela, cardapio, uow, gerente, caixa_aberto):
    """O caso em que a linha precisa ficar no banco: para o gerente, some igual."""
    from datetime import datetime

    from gestor_comercial.domain.comanda import Comanda
    from gestor_comercial.domain.item_comanda import ItemComanda

    vendido = next(p for p in cardapio.listar_produtos() if p.nome == "X Burguer")
    comanda = uow.comandas.salvar(
        Comanda(
            aberta_em=datetime(2026, 9, 12, 12, 0),
            usuario_id=gerente.id,
            caixa_id=caixa_aberto.id,
        )
    )
    uow.itens.salvar(
        ItemComanda(
            quantidade=1,
            preco_unit_congelado=vendido.preco,
            comanda_id=comanda.id,
            produto_id=vendido.id,
        )
    )
    tela.atualizar()
    _abrir(tela, "Lanches")

    encenar(
        qapp,
        tela,
        [("cartao", "confirmar"), ("pin", PIN_MASTER)],
        tela._painel_produtos._botao_excluir.click,
    )

    assert [c.nome for c in cardapio.listar_categorias()] == ["Bebidas"]
    assert uow.categorias.buscar_por_id(vendido.categoria_id).arquivado is True
    with pytest.raises(AssertionError):
        _item_categoria(tela, "Lanches")


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
        encenar(qapp, tela, [("cartao", "confirmar")], tela._painel_produtos._botao_excluir.click)

    assentar()
    assert [s.nome for s in cardapio.listar_subcategorias(lanches.id)] == [
        "Combo pastel",
        "Podrão",
    ]
    assert len(tela.findChildren(QWidget)) == antes


def test_cartao_e_pin_nao_ficam_presos_a_tela_nem_escurecem_a_janela(
    qapp, tela, cardapio, cardapio_montado, assentar
):
    """Os caminhos que mais criam diálogo: o cartão com o PIN por cima, o PIN
    recusado que devolve ao cartão, e o cancelamento. Nada disso pode sobrar —
    nem diálogo pendurado na view, nem escurecedor pendurado na janela, que
    vive o turno inteiro."""
    tela.show()
    _abrir(tela, "Lanches")
    assentar()
    antes = len(tela.findChildren(QWidget))
    lanches = cardapio_montado["lanches"]

    for numero in range(4):
        vazia = cardapio.criar_subcategoria(lanches.id, f"Vazia {numero}")
        cheia = cardapio.criar_subcategoria(lanches.id, f"Cheia {numero}")
        cardapio.criar_produto(f"Item {numero}", Decimal("5.00"), lanches.id, subcategoria_id=cheia.id)
        tela.atualizar()
        _escolher_subdivisao(tela, "Lanches", vazia.nome)
        encenar(qapp, tela, [("cartao", "cancelar")], tela._painel_produtos._botao_excluir.click)
        encenar(qapp, tela, [("cartao", "confirmar")], tela._painel_produtos._botao_excluir.click)
        _escolher_subdivisao(tela, "Lanches", cheia.nome)
        encenar(
            qapp,
            tela,
            [("cartao", "confirmar"), ("pin", PIN_OPERACIONAL), ("cartao", "confirmar"), ("pin", PIN_MASTER)],
            tela._painel_produtos._botao_excluir.click,
        )

    assentar()
    assert [s.nome for s in cardapio.listar_subcategorias(lanches.id)] == ["Combo pastel", "Podrão"]
    assert tela.findChildren(QDialog) == []
    assert tela.window().findChildren(Backdrop) == []
    assert len(tela.findChildren(QWidget)) == antes
