"""Ponto de entrada do PDV desktop.

Cuida só do que precisa acontecer uma vez por processo: aplicar as
migrations do Alembic, rodar o seed (mesas + gerente padrão), montar o
`UnitOfWork` único que vive o processo inteiro (ver docstring de
`UnitOfWork`, §3.1 da arquitetura) e os services em cima dele, aplicar o
tema QSS e abrir `MainWindow`. A composição das telas fica em
`ui/main_window.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox


def _raiz_recursos() -> Path:
    """Raiz de onde ler `alembic.ini`, `migrations/` e `resources/`.

    Em desenvolvimento é a raiz do repositório (2 níveis acima deste
    arquivo). Empacotado pelo PyInstaller (`packaging/build.spec`), o
    processo roda a partir de uma pasta temporária de extração
    (`sys._MEIPASS`) que contém esses mesmos itens copiados pelo `datas`
    do spec — por isso o caminho não pode ser fixo.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


_RAIZ_PROJETO = _raiz_recursos()


def _aplicar_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(_RAIZ_PROJETO / "alembic.ini"))
    command.upgrade(config, "head")


def _rodar_seed() -> None:
    from gestor_comercial.repository.seed import run_seed

    run_seed()


def _registrar_fonte_marca() -> None:
    """Carrega a fonte "Archivo Black" (letra de forma, grossa e forte, ver
    `resources/fonts/`) para todo o app poder usá-la via `font-family` no
    QSS — não é fonte de sistema, então precisa ser embutida e registrada
    manualmente."""
    caminho_fonte = _RAIZ_PROJETO / "resources" / "fonts" / "ArchivoBlack-Regular.ttf"
    QFontDatabase.addApplicationFont(str(caminho_fonte))


def main() -> int:
    # PRIMEIRA linha de tudo, antes do Qt e antes do banco: daqui pra frente
    # qualquer estouro vira registro em `~/.gestor_comercial/logs/gestor.log`.
    # Ver `core/resilience.py` e `Mitigação de Falhas.md` §1.1 — sem isto, um
    # defeito no food truck não derruba o programa, ele **evapora**: o `.exe` é
    # empacotado com `console=False` e o traceback do Qt não tem para onde ir.
    from gestor_comercial.core.resilience import caminho_do_log, instalar_escudo

    logger = instalar_escudo()
    logger.info("Boot do Gestor Comercial")

    app = QApplication(sys.argv)
    _registrar_fonte_marca()

    from gestor_comercial.ui.theme.controller import ThemeController

    ThemeController.instancia().aplicar_inicial()

    try:
        _aplicar_migrations()
        _rodar_seed()
    except Exception as erro:  # banco não sobe -> nada no app funciona
        logger.exception("Falha ao preparar o banco no boot")
        QMessageBox.critical(
            None,
            "Erro ao iniciar",
            f"Não foi possível preparar o banco de dados:\n\n{erro}",
        )
        return 1

    # Import tardio: só depois que os mappers do domain já foram registrados
    # pelas migrations/seed acima, e para não montar as dez views antes de
    # sabermos que o banco sobe. (O PySide6 em si já entrou no topo deste
    # arquivo — a economia é das views e dos services, não do Qt.)
    from gestor_comercial.repository.unit_of_work import UnitOfWork
    from gestor_comercial.services.auth_service import AuthService
    from gestor_comercial.services.caixa_service import CaixaService
    from gestor_comercial.services.cardapio_service import CardapioService
    from gestor_comercial.services.comanda_service import ComandaService
    from gestor_comercial.services.funcionario_service import FuncionarioService
    from gestor_comercial.services.impressao_service import ImpressaoService
    from gestor_comercial.services.pagamento_service import PagamentoService
    from gestor_comercial.ui.main_window import MainWindow

    # Um único UnitOfWork por processo (ver docstring de UnitOfWork): app
    # desktop de usuário único, sem servidor, então a Session dele serve de
    # cache e evita reabrir conexão a cada clique.
    #
    # `with` e não `uow = UnitOfWork()`: o `__exit__` desfaz o que estiver
    # pendente e fecha a Session mesmo se algo estourar depois daqui — antes
    # ele nunca rodava, porque ninguém usava o UnitOfWork como context manager
    # (ver REMASTERIZACAO-V1.md §3.1).
    # A terceira peça do escudo (`Mitigação de Falhas.md` §1.2). As outras duas
    # — `sys.excepthook` e o espelho do `stderr` — só valem DENTRO do laço de
    # eventos: lá o Qt segue rodando depois do erro. Aqui fora não há laço
    # nenhum, então um estouro ao montar os services ou as views encerra o
    # processo de verdade, e é o único caso em que a janela some (ou nunca
    # aparece). Este `try` é o que troca esse sumiço por uma mensagem.
    try:
        with UnitOfWork() as uow:
            auth_service = AuthService(uow)
            comanda_service = ComandaService(uow, auth_service)
            cardapio_service = CardapioService(uow, auth_service)
            caixa_service = CaixaService(uow, auth_service)
            funcionario_service = FuncionarioService(uow, auth_service)
            pagamento_service = PagamentoService(
                uow, auth_service, comanda_service, funcionario_service
            )
            # Sem `abrir_driver` explícito: em produção vale o driver ESC/POS de
            # verdade. Quem troca isso por um driver falso é a suíte de testes.
            impressao_service = ImpressaoService(uow, auth_service)

            janela = MainWindow(
                auth_service,
                comanda_service,
                cardapio_service,
                caixa_service,
                pagamento_service,
                impressao_service,
                funcionario_service,
            )
            janela.showMaximized()

            codigo = app.exec()

            # Com `journal_mode=WAL` (§8) as últimas transações ficam num arquivo
            # `-wal` ao lado do banco. O checkpoint aqui empurra tudo para dentro
            # do `.db` antes de o processo morrer, para o arquivo principal estar
            # sempre completo com o programa fechado. Depois disto, copiar o
            # `.db` é seguro. Ver `repository/backup.py`.
            from gestor_comercial.repository.backup import consolidar_wal

            consolidar_wal(uow.session)

            logger.info("Encerramento normal, código %s", codigo)
            return codigo
    except Exception as erro:
        logger.exception("Falha fatal fora do laço de eventos")
        QMessageBox.critical(
            None,
            "Erro ao iniciar",
            "O programa não conseguiu abrir. Nenhum dado foi perdido — o "
            "registro técnico está em:\n\n"
            f"{caminho_do_log()}\n\n{erro}",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
