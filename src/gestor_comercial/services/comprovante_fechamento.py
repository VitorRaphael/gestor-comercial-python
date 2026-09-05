"""Comprovante digital de fechamento de caixa (tela de Relatórios).

Monta o MESMO tipo de documento que `ImpressaoService._documento_fechamento`
manda para a bobina térmica (`BlocoTexto`/`formatador_cupom`, mesma
aritmética de colunas), só que com seções que o cupom físico não tem:
conferência de pagamento por forma (Esperado x Conferido x Diferença) e
produtos agrupados por Categoria. Existe separado do `ImpressaoService`
porque este documento nunca vai para uma impressora — só para a tela e para
exportação em `.txt` — então não depende de `Impressora` nem de
`abrir_driver`.

Módulo puro: só recebe os dataclasses que `CaixaService` já expõe e devolve
`Documento`/texto. Nada aqui abre banco nem toca hardware.
"""

from __future__ import annotations

import textwrap
from datetime import datetime

from gestor_comercial.domain.caixa import Caixa
from gestor_comercial.domain.enums import StatusCaixa, TipoMovimento
from gestor_comercial.domain.movimento_caixa import MovimentoCaixa
from gestor_comercial.hardware.impressora_escpos import BlocoTexto, Documento
from gestor_comercial.services import formatador_cupom as cupom
from gestor_comercial.services.caixa_service import (
    GrupoVendaCategoria,
    LinhaConferenciaPagamento,
    ResumoCaixa,
    periodo_do_turno,
)
from gestor_comercial.services.dinheiro import ZERO, dinheiro

# 48 colunas = bobina de 80mm, a referência visual do comprovante digital.
# Não vem de `Impressora.colunas` de propósito: este documento nunca é
# impresso, e usar sempre a mesma largura mantém a tela e o .txt exportado
# estáveis, independente de qual impressora está cadastrada no sistema.
LARGURA_PADRAO = 48


def montar_documento(
    *,
    caixa: Caixa,
    titulo_fechamento: str | None,
    resumo: ResumoCaixa,
    conferencia: list[LinhaConferenciaPagamento],
    grupos_categoria: list[GrupoVendaCategoria],
    movimentos: list[MovimentoCaixa],
    conferido_por: str,
    agora: datetime,
    largura: int = LARGURA_PADRAO,
) -> Documento:
    """Roteiro completo do comprovante digital, na ordem em que aparece na tela."""
    documento: Documento = [
        BlocoTexto("COMPROVANTE DE FECHAMENTO DE CAIXA", negrito=True, centralizado=True)
    ]
    if titulo_fechamento:
        documento.append(BlocoTexto(titulo_fechamento, centralizado=True))
    # §3.1: o cupom identifica a GAVETA/turno pelo período em que abriu — não
    # pelo id interno nem por quem operou — mesmo raciocínio de
    # `CaixaService.identificacao_turno` (duplicado aqui, função pura, para
    # este módulo não precisar de uma instância de `CaixaService` só por isso).
    documento.append(BlocoTexto(f"Caixa Turno - {periodo_do_turno(caixa.aberto_em)}", centralizado=True))
    documento.extend([
        BlocoTexto(cupom.duas_colunas("Aberto em", cupom.data_hora(caixa.aberto_em), largura)),
        BlocoTexto(
            cupom.duas_colunas(
                "Fechado em",
                cupom.data_hora(caixa.fechado_em) if caixa.fechado_em else "em aberto",
                largura,
            )
        ),
    ])
    if caixa.aberto_por is not None:
        for linha in cupom.quebrar(f"Aberto por: {caixa.aberto_por.nome}", largura):
            documento.append(BlocoTexto(linha))
    if caixa.fechado_por is not None:
        for linha in cupom.quebrar(f"Fechado por: {caixa.fechado_por.nome}", largura):
            documento.append(BlocoTexto(linha))

    documento.extend(_secao_conferencia(conferencia, largura))
    documento.extend(_secao_produtos(grupos_categoria, largura))
    documento.extend(_secao_entradas(caixa, movimentos, largura))
    documento.extend(_secao_saidas(movimentos, largura))

    documento.append(BlocoTexto(cupom.separador(largura)))
    situacao = "FECHADO" if caixa.status is StatusCaixa.FECHADO else "ABERTO"
    documento.append(BlocoTexto(cupom.duas_colunas("Situação", situacao, largura)))
    documento.append(BlocoTexto(cupom.duas_colunas("Emitido em", cupom.data_hora(agora), largura)))
    for linha in cupom.quebrar(f"Conferido por: {conferido_por}", largura):
        documento.append(BlocoTexto(linha))
    return documento


def _secao_conferencia(linhas: list[LinhaConferenciaPagamento], largura: int) -> Documento:
    documento: Documento = [BlocoTexto(cupom.separador(largura, titulo="CONFERÊNCIA DE PAGAMENTOS"))]
    for linha in linhas:
        negrito = linha.forma is None  # linha "Total" em destaque
        documento.append(BlocoTexto(cupom.linha_de_valor(linha.rotulo, linha.esperado, largura), negrito=negrito))
        conferido_txt = "—" if linha.conferido is None else f"R$ {cupom.moeda(linha.conferido)}"
        diferenca_txt = "—" if linha.diferenca is None else f"R$ {cupom.moeda(linha.diferenca)}"
        documento.append(BlocoTexto(cupom.duas_colunas("  Conferido", conferido_txt, largura)))
        documento.append(BlocoTexto(cupom.duas_colunas("  Diferença", diferenca_txt, largura), negrito=negrito))
    return documento


def _secao_produtos(grupos: list[GrupoVendaCategoria], largura: int) -> Documento:
    documento: Documento = [BlocoTexto(cupom.separador(largura, titulo="PRODUTOS VENDIDOS"))]

    if not grupos:
        for linha in cupom.quebrar("Nenhum item vendido neste turno.", largura):
            documento.append(BlocoTexto(linha))
        return documento

    quantidade_geral = 0
    valor_geral = ZERO
    for grupo in grupos:
        documento.append(
            BlocoTexto(
                cupom.duas_colunas(
                    grupo.categoria_nome,
                    f"{grupo.quantidade_total} un | R$ {cupom.moeda(grupo.valor_total)}",
                    largura,
                ),
                negrito=True,
            )
        )
        for item in grupo.itens:
            for linha in cupom.linha_de_item(item.quantidade, item.produto_nome, largura, item.valor_total):
                documento.append(BlocoTexto(linha))
        quantidade_geral += grupo.quantidade_total
        valor_geral = dinheiro(valor_geral + grupo.valor_total)

    documento.append(BlocoTexto(cupom.separador(largura, caractere=".")))
    documento.append(
        BlocoTexto(
            cupom.duas_colunas(
                "TOTAL GERAL DE PRODUTOS",
                f"{quantidade_geral} un | R$ {cupom.moeda(valor_geral)}",
                largura,
            ),
            negrito=True,
        )
    )
    return documento


def _secao_entradas(caixa: Caixa, movimentos: list[MovimentoCaixa], largura: int) -> Documento:
    reforcos = [m for m in movimentos if m.tipo is TipoMovimento.REFORCO]
    documento: Documento = [BlocoTexto(cupom.separador(largura, titulo="ENTRADAS E SUPRIMENTOS"))]
    documento.append(
        BlocoTexto(cupom.linha_de_valor("Fundo de Caixa (abertura)", caixa.valor_abertura, largura))
    )
    for movimento in reforcos:
        motivo = movimento.descricao or "Reforço de caixa"
        for linha in cupom.linha_de_item(1, motivo, largura, movimento.valor):
            documento.append(BlocoTexto(linha))
    return documento


def _secao_saidas(movimentos: list[MovimentoCaixa], largura: int) -> Documento:
    saidas = [m for m in movimentos if m.tipo in (TipoMovimento.SANGRIA, TipoMovimento.DESPESA)]
    documento: Documento = [BlocoTexto(cupom.separador(largura, titulo="PAGAMENTOS / SANGRIAS"))]
    if not saidas:
        for linha in cupom.quebrar("Nenhuma sangria ou pagamento neste turno.", largura):
            documento.append(BlocoTexto(linha))
        return documento
    for movimento in saidas:
        descricao = movimento.descricao or (
            "Sangria" if movimento.tipo is TipoMovimento.SANGRIA else "Pagamento de conta"
        )
        documento.extend(
            BlocoTexto(linha)
            for linha in cupom.linha_de_item(1, descricao, largura, -dinheiro(movimento.valor))
        )
    return documento


def renderizar_texto(documento: Documento, largura: int = LARGURA_PADRAO) -> str:
    """Documento -> texto monoespaçado, para a tela e para o `.txt` exportado.

    Mesma convenção visual do modo ARQUIVO da impressora (`_DriverArquivo`):
    negrito vira MAIÚSCULA, centralizado centraliza dentro da largura. Não
    reaproveita o renderer de `hardware/` diretamente porque aquele é privado
    e amarrado à escrita em arquivo (append, cabeçalho de impressora); aqui o
    resultado é uma string só, para exibir num widget Qt.
    """
    linhas: list[str] = []
    for bloco in documento:
        texto = bloco.texto.upper() if bloco.negrito else bloco.texto
        if not texto.strip():
            linhas.append("")
            continue
        # `textwrap.wrap` puro (sem normalizar espaços): as linhas que chegam
        # aqui já vêm alinhadas por `formatador_cupom` (espaços múltiplos são
        # o preenchimento entre rótulo e valor) — usar `cupom.quebrar` as
        # destruiria, porque ele colapsa espaço repetido antes de quebrar.
        for fragmento in textwrap.wrap(texto, width=largura) or [texto[:largura]]:
            linhas.append(fragmento.center(largura) if bloco.centralizado else fragmento)
    return "\n".join(linhas)
