"""A caixa-preta e o escudo, sem Qt (ver `Mitigação de Falhas.md` §3, Fases 1 e 2).

Aqui ficam as garantias que não dependem de janela: o handler rotativo é do
tamanho combinado, o `stderr` vira registro sem perder o console, o anti-repique
conta o tempo direito e o `excepthook` grava antes de avisar.

Os cenários com widget de verdade (C1, C4, C6) estão em `tests/ui/test_caos.py`.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys

import pytest

from gestor_comercial.core import resilience


# `escudo_isolado` vem de `tests/conftest.py`: os testes de caos com Qt
# (`tests/ui/test_caos.py`) precisam exatamente do mesmo isolamento.


# ----------------------------------------------------------------------
# Fase 1 — a caixa-preta
# ----------------------------------------------------------------------


def test_handler_tem_o_tamanho_e_a_rotacao_combinados(tmp_path, escudo_isolado):
    """2 MB × 2 backups = teto de 6 MB de disco, para sempre.

    O número é o contrato com a máquina do food truck: o programa fica meses
    ligado e um defeito repetitivo encheria a partição sozinho sem rotação.
    """
    logger = resilience.configurar_log(tmp_path / "logs" / "gestor.log")

    handlers = [h for h in logger.handlers if getattr(h, "_gestor_comercial", False)]
    assert len(handlers) == 1
    handler = handlers[0]
    assert isinstance(handler, logging.handlers.RotatingFileHandler)
    assert handler.maxBytes == 2 * 1024 * 1024
    assert handler.backupCount == 2
    assert handler.encoding == "utf-8"


def test_configurar_log_e_idempotente(tmp_path, escudo_isolado):
    """Chamar duas vezes não duplica handler — nem duplica linha no arquivo."""
    destino = tmp_path / "logs" / "gestor.log"
    resilience.configurar_log(destino)
    logger = resilience.configurar_log(destino)

    assert sum(1 for h in logger.handlers if getattr(h, "_gestor_comercial", False)) == 1

    logger.error("uma vez só")
    assert destino.read_text(encoding="utf-8").count("uma vez só") == 1


def test_arquivo_so_nasce_na_primeira_linha(tmp_path, escudo_isolado):
    """`delay=True`: quem abriu e fechou o programa sem erro não deixa log vazio."""
    destino = tmp_path / "logs" / "gestor.log"
    logger = resilience.configurar_log(destino)
    assert not destino.exists()

    logger.error("agora sim")
    assert destino.exists()


def test_pasta_impossivel_nao_derruba_o_boot(tmp_path, escudo_isolado, monkeypatch):
    """Ficar sem caixa-preta é ruim; não abrir o PDV no meio do almoço é pior."""

    def mkdir_que_falha(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr("pathlib.Path.mkdir", mkdir_que_falha)

    logger = resilience.configurar_log(tmp_path / "logs" / "gestor.log")
    assert not any(getattr(h, "_gestor_comercial", False) for h in logger.handlers)
    logger.error("não pode levantar")  # não deve estourar


def test_log_nao_vaza_para_o_root(tmp_path, escudo_isolado):
    """O Alembic configura o root em todo boot; sem `propagate=False` cada linha
    nossa sairia duas vezes."""
    logger = resilience.configurar_log(tmp_path / "logs" / "gestor.log")
    assert logger.propagate is False


# ----------------------------------------------------------------------
# Fase 2 — o espelho do stderr
# ----------------------------------------------------------------------


def test_stderr_vira_registro_sem_sumir_do_console(tmp_path, escudo_isolado):
    """Espelha, não substitui: em dev o traceback continua no terminal.

    É a única peça que captura exceção em override virtual do Qt (§1.2), e a
    troca simples obrigaria a escolher entre depurar aqui e ter evidência lá.
    """

    class ConsoleFalso:
        def __init__(self) -> None:
            self.escrito = ""

        def write(self, texto: str) -> int:
            self.escrito += texto
            return len(texto)

        def flush(self) -> None:
            pass

        def isatty(self) -> bool:
            return False

    destino = tmp_path / "logs" / "gestor.log"
    logger = resilience.configurar_log(destino)
    console = ConsoleFalso()
    desvio = resilience._DesvioDeStderr(console, logger)

    desvio.write("Error calling Python override of QWidget::paintEvent()\n")

    assert "paintEvent" in console.escrito
    assert "[stderr] Error calling Python override" in destino.read_text(encoding="utf-8")


def test_stderr_picotado_vira_uma_linha_so(tmp_path, escudo_isolado):
    """O Qt escreve o traceback em vários `write()`; o log tem que ficar legível."""
    destino = tmp_path / "logs" / "gestor.log"
    logger = resilience.configurar_log(destino)
    desvio = resilience._DesvioDeStderr(None, logger)

    for pedaco in ("Runtime", "Error: ", "estouro no ", "paintEvent", "\n"):
        desvio.write(pedaco)

    conteudo = destino.read_text(encoding="utf-8")
    assert "[stderr] RuntimeError: estouro no paintEvent" in conteudo
    assert conteudo.count("[stderr]") == 1


def test_stderr_sem_console_nao_levanta(tmp_path, escudo_isolado):
    """No `.exe` com `console=False`, `sys.stderr` é `None`. Tem que gravar assim mesmo."""
    destino = tmp_path / "logs" / "gestor.log"
    logger = resilience.configurar_log(destino)
    desvio = resilience._DesvioDeStderr(None, logger)

    desvio.write("erro sem console\n")
    desvio.flush()

    assert "erro sem console" in destino.read_text(encoding="utf-8")


def test_falha_do_proprio_log_nao_vira_recursao(tmp_path, escudo_isolado):
    """O `logging` escreve no `stderr` quando ele próprio falha (`handleError`).

    Sem a trava de reentrância isso seria recursão infinita — o escudo matando o
    programa que veio proteger.
    """

    class LoggerQueFalhaNoStderr:
        def __init__(self) -> None:
            self.tentativas = 0

        def error(self, *_args, **_kwargs) -> None:
            self.tentativas += 1
            sys.stderr.write("falha ao gravar o log\n")

    logger_quebrado = LoggerQueFalhaNoStderr()
    desvio = resilience._DesvioDeStderr(None, logger_quebrado)
    sys.stderr = desvio

    desvio.write("primeiro erro\n")

    # Uma tentativa, não infinitas: a segunda escrita foi barrada pela trava.
    assert logger_quebrado.tentativas == 1


# ----------------------------------------------------------------------
# Fase 2 — o anti-repique
# ----------------------------------------------------------------------


def test_limitador_deixa_passar_o_primeiro_e_barra_o_repique():
    limitador = resilience._LimitadorDeModal(janela=30.0)

    assert limitador.liberar("ZeroDivisionError@caixa_view.py:649", agora=100.0)
    assert not limitador.liberar("ZeroDivisionError@caixa_view.py:649", agora=101.0)
    assert not limitador.liberar("ZeroDivisionError@caixa_view.py:649", agora=129.9)
    assert limitador.liberar("ZeroDivisionError@caixa_view.py:649", agora=130.1)


def test_limitador_nao_confunde_defeitos_diferentes():
    """Dois problemas ao mesmo tempo ainda produzem dois avisos."""
    limitador = resilience._LimitadorDeModal(janela=30.0)

    assert limitador.liberar("ZeroDivisionError@caixa_view.py:649", agora=100.0)
    assert limitador.liberar("ValueError@cardapio_view.py:1062", agora=100.1)


def test_limitador_nao_acumula_entradas_ao_longo_do_tempo():
    """RNF de memória: semanas ligado não podem virar um dicionário crescente."""
    limitador = resilience._LimitadorDeModal(janela=30.0)

    for i in range(500):
        limitador.liberar(f"Erro{i}@view.py:{i}", agora=float(i))

    assert len(limitador._ultimos) < 50


def test_assinatura_aponta_o_ultimo_quadro():
    """A assinatura tem que ser onde o erro estourou, não onde foi chamado."""
    try:
        raise ZeroDivisionError("boom")
    except ZeroDivisionError as erro:
        assinatura = resilience.assinatura_do_erro(type(erro), erro.__traceback__)

    assert assinatura.startswith("ZeroDivisionError@test_resiliencia.py:")


# ----------------------------------------------------------------------
# Fase 2 — o excepthook
# ----------------------------------------------------------------------


def test_excepthook_grava_antes_de_avisar(tmp_path, escudo_isolado):
    """Se abrir a janela falhar, a evidência já tem que estar em disco."""
    destino = tmp_path / "logs" / "gestor.log"
    ordem: list[str] = []

    def modal_que_falha(_caminho):
        ordem.append("modal")
        raise RuntimeError("Qt já foi derrubado")

    resilience.instalar_escudo(destino, mostrar_modal=modal_que_falha)

    try:
        raise ZeroDivisionError("division by zero")
    except ZeroDivisionError:
        sys.excepthook(*sys.exc_info())  # o que o Qt faz por baixo

    assert ordem == ["modal"]
    conteudo = destino.read_text(encoding="utf-8")
    assert "Exceção não tratada" in conteudo
    assert "ZeroDivisionError: division by zero" in conteudo


def test_excepthook_recebe_o_caminho_do_log_para_o_ver_detalhes(tmp_path, escudo_isolado):
    """Sem o caminho, o suporte depende do pai do Vitor descrever o erro por telefone."""
    destino = tmp_path / "logs" / "gestor.log"
    recebidos = []
    resilience.instalar_escudo(destino, mostrar_modal=recebidos.append)

    try:
        raise ValueError("qualquer")
    except ValueError:
        sys.excepthook(*sys.exc_info())

    assert recebidos == [destino]


def test_ctrl_c_nao_vira_modal(tmp_path, escudo_isolado):
    """Saída pedida não é defeito: pouparia o log de quem roda pelo terminal."""
    avisos = []
    resilience.instalar_escudo(tmp_path / "logs" / "gestor.log", mostrar_modal=avisos.append)

    try:
        raise KeyboardInterrupt
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())

    assert avisos == []


def test_instalar_escudo_nao_empilha_desvios(tmp_path, escudo_isolado):
    """Duas chamadas não podem virar espelho de espelho (cada linha 2×, 4×...)."""
    destino = tmp_path / "logs" / "gestor.log"
    resilience.instalar_escudo(destino, mostrar_modal=lambda _c: None)
    primeiro = sys.stderr
    resilience.instalar_escudo(destino, mostrar_modal=lambda _c: None)

    assert sys.stderr is primeiro
    assert not isinstance(primeiro._original, resilience._DesvioDeStderr)
