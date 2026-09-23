"""Fronteira única entre o sistema e a impressora térmica (§3.12 e §6 da arquitetura).

Este é o único arquivo do projeto que conhece o `python-escpos`. Todo o resto
do sistema fala em `BlocoTexto` (um pedaço de texto com negrito/centralizado/
dobro) e recebe um `DriverImpressora` — nunca um objeto da biblioteca. Trocar
de biblioteca, de protocolo ou de modelo de impressora no futuro afeta só este
arquivo, que é exatamente o que §6 promete sobre a pasta `hardware/`.

A camada não importa `services/` nem `ui/`: ela não sabe o que é comanda, nem
recibo, nem caixa. Recebe uma lista de blocos já formatados e manda pro papel.

São 5 tipos de conexão. Os 4 primeiros (USB, SERIAL, REDE, WINDOWS) são
hardware de verdade; o 5º, ARQUIVO, grava o cupom num `.txt` legível e existe
para o Vitor testar o fluxo inteiro de venda antes de a impressora física
chegar — por isso ele é o padrão de quem cadastra uma impressora sem informar
nada.
"""

from __future__ import annotations

import contextlib
import json
import textwrap
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Protocol, runtime_checkable

from gestor_comercial.core.caminhos import pasta_de_dados

if TYPE_CHECKING:  # pragma: no cover - só para o type checker
    # Import só de tipo: em runtime `hardware/` não depende de `domain/`, o que
    # mantém esta camada testável com um objeto qualquer que tenha os campos
    # certos (é assim que os testes injetam impressora falsa sem tocar o banco).
    from gestor_comercial.domain.impressora import Impressora

# Largura da bobina quando a impressora cadastrada não informa: 48 colunas é a
# bobina de 80mm, a mais comum em food truck. 32 é a de 58mm.
COLUNAS_PADRAO = 48

# Quantas colunas cada bobina imprime na fonte NORMAL do ESC/POS (a fonte A, 12
# pontos por caractere): 384 pontos úteis na de 58mm, 576 na de 80mm. Passou
# disso, o driver liga a fonte condensada (a fonte B, 9 pontos), que é o que
# faz as 64 colunas da bobina de 80mm caberem numa linha (§9.22). As 80 colunas
# não cabem nem na condensada de uma térmica comum, e ficaram no seletor por
# decisão do Vitor: quem responde se a impressora dele imprime é a régua do
# cupom de teste.
COLUNAS_NA_FONTE_NORMAL = {58: 32, 80: 48}
BOBINA_PADRAO_MM = 80

# A escala das linhas de destaque (§9.30). O `GS !` aceita de 1 a 8; o cadastro
# só oferece 2, 3 e 4, e o que chegar fora disso (objeto de teste, valor mexido à
# mão) cai no dobro, que é o tamanho que a mesa sempre teve.
ESCALA_PADRAO = 2
ESCALA_MAXIMA = 8

# Pasta onde caem os cupons do modo ARQUIVO quando ninguém informa caminho.
# Mesma raiz do banco, vinda de `core/` e não do repository: `hardware/` não deve
# depender da camada de dados. No `.exe`, é a pasta de dados própria da versão —
# nunca a `~/.gestor_comercial/` do programa anterior.
PASTA_CUPONS_PADRAO = pasta_de_dados() / "cupons"

TIPOS_SUPORTADOS = ("USB", "SERIAL", "REDE", "WINDOWS", "ARQUIVO")


@dataclass(frozen=True)
class BlocoTexto:
    """Uma linha (ou parágrafo) do cupom com os únicos estilos que uma térmica tem.

    `ampliado` é a linha de DESTAQUE (título, mesa, TOTAL): sai na escala da
    impressora (2x, 3x ou 4x, `Impressora.escala_fonte`, §9.30), e não numa
    escala do documento — o mesmo recibo sai em 3x numa impressora e em 2x em
    outra, e a fila de contingência reimprime com o que a impressora é HOJE.
    Ela consome `escala` vezes as colunas, então quem monta o documento conta
    com a largura dividida pela escala nesses blocos.

    `dobro` é o destaque de antes da escala: 2x fixo. Continua existindo para os
    cupons que já estão guardados na fila de contingência voltarem iguais.

    `escala` é a exceção de `ampliado`: uma escala FIXA, só deste bloco,
    ignorando a da impressora. Existe para o cupom de diagnóstico de fonte
    (§9.31), que precisa mostrar 1x, 2x, 3x e 4x lado a lado no mesmo papel —
    o único caso em que o documento, e não o cadastro, decide o tamanho. Fora
    dele, continua `None`: quem manda na escala é a impressora.
    """

    texto: str
    negrito: bool = False
    centralizado: bool = False
    dobro: bool = False
    ampliado: bool = False
    escala: int | None = None


Documento = list[BlocoTexto]


def documento_para_json(documento: Documento) -> str:
    """Serializa o documento para guardar na fila de contingência (Fase 3).

    JSON e não pickle: o arquivo do banco vai para pendrive e precisa ser
    legível e inofensivo — pickle executaria código na volta. As chaves são os
    nomes dos campos de `BlocoTexto`, então um cupom guardado hoje continua
    legível depois de o resto do sistema mudar.
    """
    return json.dumps(
        [
            {
                "texto": bloco.texto,
                "negrito": bloco.negrito,
                "centralizado": bloco.centralizado,
                "dobro": bloco.dobro,
                "ampliado": bloco.ampliado,
                "escala": bloco.escala,
            }
            for bloco in documento
        ],
        ensure_ascii=False,
    )


def _escala_do_bloco_json(bruto: object) -> int | None:
    """A escala fixa de um bloco vinda do JSON da fila. Fora da faixa, `None`."""
    if isinstance(bruto, int) and not isinstance(bruto, bool) and 1 <= bruto <= ESCALA_MAXIMA:
        return bruto
    return None


def documento_de_json(bruto: str) -> Documento:
    """A volta de `documento_para_json`. Documento ilegível vira lista vazia.

    Não levanta de propósito: um registro corrompido na fila não pode impedir os
    outros cupons de saírem, e muito menos derrubar a tela que lista a fila.
    Campo faltando cai no default do `BlocoTexto`.
    """
    try:
        crus = json.loads(bruto)
    except (ValueError, TypeError):
        return []
    if not isinstance(crus, list):
        return []
    blocos: Documento = []
    for cru in crus:
        if not isinstance(cru, dict):
            continue
        blocos.append(
            BlocoTexto(
                texto=str(cru.get("texto", "")),
                negrito=bool(cru.get("negrito", False)),
                centralizado=bool(cru.get("centralizado", False)),
                dobro=bool(cru.get("dobro", False)),
                ampliado=bool(cru.get("ampliado", False)),
                # `None` (e não um int) quando o cupom foi guardado antes
                # deste campo existir: a fila antiga reimprime na escala da
                # impressora, como sempre reimprimiu.
                escala=_escala_do_bloco_json(cru.get("escala")),
            )
        )
    return blocos


@dataclass(frozen=True)
class ParametrosImpressora:
    """Retrato dos dados de conexão de uma impressora, sem vínculo com o banco.

    Existe para a impressão poder sair da thread da UI (Fase 3 de `Mitigação de
    Falhas.md`). O objeto `Impressora` do `domain/` é uma entidade do
    SQLAlchemy: ler um atributo dele em outra thread mexe na `Session`, que não
    é thread-safe — exatamente a corrupção silenciosa que a decisão da Fase 4 da
    remasterização queria evitar.

    Este retrato é tirado **na thread da UI**, é imutável e só tem str/int/None.
    É ele que atravessa para a thread de trabalho.

    Nada precisou mudar em `abrir_driver` para aceitá-lo: esta camada sempre leu
    a impressora por `getattr`, e a docstring do módulo já dizia que isso
    "permite testar com um objeto qualquer que tenha os campos certos". O
    desacoplamento estava pronto antes de existir motivo para usá-lo.
    """

    nome: str
    tipo_conexao: str
    colunas: int
    vendor_id: str | None = None
    product_id: str | None = None
    porta_serial: str | None = None
    baudrate: int | None = None
    host: str | None = None
    porta_rede: int | None = None
    nome_fila: str | None = None
    caminho_arquivo: str | None = None
    bobina_mm: int = BOBINA_PADRAO_MM
    escala_fonte: int = ESCALA_PADRAO

    @classmethod
    def de(cls, impressora: "Impressora") -> "ParametrosImpressora":
        bruto = getattr(impressora, "tipo_conexao", None)
        return cls(
            nome=_nome_da(impressora),
            tipo_conexao=str(getattr(bruto, "value", bruto) or ""),
            colunas=_colunas_de(impressora),
            bobina_mm=_bobina_de(impressora),
            escala_fonte=escala_de(impressora),
            vendor_id=getattr(impressora, "vendor_id", None),
            product_id=getattr(impressora, "product_id", None),
            porta_serial=getattr(impressora, "porta_serial", None),
            baudrate=getattr(impressora, "baudrate", None),
            host=getattr(impressora, "host", None),
            porta_rede=getattr(impressora, "porta_rede", None),
            nome_fila=getattr(impressora, "nome_fila", None),
            caminho_arquivo=getattr(impressora, "caminho_arquivo", None),
        )


class ErroDeImpressao(Exception):
    """Falha local do periférico: sem papel, cabo solto, IP errado, driver faltando.

    Nunca sobe até a UI. O `ImpressaoService` captura esta exceção e a
    transforma num resultado com `sucesso=False`, porque o RNF inegociável
    de §2 é que impressora quebrada não derruba a venda — o cliente paga e
    vai embora mesmo que a cozinha tenha que ouvir o pedido gritado.

    A mensagem é escrita em português e no imperativo, para o operador do food
    truck saber o que fazer sem chamar ninguém.
    """


@runtime_checkable
class DriverImpressora(Protocol):
    """O que o resto do sistema enxerga de uma impressora: um jeito de imprimir."""

    def imprimir(self, documento: Documento) -> None:
        """Renderiza os blocos com os estilos pedidos e corta o papel no fim."""
        ...


def abrir_driver(
    impressora: "Impressora", timeout_s: float = 3.0
) -> AbstractContextManager[DriverImpressora]:
    """Abre a conexão com `impressora` e devolve o driver certo para o tipo dela.

    Uso:

        with abrir_driver(impressora) as driver:
            driver.imprimir(documento)

    A conexão fecha ao sair do bloco, mesmo se `imprimir` levantar. Qualquer
    problema (parâmetro faltando, biblioteca ausente, cabo solto, host que não
    responde) vira `ErroDeImpressao` com mensagem em português.

    `timeout_s` é curto de propósito: a impressão roda na thread da UI (decisão
    de arquitetura da Fase 4) e o operador não pode ficar com a tela travada
    esperando um IP que não existe.
    """
    return _sessao_de_impressao(impressora, timeout_s)


# ----------------------------------------------------------------------
# Implementação
# ----------------------------------------------------------------------


@contextlib.contextmanager
def _sessao_de_impressao(
    impressora: "Impressora", timeout_s: float
) -> Iterator[DriverImpressora]:
    tipo = _tipo_de_conexao(impressora)
    nome = _nome_da(impressora)
    colunas = _colunas_de(impressora)
    escala = escala_de(impressora)

    if tipo == "ARQUIVO":
        # Não há conexão a fechar: cada impressão abre e fecha o arquivo.
        yield _DriverArquivo(_caminho_do_arquivo(impressora), colunas, nome, escala=escala)
        return

    conexao = _abrir_conexao_escpos(impressora, tipo, nome, timeout_s)
    try:
        yield _DriverEscpos(
            conexao,
            nome,
            escala=escala,
            condensada=usa_fonte_condensada(colunas, _bobina_de(impressora)),
        )
    except BaseException:
        # Já existe um erro em curso: fechar não pode mascarar o erro real da
        # impressão. Se a impressora caiu no meio do cupom, o close também vai
        # falhar, e o que interessa ao operador é a mensagem da falha original.
        with contextlib.suppress(Exception):
            conexao.close()
        raise
    else:
        # Caminho feliz: aqui o close() PRECISA poder falhar em voz alta. No
        # driver Win32Raw é ele quem faz EndPagePrinter/EndDocPrinter — ou seja,
        # é o close que efetiva o job na fila do Windows; o write anterior só
        # encheu um documento ainda aberto. Engolir esse erro faria o service
        # devolver sucesso=True, marcar `impresso_em` e esconder para sempre um
        # pedido que nunca saiu no papel.
        try:
            conexao.close()
        except Exception as erro:
            raise ErroDeImpressao(
                f"O cupom não chegou a ser finalizado na impressora '{nome}': {erro}. "
                "Verifique se ela continua ligada e se a fila de impressão do Windows "
                "não foi pausada ou cancelada, e imprima a 2ª via."
            ) from erro


class _DriverEscpos:
    """Adapta os `BlocoTexto` para os comandos ESC/POS da biblioteca.

    `escala` e `condensada` são do cadastro da impressora, e não do documento
    (§9.22, §9.30): o mesmo recibo sai com o TOTAL em 3x numa impressora e em
    2x em outra, e a fila de contingência reimprime com o que a impressora é HOJE.
    """

    def __init__(
        self, conexao: Any, nome: str, *, escala: int = ESCALA_PADRAO, condensada: bool = False
    ) -> None:
        self._conexao = conexao
        self._nome = nome
        self._escala = escala
        self._condensada = condensada

    def _tamanho(self, bloco: BlocoTexto) -> int:
        # A escala fixa do bloco vem na frente de tudo: é o cupom de
        # diagnóstico dizendo "esta linha sai em 3x", independentemente do
        # que a impressora tenha cadastrado — é justamente o que ele prova.
        if bloco.escala is not None:
            return max(1, min(int(bloco.escala), ESCALA_MAXIMA))
        if bloco.ampliado:
            return self._escala
        return 2 if bloco.dobro else 1

    def imprimir(self, documento: Documento) -> None:
        try:
            # ESC @ antes de qualquer coisa: se um cupom anterior morreu no meio
            # (papel acabou, cabo caiu), a impressora ficou com o último estilo
            # ligado na memória dela. Sem o reset, o cupom novo herdaria isso.
            self._conexao.hw("INIT")
            for bloco in documento:
                tamanho = self._tamanho(bloco)
                # O tamanho vai EM TODO BLOCO, e sempre pelo `GS !` (o
                # `custom_size`), inclusive o 1x do texto comum. Não é enfeite:
                # o `normal_textsize` do python-escpos só manda `ESC ! 0`, que
                # não zera com segurança o tamanho que um `GS !` ligou — depois
                # de um TOTAL em 3x, a linha seguinte (e o cupom seguinte)
                # sairia ampliada e cortada pela largura da bobina. Com um
                # comando só para o tamanho, cada linha diz o dela.
                #
                # Negrito e fonte também vão em todo bloco: o `bold=False` de uma
                # linha comum manda `ESC E 0`, e o `GS !` não mexe em nenhum dos
                # dois, então a condensada escolhida vale para o cupom inteiro.
                self._conexao.set(
                    align="center" if bloco.centralizado else "left",
                    bold=bloco.negrito,
                    # `None` quando não é condensada: nada é enviado, e o cupom
                    # de quem cabe na fonte normal não ganha bytes à toa.
                    font="b" if self._condensada else None,
                    custom_size=True,
                    width=tamanho,
                    height=tamanho,
                )
                self._conexao.textln(bloco.texto)
            # Volta ao estado neutro antes de cortar: a impressora guarda o
            # último estilo entre trabalhos, e sem isso o próximo cupom sairia
            # inteiro em negrito ampliado.
            self._conexao.set(align="left", bold=False, custom_size=True, width=1, height=1)
            self._conexao.cut()
        except Exception as erro:
            # `except Exception` largo é proposital e não é preguiça: o
            # python-escpos deixa vazar exceção de pyusb, pyserial, socket e
            # OSError sem um ancestral comum, e o contrato desta camada é que
            # nada além de ErroDeImpressao atravesse a fronteira.
            raise ErroDeImpressao(
                f"Falha ao imprimir na impressora '{self._nome}': {erro}. "
                "Verifique se ela está ligada, com papel e conectada."
            ) from erro


class _DriverArquivo:
    """Grava o cupom num `.txt` legível, simulando o que sairia no papel.

    DIVERGÊNCIA do python-escpos: existe um `escpos.printer.File`, mas ele
    grava os bytes ESC/POS crus — abrir o arquivo no Bloco de Notas mostra
    `\\x1b@\\x1ba\\x01` e não um cupom. Como o propósito deste tipo de conexão
    é justamente conferir o cupom sem impressora física, ele escreve texto
    puro e simula os estilos: negrito vira MAIÚSCULA, `dobro` vira letra
    espaçada (ocupando o dobro das colunas, como no papel) e `centralizado`
    centraliza dentro da largura da bobina.

    A quebra de linha na largura também é simulada aqui, e não é duplicação do
    `formatador_cupom`: quebrar o que não coube é comportamento da impressora,
    não do documento — se o serviço mandar uma linha larga demais, o arquivo
    tem que mostrar o mesmo estrago que o papel mostraria.

    A linha `ampliado` (§9.30) é simulada como o `dobro`, na escala da
    impressora: cabem `colunas // escala` caracteres, cada um seguido de
    `escala - 1` espaços. A altura não tem como sair num `.txt`.
    """

    def __init__(
        self, caminho: Path, colunas: int, nome: str, *, escala: int = ESCALA_PADRAO
    ) -> None:
        self._caminho = caminho
        self._colunas = colunas
        self._nome = nome
        self._escala = escala

    def imprimir(self, documento: Documento) -> None:
        linhas: list[str] = [
            f"===== {self._nome} — {datetime.now():%d/%m/%Y %H:%M:%S} ".ljust(
                self._colunas, "="
            )
        ]
        for bloco in documento:
            linhas.extend(self._renderizar(bloco))
        # Avanço de papel + marca de corte: deixa claro onde termina um cupom
        # e começa o próximo quando vários se acumulam no mesmo arquivo.
        linhas.extend(["", "", " CORTE ".center(self._colunas, "-"), ""])

        try:
            self._caminho.parent.mkdir(parents=True, exist_ok=True)
            # Modo append: o arquivo vira o histórico do turno de teste, e não
            # some quando o cupom seguinte é impresso.
            with self._caminho.open("a", encoding="utf-8", newline="\n") as arquivo:
                arquivo.write("\n".join(linhas) + "\n")
        except OSError as erro:
            raise ErroDeImpressao(
                f"Não foi possível gravar o cupom em '{self._caminho}': {erro}. "
                "Confira o caminho cadastrado para a impressora "
                f"'{self._nome}' e a permissão da pasta."
            ) from erro

    def _renderizar(self, bloco: BlocoTexto) -> list[str]:
        texto = bloco.texto.upper() if bloco.negrito else bloco.texto
        # Bloco ampliado ocupa `tamanho` colunas por caractere: cabe a fração.
        if bloco.escala is not None:
            tamanho = max(1, min(int(bloco.escala), ESCALA_MAXIMA))
        else:
            tamanho = self._escala if bloco.ampliado else 2 if bloco.dobro else 1
        largura_util = max(1, self._colunas // tamanho)

        if not texto.strip():
            return [""]

        renderizadas = []
        for linha in textwrap.wrap(texto, width=largura_util) or [""]:
            if tamanho > 1:
                # Letra espaçada aproxima visualmente a largura ampliada; o
                # resultado tem k·n-(k-1) caracteres para n impressos em k x.
                linha = (" " * (tamanho - 1)).join(linha)
            renderizadas.append(linha.center(self._colunas) if bloco.centralizado else linha)
        return renderizadas


def _abrir_conexao_escpos(impressora: "Impressora", tipo: str, nome: str, timeout_s: float):
    """Constrói e abre o objeto do python-escpos correspondente ao tipo."""
    # Import tardio, dentro da função, por dois motivos: o boot do app não pode
    # pagar o custo de carregar o python-escpos (RNF de otimização, §2), e a
    # suíte de testes roda em máquina sem nenhuma impressora nem pyusb.
    from escpos.printer import Network, Serial, Usb, Win32Raw

    # Em todos os ramos os parâmetros do cadastro são lidos ANTES de checar a
    # biblioteca: assim um cadastro incompleto dá a mesma mensagem na máquina
    # do Vitor e na do food truck, independentemente de qual extra do
    # python-escpos está instalado ali. É também o erro que o operador
    # consegue resolver sozinho, pela tela de Impressoras.
    if tipo == "USB":
        vendor = _id_usb(impressora, "vendor_id", "Vendor ID", nome)
        produto = _id_usb(impressora, "product_id", "Product ID", nome)
        _exigir_biblioteca(Usb, nome, "pyusb", "USB")
        # pyusb conta timeout em milissegundos, não em segundos.
        conexao = Usb(idVendor=vendor, idProduct=produto, timeout=int(timeout_s * 1000))
    elif tipo == "SERIAL":
        porta = _texto_obrigatorio(
            impressora,
            "porta_serial",
            f"A impressora '{nome}' está como SERIAL mas não tem porta cadastrada. "
            "Informe a porta (ex: COM3) no cadastro de Impressoras.",
        )
        baudrate = _inteiro_ou(impressora, "baudrate", 9600)
        _exigir_biblioteca(Serial, nome, "pyserial", "serial")
        # `dsrdtr=False` desliga o controle de fluxo por hardware, que o escpos
        # liga por padrão: com ele ativo, uma impressora desligada no botão (ou
        # um pino de handshake solto) faz o write bloquear esperando um DSR que
        # nunca vem. O limite de escrita é imposto logo depois do open().
        conexao = Serial(devfile=porta, baudrate=baudrate, timeout=timeout_s, dsrdtr=False)
    elif tipo == "REDE":
        host = _texto_obrigatorio(
            impressora,
            "host",
            f"A impressora '{nome}' está como REDE mas não tem endereço cadastrado. "
            "Informe o IP dela (ex: 192.168.0.100) no cadastro de Impressoras.",
        )
        # Network não precisa de biblioteca extra: é socket da stdlib.
        conexao = Network(
            host=host, port=_inteiro_ou(impressora, "porta_rede", 9100), timeout=timeout_s
        )
    elif tipo == "WINDOWS":
        fila = _texto_obrigatorio(
            impressora,
            "nome_fila",
            f"A impressora '{nome}' está como WINDOWS mas não tem fila cadastrada. "
            "Informe o nome exato que aparece em Dispositivos e Impressoras.",
        )
        _exigir_biblioteca(Win32Raw, nome, "pywin32", "pelo Windows")
        # Win32Raw não aceita timeout: quem controla o tempo é a fila de
        # impressão do próprio Windows, que já devolve na hora e imprime depois.
        conexao = Win32Raw(printer_name=fila)
    else:  # pragma: no cover - _tipo_de_conexao já barrou o que não é suportado
        raise ErroDeImpressao(f"Tipo de conexão não suportado: {tipo}.")

    try:
        # Abre agora, e não na primeira escrita: o python-escpos abre a conexão
        # preguiçosamente no primeiro acesso a `.device`, o que faria a falha de
        # cabo/IP estourar no meio do cupom em vez de aqui, onde ainda dá pra
        # avisar o operador antes de gastar papel.
        conexao.open()
        _limitar_escrita_serial(conexao, tipo, timeout_s)
    except Exception as erro:
        with contextlib.suppress(Exception):
            conexao.close()
        raise ErroDeImpressao(
            f"Não foi possível conectar na impressora '{nome}' ({tipo}): {erro}. "
            "Verifique se ela está ligada e com o cabo (ou a rede) conectado."
        ) from erro
    return conexao


def _limitar_escrita_serial(conexao, tipo: str, timeout_s: float) -> None:
    """Impõe `write_timeout` na porta serial já aberta.

    No pyserial, `timeout` limita só a LEITURA; quem limita a escrita é
    `write_timeout`, e o python-escpos não repassa esse parâmetro (o `**kwargs`
    do `Serial` vai para `Escpos.__init__`, não para o `serial.Serial`). Sem
    ele a escrita é bloqueante para sempre — e como a impressão roda na thread
    da UI por decisão de arquitetura, uma impressora desligada em COM3
    congelaria a janela inteira do PDV, sem exceção nenhuma para capturar. O
    contrato da Fase 4 é explícito: nada pode ficar pendurado.
    """
    if tipo != "SERIAL":
        return
    porta = getattr(conexao, "device", None)
    if porta is None:
        return
    porta.write_timeout = timeout_s


# ----------------------------------------------------------------------
# Leitura e validação dos parâmetros do cadastro
# ----------------------------------------------------------------------


def _tipo_de_conexao(impressora: "Impressora") -> str:
    """Normaliza `impressora.tipo_conexao` para o nome do tipo, em maiúsculas.

    Aceita tanto o enum `TipoConexaoImpressora` quanto a string equivalente.
    Isso é o que mantém `hardware/` sem import de `domain/` em runtime — e de
    quebra permite testar com um objeto simples, sem banco.
    """
    bruto = getattr(impressora, "tipo_conexao", None)
    if bruto is None:
        raise ErroDeImpressao(
            f"A impressora '{_nome_da(impressora)}' não tem tipo de conexão cadastrado. "
            "Escolha um tipo (USB, SERIAL, REDE, WINDOWS ou ARQUIVO) no cadastro de Impressoras."
        )
    tipo = str(getattr(bruto, "value", bruto)).strip().upper()
    if tipo not in TIPOS_SUPORTADOS:
        raise ErroDeImpressao(
            f"Tipo de conexão '{tipo}' não é suportado pela impressora "
            f"'{_nome_da(impressora)}'. Use um destes: {', '.join(TIPOS_SUPORTADOS)}."
        )
    return tipo


def _nome_da(impressora: "Impressora") -> str:
    nome = str(getattr(impressora, "nome", "") or "").strip()
    return nome or "sem nome"


def _colunas_de(impressora: "Impressora") -> int:
    colunas = getattr(impressora, "colunas", None)
    try:
        valor = int(colunas)
    except (TypeError, ValueError):
        return COLUNAS_PADRAO
    # Largura absurda (ou negativa) quebraria o center()/wrap() lá embaixo;
    # cair no padrão é melhor do que derrubar a impressão por um cadastro torto.
    return valor if 20 <= valor <= 120 else COLUNAS_PADRAO


def _bobina_de(impressora: "Impressora") -> int:
    """58 ou 80. Sem bobina válida, a de 80mm.

    Do banco ela sempre vem (`NOT NULL` desde a migração `b9d2f5a31c47`); sem
    ela só chega um objeto solto de teste ou um valor mexido à mão. Cair na de
    80mm nunca liga a condensada para quem cabe nas 48 colunas da fonte normal.
    """
    bobina = getattr(impressora, "bobina_mm", None)
    return bobina if bobina in COLUNAS_NA_FONTE_NORMAL else BOBINA_PADRAO_MM


def escala_de(impressora: "Impressora") -> int:
    """2, 3 ou 4 do cadastro; fora da faixa do `GS !`, o dobro."""
    escala = getattr(impressora, "escala_fonte", None)
    if isinstance(escala, int) and not isinstance(escala, bool) and 1 <= escala <= ESCALA_MAXIMA:
        return escala
    return ESCALA_PADRAO


def usa_fonte_condensada(colunas: int, bobina_mm: int) -> bool:
    """A fonte B entra quando as colunas passam do que a bobina imprime na fonte A.

    32 na de 58mm e 48 na de 80mm ficam na normal; 64 e 80 na de 80mm, e
    qualquer coisa acima de 32 na de 58mm, pedem a condensada.
    """
    return colunas > COLUNAS_NA_FONTE_NORMAL.get(bobina_mm, COLUNAS_PADRAO)


def _caminho_do_arquivo(impressora: "Impressora") -> Path:
    bruto = str(getattr(impressora, "caminho_arquivo", "") or "").strip()
    if bruto:
        return Path(bruto).expanduser()
    # Sem caminho informado o modo ARQUIVO ainda tem que funcionar: ele é o
    # padrão de quem cadastra sem preencher nada, e falhar aqui tiraria do
    # Vitor justamente o modo que existe para testar sem impressora.
    seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in _nome_da(impressora))
    return PASTA_CUPONS_PADRAO / f"{seguro.strip() or 'impressora'}.txt"


def _texto_obrigatorio(impressora: "Impressora", campo: str, mensagem: str) -> str:
    valor = str(getattr(impressora, campo, "") or "").strip()
    if not valor:
        raise ErroDeImpressao(mensagem)
    return valor


def _inteiro_ou(impressora: "Impressora", campo: str, padrao: int) -> int:
    valor = getattr(impressora, campo, None)
    if valor in (None, ""):
        return padrao
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ErroDeImpressao(
            f"O campo '{campo}' da impressora '{_nome_da(impressora)}' precisa ser um "
            f"número inteiro, e está como {valor!r}."
        ) from None


def _id_usb(impressora: "Impressora", campo: str, rotulo: str, nome: str) -> int:
    """Converte o id USB cadastrado ('0x04b8', '04b8' ou '04B8') para inteiro."""
    bruto = _texto_obrigatorio(
        impressora,
        campo,
        f"A impressora '{nome}' está como USB mas não tem {rotulo} cadastrado. "
        f"Rode 'lsusb' (ou veja o Gerenciador de Dispositivos) e informe {rotulo} "
        "no cadastro de Impressoras.",
    )
    try:
        # Sempre hexadecimal: fabricante e etiqueta do produto publicam esses
        # ids em hex ('0x04b8'), e interpretar '4b8' como decimal abriria a
        # porta pra impressora certa nunca ser encontrada por um zero à toa.
        return int(bruto, 16)
    except ValueError:
        raise ErroDeImpressao(
            f"O {rotulo} da impressora '{nome}' está como {bruto!r}, que não é um "
            "número hexadecimal válido. Use o formato 0x04b8."
        ) from None


def _exigir_biblioteca(classe, nome: str, pacote: str, descricao: str) -> None:
    """Barra o tipo de conexão cuja biblioteca opcional não está instalada.

    O python-escpos declara pyusb, pyserial e pywin32 como extras. Sem elas ele
    levanta `RuntimeError` com mensagem em inglês — e, no caso do USB, ainda
    constrói o objeto e só quebra no coletor de lixo, poluindo o terminal. Por
    isso a checagem é feita antes de construir, via `is_usable()`.
    """
    if not classe.is_usable():
        raise ErroDeImpressao(
            f"A impressora '{nome}' usa conexão {descricao}, mas a biblioteca "
            f"necessária não está instalada nesta máquina. Instale com: "
            f"pip install {pacote}"
        )
