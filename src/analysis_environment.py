"""Reject an unverified notebook environment before loading research data."""

import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REQUIREMENTS_PATH = Path(__file__).resolve().parents[1] / "requirements.txt"


def validate_analysis_environment():
    """Check the runtime pins without importing the scientific libraries."""
    problems = []
    if sys.version_info[:2] != (3, 12):
        problems.append(f"Python: running {sys.version.split()[0]}; required 3.12")

    for line in REQUIREMENTS_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        try:
            installed = version(requirement.name)
        except PackageNotFoundError:
            problems.append(f"{requirement.name}: missing; required {requirement.specifier}")
            continue
        if not requirement.specifier.contains(installed, prereleases=True):
            problems.append(
                f"{requirement.name}: installed {installed}; required {requirement.specifier}"
            )
        name = canonicalize_name(requirement.name)
        module_name = {"pillow": "PIL", "scikit-learn": "sklearn", "ipython": "IPython"}.get(
            name, name.replace("-", "_")
        )
        loaded = getattr(sys.modules.get(module_name), "__version__", None)
        if loaded is not None and str(loaded) != installed and not requirement.specifier.contains(str(loaded), prereleases=True):
            problems.append(f"{requirement.name}: this kernel has {loaded} loaded; restart it")

    if problems:
        details = "\n".join(f"- {problem}" for problem in problems)
        raise RuntimeError(
            "Analysis environment does not match requirements.txt.\n"
            f"Python executable: {os.path.relpath(sys.executable)}\n{details}\n"
            "Select the 'Voting mortality (pinned)' kernel from the project's .venv, "
            "restart the kernel and run all cells from the beginning. "
            "Installing requirements in a terminal does not switch a running notebook. "
            "For command-line execution, use .venv/bin/python scripts/run_analysis.py "
            "(Windows: .venv\\Scripts\\python.exe). "
            "See docs/reproducibility.md for environment setup. "
            "Do not replace the pinned result hashes to bypass this mismatch."
        )
    print(f"Analysis environment matches requirements.txt. Python: {os.path.relpath(sys.executable)}")
