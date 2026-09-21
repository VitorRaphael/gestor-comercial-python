"""Ponto de entrada do PDV desktop.

Cuida só do que precisa acontecer uma vez por processo: criar o banco de
produção a partir da semente embutida (só na primeira abertura do `.exe`),
aplicar as migrations do Alembic, rodar o seed (mesas + gerente padrão), montar
o `UnitOfWork` único que vive o processo inteiro (ver docstring de
`UnitOfWork`, §3.1 da arquitetura) e os services em cima dele, aplicar o
tema QSS (o que o operador escolheu da última vez) e abrir `MainWindow`. A composição das telas fica em
`ui/main_window.py`.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from gestor_comercial.core.caminhos import caminho_do_banco, recurso

# O identificador com que o Windows agrupa as janelas na barra de tarefas. Sem
# ele, rodando pelo `python.exe` o botão da barra mostra o ícone do Python; com
# ele, a barra usa o ícone da janela. O atalho do instalador
# (`packaging/instalador.iss`) grava o MESMO valor: se divergissem, o programa
# fixado na barra e o programa aberto virariam dois botões separados.
ID_DO_APP_NO_WINDOWS = "gestor.comercial.pdv.v2"
ICONE_DO_APP = "resources/icons/app_icon.ico"


def _identificar_processo_no_windows() -> None:
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ID_DO_APP_NO_WINDOWS)
    except Exception:  # fora do Windows, ou shell sem a função: só perde o agrupamento
        pass


def _provisionar_banco() -> None:
    """Na primeira abertura do `.exe`, cria o banco a partir da semente embutida.

    Roda antes de qualquer conexão com o banco — a migration abriria (e criaria)
    um arquivo vazio no lugar onde a semente tem que entrar. Ver
    `core/banco_semente.py`.
    """
    from gestor_comercial.core.banco_semente import PASTA_DA_SEMENTE, provisionar
    from gestor_comercial.core.resilience import logger_do_app

    resultado = provisionar(caminho_do_banco(), recurso(PASTA_DA_SEMENTE))
    logger_do_app().info("Banco de dados: %s (%s)", resultado.situacao.value, resultado.banco)


def _aplicar_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(recurso("alembic.ini")))
    # O `alembic.ini` manda o progresso das migrations para o `stderr`, e o
    # espelho do escudo transformaria cada uma daquelas linhas informativas num
    # ERROR no log do app — 17 delas num boot saudável, afogando qualquer erro
    # de verdade. Esta bandeira pede a `migrations/env.py` que cale o progresso
    # **só quando quem chama é o boot**; pela linha de comando o Vitor continua
    # vendo tudo. Se a migration falhar, o `except` de `main()` registra a
    # exceção inteira, que é a informação que importa.
    config.attributes["boot_do_app"] = True
    command.upgrade(config, "head")


def _rodar_seed() -> None:
    from gestor_comercial.repository.seed import run_seed

    run_seed()


def _registrar_fonte_marca() -> None:
    """Carrega a fonte "Archivo Black" (letra de forma, grossa e forte, ver
    `resources/fonts/`) para todo o app poder usá-la via `font-family` no
    QSS — não é fonte de sistema, então precisa ser embutida e registrada
    manualmente."""
    caminho_fonte = recurso("resources/fonts/ArchivoBlack-Regular.ttf")
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
    _identificar_processo_no_windows()

    app = QApplication(sys.argv)
    # No `QApplication`, e não só na `MainWindow`: vale para toda janela que
    # abrir sem pai, inclusive o "Erro ao iniciar" logo abaixo.
    app.setWindowIcon(QIcon(str(recurso(ICONE_DO_APP))))
    _registrar_fonte_marca()

    from gestor_comercial.ui.theme.controller import ThemeController

    ThemeController.instancia().aplicar_inicial()

    try:
        _provisionar_banco()
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
    from gestor_comercial.services.preferencia_service import PreferenciaService
    from gestor_comercial.ui.main_window import MainWindow
    from gestor_comercial.ui.widgets.aviso_impressao import aguardar_repintando

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
            #
            # `aguardar` é o que faz a impressão não congelar a tela (Fase 3 de
            # `Mitigação de Falhas.md`): a conversa com o cabo roda numa thread e
            # esta espera mantém a janela repintando, sem aceitar clique novo. O
            # service não importa Qt — a escolha é injetada aqui.
            impressao_service = ImpressaoService(
                uow, auth_service, aguardar=aguardar_repintando
            )

            # O tema escolhido da última vez, aplicado ANTES de montar a
            # janela: as telas nascem na paleta certa, sem repintura. Uma
            # leitura por chave primária — e daqui em diante toda troca de
            # tema grava na hora (ver `ThemeController.restaurar`).
            ThemeController.instancia().restaurar(PreferenciaService(uow))

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
            # Com o "Boot" lá de cima, dá no log o tempo que o Celeron leva até a
            # tela — e é a linha que a prova de fumaça do build espera ver.
            logger.info("Janela principal aberta")

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
