#!/usr/bin/env python3
"""Release validation for the go-turbo skill collection.

The validator intentionally uses only the Python standard library so a fresh
checkout can run the same gate locally and in CI.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIMARY = "go-turbo"
ALLOWED_SKILL_FRONTMATTER = {
    "name",
    "description",
    "disable-model-invocation",
    "argument-hint",
}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
REPOSITORY_URL = "https://github.com/hendriknielaender/go-turbo"
PLUGIN_CATEGORIES = {
    "Productivity",
    "Creativity",
    "Developer Tools",
    "Business & Operations",
    "Data & Analytics",
    "Communication",
    "Education & Research",
    "Security",
    "Finance",
    "Healthcare",
    "Travel",
    "Entertainment",
    "Other",
}
IGNORED_SCAN_DIRECTORIES = {".git", "node_modules", "dist", "__pycache__"}

REQUIRED_REFERENCES = {
    "admission-control.md",
    "aead-nonces.md",
    "backpressure.md",
    "base64.md",
    "batching.md",
    "benchmark-inputs.md",
    "binary-encoding.md",
    "block-profiles.md",
    "bounded-queues.md",
    "bounding-concurrency.md",
    "bounds-check-elimination.md",
    "buffering.md",
    "build-experiments.md",
    "build-flags.md",
    "caller-owned-buffers.md",
    "cgo.md",
    "channels.md",
    "choosing-structures.md",
    "circuit-breakers.md",
    "comparing-benchmarks.md",
    "compiler-diagnostics.md",
    "compression.md",
    "connection-scale.md",
    "context-cancellation.md",
    "dns.md",
    "escape-analysis.md",
    "escape-causes.md",
    "files-and-mmap.md",
    "finding-allocations.md",
    "framing.md",
    "gc-cost.md",
    "gc-diagnosis.md",
    "gc-tuning.md",
    "gomaxprocs.md",
    "goroutine-budgets.md",
    "goroutine-leaks.md",
    "graceful-shutdown.md",
    "grpc.md",
    "hashing.md",
    "heaps.md",
    "hot-dispatch.md",
    "http-client-config.md",
    "http-connection-reuse.md",
    "http-servers.md",
    "http-versions.md",
    "http2-tuning.md",
    "httptrace.md",
    "immutable-snapshots.md",
    "in-place-transforms.md",
    "inlining.md",
    "interface-boxing.md",
    "interpreting-results.md",
    "json.md",
    "load-shedding.md",
    "load-testing.md",
    "map-vs-slice.md",
    "memory-layout.md",
    "monotonic-stacks.md",
    "mutexes-and-atomics.md",
    "necessary-escapes.md",
    "netpoll.md",
    "object-lifetime.md",
    "pgo.md",
    "pointer-density.md",
    "pooling.md",
    "pprof.md",
    "presizing.md",
    "protocol-selection.md",
    "queues-and-rings.md",
    "quic.md",
    "rate-limiting.md",
    "request-deadlines.md",
    "resource-budgets.md",
    "retention.md",
    "retries.md",
    "run-metadata.md",
    "same-host-comparison.md",
    "sample-variance.md",
    "scheduler-state.md",
    "sharding.md",
    "socket-options.md",
    "sorting.md",
    "stream-copies.md",
    "strings-and-bytes.md",
    "tcp-framing.md",
    "text-processing.md",
    "tls.md",
    "udp.md",
    "upgrade-experiment.md",
    "value-semantics.md",
    "workflow.md",
    "writing-benchmarks.md",
}

# Each group describes a capability the knowledge base promises. At least one
# phrase in every tuple must appear in that reference. Keep these as domain
# contracts, not as a prose snapshot, so authors can rewrite sections freely.
COVERAGE: dict[str, tuple[tuple[str, ...], ...]] = {
    "admission-control.md": (
        ("bounded", "admission"),
        ("admission control",),
    ),
    "aead-nonces.md": (
        ("newgcmwithrandomnonce",),
    ),
    "backpressure.md": (
        ("backpressure",),
    ),
    "base64.md": (
        ("base64",),
    ),
    "batching.md": (
        ("flush",),
        ("batch",),
        ("lock",),
    ),
    "binary-encoding.md": (
        ("binary.append", "binary.encode"),
    ),
    "bounded-queues.md": (
        ("queue",),
    ),
    "bounds-check-elimination.md": (
        ("bounds-check", "bounds check"),
    ),
    "buffering.md": (
        ("buffer",),
    ),
    "build-flags.md": (
        ("build tag", "//go:build"),
    ),
    "cgo.md": (
        ("cgo",),
    ),
    "circuit-breakers.md": (
        ("circuit breaker", "circuit-breaker"),
    ),
    "compiler-diagnostics.md": (
        ("disassembly", "objdump"),
    ),
    "compression.md": (
        ("compression", "gzip", "zstd"),
    ),
    "connection-scale.md": (
        ("accept",),
    ),
    "context-cancellation.md": (
        ("cancellation", "context"),
    ),
    "dns.md": (
        ("dns",),
    ),
    "escape-analysis.md": (
        ("-m=2",),
    ),
    "escape-causes.md": (
        ("closure",),
    ),
    "files-and-mmap.md": (
        ("slice", "map"),
        ("mmap",),
    ),
    "gc-tuning.md": (
        ("gogc",),
        ("gomemlimit",),
    ),
    "gomaxprocs.md": (
        ("gomaxprocs",),
    ),
    "goroutine-budgets.md": (
        ("goroutine", "stack"),
    ),
    "goroutine-leaks.md": (
        ("leak",),
    ),
    "grpc.md": (
        ("grpc",),
    ),
    "hashing.md": (
        ("hash.hash", "streaming hasher"),
    ),
    "heaps.md": (
        ("priority queue", "container/heap"),
    ),
    "hot-dispatch.md": (
        ("inlining",),
    ),
    "http-client-config.md": (
        ("http.transport",),
    ),
    "http-versions.md": (
        ("decoder", "stream"),
        ("http/3",),
    ),
    "http2-tuning.md": (
        ("http/2",),
    ),
    "httptrace.md": (
        ("observability", "httptrace"),
    ),
    "inlining.md": (
        ("devirtual",),
    ),
    "interface-boxing.md": (
        ("interface", "boxing"),
        ("interface",),
    ),
    "interpreting-results.md": (
        ("rollout", "canary"),
        ("rollback",),
    ),
    "json.md": (
        ("json",),
    ),
    "load-shedding.md": (
        ("load shedding", "shed"),
        ("retry-after",),
    ),
    "load-testing.md": (
        ("coordinated omission", "open-loop"),
    ),
    "memory-layout.md": (
        ("false sharing", "false-sharing"),
        ("alias",),
    ),
    "mutexes-and-atomics.md": (
        ("mutex", "atomic"),
    ),
    "netpoll.md": (
        ("netpoll",),
    ),
    "object-lifetime.md": (
        ("lifetime",),
        ("weak",),
        ("cleanup", "finalizer"),
    ),
    "pgo.md": (
        ("profile-guided optimization", "pgo"),
    ),
    "pooling.md": (
        ("sync.pool",),
    ),
    "pprof.md": (
        ("pprof",),
    ),
    "presizing.md": (
        ("preallocate", "preallocation"),
    ),
    "queues-and-rings.md": (
        ("ring", "queue"),
    ),
    "quic.md": (
        ("quic",),
        ("replay-safe", "replay safe"),
    ),
    "rate-limiting.md": (
        ("rate limiting", "token bucket"),
    ),
    "request-deadlines.md": (
        ("deadline", "timeout"),
        ("timeout",),
    ),
    "retention.md": (
        ("backing-store retention", "backing array"),
    ),
    "retries.md": (
        ("retry",),
        ("degraded", "degradation"),
        ("idempot",),
    ),
    "sample-variance.md": (
        ("benchstat",),
        ("allocs/op",),
    ),
    "sharding.md": (
        ("shard",),
    ),
    "socket-options.md": (
        ("so_reuseport", "socket option", "setsockopt"),
    ),
    "sorting.md": (
        ("sort",),
    ),
    "strings-and-bytes.md": (
        ("strings.builder",),
        ("[]byte",),
    ),
    "text-processing.md": (
        ("regexp", "regex"),
        ("strconv.append", "appendint"),
    ),
    "tls.md": (
        ("tls",),
    ),
    "udp.md": (
        ("udp",),
    ),
    "upgrade-experiment.md": (
        ("go version", "toolchain"),
    ),
    "workflow.md": (
        ("cruise",),
        ("redline",),
        ("complexity", "cost model"),
    ),
    "writing-benchmarks.md": (
        ("b.loop",),
        ("benchmark",),
    ),
}

errors: list[str] = []
checks = 0


def fail(message: str) -> None:
    errors.append(message)


def checked() -> None:
    global checks
    checks += 1


def rel(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def check_branding_image(path: pathlib.Path) -> None:
    checked()
    relative = rel(path)
    if path.stat().st_size > 5 * 1024 * 1024:
        fail(f"{relative}: branding image must not exceed 5 MiB")
        return

    width: float
    height: float
    if path.suffix.casefold() == ".png":
        header = path.read_bytes()[:24]
        if (
            len(header) != 24
            or header[:8] != b"\x89PNG\r\n\x1a\n"
            or header[12:16] != b"IHDR"
        ):
            fail(f"{relative}: malformed PNG header")
            return
        width = float(int.from_bytes(header[16:20], "big"))
        height = float(int.from_bytes(header[20:24], "big"))
    elif path.suffix.casefold() == ".svg":
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
        except (ET.ParseError, UnicodeDecodeError) as exc:
            fail(f"{relative}: malformed SVG: {exc}")
            return
        if root.tag.rsplit("}", 1)[-1] != "svg":
            fail(f"{relative}: SVG root element must be <svg>")
            return
        view_box = root.attrib.get("viewBox", "").replace(",", " ").split()
        try:
            if len(view_box) == 4:
                width, height = float(view_box[2]), float(view_box[3])
            else:
                width = float(root.attrib["width"])
                height = float(root.attrib["height"])
        except (KeyError, ValueError):
            fail(f"{relative}: SVG must declare numeric dimensions")
            return
    else:
        fail(f"{relative}: branding image must be PNG or SVG")
        return


def split_frontmatter(text: str, path: pathlib.Path) -> tuple[dict[str, str], str] | None:
    """Parse the flat YAML subset used by skill frontmatter."""
    if not text.startswith("---\n"):
        fail(f"{rel(path)}: missing YAML frontmatter")
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        fail(f"{rel(path)}: unterminated YAML frontmatter")
        return None

    lines = text[4:end].splitlines()
    data: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):(?:\s*(.*))?", line)
        if not match:
            fail(f"{rel(path)}: invalid flat frontmatter line: {line!r}")
            return None
        key, value = match.group(1), (match.group(2) or "").strip()
        if key in data:
            fail(f"{rel(path)}: duplicate frontmatter key {key!r}")
            return None
        index += 1

        if value in {">", "|-", "|", ">-"}:
            folded: list[str] = []
            while index < len(lines) and (not lines[index] or lines[index][0].isspace()):
                folded.append(lines[index].strip())
                index += 1
            value = " ".join(part for part in folded if part)
        elif ((value.startswith('"') and value.endswith('"')) or
              (value.startswith("'") and value.endswith("'"))):
            value = value[1:-1]
        data[key] = value

    return data, text[end + 5 :]


def parse_openai_yaml(path: pathlib.Path) -> dict[str, dict[str, Any]] | None:
    """Parse the deliberately small agents/openai.yaml schema we publish."""
    result: dict[str, dict[str, Any]] = {}
    section: str | None = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        top = re.fullmatch(r"([a-z_]+):", raw)
        if top:
            section = top.group(1)
            if section in result:
                fail(f"{rel(path)}:{number}: duplicate section {section!r}")
                return None
            result[section] = {}
            continue
        child = re.fullmatch(r"  ([a-z_]+):\s*(.+)", raw)
        if not child or section is None:
            fail(f"{rel(path)}:{number}: unsupported YAML shape")
            return None
        key, scalar = child.groups()
        if key in result[section]:
            fail(f"{rel(path)}:{number}: duplicate key {key!r}")
            return None
        if scalar in {"true", "false"}:
            value: Any = scalar == "true"
        else:
            try:
                value = json.loads(scalar)
            except json.JSONDecodeError:
                fail(f"{rel(path)}:{number}: scalar must be JSON-quoted or boolean")
                return None
        result[section][key] = value
    return result


def check_skills() -> set[str]:
    names: set[str] = set()
    paths = sorted((ROOT / "skills").glob("*/SKILL.md"))
    if not paths:
        fail("skills/: no SKILL.md files found")
        return names

    for path in paths:
        checked()
        text = path.read_text(encoding="utf-8")
        parsed = split_frontmatter(text, path)
        if parsed is None:
            continue
        frontmatter, body = parsed
        extra = set(frontmatter) - ALLOWED_SKILL_FRONTMATTER
        if extra:
            fail(f"{rel(path)}: unsupported frontmatter keys {sorted(extra)}")

        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")
        if not NAME_RE.fullmatch(name) or len(name) > 64:
            fail(f"{rel(path)}: invalid skill name {name!r}")
        elif name != path.parent.name:
            fail(f"{rel(path)}: name {name!r} does not match directory")
        else:
            names.add(name)

        disabled = frontmatter.get("disable-model-invocation")
        if name == PRIMARY:
            if disabled is not None:
                fail(f"{rel(path)}: the primary skill must stay model-invocable")
        elif disabled != "true":
            fail(
                f"{rel(path)}: companion skills must set "
                f"disable-model-invocation: true so only {PRIMARY} auto-triggers"
            )

        # The primary skill is model-invoked, so its description is the trigger and
        # earns the richer floor. Companions fire only when a human types them, so
        # their description is a human-facing one-liner; padding it to 80 buys
        # nothing and costs always-loaded context on every turn.
        floor = 80 if name == PRIMARY else 40
        if not floor <= len(description) <= 1024:
            fail(
                f"{rel(path)}: description length {len(description)} "
                f"is outside {floor}..1024"
            )
        if len(text.splitlines()) > 500:
            fail(f"{rel(path)}: exceeds the 500-line skill guideline")
        if re.search(r"(?:^|\s)/go-turbo(?:\s|$)", body, re.MULTILINE):
            fail(f"{rel(path)}: uses a slash invocation instead of a $skill invocation")
        if re.search(r"stay active|level sticks|persists until|persistent mode", body, re.I):
            fail(f"{rel(path)}: claims unsupported cross-task persistence")

        metadata_path = path.parent / "agents" / "openai.yaml"
        if not metadata_path.is_file():
            fail(f"{rel(metadata_path)}: missing Codex metadata")
            continue
        checked()
        metadata = parse_openai_yaml(metadata_path)
        if metadata is None:
            continue
        if set(metadata) != {"interface", "policy"}:
            fail(f"{rel(metadata_path)}: expected interface and policy sections")
            continue
        interface = metadata["interface"]
        policy = metadata["policy"]
        if set(interface) != {"display_name", "short_description", "default_prompt"}:
            fail(f"{rel(metadata_path)}: incomplete or unexpected interface fields")
        if set(policy) != {"allow_implicit_invocation"}:
            fail(f"{rel(metadata_path)}: incomplete or unexpected policy fields")

        short = interface.get("short_description")
        prompt = interface.get("default_prompt")
        implicit = policy.get("allow_implicit_invocation")
        if not isinstance(short, str) or not 25 <= len(short) <= 64:
            fail(f"{rel(metadata_path)}: short_description must be 25..64 characters")
        if not isinstance(prompt, str) or f"${name}" not in prompt:
            fail(f"{rel(metadata_path)}: default_prompt must explicitly invoke ${name}")
        expected_implicit = name == PRIMARY
        if implicit is not expected_implicit:
            fail(f"{rel(metadata_path)}: allow_implicit_invocation must be {str(expected_implicit).lower()}")

    return names


def check_codex_discovery(skill_names: set[str]) -> None:
    exposed_dir = ROOT / ".agents" / "skills"
    if not exposed_dir.is_dir():
        fail(f"{rel(exposed_dir)}: missing Codex discovery directory")
        return

    exposed = {path.name for path in exposed_dir.iterdir()}
    if exposed != skill_names:
        fail(
            f"{rel(exposed_dir)}: exposed skills do not match skill inventory; "
            f"expected={sorted(skill_names)}, found={sorted(exposed)}"
        )
    for name in sorted(skill_names):
        expected = exposed_dir / name
        checked()
        if not expected.is_symlink():
            fail(f"{rel(expected)}: expected a repository-local skill symlink")
            continue
        if expected.resolve() != (ROOT / "skills" / name).resolve():
            fail(f"{rel(expected)}: symlink target is not skills/{name}")
        if not (expected / "SKILL.md").is_file():
            fail(f"{rel(expected)}: symlink does not expose SKILL.md")


def check_references() -> None:
    refs_dir = ROOT / "skills" / PRIMARY / "references"
    paths = sorted(refs_dir.glob("*.md"))
    actual = {path.name for path in paths}
    checked()
    if actual != REQUIRED_REFERENCES:
        missing = sorted(REQUIRED_REFERENCES - actual)
        extra = sorted(actual - REQUIRED_REFERENCES)
        fail(f"{rel(refs_dir)}: reference inventory mismatch; missing={missing}, extra={extra}")

    core = (ROOT / "skills" / PRIMARY / "SKILL.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for path in paths:
        checked()
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        if f"references/{path.name}" not in core:
            fail(f"{rel(path)}: not directly routed from the primary SKILL.md")
        if f"`{path.name}`" not in readme:
            fail(f"{rel(path)}: not listed in README.md")
        # An index earns its place only where there is something to navigate:
        # a long file with several sections. One entry is the title restated.
        sections = len(re.findall(r"^## (?!Contents$)", text, re.M))
        if len(text.splitlines()) > 100 and sections >= 3 and "## Contents" not in text:
            fail(f"{rel(path)}: long multi-section reference needs a Contents section")
        if "## Contents" in text and sections < 3:
            fail(f"{rel(path)}: Contents index with {sections} section(s) is furniture")
        for alternatives in COVERAGE.get(path.name, ()):
            if not any(phrase in lower for phrase in alternatives):
                fail(f"{rel(path)}: missing capability phrase from {alternatives}")


def read_json(relative: str) -> dict[str, Any] | None:
    path = ROOT / relative
    checked()
    if not path.is_file():
        fail(f"{relative}: missing")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{relative}: invalid JSON: {exc}")
        return None
    if not isinstance(data, dict):
        fail(f"{relative}: top level must be a JSON object")
        return None
    return data


def check_public_interface(manifest: dict[str, Any], relative: str) -> None:
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        fail(f"{relative}: interface must be an object")
        return

    limits = {
        "displayName": 30,
        "shortDescription": 30,
        "longDescription": 4000,
        "developerName": 80,
    }
    for field, limit in limits.items():
        value = interface.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            fail(f"{relative}: interface.{field} must be 1..{limit} characters")
        elif field != "longDescription" and "\n" in value:
            fail(f"{relative}: interface.{field} must fit on one line")

    author = manifest.get("author")
    if not isinstance(author, dict) or author.get("name") != interface.get("developerName"):
        fail(f"{relative}: author.name and interface.developerName must match")

    category = interface.get("category")
    if category not in PLUGIN_CATEGORIES:
        fail(f"{relative}: unsupported interface.category {category!r}")

    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 20:
        fail(f"{relative}: interface.capabilities must contain 1..20 entries")
    else:
        for value in capabilities:
            if not isinstance(value, str) or not value.strip() or len(value) > 120 or "\n" in value:
                fail(f"{relative}: every capability must be a non-empty one-line string <=120 characters")

    prompts = interface.get("defaultPrompt")
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
        fail(f"{relative}: interface.defaultPrompt must contain 1..3 entries")
    else:
        normalized: set[str] = set()
        for value in prompts:
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 128
                or "\n" in value
                or "@" in value
            ):
                fail(f"{relative}: every starter prompt must be one line, <=128 characters, and contain no @mention")
                continue
            key = " ".join(value.casefold().split())
            if key in normalized:
                fail(f"{relative}: starter prompts must be unique")
            normalized.add(key)

    for field in (
        "websiteURL",
        "privacyPolicyURL",
        "termsOfServiceURL",
    ):
        url = interface.get(field)
        if not isinstance(url, str) or not url.startswith("https://") or len(url) > 1024:
            fail(f"{relative}: interface.{field} must be an HTTPS URL <=1024 characters")

    for field in ("brandColor",):
        color = interface.get(field)
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            fail(f"{relative}: interface.{field} must be a six-digit hex color")

    for field in ("composerIcon", "logo"):
        value = interface.get(field)
        if not isinstance(value, str) or not value.startswith("./assets/"):
            fail(f"{relative}: interface.{field} must point inside ./assets/")
            continue
        asset = ROOT / value.removeprefix("./")
        if not asset.is_file() or asset.is_symlink():
            fail(f"{relative}: interface.{field} must reference a regular file")
            continue
        check_branding_image(asset)


def check_manifests(skill_names: set[str]) -> None:
    package = read_json("package.json")
    codex = read_json(".codex-plugin/plugin.json")
    claude = read_json(".claude-plugin/plugin.json")
    codex_marketplace = read_json(".agents/plugins/marketplace.json")
    claude_marketplace = read_json(".claude-plugin/marketplace.json")
    lock = read_json("package-lock.json")

    if package is None:
        return
    version = package.get("version")
    if package.get("name") != PRIMARY:
        fail(f"package.json: name must be {PRIMARY!r}")
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        fail(f"package.json: invalid semantic version {version!r}")
    if package.get("private") is not True:
        fail("package.json: release authority must remain private")
    if package.get("license") != "MIT":
        fail("package.json: license must be MIT")
    repository = package.get("repository")
    if not isinstance(repository, dict) or repository.get("url") != REPOSITORY_URL:
        fail(f"package.json: repository URL must be {REPOSITORY_URL}")
    scripts = package.get("scripts")
    required_scripts = {
        "changeset",
        "version",
        "check-plugin-versions",
        "validate",
    }
    if not isinstance(scripts, dict) or not required_scripts <= set(scripts):
        fail(f"package.json: missing release scripts {sorted(required_scripts)}")
    elif "release:tag" in scripts:
        fail("package.json: Changesets must not own tag creation")
    dependencies = package.get("devDependencies")
    if not isinstance(dependencies, dict) or not {
        "@changesets/changelog-github",
        "@changesets/cli",
    } <= set(dependencies):
        fail("package.json: missing Changesets release dependencies")

    expected_skills = [f"./skills/{name}" for name in sorted(skill_names)]
    for relative, manifest in (
        (".codex-plugin/plugin.json", codex),
        (".claude-plugin/plugin.json", claude),
    ):
        if manifest is None:
            continue
        if manifest.get("name") != PRIMARY:
            fail(f"{relative}: name must be {PRIMARY!r}")
        if manifest.get("version") != version:
            fail(f"{relative}: version must match package.json")
        if manifest.get("license") != "MIT":
            fail(f"{relative}: license must be MIT")
        if manifest.get("repository") != REPOSITORY_URL:
            fail(f"{relative}: repository must be {REPOSITORY_URL}")

    if codex is not None:
        if codex.get("skills") != "./skills/":
            fail(".codex-plugin/plugin.json: skills must be './skills/'")
        check_public_interface(codex, ".codex-plugin/plugin.json")
        for name in skill_names:
            if len(f"{PRIMARY}:{name}") > 64:
                fail(f".codex-plugin/plugin.json: combined skill identity is too long for {name}")

    if claude is not None and claude.get("skills") != expected_skills:
        fail(
            ".claude-plugin/plugin.json: explicit skill allowlist must exactly match "
            f"{expected_skills}"
        )

    if codex_marketplace is not None:
        if codex_marketplace.get("name") != PRIMARY:
            fail(f".agents/plugins/marketplace.json: name must be {PRIMARY!r}")
        market_interface = codex_marketplace.get("interface")
        if not isinstance(market_interface, dict) or not market_interface.get("displayName"):
            fail(".agents/plugins/marketplace.json: interface.displayName is required")
        entries = codex_marketplace.get("plugins")
        if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
            fail(".agents/plugins/marketplace.json: expected exactly one plugin entry")
        else:
            entry = entries[0]
            source = entry.get("source")
            policy = entry.get("policy")
            if entry.get("name") != PRIMARY:
                fail(f".agents/plugins/marketplace.json: plugin name must be {PRIMARY!r}")
            if source != {"source": "local", "path": "./"}:
                fail(".agents/plugins/marketplace.json: local source must point at the plugin root")
            if policy != {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}:
                fail(".agents/plugins/marketplace.json: install and authentication policy drift")
            if codex is not None and entry.get("category") != codex.get("interface", {}).get("category"):
                fail(".agents/plugins/marketplace.json: category must match the Codex manifest")

    if claude_marketplace is not None:
        if claude_marketplace.get("name") != PRIMARY:
            fail(f".claude-plugin/marketplace.json: name must be {PRIMARY!r}")
        entries = claude_marketplace.get("plugins")
        if not isinstance(entries, list) or len(entries) != 1:
            fail(".claude-plugin/marketplace.json: expected exactly one plugin entry")
        elif entries[0].get("name") != PRIMARY or entries[0].get("source") != "./":
            fail(".claude-plugin/marketplace.json: plugin must resolve from repository root")

    if lock is not None:
        root_package = lock.get("packages", {}).get("") if isinstance(lock.get("packages"), dict) else None
        if not isinstance(root_package, dict):
            fail("package-lock.json: missing root package")
        elif root_package.get("name") != PRIMARY or root_package.get("version") != version:
            fail("package-lock.json: root name and version must match package.json")


def check_release_contract() -> None:
    required_files = (
        ".changeset/config.json",
        ".changeset/README.md",
        ".github/workflows/release.yml",
        "assets/go-turbo.png",
        "CHANGELOG.md",
        "PRIVACY.md",
        "TERMS.md",
        "scripts/sync-plugin-version.mjs",
        "tests/submission-cases.md",
    )
    for relative in required_files:
        checked()
        if not (ROOT / relative).is_file():
            fail(f"{relative}: missing release contract file")

    config = read_json(".changeset/config.json")
    if config is not None:
        if config.get("baseBranch") != "main":
            fail(".changeset/config.json: baseBranch must be main")
        if config.get("privatePackages") != {"version": True, "tag": True}:
            fail(".changeset/config.json: private package versioning and tags must stay enabled")
        changelog = config.get("changelog")
        expected = ["@changesets/changelog-github", {"repo": "hendriknielaender/go-turbo"}]
        if changelog != expected:
            fail(".changeset/config.json: GitHub changelog repository drift")

    # These assert the properties a release must hold, not the steps that
    # achieve them. Pinning step text freezes the implementation and turns every
    # refactor into a validator edit.
    workflow_path = ROOT / ".github/workflows/release.yml"
    if workflow_path.is_file():
        workflow = workflow_path.read_text(encoding="utf-8")
        checked()
        if "workflow_call:" not in workflow:
            fail(".github/workflows/release.yml: release must stay reusable behind the validation gate")
        checked()
        if re.search(r"(?m)^\s{2}(push|schedule|workflow_run):", workflow):
            fail(".github/workflows/release.yml: release must not self-trigger; it can tag an unvalidated commit")
        checked()
        if "persist-credentials: false" not in workflow:
            fail(".github/workflows/release.yml: checkout must not persist git credentials")
        checked()
        if "npm publish" in workflow or "changeset publish" in workflow:
            fail(".github/workflows/release.yml: this private package is never published to a registry")

    validation_path = ROOT / ".github/workflows/validate.yml"
    if validation_path.is_file():
        validation = validation_path.read_text(encoding="utf-8")
        for phrase in (
            "needs: validate",
            "github.event_name == 'push'",
            "github.ref == 'refs/heads/main'",
            "uses: ./.github/workflows/release.yml",
        ):
            checked()
            if phrase not in validation:
                fail(f".github/workflows/validate.yml: missing release gate {phrase!r}")

    workflow_directory = ROOT / ".github/workflows"
    if workflow_directory.is_dir():
        for path in sorted(workflow_directory.glob("*.yml")):
            relative = rel(path)
            source = path.read_text(encoding="utf-8")
            checked()
            if "npm ci --ignore-scripts" not in source:
                fail(f"{relative}: dependency install must skip lifecycle scripts")
            for match in re.finditer(r"(?m)^\s*-?\s*uses:\s*(\S+)", source):
                reference = match.group(1)
                if reference.startswith("./"):
                    continue
                checked()
                _, separator, revision = reference.partition("@")
                if not separator or not re.fullmatch(r"[0-9a-f]{40}", revision):
                    fail(f"{relative}: {reference} must be pinned to a full commit SHA")

    sync_path = ROOT / "scripts/sync-plugin-version.mjs"
    if sync_path.is_file():
        sync = sync_path.read_text(encoding="utf-8")
        for relative in (".codex-plugin", ".claude-plugin", "package-lock.json"):
            if relative not in sync:
                fail(f"scripts/sync-plugin-version.mjs: does not synchronize {relative}")

    package = read_json("package.json")
    if package is not None:
        version = package.get("version")
        changelog_path = ROOT / "CHANGELOG.md"
        pending_changesets = [
            path
            for path in (ROOT / ".changeset").glob("*.md")
            if path.name != "README.md"
        ]
        if (
            changelog_path.is_file()
            and not pending_changesets
            and f"## {version}" not in changelog_path.read_text(encoding="utf-8")
        ):
            fail(f"CHANGELOG.md: missing current version {version}")
        if os.environ.get("GITHUB_REF_TYPE") == "tag":
            expected_tag = f"v{version}"
            if os.environ.get("GITHUB_REF_NAME") != expected_tag:
                fail(f"release tag must be {expected_tag}")

    cases_path = ROOT / "tests/submission-cases.md"
    if cases_path.is_file():
        cases = cases_path.read_text(encoding="utf-8")
        positive = list(re.finditer(r"(?m)^## Positive \d+:", cases))
        negative = list(re.finditer(r"(?m)^## Negative \d+:", cases))
        if len(positive) < 5:
            fail("tests/submission-cases.md: needs at least five positive cases")
        if len(negative) < 3:
            fail("tests/submission-cases.md: needs at least three negative cases")
        headings = sorted([*positive, *negative], key=lambda match: match.start())
        for index, match in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(cases)
            section = cases[match.start() : end]
            required = (
                ("**Prompt:**", "**Expected workflow:**", "**Expected result:**", "**Fixture:**")
                if "Positive" in match.group(0)
                else ("**Prompt:**", "**Expected fallback:**", "**Why not complete", "**Fixture:**")
            )
            for label in required:
                if label not in section:
                    fail(f"tests/submission-cases.md: {match.group(0)} missing {label}")


def check_local_markdown_links() -> None:
    link_re = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
    for path in [ROOT / "README.md", *sorted((ROOT / "skills").rglob("*.md"))]:
        checked()
        text = path.read_text(encoding="utf-8")
        prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        prose = re.sub(r"`[^`\n]*`", "", prose)
        for target in link_re.findall(prose):
            target = target.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            candidate = (path.parent / target).resolve()
            if not candidate.exists():
                fail(f"{rel(path)}: broken local link {target!r}")


def check_shell_examples() -> None:
    block_re = re.compile(r"```(?:sh|bash|shell)\n(.*?)```", re.DOTALL)
    placeholder_re = re.compile(r"=\s*<[^>\n]+>")
    for path in [ROOT / "README.md", *sorted((ROOT / "skills").rglob("*.md"))]:
        checked()
        text = path.read_text(encoding="utf-8")
        for block in block_re.findall(text):
            if placeholder_re.search(block):
                fail(
                    f"{rel(path)}: shell assignment uses an angle-bracket "
                    "placeholder that the shell interprets as redirection"
                )


def check_behavioral_contract() -> None:
    path = ROOT / "tests" / "behavioral-cases.md"
    checked()
    if not path.is_file():
        fail(f"{rel(path)}: missing fresh-agent acceptance contract")
        return
    text = path.read_text(encoding="utf-8")
    for number in range(1, 7):
        if f"## {number}." not in text:
            fail(f"{rel(path)}: missing behavioral case {number}")
    for phrase in (
        "unmeasured speedup",
        "bounded concurrency",
        "retry safety",
        "toolchain comparison",
        "forbidden-provenance scan",
    ):
        if phrase not in text.lower():
            fail(f"{rel(path)}: missing acceptance concept {phrase!r}")


PROHIBITED_NORMALIZED_DIGESTS: dict[int, frozenset[str]] = {
    9: frozenset({
        "93110c100fa1db31ac5ff0c130a71c88a8faec619b80a4890adccb4ac918fcca",
        "752ef058a2fdf5ba1740620ec2c059dab83da7425b311c915fc5495475dc1154",
    }),
    19: frozenset({
        "11e636c77fcc0a8dc1b6d9f21fe3609a1c3dc573aa33f7a1e456568025f14ca8",
    }),
}


def contains_prohibited_identity(value: str) -> bool:
    """Match prohibited identities without storing readable provenance."""
    normalized = "".join(char for char in value.casefold() if char.isalnum())
    for width, digests in PROHIBITED_NORMALIZED_DIGESTS.items():
        if len(normalized) < width:
            continue
        for start in range(len(normalized) - width + 1):
            candidate = normalized[start : start + width]
            digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
            if digest in digests:
                return True
    return False


def check_provenance_gate() -> None:
    for path in sorted(ROOT.rglob("*")):
        if IGNORED_SCAN_DIRECTORIES.intersection(path.parts) or not path.is_file():
            continue
        checked()
        if contains_prohibited_identity(str(path.relative_to(ROOT))):
            fail(f"{rel(path)}: release-prohibited provenance in path")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            fail(f"{rel(path)}: cannot read for provenance scan: {exc}")
            continue
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        if contains_prohibited_identity(text):
            fail(f"{rel(path)}: release-prohibited provenance marker")


def main() -> int:
    names = check_skills()
    check_codex_discovery(names)
    check_references()
    check_manifests(names)
    check_release_contract()
    check_local_markdown_links()
    check_shell_examples()
    check_behavioral_contract()
    check_provenance_gate()

    if errors:
        print(f"FAIL: {len(errors)} problem(s) across {checks} checks", file=sys.stderr)
        for message in errors:
            print(f"  {message}", file=sys.stderr)
        return 1

    print(
        f"OK: {checks} checks passed; {len(names)} skills, "
        f"{len(REQUIRED_REFERENCES)} references, Codex discovery ready"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
