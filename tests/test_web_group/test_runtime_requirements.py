"""Keeps requirements-runtime.txt honest about what the API actually needs.

The deployed image installs requirements-runtime.txt, not requirements.txt,
so anything api/ or utils/ imports must be satisfiable from the smaller file.
The failure mode this guards against is silent: an import added to a route
works locally (where the full requirements are installed) and only explodes at
container start, which is the worst place to find out.

The transitive edge matters as much as the direct one. api/routes/frontend.py
imports pipeline.builder for EXHIBIT_TYPES, and pipeline/builder.py imports
openpyxl at module scope — so openpyxl is a hard runtime dependency despite no
route importing it directly. This test follows those first-party edges rather
than only scanning api/ and utils/.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RUNTIME_REQS = REPO / "requirements-runtime.txt"

# Distribution name on PyPI → module name it installs, where they differ.
_DIST_TO_MODULE = {
    "python-multipart": "multipart",
    "uvicorn[standard]": "uvicorn",
    "beautifulsoup4": "bs4",
}

# First-party packages — these are copied into the image, not pip-installed.
_FIRST_PARTY = {"api", "utils", "pipeline", "downloader", "scripts", "tests"}

# Pulled in as transitive dependencies of the declared distributions, so they
# are present in the image without being named in requirements-runtime.txt.
_TRANSITIVE_OK = {
    "pydantic", "starlette", "anyio", "click", "h11", "certifi",
    "urllib3",  # installed by requests
}


def _declared_modules() -> set[str]:
    """Module names importable from requirements-runtime.txt."""
    mods: set[str] = set()
    for raw in RUNTIME_REQS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        # Strip version specifiers: "fastapi>=0.109,<1.0" → "fastapi"
        dist = line
        for sep in (">=", "<=", "==", "!=", "~=", ">", "<"):
            dist = dist.split(sep, 1)[0]
        dist = dist.strip()
        mods.add(_DIST_TO_MODULE.get(dist, dist.split("[", 1)[0]).lower())
    return mods


def _import_roots(path: Path, module_level_only: bool = True) -> set[str]:
    """Top-level module names imported by a Python file.

    With *module_level_only* (the default), imports nested inside a function
    body are ignored: they run when that function is called, not at import
    time, so they cannot stop the container from starting. This distinction is
    load-bearing — pipeline/builder.py imports pdfplumber, xlrd, and
    python_calamine inside its parsing functions, none of which the API ever
    calls, while its module-scope openpyxl import runs the moment
    api/routes/frontend.py touches it.

    Imports guarded by `try: ... except ImportError:` are skipped for the same
    reason: the module already handles their absence (pipeline/builder.py sets
    _HAS_CALAMINE / _HAS_XLRD that way), so they are optional accelerants, not
    requirements. Module-level `if:` blocks and class bodies still execute at
    import, so those are traversed.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
        return set()

    roots: set[str] = set()

    def _guards_importerror(node: ast.Try) -> bool:
        for handler in node.handlers:
            exc = handler.type
            names = []
            if isinstance(exc, ast.Name):
                names = [exc.id]
            elif isinstance(exc, ast.Tuple):
                names = [e.id for e in exc.elts if isinstance(e, ast.Name)]
            if {"ImportError", "ModuleNotFoundError"} & set(names):
                return True
        return False

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if module_level_only and isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            if isinstance(child, ast.Try) and _guards_importerror(child):
                continue
            if isinstance(child, ast.Import):
                for alias in child.names:
                    roots.add(alias.name.split(".", 1)[0])
            elif isinstance(child, ast.ImportFrom):
                # Relative imports resolve within the package — not third-party.
                if child.level == 0 and child.module:
                    roots.add(child.module.split(".", 1)[0])
            visit(child)

    visit(tree)
    return roots


def _first_party_modules_reachable_from_api() -> set[Path]:
    """API/utils sources plus the first-party modules they pull in.

    Follows pipeline.* and downloader.* edges one hop, which is where the
    non-obvious runtime dependencies live.
    """
    files: set[Path] = set()
    for pkg in ("api", "utils"):
        files.update((REPO / pkg).rglob("*.py"))

    extra: set[Path] = set()
    for f in list(files):
        for root in _import_roots(f):
            if root not in {"pipeline", "downloader"}:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    parts = node.module.split(".")
                    if parts[0] in {"pipeline", "downloader"} and len(parts) > 1:
                        candidate = REPO / parts[0] / f"{parts[1]}.py"
                        if candidate.exists():
                            extra.add(candidate)
    return files | extra


def test_runtime_requirements_file_exists():
    assert RUNTIME_REQS.exists(), "requirements-runtime.txt is missing"


def test_api_imports_are_satisfiable_from_runtime_requirements():
    """Every third-party import reachable from the API must be declared."""
    allowed = _declared_modules() | _FIRST_PARTY | _TRANSITIVE_OK
    stdlib = set(sys.stdlib_module_names)

    missing: dict[str, set[str]] = {}
    for path in sorted(_first_party_modules_reachable_from_api()):
        for root in _import_roots(path):
            if root in stdlib or root in allowed or root.startswith("_"):
                continue
            missing.setdefault(root, set()).add(
                str(path.relative_to(REPO)).replace("\\", "/")
            )

    assert not missing, (
        "Imports reachable from the API are not in requirements-runtime.txt — "
        "the container would fail to start:\n"
        + "\n".join(f"  {mod}: {sorted(files)}" for mod, files in sorted(missing.items()))
    )


def test_heavy_pipeline_deps_are_not_in_the_runtime_set():
    """The point of the split: parsing/automation stacks stay out of the image."""
    declared = _declared_modules()
    for heavy in ("pandas", "pdfplumber", "playwright", "pyarrow", "beautifulsoup4"):
        assert heavy not in declared, (
            f"{heavy} is a pipeline/downloader dependency; adding it to "
            "requirements-runtime.txt undoes the image slimming. If a route "
            "genuinely needs it, import it lazily inside the handler instead."
        )


def test_dockerfile_installs_the_runtime_requirements():
    """A correct requirements file does nothing if the image ignores it."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "requirements-runtime.txt" in dockerfile, (
        "Dockerfile does not install requirements-runtime.txt"
    )


@pytest.mark.parametrize("pkg", ["fastapi", "uvicorn", "jinja2", "openpyxl", "xlsxwriter"])
def test_core_runtime_packages_are_declared(pkg):
    assert pkg in _declared_modules()
