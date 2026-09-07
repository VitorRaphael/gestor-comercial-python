"""Caixa-preta e escudo anti-crash do PDV (ver `Mitigação de Falhas.md`).

Este módulo existe por causa de um achado que inverteu a prioridade da etapa
inteira (§1.1 daquele documento). A suposição era "o programa fecha sozinho".
Medido nesta máquina, com o PySide6 6.11.2 do projeto, o que acontece é o
oposto e é pior:

- Exceção não tratada dentro de um slot **não derruba o processo**. O Qt
  imprime o traceback no `stderr` e o laço de eventos segue.
- O `.exe` é empacotado com `console=False` (`packaging/build.spec`), então no
  food truck **não existe `stderr`** para onde esse traceback possa ir.

Somados: o pai do Vitor clica em "Enviar Pedido", a tela não muda, nada é
impresso, nada é gravado, nenhuma mensagem aparece — e **não fica registro
nenhum**. Ele clica de novo achando que não acertou o toque. O defeito não
derruba o programa; ele evapora, e depois é indiagnosticável, porque não há uma
linha sequer para alguém ler.

Por isso a ordem aqui é log primeiro, aviso depois.

**Mas existe um caminho em que o programa morre de verdade, e ele é o único.**
Medido também aqui (`Mitigação de Falhas.md` §1.6): quando uma exceção escapa de
um **override de método virtual** do Qt (`paintEvent`, `resizeEvent`, `sizeHint`,
`mousePressEvent`...), o PySide6 imprime `Error calling Python override`, chama o
excepthook — e **na segunda ocorrência aborta o processo**, com código 1. Não há
excepthook que salve: o `abort()` acontece no C++ depois de o hook retornar.

Ou seja, os dois diagnósticos estão certos, em caminhos diferentes:

| Caminho | O que acontece de verdade |
|---|---|
| Slot de sinal | App sobrevive para sempre; sem log, o erro **evapora** |
| Override virtual | 1ª vez registra, **2ª vez o processo morre e a janela some** |
| Fora do `app.exec()` | Processo morre na hora |

Daí as **quatro peças** desta blindagem:

1. `sys.excepthook` — pega exceção em slot de sinal (`botao.clicked`), em
   override virtual e qualquer estouro fora do laço de eventos.
2. `nao_deixa_escapar` — decorador obrigatório nos overrides virtuais. É a
   **única** defesa possível contra o abort acima, porque impede a exceção de
   chegar ao C++. As outras três peças registram; só esta evita.
3. Desvio do `sys.stderr` — o PySide6 escreve o cabeçalho `Error calling Python
   override` direto no `stderr`, fora do excepthook, e o `.exe` não tem
   `stderr`. Sem o espelho, essa metade da mensagem some.
4. `try/except` no `main()` — para o estouro fora do `app.exec()` (migrations,
   seed, montagem das views, teardown). Esse fica em `main.py`, não aqui.

Só stdlib, por RNF: `logging`, `sys`, `os`, `time`, `threading`, `traceback`,
`pathlib`. Nada de Sentry, watchdog ou daemon — o teto é de ~90 MB de RAM num
Celeron.
"""

from __future__ import annotations

import functools
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, TextIO

NOME_LOGGER = "gestor_comercial"

# 2 MB por arquivo e 2 backups: teto de 6 MB de disco, para sempre. O disco da
# máquina do food truck é pequeno e o programa vai ficar meses ligado — sem
# rotação, um erro repetitivo (um `paintEvent` que estoura a cada repintura)
# encheria a partição sozinho em um turno.
TAMANHO_MAXIMO_BYTES = 2 * 1024 * 1024
BACKUPS_MANTIDOS = 2

# Anti-repique do modal (§3, Fase 2). Erro em repintura dispara a cada frame:
# sem limitador, o operador leva centenas de modais empilhados e o PDV fica
# inutilizável — o escudo viraria exatamente o travamento que ele deve evitar.
# O LOG continua recebendo todas as ocorrências; o que é limitado é a interrupção
# da tela.
SEGUNDOS_ENTRE_MODAIS = 30.0

MENSAGEM_AMIGAVEL = (
    "Ocorreu uma oscilação pontual nesta ação, mas seus dados continuam "
    "salvos. O sistema continua operando."
)

TITULO_MODAL = "Aviso do sistema"


# ----------------------------------------------------------------------
# Onde mora o log
# ----------------------------------------------------------------------


def pasta_de_dados() -> Path:
    """A pasta de dados do app, derivada em runtime e nunca gravada.

    Mesma escolha (e mesma variável de ambiente) de `repository/base.py` e
    `hardware/impressora_escpos.py`, mas montada aqui com `os.environ` em vez de
    importada: `core/` é a camada mais baixa e não pode depender de `repository/`
    — se dependesse, configurar o log exigiria carregar SQLAlchemy antes, e o log
    tem que existir *antes* de qualquer coisa que possa falhar.
    """
    bruto = os.environ.get("GESTOR_COMERCIAL_DB")
    if bruto and bruto != ":memory:":
        return Path(bruto).expanduser().parent
    return Path.home() / ".gestor_comercial"


def caminho_do_log() -> Path:
    """`<dir_dados>/logs/gestor.log`.

    Fora do diretório do `.exe` de propósito: o PyInstaller extrai o bundle numa
    pasta temporária a cada boot (`sys._MEIPASS`), então um log gravado ali seria
    apagado justamente antes de alguém poder lê-lo. Ao lado do banco, ele
    sobrevive a reinstalar o programa — igual ao `.db` e à pasta `backups/`.
    """
    return pasta_de_dados() / "logs" / "gestor.log"


# ----------------------------------------------------------------------
# Fase 1 — a caixa-preta
# ----------------------------------------------------------------------


def configurar_log(caminho: Path | str | None = None) -> logging.Logger:
    """Liga o log rotativo em disco e devolve o logger do app.

    Idempotente: chamar duas vezes não duplica handler (e não duplica linha no
    arquivo). Isso importa porque a suíte chama isto muitas vezes num mesmo
    processo.

    **Nunca levanta.** Se a pasta não puder ser criada (disco cheio, pendrive
    removido, permissão), o app perde o log mas continua abrindo — ficar sem
    caixa-preta é ruim, não abrir o PDV no meio do almoço é pior.
    """
    logger = logging.getLogger(NOME_LOGGER)
    logger.setLevel(logging.INFO)
    # `propagate=False` para o log do app não vazar para o root, que o Alembic
    # configura em todo boot (`_aplicar_migrations`) — sem isso cada linha nossa
    # sairia duas vezes.
    logger.propagate = False

    destino = Path(caminho) if caminho is not None else caminho_do_log()

    if any(getattr(h, "_gestor_comercial", False) for h in logger.handlers):
        return logger

    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            destino,
            maxBytes=TAMANHO_MAXIMO_BYTES,
            backupCount=BACKUPS_MANTIDOS,
            encoding="utf-8",
            # `delay=True`: não abre o arquivo até a primeira linha. Economiza um
            # handle no boot do caminho feliz (RNF de otimização) e evita criar
            # `gestor.log` vazio em quem só abriu e fechou o programa.
            delay=True,
        )
    except OSError:
        return logger

    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    # Marca própria em vez de checar `isinstance`: a suíte instala handlers
    # temporários e este atributo é o que distingue "o nosso" de "o do teste".
    handler._gestor_comercial = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return logger


def logger_do_app() -> logging.Logger:
    return logging.getLogger(NOME_LOGGER)


# ----------------------------------------------------------------------
# Fase 2 — o escudo
# ----------------------------------------------------------------------


def nao_deixa_escapar(retorno: object = None) -> Callable:
    """Decorador **obrigatório** em todo override de método virtual do Qt.

    É a peça 2 do escudo, e a única que de fato *evita* uma falha em vez de só
    registrá-la. Sem ela, uma exceção que escapa de `paintEvent` (ou de
    `mousePressEvent`, `sizeHint`, `resizeEvent`, `eventFilter`...) chega ao C++
    do Qt, e na **segunda** ocorrência o PySide6 aborta o processo: a janela
    some do balcão no meio do atendimento, com código de saída 1 e uma mensagem
    num `stderr` que o `.exe` não tem. Provado em
    `tests/ui/test_caos.py::test_c6_*`.

    Nenhum `sys.excepthook` resolve isso, porque o `abort()` acontece depois de
    o hook já ter rodado. A exceção tem que morrer aqui, do lado Python.

    `retorno` é o valor devolvido quando o método estoura, e **precisa** ser
    informado quando o Qt espera algo de volta: `False` num `eventFilter`
    ("não consumi o evento", que é o padrão seguro) e um `QSize` num `sizeHint`.
    Devolver `None` nesses dois casos trocaria o abort por um `TypeError` na
    conversão para C++ — o mesmo problema com outro nome. Para os `*Event`, que
    são `void`, o padrão `None` está correto.

    Uso:

        @nao_deixa_escapar()
        def paintEvent(self, evento): ...

        @nao_deixa_escapar(retorno=False)
        def eventFilter(self, obj, evento): ...

    O teste `test_todo_override_virtual_esta_blindado` reprova qualquer override
    novo que esqueça o decorador — é o que impede a blindagem de se perder na
    próxima tela.
    """

    def decorador(metodo: Callable) -> Callable:
        @functools.wraps(metodo)
        def envelope(self: object, *args: Any, **kwargs: Any) -> Any:
            try:
                return metodo(self, *args, **kwargs)
            except Exception:
                # Registra e engole. A tela pode ficar com um pedaço sem
                # desenhar ou um clique sem efeito — o que é ruim, mas é
                # infinitamente melhor que o PDV fechar sozinho, e o log diz
                # exatamente qual widget falhou.
                try:
                    logger_do_app().exception(
                        "Erro contido em %s.%s — o Qt teria derrubado o app",
                        type(self).__name__,
                        metodo.__name__,
                    )
                except Exception:
                    pass
                return retorno

        envelope._blindado = True  # type: ignore[attr-defined]
        return envelope

    return decorador


class _DesvioDeStderr:
    """Espelha o `stderr` no log, **sem** tirá-lo do console de desenvolvimento.

    Espelha, e não substitui, de propósito: em desenvolvimento o Vitor continua
    vendo o traceback no terminal na hora em que acontece, e no `.exe` (onde
    `sys.stderr` é `None`) a mesma linha vira registro em disco. Trocar um pelo
    outro obrigaria a escolher entre depurar aqui e ter evidência lá.

    O `_reentrante` não é zelo excessivo: o `logging` escreve no `stderr` quando
    ele próprio falha (`handleError`). Sem a trava, uma falha de escrita no
    arquivo de log viraria recursão infinita e derrubaria o app — o escudo
    matando o programa que veio proteger.
    """

    def __init__(self, original: TextIO | None, logger: logging.Logger) -> None:
        self._original = original
        self._logger = logger
        self._pendente = ""
        self._reentrante = threading.local()

    def write(self, texto: str) -> int:
        if self._original is not None:
            try:
                self._original.write(texto)
            except Exception:
                pass

        if getattr(self._reentrante, "ativo", False):
            return len(texto)

        self._reentrante.ativo = True
        try:
            # O Qt escreve o traceback em vários `write()` picotados; juntar até
            # a quebra de linha é o que faz o arquivo de log ficar legível em vez
            # de uma linha por fragmento.
            self._pendente += texto
            while "\n" in self._pendente:
                linha, self._pendente = self._pendente.split("\n", 1)
                if linha.strip():
                    self._logger.error("[stderr] %s", linha.rstrip())
        except Exception:
            pass
        finally:
            self._reentrante.ativo = False
        return len(texto)

    def flush(self) -> None:
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return bool(self._original is not None and self._original.isatty())

    @property
    def encoding(self) -> str:
        return getattr(self._original, "encoding", "utf-8") or "utf-8"


class _LimitadorDeModal:
    """Deixa passar um modal por assinatura de erro a cada `janela` segundos.

    A assinatura é o tipo da exceção + o último quadro do traceback (arquivo e
    linha). Dois defeitos diferentes acontecendo juntos ainda produzem dois
    avisos; o mesmo defeito repetindo a 60 quadros por segundo produz um.
    """

    def __init__(self, janela: float = SEGUNDOS_ENTRE_MODAIS) -> None:
        self._janela = janela
        self._ultimos: dict[str, float] = {}
        self._trava = threading.Lock()

    def liberar(self, assinatura: str, agora: float | None = None) -> bool:
        instante = time.monotonic() if agora is None else agora
        with self._trava:
            anterior = self._ultimos.get(assinatura)
            if anterior is not None and instante - anterior < self._janela:
                return False
            self._ultimos[assinatura] = instante
            # O dicionário é limpo do que já saiu da janela para o app não
            # acumular uma entrada por defeito distinto ao longo de semanas
            # ligado (RNF de memória).
            for chave, quando in list(self._ultimos.items()):
                if instante - quando >= self._janela:
                    del self._ultimos[chave]
            return True


def assinatura_do_erro(
    tipo: type[BaseException], tb: TracebackType | None
) -> str:
    """`'ZeroDivisionError@caixa_view.py:649'` — o que o anti-repique compara."""
    ultimo = tb
    while ultimo is not None and ultimo.tb_next is not None:
        ultimo = ultimo.tb_next
    if ultimo is None:
        return tipo.__name__
    quadro = ultimo.tb_frame
    return f"{tipo.__name__}@{Path(quadro.f_code.co_filename).name}:{ultimo.tb_lineno}"


def _mostrar_modal_qt(caminho_log: Path) -> None:
    """Aviso amigável, só quando já existe uma `QApplication` de pé.

    Sem `QApplication` (import de módulo, teste de unidade, estouro antes de o Qt
    subir) não há como abrir janela — e forçar uma aqui travaria o processo. Nesse
    caso o registro em disco é o que resta, e é justamente o que a Fase 1 garante.

    Import do PySide6 dentro da função: `core/` é carregado no primeiro instante
    do boot e não pode arrastar o Qt junto.
    """
    from PySide6.QtWidgets import QApplication, QMessageBox

    if QApplication.instance() is None:
        return

    caixa = QMessageBox()
    caixa.setIcon(QMessageBox.Icon.Information)
    caixa.setWindowTitle(TITULO_MODAL)
    caixa.setText(MENSAGEM_AMIGAVEL)
    # O caminho do log vai no "Ver detalhes" (recolhido) e não no corpo: o
    # operador não precisa dele, e o Vitor precisa muito — sem isso o suporte
    # depende do pai conseguir descrever o erro por telefone.
    caixa.setDetailedText(f"Registro técnico desta ocorrência:\n{caminho_log}")
    caixa.setStandardButtons(QMessageBox.StandardButton.Ok)
    caixa.exec()


def instalar_escudo(
    caminho_log: Path | str | None = None,
    mostrar_modal: Callable[[Path], None] | None = None,
    limitador: _LimitadorDeModal | None = None,
) -> logging.Logger:
    """Liga log + `sys.excepthook` + espelho do `stderr`. Ponto único de entrada.

    Chamada na primeira linha de `main()`, antes de `QApplication`, antes das
    migrations, antes de qualquer widget: o que vier depois já cai na rede.

    `mostrar_modal` e `limitador` existem para o teste de caos poder observar o
    escudo sem abrir janela de verdade.
    """
    destino = Path(caminho_log) if caminho_log is not None else caminho_do_log()
    logger = configurar_log(destino)
    aviso = mostrar_modal if mostrar_modal is not None else _mostrar_modal_qt
    porteiro = limitador if limitador is not None else _LimitadorDeModal()

    def escudo(
        tipo: type[BaseException],
        valor: BaseException,
        tb: TracebackType | None,
    ) -> None:
        # Ctrl+C e `sys.exit()` são saída pedida, não defeito: viram registro de
        # modal e poluiriam o log de quem roda pelo terminal.
        if issubclass(tipo, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(tipo, valor, tb)
            return

        # O log vem ANTES do modal, e num `try` próprio: se abrir a janela
        # falhar (Qt já derrubado no encerramento, por exemplo), a evidência já
        # está gravada. Ao contrário, perderíamos as duas coisas.
        try:
            logger.error(
                "Exceção não tratada:\n%s",
                "".join(traceback.format_exception(tipo, valor, tb)).rstrip(),
            )
        except Exception:
            pass

        try:
            if porteiro.liberar(assinatura_do_erro(tipo, tb)):
                aviso(destino)
        except Exception:
            # Falha ao avisar não pode virar uma segunda exceção não tratada
            # dentro do próprio excepthook — seria recursão sem saída.
            pass

    sys.excepthook = escudo

    if not isinstance(sys.stderr, _DesvioDeStderr):
        sys.stderr = _DesvioDeStderr(sys.stderr, logger)  # type: ignore[assignment]

    return logger
