# tests/conftest.py
import os, sys
# lägg till projektroten (mappen som innehåller "src") först i sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
