"""Bancada de paridade da impressão: gera todos os cupons em `.txt` e compara.

Irmã de `comparar_telas.py`, para o outro produto final do sistema. A suíte já
testa o roteamento e o formatador, mas nenhum teste responde à pergunta da
Fase 7: **o papel que sai da bobina hoje é byte a byte o mesmo de antes da
remasterização?** Aqui os seis documentos são impressos de verdade, pelo driver
de verdade, num tipo de conexão ARQUIVO — que é o tipo que grava o cupom em
texto (ver `_DriverArquivo`) — e o `diff` responde.

    # o "depois" — código da árvore de trabalho
    python tools/comparar_cupons.py C:\\tmp\\cupons-depois

    # o "antes" — a mesma bancada contra outro commit
    git worktree add C:\\tmp\\antes-src <commit>
    PYTHONPATH=C:\\tmp\\antes-src/src python tools/comparar_cupons.py C:\\tmp\\cupons-antes

    python tools/comparar_cupons.py --comparar C:\\tmp\\cupons-antes C:\\tmp\\cupons-depois

O cenário é o mesmo de `comparar_telas.py` (`_montar_servicos` + `_povoar`), e
de propósito: um seed próprio aqui seria uma segunda versão do mesmo dia de
operação, com liberdade para divergir daquele — exatamente o tipo de
duplicação que a Fase 6 passou o dia caçando.

**Hora do relógio é normalizada, não congelada.** Ao contrário das telas, o
cupom carrega a hora em que foi IMPRESSO (`datetime.now()` dentro do serviço,
que nenhum dado de banco alcança), então as duas execuções nunca bateriam byte
a byte. `_normalizar` troca cada hora por `HH:MM:SS` antes do `diff`; todo o
resto do cupom — layout, largura, roteamento, valores, acentuação — é
comparado como está.
"""

from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comparar_telas import _montar_servicos, _povoar  # noqa: E402

# Hora impressa no cupom: cabeçalho do driver ("===== Balcão — 06/09/2026
# 14:22:07") e as datas dentro do documento. A data em si fica (duas execuções
# do mesmo dia têm que bater); só o relógio vira marcador.
_HORAS = re.compile(r"\b\d{2}:\d{2}(:\d{2})?\b")


def imprimir(destino: Path) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    servicos = _montar_servicos()
    dados = _povoar(servicos, pasta_cupons=destino)
    impressao = servicos["impressao"]

    # Os seis documentos que o sistema sabe imprimir, na ordem em que aparecem
    # num turno: pedido para a produção, 2ª via do pedido, pré-conta,
    # recibo do cliente, fechamento da gaveta e o teste de impressora.
    comanda = dados["comanda"]
    impressao.imprimir_comanda(comanda.id)
    impressao.reimprimir_comanda(comanda.id)
    impressao.imprimir_pre_conta(comanda.id)
    impressao.imprimir_recibo(dados["comanda_paga"].id)
    impressao.imprimir_fechamento_caixa(dados["caixa_fechado"])
    for impressora_id in dados["impressoras"]:
        impressao.imprimir_teste(impressora_id)

    return sorted(destino.glob("*.txt"))


def _normalizar(caminho: Path) -> list[str]:
    return [_HORAS.sub("HH:MM:SS", linha) for linha in caminho.read_text(encoding="utf-8").splitlines()]


def comparar(antes: Path, depois: Path) -> int:
    diferentes = 0
    for arquivo in sorted(depois.glob("*.txt")):
        par = antes / arquivo.name
        if not par.exists():
            print(f"{arquivo.name:16s} SÓ EXISTE NO DEPOIS")
            diferentes += 1
            continue
        linhas_antes, linhas_depois = _normalizar(par), _normalizar(arquivo)
        if linhas_antes == linhas_depois:
            print(f"{arquivo.name:16s} idêntico    {len(linhas_depois)} linhas")
            continue
        diferentes += 1
        print(f"{arquivo.name:16s} >>> DIFERE")
        for linha in difflib.unified_diff(
            linhas_antes, linhas_depois, fromfile=str(par), tofile=str(arquivo), lineterm=""
        ):
            print(f"    {linha}")
    return diferentes


def main() -> int:
    argumentos = sys.argv[1:]
    if argumentos[:1] == ["--comparar"]:
        return 1 if comparar(Path(argumentos[1]), Path(argumentos[2])) else 0
    if not argumentos:
        print(__doc__)
        return 2
    for caminho in imprimir(Path(argumentos[0])):
        print(f"{caminho}  ({len(caminho.read_text(encoding='utf-8').splitlines())} linhas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
