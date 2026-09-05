"""Paleta de cores do Gestor Comercial Python — tema "Axiom Solvir".

Duas paletas completas (`TEMA_ESCURO` "Concreto" e `TEMA_CLARO` "Vívido"),
compartilhadas entre a tela de login (`ui/views/login_view.py`) e o resto do
shell (`ui/theme/qss_app.py`, aplicado via `ThemeController` em
`ui/theme/controller.py`) — um único lugar de verdade para as cores do app
inteiro, escuro ou claro.

QSS não suporta `var()`, então os dicts abaixo são interpolados direto nos
templates de `qss_app.py` / `login_view.py` a cada troca de tema.
"""

TEMA_ESCURO: dict[str, str] = {
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
    # Ciano de métricas de produto (Dashboard Mensal: barra de ranking do mix
    # de vendas) — deliberadamente diferente do ciano de "ação neutra"
    # (#0891b2) usado em botões, pra não confundir dado com controle.
    "ciano_metrica": "#22D3EE",
    # Cards de mesa (livre/ocupada/fechando): mesma superfície elevada pras
    # três, só a barra/borda superior muda de cor por status — não é mais
    # fundo tingido por estado (era roxo pra ocupada antes do redesign
    # "Dark Industrial").
    "mesa_bg": "#1a1a1a",
    "mesa_ocupada_bg": "#1a1a1a",
    "mesa_ocupada_borda": "#38bdf8",
    # "Fechando" = comanda em conferência (pré-conta emitida, itens travados)
    # numa mesa ocupada — estado intermediário entre ocupada e livre de novo.
    "mesa_fechando_borda": "#f59e0b",
    "mesa_livre_bg": "#1a1a1a",
    # Logo isométrico na mesma tonalidade vívida do acento (botão ENTER/pílula
    # ESCURO), só com camadas mais escuras por baixo pra dar profundidade.
    "logo_clara": "#ffd873",
    "logo_media": "#E5A93C",
    "logo_escura": "#9c6f10",
}

TEMA_CLARO: dict[str, str] = {
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
    # Logo isométrico "concreto claro": face frontal quase branca, profundidade em cinza-azulado.
    "logo_clara": "#f5f7fb",
    "logo_media": "#c3cadb",
    "logo_escura": "#8991a8",
}

# ----------------------------------------------------------------------
# Constantes planas (tema escuro) -- usadas por widgets que ainda não
# reagem à troca de tema (diálogos pontuais como `comprovante_dialog.py`).
# Ao tornar um widget reativo, prefira ler de `TEMA_ESCURO`/`TEMA_CLARO`
# via `ThemeController` em vez de importar estas constantes.
# ----------------------------------------------------------------------

BG = TEMA_ESCURO["bg_marca"]
BG_ELEVADO = TEMA_ESCURO["bg_terminal"]
SUPERFICIE = TEMA_ESCURO["superficie"]
SUPERFICIE_2 = TEMA_ESCURO["superficie_2"]
SUPERFICIE_3 = TEMA_ESCURO["borda"]
BORDA = TEMA_ESCURO["borda"]

TEXTO = TEMA_ESCURO["texto"]
TEXTO_FRACO = TEMA_ESCURO["texto_fraco"]
TEXTO_FRAQUISSIMO = TEMA_ESCURO["texto_fraquissimo"]

ACENTO = TEMA_ESCURO["acento"]
ACENTO_TEXTO = TEMA_ESCURO["acento_texto"]
ROSA = TEMA_ESCURO["rosa"]
AZUL = "#3b82f6"

SUCESSO = TEMA_ESCURO["sucesso"]
PERIGO = TEMA_ESCURO["perigo"]
PERIGO_HOVER = TEMA_ESCURO["perigo_hover"]
AVISO = TEMA_ESCURO["aviso"]
INFO = AZUL
CIANO_METRICA = TEMA_ESCURO["ciano_metrica"]

RAIO_SM = 8
RAIO = 14
RAIO_LG = 20
