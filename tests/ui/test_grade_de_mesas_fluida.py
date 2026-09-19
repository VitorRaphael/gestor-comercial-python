"""A grade de mesas cabe na largura da tela: nenhuma rolagem para o lado. Ver §9.24.

Até 2026-09-19 a grade era um `QGridLayout` com 8 colunas fixas. Com o cartão
no mínimo de 96px ela pedia 884px de largura, e a 1366px (o monitor do food
truck, com a sidebar e o painel do salão) a área só oferece 710: a sétima
coluna saía cortada, a oitava ficava inteira atrás de uma barra de rolagem
horizontal, e o operador precisava rolar para o lado para achar a mesa 8, a 16,
a 24... O defeito estava registrado desde o §9.5.

Agora a grade é uma `GradeFluida`: o número de colunas sai da largura do
momento, e as células se esticam até a borda. Este arquivo cobre as duas
metades:

* **o layout sozinho**, com widgets de mentira e medidas redondas, varrendo
  mais de duzentas larguras (a regra tem que valer em qualquer monitor, e não
  só nos que alguém lembrou de testar);
* **a tela de Mesas de verdade**, com as sessenta mesas do salão, nas larguras
  que a página de conteúdo tem nas resoluções comuns de notebook e de monitor
  de PDV.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from gestor_comercial.domain.mesa import Mesa
from gestor_comercial.ui.views.mesas_view import MesasView, _CartaoMesa
from gestor_comercial.ui.widgets.flow_layout import GradeFluida

# ----------------------------------------------------------------------
# O layout sozinho
# ----------------------------------------------------------------------

MARGEM = 9
ESPACO = 14
CELULA = QSize(100, 50)
# De uma célula só até um monitor largo, de 7 em 7px: passa por todas as
# viradas de coluna (a cada 114px) e por larguras que não caem em nenhuma.
LARGURAS = range(CELULA.width() + 2 * MARGEM, 1701, 7)
# Itens bastantes para a primeira fileira encher até a borda mesmo na maior
# largura (14 colunas a 1700px).
ITENS = 30


def _item(minimo: QSize = CELULA) -> QWidget:
    """Um widget que se comporta como o cartão de mesa: largura elástica a
    partir de um mínimo, altura fixa."""
    widget = QWidget()
    widget.setMinimumSize(minimo)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return widget


@pytest.fixture
def grade(qapp):
    moldura = QWidget()
    layout = GradeFluida(moldura, margin=MARGEM, spacing=ESPACO)
    itens = [_item() for _ in range(ITENS)]
    layout.repovoar(itens)
    yield layout, itens
    moldura.deleteLater()


def _posicionar(layout: GradeFluida, largura: int) -> None:
    """Dá à grade a largura pedida e a altura que ela mesma diz precisar —
    exatamente o que a `QScrollArea` faz com o conteúdo."""
    layout.setGeometry(QRect(0, 0, largura, layout.heightForWidth(largura)))


def _colunas(widgets: list[QWidget]) -> int:
    return len({w.x() for w in widgets})


def test_a_ultima_coluna_termina_exatamente_na_margem_direita(grade):
    """Nem passa da borda (seria o corte, ou a barra horizontal de volta), nem
    para antes dela (seria uma faixa vazia à direita, a sobra irregular que a
    grade existe para não ter)."""
    layout, itens = grade
    for largura in LARGURAS:
        _posicionar(layout, largura)
        direita = max(w.x() + w.width() for w in itens)
        assert direita == largura - MARGEM, f"a {largura}px a grade termina em {direita}"


def test_as_celulas_tem_todas_a_mesma_largura(grade):
    """A divisão da largura raramente é exata; a sobra vai 1px para cada uma
    das primeiras colunas. Mais que isso seria uma coluna visivelmente mais
    larga que as outras."""
    layout, itens = grade
    for largura in LARGURAS:
        _posicionar(layout, largura)
        larguras = {w.width() for w in itens}
        assert max(larguras) - min(larguras) <= 1, f"a {largura}px: {sorted(larguras)}"


def test_o_espaco_entre_cartoes_e_sempre_o_mesmo(grade):
    """A sobra de pixels tem que ir para a LARGURA das primeiras colunas, e não
    para o vão entre elas: a borda direita sairia certa do mesmo jeito, mas a
    grade ficaria com vãos de 14 e de 15px misturados na mesma fileira."""
    layout, itens = grade
    for largura in LARGURAS:
        _posicionar(layout, largura)
        fileiras: dict[int, list[QWidget]] = {}
        for widget in itens:
            fileiras.setdefault(widget.y(), []).append(widget)
        for fileira in fileiras.values():
            fileira.sort(key=QWidget.x)
            vaos = {b.x() - (a.x() + a.width()) for a, b in zip(fileira, fileira[1:])}
            assert vaos <= {ESPACO}, f"a {largura}px: vãos {sorted(vaos)}"


def test_o_numero_de_colunas_e_o_maior_que_cabe_sem_espremer_a_celula(grade):
    layout, itens = grade
    for largura in LARGURAS:
        _posicionar(layout, largura)
        colunas = _colunas(itens)
        assert min(w.width() for w in itens) >= CELULA.width(), f"a {largura}px uma célula ficou espremida"
        area = largura - 2 * MARGEM
        uma_a_mais = (area - colunas * ESPACO) / (colunas + 1)
        assert uma_a_mais < CELULA.width(), f"a {largura}px cabiam {colunas + 1} colunas e a grade usou {colunas}"


def test_a_altura_pedida_e_a_altura_que_a_grade_ocupa(grade):
    """É pelo `heightForWidth` que a `QScrollArea` sabe até onde rolar: se ele
    pedir menos que a grade ocupa, a última fileira de mesas fica inalcançável;
    se pedir mais, sobra rolagem para o vazio."""
    layout, itens = grade
    for largura in LARGURAS:
        _posicionar(layout, largura)
        fundo = max(w.y() + w.height() for w in itens) + MARGEM
        assert layout.heightForWidth(largura) == fundo, f"a {largura}px"


def test_o_minimo_da_grade_e_uma_celula_so(grade):
    """É isto que torna a rolagem horizontal impossível, e não só escondida:
    a `QScrollArea` só rola para o lado quando o mínimo do conteúdo passa da
    largura da área, e o mínimo aqui é um cartão. O `QGridLayout` de 8
    colunas tinha mínimo de oito cartões."""
    layout, _ = grade
    assert layout.minimumSize() == CELULA + QSize(2 * MARGEM, 2 * MARGEM)


def test_a_celula_nao_depende_de_quantos_itens_ha(qapp, grade):
    """Filtrar a grade para duas mesas não pode transformar as duas em
    cartões gigantes: a célula é a mesma com 2 itens e com 30."""
    layout, itens = grade
    _posicionar(layout, 1000)
    largura_cheia = itens[0].width()

    poucos = [_item(), _item()]
    layout.repovoar(poucos)
    _posicionar(layout, 1000)
    assert [w.width() for w in poucos] == [largura_cheia, largura_cheia]


class _ItemQuePedeMais(QWidget):
    """Um cartão cujo conteúdo pede o triplo do mínimo — como o de uma mesa
    com "R$ 9.999,99" ou um atendente de nome comprido. Por `sizeHint`, e não
    por um texto de verdade: a plataforma `offscreen` sobe sem fontes e ali
    todo texto mede quase nada."""

    def sizeHint(self) -> QSize:  # noqa: N802 (override Qt)
        return QSize(3 * CELULA.width(), CELULA.height())


def test_a_celula_vem_do_minimo_do_cartao_e_nao_do_conteudo(qapp, grade):
    """Uma mesa que abre com um valor alto ou com um nome comprido NÃO
    reorganiza a grade. Se a célula seguisse o conteúdo, bastaria uma comanda
    de R$ 1.000 para a grade inteira perder uma coluna, e a mesa 7, que estava
    embaixo da 1, pularia para o lado da 6: o operador acha a mesa pela
    posição, e a posição não pode depender do que tem dentro dela. Quem
    decide quanto o cartão precisa é o mínimo dele (`LARGURA_MINIMA_PX`)."""
    layout, itens = grade
    _posicionar(layout, 1000)
    antes = _colunas(itens)

    comprido = _ItemQuePedeMais()
    comprido.setMinimumSize(CELULA)
    comprido.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    layout.repovoar([*[_item() for _ in range(ITENS - 1)], comprido])
    _posicionar(layout, 1000)
    assert _colunas([layout.itemAt(i).widget() for i in range(layout.count())]) == antes


def test_por_e_tirar_o_item_mais_largo_muda_a_medida(qapp, grade):
    """A medida guardada vale para o conjunto de itens em que foi tirada. Pôr
    um widget numa grade que não está na tela e tirar um com `takeAt` não
    passam pelo Qt (nada é exibido, e o tirado continua filho e visível),
    então é o próprio layout que tem que esquecê-la nas duas pontas."""
    layout, _ = grade
    assert layout.minimumSize().width() == CELULA.width() + 2 * MARGEM

    layout.addWidget(_item(QSize(300, 50)))
    assert layout.minimumSize().width() == 300 + 2 * MARGEM

    layout.takeAt(layout.count() - 1)
    assert layout.minimumSize().width() == CELULA.width() + 2 * MARGEM


def test_repovoar_troca_o_conteudo_inteiro(grade):
    layout, antigos = grade
    novos = [_item() for _ in range(5)]
    layout.repovoar(novos)
    assert layout.count() == 5
    assert [layout.itemAt(i).widget() for i in range(5)] == novos
    assert all(w.parent() is None for w in antigos), "o antigo continuaria desenhado por baixo do novo"


def test_a_medida_acompanha_um_item_que_mudou_de_tamanho(qapp, grade):
    """A medida da célula fica guardada (é o que deixa o redimensionamento
    barato). Guardada demais seria pior que não guardar: um cartão que passa a
    precisar de mais largura, com a grade ainda usando a medida velha, sairia
    cortado. Quem avisa a grade é o próprio Qt, invalidando o layout."""
    layout, itens = grade
    _posicionar(layout, 700)
    assert _colunas(itens) == 6

    for widget in itens:
        widget.setMinimumWidth(200)
    _posicionar(layout, 700)
    assert _colunas(itens) == 3
    assert min(w.width() for w in itens) >= 200


class _GradeQueContaRelayouts(GradeFluida):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.relayouts = 0

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 (override Qt)
        self.relayouts += 1
        super().setGeometry(rect)


def test_repovoar_uma_grade_visivel_refaz_o_layout_uma_vez_so(qapp):
    """Widget novo num pai visível ganha um `show()` agendado, e cada `show()`
    refaz o layout do pai na hora. Sem o lote do `repovoar`, trocar as
    sessenta mesas custava 61 relayouts completos (medido): 3.600
    posicionamentos para pôr 60 cartões no lugar."""
    moldura = QWidget()
    layout = _GradeQueContaRelayouts(moldura, margin=MARGEM, spacing=ESPACO)
    moldura.resize(1000, 600)
    moldura.show()
    qapp.processEvents()

    layout.relayouts = 0
    layout.repovoar([_item() for _ in range(60)])
    for _ in range(5):
        qapp.processEvents()

    assert layout.relayouts == 1
    moldura.close()
    moldura.deleteLater()


# ----------------------------------------------------------------------
# A tela de Mesas
# ----------------------------------------------------------------------

MESAS_DO_SALAO = 60
ALTURA_DA_PAGINA_PX = 690
# A largura da página de conteúdo em cada resolução: a janela maximizada,
# menos a sidebar (212px) e as margens da coluna de conteúdo (24px de cada
# lado) — `MainWindow._montar_shell`. É dentro dela que a tela de Mesas mora.
PAGINAS = {
    "1280": 1280 - 212 - 48,
    "1366": 1366 - 212 - 48,
    "1440": 1440 - 212 - 48,
    "1600": 1600 - 212 - 48,
    "1920": 1920 - 212 - 48,
}


@pytest.fixture
def salao(qapp, comandas, gerente, produto, caixa_aberto, uow):
    """As sessenta mesas do food truck, uma delas ocupada, numa página de
    conteúdo do tamanho que a janela tem."""
    mesas = [uow.mesas.salvar(Mesa(numero=numero)) for numero in range(1, MESAS_DO_SALAO + 1)]
    comanda = comandas.abrir_por_mesa(mesas[2].id)
    comandas.lancar_item(comanda.id, produto.id, 2)

    pagina = QWidget()
    layout = QVBoxLayout(pagina)
    layout.setContentsMargins(0, 0, 0, 0)
    view = MesasView(comandas)
    layout.addWidget(view)
    pagina.show()
    yield pagina, view
    pagina.close()
    pagina.deleteLater()


def _na_largura(qapp, pagina: QWidget, largura: int) -> None:
    pagina.setFixedSize(largura, ALTURA_DA_PAGINA_PX)
    # Várias voltas: a `QScrollArea` só decide a barra vertical depois de o
    # layout de dentro se acomodar (mesmo cuidado de `test_mesas_ocupadas_
    # em_vermelho.py`).
    for _ in range(10):
        qapp.processEvents()


def _rolagem_da_grade(view: MesasView) -> QScrollArea:
    return next(r for r in view.findChildren(QScrollArea) if r.widget().findChildren(_CartaoMesa))


def _cartoes(view: MesasView) -> list[_CartaoMesa]:
    cartoes = _rolagem_da_grade(view).widget().findChildren(_CartaoMesa)
    assert len(cartoes) == MESAS_DO_SALAO
    return cartoes


@pytest.mark.parametrize("resolucao", PAGINAS)
def test_nenhuma_mesa_fica_atras_da_borda_direita(qapp, salao, resolucao):
    pagina, view = salao
    _na_largura(qapp, pagina, PAGINAS[resolucao])
    rolagem = _rolagem_da_grade(view)
    area = rolagem.viewport().width()

    cortadas = [c for c in _cartoes(view) if c.x() + c.width() > area]
    assert not cortadas, f"a {resolucao}px, {len(cortadas)} mesas passam da borda direita de {area}px"
    assert rolagem.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    # A barra está desligada, mas a faixa dela continua sendo calculada pelo
    # Qt: máximo zero é o conteúdo não tendo NADA para rolar de lado — e não
    # só a barra escondida em cima de um corte.
    assert rolagem.horizontalScrollBar().maximum() == 0
    assert rolagem.widget().width() == area


def test_a_largura_decide_quantas_colunas_a_grade_tem(qapp, salao):
    pagina, view = salao
    colunas = []
    for resolucao in ("1280", "1366", "1600", "1920"):
        _na_largura(qapp, pagina, PAGINAS[resolucao])
        colunas.append(_colunas(_cartoes(view)))
    assert colunas == sorted(colunas) and colunas[0] < colunas[-1], (
        f"colunas por resolução: {colunas} — a grade deveria ganhar colunas com a largura"
    )


def test_redimensionar_reposiciona_sem_recriar_cartao(qapp, salao):
    """Redimensionar é só aritmética e `setGeometry`: os sessenta cartões são
    os MESMOS objetos antes e depois. Recriar a cada redimensionamento seria
    polir sessenta widgets contra o QSS inteiro a cada arrasto da janela."""
    pagina, view = salao
    _na_largura(qapp, pagina, PAGINAS["1366"])
    antes = set(map(id, _cartoes(view)))

    for resolucao in ("1920", "1280", "1600", "1366"):
        _na_largura(qapp, pagina, PAGINAS[resolucao])
    assert set(map(id, _cartoes(view))) == antes


def test_a_ultima_mesa_e_alcancada_pela_rolagem_vertical(qapp, salao):
    pagina, view = salao
    _na_largura(qapp, pagina, PAGINAS["1366"])
    rolagem = _rolagem_da_grade(view)
    barra = rolagem.verticalScrollBar()
    assert barra.maximum() > 0, "sessenta mesas não cabem na altura: a rolagem vertical tinha que existir"

    barra.setValue(barra.maximum())
    qapp.processEvents()
    ultima = next(c for c in _cartoes(view) if c.findChildren(QLabel)[0].text() == str(MESAS_DO_SALAO))
    topo = ultima.mapTo(rolagem.viewport(), QPoint(0, 0)).y()
    assert topo >= 0
    assert topo + ultima.height() <= rolagem.viewport().height(), "a mesa 60 ficou abaixo do fim da rolagem"
