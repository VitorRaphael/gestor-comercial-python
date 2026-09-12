"""O cartão dos dois níveis do cardápio: contexto, validação e limpeza. §9.12.

O §9.9 tinha um cartão para a subcategoria e um formulário de fábrica para a
categoria. O §9.12 juntou os dois num modal só, parametrizado por
`NivelDoCardapio` — e é justamente essa unificação que estes testes precisam
segurar, porque o jeito de ela apodrecer é silencioso: alguém acrescenta um
`if nivel is CATEGORIA` no meio da montagem e, seis meses depois, existem duas
telas de novo sem ninguém ter decidido isso.

Por isso quase tudo aqui é `parametrize` pelos DOIS níveis: o que é igual tem
que continuar igual nos dois, e o que difere está isolado nos testes do papel.

O que cobrem, em ordem:

1. **o papel** — o glifo, os rótulos e as frases certos para cada nível, e o
   cartão de contexto dizendo onde a coisa vai nascer (com a impressora, na
   subcategoria: a regra de ouro do §9.8 dita em voz alta);
2. **a validação reativa** — o contador, o "✓ Nome válido", o "✕ Nome já
   existente" e o botão que só liga quando há o que gravar;
3. **as duas regras de duplicidade** — exata na categoria, tolerante a acento e
   caixa na subcategoria, cada uma espelhando o service do seu nível. Este é o
   par que mais fácil sairia errado num modal compartilhado;
4. **o teclado** — Enter grava, Esc fecha;
5. **o ciclo de vida** — o RNF do Celeron: escurecedor solto, sinais
   desconectados, nada preso à view depois de trinta idas e voltas.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QFocusEvent, QFontDatabase, QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QWidget

import gestor_comercial
from gestor_comercial.ui.theme.controller import ThemeController
from gestor_comercial.ui.widgets.cardapio_cartoes import GLIFO_PASTA_MAIS, GLIFO_RAMO, GlifoSolto
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.organizacao_cardapio_dialog import (
    LIMITE_NOME,
    MINIMO_NOME,
    DadosOrganizacao,
    NivelDoCardapio,
    OrganizacaoCardapioDialog,
)

NIVEIS = [NivelDoCardapio.CATEGORIA, NivelDoCardapio.SUBCATEGORIA]


def _montar(nivel: NivelDoCardapio, pai: QWidget | None = None) -> OrganizacaoCardapioDialog:
    """O cartão do nível pedido, sem a fixture — para os testes de vazamento,
    que fazem o próprio descarte."""
    if nivel is NivelDoCardapio.CATEGORIA:
        return OrganizacaoCardapioDialog.para_categoria(["Lanches"], pai)
    return OrganizacaoCardapioDialog.para_subcategoria("Lanches", "Cozinha", ["Podrão"], pai)


@pytest.fixture
def abrir(qapp):
    """Monta o cartão sem `exec()` — e o descarta no fim do teste.

    `existentes=None` e não `existentes=[]` como padrão, e o `if is None` em vez
    de `or`: com `or`, passar uma lista VAZIA cairia no padrão — e o teste do
    cardápio sem nada cadastrado testaria o caso oposto do que diz.
    """
    criados: list[OrganizacaoCardapioDialog] = []

    def _abrir(
        nivel=NivelDoCardapio.SUBCATEGORIA,
        existentes=None,
        nome_inicial="",
        categoria="Lanches",
        impressora="Cozinha",
        pai=None,
    ):
        if existentes is None:
            existentes = ["Podrão", "Artesanal"]
        if nivel is NivelDoCardapio.CATEGORIA:
            modal = OrganizacaoCardapioDialog.para_categoria(
                existentes, pai, nome_inicial=nome_inicial
            )
        else:
            modal = OrganizacaoCardapioDialog.para_subcategoria(
                categoria, impressora, existentes, pai, nome_inicial=nome_inicial
            )
        criados.append(modal)
        return modal

    yield _abrir
    for modal in criados:
        modal.deleteLater()


def _rotulo(modal: OrganizacaoCardapioDialog, nome_do_objeto: str) -> str:
    return next(
        r.text() for r in modal.findChildren(QLabel) if r.objectName() == nome_do_objeto
    )


def _rotulos(modal: OrganizacaoCardapioDialog, nome_do_objeto: str) -> list[str]:
    return [r.text() for r in modal.findChildren(QLabel) if r.objectName() == nome_do_objeto]


# ---------------------------------------------------------------------------
# 1. O papel: o que muda entre os dois níveis, e o que não pode mudar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nivel", NIVEIS)
def test_o_cabecalho_diz_a_secao_nos_dois_niveis(abrir, nivel):
    """A tarja de cima é a mesma nos dois: quem abriu está organizando o
    cardápio, e o nível é detalhe do que vem abaixo dela."""
    modal = abrir(nivel=nivel)

    assert _rotulo(modal, "orgDialogSecao") == "ORGANIZAÇÃO DO CARDÁPIO"


def test_a_categoria_nasce_na_raiz_e_diz_isso(abrir):
    modal = abrir(nivel=NivelDoCardapio.CATEGORIA, existentes=[])

    assert _rotulo(modal, "orgDialogTitulo") == "Nova categoria"
    assert _rotulo(modal, "orgDialogRotulo") == "SERÁ CRIADA EM"
    assert _rotulo(modal, "orgDialogDestino") == "Raiz do cardápio"
    assert _rotulo(modal, "orgDialogAtalhos") == "ENTER PARA CRIAR · ESC PARA FECHAR"


def test_a_subcategoria_diz_a_categoria_e_a_impressora_dela(abrir):
    """A regra de ouro do §9.8 dita em voz alta: a bobina é da CATEGORIA, e
    continua sendo depois desta tela. Sem isso, a pergunta que a tela levanta
    ("isso muda onde meu pedido sai?") fica sem resposta."""
    modal = abrir(nivel=NivelDoCardapio.SUBCATEGORIA, categoria="Lanches", impressora="Cozinha")

    assert _rotulo(modal, "orgDialogDestino") == "Lanches"
    assert _rotulo(modal, "orgDialogImpressora") == "COZINHA"
    assert "SERÁ CRIADA DENTRO DE" in _rotulos(modal, "orgDialogRotulo")


def test_categoria_sem_impressora_diz_isso_em_vez_de_ficar_em_branco(abrir):
    modal = abrir(nivel=NivelDoCardapio.SUBCATEGORIA, impressora=None)

    assert _rotulo(modal, "orgDialogImpressora") == "SEM IMPRESSORA"


def test_a_raiz_nao_mostra_selo_de_impressora(abrir):
    """Na raiz não há bobina a citar: um "SEM IMPRESSORA" ali diria de uma
    categoria recém-nascida algo que não é escolha de quem a cria."""
    modal = abrir(nivel=NivelDoCardapio.CATEGORIA, existentes=[])

    assert _rotulos(modal, "orgDialogImpressora") == []


@pytest.mark.parametrize(
    ("nivel", "glifo"),
    [
        (NivelDoCardapio.CATEGORIA, GLIFO_PASTA_MAIS),
        (NivelDoCardapio.SUBCATEGORIA, GLIFO_RAMO),
    ],
)
def test_cada_nivel_tem_o_proprio_glifo_no_cabecalho(abrir, nivel, glifo):
    modal = abrir(nivel=nivel)

    glifos = [g._glifo for g in modal.findChildren(GlifoSolto)]

    assert glifo in glifos, f"o cabeçalho de {nivel.value} não desenhou {glifo}"


@pytest.mark.parametrize(
    ("nivel", "rotulo", "trecho"),
    [
        (NivelDoCardapio.CATEGORIA, "NOME DA CATEGORIA", "Sobremesas"),
        (NivelDoCardapio.SUBCATEGORIA, "NOME DA SUBCATEGORIA", "Podrão"),
    ],
)
def test_o_campo_se_apresenta_pelo_nivel(abrir, nivel, rotulo, trecho):
    modal = abrir(nivel=nivel)

    assert rotulo in _rotulos(modal, "orgDialogRotulo")
    assert trecho in modal._campo_nome.placeholderText()


@pytest.mark.parametrize("nivel", NIVEIS)
def test_editar_troca_titulo_botao_e_atalho(abrir, nivel):
    """Renomear não é criar: o cartão inteiro tem que dizer isso, incluindo a
    linha de atalhos — "ENTER PARA CRIAR" num cartão de edição é instrução
    errada no lugar onde o operador olha para se decidir."""
    modal = abrir(nivel=nivel, nome_inicial="Podrão")

    assert _rotulo(modal, "orgDialogTitulo").startswith("Editar")
    assert modal._botao_confirmar.text() == "Salvar alterações"
    assert _rotulo(modal, "orgDialogAtalhos") == "ENTER PARA SALVAR · ESC PARA FECHAR"


# ---------------------------------------------------------------------------
# 2. A validação reativa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nivel", NIVEIS)
def test_o_botao_nasce_desligado_com_o_campo_vazio(abrir, nivel):
    modal = abrir(nivel=nivel, existentes=[])

    assert modal._botao_confirmar.isEnabled() is False
    assert _rotulo(modal, "orgDialogStatus") == ""


@pytest.mark.parametrize("nivel", NIVEIS)
def test_uma_letra_so_nao_liga_o_botao_e_diz_por_que(abrir, nivel):
    """Botão desligado sem explicação é o gerente clicando duas vezes e
    concluindo que o programa travou."""
    modal = abrir(nivel=nivel, existentes=[])

    modal._campo_nome.setText("P")

    assert modal._botao_confirmar.isEnabled() is False
    assert str(MINIMO_NOME) in _rotulo(modal, "orgDialogStatus")


@pytest.mark.parametrize("nivel", NIVEIS)
def test_um_nome_novo_liga_o_botao_e_acende_o_visto(abrir, nivel):
    modal = abrir(nivel=nivel, existentes=["Podrão"])

    modal._campo_nome.setText("Prensado")

    assert modal._botao_confirmar.isEnabled() is True
    assert _rotulo(modal, "orgDialogStatus") == "✓  Nome válido"
    assert modal._status.property("estado") == "ok"
    assert modal.resultado() == DadosOrganizacao(nome="Prensado")


@pytest.mark.parametrize("nivel", NIVEIS)
def test_o_contador_acompanha_a_digitacao(abrir, nivel):
    modal = abrir(nivel=nivel)

    modal._campo_nome.setText("Prensado")

    assert _rotulo(modal, "orgDialogContador") == f"8/{LIMITE_NOME}"
    assert modal._campo_nome.maxLength() == LIMITE_NOME


def test_editar_um_nome_mais_longo_que_o_teto_nao_o_corta(abrir):
    """`setMaxLength` apara o texto que já está no campo. Abrir a edição de um
    nome cadastrado antes deste teto e devolvê-lo cortado seria perder dado sem
    dizer nada — e o gerente só descobriria pela árvore, depois de salvar."""
    comprido = "C" * (LIMITE_NOME + 12)
    modal = abrir(nome_inicial=comprido, existentes=[comprido])

    assert modal._campo_nome.text() == comprido
    assert modal.resultado() == DadosOrganizacao(nome=comprido)


@pytest.mark.parametrize("nivel", NIVEIS)
def test_o_resultado_vem_aparado(abrir, nivel):
    modal = abrir(nivel=nivel, existentes=[])

    modal._campo_nome.setText("  Lanche   Prensado  ")

    assert modal.resultado() == DadosOrganizacao(nome="Lanche Prensado")


@pytest.mark.parametrize("nivel", NIVEIS)
def test_o_erro_do_service_aparece_sem_fechar_nem_perder_o_texto(abrir, nivel):
    """O modal é reaberto no `while` da view quando o service recusa: o gerente
    corrige sem redigitar. A mensagem toma a linha da ESQUERDA, que é a larga —
    as do service são frases inteiras e não caberiam no selo da direita."""
    modal = abrir(nivel=nivel, existentes=[])
    modal._campo_nome.setText("Prensado")

    modal.mostrar_erro_servico("Já existe a subcategoria 'Prensado' nesta categoria.")

    assert modal._campo_nome.text() == "Prensado"
    assert _rotulo(modal, "orgDialogAjuda").startswith("Já existe")
    assert modal._ajuda.property("estado") == "erro"


@pytest.mark.parametrize("nivel", NIVEIS)
def test_digitar_de_novo_apaga_o_erro_do_service(abrir, nivel):
    """O erro falava do texto anterior: deixá-lo aceso enquanto se corrige é o
    aviso contradizendo o campo."""
    modal = abrir(nivel=nivel, existentes=[])
    modal._campo_nome.setText("Prensado")
    modal.mostrar_erro_servico("Já existe.")

    modal._campo_nome.setText("Prensados")

    assert modal._ajuda.property("estado") == "dica"
    assert _rotulo(modal, "orgDialogAjuda") != "Já existe."


# ---------------------------------------------------------------------------
# 3. As duas regras de nome repetido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nivel", NIVEIS)
def test_o_nome_repetido_desliga_o_botao_antes_de_salvar(abrir, nivel):
    modal = abrir(nivel=nivel, existentes=["Podrão"])

    modal._campo_nome.setText("Podrão")

    assert modal._botao_confirmar.isEnabled() is False
    assert _rotulo(modal, "orgDialogStatus") == "✕  Nome já existente"
    assert modal._status.property("estado") == "erro"


@pytest.mark.parametrize("quase", ["podrao", "PODRÃO", "  podrão  "])
def test_na_subcategoria_o_quase_igual_tambem_e_barrado(abrir, quase):
    """A mesma comparação de `_exigir_nome_de_subcategoria_livre` (acento, caixa
    e espaço repetido ignorados): "Podrão" e "podrao" lado a lado na árvore
    seriam dois grupos que o gerente lê como um só."""
    modal = abrir(nivel=NivelDoCardapio.SUBCATEGORIA, existentes=["Podrão"])

    modal._campo_nome.setText(quase)

    assert modal._botao_confirmar.isEnabled() is False


@pytest.mark.parametrize("quase", ["lanches", "LANCHES"])
def test_na_categoria_o_quase_igual_passa_porque_o_service_o_aceita(abrir, quase):
    """`_exigir_nome_de_categoria_livre` compara o nome EXATO
    (`Categoria.nome == nome`). Barrar aqui o que o service aceita seria a tela
    mentindo: botão desligado por uma regra que não existe do outro lado, e o
    gerente sem saber por que não consegue salvar.

    É o oposto do teste acima de propósito. Se um dia o service passar a
    comparar categoria pela `chave_de_agrupamento`, é este teste que reprova —
    e o conserto é uma linha em `PAPEIS`, não uma tela nova."""
    modal = abrir(nivel=NivelDoCardapio.CATEGORIA, existentes=["Lanches"])

    modal._campo_nome.setText(quase)

    assert modal._botao_confirmar.isEnabled() is True


@pytest.mark.parametrize("nivel", NIVEIS)
def test_editar_aceita_o_proprio_nome(abrir, nivel):
    """Renomear "Podrão" para "Podrão" (sem mexer) não pode acusar duplicidade."""
    modal = abrir(nivel=nivel, existentes=["Podrão", "Artesanal"], nome_inicial="Podrão")

    assert modal._botao_confirmar.isEnabled() is True
    assert modal.resultado() == DadosOrganizacao(nome="Podrão")


@pytest.mark.parametrize("nivel", NIVEIS)
def test_editar_ainda_barra_o_nome_da_outra(abrir, nivel):
    modal = abrir(nivel=nivel, existentes=["Podrão", "Artesanal"], nome_inicial="Podrão")

    modal._campo_nome.setText("Artesanal")

    assert modal._botao_confirmar.isEnabled() is False


# ---------------------------------------------------------------------------
# 3.5 O rodapé de uma linha cabe no cartão
# ---------------------------------------------------------------------------


@pytest.fixture
def com_fonte_e_tema(qapp):
    """A fonte da marca registrada e o QSS aplicado, antes de medir qualquer coisa.

    As duas metades importam. A plataforma `offscreen` sobe com o banco de
    fontes **vazio** e sem fonte todo texto mede quase nada — o aperto de
    largura simplesmente não acontece, e um teste que o cobrasse passaria verde
    sem ter olhado (é a mesma armadilha registrada em
    `test_mesas_ocupadas_em_vermelho`). E é o QSS que define os tamanhos de
    letra do rodapé: sem ele, o rótulo de atalhos mede na fonte padrão do
    sistema, que não é a que o operador vê.
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


@pytest.mark.parametrize("nivel", NIVEIS)
@pytest.mark.parametrize("nome_inicial", ["", "Podrão"])
def test_o_rodape_cabe_no_cartao(qapp, com_fonte_e_tema, nivel, nome_inicial):
    """Nenhuma peça do rodapé pode ser desenhada menor do que ela pede.

    É a linha mais apertada do cartão: atalhos à esquerda, dois botões à
    direita, tudo numa fileira só (o mockup). A fonte da marca é ~20% mais
    larga que a do desenho, e a 480px o "+ Criar subcategoria" saía como
    "Criar subcategol" e o rótulo virava "ENTER PARA CRIAR · ES" — um rodapé
    que corta a própria instrução de teclado.

    Mede `width() < sizeHint().width()`, e não o texto pintado, porque é isso
    que o layout decide: quando a soma não cabe, o Qt espreme o `QLabel` abaixo
    do que ele pediu e o corte aparece. Roda nos dois níveis e nos dois modos
    porque os quatro rótulos de botão têm larguras diferentes — a folga é de
    6px no pior deles.
    """
    janela = QWidget()
    janela.resize(1366, 738)
    janela.show()
    modal = (
        OrganizacaoCardapioDialog.para_categoria(["Lanches"], janela, nome_inicial=nome_inicial)
        if nivel is NivelDoCardapio.CATEGORIA
        else OrganizacaoCardapioDialog.para_subcategoria(
            "Acompanhamentos", "Cozinha", ["Guarnições"], janela, nome_inicial=nome_inicial
        )
    )
    modal.show()
    qapp.processEvents()

    rodape = next(
        w for w in modal.findChildren(QWidget) if w.objectName() == "orgDialogRodape"
    )
    pecas = [
        w
        for w in rodape.findChildren(QWidget)
        if isinstance(w, (QLabel, QPushButton)) and w.objectName().startswith("orgDialog")
    ]
    assert pecas, "premissa: o rodapé tem peças a medir"
    apertadas = {
        w.objectName(): (w.width(), w.sizeHint().width())
        for w in pecas
        if w.width() < w.sizeHint().width()
    }

    modal.reject()
    modal.deleteLater()
    assert not apertadas, f"rodapé espremido (tem, pede): {apertadas}"


# ---------------------------------------------------------------------------
# 4. Teclado
# ---------------------------------------------------------------------------


def _tecla(modal: OrganizacaoCardapioDialog, tecla: Qt.Key) -> None:
    modal.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, tecla, Qt.KeyboardModifier.NoModifier))


@pytest.mark.parametrize("nivel", NIVEIS)
def test_enter_grava_quando_ha_o_que_gravar(qapp, abrir, nivel):
    modal = abrir(nivel=nivel, existentes=[])
    modal._campo_nome.setText("Prensado")

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.result() == QDialog.DialogCode.Accepted


@pytest.mark.parametrize("nivel", NIVEIS)
def test_enter_com_nome_repetido_nao_faz_nada(qapp, abrir, nivel):
    """Sem isto, o Enter passaria por cima do botão desligado — e o gerente
    receberia o erro do service num modal que ele achava que estava travado."""
    modal = abrir(nivel=nivel, existentes=["Podrão"])
    modal._campo_nome.setText("Podrão")

    _tecla(modal, Qt.Key.Key_Return)

    assert modal.result() != QDialog.DialogCode.Accepted


@pytest.mark.parametrize("nivel", NIVEIS)
def test_esc_fecha_o_modal(qapp, abrir, nivel):
    modal = abrir(nivel=nivel)

    _tecla(modal, Qt.Key.Key_Escape)

    assert modal.result() == QDialog.DialogCode.Rejected


# ---------------------------------------------------------------------------
# 5. Ciclo de vida — o RNF do Celeron
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nivel", NIVEIS)
def test_fechar_solta_o_escurecedor_da_janela(qapp, assentar, nivel):
    """O escurecedor é filho da JANELA, não do diálogo: sem soltá-lo, uma tarde
    de idas e voltas ao cadastro deixaria uma pilha de retângulos pretos
    invisíveis pendurada no `MainWindow`, que vive o processo inteiro.

    Monta sem a fixture `abrir` de propósito: aqui o teste descarta cada modal
    ele mesmo, e o descarte da fixture cairia num objeto C++ já destruído.
    """
    janela = QWidget()
    janela.show()

    for _ in range(5):
        modal = _montar(nivel, janela)
        modal.show()
        qapp.processEvents()
        assert len(janela.findChildren(Backdrop)) == 1
        modal.reject()
        modal.deleteLater()
    assentar()

    assert janela.findChildren(Backdrop) == []


@pytest.mark.parametrize("nivel", NIVEIS)
def test_trinta_aberturas_nao_deixam_nada_preso_a_view(qapp, assentar, nivel):
    """O caminho real do app: aberto com `exec()` e fechado pelo botão."""
    pai = QWidget()

    for _ in range(30):
        modal = _montar(nivel, pai)
        QTimer.singleShot(0, modal.reject)
        modal.exec()
        del modal
    assentar()

    assert pai.findChildren(OrganizacaoCardapioDialog) == []


def test_fechar_desliga_os_sinais(qapp, abrir):
    """O `unbind` explícito do pedido: as três ligações são desconectadas
    nominalmente. Elas morreriam com os filhos de qualquer forma — explicitá-las
    é o que impede que uma quarta ligação, a um objeto de FORA do cartão, entre
    um dia sem ninguém notar que aquela, sim, sobreviveria ao fechamento."""
    modal = abrir()
    modal._campo_nome.setText("Prensado")

    modal.reject()
    modal._campo_nome.setText("Outro")

    assert modal._backdrop is None
    # O contador parou no texto de "Prensado": o `textChanged` não chega mais.
    assert _rotulo(modal, "orgDialogContador") == f"8/{LIMITE_NOME}"


def test_fechar_tira_o_filtro_de_eventos_do_campo(qapp, abrir):
    """O anel de foco é do QUADRO e o foco é do campo lá dentro: o filtro é a
    única coisa que este diálogo instala em outro objeto. Depois de fechado,
    ele não pode mais reagir."""
    modal = abrir()
    entrar = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.OtherFocusReason)
    qapp.sendEvent(modal._campo_nome, entrar)
    assert modal._caixa_campo.property("foco") is True, "premissa: o filtro acende o anel"
    qapp.sendEvent(
        modal._campo_nome, QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason)
    )

    modal.reject()
    qapp.sendEvent(modal._campo_nome, entrar)

    assert modal._caixa_campo.property("foco") is False


def test_soltar_os_recursos_duas_vezes_e_silencioso(qapp, abrir):
    """A segunda passagem da limpeza não pode reclamar nem desfazer nada.

    `done()` roda de novo em caminhos normais (um Esc num diálogo já fechando),
    e sem a trava `_limpo` cada ligação desconectada duas vezes imprime
    `RuntimeWarning: libpyside: Failed to disconnect` — três avisos por
    fechamento, sempre, que é o que faz ninguém ler o aviso que importa quando
    ele vier.

    Mede o AVISO, e não uma exceção: nesta versão do PySide6 o segundo
    `disconnect` devolve `False` em vez de estourar, e um teste escrito contra
    `RuntimeError` passaria verde sem ter olhado a trava. Foi a checagem por
    mutação que mostrou isso — apagar o `if self._limpo` não reprovava a
    primeira versão deste teste.
    """
    modal = abrir()
    modal.reject()

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        modal._soltar_recursos()

    assert [str(a.message) for a in avisos] == []
    assert modal.result() == QDialog.DialogCode.Rejected
