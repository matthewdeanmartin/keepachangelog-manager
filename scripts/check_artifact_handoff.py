"""Verify that upload-artifact/download-artifact pairs within each workflow
file agree on artifact name and path.

Scans every workflow under .github/workflows/*.yml generically (no
hardcoded file/job names), so it keeps working as workflows are renamed,
merged, or split.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(".github/workflows")


def iter_steps(jobs: dict) -> list[tuple[str, dict]]:
    steps = []
    for job_name, job in jobs.items():
        for step in job.get("steps", []) or []:
            steps.append((job_name, step))
    return steps


def check_workflow(path: Path) -> list[str]:
    errors = []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = data.get("jobs", {}) or {}
    steps = iter_steps(jobs)

    uploads = [
        (job_name, step)
        for job_name, step in steps
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    downloads = [
        (job_name, step)
        for job_name, step in steps
        if step.get("uses", "").startswith("actions/download-artifact@")
    ]

    if not uploads and not downloads:
        return errors

    if uploads and not downloads:
        errors.append(f"{path.name}: has upload-artifact but no matching download-artifact")
        return errors
    if downloads and not uploads:
        errors.append(f"{path.name}: has download-artifact but no matching upload-artifact")
        return errors

    for upload_job, upload_step in uploads:
        upload_with = upload_step.get("with", {}) or {}
        for download_job, download_step in downloads:
            download_with = download_step.get("with", {}) or {}
            if upload_with.get("name") != download_with.get("name"):
                errors.append(
                    f"{path.name}: artifact name mismatch between "
                    f"{upload_job} ({upload_with.get('name')!r}) and "
                    f"{download_job} ({download_with.get('name')!r})"
                )
            if upload_with.get("path") != download_with.get("path"):
                errors.append(
                    f"{path.name}: artifact path mismatch between "
                    f"{upload_job} ({upload_with.get('path')!r}) and "
                    f"{download_job} ({download_with.get('path')!r})"
                )

    if not errors:
        print(f"Artifact handoff OK for {path.name}")

    return errors


def main() -> int:
    all_errors: list[str] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        all_errors.extend(check_workflow(path))

    for error in all_errors:
        print(f"::error::{error}")

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
