"""O que esta máquina enxerga de impressora local, para o cadastro escolher (§9.19).

O cartão "Nova impressora" tem um card **USB · Conexão local**, e na máquina do
food truck uma térmica USB quase nunca é aberta pelo `pyusb`: ela é instalada
no Windows com o driver do fabricante (vira uma **fila de impressão**) ou
aparece como **porta COM** (cabo serial, adaptador USB-serial ou Bluetooth).
Este módulo lista essas duas coisas, para o gerente escolher numa lista em vez
de digitar de cabeça o nome exato de "Dispositivos e Impressoras".

## O que este módulo NÃO faz

Não imprime, não abre porta e não é consultado na hora de imprimir. É só a
lista que o cadastro mostra. O despacho continua inteiro em
`impressora_escpos.py`, que não foi tocado: uma impressora escolhida aqui é
gravada como WINDOWS (`nome_fila`) ou SERIAL (`porta_serial`), exatamente os
campos que já existiam, e sai no papel pelo mesmo caminho de sempre. Não há
"detectar automaticamente" na impressão — foi a decisão do Vitor (§9.19).

## Por que pode demorar, e quem espera

`EnumPrinters` com `PRINTER_ENUM_CONNECTIONS` pergunta ao spooler pelas
impressoras de rede conectadas, e uma impressora compartilhada que saiu da rede
pode segurar a resposta por segundos. Por isso quem chama isto é uma thread de
trabalho aberta pelo cartão (`impressora_dialog._BuscaDeDestinos`), nunca a
thread da UI. Esta função não sabe de thread nenhuma: é síncrona, só lê, e
devolve lista vazia em vez de levantar.

## As filas que ficam de fora

Filas virtuais — "Microsoft Print to PDF", "OneNote", fax, XPS — aparecem em
toda máquina Windows e nenhuma delas põe papel na bobina: um cupom ESC/POS
mandado para lá vira um PDF ilegível ou some. Oferecê-las ao lado da térmica é
convite para escolher a errada, que é o mesmo motivo de a tela antiga esconder
os campos do tipo que não foi escolhido. O critério é a **porta** da fila, e não
o nome (que o usuário pode renomear): as virtuais usam portas que não são
hardware (`nul:`, `PORTPROMPT:`, `XPSPort:`...). Quem precisar de uma delas
ainda pode digitar o nome no campo.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass

TIPO_FILA_WINDOWS = "WINDOWS"
TIPO_PORTA_SERIAL = "SERIAL"

# Portas de fila que não levam a papel nenhum. Comparadas em maiúsculas.
PORTAS_SEM_PAPEL = frozenset({"NUL:", "PORTPROMPT:", "XPSPORT:", "SHRFAX:", "FILE:"})

# A chave do registro onde o Windows publica as portas COM que existem agora.
# É o mesmo lugar que o `serial.tools.list_ports` lê — e ler direto evita pedir
# o `pyserial`, que não está instalado na máquina do food truck.
_CHAVE_PORTAS_COM = r"HARDWARE\DEVICEMAP\SERIALCOMM"

_NUMERO_DA_PORTA = re.compile(r"(\d+)$")


@dataclass(frozen=True, slots=True)
class DestinoLocal:
    """Uma opção da lista: o valor que vai para o banco e o que o gerente lê.

    `tipo` é o NOME do tipo de conexão (`"WINDOWS"` ou `"SERIAL"`), e não o
    enum do `domain/`: esta camada não importa `domain/` em runtime, pela mesma
    regra de `impressora_escpos.py`.
    """

    valor: str
    tipo: str
    detalhe: str


def listar_destinos_locais() -> list[DestinoLocal]:
    """As filas de impressão reais e as portas COM desta máquina, nessa ordem.

    Fila primeiro porque é o caminho comum de uma térmica USB no Windows. Fora
    do Windows (a suíte roda em qualquer lugar) as duas listas saem vazias.
    """
    return _filas_do_windows() + _portas_com()


def _filas_do_windows() -> list[DestinoLocal]:
    try:
        # Import tardio pelo mesmo motivo do `python-escpos` em
        # `impressora_escpos.py`: o boot do app não paga por ele, e a suíte roda
        # em máquina sem pywin32.
        import win32print
    except ImportError:
        return []

    try:
        brutas = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS, None, 2
        )
    except Exception:
        # `except Exception` largo de propósito: o spooler parado levanta
        # `pywintypes.error`, e o contrato aqui é devolver a lista vazia — o
        # campo continua aceitando o nome digitado.
        return []

    destinos: dict[str, DestinoLocal] = {}
    for bruta in brutas:
        nome = str(bruta.get("pPrinterName") or "").strip()
        porta = str(bruta.get("pPortName") or "").strip()
        if not nome or porta.upper() in PORTAS_SEM_PAPEL:
            continue
        detalhe = f"Impressora do Windows · {porta}" if porta else "Impressora do Windows"
        # Por nome: a mesma fila pode vir duas vezes (local e conexão).
        destinos.setdefault(nome.casefold(), DestinoLocal(nome, TIPO_FILA_WINDOWS, detalhe))
    return sorted(destinos.values(), key=lambda destino: destino.valor.casefold())


def _portas_com() -> list[DestinoLocal]:
    if sys.platform != "win32":
        return []
    import winreg

    portas: dict[str, DestinoLocal] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CHAVE_PORTAS_COM) as chave:
            indice = 0
            while True:
                try:
                    dispositivo, porta, _tipo = winreg.EnumValue(chave, indice)
                except OSError:
                    break
                indice += 1
                porta = str(porta).strip().upper()
                if porta:
                    portas.setdefault(porta, DestinoLocal(porta, TIPO_PORTA_SERIAL, _detalhe(dispositivo)))
    except OSError:
        # A chave nem existe numa máquina sem porta COM nenhuma.
        return []
    return sorted(portas.values(), key=_ordem_da_porta)


def _detalhe(dispositivo: object) -> str:
    """"Porta serial · Bluetooth" para as portas SPP, que é como uma térmica
    Bluetooth aparece — e é a pista que separa a impressora do celular pareado."""
    if "bth" in str(dispositivo).casefold():
        return "Porta serial · Bluetooth"
    return "Porta serial"


def _ordem_da_porta(destino: DestinoLocal) -> tuple[int, str]:
    """COM2 antes de COM10: a ordem alfabética poria a 10 logo depois da 1."""
    numero = _NUMERO_DA_PORTA.search(destino.valor)
    return (int(numero.group(1)) if numero else 0, destino.valor)
