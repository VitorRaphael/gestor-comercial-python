from pathlib import Path

_QSS_PATH = Path(__file__).resolve().parents[4] / "resources" / "qss" / "base.qss"


def carregar_stylesheet() -> str:
    """Lê o QSS base do tema escuro. Levanta FileNotFoundError se ausente."""
    return _QSS_PATH.read_text(encoding="utf-8")
