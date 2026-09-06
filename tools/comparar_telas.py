"""Bancada de paridade visual: renderiza telas do app em PNG, offscreen.

Existe porque a Fase 6 mexeu na montagem de duas telas inteiras, e "a suíte
está verde" não prova que o pai do Vitor vê a mesma coisa no balcão: nenhum
teste compara pixel. Renderizando a mesma tela com o código de antes e o de
depois, o `diff` responde direto.

Roda sem dependência nova (só PySide6 e SQLAlchemy, que já são do projeto) e
fica fora de `src/`, então não entra no `.exe`.

    # o "depois" — código da árvore de trabalho
    python tools/comparar_telas.py C:\\tmp\\depois

    # o "antes" — a mesma bancada contra outro commit
    git worktree add C:\\tmp\\head HEAD
    PYTHONPATH=C:\\tmp\\head/src python tools/comparar_telas.py C:\\tmp\\antes

    python tools/comparar_telas.py --comparar C:\\tmp\\antes C:\\tmp\\depois

Cada tela é gravada em três estados, porque foi assim que os defeitos das
fases anteriores apareceram: tema escuro, tema claro (§3.15 — cor congelada na
construção só aparece ao trocar o tema) e com um operador filtrado (§ pílulas
do filtro, cujo destaque depende de estado interno).

O banco é em memória e o mês vem vazio de propósito: o objetivo é comparar a
*montagem* da tela, e um banco com data real mudaria os números a cada dia,
tornando duas execuções incomparáveis.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TAMANHO = (1280, 800)
OPERADOR = "Joana"


def _montar_servicos():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import gestor_comercial.domain  # noqa: F401 - registra os mappers
    from gestor_comercial.domain.enums import CargoFuncionario, PerfilUsuario
    from gestor_comercial.repository.base import Base
    from gestor_comercial.repository.unit_of_work import UnitOfWork
    from gestor_comercial.services.auth_service import AuthService
    from gestor_comercial.services.caixa_service import CaixaService
    from gestor_comercial.services.funcionario_service import FuncionarioService
    from gestor_comercial.services.impressao_service import ImpressaoService
    from gestor_comercial.services.loja_config_service import SENHA_MASTER_PADRAO

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    uow = UnitOfWork(session=sessionmaker(bind=engine)())
    auth = AuthService(uow)
    funcionarios = FuncionarioService(uow, auth)

    gerente = auth.criar_usuario("Gerente", PerfilUsuario.GERENTE)
    auth.login_como(gerente.id, SENHA_MASTER_PADRAO)
    # Um Caixa aparece nas pílulas do filtro quando existe `Funcionario` ativo
    # com cargo Caixa **e** `Usuario` de login de mesmo nome.
    funcionarios.criar(OPERADOR, CargoFuncionario.CAIXA.value)
    auth.criar_usuario(OPERADOR, PerfilUsuario.OPERADOR_CAIXA)

    return {
        "auth": auth,
        "funcionarios": funcionarios,
        "caixas": CaixaService(uow, auth),
        "impressao": ImpressaoService(uow, auth),
    }


def renderizar(destino: Path) -> list[Path]:
    from PySide6.QtWidgets import QApplication, QPushButton

    app = QApplication.instance() or QApplication([])

    from gestor_comercial.ui.theme.controller import ThemeController
    from gestor_comercial.ui.views.dashboard_mensal_view import DashboardMensalView
    from gestor_comercial.ui.views.historico_caixa_view import HistoricoCaixaView

    ThemeController.instancia().aplicar_inicial()
    servicos = _montar_servicos()
    telas = {
        "historico": HistoricoCaixaView(
            servicos["caixas"], servicos["auth"], servicos["impressao"], servicos["funcionarios"]
        ),
        "dashboard": DashboardMensalView(servicos["caixas"], servicos["funcionarios"]),
    }

    destino.mkdir(parents=True, exist_ok=True)
    gerados = []

    def gravar(nome: str, tela, estado: str) -> None:
        app.processEvents()
        caminho = destino / f"{nome}-{estado}.png"
        tela.grab().save(str(caminho))
        gerados.append(caminho)

    for nome, tela in telas.items():
        tela.resize(*TAMANHO)
        tela.atualizar()
        gravar(nome, tela, "escuro")

        pilula = next(b for b in tela.findChildren(QPushButton) if b.text() == OPERADOR)
        pilula.click()
        gravar(nome, tela, "operador")

        ThemeController.instancia().alternar_para(True)
        tela.atualizar()
        gravar(nome, tela, "claro")
        ThemeController.instancia().alternar_para(False)

    return gerados


def comparar(antes: Path, depois: Path) -> int:
    diferentes = 0
    for arquivo in sorted(depois.glob("*.png")):
        par = antes / arquivo.name
        if not par.exists():
            print(f"{arquivo.name:26s} SÓ EXISTE NO DEPOIS")
            diferentes += 1
            continue
        igual = par.read_bytes() == arquivo.read_bytes()
        marca = "idêntico" if igual else ">>> DIFERE"
        print(f"{arquivo.name:26s} {marca}  {hashlib.sha256(arquivo.read_bytes()).hexdigest()[:12]}")
        diferentes += 0 if igual else 1
    return diferentes


def main() -> int:
    argumentos = sys.argv[1:]
    if argumentos[:1] == ["--comparar"]:
        return 1 if comparar(Path(argumentos[1]), Path(argumentos[2])) else 0
    if not argumentos:
        print(__doc__)
        return 2
    for caminho in renderizar(Path(argumentos[0])):
        print(caminho)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
