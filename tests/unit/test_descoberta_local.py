"""A lista de impressoras locais que o cadastro oferece. §9.19.

`hardware/descoberta_local.py` pergunta ao Windows pelas filas de impressão e
pelas portas COM. Nada disto é consultado na hora de imprimir — é só a lista do
card "USB · Conexão local" —, e por isso a regra é devolver lista vazia em vez
de levantar: sem a lista, o campo continua aceitando o que for digitado.

A suíte roda sem spooler nem registro de verdade: `win32print` e `winreg` são
trocados por módulos falsos em `sys.modules`, que é de onde o `import` tardio
dentro das funções os busca.
"""

from __future__ import annotations

import sys
import types

import pytest

from gestor_comercial.hardware import descoberta_local
from gestor_comercial.hardware.descoberta_local import DestinoLocal, listar_destinos_locais
from gestor_comercial.services.impressao_service import ImpressaoService


def _win32print_falso(filas: list[dict] | Exception) -> types.ModuleType:
    modulo = types.ModuleType("win32print")
    modulo.PRINTER_ENUM_LOCAL = 2
    modulo.PRINTER_ENUM_CONNECTIONS = 4

    def enum_printers(flags, nome, nivel):
        assert flags == 6 and nivel == 2, "a busca tem que pedir locais E conexões, no nível 2"
        if isinstance(filas, Exception):
            raise filas
        return filas

    modulo.EnumPrinters = enum_printers
    return modulo


def _winreg_falso(valores: list[tuple[str, str, int]] | None) -> types.ModuleType:
    modulo = types.ModuleType("winreg")
    modulo.HKEY_LOCAL_MACHINE = object()

    class _Chave:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def abrir(raiz, caminho):
        if valores is None:
            raise FileNotFoundError(caminho)
        assert caminho == r"HARDWARE\DEVICEMAP\SERIALCOMM"
        return _Chave()

    def enumerar(chave, indice):
        if indice >= len(valores):
            raise OSError("Não há mais dados disponíveis")
        return valores[indice]

    modulo.OpenKey = abrir
    modulo.EnumValue = enumerar
    return modulo


@pytest.fixture
def sem_portas(monkeypatch):
    monkeypatch.setattr(descoberta_local.sys, "platform", "linux")


@pytest.fixture
def sem_filas(monkeypatch):
    monkeypatch.setitem(sys.modules, "win32print", _win32print_falso([]))


# ----------------------------------------------------------------------
# Filas do Windows
# ----------------------------------------------------------------------


def test_as_filas_reais_entram_e_as_virtuais_ficam_de_fora(monkeypatch, sem_portas):
    """PDF, OneNote, XPS e fax existem em toda máquina e nenhuma põe papel na
    bobina: oferecê-las ao lado da térmica é convite a escolher a errada."""
    monkeypatch.setitem(
        sys.modules,
        "win32print",
        _win32print_falso(
            [
                {"pPrinterName": "OneNote (Desktop)", "pPortName": "nul:"},
                {"pPrinterName": "Microsoft Print to PDF", "pPortName": "PORTPROMPT:"},
                {"pPrinterName": "Microsoft XPS Document Writer", "pPortName": "XPSPort:"},
                {"pPrinterName": "Fax", "pPortName": "SHRFAX:"},
                {"pPrinterName": "EPSON TM-T20", "pPortName": "USB001"},
                {"pPrinterName": "Bematech MP-4200", "pPortName": "COM4"},
            ]
        ),
    )

    assert listar_destinos_locais() == [
        DestinoLocal("Bematech MP-4200", "WINDOWS", "Impressora do Windows · COM4"),
        DestinoLocal("EPSON TM-T20", "WINDOWS", "Impressora do Windows · USB001"),
    ]


def test_a_mesma_fila_listada_duas_vezes_aparece_uma(monkeypatch, sem_portas):
    monkeypatch.setitem(
        sys.modules,
        "win32print",
        _win32print_falso(
            [
                {"pPrinterName": "EPSON TM-T20", "pPortName": "USB001"},
                {"pPrinterName": "epson tm-t20", "pPortName": "USB001"},
            ]
        ),
    )

    assert [destino.valor for destino in listar_destinos_locais()] == ["EPSON TM-T20"]


def test_spooler_parado_devolve_lista_vazia(monkeypatch, sem_portas):
    monkeypatch.setitem(sys.modules, "win32print", _win32print_falso(RuntimeError("spooler")))

    assert listar_destinos_locais() == []


def test_sem_pywin32_devolve_lista_vazia(monkeypatch, sem_portas):
    # `None` em `sys.modules` faz o `import` levantar ImportError.
    monkeypatch.setitem(sys.modules, "win32print", None)

    assert listar_destinos_locais() == []


# ----------------------------------------------------------------------
# Portas COM
# ----------------------------------------------------------------------


def test_as_portas_com_vem_do_registro_em_ordem_numerica(monkeypatch, sem_filas):
    """COM2 antes de COM10: a ordem alfabética poria a 10 logo depois da 1."""
    monkeypatch.setattr(descoberta_local.sys, "platform", "win32")
    monkeypatch.setitem(
        sys.modules,
        "winreg",
        _winreg_falso(
            [
                (r"\Device\Serial0", "COM10", 1),
                (r"\Device\BthModem0", "COM2", 1),
                (r"\Device\VCP0", "com3", 1),
            ]
        ),
    )

    assert listar_destinos_locais() == [
        DestinoLocal("COM2", "SERIAL", "Porta serial · Bluetooth"),
        DestinoLocal("COM3", "SERIAL", "Porta serial"),
        DestinoLocal("COM10", "SERIAL", "Porta serial"),
    ]


def test_maquina_sem_porta_com_devolve_lista_vazia(monkeypatch, sem_filas):
    monkeypatch.setattr(descoberta_local.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", _winreg_falso(None))

    assert listar_destinos_locais() == []


def test_fora_do_windows_nao_ha_porta_com(sem_filas, sem_portas):
    assert listar_destinos_locais() == []


def test_as_filas_vem_antes_das_portas(monkeypatch):
    """Fila primeiro: é o caminho comum de uma térmica USB no Windows."""
    monkeypatch.setitem(
        sys.modules,
        "win32print",
        _win32print_falso([{"pPrinterName": "EPSON TM-T20", "pPortName": "USB001"}]),
    )
    monkeypatch.setattr(descoberta_local.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", _winreg_falso([(r"\Device\Serial0", "COM1", 1)]))

    assert [destino.tipo for destino in listar_destinos_locais()] == ["WINDOWS", "SERIAL"]


# ----------------------------------------------------------------------
# A porta do service
# ----------------------------------------------------------------------


def test_a_porta_do_service_e_estatica_e_fica_fora_do_transacional():
    """A lista é pedida numa thread de trabalho. Um método comum passaria pelo
    `@transacional`, que num estouro faria `rollback()` na `Session` — e na
    thread errada. `staticmethod` fica fora do embrulho e não tem `self`."""
    assert isinstance(vars(ImpressaoService)["listar_destinos_locais"], staticmethod)


def test_a_porta_do_service_repassa_a_lista_do_hardware(monkeypatch):
    esperado = [DestinoLocal("COM3", "SERIAL", "Porta serial")]
    monkeypatch.setattr(
        "gestor_comercial.services.impressao_service._descobrir_destinos_locais", lambda: esperado
    )

    assert ImpressaoService.listar_destinos_locais() == esperado
