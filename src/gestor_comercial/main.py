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


def _carregar_qss() -> str:
    caminho = _RAIZ_PROJETO / "resources" / "qss" / "base.qss"
    return caminho.read_text(encoding="utf-8") if caminho.exists() else ""


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(_carregar_qss())

    try:
        _aplicar_migrations()
        _rodar_seed()
    except Exception as erro:  # banco não sobe -> nada no app funciona
        QMessageBox.critical(
            None,
            "Erro ao iniciar",
            f"Não foi possível preparar o banco de dados:\n\n{erro}",
        )
        return 1

    # Import tardio: só depois que os mappers do domain já foram registrados
    # pelas migrations/seed acima, e para não pagar o custo de importar
    # PySide6 + todas as views antes de sabermos que o banco sobe.
    from gestor_comercial.repository.unit_of_work import UnitOfWork
    from gestor_comercial.services.auth_service import AuthService
    from gestor_comercial.services.caixa_service import CaixaService
    from gestor_comercial.services.cardapio_service import CardapioService
    from gestor_comercial.services.comanda_service import ComandaService
    from gestor_comercial.services.impressao_service import ImpressaoService
    from gestor_comercial.services.pagamento_service import PagamentoService
    from gestor_comercial.ui.main_window import MainWindow

    # Um único UnitOfWork por processo (ver docstring de UnitOfWork): app
    # desktop de usuário único, sem servidor, então a Session dele serve de
    # cache e evita reabrir conexão a cada clique.
    uow = UnitOfWork()
    auth_service = AuthService(uow)
    comanda_service = ComandaService(uow, auth_service)
    cardapio_service = CardapioService(uow, auth_service)
    caixa_service = CaixaService(uow, auth_service)
    pagamento_service = PagamentoService(uow, auth_service, comanda_service)
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
    )
    janela.showMaximized()

    codigo_saida = app.exec()
    uow.fechar()
    return codigo_saida


if __name__ == "__main__":
    sys.exit(main())
