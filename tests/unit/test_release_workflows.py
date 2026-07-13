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


def test_release_configures_bot_identity_before_creating_annotated_tag():
    workflow = _read(".github/workflows/release.yml")
    publish_step = workflow.split("- name: Promote candidate commit and create draft release", 1)[1].split(
        "- name: Publish distribution package to PyPI", 1
    )[0]

    assert 'git config user.name "github-actions[bot]"' in publish_step
    assert 'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"' in publish_step
    assert publish_step.index("git config user.name") < publish_step.index('git tag -a "${RELEASE_TAG}"')


def test_release_recovery_revalidates_exact_artifacts_before_publication():
    recovery_path = WORKFLOWS / "recover_release.yml"

    assert recovery_path.is_file()
    workflow = recovery_path.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "source_run_id:" in workflow
    assert "release_sha:" in workflow
    assert "release_version:" in workflow
    assert "release_tag:" in workflow
    assert "packages: write" in workflow
    assert "verify-release-integrity.py" in workflow
    assert 'git merge-base --is-ancestor "${RELEASE_SHA}" origin/master' in workflow
    assert 'test "${tag_sha}" = "${RELEASE_SHA}"' in workflow
    assert "gh release download" in workflow
    assert "cmp --silent" in workflow
    assert 'docker buildx imagetools create -t "${image}:${RELEASE_VERSION}"' in workflow
    assert 'docker buildx imagetools create -t "${image}:latest"' in workflow
    assert 'gh release edit "${RELEASE_TAG}" --draft=false' in workflow


def test_issue_only_stale_jobs_cannot_close_pull_requests():
    workflow = _read(".github/workflows/issues-stale.yml")

    for step_name in ("Plugin Issues", "Documentation Issues"):
        step = workflow.split(f"- name: {step_name}", 1)[1]
        if "      - name:" in step:
            step = step.split("      - name:", 1)[0]
        assert "days-before-pr-stale: -1" in step
        assert "days-before-pr-close: -1" in step
