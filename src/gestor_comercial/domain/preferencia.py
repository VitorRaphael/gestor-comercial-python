from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from gestor_comercial.repository.base import Base


class Preferencia(Base):
    """Estado leve do app que não é regra de negócio nem cadastro: uma linha
    por chave, o valor sempre como texto.

    Existe porque duas necessidades pequenas apareceram juntas e nenhuma delas
    merecia tabela própria:

    * **`bootstrap_concluido`** — a marca de que o seed do primeiro boot já
      rodou. Sem ela o `run_seed()` reexecutava a cada abertura do programa e
      ressuscitava tudo que o Vitor tivesse apagado na tela: o operador de
      turno excluído em Funcionários voltava, o produto excluído no Cardápio
      voltava. A marca é o que transforma "seed idempotente por nome" em "seed
      da criação do banco".
    * **`ultimo_operador_id`** — quem entrou por último na tela de login, para
      o dropdown já vir naquele nome em vez de no primeiro da lista.

    Por que texto e não uma coluna por assunto: cada chave nova aqui é uma
    linha, não uma migração. O preço é não haver tipo — quem lê converte e
    trata lixo (ver `PreferenciaRepository.obter_int`), e é um preço barato
    para dado que nenhuma regra de negócio consulta.

    Não confundir com `LojaConfig`, que é o singleton dos SEGREDOS da loja
    (§3.13) e tem coluna, tipo e regra própria para cada campo.
    """

    __tablename__ = "preferencias"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str | None] = mapped_column(String(255))
