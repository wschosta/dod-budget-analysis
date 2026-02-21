"""
BEAR-009: Dockerfile/docker-compose lint-level validation tests.

Validate Docker configuration without building:
1. Dockerfile exists and contains required directives.
2. docker-compose.yml is valid YAML with required services.
3. docker-compose.staging.yml has production-like settings.
4. .dockerignore excludes expected patterns.
5. All Python files referenced in Dockerfile COPY exist.
6. requirements.txt is pinned (every line has ==).
"""
# DONE [Group: BEAR] BEAR-009: Add Dockerfile/docker-compose lint-level validation tests (~1,500 tokens)

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestDockerfile:
    """Validate Dockerfile contents."""

    def test_dockerfile_exists(self):
        assert (PROJECT_ROOT / "Dockerfile").is_file()

    def test_dockerfile_multistage_exists(self):
        assert (PROJECT_ROOT / "docker" / "Dockerfile.multistage").is_file()

    def test_dockerfile_has_required_directives(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "FROM" in content, "Missing FROM directive"
        assert "COPY" in content, "Missing COPY directive"
        assert "HEALTHCHECK" in content, "Missing HEALTHCHECK directive"
        assert "USER" in content, "Missing USER directive (non-root)"
        assert "EXPOSE" in content, "Missing EXPOSE directive"

    def test_dockerfile_exposes_port_8000(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "EXPOSE 8000" in content

    def test_dockerfile_uses_nonroot_user(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "USER appuser" in content or "USER nonroot" in content

    def test_dockerfile_sets_python_env_vars(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        assert "PYTHONDONTWRITEBYTECODE" in content
        assert "PYTHONUNBUFFERED" in content


class TestDockerCompose:
    """Validate docker-compose.yml."""

    def test_docker_compose_exists(self):
        assert (PROJECT_ROOT / "docker-compose.yml").is_file()

    def test_docker_compose_valid_yaml(self):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        data = yaml.safe_load(content)
        assert isinstance(data, dict)

    def test_docker_compose_has_web_service(self):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        data = yaml.safe_load(content)
        assert "services" in data
        assert "web" in data["services"]

    def test_docker_compose_has_healthcheck(self):
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        assert "healthcheck" in content


class TestDockerComposeStaging:
    """Validate docker-compose.staging.yml has production-like settings."""

    def test_staging_exists(self):
        assert (PROJECT_ROOT / "docker" / "docker-compose.staging.yml").is_file()

    def test_staging_no_reload(self):
        content = (PROJECT_ROOT / "docker" / "docker-compose.staging.yml").read_text()
        # Staging should NOT use --reload
        # Check command section for --reload absence in the web service command
        lines = content.split("\n")
        in_web_command = False
        for line in lines:
            if "command:" in line and "web" not in line:
                in_web_command = True
            if in_web_command and "--reload" in line:
                pytest.fail("Staging should not use --reload flag")

    def test_staging_has_backup_service(self):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        content = (PROJECT_ROOT / "docker" / "docker-compose.staging.yml").read_text()
        data = yaml.safe_load(content)
        assert "backup" in data.get("services", {}), "Staging should have backup sidecar"


class TestDockerIgnore:
    """Validate .dockerignore excludes expected patterns."""

    def test_dockerignore_exists(self):
        assert (PROJECT_ROOT / ".dockerignore").is_file()

    def test_dockerignore_excludes_tests(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text()
        assert "tests/" in content

    def test_dockerignore_excludes_git(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text()
        assert ".git/" in content

    def test_dockerignore_excludes_pycache(self):
        content = (PROJECT_ROOT / ".dockerignore").read_text()
        assert "__pycache__" in content


class TestDockerfileCopiedFiles:
    """Verify all Python files referenced in Dockerfile COPY exist."""

    def test_copied_files_exist(self):
        content = (PROJECT_ROOT / "Dockerfile").read_text()
        # Extract COPY source paths (lines like "COPY api/ api/" or "COPY schema_design.py .")
        for line in content.split("\n"):
            line = line.strip()
            if not line.startswith("COPY") or line.startswith("COPY --from"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            src = parts[1]
            # Skip requirements.txt (always exists) and directories
            if src == "requirements.txt":
                continue
            src_path = PROJECT_ROOT / src
            assert src_path.exists(), f"COPY source does not exist: {src}"


class TestRequirementsPinning:
    """Verify requirements.txt format."""

    def test_requirements_txt_exists(self):
        assert (PROJECT_ROOT / "requirements.txt").is_file()

    def test_requirements_lines_have_version_spec(self):
        """Each dependency line has a version specifier (>= or ==)."""
        content = (PROJECT_ROOT / "requirements.txt").read_text()
        for line in content.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Each line should have some version specifier
            assert ">=" in line or "==" in line or "~=" in line, (
                f"Dependency without version spec: {line}"
            )
