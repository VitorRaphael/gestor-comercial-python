"""Folha de estilo do shell inteiro (tudo além da tela de login), como um
template parametrizado pelos tokens de `tokens.py` -- portado de
`resources/qss/base.qss` (agora obsoleto/removido) para poder ser
recalculado a cada troca de tema claro/escuro pelo `ThemeController`.

Convenção de propriedade dinâmica para variantes de botão (ver
`QPushButton.setProperty("variante", "primario"|"secundario"|"perigo")`):
qproperty não é usado para estilo -- usamos seletor `[variante="..."]`.
"""

from __future__ import annotations


def construir_qss_app(t: dict[str, str]) -> str:
    return f"""
    * {{
      font-family: "Archivo Black", "Segoe UI Variable Display", "Segoe UI", "Inter", Arial, sans-serif;
    }}

    QWidget {{
      background: {t['bg_marca']};
      color: {t['texto']};
    }}

    QMainWindow {{
      background: {t['bg_marca']};
    }}

    QLineEdit {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 8px;
      padding: 10px 12px;
      color: {t['texto']};
    }}
    QLineEdit:focus {{ border: 1px solid {t['acento']}; }}

    /* ---------- Combo Box ---------- */

    QComboBox {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 8px;
      padding: 8px 12px;
      color: {t['texto']};
      font-size: 13px;
    }}
    QComboBox:focus {{ border: 1px solid {t['acento']}; }}
    QComboBox::drop-down {{ border: none; width: 24px; background: transparent; }}
    QComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}

    QComboBox QAbstractItemView {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 8px;
      color: {t['texto']};
      selection-background-color: {t['acento']};
      selection-color: {t['acento_texto']};
    }}
    QComboBox QAbstractItemView::item {{ padding: 8px 12px; border: none; }}
    QComboBox QAbstractItemView::item:hover {{ background: {t['borda']}; }}

    /* ---------- Sidebar ---------- */

    #sidebar {{
      background: {t['bg_terminal']};
      border-right: 1px solid {t['borda']};
    }}
    #sidebarSelo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      padding: 0 12px;
    }}
    #sidebarMarca {{
      color: {t['texto']};
      font-size: 15px;
      font-weight: 700;
      padding: 2px 12px 0 12px;
    }}
    #sidebarDivisor {{
      background: {t['borda']};
      max-height: 1px;
      min-height: 1px;
      margin: 0 8px;
    }}
    #sidebarBarraUsuario {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    #sidebarGrupoRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      padding: 0 12px;
      background: transparent;
    }}
    #sidebarSelo, #sidebarMarca {{ background: transparent; }}

    QPushButton[variante="nav"] {{
      background: transparent;
      border: none;
      border-left: 3px solid transparent;
      color: {t['texto_fraco']};
      text-align: left;
      padding: 11px 12px;
      border-radius: 10px;
      font-size: 13px;
    }}
    QPushButton[variante="nav"]:hover {{ background: {t['superficie']}; color: {t['texto']}; }}
    QPushButton[variante="nav"][ativo="true"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border-left: 3px solid {t['acento']};
    }}

    /* ---------- Pílula de tema (agora só na tela de Configurações) ---------- */

    QFrame[variante="pilula-tema"] {{
      background: {t['superficie_2']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}
    QPushButton[variante="temaBotao"] {{
      background: transparent;
      color: {t['texto_fraco']};
      border: none;
      border-radius: 11px;
      padding: 7px 0px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
    }}
    QPushButton[variante="temaBotao"]:checked {{
      background: {t['acento']};
      color: {t['acento_texto']};
    }}

    /* ---------- Botões ---------- */

    QPushButton {{
      border: none;
      border-radius: 10px;
      padding: 10px 16px;
      font-size: 13px;
      font-weight: 600;
    }}

    QPushButton[variante="primario"] {{ background: {t['acento']}; color: {t['acento_texto']}; }}
    QPushButton[variante="primario"]:hover {{ background: {t['acento']}; }}
    QPushButton[variante="primario"]:disabled {{ background: {t['borda']}; color: {t['texto_fraquissimo']}; }}

    QPushButton[variante="secundario"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border: 1px solid {t['borda']};
    }}
    QPushButton[variante="secundario"]:hover {{ background: {t['borda']}; }}

    QPushButton[variante="perigo"] {{ background: {t['perigo']}; color: white; border: none; }}
    QPushButton[variante="perigo"]:hover {{ background: {t['perigo_hover']}; }}
    QPushButton[variante="perigo"]:pressed {{ background: {t['perigo']}; }}

    /* Variante compacta de "perigo" para botões dentro de linha de tabela
       (Remover/Cancelar em `ComandaView`): o padding padrão de QPushButton
       (10px 16px + fonte 13px) exige ~38px de altura, mais que a linha da
       tabela (~30px) comporta — o botão fica espremido pelo `setCellWidget`
       e, abaixo de um certo limiar, o Qt para de desenhar o texto (vira uma
       barra vermelha vazia). Padding e fonte menores cabem na linha padrão. */
    QPushButton[variante="perigo-tabela"] {{
      background: #DC2626; color: #FFFFFF; border: none;
      height: 22px; padding: 0 12px; font-size: 11px; font-weight: 700; border-radius: 11px;
    }}
    QPushButton[variante="perigo-tabela"]:hover {{ background: {t['perigo_hover']}; }}
    QPushButton[variante="perigo-tabela"]:pressed {{ background: {t['perigo']}; }}

    /* ---------- Pílulas do cabeçalho da Comanda ---------- */

    /* "← Mesas": ponto de saída da tela — precisa se destacar dos botões
       neutros ao lado (+ Item, 2ª via) pra ficar óbvio que é a saída, não
       mais uma ação da comanda. Borda âmbar + peso maior que o padrão. */
    QPushButton[variante="pilula-voltar"] {{
      background: #1F1D1B;
      color: #DF9F3D;
      border: 1.5px solid #DF9F3D;
      border-radius: 18px;
      padding: 7px 18px;
      font-size: 13px;
      font-weight: 800;
    }}
    QPushButton[variante="pilula-voltar"]:hover {{ background: #2A2723; }}
    QPushButton[variante="pilula-voltar"]:disabled {{ color: #6B655D; border-color: #3A362E; }}

    QPushButton[variante="pilula-secundario"] {{
      background: #1F1D1B;
      color: #FFFFFF;
      border: none;
      border-radius: 18px;
      padding: 7px 18px;
      font-size: 12px;
      font-weight: 600;
    }}
    QPushButton[variante="pilula-secundario"]:hover {{ background: #2A2723; }}
    QPushButton[variante="pilula-secundario"]:disabled {{ color: #6B655D; }}

    QPushButton[variante="pilula-destaque"] {{
      background: #DF9F3D;
      color: #12100C;
      border: none;
      border-radius: 18px;
      padding: 7px 20px;
      font-size: 13px;
      font-weight: 800;
    }}
    QPushButton[variante="pilula-destaque"]:hover {{ background: #eab54f; }}
    QPushButton[variante="pilula-destaque"]:disabled {{ background: #2A2723; color: #6B655D; }}

    QPushButton[variante="pilula-perigo"] {{
      background: #EA4335;
      color: #FFFFFF;
      border: none;
      border-radius: 18px;
      padding: 7px 20px;
      font-size: 13px;
      font-weight: 700;
    }}
    QPushButton[variante="pilula-perigo"]:hover {{ background: #f0564a; }}
    QPushButton[variante="pilula-perigo"]:disabled {{ background: #2A2723; color: #6B655D; }}

    /* Combo "Atendeu": some com a aparência de caixa de formulário e vira
       texto simples, como no mockup — continua clicável/funcional, só sem o
       chrome visual de combo box. */
    QComboBox#combo-atendente {{
      background: transparent;
      border: none;
      padding: 0 4px;
      color: #A8A29E;
      font-size: 13px;
      font-weight: 500;
    }}
    QComboBox#combo-atendente::drop-down {{ border: none; width: 14px; }}
    QComboBox#combo-atendente QAbstractItemView {{
      background: #1C1B19;
      border: 1px solid #242220;
      color: #FFFFFF;
    }}

    /* Botão "Enviar Pedido à Produção", no header do card de pendentes */
    QPushButton[variante="enviar-pedido"] {{
      background: #5EEAD4;
      color: #082F2C;
      border: none;
      border-radius: 18px;
      padding: 8px 22px;
      font-size: 13px;
      font-weight: 800;
    }}
    QPushButton[variante="enviar-pedido"]:hover {{ background: #7ff2df; }}
    QPushButton[variante="enviar-pedido"]:disabled {{ background: #2A2723; color: #6B655D; }}

    /* Botão "Remover" compacto na tabela de itens pendentes */
    QPushButton[variante="remover-tabela"] {{
      background: #241416;
      color: #F87171;
      border: 1px solid #4C1D24;
      border-radius: 11px;
      font-size: 11px;
      font-weight: 700;
      height: 22px;
      padding: 0 10px;
    }}
    QPushButton[variante="remover-tabela"]:hover {{ background: #341c20; }}

    QPushButton[variante="neutro"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border: 1px solid {t['borda']};
    }}
    QPushButton[variante="neutro"]:hover {{ background: {t['borda']}; }}

    QPushButton[variante="sucesso"] {{ background: {t['sucesso']}; color: white; font-weight: 700; }}
    QPushButton[variante="sucesso"]:hover {{ background: {t['sucesso']}; }}
    QPushButton[variante="sucesso"]:disabled {{ background: {t['borda']}; color: {t['texto_fraquissimo']}; }}

    /* ---------- Grid de mesas ---------- */

    QFrame[variante="mesa"] {{
      background: {t['mesa_livre_bg']};
      border: 1px solid {t['borda']};
      border-top: 3px solid {t['sucesso']};
      border-radius: 14px;
    }}
    QFrame[variante="mesa"]:hover {{ background: {t['superficie_2']}; }}
    QLabel#mesaCartaoNumero {{ color: {t['texto']}; font-size: 20px; font-weight: 800; background: transparent; }}
    QLabel#mesaCartaoTag {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QFrame[variante="mesa"][ocupada="true"] QLabel#mesaCartaoTag {{ color: {t['mesa_ocupada_borda']}; }}
    QFrame[variante="mesa"][fechando="true"] QLabel#mesaCartaoTag {{ color: {t['mesa_fechando_borda']}; }}
    QLabel#mesaCartaoValor {{ color: {t['texto']}; font-size: 13px; font-weight: 800; background: transparent; }}
    QLabel#mesaCartaoNome {{ color: {t['texto_fraco']}; font-size: 11px; background: transparent; }}
    /* Ciano, não roxo/vermelho: "ocupada" é estado normal (mesa em
       atendimento), não um alerta — vermelho fica reservado pra ações
       destrutivas (perigo). */
    QFrame[variante="mesa"][ocupada="true"] {{
      background: {t['mesa_ocupada_bg']};
      border: 1px solid {t['mesa_ocupada_borda']};
      border-top: 3px solid {t['mesa_ocupada_borda']};
    }}
    /* "Fechando" = comanda em conferência (pré-conta emitida) numa mesa
       ocupada -- sobrepõe a cor de "ocupada" acima. */
    QFrame[variante="mesa"][fechando="true"] {{
      background: {t['mesa_bg']};
      border: 1px solid {t['mesa_fechando_borda']};
      border-top: 3px solid {t['mesa_fechando_borda']};
    }}

    /* ---------- Tela de Mesas: cabeçalho, filtros, container do grid ---------- */

    QLabel#mesasTitulo {{ color: {t['texto']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#mesasSubtitulo {{ color: {t['texto_fraco']}; font-size: 13px; background: transparent; }}

    QPushButton[variante="filtro-pill"] {{
      background: {t['superficie_2']};
      color: {t['texto_fraco']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
      padding: 7px 16px;
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton[variante="filtro-pill"]:hover {{ color: {t['texto']}; }}
    QPushButton[variante="filtro-pill"][ativo="true"] {{
      background: {t['superficie_2']};
      color: {t['acento']};
      border: 1px solid {t['acento']};
    }}

    QFrame#mesasContainer {{
      background: {t['bg_terminal']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}

    /* ---------- Painel direito (resumo do salão + comandas ativas) ---------- */

    QFrame#painelResumoSalao, QFrame#painelComandasAtivas {{
      background: {t['mesa_bg']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#painelTituloSecao {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#painelValorGrande {{ color: {t['texto']}; font-size: 32px; font-weight: 800; background: transparent; }}
    QLabel#painelRotuloMini {{ color: {t['texto_fraco']}; font-size: 11px; font-weight: 600; background: transparent; }}
    QFrame#painelBarraTrilho {{ background: {t['borda']}; border-radius: 3px; }}
    QFrame#painelBarraPreenchida {{ background: {t['acento']}; border-radius: 3px; }}

    QFrame#painelMiniStat {{
      background: {t['superficie_2']};
      border-radius: 10px;
    }}
    QLabel#painelMiniStatValor {{ color: {t['texto']}; font-size: 17px; font-weight: 800; background: transparent; }}
    QLabel#painelMiniStatRotulo {{ color: {t['texto_fraco']}; font-size: 10px; font-weight: 600; background: transparent; }}

    QLabel#comandaListaMesa {{ color: {t['texto']}; font-size: 13px; font-weight: 700; background: transparent; }}
    QLabel#comandaListaAtendente {{ color: {t['texto_fraco']}; font-size: 11px; background: transparent; }}
    QLabel#comandaListaValor {{ color: {t['texto']}; font-size: 13px; font-weight: 800; background: transparent; }}
    QLabel#comandaListaPontoOcupada {{ color: {t['mesa_ocupada_borda']}; font-size: 10px; background: transparent; }}
    QLabel#comandaListaPontoFechando {{ color: {t['mesa_fechando_borda']}; font-size: 10px; background: transparent; }}
    QLabel#painelMiniStatDotLivre {{ color: {t['sucesso']}; font-size: 9px; background: transparent; }}
    QLabel#painelMiniStatDotOcupada {{ color: {t['mesa_ocupada_borda']}; font-size: 9px; background: transparent; }}
    QLabel#painelMiniStatDotFechando {{ color: {t['mesa_fechando_borda']}; font-size: 9px; background: transparent; }}

    /* ---------- Painéis / cartões ---------- */

    QFrame[variante="painel"], QFrame[variante="cartao"] {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}

    /* ---------- Tabelas ---------- */

    QTableWidget, QTableView {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
      gridline-color: {t['borda']};
    }}
    QHeaderView::section {{
      background: {t['superficie_2']};
      color: {t['texto_fraco']};
      padding: 10px 12px;
      border: none;
      border-bottom: 1px solid {t['borda']};
      text-transform: uppercase;
      font-size: 11px;
    }}
    QTableWidget::item, QTableView::item {{
      padding: 8px 12px;
      border-bottom: 1px solid {t['borda']};
    }}
    QTableWidget::item:selected, QTableView::item:selected {{ background: {t['superficie_2']}; }}

    /* ---------- Tabelas da Comanda (itens pendentes/lançados) ---------- */

    QTableWidget#tabela-comanda {{
      background: transparent;
      border: none;
      border-radius: 0px;
      gridline-color: transparent;
      outline: none;
    }}
    QTableWidget#tabela-comanda::item {{
      padding: 2px 12px;
      border-bottom: 1px solid #242220;
      color: #FFFFFF;
      font-weight: 600;
      font-size: 14px;
    }}
    QTableWidget#tabela-comanda::item:selected {{
      background: #1E1D1B;
      color: #FFFFFF;
      outline: none;
    }}
    QTableWidget#tabela-comanda::item:hover {{
      background: #1E1D1B;
    }}
    QTableWidget#tabela-comanda QHeaderView::section {{
      background: transparent;
      color: #78716C;
      padding: 6px 12px;
      border: none;
      border-bottom: 1px solid #242220;
      text-transform: uppercase;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.2px;
    }}

    /* ---------- Cards de seção da Comanda ---------- */

    #secao-pendentes {{
      background: #161514;
      border: 1px solid #183D39;
      border-radius: 16px;
      padding: 8px;
    }}
    #titulo-secao-pendentes {{
      color: #2DD4BF;
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
    }}
    #secao-lancados {{
      background: #161514;
      border: 1px solid #242220;
      border-radius: 16px;
      padding: 8px;
    }}
    #titulo-secao-lancados {{
      color: #78716C;
      font-weight: 700;
      font-size: 11px;
      letter-spacing: 1.5px;
      text-transform: uppercase;
    }}

    /* ---------- Barra de total (Comanda) ---------- */

    #barra-total {{
      background: #DF9F3D;
      border-radius: 10px;
      border: none;
      min-height: 34px;
    }}
    #barra-total-rotulo {{
      color: #573A08;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      margin-right: 10px;
      background: transparent;
    }}
    #barra-total-valor {{
      color: #0E0B05;
      font-size: 18px;
      font-weight: 900;
      background: transparent;
    }}

    /* ---------- Labels auxiliares ---------- */

    QLabel[variante="fraco"] {{ color: {t['texto_fraco']}; }}
    QLabel[variante="fraquissimo"] {{ color: {t['texto_fraquissimo']}; }}
    QLabel[variante="badge"] {{
      background: {t['sucesso']};
      color: white;
      border-radius: 999px;
      padding: 3px 10px;
      font-size: 10px;
    }}
    QLabel[variante="badge"][status="ocupada"] {{ background: {t['mesa_ocupada_borda']}; }}
    QLabel[variante="badge"][status="fechada"], QLabel[variante="badge"][status="inativo"] {{
      background: {t['borda']};
      color: {t['texto_fraco']};
    }}
    QLabel[variante="badge"][status="cancelada"], QLabel[variante="badge"][status="perigo"] {{
      background: {t['perigo']};
    }}

    /* ---------- Tela de Caixa: dashboard financeiro do turno ---------- */

    QLabel#caixaEyebrow {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      background: transparent;
    }}
    QLabel#caixaTitulo {{ color: {t['texto']}; font-size: 22px; font-weight: 800; background: transparent; }}
    QLabel#caixaSubtitulo {{ color: {t['texto_fraco']}; font-size: 12px; background: transparent; }}

    QFrame#caixaCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#caixaCardRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QLabel#caixaValorGrande {{ color: {t['texto']}; font-size: 30px; font-weight: 800; background: transparent; }}

    QFrame#caixaMiniStat {{
      background: {t['superficie_2']};
      border-radius: 10px;
    }}
    QLabel#caixaMiniStatRotulo {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 1px;
      background: transparent;
    }}
    QLabel#caixaMiniStatValor {{ color: {t['texto']}; font-size: 16px; font-weight: 800; background: transparent; }}

    QLabel#caixaFormaNome {{ color: {t['texto']}; font-size: 12px; font-weight: 600; background: transparent; }}
    QLabel#caixaFormaValor {{ color: {t['texto']}; font-size: 12px; font-weight: 700; background: transparent; }}
    QProgressBar#caixaBarraPagamento {{
      background: {t['borda']};
      border: none;
      border-radius: 2px;
      max-height: 4px;
      min-height: 4px;
    }}
    QProgressBar#caixaBarraPagamento::chunk {{ background: {t['acento']}; border-radius: 2px; }}

    QLabel#caixaAjusteRotulo {{ color: {t['texto']}; font-size: 12px; background: transparent; }}
    QLabel#caixaAjusteValor {{ color: {t['texto']}; font-size: 12px; font-weight: 700; background: transparent; }}
    QLabel#caixaAjusteValorNegativo {{ color: {t['perigo_hover']}; font-size: 12px; font-weight: 700; background: transparent; }}

    QFrame#caixaMovimentosCard {{
      background: {t['bg_terminal']};
      border: 1px solid {t['borda']};
      border-radius: 16px;
    }}
    QLabel#caixaMovimentosTitulo {{ color: {t['texto']}; font-size: 15px; font-weight: 700; background: transparent; }}
    QLabel#caixaMovimentosSubtitulo {{ color: {t['texto_fraco']}; font-size: 11px; background: transparent; }}

    QLabel[variante="badgeMovimento"] {{
      border: 1px solid;
      border-radius: 999px;
      padding: 2px 10px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.5px;
      background: transparent;
    }}
    QLabel[variante="badgeMovimento"][tipo="reforco"] {{ color: {t['sucesso']}; border-color: {t['sucesso']}; }}
    QLabel[variante="badgeMovimento"][tipo="sangria"] {{ color: {t['perigo_hover']}; border-color: {t['perigo_hover']}; }}
    QLabel[variante="badgeMovimento"][tipo="despesa"] {{ color: {t['mesa_ocupada_borda']}; border-color: {t['mesa_ocupada_borda']}; }}

    QFrame#caixaMiniCard {{
      background: {t['mesa_bg']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
    }}
    QLabel#caixaMiniCardTitulo {{ color: {t['texto']}; font-size: 12px; font-weight: 700; background: transparent; }}
    QLabel#caixaMiniCardSub {{ color: {t['texto_fraquissimo']}; font-size: 10px; letter-spacing: 0.4px; background: transparent; }}
    QLabel#caixaMiniCardValor {{ color: {t['perigo_hover']}; font-size: 13px; font-weight: 800; background: transparent; }}
    QLabel#caixaMiniCardValorPositivo {{ color: {t['sucesso']}; font-size: 11px; font-weight: 700; background: transparent; }}
    QLabel#caixaMiniCardValorNegativo {{ color: {t['perigo_hover']}; font-size: 11px; font-weight: 700; background: transparent; }}
    QLabel#caixaMiniCardValorNeutro {{ color: {t['texto_fraco']}; font-size: 11px; font-weight: 700; background: transparent; }}

    QPushButton[variante="pilula-vazia"] {{
      background: transparent;
      color: {t['texto']};
      border: 1px solid {t['borda']};
      border-radius: 18px;
      padding: 7px 18px;
      font-size: 12px;
      font-weight: 600;
    }}
    QPushButton[variante="pilula-vazia"]:hover {{ background: {t['superficie_2']}; }}
    QPushButton[variante="pilula-vazia"]:disabled {{ color: {t['texto_fraquissimo']}; }}

    /* `SecaoCancelamentos` (Caixa e Histórico): sem isto, o QWidget e seus
       QLabel herdam o fundo opaco global e pintam um retângulo escuro por
       cima do card mais claro em que o widget é embutido. */
    QWidget#secaoCancelamentos, QWidget#secaoCancelamentos QLabel {{ background: transparent; }}

    /* ---------- Central de Loja ---------- */

    QLabel#centralLojaBreadcrumb {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      background: transparent;
    }}
    QLabel#centralLojaTitulo {{ color: {t['texto']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#centralLojaSubtitulo {{ color: {t['texto_fraco']}; font-size: 13px; background: transparent; }}
    QLabel#centralLojaSecaoTitulo {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}

    QFrame[variante="loja-hub-card"] {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}
    QFrame[variante="loja-hub-card"]:hover {{
      background: {t['superficie_2']};
      border: 1px solid {t['acento']};
    }}
    QLabel[variante="loja-hub-icone"] {{
      background: {t['acento']};
      color: {t['acento_texto']};
      border-radius: 10px;
      font-size: 18px;
      font-weight: 800;
    }}
    QLabel[variante="loja-hub-card-titulo"] {{
      color: {t['texto']};
      font-size: 14px;
      font-weight: 700;
      background: transparent;
    }}
    QLabel[variante="loja-hub-card-subtitulo"] {{
      color: {t['texto_fraco']};
      font-size: 11px;
      background: transparent;
    }}
    QPushButton[variante="voltar-pdv"] {{
      background: {t['superficie_2']};
      color: {t['texto']};
      border: 1px solid {t['borda']};
      border-radius: 12px;
      padding: 10px 18px;
      font-size: 12px;
      font-weight: 700;
    }}
    QPushButton[variante="voltar-pdv"]:hover {{ background: {t['borda']}; }}

    /* ---------- Configurações / placeholders simples (Estoque) ---------- */

    QLabel#configEyebrow {{
      color: {t['texto_fraquissimo']};
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 2px;
      background: transparent;
    }}
    QLabel#configTitulo {{ color: {t['texto']}; font-size: 26px; font-weight: 800; background: transparent; }}
    QLabel#configSubtitulo {{ color: {t['texto_fraco']}; font-size: 13px; background: transparent; }}
    QLabel#configSecaoTitulo {{
      color: {t['texto_fraquissimo']};
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      background: transparent;
    }}
    QFrame#configCard {{
      background: {t['superficie']};
      border: 1px solid {t['borda']};
      border-radius: 14px;
    }}

    /* ---------- Modais ---------- */

    QDialog {{ background: {t['superficie']}; }}
    """
