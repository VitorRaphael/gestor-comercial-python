"""Paleta de cores do Gestor Comercial Python — tema "Axiom Solvir".

Duas paletas completas (`TEMA_ESCURO` "Concreto" e `TEMA_CLARO` "Vívido"),
compartilhadas entre a tela de login (`ui/views/login_view.py`) e o resto do
shell (`ui/theme/qss_app.py`, aplicado via `ThemeController` em
`ui/theme/controller.py`) — um único lugar de verdade para as cores do app
inteiro, escuro ou claro.

QSS não suporta `var()`, então os dicts abaixo são interpolados direto nos
templates de `qss_app.py` / `login_view.py` a cada troca de tema.
"""

# ----------------------------------------------------------------------
# Cópia congelada dos tokens do tema escuro/claro tal como eram antes do
# redesign "Concreto" (2026-09-05) -- usada exclusivamente pela tela de
# Login (`login_view.py`), que foi propositalmente excluída do redesign e
# deve permanecer visualmente intacta. NUNCA edite estes dois dicts; toda
# mudança de paleta do shell entra em `TEMA_ESCURO`/`TEMA_CLARO` abaixo.
# ----------------------------------------------------------------------

TEMA_ESCURO_LOGIN: dict[str, str] = {
    "bg_marca": "#000000",
    "bg_terminal": "#101010",
    "divisor_vertical": "#202020",
    "canto_azul": "#2f5bd6",
    "superficie": "#161514",
    "superficie_2": "#1C1B19",
    "borda": "#242220",
    "texto": "#F1F3F5",
    "texto_fraco": "#9195ac",
    "texto_fraquissimo": "#6a6f89",
    "acento": "#E5A93C",
    "acento_texto": "#0C0E12",
    "sucesso": "#22c55e",
    "perigo": "#DC2626",
    "perigo_hover": "#ef4444",
    "rosa": "#ec4899",
    "aviso": "#eab308",
    "ciano_metrica": "#22D3EE",
    "mesa_bg": "#1a1a1a",
    "mesa_ocupada_bg": "#1a1a1a",
    "mesa_ocupada_borda": "#38bdf8",
    "mesa_fechando_borda": "#f59e0b",
    "mesa_livre_bg": "#1a1a1a",
    "logo_clara": "#ffd873",
    "logo_media": "#E5A93C",
    "logo_escura": "#9c6f10",
}

TEMA_CLARO_LOGIN: dict[str, str] = {
    "bg_marca": "#F4F2EB",
    "bg_terminal": "#F4F2EB",
    "divisor_vertical": "#d8deec",
    "canto_azul": "#0055FF",
    "superficie": "#FFFFFF",
    "superficie_2": "#f4f6fb",
    "borda": "#d8deec",
    "texto": "#0F141C",
    "texto_fraco": "#5b6178",
    "texto_fraquissimo": "#8a90a8",
    "acento": "#0055FF",
    "acento_texto": "#ffffff",
    "sucesso": "#16a34a",
    "perigo": "#DC2626",
    "perigo_hover": "#ef4444",
    "rosa": "#db2777",
    "aviso": "#b45309",
    "ciano_metrica": "#0e7490",
    "mesa_bg": "#FFFFFF",
    "mesa_ocupada_bg": "#FFFFFF",
    "mesa_ocupada_borda": "#0284c7",
    "mesa_fechando_borda": "#b45309",
    "mesa_livre_bg": "#FFFFFF",
    "logo_clara": "#f5f7fb",
    "logo_media": "#c3cadb",
    "logo_escura": "#8991a8",
}

# ----------------------------------------------------------------------
# Tema escuro do shell (tudo exceto Login) -- redesign "Concreto"
# (2026-09-05): grafite aquecido em vez de preto chapado, com destaques
# âmbar/ciano/verde suave/coral. Consumido por `qss_app.py` via
# `ThemeController`. Ver `TEMA_ESCURO_LOGIN` acima para a paleta congelada
# usada só pelo login.
# ----------------------------------------------------------------------

TEMA_ESCURO: dict[str, str] = {
    "bg_marca": "#0F0F0E",
    "bg_terminal": "#121211",
    "divisor_vertical": "#202020",
    "canto_azul": "#2f5bd6",
    "superficie": "#161615",
    "superficie_2": "#1C1C1A",
    "borda": "rgba(255, 255, 255, 0.08)",
    "texto": "#FFFFFF",
    "texto_fraco": "#A1A1AA",
    "texto_fraquissimo": "#71717A",
    "acento": "#E5A93C",
    "acento_hover": "#F0B854",
    "acento_texto": "#0C0E12",
    "sucesso": "#4ADE80",
    "perigo": "#F87171",
    "perigo_hover": "#FCA5A5",
    "rosa": "#ec4899",
    "aviso": "#eab308",
    # Ciano de métricas de produto (Dashboard Mensal: barra de ranking do mix
    # de vendas) — deliberadamente diferente do ciano de "ação neutra"
    # (#0891b2) usado em botões, pra não confundir dado com controle.
    "ciano_metrica": "#22D3EE",
    # Cards de mesa (livre/ocupada/fechando). LIVRE e FECHANDO continuam na
    # superfície elevada com a barra superior mudando de cor; OCUPADA voltou a
    # ser fundo tingido — Vermelho Ferrari (Rosso Corsa), decisão do Vitor em
    # 2026-09-08. O ciano de antes tratava a mesa cheia como estado neutro, e
    # no balcão ela é a informação que o operador precisa achar de longe: é
    # onde tem dinheiro em aberto. O par é o da spec: corpo `#2D1214`
    # (vermelho quase preto, que não brilha num turno inteiro de tela ligada)
    # com contorno `#DC2626`.
    "mesa_bg": "#161615",
    "mesa_ocupada_bg": "#2D1214",
    "mesa_ocupada_borda": "#DC2626",
    # Número e valor do card ocupado. Existia desde o redesign "Vívido" e nunca
    # tinha sido ligado ao QSS — com o fundo tingido ele passou a ser
    # necessário, porque `texto` sozinho não sabe que o fundo mudou.
    "mesa_ocupada_texto": "#FFFFFF",
    # A palavra OCUPADA e nada mais. Separada da borda de propósito: `#DC2626`
    # em 10px com 1px de espaçamento sobre `#2D1214` fica escuro demais para
    # ler de pé; `#EF4444` é o mesmo vermelho um degrau acima, que a spec chama
    # de "glow".
    "mesa_ocupada_tag": "#EF4444",
    # "Fechando" = comanda em conferência (pré-conta emitida, itens travados)
    # numa mesa ocupada — estado intermediário entre ocupada e livre de novo.
    "mesa_fechando_bg": "#1C1C1A",
    "mesa_fechando_borda": "#E5A93C",
    "mesa_fechando_texto": "#FFFFFF",
    "mesa_livre_bg": "#181817",
    # Logo isométrico na mesma tonalidade vívida do acento (botão ENTER/pílula
    # ESCURO), só com camadas mais escuras por baixo pra dar profundidade.
    "logo_clara": "#ffd873",
    "logo_media": "#E5A93C",
    "logo_escura": "#9c6f10",
    "borda_card": "rgba(255, 255, 255, 0.08)",
    # ---- Chaves espelhadas do polimento do tema claro (ver TEMA_CLARO) --
    # mantêm exatamente os hex que já estavam hardcoded em qss_app.py, só
    # que agora nomeados/roteados por token em vez de literais soltos.
    "pill_comanda_bg": "#1F1D1B",
    "pill_comanda_texto": "#DF9F3D",
    "pill_comanda_bg_2": "#2A2723",
    "pill_comanda_perigo_bg": "#241416",
    "pill_comanda_perigo_borda": "#EA4335",
    "pill_comanda_sucesso": "#5EEAD4",
    "pill_comanda_sucesso_bg": "#241416",
    "pill_comanda_perigo_texto": "#F87171",
    "secao_pendentes_bg": "#161514",
    "secao_pendentes_borda": "#183D39",
    "secao_pendentes_titulo": "#2DD4BF",
    "secao_lancados_bg": "#242220",
    "secao_lancados_acento": "#2DD4BF",
    "secao_texto_fraco": "#78716C",
    "barra_total_bg": "#DF9F3D",
    "barra_total_texto": "#573A08",
    "barra_total_texto_forte": "#0E0B05",
    "combo_atendente_borda": "#A8A29E",
    "combo_atendente_bg": "#1C1B19",
    "ranking_barra_bg": "#1C1C1A",
    "ranking_barra_acento": "#22D3EE",
    "ciano_acao": "#0891b2",
    "ciano_acao_hover": "#06b6d4",
    "ciano_acao_texto": "#ecfeff",
    "perigo_tabela_bg": "#DC2626",
    "pilula_disabled_bg": "#2A2723",
    "pilula_disabled_texto": "#6B655D",
    "pilula_voltar_disabled_borda": "#3A362E",
    "pilula_secundario_texto": "#FFFFFF",
    "pilula_destaque_texto": "#12100C",
    "pilula_destaque_hover": "#eab54f",
    "pilula_perigo_bg": "#EA4335",
    "pilula_perigo_texto": "#FFFFFF",
    "pilula_perigo_hover": "#f0564a",
    "enviar_pedido_bg": "#5EEAD4",
    "enviar_pedido_texto": "#082F2C",
    "enviar_pedido_hover": "#7ff2df",
    "remover_tabela_bg": "#241416",
    "remover_tabela_texto": "#F87171",
    "remover_tabela_borda": "#4C1D24",
    "remover_tabela_hover": "#341c20",
    "tabela_comanda_borda": "#242220",
    "tabela_comanda_texto": "#FFFFFF",
    "tabela_comanda_selecionado_bg": "#1E1D1B",
    "pilula_ciano2_texto": "#072228",
    "pilula_ciano2_hover": "#67e8f9",
    "badge_vazio_bg": "#3f3d3a",
    "badge_vazio_texto": "#a8a29e",
    "badge_ativo_bg": "#16a34a",
    "badge_ativo_texto": "#f0fdf4",
    "badge_desativado_bg": "#57534e",
    "badge_desativado_texto": "#fafaf9",
    "badge_combo_bg": "#f59e0b",
    "badge_combo_texto": "#1c1917",
    "campo_erro_texto": "#f43f5e",
    "campo_erro_bg": "#fdecea",
    # ---- Modais em cartao (`pin_pad_dialog.py`, `funcionario_dialog.py`,
    #      `movimentacao_caixa_dialog.py`) ----
    # Ciano proprio, nomeado pelo papel, em vez de reaproveitar
    # `ciano_metrica` (dado) ou `ciano_acao` (botao): o marcador de digito
    # e o ENTRAR do teclado sao FEEDBACK de autenticacao, e o dia em que a
    # paleta de metricas mudar nao pode arrastar junto a tela que tranca o
    # Caixa. As teclas tem fundo/borda proprios porque ficam DENTRO do
    # cartao (`superficie`) e precisam de um degrau de contraste a mais.
    #
    # `badge_icone_*` chamava-se `pin_icone_*` enquanto so o cadeado do PIN o
    # usava. Hoje veste tambem o badge do modal de funcionario, as iniciais do
    # avatar e o card de cargo escolhido -- o nome passou a ser o papel, e nao
    # a tela, pelo mesmo criterio que renomeou `pin_fechar_*` no §9.4.
    # Pilula "Ativo" marcada, no modal de funcionario: verde do tema sobre um
    # fundo tingido proprio. `sucesso` sozinho, chapado, viraria um botao verde
    # do tamanho de "Cadastrar" ao lado dele -- o que se quer aqui e um estado
    # marcado, nao uma segunda acao primaria.
    "pilula_ativo_bg": "#14291E",
    "pilula_ativo_texto": "#4ADE80",
    "badge_icone_bg": "#132E35",
    "badge_icone_borda": "rgba(34, 211, 238, 0.22)",
    "badge_icone_glifo": "#22D3EE",
    # `botao_circular_*` nomeia o PAPEL, não a tela: o mesmo par bg/borda veste
    # o ✕ do modal de PIN, o ✕ do modal "Adicionar item" e os passos −/+ da
    # quantidade. Chamava-se `pin_fechar_*` enquanto só o PIN o usava; renomear
    # foi mais barato que duplicar a família com os mesmos quatro hex.
    "botao_circular_bg": "#1F1F1D",
    "botao_circular_borda": "rgba(255, 255, 255, 0.06)",
    "botao_circular_hover": "#2A2A27",
    "botao_circular_texto": "#A1A1AA",
    # `tecla_numerica_*` chamava-se `pin_tecla_*` enquanto só o numpad do PIN
    # existia. O modal de movimentação de caixa (§9.6) trouxe o SEGUNDO numpad
    # do app, com as mesmas teclas de 10px de raio dentro do mesmo cartão —
    # renomear pelo papel foi mais barato que duplicar a família com os mesmos
    # quatro hex, pelo mesmo critério de `botao_circular_*`.
    "tecla_numerica_bg": "#1E1E1C",
    "tecla_numerica_borda": "rgba(255, 255, 255, 0.06)",
    "tecla_numerica_hover": "#2A2A27",
    "tecla_numerica_pressed": "#141413",
    "pin_confirmar_bg": "#1D5E65",
    "pin_confirmar_hover": "#22757F",
    "pin_confirmar_texto": "#FFFFFF",
    "pin_dot_vazio": "rgba(255, 255, 255, 0.15)",
    "pin_dot_cheio": "#22D3EE",
    # ---- Movimentação manual da gaveta (`movimentacao_caixa_dialog.py`) ----
    # Uma família por operação, e NÃO `perigo`/`sucesso`/`acento` emprestados.
    # As cores até coincidem hoje (o coral da sangria é o mesmo hex de
    # `perigo`), e é exatamente por isso que o empréstimo seria perigoso: é a
    # armadilha que o §9.5 desarmou quando a mesa ocupada virou vermelha e
    # arrastou junto o badge de despesa do Caixa, que só queria "aquele ciano
    # ali". Sangria não é ERRO e reforço não é SUCESSO — são duas direções de
    # dinheiro. Com nome próprio, mudar o vermelho de alerta do app não repinta
    # a gaveta, e vice-versa.
    #
    # `_tinta` é o fundo do badge do cabeçalho e `_glifo` é o ícone desenhado
    # dentro dele (`_IconeMovimento` lê estes dois nomes de `Operacao`).
    "mov_sangria_tinta": "#2D1517",
    "mov_sangria_glifo": "#F87171",
    "mov_reforco_tinta": "#14291E",
    "mov_reforco_glifo": "#4ADE80",
    "mov_despesa_tinta": "#2B2113",
    "mov_despesa_glifo": "#FBBF24",
    # O botão que grava. Sangria em ciano, e não em vermelho, porque tirar
    # troco para o malote é rotina de turno, não operação destrutiva: pintar de
    # vermelho o botão que o gerente aperta cinco vezes por noite gasta o único
    # sinal de alerta que a tela tem. O vermelho continua reservado para
    # "Fechar caixa" e para os cancelamentos.
    "mov_sangria_acao": "#22D3EE",
    "mov_sangria_acao_texto": "#062A30",
    "mov_reforco_acao": "#22C55E",
    "mov_reforco_acao_texto": "#052E16",
    "mov_despesa_acao": "#E5A93C",
    "mov_despesa_acao_texto": "#2B1D02",
    # O visor de valor é REBAIXADO, não elevado: `superficie_2` (#1C1C1A) é
    # mais claro que o cartão e faria o número parecer um botão. O mockup pede
    # o contrário — um recorte mais escuro que o cartão, como o vidro de uma
    # maquininha.
    "mov_visor_bg": "#111110",
}

TEMA_CLARO: dict[str, str] = {
    "bg_marca": "#F5F4EE",
    "bg_terminal": "#F0EFE9",
    "divisor_vertical": "#E2E1D9",
    "canto_azul": "#0055FF",
    "superficie": "#FFFFFF",
    "superficie_2": "#E9E8E2",
    "borda": "rgba(0, 0, 0, 0.08)",
    "borda_card": "#E2E1D9",
    "texto": "#09090B",
    "texto_fraco": "#64748B",
    "texto_fraquissimo": "#94A3B8",
    "acento": "#0055FF",
    "acento_hover": "#0043CC",
    "acento_texto": "#FFFFFF",
    "sucesso": "#22C55E",
    "perigo": "#EF4444",
    "perigo_hover": "#DC2626",
    "rosa": "#db2777",
    "aviso": "#b45309",
    "ciano_metrica": "#0e7490",
    # Cards de mesa: LIVRE em branco puro (mesma leitura do dashboard),
    # OCUPADA em vermelho pastel e FECHANDO em azul pastel -- ver spec do
    # redesign "Vívido" (2026-09-05) e a troca do âmbar pelo Vermelho Ferrari
    # (2026-09-08). A borda é o MESMO `#DC2626` do tema escuro: o vermelho de
    # mesa ocupada é o único token de status que não muda entre os dois temas,
    # porque é ele que o operador procura de longe.
    "mesa_bg": "#FFFFFF",
    "mesa_ocupada_bg": "#FEE2E2",
    "mesa_ocupada_borda": "#DC2626",
    "mesa_ocupada_texto": "#991B1B",
    # No claro a palavra OCUPADA e o número do card usam o mesmo carmim: sobre
    # `#FEE2E2` o `#991B1B` já tem contraste de sobra, e o degrau que o tema
    # escuro precisa aqui só serviria para clarear texto sobre fundo claro.
    "mesa_ocupada_tag": "#991B1B",
    "mesa_fechando_bg": "#DBEAFE",
    "mesa_fechando_borda": "#3B82F6",
    "mesa_fechando_texto": "#1E40AF",
    "mesa_livre_bg": "#FFFFFF",
    # Logo isométrico "concreto claro": face frontal quase branca, profundidade em cinza-azulado.
    "logo_clara": "#f5f7fb",
    "logo_media": "#c3cadb",
    "logo_escura": "#8991a8",
    # ---- Chaves adicionadas no polimento do tema claro "Vívido" p/
    # eliminar cores hex "órfãs" que ficavam fixas em modo escuro dentro
    # de qss_app.py (pílulas de comanda, seções pendentes/lançados, barra
    # de total, combo de atendente, pílula ciano/ranking).
    "pill_comanda_bg": "#FEF3C7",
    "pill_comanda_texto": "#78350F",
    "pill_comanda_bg_2": "#E9E8E2",
    "pill_comanda_perigo_bg": "#FEE2E2",
    "pill_comanda_perigo_borda": "#EF4444",
    "pill_comanda_sucesso": "#0F766E",
    "pill_comanda_sucesso_bg": "#CCFBF1",
    "pill_comanda_perigo_texto": "#EF4444",
    "secao_pendentes_bg": "#FFFFFF",
    "secao_pendentes_borda": "#99F6E4",
    "secao_pendentes_titulo": "#0F766E",
    "secao_lancados_bg": "#F0EFE9",
    "secao_lancados_acento": "#0F766E",
    "secao_texto_fraco": "#78716C",
    "barra_total_bg": "#FEF3C7",
    "barra_total_texto": "#78350F",
    "barra_total_texto_forte": "#451A03",
    "combo_atendente_borda": "#CBD5C0",
    "combo_atendente_bg": "#FFFFFF",
    "ranking_barra_bg": "#E9E8E2",
    "ranking_barra_acento": "#0891B2",
    "ciano_acao": "#0891B2",
    "ciano_acao_hover": "#0E7490",
    "ciano_acao_texto": "#ecfeff",
    "perigo_tabela_bg": "#DC2626",
    "pilula_disabled_bg": "#E9E8E2",
    "pilula_disabled_texto": "#94A3B8",
    "pilula_voltar_disabled_borda": "#D8D6CC",
    "pilula_secundario_texto": "#09090B",
    "pilula_destaque_texto": "#78350F",
    "pilula_destaque_hover": "#FDE68A",
    "pilula_perigo_bg": "#EF4444",
    "pilula_perigo_texto": "#FFFFFF",
    "pilula_perigo_hover": "#DC2626",
    "enviar_pedido_bg": "#14B8A6",
    "enviar_pedido_texto": "#FFFFFF",
    "enviar_pedido_hover": "#0D9488",
    "remover_tabela_bg": "#FEE2E2",
    "remover_tabela_texto": "#DC2626",
    "remover_tabela_borda": "#FCA5A5",
    "remover_tabela_hover": "#FECACA",
    "tabela_comanda_borda": "#E2E1D9",
    "tabela_comanda_texto": "#09090B",
    "tabela_comanda_selecionado_bg": "#E9E8E2",
    "pilula_ciano2_texto": "#FFFFFF",
    "pilula_ciano2_hover": "#0891B2",
    "badge_vazio_bg": "#E9E8E2",
    "badge_vazio_texto": "#94A3B8",
    "badge_ativo_bg": "#16a34a",
    "badge_ativo_texto": "#f0fdf4",
    "badge_desativado_bg": "#E2E1D9",
    "badge_desativado_texto": "#64748B",
    "badge_combo_bg": "#F59E0B",
    "badge_combo_texto": "#FFFFFF",
    "campo_erro_texto": "#DC2626",
    "campo_erro_bg": "#FEE2E2",
    # ---- Modais em cartao (`pin_pad_dialog.py`, `funcionario_dialog.py`,
    #      `movimentacao_caixa_dialog.py`) ----
    # Ciano proprio, nomeado pelo papel, em vez de reaproveitar
    # `ciano_metrica` (dado) ou `ciano_acao` (botao): o marcador de digito
    # e o ENTRAR do teclado sao FEEDBACK de autenticacao, e o dia em que a
    # paleta de metricas mudar nao pode arrastar junto a tela que tranca o
    # Caixa. As teclas tem fundo/borda proprios porque ficam DENTRO do
    # cartao (`superficie`) e precisam de um degrau de contraste a mais.
    #
    # `badge_icone_*` chamava-se `pin_icone_*` enquanto so o cadeado do PIN o
    # usava. Hoje veste tambem o badge do modal de funcionario, as iniciais do
    # avatar e o card de cargo escolhido -- o nome passou a ser o papel, e nao
    # a tela, pelo mesmo criterio que renomeou `pin_fechar_*` no §9.4.
    # Ver o comentario gemeo em TEMA_ESCURO. No claro o verde do token
    # `sucesso` (#22C55E) sobre o pastel nao tem contraste de texto, entao a
    # pilula marcada usa o verde escuro.
    "pilula_ativo_bg": "#DCFCE7",
    "pilula_ativo_texto": "#15803D",
    "badge_icone_bg": "#CFFAFE",
    "badge_icone_borda": "#A5F3FC",
    "badge_icone_glifo": "#0E7490",
    # Ver o comentário gêmeo em TEMA_ESCURO: o nome é o papel, não a tela.
    "botao_circular_bg": "#F0EFE9",
    "botao_circular_borda": "#E2E1D9",
    "botao_circular_hover": "#E2E1D9",
    "botao_circular_texto": "#64748B",
    "tecla_numerica_bg": "#FFFFFF",
    "tecla_numerica_borda": "#E2E1D9",
    "tecla_numerica_hover": "#F0EFE9",
    "tecla_numerica_pressed": "#E2E1D9",
    "pin_confirmar_bg": "#0891B2",
    "pin_confirmar_hover": "#0E7490",
    "pin_confirmar_texto": "#FFFFFF",
    "pin_dot_vazio": "rgba(0, 0, 0, 0.15)",
    "pin_dot_cheio": "#0891B2",
    # ---- Movimentação manual da gaveta (`movimentacao_caixa_dialog.py`) ----
    # Ver o comentário gêmeo em TEMA_ESCURO para o PORQUÊ de cada operação ter
    # família própria em vez de pegar `perigo`/`sucesso`/`acento` emprestados.
    # O que muda aqui é o arranjo, não o significado: no claro o badge é pastel
    # com o ícone escuro (o inverso do escuro, que é tinta escura com ícone
    # aceso), e o botão usa o degrau saturado da paleta clara — `#22D3EE` e
    # `#4ADE80` sobre branco não têm contraste de texto em botão.
    "mov_sangria_tinta": "#FEE2E2",
    "mov_sangria_glifo": "#DC2626",
    "mov_reforco_tinta": "#DCFCE7",
    "mov_reforco_glifo": "#15803D",
    "mov_despesa_tinta": "#FEF3C7",
    "mov_despesa_glifo": "#B45309",
    "mov_sangria_acao": "#0891B2",
    "mov_sangria_acao_texto": "#ECFEFF",
    "mov_reforco_acao": "#16A34A",
    "mov_reforco_acao_texto": "#F0FDF4",
    "mov_despesa_acao": "#B45309",
    "mov_despesa_acao_texto": "#FFFBEB",
    # Rebaixado em relação ao cartão, como no escuro — só que aqui o cartão é
    # branco puro, então "mais fundo" é o bege do terminal.
    "mov_visor_bg": "#F0EFE9",
}
