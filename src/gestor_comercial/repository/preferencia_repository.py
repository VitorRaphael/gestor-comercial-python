from __future__ import annotations

from sqlalchemy import select

from gestor_comercial.domain.preferencia import Preferencia
from gestor_comercial.repository.base import Repository

# As chaves em uso, como constante e não como literal solto: o nome digitado
# errado num dos dois lados não daria erro nenhum — a leitura simplesmente
# devolveria `None` e o app se comportaria como se a preferência nunca tivesse
# sido gravada, calado.
BOOTSTRAP_CONCLUIDO = "bootstrap_concluido"
ULTIMO_OPERADOR_ID = "ultimo_operador_id"
CHAVE_DE_EXIBICAO = "chave_de_exibicao"

# Valor gravado em `BOOTSTRAP_CONCLUIDO`. O que importa é a chave EXISTIR; o
# texto é para quem abrir o banco num navegador de SQLite entender o que leu.
SIM = "sim"


class PreferenciaRepository(Repository[Preferencia]):
    modelo = Preferencia

    def obter(self, chave: str) -> str | None:
        """O valor da chave, ou `None` se ela nunca foi gravada."""
        linha = self.session.get(Preferencia, chave)
        return linha.valor if linha is not None else None

    def obter_int(self, chave: str) -> int | None:
        """O valor como inteiro, ou `None` se faltar ou não for número.

        Texto que não converte é tratado como ausência de propósito: o único
        jeito de uma linha dessas existir é edição manual do banco, e nesse
        caso o certo é a tela cair no padrão dela, não estourar no boot.
        """
        valor = self.obter(chave)
        if valor is None:
            return None
        try:
            return int(valor)
        except ValueError:
            return None

    def existe(self, chave: str) -> bool:
        return self.session.scalar(
            select(Preferencia.chave).where(Preferencia.chave == chave)
        ) is not None

    def definir(self, chave: str, valor: str) -> Preferencia:
        """Grava (ou regrava) a chave. `flush`, não `commit` — quem decide o
        momento do commit continua sendo o service, como em todo `Repository`."""
        linha = self.session.get(Preferencia, chave)
        if linha is None:
            linha = Preferencia(chave=chave, valor=valor)
            self.session.add(linha)
        else:
            linha.valor = valor
        self.session.flush()
        return linha

    def remover_chave(self, chave: str) -> None:
        """Apaga a preferência, se existir. Chave ausente não é erro.

        Nome diferente de `remover` (herdado, que recebe a entidade) de
        propósito: uma sobrecarga que aceitasse ora o objeto ora a string
        trocaria um erro de tipo por uma gravação silenciosa no lugar errado.
        """
        linha = self.session.get(Preferencia, chave)
        if linha is not None:
            self.session.delete(linha)
            self.session.flush()
