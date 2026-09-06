"""Bancada de paridade visual: renderiza as telas do app em PNG, offscreen.

Existe porque a remasterização mexeu na montagem de telas inteiras, e "a suíte
está verde" não prova que o pai do Vitor vê a mesma coisa no balcão: nenhum
teste compara pixel. Renderizando a mesma tela com o código de antes e o de
depois, o `diff` responde direto.

Roda sem dependência nova (só PySide6 e SQLAlchemy, que já são do projeto) e
fica fora de `src/`, então não entra no `.exe`.

    # o "depois" — código da árvore de trabalho
    python tools/comparar_telas.py C:\\tmp\\depois

    # o "antes" — a mesma bancada contra outro commit
    git worktree add C:\\tmp\\antes-src <commit>
    PYTHONPATH=C:\\tmp\\antes-src/src python tools/comparar_telas.py C:\\tmp\\antes

    python tools/comparar_telas.py --comparar C:\\tmp\\antes C:\\tmp\\depois

    # a janela do food truck: monitor de 768px com a janela maximizada
    python tools/comparar_telas.py C:\\tmp\\depois --tamanho 1366x738

A janela renderizada é a `MainWindow` de verdade, não a view solta: assim a
paridade cobre também a sidebar, a barra de usuário e a barra da Central de
Loja, que são montadas por ela. A navegação usa os mesmos pontos de entrada da
navegação real (`_navegar_agora`), com os cadeados de PIN da Loja e do Caixa
abertos na mão — o PIN é o que esta bancada não tem como digitar, e a tela
depois dele é a mesma.

Cada tela é gravada nos dois temas, porque foi assim que os defeitos das fases
anteriores apareceram (§3.15 — cor congelada na construção só aparece ao trocar
o tema). As duas telas de Relatórios ganham um terceiro estado, com um operador
filtrado, porque o destaque das pílulas depende de estado interno (Fase 6).

O banco é em memória e as datas dos dados são **congeladas** no dia 1 do mês
vigente (`_congelar_datas`): a montagem das telas é o que se quer comparar, e
um `datetime.now()` gravado no dado faria duas execuções diferirem por causa do
relógio, não do código. O mês vigente é o que o Histórico Diário e o Dashboard
Mensal abrem por padrão, então os dados precisam cair dentro dele.
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Tamanho padrão da janela. `--tamanho LxA` troca por outro: a altura é o que
# separa uma tela folgada de uma espremida, e a classe de máquina do food truck
# é o monitor de 768px (1366x738 com a janela maximizada, descontada a barra de
# tarefas). Foi assim que a Fase 7 achou a Configurações espremida.
TAMANHO = (1280, 800)
OPERADOR = "Joana"

# A plataforma `offscreen` sobe com o banco de fontes VAZIO (`QFontDatabase.
# families()` devolve `[]`), e sem fonte todo texto sai como quadradinho: a
# comparação viraria só de layout, cega para o conteúdo. Carregar os arquivos
# na mão devolve a letra — Segoe UI é a fonte de interface do Windows, que é o
# que a máquina do food truck usa; Segoe UI Emoji é o que desenha os ícones das
# telas; Archivo Black é a fonte da marca, que `main.py` também registra.
FONTES = (
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/seguiemj.ttf"),
    Path(__file__).resolve().parents[1] / "resources" / "fonts" / "ArchivoBlack-Regular.ttf",
)

# Telas alcançadas por rótulo da sidebar. Login, Comanda, Histórico e Dashboard
# têm caminho próprio (ver `abrir`, dentro de `renderizar`).
TELAS_POR_ROTULO = {
    "mesas": "Mesas",
    "caixa": "Caixa",
    "cardapio": "Cardápio",
    "funcionarios": "Funcionários",
    "impressoras": "Impressoras",
    "configuracoes": "Configurações",
    "loja": "Loja",
}


def _montar_servicos() -> dict:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import gestor_comercial.domain  # noqa: F401 - registra os mappers
    from gestor_comercial.repository.base import Base
    from gestor_comercial.repository.seed import (
        seed_cardapio,
        seed_combos,
        seed_funcionarios_turno,
        seed_mesas,
        seed_usuarios_turno,
    )
    from gestor_comercial.repository.unit_of_work import UnitOfWork
    from gestor_comercial.services.auth_service import AuthService
    from gestor_comercial.services.caixa_service import CaixaService
    from gestor_comercial.services.cardapio_service import CardapioService
    from gestor_comercial.services.comanda_service import ComandaService
    from gestor_comercial.services.funcionario_service import FuncionarioService
    from gestor_comercial.services.impressao_service import ImpressaoService
    from gestor_comercial.services.pagamento_service import PagamentoService

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessao = sessionmaker(bind=engine)()

    # O mesmo seed do primeiro boot (mesas, operadores de turno, cardápio):
    # tela cheia acha diferença que tela vazia esconde, e este é o conteúdo
    # que a máquina do food truck realmente mostra.
    seed_mesas(sessao)
    seed_usuarios_turno(sessao)
    seed_funcionarios_turno(sessao)
    seed_cardapio(sessao)
    seed_combos(sessao)
    sessao.commit()

    uow = UnitOfWork(session=sessao)
    auth = AuthService(uow)
    comandas = ComandaService(uow, auth)
    funcionarios = FuncionarioService(uow, auth)
    return {
        "uow": uow,
        "auth": auth,
        "comandas": comandas,
        "cardapio": CardapioService(uow, auth),
        "caixas": CaixaService(uow, auth),
        "funcionarios": funcionarios,
        "pagamentos": PagamentoService(uow, auth, comandas, funcionarios),
        "impressao": ImpressaoService(uow, auth),
    }


def _povoar(servicos: dict, pasta_cupons: Path | None = None) -> dict:
    """Um dia de operação: um turno já fechado (o que o Histórico e o Dashboard
    mostram), um turno aberto com movimentos (a tela de Caixa) e uma comanda
    viva numa mesa (as telas de Mesas e Comanda).

    `pasta_cupons` diz onde as duas impressoras do tipo ARQUIVO gravam os
    `.txt` — é o que `comparar_cupons.py` usa para reaproveitar exatamente este
    cenário sem montar um segundo seed paralelo a este."""
    from gestor_comercial.domain.enums import (
        CargoFuncionario,
        FormaPagamento,
        PerfilUsuario,
        TipoMovimento,
    )
    from gestor_comercial.services.loja_config_service import SENHA_LOGIN_PADRAO

    auth = servicos["auth"]
    caixas = servicos["caixas"]
    cardapio = servicos["cardapio"]
    comandas = servicos["comandas"]

    operador = auth.listar_ativos()[0]
    auth.login_como(operador.id, SENHA_LOGIN_PADRAO)

    # Um Caixa aparece nas pílulas do filtro dos relatórios quando existe
    # `Funcionario` ativo com cargo Caixa **e** `Usuario` de login de mesmo nome.
    servicos["funcionarios"].criar(OPERADOR, CargoFuncionario.CAIXA.value)
    auth.criar_usuario(OPERADOR, PerfilUsuario.OPERADOR_CAIXA)
    garcom = servicos["funcionarios"].criar("Pedro", CargoFuncionario.GARCOM.value)

    pasta = pasta_cupons or Path("cupons")
    cardapio.criar_impressora("Balcão", caminho_arquivo=str(pasta / "balcao.txt"))
    cozinha = cardapio.criar_impressora("Cozinha", caminho_arquivo=str(pasta / "cozinha.txt"))
    # Balcão é a padrão (foi cadastrada primeiro) e recebe recibo, pré-conta e
    # fechamento; Lanches vai para a Cozinha e o resto cai no fallback da
    # padrão — é assim que o roteamento do §3.12 fica exercitado nos cupons.
    categorias = {c.nome: c for c in cardapio.listar_categorias_ativas()}
    cardapio.associar_impressora(categorias["Lanches"].id, cozinha.id)

    produtos = {p.nome: p for p in cardapio.listar_produtos_ativos()}
    x_tudo = produtos["X Tudo"]
    coca = produtos["Coca Lata"]
    batata = produtos["Batata P Simples"]

    # --- turno já fechado: vira linha no Histórico e número no Dashboard ---
    fechado = caixas.abrir(Decimal("150.00"))
    venda = comandas.abrir_balcao()
    comandas.lancar_item(venda.id, x_tudo.id, 2)
    comandas.lancar_item(venda.id, coca.id, 2)
    comandas.fechar_para_conferencia(venda.id)
    servicos["pagamentos"].registrar(venda.id, FormaPagamento.DINHEIRO, Decimal("48.00"))
    caixas.fechar(fechado.id, Decimal("198.00"), Decimal("0.00"))

    # --- turno aberto: é o que a tela de Caixa mostra ---
    aberto = caixas.abrir(Decimal("200.00"))
    caixas.registrar_movimento(TipoMovimento.SANGRIA, Decimal("50.00"), "Depósito no cofre")
    caixas.registrar_movimento(TipoMovimento.REFORCO, Decimal("30.00"), "Troco da padaria")

    mesa = comandas.listar_mesas()[2]
    comanda = comandas.abrir_por_mesa(mesa.id)
    comandas.definir_atendente(comanda.id, garcom.id)
    comandas.lancar_item(comanda.id, x_tudo.id, 1)
    comandas.lancar_item(comanda.id, batata.id, 1, "sem sal")
    comandas.lancar_item(comanda.id, coca.id, 2)

    _congelar_datas(servicos["uow"].session)
    return {
        "usuario": operador,
        "comanda": comandas.buscar(comanda.id),
        "comanda_paga": comandas.buscar(venda.id),
        "caixa_fechado": fechado.id,
        "caixa_aberto": aberto.id,
        "impressoras": [i.id for i in cardapio.listar_impressoras_ativas()],
    }


def _congelar_datas(sessao) -> None:
    """Troca todo `datetime.now()` gravado pelos services por hora fixa no dia 1
    do mês vigente. Sem isto, duas execuções da bancada diferem pelo relógio
    (hora do turno no cabeçalho, hora do item na comanda) e o `diff` acusaria
    diferença onde o código é o mesmo."""
    from sqlalchemy import update

    from gestor_comercial.domain.caixa import Caixa
    from gestor_comercial.domain.comanda import Comanda
    from gestor_comercial.domain.item_comanda import ItemComanda
    from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
    from gestor_comercial.domain.pagamento import Pagamento

    hoje = datetime.now()
    dia = datetime(hoje.year, hoje.month, 1)

    def em(hora: int, minuto: int = 0) -> datetime:
        return dia.replace(hour=hora, minute=minuto)

    sessao.execute(update(Caixa).values(aberto_em=em(8)))
    sessao.execute(update(Caixa).where(Caixa.fechado_em.isnot(None)).values(fechado_em=em(16)))
    sessao.execute(update(Comanda).values(aberta_em=em(9)))
    sessao.execute(
        update(Comanda)
        .where(Comanda.em_conferencia_em.isnot(None))
        .values(em_conferencia_em=em(10))
    )
    sessao.execute(
        update(Comanda).where(Comanda.fechada_em.isnot(None)).values(fechada_em=em(10, 5))
    )
    sessao.execute(
        update(ItemComanda).where(ItemComanda.impresso_em.isnot(None)).values(impresso_em=em(9, 5))
    )
    sessao.execute(update(MovimentoCaixa).values(registrado_em=em(11)))
    sessao.execute(update(Pagamento).values(registrado_em=em(10, 5)))
    sessao.commit()
    sessao.expire_all()


def _registrar_fontes(app) -> None:
    from PySide6.QtGui import QFont, QFontDatabase

    familias: list[str] = []
    for caminho in FONTES:
        if caminho.exists():
            identificador = QFontDatabase.addApplicationFont(str(caminho))
            familias += QFontDatabase.applicationFontFamilies(identificador)
    if "Segoe UI" in familias:
        app.setFont(QFont("Segoe UI", 9))


def renderizar(destino: Path, tamanho: tuple[int, int] = TAMANHO) -> list[Path]:
    from PySide6.QtWidgets import QApplication, QPushButton

    app = QApplication.instance() or QApplication([])
    _registrar_fontes(app)

    from gestor_comercial.ui.main_window import MainWindow
    from gestor_comercial.ui.theme.controller import ThemeController

    ThemeController.instancia().aplicar_inicial()
    servicos = _montar_servicos()
    dados = _povoar(servicos)

    janela = MainWindow(
        servicos["auth"],
        servicos["comandas"],
        servicos["cardapio"],
        servicos["caixas"],
        servicos["pagamentos"],
        servicos["impressao"],
        servicos["funcionarios"],
    )
    janela.resize(*tamanho)
    janela.show()

    destino.mkdir(parents=True, exist_ok=True)
    gerados: list[Path] = []

    def gravar(nome: str, estado: str) -> None:
        app.processEvents()
        caminho = destino / f"{nome}-{estado}.png"
        janela.grab().save(str(caminho))
        gerados.append(caminho)

    def botao(texto: str, dentro=None) -> QPushButton:
        return next(b for b in (dentro or janela).findChildren(QPushButton) if texto in b.text())

    def sub_relatorio():
        """A sub-tela de Relatórios em cartaz. As duas (Histórico e Dashboard)
        têm a MESMA pílula de operador, e `isVisible()` não separa uma da outra
        de forma confiável enquanto a janela roda offscreen — sem escopo, o
        clique cai na pílula da tela escondida e o estado "operador filtrado"
        nunca aparece no PNG."""
        return janela._relatorios_view._pilha.currentWidget()

    def abrir(nome: str) -> None:
        """Leva a janela até a tela `nome`, pelos mesmos pontos de entrada da
        navegação real."""
        if nome == "login":
            janela._pilha_raiz.setCurrentIndex(0)
            return
        # Depois do login: a sessão existe, e os cadeados de PIN da Loja e do
        # Caixa saem do caminho (a bancada não tem como digitar PIN; a tela
        # depois dele é a mesma).
        janela._pilha_raiz.setCurrentIndex(1)
        janela._loja_desbloqueada = True
        janela._caixa_desbloqueada = True
        if nome == "comanda":
            janela._mesas_view.comanda_aberta.emit(dados["comanda"])
            return
        if nome in ("historico", "dashboard"):
            janela._navegar_agora("Relatórios")
            botao("Histórico Diário" if nome == "historico" else "Dashboard Mensal").click()
            return
        janela._navegar_agora(TELAS_POR_ROTULO[nome])

    telas = ["login", "mesas", "comanda", "caixa", "historico", "dashboard"]
    telas += ["cardapio", "funcionarios", "impressoras", "configuracoes", "loja"]

    janela._login_view.autenticado.emit(dados["usuario"])
    for claro in (False, True):
        ThemeController.instancia().alternar_para(claro)
        estado = "claro" if claro else "escuro"
        for nome in telas:
            abrir(nome)
            gravar(nome, estado)

    # Estado extra das duas telas de Relatórios: com um operador filtrado, o
    # destaque das pílulas depende de estado interno (Fase 6).
    ThemeController.instancia().alternar_para(False)
    for nome in ("historico", "dashboard"):
        abrir(nome)
        botao(OPERADOR, dentro=sub_relatorio()).click()
        gravar(nome, "operador")

    return gerados


def _onde_difere(antes: Path, depois: Path) -> str:
    """"Diferente" sozinho não diz se mudou um cabeçalho ou a tela inteira.
    Devolve quantos pixels mudaram e o retângulo que os contém, que é o que
    permite ir olhar o lugar certo da imagem."""
    from PySide6.QtGui import QImage

    um, outro = QImage(str(antes)), QImage(str(depois))
    if um.size() != outro.size():
        return f"tamanho {um.width()}x{um.height()} -> {outro.width()}x{outro.height()}"

    largura, altura = um.width(), um.height()
    um = um.convertToFormat(QImage.Format.Format_RGB32)
    outro = outro.convertToFormat(QImage.Format.Format_RGB32)
    bytes_um, bytes_outro = um.constBits().tobytes(), outro.constBits().tobytes()
    passo = um.bytesPerLine()

    esquerda, topo, direita, base, total = largura, altura, -1, -1, 0
    for y in range(altura):
        inicio = y * passo
        linha_um = bytes_um[inicio : inicio + largura * 4]
        linha_outro = bytes_outro[inicio : inicio + largura * 4]
        if linha_um == linha_outro:  # caminho rápido: a maioria das linhas é igual
            continue
        topo = min(topo, y)
        base = max(base, y)
        for x in range(largura):
            if linha_um[x * 4 : x * 4 + 4] != linha_outro[x * 4 : x * 4 + 4]:
                total += 1
                esquerda, direita = min(esquerda, x), max(direita, x)
    proporcao = 100 * total / (largura * altura)
    return (
        f"{total} px ({proporcao:.2f}%) em x={esquerda}..{direita} y={topo}..{base}"
    )


def comparar(antes: Path, depois: Path) -> int:
    diferentes = 0
    for arquivo in sorted(depois.glob("*.png")):
        par = antes / arquivo.name
        if not par.exists():
            print(f"{arquivo.name:26s} SÓ EXISTE NO DEPOIS")
            diferentes += 1
            continue
        if par.read_bytes() == arquivo.read_bytes():
            digest = hashlib.sha256(arquivo.read_bytes()).hexdigest()[:12]
            print(f"{arquivo.name:26s} idêntico    {digest}")
            continue
        diferentes += 1
        print(f"{arquivo.name:26s} >>> DIFERE  {_onde_difere(par, arquivo)}")
    return diferentes


def main() -> int:
    argumentos = sys.argv[1:]
    if argumentos[:1] == ["--comparar"]:
        return 1 if comparar(Path(argumentos[1]), Path(argumentos[2])) else 0
    if not argumentos:
        print(__doc__)
        return 2
    tamanho = TAMANHO
    if "--tamanho" in argumentos:
        largura, _, altura = argumentos[argumentos.index("--tamanho") + 1].partition("x")
        tamanho = (int(largura), int(altura))
    for caminho in renderizar(Path(argumentos[0]), tamanho):
        print(caminho)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
