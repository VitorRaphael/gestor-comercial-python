from sqlalchemy import select

from gestor_comercial.domain.fila_impressao import FILA_MAXIMA, ItemFilaImpressao
from gestor_comercial.repository.base import Repository


class FilaImpressaoRepository(Repository[ItemFilaImpressao]):
    modelo = ItemFilaImpressao

    def listar_pendentes(self) -> list[ItemFilaImpressao]:
        """Ordem de chegada: o pedido mais antigo é o que o cliente espera há mais tempo."""
        stmt = select(ItemFilaImpressao).order_by(
            ItemFilaImpressao.criado_em, ItemFilaImpressao.id
        )
        return list(self.session.scalars(stmt))

    def listar_da_impressora(self, impressora_id: int) -> list[ItemFilaImpressao]:
        stmt = (
            select(ItemFilaImpressao)
            .where(ItemFilaImpressao.impressora_id == impressora_id)
            .order_by(ItemFilaImpressao.criado_em, ItemFilaImpressao.id)
        )
        return list(self.session.scalars(stmt))

    def contar(self) -> int:
        return len(list(self.session.scalars(select(ItemFilaImpressao.id))))

    def podar_excedente(self, manter: int = FILA_MAXIMA) -> int:
        """Descarta os cupons mais antigos além do teto, devolvendo quantos saíram.

        A fila é rede de contingência, não histórico. Sem esta poda, uma
        impressora esquecida desligada durante um mês encheria a tabela com
        milhares de cupons que ninguém vai imprimir — e o alvo é um Celeron de
        4 GB. Descartar o **mais antigo** é a escolha certa: cupom de ontem já
        não interessa a ninguém; o do almoço de hoje ainda pode salvar um pedido.
        """
        pendentes = self.listar_pendentes()
        excedentes = pendentes[:-manter] if manter > 0 else pendentes
        for item in excedentes:
            self.session.delete(item)
        if excedentes:
            self.session.flush()
        return len(excedentes)
