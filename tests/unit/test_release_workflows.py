import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_release_tooling_is_locked_and_installed_reproducibly():
    workflow = _read(".github/workflows/release.yml")
    release_config = json.loads(_read(".releaserc.json"))

    assert (ROOT / ".github" / "release" / "package.json").is_file()
    assert (ROOT / ".github" / "release" / "package-lock.json").is_file()
    assert "npm ci" in workflow
    assert "npm install --no-save" not in workflow
    assert release_config["plugins"] == [
        "@semantic-release/commit-analyzer",
        "@semantic-release/release-notes-generator",
    ]


def test_release_uses_exact_candidate_sha_for_every_gate_before_publication():
    workflow = _read(".github/workflows/release.yml")
    candidate_ref = "checkout_ref: ${{ needs.prepare_candidate.outputs.release_sha }}"

    assert "prepare_candidate:" in workflow
    assert "python_gate:" in workflow
    assert "frontend_gate:" in workflow
    assert "package_gate:" in workflow
    assert "publish_release:" in workflow
    assert workflow.count(candidate_ref) == 3
    assert "needs: [prepare_candidate, python_gate, frontend_gate]" in workflow
    assert "needs: [prepare_candidate, package_gate]" in workflow
    assert workflow.index("package_gate:") < workflow.index("publish_release:")


def test_validation_workflows_can_checkout_an_explicit_release_candidate():
    for workflow_name in (
        "python_lint_and_run_unit_tests.yml",
        "frontend_lint_and_build.yml",
        "integration_test_and_build_all_packages_ci.yml",
    ):
        workflow = (WORKFLOWS / workflow_name).read_text(encoding="utf-8")
        assert "workflow_call:" in workflow
        assert "checkout_ref:" in workflow
        assert "ref: ${{ inputs.checkout_ref || github.sha }}" in workflow


def test_master_package_ci_never_publishes_release_tags_or_pypi():
    workflow = _read(".github/workflows/integration_test_and_build_all_packages_ci.yml")
    master_branch = workflow.split("if [[ ${GITHUB_REF} == refs/heads/master ]]", 1)[1].split("elif", 1)[0]
    tag_branch = workflow.split("elif [[ ${GITHUB_REF} == refs/tags/* ]]", 1)[1].split("elif", 1)[0]

    assert 'append_publish_tag "latest"' not in master_branch
    assert 'append_publish_tag "${PY_VERSION}"' not in master_branch
    assert 'append_publish_tag "latest"' not in tag_branch
    assert 'append_publish_tag "${VERSION}"' not in tag_branch
    assert "github.ref == 'refs/heads/master'" not in workflow
    assert "startsWith(github.ref, 'refs/tags/')" not in workflow.split("Publish distribution package to PyPI", 1)[1]


def test_release_publication_requires_version_and_commit_integrity_checks():
    workflow = _read(".github/workflows/release.yml")

    assert "verify-release-integrity.py" in workflow
    assert "--expected-version" in workflow
    assert "--expected-sha" in workflow
    assert "gh release create" in workflow
    assert "packages-dir: pypi-dist/" in workflow
