from sqlalchemy import exists, select

from gestor_comercial.domain.combo_item import ComboItem
from gestor_comercial.repository.base import Repository


class ComboItemRepository(Repository[ComboItem]):
    modelo = ComboItem

    def listar_por_combo(self, combo_id: int) -> list[ComboItem]:
        stmt = select(ComboItem).where(ComboItem.combo_id == combo_id).order_by(ComboItem.id)
        return list(self.session.scalars(stmt))

    def existe_como_combo(self, produto_id: int) -> bool:
        return bool(self.session.scalar(select(exists().where(ComboItem.combo_id == produto_id))))

    def existe_como_componente(self, produto_id: int) -> bool:
        return bool(self.session.scalar(select(exists().where(ComboItem.produto_id == produto_id))))

    def buscar_por_combo_e_produto(self, combo_id: int, produto_id: int) -> ComboItem | None:
        stmt = select(ComboItem).where(
            ComboItem.combo_id == combo_id, ComboItem.produto_id == produto_id
        )
        return self.session.scalars(stmt).first()
