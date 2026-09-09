"""Guarda um segredo de um jeito que dá para LER de volta — e diz o preço disso.

## Por que isto existe

A cascata de 3 níveis (§3.13) nasceu com uma regra explícita: nenhum segredo é
recuperável, só hash+salt, e "ver o valor" não é uma operação que existe. Isso
continua sendo o certo para AUTENTICAR — quem confere se o PIN digitado bate é
sempre o hash, e nada aqui muda isso.

O que mudou foi o pedido: o Vitor quer poder **conferir** a senha que ele
mesmo cadastrou, com o CPF do Dono como chave, porque quem esquece a Senha
Master hoje não tem para onde ir — o único caminho é o próprio CPF, que também
é a credencial para trocá-la. Hash não devolve valor, então uma segunda cópia
precisa existir.

## O que este módulo protege, e o que NÃO protege

Protege contra **leitura casual do banco**: abrir o `.db` num navegador de
SQLite e enxergar a senha do caixa numa coluna. O que sai gravado é ruído em
Base64.

**Não** protege contra quem tem o arquivo do banco E o programa. A chave mora
no mesmo banco (`preferencias.chave_de_exibicao`), porque tem que estar ao
alcance do app sozinho — não há servidor, não há login de sistema operacional
no meio e o backup é uma cópia do `.db` (`repository/backup.py`), então uma
chave guardada fora dele tornaria todo backup restaurado ilegível. Chamar isto
de criptografia forte seria mentira: é **ofuscação em repouso**, e a barreira
de verdade é a exigência do CPF do Dono na tela (`LojaConfigService.revelar`).

Na prática do food truck isso está dimensionado: as senhas são de 4 a 8 dígitos
NUMÉRICOS, e um ataque offline percorre esse espaço inteiro em segundos contra
o hash — com ou sem este módulo. Quem quiser subir a barra troca o modelo de
senha, não a cifra.

## Como funciona

Cifra de fluxo com o material que a biblioteca padrão já traz (nenhuma
dependência nova, o que importa para o `.exe` do PyInstaller): a chave e um
nonce aleatório alimentam blocos de `HMAC-SHA256` que formam o fluxo, e o texto
é combinado com ele por XOR. Depois vem o selo (`encrypt-then-MAC`): um HMAC
sobre o que saiu, conferido ANTES de decifrar. Sem o selo, um byte trocado no
banco viraria uma senha diferente exibida como se fosse a verdadeira — e é
melhor dizer "não consegui ler" do que mostrar lixo com cara de segredo.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

TAMANHO_CHAVE_BYTES = 32
TAMANHO_NONCE_BYTES = 16
TAMANHO_SELO_BYTES = 16
_BLOCO = hashlib.sha256().digest_size

# Rótulos de domínio: o mesmo par (chave, nonce) gera dois materiais diferentes
# — o fluxo que embaralha e o selo que confere. Sem separar, o selo seria um
# pedaço do próprio fluxo e entregaria bytes dele de graça.
_ROTULO_FLUXO = b"fluxo"
_ROTULO_SELO = b"selo"


def gerar_chave() -> str:
    """Uma chave nova, em Base64. Gerada uma vez por instalação."""
    return base64.b64encode(os.urandom(TAMANHO_CHAVE_BYTES)).decode()


def _fluxo(chave: bytes, nonce: bytes, tamanho: int) -> bytes:
    """`tamanho` bytes de fluxo, em blocos numerados (o contador do modo CTR)."""
    saida = bytearray()
    contador = 0
    while len(saida) < tamanho:
        bloco = hmac.new(
            chave,
            _ROTULO_FLUXO + nonce + contador.to_bytes(4, "big"),
            hashlib.sha256,
        ).digest()
        saida.extend(bloco)
        contador += 1
    return bytes(saida[:tamanho])


def _selar(chave: bytes, nonce: bytes, cifrado: bytes) -> bytes:
    return hmac.new(chave, _ROTULO_SELO + nonce + cifrado, hashlib.sha256).digest()[
        :TAMANHO_SELO_BYTES
    ]


def cifrar(valor: str, chave: str) -> str:
    """Embaralha `valor` com `chave` e devolve `nonce + selo + cifrado` em Base64.

    Nonce novo a cada chamada, e é o que importa: sem ele, cifrar a mesma senha
    duas vezes daria o mesmo texto, e quem olhasse o banco saberia que a Senha
    de Login e a Operacional são iguais sem precisar decifrar nenhuma.
    """
    chave_bytes = base64.b64decode(chave)
    nonce = os.urandom(TAMANHO_NONCE_BYTES)
    claro = valor.encode("utf-8")
    cifrado = bytes(a ^ b for a, b in zip(claro, _fluxo(chave_bytes, nonce, len(claro))))
    return base64.b64encode(nonce + _selar(chave_bytes, nonce, cifrado) + cifrado).decode()


def decifrar(texto: str, chave: str) -> str | None:
    """O valor original, ou `None` quando não dá para afirmar que é ele.

    `None` cobre tudo que não é um texto íntegro cifrado com esta chave: Base64
    quebrado, curto demais, selo que não confere (banco adulterado ou chave
    trocada) e bytes que não formam UTF-8. Nunca levanta: quem chama é uma tela
    que precisa dizer "não consegui recuperar este valor" e seguir viva, e um
    estouro dentro de um slot de clique evapora sem mensagem (ver
    `core/resilience.py`).
    """
    if not isinstance(texto, str) or not texto:
        return None
    try:
        chave_bytes = base64.b64decode(chave)
        bruto = base64.b64decode(texto, validate=True)
    except (ValueError, TypeError):
        return None

    cabecalho = TAMANHO_NONCE_BYTES + TAMANHO_SELO_BYTES
    if len(bruto) < cabecalho:
        return None
    nonce = bruto[:TAMANHO_NONCE_BYTES]
    selo = bruto[TAMANHO_NONCE_BYTES:cabecalho]
    cifrado = bruto[cabecalho:]

    # `compare_digest` e não `==`: o tempo da comparação não pode contar quantos
    # bytes do selo já bateram.
    if not hmac.compare_digest(selo, _selar(chave_bytes, nonce, cifrado)):
        return None
    claro = bytes(a ^ b for a, b in zip(cifrado, _fluxo(chave_bytes, nonce, len(cifrado))))
    try:
        return claro.decode("utf-8")
    except UnicodeDecodeError:
        return None
