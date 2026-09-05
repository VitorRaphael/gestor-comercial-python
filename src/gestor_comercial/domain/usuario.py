from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gestor_comercial.domain.enums import PerfilUsuario
from gestor_comercial.repository.base import Base


class Usuario(Base):
    """Quem loga no sistema (§3.1). Não confundir com `Funcionario`
    (atendimento, sem login) — ver docs/arquitetura.md §3.1/§3.11.

    Não tem mais PIN pessoal (removido em favor da cascata de 3 níveis de
    `LojaConfig`/`LojaConfigService` — Senha de Login, Senha Operacional,
    Senha Master, ver `AuthService.validar_pin_nivel`): esta entidade só
    identifica QUEM está logando (nome, `perfil` para `exigir_gerente()`,
    `ativo`) — a validação do PIN em si acontece contra a loja, não contra
    o usuário.
    """

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    perfil: Mapped[PerfilUsuario] = mapped_column(Enum(PerfilUsuario), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    comandas: Mapped[list["Comanda"]] = relationship(
        foreign_keys="Comanda.usuario_id", back_populates="usuario"
    )
    comandas_canceladas: Mapped[list["Comanda"]] = relationship(
        foreign_keys="Comanda.cancelado_por_id", back_populates="cancelado_por"
    )
    itens_cancelados: Mapped[list["ItemComanda"]] = relationship(back_populates="cancelado_por")
    movimentos_caixa: Mapped[list["MovimentoCaixa"]] = relationship(back_populates="usuario")
    caixas_abertos: Mapped[list["Caixa"]] = relationship(
        foreign_keys="Caixa.aberto_por_id", back_populates="aberto_por"
    )
    caixas_fechados: Mapped[list["Caixa"]] = relationship(
        foreign_keys="Caixa.fechado_por_id", back_populates="fechado_por"
    )
    quitacoes_autorizadas: Mapped[list["QuitacaoConsumo"]] = relationship(back_populates="autorizado_por")
