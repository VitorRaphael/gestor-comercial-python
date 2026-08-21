from sqlalchemy import select

from gestor_comercial.domain.impressora import Impressora
from gestor_comercial.repository.base import Repository


class ImpressoraRepository(Repository[Impressora]):
    modelo = Impressora

    def buscar_por_nome(self, nome: str) -> Impressora | None:
        return self.session.scalars(select(Impressora).where(Impressora.nome == nome)).first()

    def buscar_padrao(self) -> Impressora | None:
        """A impressora do fallback, do recibo e do fechamento de caixa (§3.12).

        Filtra por `ativa` de propósito: impressora desligada pelo gerente não
        pode continuar recebendo cupom só porque tem a marca de padrão. Sem
        padrão ativa o service avisa na tela em vez de mandar pro vazio.
        """
        stmt = (
            select(Impressora)
            .where(Impressora.padrao.is_(True), Impressora.ativa.is_(True))
            .order_by(Impressora.id)
        )
        return self.session.scalars(stmt).first()

    def listar_ativas(self) -> list[Impressora]:
        stmt = select(Impressora).where(Impressora.ativa.is_(True)).order_by(Impressora.id)
        return list(self.session.scalars(stmt))
