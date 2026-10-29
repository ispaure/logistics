"""Logistics build policy and adapters for the external build-deployment-manager."""
from pathlib import Path
import sys

# This is the trusted project adapter process, not the manager GUI. Bind the
# consumer's own dependency before importing the external manager's bootstrap.
# The standalone manager keeps its foreign-working-directory protection.
_project_source = Path(__file__).resolve().parents[1] / 'Python'
sys.path.insert(0, str(_project_source))
import commonUtils as _project_commonutils  # noqa: E402,F401
