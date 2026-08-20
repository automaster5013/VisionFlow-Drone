#!/usr/bin/env python3
"""Classify repository changes for VisionFlow Docker Hub publishing."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


IMAGE_CONTEXTS: tuple[tuple[str, str], ...] = (
    ("frontend", "01_frontend/visionflow-web/"),
    ("backend", "02_backend/visionflow-api/"),
    ("ai", "03_ai-server/visionflow-ai/"),
)

FORCE_RELEASE_PATHS = {
    ".github/workflows/docker-publish.yml",
}


@dataclass(frozen=True, slots=True)
class ReleasePlan:
    release_required: bool
    changed_components: tuple[str, ...]
    reason: str


def normalize_path(value: str) -> str:
    return value.strip().replace("\\", "/")


def analyze_changed_paths(
    paths: Iterable[str],
    *,
    force: bool = False,
) -> ReleasePlan:
    normalized = tuple(
        path
        for raw in paths
        if (path := normalize_path(raw))
    )

    changed_components = tuple(
        component
        for component, prefix in IMAGE_CONTEXTS
        if any(path.startswith(prefix) for path in normalized)
    )

    if force:
        return ReleasePlan(
            True,
            changed_components,
            "manual-or-safe-fallback",
        )

    if any(path in FORCE_RELEASE_PATHS for path in normalized):
        return ReleasePlan(
            True,
            changed_components,
            "publish-workflow-changed",
        )

    if changed_components:
        return ReleasePlan(
            True,
            changed_components,
            "docker-build-context-changed",
        )

    return ReleasePlan(
        False,
        (),
        "no-docker-build-context-change",
    )


def append_output(path: Path, key: str, value: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{key}={value}\n")


def append_summary(
    path: Path,
    plan: ReleasePlan,
    changed_paths: tuple[str, ...],
) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("### Container release decision\n\n")
        handle.write(
            "- Release required: `"
            + ("yes" if plan.release_required else "no")
            + "`\n"
        )
        handle.write(f"- Reason: `{plan.reason}`\n")
        handle.write(
            "- Changed image contexts: `"
            + (
                ", ".join(plan.changed_components)
                if plan.changed_components
                else "none"
            )
            + "`\n"
        )
        if not plan.release_required:
            handle.write(
                "- Docker Hub: `SKIPPED` "
                "(no image build-context change)\n"
            )
        if changed_paths:
            handle.write("\n<details><summary>Changed paths</summary>\n\n")
            for changed in changed_paths:
                handle.write(f"- `{changed}`\n")
            handle.write("\n</details>\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--changed-paths-file",
        type=Path,
        required=True,
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    if not args.changed_paths_file.is_file():
        raise SystemExit(
            f"changed path list not found: {args.changed_paths_file}"
        )

    changed_paths = tuple(
        line.strip()
        for line in args.changed_paths_file.read_text(
            encoding="utf-8",
        ).splitlines()
        if line.strip()
    )
    plan = analyze_changed_paths(
        changed_paths,
        force=args.force,
    )

    if args.github_output is not None:
        append_output(
            args.github_output,
            "release_required",
            "true" if plan.release_required else "false",
        )
        append_output(
            args.github_output,
            "changed_components",
            ",".join(plan.changed_components),
        )
        append_output(
            args.github_output,
            "release_reason",
            plan.reason,
        )

    if args.summary is not None:
        append_summary(
            args.summary,
            plan,
            changed_paths,
        )

    print(
        "VISIONFLOW_CONTAINER_RELEASE="
        + ("REQUIRED" if plan.release_required else "SKIPPED")
    )
    print(f"reason={plan.reason}")
    print(
        "changed_components="
        + (
            ",".join(plan.changed_components)
            if plan.changed_components
            else "none"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
