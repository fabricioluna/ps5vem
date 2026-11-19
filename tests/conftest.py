import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def config():
    return yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8"))


def fixture_text(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")
