"""O cartão que cadastra e edita impressora: "Nova impressora" e "Editar impressora" (§9.19).

Substitui o `_ImpressoraDialog` que morava dentro de `impressoras_view.py`: um
`QFormLayout` com a moldura do sistema, um `QComboBox` de cinco tipos de
conexão, oito `QLineEdit` que apareciam e sumiam conforme o tipo, um `QSpinBox`
de colunas e um `QCheckBox` "Impressora em uso" que só existia na edição. Quem
cadastra impressora é o pai do Vitor no dia da instalação, e "Largura da bobina:
[48 colunas ▴▾]" pede a ele um número que ele não sabe — o que ele sabe é que a
bobina é de 80mm.

**Uma classe só para os dois modos** (`ModoDoCadastro`), porque "Nova" e
"Editar" são a mesma tela com três frases e o ponto de partida diferentes. As
frases moram em `MODOS`, uma linha por modo, na forma do §9.6 e do §9.12; o
ponto de partida é um `_Retrato` montado uma vez na construção. Quem chama usa
os construtores nomeados `para_nova`/`para_editar` (a convenção do
`PinPadDialog`, §9.10), e o `__init__` aceita `modo="novo"`/`modo="editar"`.

## As três decisões do Vitor, perguntadas antes de começar

1. **Três cards, cinco tipos.** O banco tem USB direto, Serial, Rede, fila do
   Windows e Arquivo; o mockup tem Arquivo, USB e Rede. O card **USB** é a
   *conexão local*: o campo dele lista as filas de impressão instaladas no
   Windows e as portas COM da máquina (`ImpressaoService.listar_destinos_locais`),
   e aceita digitar `COM3` ou `0x04b8:0x0202`. O que se escolhe ali é gravado como
   WINDOWS, SERIAL ou USB — os campos que já existiam — e sai no papel pelo
   caminho de sempre. Não há "detectar automaticamente" na hora de imprimir: o
   driver (`hardware/impressora_escpos.py`) não foi tocado;
2. **"Uso da impressão" grava a marca de padrão**, e só ela: "Recibo do
   cliente" é `padrao=True` (a antiga perde a marca no mesmo commit) e
   "Produção (por categoria)" é `padrao=False`. Copa/Bar do mockup não entrou —
   faria exatamente o mesmo que Cozinha, e seria um rótulo dizendo uma coisa
   que o sistema não faz. Schema intacto;
3. **"Impressora ativa" funciona nos dois modos.** `criar_impressora` ganhou
   `ativa`, e impressora desligada nunca é a padrão: desligar o interruptor
   desliga a opção "Recibo do cliente" na mesma hora, para a tela mostrar o que
   vai ser gravado.

## O formato do cupom (§9.22)

A linha da bobina ganhou "Colunas por linha" (32 · 48 · 64 · 80) e a de baixo
virou "Espessura da letra" ao lado da "Situação". As três decisões do Vitor:

1. **Quatro larguras, e não as três do mockup.** 64 é a bobina de 80mm na fonte
   condensada, que o driver liga sozinho (`usa_fonte_condensada`). O 80 ficou
   mesmo depois do aviso de que não cabe na fonte de nenhuma térmica comum: a
   régua do cupom de teste é quem diz se a impressora dele imprime;
2. **A bobina é gravada** (`Impressora.bobina_mm`), e não deduzida das colunas:
   "58mm + 48 col." reabre como foi salva. As colunas são livres em qualquer
   bobina. Trocar de bobina só SUGERE: cada bobina lembra as colunas que tinha
   enquanto o cartão está aberto, e a primeira visita sugere 32 na de 58mm e 48
   na de 80mm (`COLUNAS_SUGERIDAS`). Voltar à bobina de partida devolve as
   colunas cadastradas — inclusive uma largura antiga sem botão, como 42;
3. **Letra grossa é a ênfase do ESC/POS no cupom inteiro** (`letra_grossa`).

O resumo diz as cinco coisas: `Caixa 01 · USB · 80mm · 80 col. · letra grossa`.

## O que este diálogo NÃO faz

Não grava nada sozinho e não conhece `CardapioService`. Ele monta
`DadosImpressora` e entrega à função `salvar` que a view passou; a função
devolve a mensagem de erro do service, ou `None`. Com erro, o cartão continua
aberto com tudo o que foi escolhido — e é por isso que este cartão é de
**uma abertura só** (`executar_modal`), e não do `while modal.exec()` do
Cardápio, cujo cartão reaberto fica com os botões mudos (achado do §9.18).

A conferência desta tela é só um aviso: quem recusa nome repetido, gerente
ausente e parâmetro inválido continua sendo o service. A tela é MAIS estrita que
ele em dois pontos, e está escrito aqui para ninguém se surpreender comparando as
camadas: nome com pelo menos `MINIMO_NOME` letras, e endereço de rede que seja um
**IPv4** (o service aceitaria um nome de máquina).

## Ciclo de vida (o RNF do Celeron, §3.2/§3.9/§3.14)

* **destroy** — quem destrói é `executar_modal()` (§3.2), depois de ler o
  resultado. Os filhos morrem com o cartão; o único widget que não é filho do
  diálogo é o escurecedor, filho da janela, solto em `done()`;
* **unbind** — atalho global nenhum: quem lê o teclado é o `keyPressEvent` do
  próprio diálogo. As ligações de sinal saem uma a uma em `_soltar_recursos()`,
  nenhuma é `lambda`, e a trava `_limpo` torna a limpeza idempotente;
* **timer e thread** — a lista de impressoras do Windows sai de uma thread de
  trabalho (o spooler pode demorar a responder), e o cartão confere o resultado
  num `QTimer` de 50ms que para sozinho quando a lista chega. Nenhum objeto Qt
  atravessa para a thread: ela só enxerga `_BuscaDeDestinos`, que é Python puro,
  então fechar o cartão no meio da busca não deixa sinal nenhum apontando para
  widget morto. O relógio para e se desconecta em `_soltar_recursos()`; a thread
  é `daemon` e termina sozinha quando o spooler responder.
"""

from __future__ import annotations

import ipaddress
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gestor_comercial.core.resilience import logger_do_app, nao_deixa_escapar
from gestor_comercial.domain.enums import TipoConexaoImpressora
from gestor_comercial.domain.impressora import (
    BOBINA_58MM,
    BOBINA_80MM,
    BOBINAS_MM,
    COLUNAS_58MM,
    COLUNAS_PADRAO,
    PORTA_REDE_PADRAO,
    Impressora,
    bobina_mm_das_colunas,
)
from gestor_comercial.services.cardapio_service import PORTA_REDE_MAXIMA
from gestor_comercial.services.impressao_service import DestinoLocal
from gestor_comercial.ui.widgets import cartao_modal
from gestor_comercial.ui.widgets.cardapio_cartoes import (
    GLIFO_ARQUIVO_TEXTO,
    GLIFO_COLUNAS,
    GLIFO_IMPRESSORA,
    GLIFO_LETRAS,
    GLIFO_MAIS,
    GLIFO_NEGRITO,
    GLIFO_REDE,
    GLIFO_SETA_BAIXO,
    GLIFO_SINAL,
    GLIFO_USB,
    GLIFO_VISTO,
    BotaoComGlifo,
    GlifoSolto,
    RotuloComReticencias,
)
from gestor_comercial.ui.widgets.cartao_modal import Backdrop
from gestor_comercial.ui.widgets.estilo import aplicar_propriedade
from gestor_comercial.ui.widgets.interruptor import Interruptor
from gestor_comercial.ui.widgets.painel_pontilhado import PainelPontilhado

# O teto do nome. A coluna é `String(80)`; o mockup pede 40, que é o que cabe
# no resumo e na coluna "Nome" da tabela sem virar reticências. Nome que JÁ
# existe mais comprido não é cortado na edição — ver `_maximo_do_nome`.
LIMITE_NOME = 40

# Trava de TELA: o service só recusa vazio. Uma letra sozinha não identifica
# impressora nenhuma na hora de escolher para onde vai a categoria.
MINIMO_NOME = 2

# As larguras do seletor "Colunas por linha" (§9.22). Ver o cabeçalho: 64 é a
# de 80mm na fonte condensada, e 80 ficou por decisão do Vitor.
COLUNAS_POR_LINHA = (32, 48, 64, 80)

_DICA_DAS_COLUNAS = {
    32: "Bobina de 58mm na fonte normal.",
    48: "Bobina de 80mm na fonte normal.",
    64: "Bobina de 80mm na fonte condensada, que a impressão liga sozinha.",
    80: (
        "Só para impressora que imprime 80 colunas: nem a fonte condensada de uma "
        "térmica comum chega lá. Confira com a régua do cupom de teste."
    ),
}

# De quanto em quanto tempo o cartão olha se a lista do Windows chegou, e até
# quando espera. O teto não mata a thread (thread não se mata em Python): só
# para de esperar e deixa o campo aceitando o que for digitado.
INTERVALO_DA_BUSCA_MS = 50
TETO_DA_BUSCA_S = 8.0

USO_RECIBO = "Recibo do cliente"
USO_PRODUCAO = "Produção (por categoria)"

_SECAO = "SAÍDA E PRODUÇÃO"
_TAG_AJUSTE_VISUAL = "AJUSTE VISUAL"
_SEM_NOME = "Sem nome"
_ROTULO_RESUMO = "RESUMO DA CONFIGURAÇÃO"
_ROTULO_ERRO_SERVICO = "NÃO FOI POSSÍVEL SALVAR"

_CABECALHO_FILAS = "IMPRESSORAS DO WINDOWS"
_CABECALHO_PORTAS = "PORTAS COM"

_PROCURANDO = "Procurando impressoras instaladas…"
_ESCOLHA = "Escolha a impressora instalada"
_NENHUMA = "Nenhuma encontrada — digite o nome ou a porta (COM3)"

# `✕` e não `❌`: o primeiro mora na fonte de texto, o segundo cairia no Segoe
# UI Emoji e sairia colorido e chapado (§9.4, §9.10, §9.12).
_STATUS_FALTA_NOME = "Falta o nome"
_STATUS_NOME_CURTO = f"Mínimo de {MINIMO_NOME} caracteres"
_STATUS_NOME_REPETIDO = "✕  Nome já existente"
_STATUS_FALTA_LOCAL = "Escolha a impressora local"
_STATUS_FALTA_IP = "Informe o IP da impressora"
_STATUS_IP_INVALIDO = "✕  IP inválido"
_STATUS_PORTA_INVALIDA = f"✕  Porta de 1 a {PORTA_REDE_MAXIMA}"
_STATUS_SEM_RECIBO = "Sem impressora de recibo"

_PORTA_COM = re.compile(r"COM[0-9]{1,3}", re.IGNORECASE)
_PAR_USB = re.compile(r"(?:0x)?([0-9a-f]{1,4})\s*:\s*(?:0x)?([0-9a-f]{1,4})", re.IGNORECASE)
_NUMERO_DE_PORTA = re.compile(r"[0-9]{1,5}")


class ModoDoCadastro(Enum):
    NOVO = "novo"
    EDITAR = "editar"


class Conexao(Enum):
    """Os três cards. Não é `TipoConexaoImpressora`: o card LOCAL vira três tipos."""

    ARQUIVO = "arquivo"
    LOCAL = "local"
    REDE = "rede"


class Bobina(Enum):
    MM58 = "58mm"
    MM80 = "80mm"

    @property
    def mm(self) -> int:
        """O número que vai para `Impressora.bobina_mm`."""
        return BOBINA_58MM if self is Bobina.MM58 else BOBINA_80MM

    @classmethod
    def de_mm(cls, mm: int) -> "Bobina":
        return cls.MM58 if mm == BOBINA_58MM else cls.MM80


# A primeira sugestão de cada bobina, na primeira vez que o gerente a escolhe
# com o cartão aberto (o pedido: 58mm sugere 32, 80mm sugere 48).
COLUNAS_SUGERIDAS: dict[Bobina, int] = {Bobina.MM58: COLUNAS_58MM, Bobina.MM80: COLUNAS_PADRAO}


class Espessura(Enum):
    FINA = "fina"
    GROSSA = "grossa"


@dataclass(frozen=True, slots=True)
class _OpcaoDeEspessura:
    """O que separa "Letras finas" de "Letras grossas": o glifo, as palavras e a dica."""

    glifo: str
    rotulo: str
    no_resumo: str
    dica: str


ESPESSURAS: dict[Espessura, _OpcaoDeEspessura] = {
    Espessura.FINA: _OpcaoDeEspessura(
        GLIFO_LETRAS,
        "Letras finas",
        "letra fina",
        "O peso normal da impressora. Os títulos do cupom saem em negrito.",
    ),
    Espessura.GROSSA: _OpcaoDeEspessura(
        GLIFO_NEGRITO,
        "Letras grossas",
        "letra grossa",
        "O cupom inteiro em negrito, mais fácil de ler de longe. Os títulos "
        "deixam de se destacar do resto.",
    ),
}


@dataclass(frozen=True, slots=True)
class _OpcaoDeConexao:
    """Tudo o que separa um card de conexão do outro — e o campo que ele abre."""

    glifo: str
    titulo: str
    subtitulo: str
    rotulo_campo: str
    placeholder: str


CONEXOES: dict[Conexao, _OpcaoDeConexao] = {
    Conexao.ARQUIVO: _OpcaoDeConexao(
        GLIFO_ARQUIVO_TEXTO,
        "Arquivo",
        ".txt",
        "ARQUIVO DO CUPOM (opcional)",
        "Padrão: cupons/<nome>.txt",
    ),
    Conexao.LOCAL: _OpcaoDeConexao(GLIFO_USB, "USB", "Conexão local", "PORTA USB", _ESCOLHA),
    Conexao.REDE: _OpcaoDeConexao(
        GLIFO_REDE, "Rede", "IP da impressora", "IP E PORTA DA IMPRESSORA", "192.168.1.200:9100"
    ),
}


@dataclass(frozen=True, slots=True)
class _Modo:
    titulo: str
    subtitulo: str
    botao: str
    glifo_botao: str


MODOS: dict[ModoDoCadastro, _Modo] = {
    ModoDoCadastro.NOVO: _Modo(
        "Nova impressora",
        "Cadastre a conexão e o uso desta impressora.",
        "Cadastrar impressora",
        GLIFO_MAIS,
    ),
    ModoDoCadastro.EDITAR: _Modo(
        "Editar impressora",
        "Atualize a conexão e o uso desta impressora.",
        "Salvar alterações",
        GLIFO_VISTO,
    ),
}


@dataclass(frozen=True, slots=True)
class DadosImpressora:
    """O que o cartão devolve: o formulário inteiro, já no vocabulário do service.

    Campos nomeados e não uma tupla pelo motivo do `DadosProduto` (§9.8): quatro
    destes são `str | None` e trocar dois de posição gravaria o IP no lugar da
    fila, calado.
    """

    nome: str
    tipo_conexao: TipoConexaoImpressora
    colunas: int
    ativa: bool
    padrao: bool
    bobina_mm: int = BOBINA_80MM
    letra_grossa: bool = False
    vendor_id: str | None = None
    product_id: str | None = None
    porta_serial: str | None = None
    baudrate: int | None = None
    host: str | None = None
    porta_rede: int | None = None
    nome_fila: str | None = None
    caminho_arquivo: str | None = None

    def parametros(self) -> dict[str, object]:
        """Tudo menos nome e tipo, prontos para `**kwargs` em criar/editar."""
        return {
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "porta_serial": self.porta_serial,
            "baudrate": self.baudrate,
            "host": self.host,
            "porta_rede": self.porta_rede,
            "nome_fila": self.nome_fila,
            "caminho_arquivo": self.caminho_arquivo,
            "colunas": self.colunas,
            "bobina_mm": self.bobina_mm,
            "letra_grossa": self.letra_grossa,
            "ativa": self.ativa,
            "padrao": self.padrao,
        }


@dataclass(frozen=True, slots=True)
class LeituraDaConexao:
    """O que o campo da conexão escolhida diz: os parâmetros, ou por que ainda não.

    `grave=False` com `problema` é o campo incompleto (botão desligado, sem
    vermelho); `grave=True` é o campo errado.
    """

    tipo: TipoConexaoImpressora | None
    parametros: dict[str, object] = field(default_factory=dict)
    problema: str = ""
    grave: bool = False


# ---------------------------------------------------------------------------
# Leituras puras — testadas sem widget nenhum
# ---------------------------------------------------------------------------


def conexao_do_tipo(tipo: TipoConexaoImpressora) -> Conexao:
    """Em qual card uma impressora já cadastrada abre."""
    if tipo is TipoConexaoImpressora.ARQUIVO:
        return Conexao.ARQUIVO
    if tipo is TipoConexaoImpressora.REDE:
        return Conexao.REDE
    return Conexao.LOCAL


def bobina_das_colunas(colunas: int) -> Bobina:
    """A bobina de quem não a tem gravada: a regra do §9.19, a mesma da migração."""
    return Bobina.de_mm(bobina_mm_das_colunas(colunas))


def bobina_da_impressora(impressora: Impressora) -> Bobina:
    """A bobina GRAVADA, e só ela (§9.22) — "58mm + 48 col." reabre em 58mm.

    Sem valor válido, a regra das colunas. Do banco ele sempre vem (`NOT NULL`);
    cai aqui a `Impressora` solta que ainda não foi gravada, e um valor mexido à
    mão, que sem isso derrubaria a abertura da edição.
    """
    if impressora.bobina_mm in BOBINAS_MM:
        return Bobina.de_mm(impressora.bobina_mm)
    return bobina_das_colunas(impressora.colunas)


def ler_caminho_de_arquivo(texto: str) -> LeituraDaConexao:
    """Vazio vale: o service escolhe `cupons/<nome>.txt`."""
    return LeituraDaConexao(
        TipoConexaoImpressora.ARQUIVO, {"caminho_arquivo": texto.strip() or None}
    )


def ler_endereco_de_rede(texto: str) -> LeituraDaConexao:
    """`192.168.1.200` ou `192.168.1.200:9100`. Sem porta, a 9100 de sempre."""
    bruto = texto.strip()
    if not bruto:
        return LeituraDaConexao(None, problema=_STATUS_FALTA_IP)
    host, separador, porta_texto = bruto.rpartition(":")
    if not separador:
        host = bruto
    try:
        # `IPv4Address` recusa "192.168.001.200" (zero à esquerda é ambíguo
        # entre decimal e octal em algumas pilhas de rede) e "192.168.1".
        ipaddress.IPv4Address(host)
    except ValueError:
        return LeituraDaConexao(None, problema=_STATUS_IP_INVALIDO, grave=True)
    porta = PORTA_REDE_PADRAO
    if separador:
        if not _NUMERO_DE_PORTA.fullmatch(porta_texto) or not 1 <= int(porta_texto) <= PORTA_REDE_MAXIMA:
            return LeituraDaConexao(None, problema=_STATUS_PORTA_INVALIDA, grave=True)
        porta = int(porta_texto)
    return LeituraDaConexao(TipoConexaoImpressora.REDE, {"host": host, "porta_rede": porta})


def ler_destino_local(
    texto: str,
    conhecidos: Mapping[str, DestinoLocal],
    baudrate: int | None = None,
) -> LeituraDaConexao:
    """O card USB vira um de três tipos, conforme o que está no campo.

    A lista que o Windows devolveu decide primeiro (`conhecidos`, pela chave em
    `casefold`). O que foi digitado e não está nela é lido pelo formato:
    `COM3` é porta serial, `0x04b8:0x0202` é USB direto, e qualquer outro texto
    é o nome de uma fila do Windows — a impressora pode ainda nem estar
    instalada nesta máquina, e o gerente estar cadastrando pelo nome que ela vai
    ter. `baudrate` só é usado na porta serial: é o da impressora que está sendo
    editada, que o mockup não mostra e a edição não pode apagar.
    """
    bruto = texto.strip()
    if not bruto:
        return LeituraDaConexao(None, problema=_STATUS_FALTA_LOCAL)
    conhecido = conhecidos.get(bruto.casefold())
    if conhecido is not None:
        tipo = TipoConexaoImpressora(conhecido.tipo)
        valor = conhecido.valor
    else:
        tipo = _tipo_digitado(bruto)
        valor = bruto
    if tipo is TipoConexaoImpressora.SERIAL:
        return LeituraDaConexao(tipo, {"porta_serial": valor.upper(), "baudrate": baudrate})
    if tipo is TipoConexaoImpressora.USB:
        par = _PAR_USB.fullmatch(valor)
        assert par is not None  # `_tipo_digitado` só devolve USB quando casa
        return LeituraDaConexao(
            tipo,
            {"vendor_id": f"0x{int(par[1], 16):04x}", "product_id": f"0x{int(par[2], 16):04x}"},
        )
    return LeituraDaConexao(TipoConexaoImpressora.WINDOWS, {"nome_fila": valor})


def _tipo_digitado(texto: str) -> TipoConexaoImpressora:
    if _PORTA_COM.fullmatch(texto):
        return TipoConexaoImpressora.SERIAL
    if _PAR_USB.fullmatch(texto):
        return TipoConexaoImpressora.USB
    return TipoConexaoImpressora.WINDOWS


def _texto_aparado(texto: str) -> str:
    """O nome como vai para o banco: pontas aparadas, espaço interno único."""
    return " ".join(texto.split())


@dataclass(frozen=True, slots=True)
class _Retrato:
    """O ponto de partida do cartão, copiado da impressora UMA vez.

    O diálogo nunca guarda a `Impressora` do SQLAlchemy: todo commit expira a
    instância, e um modal que a lesse depois voltaria ao banco — ou pior, a
    prenderia viva na `Session` enquanto estivesse aberto (§3.4).
    """

    nome: str = ""
    conexao: Conexao = Conexao.ARQUIVO
    caminho_arquivo: str = ""
    destino_local: str = ""
    endereco_rede: str = ""
    baudrate: int | None = None
    colunas: int = COLUNAS_PADRAO
    bobina: Bobina = Bobina.MM80
    letra_grossa: bool = False
    ativa: bool = True
    padrao: bool = False

    @classmethod
    def de(cls, impressora: Impressora | None, *, padrao_se_nova: bool) -> "_Retrato":
        # Cadastro novo abre em ARQUIVO, o mesmo default de `criar_impressora`:
        # é o único tipo que funciona sem hardware nenhum, e é o que faz o food
        # truck imprimir no dia em que o app chega.
        if impressora is None:
            return cls(padrao=padrao_se_nova)
        tipo = impressora.tipo_conexao
        local = ""
        if tipo is TipoConexaoImpressora.USB:
            local = f"{impressora.vendor_id or ''}:{impressora.product_id or ''}"
        elif tipo is TipoConexaoImpressora.SERIAL:
            local = impressora.porta_serial or ""
        elif tipo is TipoConexaoImpressora.WINDOWS:
            local = impressora.nome_fila or ""
        rede = ""
        if tipo is TipoConexaoImpressora.REDE and impressora.host:
            rede = f"{impressora.host}:{impressora.porta_rede or PORTA_REDE_PADRAO}"
        return cls(
            nome=impressora.nome,
            conexao=conexao_do_tipo(tipo),
            caminho_arquivo=impressora.caminho_arquivo or "",
            destino_local=local,
            endereco_rede=rede,
            baudrate=impressora.baudrate if tipo is TipoConexaoImpressora.SERIAL else None,
            colunas=impressora.colunas,
            bobina=bobina_da_impressora(impressora),
            letra_grossa=bool(impressora.letra_grossa),
            ativa=bool(impressora.ativa),
            padrao=bool(impressora.padrao),
        )


class _BuscaDeDestinos:
    """Uma thread que pergunta ao Windows pelas impressoras, uma vez.

    Python puro de propósito: é a única coisa que a thread de trabalho enxerga.
    Sem `QObject` aqui não há sinal para emitir de outra thread, nem objeto do
    Qt para ser destruído na thread errada quando o cartão fecha no meio.
    """

    def __init__(self, listar: Callable[[], Sequence[DestinoLocal]]) -> None:
        self._listar = listar
        self._destinos: list[DestinoLocal] = []
        self._pronta = threading.Event()
        self._inicio = 0.0

    def iniciar(self) -> None:
        self._inicio = time.monotonic()
        threading.Thread(target=self._rodar, name="descoberta-de-impressoras", daemon=True).start()

    def _rodar(self) -> None:
        try:
            self._destinos = list(self._listar())
        except Exception:
            # A lista é conveniência: sem ela o campo continua aceitando o nome
            # digitado. O motivo vai para o gestor.log, e o cadastro segue.
            logger_do_app().exception("Não foi possível listar as impressoras locais.")
            self._destinos = []
        finally:
            self._pronta.set()

    def resultado(self) -> list[DestinoLocal] | None:
        """A lista, ou `None` se o Windows ainda não respondeu."""
        return list(self._destinos) if self._pronta.is_set() else None

    def esgotou(self, teto_s: float) -> bool:
        return time.monotonic() - self._inicio > teto_s


# ---------------------------------------------------------------------------
# Peças do cartão
# ---------------------------------------------------------------------------


class _CartaoConexao(QFrame):
    """Um dos três cards de conexão: glifo, título, subtítulo e o visto.

    `QFrame` e não `QPushButton` checável pelo motivo do `_CartaoCargo` (§9.5):
    são duas linhas de pesos e cores diferentes, que o texto único de um botão
    não estiliza. Sem foco: quem lê o teclado é o diálogo.
    """

    clicado = Signal()

    LADO_GLIFO_PX = 20
    LADO_VISTO_PX = 14

    def __init__(self, conexao: Conexao, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        opcao = CONEXOES[conexao]
        self.conexao = conexao
        self.setObjectName("impDialogConexao")
        self.setProperty("selecionado", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(14, 12, 12, 12)
        linha.setSpacing(12)

        self._glifo = GlifoSolto(opcao.glifo, self.LADO_GLIFO_PX, "impressora_opcao_glifo")
        linha.addWidget(self._glifo, 0, Qt.AlignmentFlag.AlignVCenter)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        titulo = QLabel(opcao.titulo)
        titulo.setObjectName("impDialogConexaoTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel(opcao.subtitulo)
        subtitulo.setObjectName("impDialogConexaoSubtitulo")
        textos.addWidget(subtitulo)
        linha.addLayout(textos, 1)

        self._visto = GlifoSolto(GLIFO_VISTO, self.LADO_VISTO_PX, "impressora_opcao_ativa_glifo")
        # O visto guarda o lugar mesmo escondido: card que muda de largura ao
        # ser escolhido é o que faz o dedo errar o próximo (§9.5).
        politica = self._visto.sizePolicy()
        politica.setRetainSizeWhenHidden(True)
        self._visto.setSizePolicy(politica)
        self._visto.setVisible(False)
        linha.addWidget(self._visto, 0, Qt.AlignmentFlag.AlignVCenter)

    def selecionar(self, selecionado: bool) -> None:
        if self.property("selecionado") == selecionado:
            return
        aplicar_propriedade(self, "selecionado", selecionado)
        self._glifo.trocar_token(
            "impressora_opcao_ativa_glifo" if selecionado else "impressora_opcao_glifo"
        )
        self._visto.setVisible(selecionado)

    @nao_deixa_escapar()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
        super().mousePressEvent(event)


class _CartaoSituacao(QFrame):
    """"Impressora ativa" com o sinal e o interruptor. O card inteiro é o alvo.

    O alvo é o card, e não só o interruptor de 38px, porque quem cadastra está
    de pé no balcão: o mockup desenha o interruptor pequeno, e o dedo acerta o
    retângulo.
    """

    clicado = Signal()

    ATIVA = "Impressora ativa"
    INATIVA = "Impressora desativada"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("impDialogSituacao")
        self.setProperty("ativa", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(14, 0, 12, 0)
        linha.setSpacing(10)
        self._sinal = GlifoSolto(GLIFO_SINAL, 18, "impressora_situacao_ativa_texto")
        linha.addWidget(self._sinal, 0, Qt.AlignmentFlag.AlignVCenter)
        self._texto = QLabel(self.ATIVA)
        self._texto.setObjectName("impDialogSituacaoTexto")
        self._texto.setProperty("ativa", True)
        linha.addWidget(self._texto, 1)
        self.interruptor = Interruptor()
        linha.addWidget(self.interruptor, 0, Qt.AlignmentFlag.AlignVCenter)

    @nao_deixa_escapar(retorno=QSize(0, 0))
    def minimumSizeHint(self) -> QSize:  # noqa: N802 (override Qt)
        """O mínimo como se o rótulo mostrasse a frase MAIS LONGA dos dois estados.

        Sem isto o card pedia 242px ligado e 291px desligado: desligar a
        impressora fazia a linha inteira se redistribuir e os botões de
        espessura andavam debaixo do dedo (160 → 142px, medido) — e, no cartão
        de 600px do §9.19, "Impressora desativada" saía cortada (o teste só
        media o estado ligado). Basta o MÍNIMO, e não o `sizeHint` junto: o
        layout usa como tamanho preferido o maior dos dois, então um mínimo fixo
        fixa os dois (a checagem por mutação mostrou que o `sizeHint` ao lado
        não mudava nada, e ele saiu). A métrica é a do próprio rótulo, que já
        passou pelo QSS: fonte de QSS vence `setFont`, e medir outra fonte
        mediria outra coisa (§9.8).
        """
        medida = super().minimumSizeHint()
        metricas = self._texto.fontMetrics()
        maior = max(metricas.horizontalAdvance(frase) for frase in (self.ATIVA, self.INATIVA))
        extra = maior - metricas.horizontalAdvance(self._texto.text())
        return QSize(medida.width() + extra, medida.height())

    def definir(self, ativa: bool) -> None:
        self.interruptor.definir(ativa)
        self._texto.setText(self.ATIVA if ativa else self.INATIVA)
        self._sinal.trocar_token(
            "impressora_situacao_ativa_texto" if ativa else "impressora_situacao_inativa_texto"
        )
        if self.property("ativa") != ativa:
            aplicar_propriedade(self, "ativa", ativa)
            aplicar_propriedade(self._texto, "ativa", ativa)

    @nao_deixa_escapar()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
        super().mousePressEvent(event)


class _BotaoDeEspessura(QFrame):
    """"Letras finas" ou "Letras grossas": o glifo e a palavra, juntos no meio.

    `QFrame` e não `QPushButton`, pelo motivo do `_CartaoConexao`: o glifo tem
    que andar colado ao texto, e o texto de cada opção tem o PESO que ela
    promete (a grossa em negrito, a fina no normal), o que o texto único de um
    botão com glifo pintado numa margem fixa não faz. Sem foco: quem lê o
    teclado é o diálogo.
    """

    clicado = Signal()

    LADO_GLIFO_PX = 15

    def __init__(self, espessura: Espessura, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        opcao = ESPESSURAS[espessura]
        self.espessura = espessura
        self.setObjectName("impDialogEspessura")
        self.setProperty("selecionada", False)
        self.setToolTip(opcao.dica)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(12, 0, 12, 0)
        # Espaço zero e o respiro posto à mão: com `setSpacing` o layout põe o
        # vão também entre as molas e as peças, e são 16px a mais pedidos por
        # botão — foi o que espremia "Letras grossas" na medição.
        linha.setSpacing(0)
        linha.addStretch(1)
        self._glifo = GlifoSolto(opcao.glifo, self.LADO_GLIFO_PX, "impressora_opcao_glifo")
        linha.addWidget(self._glifo, 0, Qt.AlignmentFlag.AlignVCenter)
        linha.addSpacing(8)
        self._texto = QLabel(opcao.rotulo)
        self._texto.setObjectName("impDialogEspessuraTexto")
        self._texto.setProperty("espessura", espessura.value)
        self._texto.setProperty("selecionada", False)
        linha.addWidget(self._texto, 0, Qt.AlignmentFlag.AlignVCenter)
        linha.addStretch(1)

    def selecionar(self, selecionada: bool) -> None:
        if self.property("selecionada") == selecionada:
            return
        aplicar_propriedade(self, "selecionada", selecionada)
        aplicar_propriedade(self._texto, "selecionada", selecionada)
        self._glifo.trocar_token(
            "impressora_opcao_ativa_glifo" if selecionada else "impressora_opcao_glifo"
        )

    @nao_deixa_escapar()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (override Qt)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicado.emit()
        super().mousePressEvent(event)


class _SeletorComSeta(QComboBox):
    """`QComboBox` com a seta desenhada.

    O QSS global apaga a seta do sistema (`::down-arrow { image: none }`), que
    sai como um triângulo de outro desenho em cada tema. Aqui ela volta como
    glifo, transparente ao mouse: o clique cai na caixa e abre a lista.
    """

    LADO_SETA_PX = 12
    MARGEM_SETA_PX = 14

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._seta = GlifoSolto(GLIFO_SETA_BAIXO, self.LADO_SETA_PX, "texto_fraco", self)

    @nao_deixa_escapar()
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (override Qt)
        super().resizeEvent(event)
        self._seta.move(
            self.width() - self.MARGEM_SETA_PX - self.LADO_SETA_PX,
            (self.height() - self.LADO_SETA_PX) // 2,
        )


# ---------------------------------------------------------------------------
# O cartão
# ---------------------------------------------------------------------------


class ImpressoraDialog(QDialog):
    """Cartão de cadastro/edição de impressora. Ver o cabeçalho do módulo."""

    # 720, medido (§9.22). O §9.19 pedia "entre 560 e 620" e ficou em 600; a
    # linha "Espessura da letra | Situação" não cabe ali com a fonte da marca,
    # ~20% mais larga que a do mockup (o achado do §9.12): os dois botões de
    # espessura iguais pedem 171px cada ("Letras grossas" em negrito), e a
    # Situação 291px ("Impressora desativada"). A 680 nada espreme, mas os dois
    # botões saem desiguais; a partir de ~707 ficam iguais, e 720 deixa folga.
    # O próprio mockup mede 768. `test_nada_fica_espremido` mede tudo isso.
    LARGURA_CARTAO_PX = 720
    LADO_BOTAO_FECHAR_PX = 32
    LADO_BADGE_PX = 44
    LADO_ICONE_RESUMO_PX = 36
    ALTURA_CAMPO_PX = 44
    ALTURA_CONEXAO_PX = 64
    LADO_GLIFO_ROTULO_PX = 14
    # Quanto cada coluna das duas linhas do formato leva da largura. As colunas
    # têm quatro botões e a bobina dois; a espessura tem duas palavras e a
    # situação uma frase ("Impressora desativada") com o interruptor ao lado.
    PESO_BOBINA = 2
    PESO_COLUNAS = 3
    PESO_ESPESSURA = 5
    PESO_SITUACAO = 4

    def __init__(
        self,
        modo: ModoDoCadastro | str,
        parent: QWidget | None = None,
        *,
        impressora: Impressora | None = None,
        nomes_existentes: Sequence[str] = (),
        outra_padrao_ativa: bool = False,
        salvar: Callable[[DadosImpressora], str | None] | None = None,
        listar_destinos: Callable[[], Sequence[DestinoLocal]] | None = None,
    ) -> None:
        self._modo = ModoDoCadastro(modo)
        if (self._modo is ModoDoCadastro.EDITAR) != (impressora is not None):
            # Antes do `super().__init__`: um QDialog que nasce e estoura no meio
            # da construção ficaria pendurado no parent até o app fechar (§3.2).
            raise ValueError(
                "ImpressoraDialog: o modo 'editar' exige a impressora, e o 'novo' não a aceita."
            )
        super().__init__(parent)
        frases = MODOS[self._modo]
        self._retrato = _Retrato.de(impressora, padrao_se_nova=not outra_padrao_ativa)
        self._outra_padrao_ativa = outra_padrao_ativa
        self._salvar = salvar
        self._listar_destinos = listar_destinos
        self._nomes_ocupados = {
            nome for nome in nomes_existentes if nome != self._retrato.nome
        }

        self._conexao = self._retrato.conexao
        self._bobina = self._retrato.bobina
        self._colunas = self._retrato.colunas
        # As colunas que cada bobina "lembra" enquanto o cartão está aberto. A
        # de partida lembra as cadastradas; a outra começa na sugestão dela.
        # Duas entradas, e morre com o cartão.
        self._colunas_da_bobina: dict[Bobina, int] = dict(COLUNAS_SUGERIDAS)
        self._colunas_da_bobina[self._bobina] = self._colunas
        self._letra_grossa = self._retrato.letra_grossa
        self._ativa = self._retrato.ativa
        # A última escolha EXPLÍCITA de uso. Separada do que o seletor mostra
        # porque desligar a impressora tira o recibo dela à força — e religar
        # tem que devolver o que o gerente tinha escolhido, não o que sobrou.
        self._recibo_escolhido = self._retrato.padrao
        self._destinos: dict[str, DestinoLocal] = {}
        self._busca: _BuscaDeDestinos | None = None
        # "procurando" desde a construção quando há quem liste: o cartão só é
        # visto depois do `show()`, que é quando a busca começa de fato.
        self._estado_da_busca = "procurando" if listar_destinos is not None else "sem_busca"
        self._backdrop: Backdrop | None = None
        self._limpo = False
        self._cards: dict[Conexao, _CartaoConexao] = {}
        self._botoes_bobina: dict[Bobina, QPushButton] = {}
        self._botoes_colunas: dict[int, QPushButton] = {}
        self._botoes_espessura: dict[Espessura, _BotaoDeEspessura] = {}

        self.setObjectName("impDialog")
        self.setWindowTitle(frases.titulo)
        # Sem moldura do sistema: o cabeçalho é do cartão, e o fundo translúcido
        # é o que faz os cantos de 16px saírem redondos de verdade.
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        self._relogio = QTimer(self)
        self._relogio.setInterval(INTERVALO_DA_BUSCA_MS)
        self._relogio.timeout.connect(self._conferir_busca)

        moldura = QVBoxLayout(self)
        moldura.setContentsMargins(0, 0, 0, 0)
        cartao = QFrame()
        cartao.setObjectName("impDialogCard")
        cartao.setFixedWidth(self.LARGURA_CARTAO_PX)
        moldura.addWidget(cartao)

        corpo = QVBoxLayout(cartao)
        corpo.setContentsMargins(0, 0, 0, 0)
        corpo.setSpacing(0)
        corpo.addWidget(self._montar_cabecalho(frases))
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_corpo())
        corpo.addWidget(self._divisor())
        corpo.addWidget(self._montar_rodape(frases))

        self._pintar_conexao()
        self._pintar_bobina()
        self._pintar_colunas()
        self._pintar_espessura()
        self._pintar_situacao()
        self._pintar_placeholder_local()
        self._atualizar()

    # ------------------------------------------------------------------
    # Construtores nomeados
    # ------------------------------------------------------------------

    @classmethod
    def para_nova(
        cls,
        nomes_existentes: Sequence[str],
        parent: QWidget | None = None,
        *,
        ha_padrao_ativa: bool,
        salvar: Callable[[DadosImpressora], str | None] | None = None,
        listar_destinos: Callable[[], Sequence[DestinoLocal]] | None = None,
    ) -> "ImpressoraDialog":
        """Cadastro. Sem padrão ativa, abre em "Recibo do cliente" — a mesma
        regra que `criar_impressora` aplicaria sozinho."""
        return cls(
            ModoDoCadastro.NOVO,
            parent,
            nomes_existentes=nomes_existentes,
            outra_padrao_ativa=ha_padrao_ativa,
            salvar=salvar,
            listar_destinos=listar_destinos,
        )

    @classmethod
    def para_editar(
        cls,
        impressora: Impressora,
        nomes_existentes: Sequence[str],
        parent: QWidget | None = None,
        *,
        outra_padrao_ativa: bool,
        salvar: Callable[[DadosImpressora], str | None] | None = None,
        listar_destinos: Callable[[], Sequence[DestinoLocal]] | None = None,
    ) -> "ImpressoraDialog":
        """Edição, pré-carregada. `outra_padrao_ativa` é de OUTRA impressora: é
        o que decide se tirar o recibo desta deixa o app sem recibo."""
        return cls(
            ModoDoCadastro.EDITAR,
            parent,
            impressora=impressora,
            nomes_existentes=nomes_existentes,
            outra_padrao_ativa=outra_padrao_ativa,
            salvar=salvar,
            listar_destinos=listar_destinos,
        )

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _divisor(self) -> QFrame:
        linha = QFrame()
        linha.setObjectName("impDialogDivisor")
        linha.setFixedHeight(1)
        return linha

    def _rotulo(self, texto: str) -> QLabel:
        rotulo = QLabel(texto)
        rotulo.setObjectName("impDialogRotulo")
        return rotulo

    def _montar_cabecalho(self, frases: _Modo) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("impDialogCabecalho")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(24, 20, 20, 18)
        linha.setSpacing(16)

        badge = QFrame()
        badge.setObjectName("impDialogBadge")
        badge.setFixedSize(self.LADO_BADGE_PX, self.LADO_BADGE_PX)
        dentro = QHBoxLayout(badge)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(
            GlifoSolto(GLIFO_IMPRESSORA, 20, "impressora_badge_glifo"),
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        linha.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        secao = QLabel(_SECAO)
        secao.setObjectName("impDialogSecao")
        textos.addWidget(secao)
        titulo = QLabel(frases.titulo)
        titulo.setObjectName("impDialogTitulo")
        textos.addWidget(titulo)
        subtitulo = QLabel(frases.subtitulo)
        subtitulo.setObjectName("impDialogSubtitulo")
        subtitulo.setWordWrap(True)
        textos.addWidget(subtitulo)
        linha.addLayout(textos, 1)

        self._botao_fechar = QPushButton("✕")
        self._botao_fechar.setObjectName("impDialogFechar")
        self._botao_fechar.setFixedSize(self.LADO_BOTAO_FECHAR_PX, self.LADO_BOTAO_FECHAR_PX)
        self._botao_fechar.setToolTip("Fechar (Esc)")
        cartao_modal.preparar_botao(self._botao_fechar)
        self._botao_fechar.clicked.connect(self.reject)
        linha.addWidget(self._botao_fechar, 0, Qt.AlignmentFlag.AlignTop)
        return faixa

    def _montar_corpo(self) -> QWidget:
        """A faixa do meio, com a textura de pontos do mockup (a do §9.12)."""
        faixa = PainelPontilhado()
        faixa.setObjectName("impDialogCorpo")
        coluna = QVBoxLayout(faixa)
        # 18/14 e não os 20/18 do §9.19: são seis faixas agora, e com o erro
        # mais longo do service aceso (três linhas) o cartão tem que caber nos
        # 728px úteis de um monitor de 768
        # (`test_o_erro_do_service_nao_empurra_o_cartao_para_fora`).
        coluna.setContentsMargins(24, 18, 24, 18)
        coluna.setSpacing(14)
        coluna.addLayout(self._montar_nome())
        coluna.addLayout(self._montar_conexoes())
        coluna.addLayout(self._montar_destino_e_uso())
        coluna.addLayout(self._montar_bobina_e_colunas())
        coluna.addLayout(self._montar_espessura_e_situacao())
        coluna.addWidget(self._montar_resumo())
        return faixa

    def _montar_nome(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(8)
        topo = QHBoxLayout()
        topo.addWidget(self._rotulo("NOME DA IMPRESSORA"))
        topo.addStretch()
        self._contador = QLabel()
        self._contador.setObjectName("impDialogContador")
        topo.addWidget(self._contador)
        coluna.addLayout(topo)

        self._campo_nome = QLineEdit(self._retrato.nome)
        self._campo_nome.setObjectName("impDialogNome")
        self._campo_nome.setPlaceholderText("Ex.: Caixa 01, Cozinha, Bar")
        self._campo_nome.setFixedHeight(self.ALTURA_CAMPO_PX)
        self._campo_nome.setMaxLength(self._maximo_do_nome())
        self._campo_nome.textChanged.connect(self._ao_mudar_texto)
        coluna.addWidget(self._campo_nome)
        return coluna

    def _maximo_do_nome(self) -> int:
        """O teto, nunca menor que o nome que já está lá.

        `setMaxLength` CORTA o texto existente na hora em que é aplicado: abrir
        a edição de um nome cadastrado antes deste teto e devolvê-lo aparado
        seria perder dado sem dizer nada (a lição do §9.12).
        """
        return max(LIMITE_NOME, len(self._retrato.nome))

    def _montar_conexoes(self) -> QVBoxLayout:
        coluna = QVBoxLayout()
        coluna.setSpacing(8)
        coluna.addWidget(self._rotulo("TIPO DE CONEXÃO"))
        linha = QHBoxLayout()
        linha.setSpacing(10)
        for conexao in Conexao:
            card = _CartaoConexao(conexao)
            card.setFixedHeight(self.ALTURA_CONEXAO_PX)
            card.clicado.connect(self._conexao_clicada)
            linha.addWidget(card, 1)
            self._cards[conexao] = card
        coluna.addLayout(linha)
        return coluna

    def _montar_destino_e_uso(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(16)

        esquerda = QVBoxLayout()
        esquerda.setSpacing(8)
        self._rotulo_destino = self._rotulo(CONEXOES[self._conexao].rotulo_campo)
        esquerda.addWidget(self._rotulo_destino)

        self._campo_arquivo = QLineEdit(self._retrato.caminho_arquivo)
        self._campo_arquivo.setObjectName("impDialogCampo")
        self._campo_arquivo.setPlaceholderText(CONEXOES[Conexao.ARQUIVO].placeholder)
        self._campo_arquivo.textChanged.connect(self._ao_mudar_texto)

        self._campo_local = _SeletorComSeta()
        self._campo_local.setObjectName("impDialogLocal")
        self._campo_local.setEditable(True)
        # O que se digita não vira item da lista: a lista é o que o Windows
        # disse que existe, e misturar os dois apagaria essa diferença.
        self._campo_local.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._campo_local.setToolTip(
            "Escolha a impressora instalada no Windows ou a porta COM.\n"
            "Também aceita digitar: COM3, ou vendor:product (0x04b8:0x0202) para USB direto."
        )
        self._campo_local.setEditText(self._retrato.destino_local)
        self._campo_local.editTextChanged.connect(self._ao_mudar_texto)

        self._campo_rede = QLineEdit(self._retrato.endereco_rede)
        self._campo_rede.setObjectName("impDialogCampo")
        self._campo_rede.setPlaceholderText(CONEXOES[Conexao.REDE].placeholder)
        self._campo_rede.textChanged.connect(self._ao_mudar_texto)

        self._pilha = QStackedWidget()
        self._pilha.setObjectName("impDialogPilha")
        self._pilha.setFixedHeight(self.ALTURA_CAMPO_PX)
        self._campos: dict[Conexao, QWidget] = {
            Conexao.ARQUIVO: self._campo_arquivo,
            Conexao.LOCAL: self._campo_local,
            Conexao.REDE: self._campo_rede,
        }
        for campo in self._campos.values():
            campo.setFixedHeight(self.ALTURA_CAMPO_PX)
            self._pilha.addWidget(campo)
        esquerda.addWidget(self._pilha)
        linha.addLayout(esquerda, 1)

        direita = QVBoxLayout()
        direita.setSpacing(8)
        direita.addWidget(self._rotulo("USO DA IMPRESSÃO"))
        self._uso = _SeletorComSeta()
        self._uso.setObjectName("impDialogUso")
        self._uso.setFixedHeight(self.ALTURA_CAMPO_PX)
        self._uso.addItem(USO_RECIBO, True)
        self._uso.addItem(USO_PRODUCAO, False)
        self._uso.setItemData(
            0,
            "Recebe o recibo do cliente, o fechamento de caixa e os itens de "
            "categorias sem impressora própria.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self._uso.setItemData(
            1,
            "Recebe só os itens das categorias marcadas para ela na tela de Impressoras.",
            Qt.ItemDataRole.ToolTipRole,
        )
        # `activated`, e não `currentIndexChanged`: só o gesto do gerente é
        # escolha. A troca que o interruptor força não pode ser lembrada como se
        # ele a tivesse feito.
        self._uso.activated.connect(self._uso_escolhido)
        direita.addWidget(self._uso)
        linha.addLayout(direita, 1)
        return linha

    def _botao_de_segmento(self, texto: str, nome: str) -> QPushButton:
        """Um botão dos seletores de bobina e de colunas, que têm o mesmo desenho."""
        botao = QPushButton(texto)
        botao.setObjectName(nome)
        botao.setProperty("selecionada", False)
        botao.setFixedHeight(self.ALTURA_CAMPO_PX)
        cartao_modal.preparar_botao(botao)
        return botao

    def _montar_bobina_e_colunas(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(16)

        esquerda = QVBoxLayout()
        esquerda.setSpacing(8)
        esquerda.addWidget(self._rotulo("LARGURA DA BOBINA"))
        botoes = QHBoxLayout()
        botoes.setSpacing(10)
        for bobina in Bobina:
            botao = self._botao_de_segmento(bobina.value, "impDialogBobina")
            botao.setProperty("bobina", bobina.value)
            botao.clicked.connect(self._bobina_clicada)
            botoes.addWidget(botao, 1)
            self._botoes_bobina[bobina] = botao
        esquerda.addLayout(botoes)
        linha.addLayout(esquerda, self.PESO_BOBINA)

        direita = QVBoxLayout()
        direita.setSpacing(8)
        topo = QHBoxLayout()
        topo.addWidget(self._rotulo("COLUNAS POR LINHA"))
        topo.addStretch()
        topo.addWidget(
            GlifoSolto(GLIFO_COLUNAS, self.LADO_GLIFO_ROTULO_PX, "impressora_opcao_ativa_glifo"),
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        direita.addLayout(topo)
        botoes = QHBoxLayout()
        botoes.setSpacing(8)
        for colunas in COLUNAS_POR_LINHA:
            botao = self._botao_de_segmento(str(colunas), "impDialogColunas")
            botao.setProperty("colunas", colunas)
            botao.setToolTip(_DICA_DAS_COLUNAS[colunas])
            botao.clicked.connect(self._colunas_clicadas)
            botoes.addWidget(botao, 1)
            self._botoes_colunas[colunas] = botao
        direita.addLayout(botoes)
        linha.addLayout(direita, self.PESO_COLUNAS)
        return linha

    def _montar_espessura_e_situacao(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(16)

        esquerda = QVBoxLayout()
        esquerda.setSpacing(8)
        topo = QHBoxLayout()
        topo.addWidget(self._rotulo("ESPESSURA DA LETRA"))
        topo.addStretch()
        # A etiqueta diz o que a escolha é: aparência do papel, e nada da
        # conexão, do uso ou do roteamento muda com ela.
        tag = QLabel(_TAG_AJUSTE_VISUAL)
        tag.setObjectName("impDialogTag")
        topo.addWidget(tag)
        esquerda.addLayout(topo)
        botoes = QHBoxLayout()
        botoes.setSpacing(10)
        for espessura in Espessura:
            opcao = _BotaoDeEspessura(espessura)
            opcao.setFixedHeight(self.ALTURA_CAMPO_PX)
            opcao.clicado.connect(self._espessura_clicada)
            botoes.addWidget(opcao, 1)
            self._botoes_espessura[espessura] = opcao
        esquerda.addLayout(botoes)
        linha.addLayout(esquerda, self.PESO_ESPESSURA)

        direita = QVBoxLayout()
        direita.setSpacing(8)
        direita.addWidget(self._rotulo("SITUAÇÃO"))
        self._situacao = _CartaoSituacao()
        self._situacao.setFixedHeight(self.ALTURA_CAMPO_PX)
        self._situacao.clicado.connect(self._situacao_clicada)
        direita.addWidget(self._situacao)
        linha.addLayout(direita, self.PESO_SITUACAO)
        return linha

    def _montar_resumo(self) -> QFrame:
        painel = QFrame()
        painel.setObjectName("impDialogResumo")
        linha = QHBoxLayout(painel)
        linha.setContentsMargins(14, 12, 16, 12)
        linha.setSpacing(12)

        icone = QFrame()
        icone.setObjectName("impDialogResumoIcone")
        icone.setFixedSize(self.LADO_ICONE_RESUMO_PX, self.LADO_ICONE_RESUMO_PX)
        dentro = QHBoxLayout(icone)
        dentro.setContentsMargins(0, 0, 0, 0)
        dentro.addWidget(
            GlifoSolto(GLIFO_IMPRESSORA, 18, "impressora_badge_glifo"),
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        linha.addWidget(icone, 0, Qt.AlignmentFlag.AlignTop)

        textos = QVBoxLayout()
        textos.setSpacing(3)
        self._rotulo_resumo = QLabel(_ROTULO_RESUMO)
        self._rotulo_resumo.setObjectName("impDialogResumoRotulo")
        self._rotulo_resumo.setProperty("estado", "resumo")
        textos.addWidget(self._rotulo_resumo)
        self._resumo = RotuloComReticencias()
        self._resumo.setObjectName("impDialogResumoTexto")
        textos.addWidget(self._resumo)
        # O erro do service é frase inteira ("Já existe uma impressora com o
        # nome..."), e cortá-la com reticências pediria ao gerente para corrigir
        # o que ele não leu. Por isso uma linha própria, que quebra — e que só
        # existe enquanto há erro.
        self._erro_servico = QLabel()
        self._erro_servico.setObjectName("impDialogErroServico")
        self._erro_servico.setWordWrap(True)
        self._erro_servico.setVisible(False)
        textos.addWidget(self._erro_servico)
        linha.addLayout(textos, 1)

        self._status = QLabel()
        self._status.setObjectName("impDialogStatus")
        self._status.setProperty("estado", "ok")
        self._status.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        linha.addWidget(self._status, 0, Qt.AlignmentFlag.AlignVCenter)
        return painel

    def _montar_rodape(self, frases: _Modo) -> QWidget:
        faixa = QWidget()
        faixa.setObjectName("impDialogRodape")
        linha = QHBoxLayout(faixa)
        linha.setContentsMargins(24, 14, 20, 16)
        linha.setSpacing(12)

        atalhos = QLabel("ESC PARA FECHAR")
        atalhos.setObjectName("impDialogAtalhos")
        linha.addWidget(atalhos)
        linha.addStretch()

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setObjectName("impDialogCancelar")
        cartao_modal.preparar_botao(self._botao_cancelar)
        self._botao_cancelar.clicked.connect(self.reject)
        linha.addWidget(self._botao_cancelar)

        self._botao_confirmar = BotaoComGlifo(
            frases.botao, frases.glifo_botao, "acento_texto", "pilula_disabled_texto"
        )
        self._botao_confirmar.setObjectName("impDialogConfirmar")
        cartao_modal.preparar_botao(self._botao_confirmar)
        self._botao_confirmar.clicked.connect(self._confirmar)
        linha.addWidget(self._botao_confirmar)
        return faixa

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def _conexao_clicada(self) -> None:
        card = self.sender()
        if not isinstance(card, _CartaoConexao) or card.conexao is self._conexao:
            return
        self._conexao = card.conexao
        self._pintar_conexao()
        self._atualizar()

    def _pintar_conexao(self) -> None:
        for conexao, card in self._cards.items():
            card.selecionar(conexao is self._conexao)
        self._rotulo_destino.setText(CONEXOES[self._conexao].rotulo_campo)
        self._pilha.setCurrentWidget(self._campos[self._conexao])

    def _bobina_clicada(self) -> None:
        """Troca a bobina e SUGERE as colunas dela — a de antes fica lembrada.

        Clicar a bobina que já estava escolhida guarda e devolve as mesmas
        colunas: não troca nada, sem precisar de um `if` para isso (a checagem
        por mutação mostrou o `if` redundante, e ele saiu).
        """
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        bobina = Bobina(str(botao.property("bobina")))
        self._colunas_da_bobina[self._bobina] = self._colunas
        self._bobina = bobina
        self._colunas = self._colunas_da_bobina[bobina]
        self._pintar_bobina()
        self._pintar_colunas()
        self._atualizar()

    def _pintar_bobina(self) -> None:
        for bobina, botao in self._botoes_bobina.items():
            selecionada = bobina is self._bobina
            if botao.property("selecionada") != selecionada:
                aplicar_propriedade(botao, "selecionada", selecionada)

    def _colunas_clicadas(self) -> None:
        """Qualquer largura em qualquer bobina: é a liberdade que o pedido deu."""
        botao = self.sender()
        if not isinstance(botao, QPushButton):
            return
        self._colunas = int(botao.property("colunas"))
        self._pintar_colunas()
        self._atualizar()

    def _pintar_colunas(self) -> None:
        # Uma largura antiga fora do seletor (42) acende botão nenhum, e volta
        # intacta: o resumo diz "42 col." e só um clique a troca.
        for colunas, botao in self._botoes_colunas.items():
            selecionada = colunas == self._colunas
            if botao.property("selecionada") != selecionada:
                aplicar_propriedade(botao, "selecionada", selecionada)

    def _espessura_clicada(self) -> None:
        opcao = self.sender()
        if not isinstance(opcao, _BotaoDeEspessura):
            return
        self._letra_grossa = opcao.espessura is Espessura.GROSSA
        self._pintar_espessura()
        self._atualizar()

    def _espessura(self) -> Espessura:
        return Espessura.GROSSA if self._letra_grossa else Espessura.FINA

    def _pintar_espessura(self) -> None:
        escolhida = self._espessura()
        for espessura, opcao in self._botoes_espessura.items():
            opcao.selecionar(espessura is escolhida)

    def _situacao_clicada(self) -> None:
        self._ativa = not self._ativa
        self._pintar_situacao()
        self._atualizar()

    def _pintar_situacao(self) -> None:
        """O interruptor, e o que ele obriga no seletor de uso.

        Impressora desligada nunca é a do recibo (`CardapioService._aplicar_uso`).
        A tela diz isso ANTES de salvar: a opção "Recibo do cliente" fica
        desligada e o seletor mostra "Produção" enquanto o interruptor estiver
        desligado. Religar devolve a escolha que o gerente tinha feito.
        """
        self._situacao.definir(self._ativa)
        item_recibo = self._uso.model().item(0)
        item_recibo.setEnabled(self._ativa)
        indice = 0 if self._padrao_final() else 1
        if self._uso.currentIndex() != indice:
            self._uso.setCurrentIndex(indice)
        self._uso.setToolTip(
            "" if self._ativa else "Impressora desativada não recebe o recibo do cliente."
        )

    def _uso_escolhido(self, indice: int) -> None:
        self._recibo_escolhido = bool(self._uso.itemData(indice))
        self._atualizar()

    def _padrao_final(self) -> bool:
        return self._ativa and self._recibo_escolhido

    def _ao_mudar_texto(self, _texto: str = "") -> None:
        self._atualizar()

    def _leitura_da_conexao(self) -> LeituraDaConexao:
        if self._conexao is Conexao.ARQUIVO:
            return ler_caminho_de_arquivo(self._campo_arquivo.text())
        if self._conexao is Conexao.REDE:
            return ler_endereco_de_rede(self._campo_rede.text())
        return ler_destino_local(
            self._campo_local.currentText(), self._destinos, self._retrato.baudrate
        )

    def _atualizar(self) -> None:
        """Resumo, contador, veredito e botão — tudo a partir do estado atual.

        Uma rotina só para toda mudança: tecla, card, bobina, colunas,
        espessura, interruptor, uso e a lista do Windows chegando. Oito caminhos
        de atualização separados seriam oito chances de o resumo contradizer o
        botão.
        """
        texto = self._campo_nome.text()
        nome = _texto_aparado(texto)
        self._contador.setText(f"{len(texto)}/{LIMITE_NOME}")
        self._esconder_erro_servico()
        self._resumo.setText(self._texto_do_resumo(nome))
        mensagem, estado = self._veredito(nome, self._leitura_da_conexao())
        self._dizer_status(mensagem, estado)
        self._botao_confirmar.setEnabled(estado in ("ok", "aviso"))

    def _texto_do_resumo(self, nome: str) -> str:
        """`Caixa 01 · USB · 80mm · 80 col. · letra grossa` — o exemplo do pedido."""
        return " · ".join(
            (
                nome or _SEM_NOME,
                CONEXOES[self._conexao].titulo,
                self._bobina.value,
                f"{self._colunas} col.",
                ESPESSURAS[self._espessura()].no_resumo,
            )
        )

    def _veredito(self, nome: str, leitura: LeituraDaConexao) -> tuple[str, str]:
        """A primeira coisa que falta ou está errada, na ordem em que a tela é lida.

        Estados: `ok` (nada a dizer), `pendente` (falta preencher, sem
        vermelho), `erro` (preenchido errado) e `aviso` (salva, mas o gerente
        precisa saber de algo).
        """
        if not nome:
            return _STATUS_FALTA_NOME, "pendente"
        if len(nome) < MINIMO_NOME:
            return _STATUS_NOME_CURTO, "pendente"
        if nome in self._nomes_ocupados:
            # O nome EXATO, que é o que `_exigir_nome_de_impressora_livre`
            # compara (`Impressora.nome == nome`). Barrar "caixa 01" com "Caixa
            # 01" cadastrada seria um botão desligado por uma regra que o service
            # não tem (o achado do §9.12).
            return _STATUS_NOME_REPETIDO, "erro"
        if leitura.tipo is None:
            return leitura.problema, "erro" if leitura.grave else "pendente"
        if not self._padrao_final() and not self._outra_padrao_ativa:
            return _STATUS_SEM_RECIBO, "aviso"
        return "", "ok"

    def _dizer_status(self, mensagem: str, estado: str) -> None:
        self._status.setText(mensagem)
        if self._status.property("estado") != estado:
            aplicar_propriedade(self._status, "estado", estado)
        self._status.setToolTip(
            "O recibo do cliente e o fechamento de caixa não vão imprimir até "
            "alguma impressora ativa ser marcada como \"Recibo do cliente\"."
            if estado == "aviso"
            else ""
        )

    def mostrar_erro_servico(self, mensagem: str) -> None:
        """Erro do service, sem fechar o cartão nem perder nada do que foi escolhido."""
        self._rotulo_resumo.setText(_ROTULO_ERRO_SERVICO)
        aplicar_propriedade(self._rotulo_resumo, "estado", "erro")
        self._erro_servico.setText(mensagem)
        self._erro_servico.setVisible(True)
        self._dar_altura_ao_erro()
        self._reacomodar()
        self._campo_nome.setFocus(Qt.FocusReason.OtherFocusReason)

    def _dar_altura_ao_erro(self) -> None:
        """A altura das linhas que o erro TEM, e não a de uma.

        `setWordWrap` quebra o texto, mas quem dá a altura é o `adjustSize()`
        do diálogo, que lê `sizeHint` e não `heightForWidth`: no cartão do
        §9.19 o rótulo ficava com 20px e a mensagem longa saía cortada na
        primeira linha (medido: pedia 64px). A largura é a do resumo, que mora
        na mesma coluna e já está desenhado; a fonte, a do próprio rótulo
        depois do QSS (§9.8).
        """
        largura = self._resumo.width()
        if largura <= 0:  # pragma: no cover - o cartão só mostra erro depois de aberto
            return
        self._erro_servico.ensurePolished()
        self._erro_servico.setMinimumHeight(self._erro_servico.heightForWidth(largura))

    def _esconder_erro_servico(self) -> None:
        # Qualquer mudança apaga o erro: ele falava do formulário anterior, e
        # deixá-lo aceso enquanto se corrige é o aviso contradizendo a tela.
        if not self._erro_servico.isVisible() and self._erro_servico.text() == "":
            return
        self._erro_servico.setText("")
        self._erro_servico.setVisible(False)
        self._erro_servico.setMinimumHeight(0)
        self._rotulo_resumo.setText(_ROTULO_RESUMO)
        aplicar_propriedade(self._rotulo_resumo, "estado", "resumo")
        self._reacomodar()

    def _reacomodar(self) -> None:
        """O cartão do tamanho do que ele mostra AGORA, com ou sem a linha do erro.

        O `adjustSize()` sozinho lia a altura antiga: o rótulo do erro mora
        quatro widgets abaixo do diálogo, cada um com o seu layout, e o `hide`
        só chega a eles num `LayoutRequest` posterior. Depois de o erro sumir, o
        cartão ficava com um vão em branco onde ele esteve (medido no §9.19
        também). O `activate()` do layout do diálogo não desce aos aninhados, e
        o `sendPostedEvents` também não resolveu (medido); ativar de dentro para
        fora resolve.
        """
        widget = self._erro_servico.parentWidget()
        while widget is not None:
            layout = widget.layout()
            if layout is not None:
                layout.activate()
            if widget is self:
                break
            widget = widget.parentWidget()
        self.adjustSize()

    def _confirmar(self) -> None:
        if not self._botao_confirmar.isEnabled():
            return
        if self._salvar is None:
            self.accept()
            return
        erro = self._salvar(self.resultado())
        if erro:
            self.mostrar_erro_servico(erro)
            return
        self.accept()

    def resultado(self) -> DadosImpressora:
        """O formulário inteiro. Lido pela função `salvar`, ou depois do `exec()`."""
        leitura = self._leitura_da_conexao()
        # Sem tipo, o campo está incompleto e o botão desligado — quem chegar
        # aqui assim (um teste) leva o tipo do card, e o service recusa com a
        # mensagem dele.
        tipo = leitura.tipo or {
            Conexao.ARQUIVO: TipoConexaoImpressora.ARQUIVO,
            Conexao.LOCAL: TipoConexaoImpressora.WINDOWS,
            Conexao.REDE: TipoConexaoImpressora.REDE,
        }[self._conexao]
        return DadosImpressora(
            nome=_texto_aparado(self._campo_nome.text()),
            tipo_conexao=tipo,
            # As colunas saem do estado, e não de uma conta sobre a bobina: uma
            # largura antiga sem botão (42) volta INTACTA para quem só foi
            # trocar o nome, porque nada a tocou.
            colunas=self._colunas,
            bobina_mm=self._bobina.mm,
            letra_grossa=self._letra_grossa,
            ativa=self._ativa,
            padrao=self._padrao_final(),
            **leitura.parametros,  # type: ignore[arg-type]
        )

    # ------------------------------------------------------------------
    # A lista do Windows
    # ------------------------------------------------------------------

    def _iniciar_busca(self) -> None:
        """Uma busca por cartão, na primeira vez que ele aparece.

        O `showEvent` roda de novo quando a janela é restaurada; uma segunda
        thread ali perguntaria ao spooler o que ele já respondeu.
        """
        if self._busca is not None or self._listar_destinos is None:
            return
        self._busca = _BuscaDeDestinos(self._listar_destinos)
        self._busca.iniciar()
        self._relogio.start()

    def _conferir_busca(self) -> None:
        busca = self._busca
        if busca is None:
            self._relogio.stop()
            return
        destinos = busca.resultado()
        if destinos is None:
            if busca.esgotou(TETO_DA_BUSCA_S):
                self._relogio.stop()
                self._estado_da_busca = "esgotou"
                self._pintar_placeholder_local()
            return
        self._relogio.stop()
        self._estado_da_busca = "pronta"
        self._preencher_destinos(destinos)

    def _preencher_destinos(self, destinos: Sequence[DestinoLocal]) -> None:
        """Monta a lista sem mexer no que já está escrito no campo.

        Num `QComboBox` editável, o primeiro `addItem` vira o item atual e
        TROCA o texto do campo — a edição de uma impressora `COM3` abriria com
        o nome da primeira fila do Windows no lugar. Por isso o texto é guardado
        antes e devolvido depois, com os sinais calados no meio.
        """
        texto = self._campo_local.currentText()
        self._destinos = {destino.valor.casefold(): destino for destino in destinos}
        modelo = self._campo_local.model()
        grupos = (
            (TipoConexaoImpressora.WINDOWS.value, _CABECALHO_FILAS),
            (TipoConexaoImpressora.SERIAL.value, _CABECALHO_PORTAS),
        )
        self._campo_local.blockSignals(True)
        try:
            self._campo_local.clear()
            for tipo, cabecalho in grupos:
                do_grupo = [destino for destino in destinos if destino.tipo == tipo]
                if not do_grupo:
                    continue
                self._campo_local.addItem(cabecalho)
                # Cabeçalho é legenda, não opção: nem clicável nem alcançável
                # pelas setas.
                modelo.item(self._campo_local.count() - 1).setEnabled(False)
                for destino in do_grupo:
                    self._campo_local.addItem(destino.valor)
                    self._campo_local.setItemData(
                        self._campo_local.count() - 1, destino.detalhe, Qt.ItemDataRole.ToolTipRole
                    )
            self._campo_local.setCurrentIndex(-1)
            self._campo_local.setEditText(texto)
        finally:
            self._campo_local.blockSignals(False)
        self._pintar_placeholder_local()
        self._atualizar()

    def _pintar_placeholder_local(self) -> None:
        campo = self._campo_local.lineEdit()
        if campo is None:  # pragma: no cover - o seletor é editável desde a montagem
            return
        if self._estado_da_busca == "procurando":
            campo.setPlaceholderText(_PROCURANDO)
        elif self._destinos:
            campo.setPlaceholderText(_ESCOLHA)
        else:
            campo.setPlaceholderText(_NENHUMA)

    # ------------------------------------------------------------------
    # Overrides do Qt
    # ------------------------------------------------------------------

    @nao_deixa_escapar()
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (override Qt)
        """O `Enter` grava, e só quando há o que gravar.

        Os campos ignoram o Return e ele sobe até aqui — ligar `returnPressed`
        ALÉM disto seria o cadastro enviado duas vezes com um Enter só (§9.4).
        O Esc cai no `super()`: lá o `QDialog` o traduz em `reject()`, que passa
        por `done()` e pela mesma limpeza dos outros caminhos de saída. Com a
        lista do seletor aberta, Enter e Esc são dela e nem chegam aqui.
        """
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._confirmar()
            return
        super().keyPressEvent(event)

    @nao_deixa_escapar()
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (override Qt)
        super().showEvent(event)
        self._backdrop = cartao_modal.apresentar(self, self._backdrop)
        self._iniciar_busca()
        self._campo_nome.setFocus(Qt.FocusReason.OtherFocusReason)

    @nao_deixa_escapar()
    def setVisible(self, visible: bool) -> None:  # noqa: N802 (override Qt)
        """Cursor no fim do nome, e nada selecionado, quando o cartão aparece.

        Não dá para fazer isso no `showEvent`: depois dele o próprio
        `QDialog::setVisible` manda ao campo em foco um `FocusIn` sintético "de
        Tab", e o `QLineEdit` responde a Tab selecionando tudo (medido numa
        sonda). Na edição, quem abriu quase sempre veio trocar a conexão, e um
        nome todo selecionado some na primeira tecla que escapar para o campo.
        `end(False)` faz as duas coisas: leva o cursor ao fim e, com `False`,
        desfaz a seleção (a checagem por mutação mostrou que um `deselect()` ao
        lado dele não mudava nada).
        """
        super().setVisible(visible)
        if visible:
            self._campo_nome.end(False)

    @nao_deixa_escapar()
    def done(self, resultado: int) -> None:  # noqa: N802 (override Qt)
        """A saída única: Salvar, Cancelar, o ✕ e o Esc passam todos por aqui
        (`done()` faz `hide()`, não `close()`, §3.9)."""
        self._soltar_recursos()
        super().done(resultado)

    def _soltar_recursos(self) -> None:
        """Desliga o que este cartão ligou — e só uma vez.

        * o **relógio** da busca, parado e desconectado: é a única coisa do
          cartão que acorda sozinha;
        * a **busca**, solta: a thread segue até o Windows responder e morre
          sozinha, sem nada do cartão para alcançar;
        * as **ligações de sinal**, desconectadas nominalmente — elas morreriam
          com os filhos, e explicitá-las é o que impede uma ligação a um objeto
          de FORA do cartão de entrar um dia sem ninguém notar;
        * o **escurecedor**, que é filho da JANELA e o Qt não recolheria junto;
        * as quatro tabelas de widgets (cards, bobina, colunas e espessura).

        A trava `_limpo` é a do §9.12: o segundo `disconnect` desta versão do
        PySide6 não levanta, imprime `RuntimeWarning` — um por ligação e por
        fechamento, o aviso que ensina a não ler avisos.
        """
        if self._limpo:
            return
        self._limpo = True
        self._relogio.stop()
        self._relogio.timeout.disconnect(self._conferir_busca)
        self._busca = None
        self._campo_nome.textChanged.disconnect(self._ao_mudar_texto)
        self._campo_arquivo.textChanged.disconnect(self._ao_mudar_texto)
        self._campo_local.editTextChanged.disconnect(self._ao_mudar_texto)
        self._campo_rede.textChanged.disconnect(self._ao_mudar_texto)
        self._uso.activated.disconnect(self._uso_escolhido)
        for card in self._cards.values():
            card.clicado.disconnect(self._conexao_clicada)
        for botao in self._botoes_bobina.values():
            botao.clicked.disconnect(self._bobina_clicada)
        for botao in self._botoes_colunas.values():
            botao.clicked.disconnect(self._colunas_clicadas)
        for opcao in self._botoes_espessura.values():
            opcao.clicado.disconnect(self._espessura_clicada)
        self._situacao.clicado.disconnect(self._situacao_clicada)
        self._botao_fechar.clicked.disconnect(self.reject)
        self._botao_cancelar.clicked.disconnect(self.reject)
        self._botao_confirmar.clicked.disconnect(self._confirmar)
        self._cards.clear()
        self._botoes_bobina.clear()
        self._botoes_colunas.clear()
        self._botoes_espessura.clear()
        backdrop, self._backdrop = self._backdrop, None
        cartao_modal.descartar(backdrop)
