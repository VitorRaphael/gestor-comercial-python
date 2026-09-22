from gestor_comercial.domain.consumo_sessao_assinatura import ConsumoSessaoAssinatura
from gestor_comercial.repository.base import Repository


class ConsumoSessaoAssinaturaRepository(Repository[ConsumoSessaoAssinatura]):
    modelo = ConsumoSessaoAssinatura
