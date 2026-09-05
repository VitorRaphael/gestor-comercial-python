from __future__ import annotations

from sqlalchemy import select

from gestor_comercial.domain.loja_config import LojaConfig
from gestor_comercial.repository.base import Repository

ID_SINGLETON = 1


class LojaConfigRepository(Repository[LojaConfig]):
    modelo = LojaConfig

    def obter(self) -> LojaConfig | None:
        stmt = select(LojaConfig).where(LojaConfig.id == ID_SINGLETON)
        return self.session.scalars(stmt).first()
