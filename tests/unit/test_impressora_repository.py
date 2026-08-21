"""Consultas de impressora que o roteamento depende (§3.12).

`buscar_padrao` e `listar_ativas` são exercitados aqui direto no repository,
sem service no meio, porque é neles que mora a decisão de qual impressora
recebe o recibo, o fechamento e o fallback da comanda. Um erro aqui não
aparece como exceção: aparece como cupom saindo na impressora errada.
"""

from gestor_comercial.domain.impressora import Impressora


def nova_impressora(uow, nome, padrao=False, ativa=True):
    return uow.impressoras.salvar(Impressora(nome=nome, padrao=padrao, ativa=ativa))


def test_buscar_padrao_devolve_a_marcada(uow, impressora):
    nova_impressora(uow, "Balcão")

    assert uow.impressoras.buscar_padrao().id == impressora.id


def test_buscar_padrao_ignora_a_desativada(uow):
    """O gerente desligou aquele destino: a marca sozinha não o traz de volta."""
    nova_impressora(uow, "Balcão", padrao=True, ativa=False)

    assert uow.impressoras.buscar_padrao() is None


def test_buscar_padrao_sem_nenhuma_cadastrada(uow):
    assert uow.impressoras.buscar_padrao() is None


def test_buscar_padrao_com_duas_marcadas_devolve_sempre_a_mesma(uow):
    """A invariante de uma padrão só é do service. Se um banco antigo (ou
    editado na mão) tiver duas, o recibo e o fechamento não podem sair em
    impressoras diferentes conforme a ordem que o SQLite devolver."""
    primeira = nova_impressora(uow, "Cozinha", padrao=True)
    nova_impressora(uow, "Balcão", padrao=True)

    assert uow.impressoras.buscar_padrao().id == primeira.id


def test_listar_ativas_ignora_desativadas_e_segue_a_ordem_de_cadastro(uow):
    cozinha = nova_impressora(uow, "Cozinha")
    nova_impressora(uow, "Chapa", ativa=False)
    bar = nova_impressora(uow, "Bar")

    assert [i.id for i in uow.impressoras.listar_ativas()] == [cozinha.id, bar.id]


def test_buscar_por_nome(uow, impressora):
    assert uow.impressoras.buscar_por_nome("Cozinha").id == impressora.id
    assert uow.impressoras.buscar_por_nome("Bar") is None
