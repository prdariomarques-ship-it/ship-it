__version__ = '1.0.0'

import sys
from pathlib import Path

# Adicionar diretório base ao path para imports funcionarem
BASE_DIR = Path(__file__).parent.absolute()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
