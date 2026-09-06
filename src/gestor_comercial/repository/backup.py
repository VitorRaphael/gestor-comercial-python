"""Cópia de segurança do banco e consolidação do WAL.

Existe por causa da decisão de ligar `journal_mode=WAL` (§8, 2026-09-06). O WAL
resolve a concorrência entre leitura e escrita — necessária para o App Mobile do
Atendente — mas muda uma coisa que o dono do food truck não tem como adivinhar:
**o banco deixa de ser um arquivo só**. As transações recentes ficam num
`gestor_comercial.db-wal` ao lado, e copiar apenas o `.db` para um pendrive com
o programa aberto leva um banco sem as últimas vendas.

A resposta deste módulo é não depender de cópia de arquivo nenhuma:

- `fazer_backup()` usa `VACUUM INTO`, comando nativo do SQLite que **grava um
  banco novo, completo e desfragmentado** num caminho de destino. O SQLite lê o
  estado consistente (arquivo principal + WAL) e escreve um único `.db` fechado.
  Não existe `-wal` do backup para esquecer de copiar junto.
- `consolidar_wal()` roda `wal_checkpoint(TRUNCATE)`, que empurra tudo o que
  está no WAL para dentro do `.db` e zera o arquivo auxiliar. É o que mantém o
  arquivo principal sempre em dia no disco — chamado no fechamento do caixa e
  no encerramento do app.

Sem dependência nova: os dois são comandos do próprio SQLite.

Toda função aqui recebe o `engine` (ou a `Session`) de quem chamou, em vez de
alcançar o engine global do módulo `base`. É o que faz a suíte de testes, que
roda em banco de memória, não escrever backup nenhum na pasta de dados real.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# Quantos backups automáticos guardar. O disco da máquina do food truck é
# pequeno e um backup por fechamento de turno se acumula rápido; ~2 meses de
# operação é histórico de sobra para voltar atrás de um erro, e o pendrive
# continua sendo o arquivo de longo prazo.
BACKUPS_MANTIDOS = 60

PREFIXO_BACKUP = "gestor_backup_"


def _engine_de(origem: Engine | Session | None) -> Engine:
    if isinstance(origem, Session):
        return origem.get_bind()
    if origem is not None:
        return origem
    from gestor_comercial.repository.base import engine as engine_padrao

    return engine_padrao


def caminho_do_banco(origem: Engine | Session | None = None) -> Path | None:
    """O arquivo `.db` por trás do engine, ou `None` se for banco de memória.

    Banco de memória não tem arquivo para versionar nem WAL para consolidar —
    é o caso da suíte de testes, e é o que faz backup e checkpoint virarem
    no-op ali em vez de escreverem na pasta de dados de verdade.
    """
    caminho = _engine_de(origem).url.database
    if not caminho or caminho == ":memory:":
        return None
    return Path(caminho)


def pasta_backups(origem: Engine | Session | None = None) -> Path | None:
    """Pasta de backups, ao lado do banco (mesmo diretório de dados).

    Mesma escolha de `imagem_service.pasta_thumbnails()`: derivada do caminho do
    banco em runtime, nunca gravada em lugar nenhum, para a pasta de dados
    inteira poder ser movida sem quebrar nada.
    """
    banco = caminho_do_banco(origem)
    if banco is None:
        return None
    pasta = banco.parent / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def consolidar_wal(origem: Engine | Session | None = None) -> bool:
    """Descarrega o WAL dentro do `.db` e zera o arquivo auxiliar.

    Chamado no fechamento do caixa e no encerramento do app, para o arquivo
    principal estar sempre atualizado no disco — inclusive para quem for olhar
    o banco por fora, com o programa fechado.

    Nunca derruba a operação: um checkpoint recusado (outra conexão lendo,
    banco em memória na suíte) significa "fica para a próxima", não "a venda
    falhou" — devolve `False` e segue. Quem garante a durabilidade da venda é o
    `commit`, não isto.
    """
    if caminho_do_banco(origem) is None:
        return False
    try:
        with _engine_de(origem).connect() as conexao:
            conexao.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        return True
    except Exception:
        return False


def fazer_backup(
    destino: Path | str | None = None, origem: Engine | Session | None = None
) -> Path | None:
    """Grava uma cópia íntegra do banco e devolve o caminho do arquivo criado.

    `VACUUM INTO` produz um `.db` único, limpo e já consolidado: o SQLite monta
    o banco de destino a partir do estado consistente atual (arquivo principal +
    o que estiver no WAL), então **não há `-wal` para copiar junto**. É por isso
    que é este o comando usado, e não uma cópia de arquivo.

    `destino` sem valor cai em
    `<dir_dados>/backups/gestor_backup_AAAAMMDD_HHMMSS.db`. O SQLite recusa
    gravar por cima de um arquivo existente — o que é proteção, não obstáculo:
    backup nunca sobrescreve backup.

    Devolve `None` sem fazer nada quando o banco é de memória (a suíte).
    """
    if caminho_do_banco(origem) is None:
        return None

    if destino is None:
        pasta = pasta_backups(origem)
        destino = pasta / f"{PREFIXO_BACKUP}{datetime.now():%Y%m%d_%H%M%S}.db"
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    # AUTOCOMMIT porque `VACUUM INTO` não roda dentro de transação, e a conexão
    # do SQLAlchemy abre uma por padrão. Aspas simples duplicadas escapam o
    # caminho no literal SQL (um `'` no nome da pasta quebraria o comando).
    caminho_sql = str(destino).replace("'", "''")
    with _engine_de(origem).connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conexao:
        conexao.execute(text(f"VACUUM INTO '{caminho_sql}'"))
    return destino


def limpar_backups_antigos(
    manter: int = BACKUPS_MANTIDOS, origem: Engine | Session | None = None
) -> list[Path]:
    """Apaga os backups automáticos mais antigos, devolvendo o que foi apagado.

    Só mexe em arquivos com o prefixo que `fazer_backup` gera — um `.db` que o
    Vitor tenha colocado ali à mão com outro nome fica onde está. O nome carrega
    a data em formato ordenável, então ordem alfabética já é ordem cronológica.
    """
    pasta = pasta_backups(origem)
    if pasta is None:
        return []
    automaticos = sorted(pasta.glob(f"{PREFIXO_BACKUP}*.db"))
    excedentes = automaticos[:-manter] if manter > 0 else automaticos
    apagados = []
    for arquivo in excedentes:
        try:
            arquivo.unlink()
        except OSError:
            # Arquivo em uso (antivírus, pendrive removido no meio): não é
            # motivo para o fechamento de caixa falhar.
            continue
        apagados.append(arquivo)
    return apagados
