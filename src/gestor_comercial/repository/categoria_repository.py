from sqlalchemy import exists, select

from gestor_comercial.domain.categoria import Categoria
from gestor_comercial.repository.base import Repository


class CategoriaRepository(Repository[Categoria]):
    modelo = Categoria

    def buscar_por_nome(self, nome: str) -> Categoria | None:
        return self.session.scalars(select(Categoria).where(Categoria.nome == nome)).first()

    def listar_todos(self) -> list[Categoria]:
        return list(self.session.scalars(select(Categoria).order_by(Categoria.nome)))

    def listar_do_cardapio(self) -> list[Categoria]:
        """Os grupos que a tela do Cardápio administra — sem os arquivados (§9.14).

        Separado de `listar_todos` pelo mesmo motivo de
        `ProdutoRepository.listar_do_cardapio`: o arquivado tem que continuar
        alcançável por quem olha para o passado (é ele que segura a FK dos
        produtos já vendidos) e sumir de quem olha para o cardápio de hoje.
        """
        stmt = select(Categoria).where(Categoria.arquivado.is_(False)).order_by(Categoria.nome)
        return list(self.session.scalars(stmt))

    def listar_ativas(self) -> list[Categoria]:
        """As que vendem: ativas E não arquivadas.

        As duas condições, e não só `ativo`: uma categoria arquivada nunca é
        desativada junto (arquivar não é desativar), então filtrar só por
        `ativo` a devolveria para o seletor do cadastro de produto — e o
        gerente cadastraria item novo dentro de um grupo que não existe mais.
        """
        stmt = (
            select(Categoria)
            .where(Categoria.ativo.is_(True), Categoria.arquivado.is_(False))
            .order_by(Categoria.nome)
        )
        return list(self.session.scalars(stmt))

    def existe_com_impressora(self, impressora_id: int) -> bool:
        return bool(
            self.session.scalar(select(exists().where(Categoria.impressora_id == impressora_id)))
        )
