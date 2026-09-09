"""O modal "Adicionar item": busca, filtro por categoria, teclado e limpeza.

A tela que o pai do Vitor mais usa no turno é esta — é por ela que cada produto
entra na comanda. Os testes abaixo cobrem as três coisas que quebrariam o
balcão em silêncio:

1. **o item certo** — a lista mostra o que a busca e a pílula de categoria
   dizem, e o `Enter` lança a linha destacada. O caso mais sutil está em
   `test_enter_logo_apos_digitar_usa_o_filtro_novo`: a busca agrupa as teclas
   num timer, e sem adiantar esse timer o `Enter` lançaria o produto do filtro
   ANTERIOR — item errado na comanda, sem ninguém ver;
2. **o modal continua aberto** — lançar um item reseta quantidade e observação
   e devolve o foco à busca, sem fechar. É o fluxo rápido que existia no modal
   antigo e que uma refatoração de visual não pode ter derrubado;
3. **nada sobra na memória** — o RNF do Celeron. Depois de trinta aberturas, a
   view não pode ter um diálogo pendurado, e o `done()` tem que parar os dois
   timers e soltar o instantâneo do cardápio.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QWidget

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.domain.produto import Produto
from gestor_comercial.services.exceptions import RegraDeNegocioError
from gestor_comercial.ui.formatacao import formatar_reais
from gestor_comercial.ui.widgets.adicionar_item_dialog import AdicionarItemDialog
from gestor_comercial.ui.widgets.thumbnail_cache import FORMATO_CIRCULO, obter_pixmap


@pytest.fixture
def cardapio_de_teste(uow):
    """Três categorias, cinco produtos — o bastante para haver o que filtrar."""
    bebidas = uow.categorias.salvar(Categoria(nome="Bebidas"))
    porcoes = uow.categorias.salvar(Categoria(nome="Porções"))
    acompanhamentos = uow.categorias.salvar(Categoria(nome="Acompanhamentos"))
    dados = [
        ("Água sem gás", "4.00", bebidas.id, False),
        ("Coca-Cola Lata", "6.00", bebidas.id, False),
        ("Anel de Cebola", "12.00", porcoes.id, False),
        ("Aipim", "20.00", porcoes.id, False),
        ("Combo Família", "50.00", acompanhamentos.id, True),
    ]
    return [
        uow.produtos.salvar(
            Produto(
                nome=nome,
                preco=Decimal(preco),
                categoria_id=categoria_id,
                is_combo=combo,
            )
        )
        for nome, preco, categoria_id, combo in dados
    ]


class _Lancamentos:
    """Faz as vezes de `ComandaView._lancar_item_do_modal`, guardando as chamadas."""

    def __init__(self, erro: Exception | None = None) -> None:
        self.chamadas: list[tuple[int, int, str | None]] = []
        self._erro = erro

    def __call__(self, produto_id: int, quantidade: int, observacao: str | None) -> None:
        if self._erro is not None:
            raise self._erro
        self.chamadas.append((produto_id, quantidade, observacao))


@pytest.fixture
def abrir(qapp, cardapio_de_teste):
    """Monta o modal já filtrado, sem `exec()` — e o descarta no fim do teste."""
    criados: list[AdicionarItemDialog] = []

    def _abrir(lancar=None, contexto="Mesa 12", pai=None):
        modal = AdicionarItemDialog(
            cardapio_de_teste, contexto, lancar or _Lancamentos(), pai
        )
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        modal.deleteLater()


def _nomes(modal: AdicionarItemDialog) -> list[str]:
    return [
        modal._lista.item(indice).data(Qt.ItemDataRole.UserRole).nome
        for indice in range(modal._lista.count())
    ]


def _digitar(modal: AdicionarItemDialog, texto: str) -> None:
    """Digita na busca **sem** adiantar o timer — como o operador digita."""
    modal._campo_busca.setText(texto)


def _tecla(modal: AdicionarItemDialog, tecla: Qt.Key) -> None:
    modal.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


# ---------------------------------------------------------------------------
# Lista, busca e categorias
# ---------------------------------------------------------------------------


def test_abre_com_o_cardapio_inteiro_e_a_primeira_linha_destacada(abrir):
    modal = abrir()

    assert len(_nomes(modal)) == 5
    assert modal._lista.currentRow() == 0


def test_a_busca_ignora_acento_e_caixa(abrir):
    modal = abrir()

    _digitar(modal, "AGUA")
    modal._filtrar_agora()

    assert _nomes(modal) == ["Água sem gás"]


def test_a_pilula_de_categoria_filtra_a_lista(abrir):
    modal = abrir()

    modal._pills["Porções"].click()

    assert sorted(_nomes(modal)) == ["Aipim", "Anel de Cebola"]
    assert modal._pills["Porções"].property("ativa") is True
    assert modal._pills[""].property("ativa") is False


def test_todos_devolve_o_cardapio_inteiro(abrir):
    modal = abrir()
    modal._pills["Bebidas"].click()

    modal._pills[""].click()

    assert len(_nomes(modal)) == 5


def test_categoria_e_busca_valem_juntas(abrir):
    """Filtrar por categoria não pode desligar o que já foi digitado."""
    modal = abrir()
    _digitar(modal, "a")

    modal._pills["Bebidas"].click()

    assert _nomes(modal) == ["Água sem gás", "Coca-Cola Lata"]


def test_o_combo_aparece_nos_metadados_e_nao_no_nome(abrir):
    """O modal antigo colava `[COMBO]` no fim do nome; agora desce pra linha
    de baixo, e o nome fica limpo para a busca e para o cupom."""
    modal = abrir()
    _digitar(modal, "combo")
    modal._filtrar_agora()

    linha = modal._lista.item(0).data(Qt.ItemDataRole.UserRole)

    assert linha.nome == "Combo Família"
    assert linha.metadados == "ACOMPANHAMENTOS · COMBO"


def test_busca_sem_resultado_desliga_o_botao_adicionar(abrir):
    """Sem linha destacada não há o que lançar — e um botão que não faz nada
    é pior que um botão apagado."""
    modal = abrir()

    _digitar(modal, "pizza")
    modal._filtrar_agora()

    assert _nomes(modal) == []
    assert not modal._botao_confirmar.isEnabled()
    assert modal._label_resumo.text() == "SELECIONE UM PRODUTO"


# ---------------------------------------------------------------------------
# Miniatura
# ---------------------------------------------------------------------------


def test_produto_sem_foto_ganha_placeholder_circular_de_duas_letras(abrir):
    """A miniatura é requisito do briefing, e sem foto cadastrada ela não pode
    virar um quadrado vazio: o cache desenha a sigla do produto."""
    modal = abrir()
    linha = modal._lista.item(0).data(Qt.ItemDataRole.UserRole)

    pixmap = obter_pixmap(linha.imagem_path, 40, linha.nome, formato=FORMATO_CIRCULO)

    assert linha.imagem_path is None
    assert not pixmap.isNull()
    assert pixmap.size().width() == pixmap.size().height() == 40


def test_a_miniatura_redonda_e_a_quadrada_sao_entradas_diferentes(qapp):
    """O mesmo produto, no mesmo tamanho, sai redondo aqui e quadrado no
    Cardápio: são dois desenhos, e o cache não pode devolver um pelo outro."""
    redonda = obter_pixmap(None, 40, "Aipim", formato=FORMATO_CIRCULO)
    quadrada = obter_pixmap(None, 40, "Aipim")

    assert redonda is not quadrada


# ---------------------------------------------------------------------------
# Teclado
# ---------------------------------------------------------------------------


def test_setas_navegam_a_lista(abrir):
    modal = abrir()

    _tecla(modal, Qt.Key.Key_Down)
    assert modal._lista.currentRow() == 1

    _tecla(modal, Qt.Key.Key_Up)
    assert modal._lista.currentRow() == 0


def test_a_seta_para_cima_na_primeira_linha_nao_perde_a_selecao(abrir):
    modal = abrir()

    _tecla(modal, Qt.Key.Key_Up)

    assert modal._lista.currentRow() == 0


def test_enter_lanca_a_linha_destacada_com_quantidade_e_observacao(abrir):
    lancamentos = _Lancamentos()
    modal = abrir(lancamentos)
    _tecla(modal, Qt.Key.Key_Down)
    linha = modal._lista.currentItem().data(Qt.ItemDataRole.UserRole)
    modal._botao_mais.click()
    modal._campo_observacao.setText("  sem gelo  ")

    _tecla(modal, Qt.Key.Key_Return)

    assert lancamentos.chamadas == [(linha.produto_id, 2, "sem gelo")]


def test_enter_logo_apos_digitar_usa_o_filtro_novo(abrir):
    """O bug que `_garantir_filtro_aplicado()` existe para impedir.

    A busca agrupa as teclas num timer de ~60 ms. Quem digita o nome e bate
    `Enter` na mesma batida chega aqui com o timer ainda pendente — e sem
    adiantá-lo o modal lançaria o produto que estava destacado ANTES da
    digitação (a primeira linha do cardápio inteiro).
    """
    lancamentos = _Lancamentos()
    modal = abrir(lancamentos)
    destacado_antes = modal._lista.currentItem().data(Qt.ItemDataRole.UserRole)

    _digitar(modal, "aipim")  # timer pendente de propósito: nada de `_filtrar_agora()`
    assert modal._timer_filtro.isActive()
    _tecla(modal, Qt.Key.Key_Return)

    (produto_id, _quantidade, _observacao) = lancamentos.chamadas[0]
    assert produto_id != destacado_antes.produto_id, "lançou o produto do filtro antigo"
    assert _nomes(modal) == ["Aipim"] or modal._campo_busca.text() == ""


def test_duplo_clique_lanca_direto(abrir):
    lancamentos = _Lancamentos()
    modal = abrir(lancamentos)
    item = modal._lista.item(2)
    linha = item.data(Qt.ItemDataRole.UserRole)

    modal._ao_duplo_clique(item)

    assert lancamentos.chamadas == [(linha.produto_id, 1, None)]


def test_esc_fecha_o_modal(qapp, abrir):
    modal = abrir()
    modal.show()
    qapp.processEvents()

    _tecla(modal, Qt.Key.Key_Escape)

    assert not modal.isVisible()
    assert modal.result() == QDialog.DialogCode.Rejected


# ---------------------------------------------------------------------------
# Quantidade e prévia
# ---------------------------------------------------------------------------


def test_a_quantidade_nao_desce_abaixo_de_um(abrir):
    modal = abrir()

    modal._botao_menos.click()
    modal._botao_menos.click()

    assert modal._label_quantidade.text() == "1"
    assert not modal._botao_menos.isEnabled()


def test_o_total_da_previa_e_preco_vezes_quantidade(abrir):
    """Prévia visual, não cálculo de comanda — mas formatada pelo mesmo
    `formatar_reais` do resto do app (§3.8), senão a tela diverge do cupom."""
    modal = abrir()
    _digitar(modal, "aipim")
    modal._filtrar_agora()

    modal._botao_mais.click()
    modal._botao_mais.click()

    assert modal._label_total.text() == formatar_reais(Decimal("60.00"))
    assert modal._label_resumo.text() == "AIPIM"


# ---------------------------------------------------------------------------
# Fluxo de balcão
# ---------------------------------------------------------------------------


def test_lancar_mantem_o_modal_aberto_e_reseta_os_campos(qapp, abrir):
    """O ganho de velocidade do PDV: numa mesa de oito, o operador lança oito
    produtos sem reabrir a tela uma vez."""
    modal = abrir()
    modal.show()
    qapp.processEvents()
    modal._botao_mais.click()
    modal._campo_observacao.setText("sem cebola")

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.isVisible()
    assert modal._label_quantidade.text() == "1"
    assert modal._campo_observacao.text() == ""
    assert modal._campo_busca.text() == ""
    assert modal._campo_busca.hasFocus()


def test_lancar_avisa_o_que_entrou_na_comanda(abrir):
    modal = abrir()

    _tecla(modal, Qt.Key.Key_Return)

    assert modal._label_aviso.property("estado") == "sucesso"
    assert "LANÇADO" in modal._label_aviso.text()


def test_erro_de_regra_de_negocio_vira_aviso_e_nao_fecha(qapp, abrir):
    """A comanda pode ter sido fechada entre um lançamento e outro. Quem decide
    sair da tela continua sendo o operador — o modal só conta o que houve."""
    modal = abrir(_Lancamentos(erro=RegraDeNegocioError("Comanda já fechada.")))
    modal.show()
    qapp.processEvents()

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.isVisible()
    assert modal._label_aviso.property("estado") == "erro"
    assert "COMANDA JÁ FECHADA." in modal._label_aviso.text()


def test_o_aviso_de_erro_nao_some_sozinho(abrir):
    """Só o aviso de sucesso tem prazo: erro que some sozinho é como um item
    deixa de ser lançado sem ninguém perceber."""
    modal = abrir(_Lancamentos(erro=RegraDeNegocioError("Comanda já fechada.")))

    _tecla(modal, Qt.Key.Key_Return)

    assert not modal._timer_aviso.isActive()


def test_o_contexto_da_comanda_aparece_no_cabecalho(abrir):
    """`Mesa 12` ou `Balcão` — o mesmo texto do título da tela de comanda, para
    o operador saber em qual conta está lançando antes de apertar."""
    modal = abrir(contexto="Balcão")

    rotulos = [
        filho.text()
        for filho in modal.findChildren(QLabel)
        if filho.objectName() == "addItemContexto"
    ]

    assert rotulos == ["BALCÃO · LANÇAMENTO RÁPIDO"]


# ---------------------------------------------------------------------------
# Sub-modelo (§9.8)
# ---------------------------------------------------------------------------
#
# No balcão o sub-modelo tem UM trabalho: dizer, em um segundo, qual das
# variações do mesmo tipo de item está destacada. Ele entra na linha de
# metadados e na busca — e em nenhum outro lugar. Não há pílula de sub-modelo
# aqui de propósito: o filtro em pílulas é por CATEGORIA, que é o eixo da
# impressora, e uma segunda fileira custaria altura num cartão medido contra os
# 728px úteis de um monitor de 768px.


@pytest.fixture
def cardapio_com_submodelo(uow):
    """Uma categoria, três porções — duas do mesmo sub-modelo e uma solta."""
    porcoes = uow.categorias.salvar(Categoria(nome="Porções"))
    dados = [
        ("Aipim", "20.00", "Fritas"),
        ("Batata Frita", "18.00", "Fritas"),
        ("Anel de Cebola", "12.00", None),
    ]
    return [
        uow.produtos.salvar(
            Produto(
                nome=nome,
                preco=Decimal(preco),
                categoria_id=porcoes.id,
                subcategoria=submodelo,
            )
        )
        for nome, preco, submodelo in dados
    ]


@pytest.fixture
def abrir_com_submodelo(qapp, cardapio_com_submodelo):
    criados: list[AdicionarItemDialog] = []

    def _abrir():
        modal = AdicionarItemDialog(cardapio_com_submodelo, "Mesa 3", _Lancamentos())
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        modal.deleteLater()


def _linha(modal: AdicionarItemDialog, indice: int):
    return modal._lista.item(indice).data(Qt.ItemDataRole.UserRole)


def test_o_submodelo_entra_nos_metadados_depois_da_categoria(abrir_com_submodelo):
    """O exemplo do pedido: `Aipim — R$ 20,00 · Porções / Fritas`. Aqui o
    caminho sai com o mesmo `·` que a linha já usava — duas pontuações
    diferentes numa linha de 9px seriam ruído, não hierarquia."""
    modal = abrir_com_submodelo()
    _digitar(modal, "aipim")
    modal._filtrar_agora()

    linha = _linha(modal, 0)

    assert linha.nome == "Aipim"
    assert linha.metadados == "PORÇÕES · FRITAS"


def test_produto_sem_submodelo_mostra_so_a_categoria(abrir_com_submodelo):
    """A garantia do "não mudou nada": o cardápio de hoje inteiro está assim."""
    modal = abrir_com_submodelo()
    _digitar(modal, "cebola")
    modal._filtrar_agora()

    assert _linha(modal, 0).metadados == "PORÇÕES"


def test_o_combo_continua_por_ultimo_na_linha(qapp, uow):
    """Categoria, sub-modelo e COMBO na mesma linha: do grupo maior para o
    menor, com a etiqueta de venda no fim."""
    categoria = uow.categorias.salvar(Categoria(nome="Porções"))
    combo = uow.produtos.salvar(
        Produto(
            nome="Combo Fritas",
            preco=Decimal("15.00"),
            categoria_id=categoria.id,
            subcategoria="Fritas",
            is_combo=True,
        )
    )
    modal = AdicionarItemDialog([combo], "Mesa 1", _Lancamentos())

    try:
        assert _linha(modal, 0).metadados == "PORÇÕES · FRITAS · COMBO"
    finally:
        modal.deleteLater()


def test_a_busca_acha_pelo_submodelo(abrir_com_submodelo):
    """O pedido do §9.8, no caminho que o operador percorre: "fritas" traz as
    duas porções desse sub-modelo, e a palavra não está no nome do Aipim."""
    modal = abrir_com_submodelo()

    _digitar(modal, "fritas")
    modal._filtrar_agora()

    assert sorted(_nomes(modal)) == ["Aipim", "Batata Frita"]


def test_a_busca_pelo_submodelo_nao_vai_ao_banco(abrir_com_submodelo, uow):
    """O sub-modelo não pode ter reaberto o caminho que o §9.4 fechou.

    O instantâneo existe para a digitação não tocar o SQLAlchemy — e o commit
    de um lançamento expira as instâncias, então ler `produto.subcategoria` na
    tecla voltaria a bater no banco depois de cada item lançado. Aqui as
    instâncias são expiradas de propósito e a busca segue funcionando: se ela
    ainda dependesse do banco, o teste passaria mesmo assim, mas a contagem
    abaixo denunciaria.
    """
    from sqlalchemy import event

    modal = abrir_com_submodelo()
    uow.session.expire_all()

    consultas = {"n": 0}

    def _contar(*_args, **_kwargs) -> None:
        consultas["n"] += 1

    event.listen(uow.session.bind, "before_cursor_execute", _contar)
    try:
        _digitar(modal, "fritas")
        modal._filtrar_agora()
    finally:
        event.remove(uow.session.bind, "before_cursor_execute", _contar)

    assert sorted(_nomes(modal)) == ["Aipim", "Batata Frita"]
    assert consultas["n"] == 0, f"a busca por sub-modelo foi ao banco {consultas['n']}x"


# ---------------------------------------------------------------------------
# O cartão continua cabendo na tela
# ---------------------------------------------------------------------------


def test_a_faixa_de_categorias_nao_passa_do_teto_de_fileiras(qapp, uow):
    """O defeito que a primeira renderização com o cardápio REAL mostrou.

    A suíte passava verde com cinco produtos de teste; com as quinze categorias
    do food truck, o `FlowLayout` quebrava em seis fileiras, o `QVBoxLayout`
    reservava a altura de UMA (é o que `FlowLayout.sizeHint()` devolve) e as
    outras cinco eram pintadas por cima da lista de produtos. No monitor de
    768px o cartão inteiro sairia da tela.

    O que segura é a área de rolagem em volta da faixa, e é a altura dela que
    este teste mede — não pixels absolutos, que a plataforma `offscreen` mede
    diferente por não ter banco de fontes.
    """
    categorias = [
        uow.categorias.salvar(Categoria(nome=f"Categoria {indice:02d}"))
        for indice in range(15)
    ]
    produtos = [
        uow.produtos.salvar(
            Produto(nome=f"Produto {indice:02d}", preco=Decimal("9.00"), categoria_id=c.id)
        )
        for indice, c in enumerate(categorias)
    ]

    modal = AdicionarItemDialog(produtos, "Mesa 1", _Lancamentos())
    modal.show()
    qapp.processEvents()

    altura_fileira = max(pill.sizeHint().height() for pill in modal._pills.values())
    espaco = modal._faixa_categorias.layout().spacing()
    teto = modal.FILEIRAS_DE_CATEGORIA * altura_fileira + espaco

    assert len(modal._pills) == 16, "TODOS + uma pílula por categoria"
    assert modal._rolagem_categorias.height() <= teto, (
        "a faixa de categorias passou do teto de fileiras e vai empurrar a "
        "lista de produtos para fora do cartão"
    )
    modal.reject()
    modal.deleteLater()


def test_a_lista_de_produtos_mantem_a_altura_com_o_cardapio_cheio(qapp, uow):
    """A outra metade: a faixa pode rolar, a lista não pode encolher — é ela
    que mostra o produto, e com duas linhas visíveis a busca perde a graça."""
    categoria = uow.categorias.salvar(Categoria(nome="Única"))
    produtos = [
        uow.produtos.salvar(
            Produto(nome=f"Produto {indice:03d}", preco=Decimal("9.00"), categoria_id=categoria.id)
        )
        for indice in range(113)
    ]

    modal = AdicionarItemDialog(produtos, "Mesa 1", _Lancamentos())
    modal.show()
    qapp.processEvents()

    assert modal._lista.height() == modal.ALTURA_LISTA_PX
    modal.reject()
    modal.deleteLater()


# ---------------------------------------------------------------------------
# Ciclo de vida (§3.2/§3.9 e o RNF do Celeron)
# ---------------------------------------------------------------------------


def test_fechar_para_os_timers_e_solta_o_cardapio(qapp, abrir):
    """A limpeza obrigatória do briefing, medida: nenhum timer pendente pode
    sobreviver ao fechamento, e o instantâneo do cardápio não pode ficar na
    memória de uma máquina de 4 GB depois que a tela sumiu."""
    modal = abrir()
    modal.show()
    qapp.processEvents()
    _digitar(modal, "aipim")  # deixa o timer de filtro pendente
    modal._avisar("TESTE", "sucesso")  # e o de aviso também
    assert modal._timer_filtro.isActive() and modal._timer_aviso.isActive()

    modal.reject()

    assert not modal._timer_filtro.isActive()
    assert not modal._timer_aviso.isActive()
    assert modal._lista.count() == 0
    assert modal._linhas == []


def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar, cardapio_de_teste):
    """O escurecedor é filho da JANELA, não do diálogo: se `done()` não o
    soltar, cada ida ao modal deixa um véu invisível pendurado na `MainWindow`,
    que vive o processo inteiro."""
    from gestor_comercial.ui.widgets.cartao_modal import Backdrop

    janela = QWidget()
    janela.resize(1000, 700)

    for _ in range(10):
        modal = AdicionarItemDialog(cardapio_de_teste, "Mesa 1", _Lancamentos(), janela)
        modal.show()
        qapp.processEvents()
        assert len(janela.findChildren(Backdrop)) == 1
        modal.reject()
        modal.deleteLater()
    assentar()

    assert janela.findChildren(Backdrop) == []


def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar, cardapio_de_teste):
    """O caminho real do app: aberto com `exec()` e fechado pelo botão."""
    pai = QWidget()

    for _ in range(30):
        modal = AdicionarItemDialog(cardapio_de_teste, "Mesa 1", _Lancamentos(), pai)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        del modal
    assentar()

    assert pai.findChildren(AdicionarItemDialog) == []
