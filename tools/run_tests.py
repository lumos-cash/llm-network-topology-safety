import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.vendor'), str(ROOT)]
import pytest
raise SystemExit(pytest.main([str(ROOT / 'tests'), '-q', '--junitxml=' + str(ROOT / 'test-results.xml')] + sys.argv[1:]))

