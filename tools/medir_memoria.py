"""Mede o RSS do app por estágio de boot — o roteiro do §2.3 da Remasterização.

    python tools/medir_memoria.py
    python tools/medir_memoria.py --roteiro-antigo

Roda headless (`QT_QPA_PLATFORM=offscreen`) contra um banco temporário, então
não encosta no banco de produção nem abre janela. Não é código de aplicação:
mora fora de `src/` e não entra no `.exe`.

## Por que existe como arquivo, e não como comando avulso

A medição original do §2.3 foi feita à mão e virou a linha de base da
Remasterização inteira — mas sem o roteiro salvo, o "depois" nunca seria
comparável com o "antes". Pior: foi assim que o §3.2 e o §3.3 entraram no
documento como vazamentos que não existiam. Uma bancada de medição que ninguém
consegue repetir é uma bancada que ninguém consegue conferir.

## `ctypes` em vez de `psutil`

Regra dura desta remasterização: **nenhuma dependência nova entra**, nem em
ferramenta de bancada. `GetProcessMemoryInfo` vem do próprio Windows.

## A armadilha que esta bancada já pisou uma vez

`QApplication.processEvents()` **não** despacha `DeferredDelete`. O Qt segura
esses eventos até o laço em que foram agendados terminar, e num script não
existe laço nenhum — então `deleteLater()` fica pendente para sempre e a
contagem acusa vazamento onde só há destruição adiada. Foi exatamente isso que
inflou o §3.2/§3.3. Daí o `_assentar()` daqui mandar
`sendPostedEvents(DeferredDelete)` explicitamente, igual à fixture `assentar`
da suíte, e os modais serem abertos com `exec()` de verdade.
"""

from __future__ import annotations

import ctypes
import gc
import os
import sys
import tempfile
from pathlib import Path

_RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RAIZ / "src"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ABERTURAS_DE_MODAL = 300


def _leitor_de_rss_windows():
    """Prepara `GetProcessMemoryInfo` uma vez e devolve a função de leitura.

    As três linhas de `argtypes`/`restype` não são cerimônia: sem
    `restype = HANDLE`, o ctypes trata o retorno de `GetCurrentProcess()` como
    `c_int` e trunca o pseudo-handle, a chamada falha, e como ninguém checa o
    `BOOL` de retorno a struct volta **zerada** — a bancada imprime 0,0 MB em
    todos os estágios e parece que o app não usa memória nenhuma. Aconteceu.
    Por isso o `raise` abaixo: medição errada é pior que medição ausente.
    """
    from ctypes import wintypes

    class _ContadoresDeMemoria(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    psapi = ctypes.WinDLL("psapi")
    kernel32 = ctypes.WinDLL("kernel32")
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ContadoresDeMemoria),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    def ler() -> float:
        contadores = _ContadoresDeMemoria()
        contadores.cb = ctypes.sizeof(contadores)
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(contadores), contadores.cb
        ):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo falhou")
        return contadores.WorkingSetSize / 1024 / 1024

    return ler


def _ler_rss_posix() -> float:
    """Fallback POSIX, para a bancada não ficar presa a uma máquina só."""
    paginas = int(Path("/proc/self/statm").read_text().split()[1])
    return paginas * os.sysconf("SC_PAGE_SIZE") / 1024 / 1024


rss_mb = _leitor_de_rss_windows() if sys.platform == "win32" else _ler_rss_posix


_medidas: list[tuple[str, float]] = []


def marcar(estagio: str) -> float:
    valor = rss_mb()
    _medidas.append((estagio, valor))
    anterior = _medidas[-2][1] if len(_medidas) > 1 else 0.0
    delta = f"{valor - anterior:+6.1f}" if len(_medidas) > 1 else "      "
    print(f"  {estagio:<44} {valor:7.1f} MB  {delta}")
    return valor


def main(roteiro_antigo: bool = False) -> int:
    rotulo = "roteiro ANTIGO (§2.3, sem exec)" if roteiro_antigo else "caminho real do app"
    print("")
    print(f"RSS por estágio — {rotulo}")
    print(f"{sys.platform}, Python {sys.version.split()[0]}")
    print("-" * 72)
    marcar("Interpretador nu")

    from PySide6.QtCore import QCoreApplication, QEvent, QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    marcar("+ QApplication")

    def assentar() -> None:
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        gc.collect()
        app.processEvents()

    # `ignore_cleanup_errors`: no Windows o SQLite ainda segura o arquivo do
    # banco quando o bloco termina, e um erro de FAXINA não pode derrubar a
    # medição que acabou de rodar. O diretório é temporário de qualquer forma.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as pasta:
        os.environ["GESTOR_COMERCIAL_DB"] = str(Path(pasta) / "medicao.db")

        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(str(_RAIZ / "alembic.ini")), "head")
        from gestor_comercial.repository.seed import run_seed

        run_seed()
        marcar("+ migrations Alembic + seed")

        from gestor_comercial.repository.unit_of_work import UnitOfWork
        from gestor_comercial.services.auth_service import AuthService
        from gestor_comercial.services.caixa_service import CaixaService
        from gestor_comercial.services.cardapio_service import CardapioService
        from gestor_comercial.services.comanda_service import ComandaService
        from gestor_comercial.services.funcionario_service import FuncionarioService
        from gestor_comercial.services.impressao_service import ImpressaoService
        from gestor_comercial.services.pagamento_service import PagamentoService
        from gestor_comercial.ui.main_window import MainWindow
        from gestor_comercial.ui.theme.controller import ThemeController
        from gestor_comercial.ui.views.cancelamento_dialog import CancelamentoDialog

        ThemeController.instancia().aplicar_inicial()

        with UnitOfWork() as uow:
            auth = AuthService(uow)
            comandas = ComandaService(uow, auth)
            cardapio = CardapioService(uow, auth)
            caixas = CaixaService(uow, auth)
            funcionarios = FuncionarioService(uow, auth)
            pagamentos = PagamentoService(uow, auth, comandas, funcionarios)
            impressao = ImpressaoService(uow, auth)

            janela = MainWindow(
                auth, comandas, cardapio, caixas, pagamentos, impressao, funcionarios
            )
            janela.show()
            app.processEvents()
            baseline = marcar("+ shell completo, telas montadas")

            if roteiro_antigo:
                # O roteiro do §2.3 exatamente como foi rodado na Fase 1: SEM
                # `exec()` e assentando só com `processEvents()`. Está aqui para
                # a comparação "antes x depois" do §7 poder ser conferida em vez
                # de acreditada — é este roteiro que produz os +40 MB e os 300
                # modais vivos, e ele os produz **hoje também**, com a Fase 4
                # pronta. A diferença entre as duas colunas do §7 é o método, não
                # a correção.
                for _ in range(ABERTURAS_DE_MODAL):
                    modal = CancelamentoDialog("Cancelar item", janela)
                    modal.reject()
                    del modal
                gc.collect()
                app.processEvents()
            else:
                # O caminho real do app: `exec()` de verdade, fechado pelo botão
                # do usuário. O `singleShot` faz o papel do dedo do operador.
                for _ in range(ABERTURAS_DE_MODAL):
                    modal = CancelamentoDialog("Cancelar item", janela)
                    QTimer.singleShot(0, modal.reject)
                    modal.exec()
                    del modal
                assentar()
            depois = marcar(f"+ {ABERTURAS_DE_MODAL} aberturas de modal")

            vivos = len(janela.findChildren(CancelamentoDialog))
            print("-" * 72)
            print(f"  Crescimento dos {ABERTURAS_DE_MODAL} modais: {depois - baseline:+.1f} MB")
            print(f"  Modais ainda presos à janela:      {vivos} de {ABERTURAS_DE_MODAL}")
            if roteiro_antigo:
                print(
                    "  (roteiro antigo: 300 vivos e +40 MB são o ESPERADO — "
                    "artefato de medir sem `exec()`, não vazamento do app)"
                )
            print()

            janela.close()
            if roteiro_antigo:
                return 0
            return 0 if vivos == 0 else 1


if __name__ == "__main__":
    sys.exit(main(roteiro_antigo="--roteiro-antigo" in sys.argv))
