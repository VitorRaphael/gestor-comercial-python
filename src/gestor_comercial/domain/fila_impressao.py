"""Cupom que não saiu no papel e ficou guardado para reimpressão (Fase 3).

O RNF inegociável de §2 já dizia que impressora quebrada não derruba a venda, e
isso valia: o `ImpressaoService` transformava a falha num aviso âmbar e o cliente
ia embora pago. O que faltava era a outra metade — **o cupom em si se perdia**.
Se a bobina acabou no meio do almoço, a cozinha não recebe o pedido, e a única
saída era o operador achar a comanda na tela e clicar "2ª via" à mão, cupom por
cupom, no meio do pico. No pico, ele não vai.

Esta tabela é onde o cupom espera. Guarda o **documento já montado**, e não o id
da comanda, por três motivos:

1. Reimprimir tem que sair igual ao que teria saído na hora. O documento montado
   é um retrato; remontar a partir da comanda semanas depois pegaria preço novo,
   item cancelado depois, nome de atendente trocado.
2. Nem todo cupom vem de comanda. O fechamento de caixa e o teste de impressora
   também caem aqui, e não têm de onde ser remontados.
3. Desacopla da `Session`: o documento é texto puro (ver `documento` abaixo), o
   que é justamente o que permite a impressão sair da thread da UI sem levar o
   SQLAlchemy junto.

Não tem `ForeignKey` para `comandas` de propósito — uma comanda apagada não pode
impedir a 2ª via de um cupom que o cliente ainda está esperando.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gestor_comercial.repository.base import Base

# Teto de cupons guardados. A fila é rede de contingência, não histórico: o que
# interessa é reimprimir o pedido do almoço de hoje, não o de três semanas atrás.
# Sem teto, uma impressora esquecida desligada durante um mês encheria a tabela
# com milhares de cupons que ninguém vai imprimir — e o RNF é um Celeron.
FILA_MAXIMA = 200


class ItemFilaImpressao(Base):
    __tablename__ = "fila_impressao_pendente"

    id: Mapped[int] = mapped_column(primary_key=True)

    # FK para a impressora que deveria ter recebido: a 2ª via tem que sair na
    # mesma, ou o pedido da cozinha vai parar no balcão.
    impressora_id: Mapped[int] = mapped_column(
        ForeignKey("impressoras.id"), nullable=False, index=True
    )

    # O documento serializado como JSON de `BlocoTexto` (texto/negrito/
    # centralizado/dobro). JSON e não pickle: o arquivo do banco vai para
    # pendrive e precisa ser legível e inofensivo — pickle executaria código na
    # volta.
    documento: Mapped[str] = mapped_column(Text, nullable=False)

    # "Comanda mesa 3", "Recibo do cliente", "Fechamento de caixa" — o que a tela
    # mostra na lista de pendentes. O operador escolhe pelo que reconhece, não
    # por id.
    descricao: Mapped[str] = mapped_column(String(120), nullable=False)

    criado_em: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, nullable=False, index=True
    )
    tentativas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # A última mensagem de `ErroDeImpressao` — em português e no imperativo, como
    # o resto da camada `hardware/`. É o que diz ao operador se o problema é
    # papel, cabo ou cadastro.
    ultimo_erro: Mapped[str | None] = mapped_column(String(400))
