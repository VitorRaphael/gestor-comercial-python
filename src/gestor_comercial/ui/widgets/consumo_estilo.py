"""O visual comum dos modais de consumo interno (assinatura e detalhes).

Montado dos tokens do tema ativo, não de cores fixas: no tema escuro dá o
cartão `#161514` com borda sutil e destaque âmbar; no claro, o mesmo cartão
claro que o resto do app. Os botões usam as `variante`s do QSS global.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from gestor_comercial.ui.theme.controller import ThemeController


def aplicar_estilo_cartao(modal: QDialog) -> None:
    t = ThemeController.instancia().tokens_atuais
    modal.setStyleSheet(
        f"""
        QDialog#{modal.objectName()} {{
            background: {t['superficie']};
            border: 1px solid {t['borda']};
            border-radius: 16px;
        }}
        QLabel {{ color: {t['texto']}; background: transparent; }}
        QLabel#consumoTitulo {{ font-size: 18px; font-weight: 700; }}
        QLabel#consumoSubtitulo, QLabel#consumoRotulo {{ color: {t['texto_fraco']}; }}
        QLabel#consumoRotulo {{ font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
        QLabel#consumoIcone {{ font-size: 26px; }}
        QFrame#consumoResumo {{
            border: 1px solid {t['aviso']};
            border-radius: 10px;
            background: transparent;
        }}
        QLabel#consumoResumoTexto, QLabel#consumoTotal {{
            color: {t['aviso']}; font-weight: 700; font-size: 15px;
        }}
        QLabel#consumoTotal {{ font-size: 20px; }}
        QFrame#consumoLinhaItem {{ border-bottom: 1px solid {t['borda']}; }}
        """
    )
