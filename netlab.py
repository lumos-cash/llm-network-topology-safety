"""Entry point; .vendor is a project-local optional dependency directory."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if (ROOT / '.vendor').is_dir():
    sys.path.insert(0, str(ROOT / '.vendor'))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

if __name__ == '__main__':
    from netlab.cli import main
    raise SystemExit(main())

