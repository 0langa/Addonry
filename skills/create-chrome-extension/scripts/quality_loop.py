#!/usr/bin/env python3
"""Assess or run Addonry's acceptance-driven extension quality loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from browser_targets import manifest_for_browser, project_browsers
from package_extension import EXCLUDED_DIRECTORIES, package_extension
from validate_extension import source_digest, validate_extension

CONTRACT_RELATIVE = Path(".addonry/contract.json")
STATE_RELATIVE = Path(".addonry/quality-loop.json")
REPORT_RELATIVE = Path(".addonry/quality-report.json")
PROJECT_RELATIVE = Path(".addonry/project.json")
SUPPORTED_EVIDENCE = frozenset({"static-validation", "chrome-e2e", "firefox-e2e", "package"})
SUPPORTED_BROWSERS = frozenset({"chrome", "firefox"})
IGNORED_SOURCE_PARTS = frozenset({".addonry", ".git", "artifacts", "node_modules", "web-ext-artifacts", "__pycache__"})
CRITERION_ID_RE = re.compile(r"^REQ-[0-9]{3,}$")
SECRET_OUTPUT_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)(\s*[:=]\s*)[^\s,;]+"
)
HISTORY_LIMIT = 20


@dataclass(frozen=True)
class LoopFinding:
    phase: str
    code: str
    message: str
    repair: str
    criterionId: str | None = None
    path: str | None = None
    blocking: bool = False


CommandRunner = Callable[[Sequence[str], Path, int], subprocess.CompletedProcess[str]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _redact(value: str) -> str:
    return SECRET_OUTPUT_RE.sub(r"\1\2[REDACTED]", value)[-4000:]


def _json_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def _read_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "file is missing"
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, str(error)
    if not isinstance(payload, dict):
        return None, "root must be an object"
    return payload, None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if (path.parent / "KEEP").is_file():
        raise ValueError(f"KEEP blocks quality-loop output: {path.parent}")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:  # pragma: no cover - Python < 3.9
        return str(candidate).startswith(str(root))


def _proof_path_findings(
    root: Path,
    criterion_id: str,
    values: Any,
    field: str,
) -> tuple[list[str], list[LoopFinding]]:
    findings: list[LoopFinding] = []
    normalized: list[str] = []
    if not isinstance(values, list) or not values:
        return normalized, [
            LoopFinding(
                "contract",
                f"criterion-{field}-missing",
                f"{criterion_id} requires at least one {field} path",
                f"Map {criterion_id} to concrete existing {field} files.",
                criterion_id,
            )
        ]
    for value in values:
        if not isinstance(value, str) or not value.strip():
            findings.append(
                LoopFinding(
                    "contract",
                    f"criterion-{field}-invalid",
                    f"{criterion_id} contains invalid {field} path",
                    "Use non-empty extension-relative file paths.",
                    criterion_id,
                )
            )
            continue
        relative = Path(value.replace("\\", "/"))
        candidate = (root / relative).resolve()
        if relative.is_absolute() or not _inside(root, candidate):
            findings.append(
                LoopFinding(
                    "contract",
                    "criterion-path-escape",
                    f"{criterion_id} {field} path escapes extension root: {value}",
                    "Use extension-relative proof paths only.",
                    criterion_id,
                    value,
                )
            )
            continue
        if candidate.is_symlink():
            findings.append(
                LoopFinding(
                    "contract",
                    "criterion-path-symlink",
                    f"{criterion_id} {field} path cannot be symbolic link: {value}",
                    "Map proof to regular source files inside extension root.",
                    criterion_id,
                    value,
                )
            )
            continue
        if not candidate.is_file():
            findings.append(
                LoopFinding(
                    "contract",
                    "criterion-path-missing",
                    f"{criterion_id} {field} path does not exist: {value}",
                    "Implement missing file or correct contract mapping.",
                    criterion_id,
                    value,
                )
            )
            continue
        parts = relative.parts
        if field == "implementation" and (not parts or parts[0] in {".addonry", "tests", "artifacts"}):
            findings.append(
                LoopFinding(
                    "contract",
                    "criterion-implementation-not-runtime",
                    f"{criterion_id} implementation path is not runtime source: {value}",
                    "Map implementation to manifest or runtime source, not metadata/tests/artifacts.",
                    criterion_id,
                    value,
                )
            )
            continue
        if field == "tests" and (not parts or parts[0] != "tests"):
            findings.append(
                LoopFinding(
                    "contract",
                    "criterion-test-outside-tests",
                    f"{criterion_id} test path must live under tests/: {value}",
                    "Move or map criterion test under tests/.",
                    criterion_id,
                    value,
                )
            )
            continue
        normalized.append(relative.as_posix())
    return normalized, findings


def _validate_contract(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[str, ...], list[LoopFinding]]:
    findings: list[LoopFinding] = []
    contract_path = root / CONTRACT_RELATIVE
    contract, error = _read_object(contract_path)
    if contract is None:
        findings.append(
            LoopFinding(
                "contract",
                "contract-invalid" if contract_path.exists() else "contract-missing",
                f"Acceptance contract {error}.",
                "Create .addonry/contract.json, confirm atomic criteria, then reassess.",
                path=CONTRACT_RELATIVE.as_posix(),
            )
        )
        return {}, [], (), findings

    if contract.get("schemaVersion") != 1:
        findings.append(LoopFinding("contract", "contract-schema", "contract schemaVersion must be 1", "Migrate contract to schemaVersion 1."))
    if contract.get("status") != "confirmed":
        findings.append(LoopFinding("contract", "contract-unconfirmed", "Acceptance contract is not confirmed", "Confirm user-visible criteria and set status to confirmed with confirmedAt."))
    if not isinstance(contract.get("confirmedAt"), str) or not contract["confirmedAt"].strip():
        findings.append(LoopFinding("contract", "contract-confirmation-time-missing", "Confirmed contract requires confirmedAt", "Record ISO-8601 confirmation time after user confirmation."))
    if not isinstance(contract.get("requestSummary"), str) or not contract["requestSummary"].strip():
        findings.append(LoopFinding("contract", "contract-summary-missing", "Contract requestSummary is empty", "Write concise user-request summary."))

    raw_targets = contract.get("browserTargets")
    targets: tuple[str, ...] = ()
    if (
        not isinstance(raw_targets, list)
        or not raw_targets
        or any(not isinstance(item, str) or item not in SUPPORTED_BROWSERS for item in raw_targets)
        or len(set(raw_targets)) != len(raw_targets)
    ):
        findings.append(LoopFinding("contract", "contract-targets-invalid", "browserTargets must contain unique chrome/firefox values", "Match contract targets to confirmed project targets."))
    else:
        targets = tuple(raw_targets)
        configured = project_browsers(root)
        if set(targets) != set(configured):
            findings.append(
                LoopFinding(
                    "contract",
                    "contract-project-target-mismatch",
                    f"Contract targets {list(targets)} differ from project targets {list(configured)}",
                    "Reconcile contract and .addonry/project.json before implementation.",
                )
            )

    if not isinstance(contract.get("packagingRequested"), bool):
        findings.append(LoopFinding("contract", "contract-packaging-invalid", "packagingRequested must be boolean", "Record explicit packaging choice as true or false."))

    policy = contract.get("qualityPolicy")
    if not isinstance(policy, dict):
        findings.append(LoopFinding("contract", "contract-policy-missing", "qualityPolicy must be object", "Add requireZeroWarnings and stallThreshold policy."))
    else:
        if not isinstance(policy.get("requireZeroWarnings"), bool):
            findings.append(LoopFinding("contract", "contract-warning-policy-invalid", "qualityPolicy.requireZeroWarnings must be boolean", "Use true unless explicit warning rationale is accepted."))
        threshold = policy.get("stallThreshold")
        if not isinstance(threshold, int) or isinstance(threshold, bool) or not 2 <= threshold <= 10:
            findings.append(LoopFinding("contract", "contract-stall-threshold-invalid", "qualityPolicy.stallThreshold must be integer from 2 to 10", "Use stall threshold 3 unless workflow needs another bounded value."))

    accepted_warnings = contract.get("acceptedWarnings", [])
    if not isinstance(accepted_warnings, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("code"), str)
        or not item["code"].strip()
        or not isinstance(item.get("rationale"), str)
        or not item["rationale"].strip()
        for item in (accepted_warnings if isinstance(accepted_warnings, list) else [])
    ):
        findings.append(LoopFinding("contract", "contract-warning-rationale-invalid", "acceptedWarnings entries require code and rationale", "Document each explicitly accepted validator warning."))

    raw_criteria = contract.get("criteria")
    criteria: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    if not isinstance(raw_criteria, list) or not raw_criteria:
        findings.append(LoopFinding("contract", "contract-criteria-missing", "Confirmed contract requires at least one criterion", "Split request into atomic observable acceptance criteria."))
        return contract, criteria, targets, findings

    target_coverage = {browser: False for browser in targets}
    package_coverage = False
    for index, raw in enumerate(raw_criteria, start=1):
        if not isinstance(raw, dict):
            findings.append(LoopFinding("contract", "criterion-invalid", f"Criterion {index} must be object", "Replace malformed criterion with schema-compliant object."))
            continue
        criterion = dict(raw)
        criterion_id = criterion.get("id")
        if not isinstance(criterion_id, str) or not CRITERION_ID_RE.fullmatch(criterion_id):
            findings.append(LoopFinding("contract", "criterion-id-invalid", f"Criterion {index} requires ID such as REQ-001", "Assign stable REQ-NNN identifier."))
            continue
        if criterion_id in seen_ids:
            findings.append(LoopFinding("contract", "criterion-id-duplicate", f"Duplicate criterion ID: {criterion_id}", "Give every criterion unique stable ID.", criterion_id))
        seen_ids.add(criterion_id)
        for field in ("requirement", "acceptance"):
            if not isinstance(criterion.get(field), str) or not criterion[field].strip():
                findings.append(LoopFinding("contract", f"criterion-{field}-missing", f"{criterion_id} {field} is empty", f"Write concrete {field} text.", criterion_id))
        kind = criterion.get("kind")
        if kind not in {"behavior", "constraint", "quality", "package"}:
            findings.append(LoopFinding("contract", "criterion-kind-invalid", f"{criterion_id} has unsupported kind", "Use behavior, constraint, quality, or package.", criterion_id))
        applies = criterion.get("appliesTo")
        if (
            not isinstance(applies, list)
            or not applies
            or any(not isinstance(item, str) or item not in targets for item in applies)
            or len(set(applies)) != len(applies)
        ):
            findings.append(LoopFinding("contract", "criterion-targets-invalid", f"{criterion_id} appliesTo must be unique subset of contract targets", "Map criterion to affected requested browsers.", criterion_id))
            applies = []
        proof = criterion.get("proof")
        if not isinstance(proof, dict):
            findings.append(LoopFinding("contract", "criterion-proof-missing", f"{criterion_id} proof must be object", "Map implementation, tests, and evidence.", criterion_id))
            proof = {}
        implementation, path_findings = _proof_path_findings(root, criterion_id, proof.get("implementation"), "implementation")
        findings.extend(path_findings)
        tests, path_findings = _proof_path_findings(root, criterion_id, proof.get("tests"), "tests")
        findings.extend(path_findings)
        raw_evidence = proof.get("evidence")
        evidence: list[str] = []
        if (
            not isinstance(raw_evidence, list)
            or not raw_evidence
            or any(not isinstance(item, str) or item not in SUPPORTED_EVIDENCE for item in raw_evidence)
            or len(set(raw_evidence)) != len(raw_evidence)
        ):
            findings.append(LoopFinding("contract", "criterion-evidence-invalid", f"{criterion_id} evidence must use unique supported evidence kinds", "Map criterion to static-validation, requested browser E2E, or package proof.", criterion_id))
        else:
            evidence = list(raw_evidence)
        if kind == "behavior":
            for browser in applies:
                expected = f"{browser}-e2e"
                expected_test = "tests/e2e.cjs" if browser == "chrome" else "tests/firefox_e2e.py"
                if expected not in evidence:
                    findings.append(LoopFinding("contract", "criterion-browser-evidence-missing", f"{criterion_id} behavior lacks {expected}", f"Add tailored {browser} assertion and evidence mapping.", criterion_id))
                elif expected_test not in tests:
                    findings.append(LoopFinding("contract", "criterion-browser-test-missing", f"{criterion_id} {expected} lacks canonical {expected_test} mapping", f"Map {criterion_id} to {expected_test} after adding its assertions.", criterion_id, expected_test))
                else:
                    target_coverage[browser] = True
        if "package" in evidence:
            package_coverage = True
            if contract.get("packagingRequested") is not True:
                findings.append(LoopFinding("contract", "criterion-package-not-requested", f"{criterion_id} requests package proof while packagingRequested is false", "Reconcile packaging choice with criterion.", criterion_id))
        criterion["appliesTo"] = applies
        criterion["proof"] = {"implementation": implementation, "tests": tests, "evidence": evidence}
        criteria.append(criterion)

    for browser, covered in target_coverage.items():
        if not covered:
            findings.append(LoopFinding("contract", "browser-contract-coverage-missing", f"No behavior criterion requires {browser} E2E proof", f"Map at least one observable behavior criterion to {browser}-e2e."))
    if contract.get("packagingRequested") is True and not package_coverage:
        findings.append(LoopFinding("contract", "package-contract-coverage-missing", "Packaging requested but no criterion requires package proof", "Add package acceptance criterion or package evidence to relevant criterion."))
    return contract, criteria, targets, findings


def _source_files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and not any(part in IGNORED_SOURCE_PARTS for part in path.relative_to(root).parts)
    )


def _default_runner(command: Sequence[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_cheap_gates(root: Path, runner: CommandRunner) -> tuple[dict[str, Any], list[LoopFinding]]:
    findings: list[LoopFinding] = []
    syntax = {"status": "passed", "javascriptFiles": 0, "pythonFiles": 0}
    javascript = _source_files(root, {".js", ".cjs", ".mjs"})
    syntax["javascriptFiles"] = len(javascript)
    if javascript:
        if shutil.which("node") is None:
            findings.append(LoopFinding("syntax", "node-missing", "Node.js is unavailable for JavaScript syntax checks", "Install/restore Node.js, then rerun quality cycle.", blocking=True))
        else:
            for path in javascript:
                try:
                    result = runner(["node", "--check", str(path)], root, 60)
                except FileNotFoundError as error:
                    findings.append(LoopFinding("syntax", "node-unavailable", str(error), "Restore Node.js executable, then rerun quality cycle.", path=path.relative_to(root).as_posix(), blocking=True))
                    break
                except subprocess.TimeoutExpired as error:
                    findings.append(LoopFinding("syntax", "javascript-syntax-timeout", str(error), "Inspect hanging Node process and retry syntax gate with working runtime.", path=path.relative_to(root).as_posix()))
                    break
                if result.returncode:
                    findings.append(LoopFinding("syntax", "javascript-syntax-failed", _redact(result.stderr or result.stdout or f"node --check failed: {path}"), "Fix syntax error, then rerun cheap gates.", path=path.relative_to(root).as_posix()))
    python_files = _source_files(root, {".py"})
    syntax["pythonFiles"] = len(python_files)
    for path in python_files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, UnicodeError, SyntaxError) as error:
            findings.append(LoopFinding("syntax", "python-syntax-failed", str(error), "Fix Python syntax error, then rerun cheap gates.", path=path.relative_to(root).as_posix()))
    if any(item.phase == "syntax" for item in findings):
        syntax["status"] = "failed"

    unit = {"status": "not-present", "commands": []}
    unit_root = root / "tests" / "unit"
    js_tests = sorted(
        path for path in unit_root.rglob("*")
        if path.is_file() and any(path.name.endswith(suffix) for suffix in (".test.js", ".test.cjs", ".test.mjs"))
    ) if unit_root.is_dir() else []
    py_tests = sorted(unit_root.rglob("test_*.py")) if unit_root.is_dir() else []
    if js_tests or py_tests:
        unit["status"] = "passed"
    if js_tests:
        command = ["node", "--test", *(str(path) for path in js_tests)]
        unit["commands"].append(command)
        if shutil.which("node") is None:
            findings.append(LoopFinding("unit", "node-missing", "Node.js is unavailable for unit tests", "Install/restore Node.js, then rerun unit tests.", blocking=True))
            unit["status"] = "failed"
        else:
            try:
                result = runner(command, root, 120)
            except FileNotFoundError as error:
                findings.append(LoopFinding("unit", "node-unavailable", str(error), "Restore Node.js executable, then rerun unit tests.", blocking=True))
                unit["status"] = "failed"
                result = None
            except subprocess.TimeoutExpired as error:
                findings.append(LoopFinding("unit", "javascript-unit-timeout", str(error), "Diagnose hanging unit test and rerun.", blocking=False))
                unit["status"] = "failed"
                result = None
            if result is not None and result.returncode:
                findings.append(LoopFinding("unit", "javascript-unit-failed", _redact(result.stdout + result.stderr), "Repair failing JavaScript unit behavior, then rerun."))
                unit["status"] = "failed"
    if py_tests:
        command = [sys.executable, "-m", "unittest", "discover", "-s", str(unit_root), "-p", "test_*.py"]
        unit["commands"].append(command)
        try:
            result = runner(command, root, 120)
        except FileNotFoundError as error:
            findings.append(LoopFinding("unit", "python-unavailable", str(error), "Restore Python executable, then rerun unit tests.", blocking=True))
            unit["status"] = "failed"
            result = None
        except subprocess.TimeoutExpired as error:
            findings.append(LoopFinding("unit", "python-unit-timeout", str(error), "Diagnose hanging Python unit test and rerun."))
            unit["status"] = "failed"
            result = None
        if result is not None and result.returncode:
            findings.append(LoopFinding("unit", "python-unit-failed", _redact(result.stdout + result.stderr), "Repair failing Python unit behavior, then rerun."))
            unit["status"] = "failed"
    return {"syntax": syntax, "unit": unit}, findings


def _browser_evidence(root: Path, browser: str) -> tuple[dict[str, Any], list[LoopFinding], set[str]]:
    filename = "verification.json" if browser == "chrome" else "firefox-verification.json"
    evidence_path = root / ".addonry" / filename
    evidence, error = _read_object(evidence_path)
    findings: list[LoopFinding] = []
    passed: set[str] = set()
    if evidence is None:
        findings.append(LoopFinding("browser", f"{browser}-evidence-missing", f"{browser.title()} evidence {error}", f"Run tailored real-{browser} verification.", path=f".addonry/{filename}"))
        return {"status": "missing", "criteriaPassed": []}, findings, passed
    if evidence.get("status") != "passed":
        findings.append(LoopFinding("browser", f"{browser}-evidence-failed", f"Latest {browser.title()} verification did not pass", f"Inspect {filename}, repair failure, and rerun browser gate.", path=f".addonry/{filename}"))
    if evidence.get("sourceSha256") != source_digest(root):
        findings.append(LoopFinding("browser", f"{browser}-evidence-stale", f"{browser.title()} evidence does not match current source", f"Rerun {browser} verification after latest source change.", path=f".addonry/{filename}"))
    if evidence.get("contractSha256") != _json_digest(root / CONTRACT_RELATIVE):
        findings.append(LoopFinding("browser", f"{browser}-evidence-contract-stale", f"{browser.title()} evidence does not match current acceptance contract", f"Rerun {browser} verification after latest contract confirmation.", path=f".addonry/{filename}"))
    expected_scenario = (root / "tests" / ("e2e.cjs" if browser == "chrome" else "firefox_e2e.py")).resolve()
    scenario = evidence.get("scenario")
    if not isinstance(scenario, str) or Path(scenario).expanduser().resolve() != expected_scenario:
        findings.append(LoopFinding("browser", f"{browser}-scenario-mismatch", f"{browser.title()} evidence used wrong scenario", f"Run {expected_scenario.relative_to(root).as_posix()} for this extension.", path=f".addonry/{filename}"))
    scenario_result = evidence.get("scenarioResult")
    criteria_passed = scenario_result.get("criteriaPassed") if isinstance(scenario_result, dict) else None
    if not isinstance(criteria_passed, list) or any(not isinstance(item, str) for item in criteria_passed):
        findings.append(LoopFinding("browser", f"{browser}-criterion-proof-missing", f"{browser.title()} scenario did not report criteriaPassed", "Return criteriaPassed only after tailored scenario assertions succeed.", path=f".addonry/{filename}"))
    else:
        passed = set(criteria_passed)
    final_errors = [item for item in validate_extension(root, final_ready=True, target=browser) if item.level == "error"]
    for item in final_errors:
        findings.append(LoopFinding("final-ready", f"{browser}-{item.code}", item.message, f"Resolve final-ready {browser} evidence gate.", path=item.path))
    status = "passed" if not findings else "failed"
    return {"status": status, "criteriaPassed": sorted(passed), "path": f".addonry/{filename}"}, findings, passed


def _package_evidence(root: Path, targets: tuple[str, ...]) -> tuple[dict[str, Any], list[LoopFinding]]:
    report_path = root / ".addonry" / "package-report.json"
    report, error = _read_object(report_path)
    findings: list[LoopFinding] = []
    if report is None:
        findings.append(LoopFinding("package", "package-report-missing", f"Package report {error}", "Run deterministic package gate after browser proof.", path=".addonry/package-report.json"))
        return {"status": "missing", "targets": []}, findings
    if report.get("status") != "packaged" or report.get("sourceSha256") != source_digest(root):
        findings.append(LoopFinding("package", "package-report-stale", "Package report is failed or does not match current source", "Regenerate packages from exact verified source.", path=".addonry/package-report.json"))
    if report.get("contractSha256") != _json_digest(root / CONTRACT_RELATIVE):
        findings.append(LoopFinding("package", "package-report-contract-stale", "Package report does not match current acceptance contract", "Regenerate packages after latest contract confirmation.", path=".addonry/package-report.json"))
    raw_targets = report.get("targets")
    if not isinstance(raw_targets, list) or set(raw_targets) != set(targets):
        findings.append(LoopFinding("package", "package-target-mismatch", "Package targets do not match contract targets", "Regenerate package for every requested browser.", path=".addonry/package-report.json"))
    if report.get("signed") is not False or report.get("published") is not False:
        findings.append(LoopFinding("package", "package-distribution-state-invalid", "Local quality loop requires unsigned, unpublished package state", "Keep signing/publication behind separate explicit authorization."))
    rows = report.get("packages")
    rows_by_browser = {
        row.get("browser"): row for row in rows
        if isinstance(rows, list) and isinstance(row, dict) and isinstance(row.get("browser"), str)
    } if isinstance(rows, list) else {}
    try:
        source_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        source_manifest = {}
    for browser in targets:
        row = rows_by_browser.get(browser)
        if not isinstance(row, dict):
            findings.append(LoopFinding("package", "package-row-missing", f"Missing {browser} package row", f"Regenerate {browser} package."))
            continue
        raw_path = row.get("path")
        if not isinstance(raw_path, str) or not Path(raw_path).expanduser().is_file():
            findings.append(LoopFinding("package", "package-file-missing", f"{browser} package file is missing", f"Regenerate {browser} package."))
            continue
        package_path = Path(raw_path).expanduser().resolve()
        artifact_root = (root / "artifacts").resolve()
        if not _inside(artifact_root, package_path):
            findings.append(LoopFinding("package", "package-path-outside-artifacts", f"{browser} package path is outside extension artifacts directory", "Regenerate through quality cycle's managed artifacts directory.", path=str(package_path)))
            continue
        payload = package_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if row.get("sha256") != digest or row.get("bytes") != len(payload):
            findings.append(LoopFinding("package", "package-hash-mismatch", f"{browser} package hash/size differs from report", f"Delete suspect artifact through normal overwrite path and regenerate {browser} package.", path=str(package_path)))
        try:
            with zipfile.ZipFile(package_path, "r") as archive:
                names = archive.namelist()
                if not names or names[0] != "manifest.json" or len(names) != len(set(names)):
                    raise ValueError("manifest.json must be first and paths unique")
                if any(any(part in EXCLUDED_DIRECTORIES for part in Path(name).parts) for name in names):
                    raise ValueError("excluded development path present")
                packaged_manifest = json.loads(archive.read("manifest.json"))
                if packaged_manifest != manifest_for_browser(source_manifest, browser):
                    raise ValueError("target manifest differs from source transform")
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as error:
            findings.append(LoopFinding("package", "package-layout-invalid", f"{browser} package validation failed: {error}", f"Regenerate package with Addonry packager; never hand-edit ZIP.", path=str(package_path)))
    status = "passed" if not findings else "failed"
    return {"status": status, "targets": list(targets), "path": ".addonry/package-report.json"}, findings


def _accepted_warning_codes(contract: dict[str, Any]) -> set[str]:
    values = contract.get("acceptedWarnings", [])
    return {item["code"] for item in values if isinstance(item, dict) and isinstance(item.get("code"), str)} if isinstance(values, list) else set()


def assess_quality(
    root: Path,
    *,
    persist: bool = True,
    runner: CommandRunner = _default_runner,
    extra_findings: Sequence[LoopFinding] = (),
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"extension path is not directory: {root}")
    source_sha = source_digest(root)
    contract_sha = _json_digest(root / CONTRACT_RELATIVE)
    contract, criteria, targets, findings = _validate_contract(root)
    criterion_contract_errors = {item.criterionId for item in findings if item.criterionId}

    static_raw = validate_extension(root, release_ready=True)
    accepted_warning_codes = _accepted_warning_codes(contract)
    require_zero_warnings = not isinstance(contract.get("qualityPolicy"), dict) or contract["qualityPolicy"].get("requireZeroWarnings") is not False
    static_findings: list[LoopFinding] = []
    advisories: list[dict[str, Any]] = []
    for item in static_raw:
        if item.level == "error":
            static_findings.append(LoopFinding("static", item.code, item.message, "Repair static/release-ready finding, then reassess.", path=item.path))
        elif require_zero_warnings or item.code not in accepted_warning_codes:
            static_findings.append(LoopFinding("static", f"unresolved-{item.code}", item.message, "Remove warning cause or record explicit acceptedWarnings rationale.", path=item.path))
        else:
            advisories.append({**asdict(item), "accepted": True})
    findings.extend(static_findings)
    static_passed = not static_findings

    cheap_proof, cheap_findings = _run_cheap_gates(root, runner)
    findings.extend(cheap_findings)

    browser_proof: dict[str, Any] = {}
    browser_criteria: dict[str, set[str]] = {}
    for browser in targets:
        evidence, browser_findings, criteria_passed = _browser_evidence(root, browser)
        browser_proof[browser] = evidence
        browser_criteria[browser] = criteria_passed
        findings.extend(browser_findings)

    packaging_requested = contract.get("packagingRequested") is True
    if packaging_requested and targets:
        package_proof, package_findings = _package_evidence(root, targets)
        findings.extend(package_findings)
    else:
        package_proof = {"status": "not-requested", "targets": []}

    findings.extend(extra_findings)
    ending_source_sha = source_digest(root)
    ending_contract_sha = _json_digest(root / CONTRACT_RELATIVE)
    if ending_source_sha != source_sha:
        findings.append(
            LoopFinding(
                "integrity",
                "source-changed-during-assessment",
                "Extension source changed while quality gates were running",
                "Stop mutating tests/processes, then rerun complete assessment against stable source.",
            )
        )
        source_sha = ending_source_sha
    if ending_contract_sha != contract_sha:
        findings.append(
            LoopFinding(
                "integrity",
                "contract-changed-during-assessment",
                "Acceptance contract changed while quality gates were running",
                "Reconfirm stable contract, then rerun complete assessment.",
            )
        )
        contract_sha = ending_contract_sha
    criterion_rows: list[dict[str, Any]] = []
    for criterion in criteria:
        criterion_id = criterion["id"]
        evidence_status: dict[str, bool] = {}
        for evidence_kind in criterion["proof"]["evidence"]:
            if evidence_kind == "static-validation":
                evidence_status[evidence_kind] = static_passed
            elif evidence_kind == "chrome-e2e":
                evidence_status[evidence_kind] = browser_proof.get("chrome", {}).get("status") == "passed" and criterion_id in browser_criteria.get("chrome", set())
            elif evidence_kind == "firefox-e2e":
                evidence_status[evidence_kind] = browser_proof.get("firefox", {}).get("status") == "passed" and criterion_id in browser_criteria.get("firefox", set())
            elif evidence_kind == "package":
                evidence_status[evidence_kind] = package_proof.get("status") == "passed"
        missing = sorted(kind for kind, passed in evidence_status.items() if not passed)
        if missing:
            findings.append(
                LoopFinding(
                    "traceability",
                    "criterion-proof-incomplete",
                    f"{criterion_id} lacks current proof: {', '.join(missing)}",
                    "Repair mapped implementation/test, rerun affected gate, and return criterion ID after assertions.",
                    criterion_id,
                )
            )
        passed = criterion_id not in criterion_contract_errors and bool(evidence_status) and not missing
        criterion_rows.append(
            {
                "id": criterion_id,
                "requirement": criterion.get("requirement"),
                "acceptance": criterion.get("acceptance"),
                "appliesTo": criterion.get("appliesTo"),
                "implementation": criterion["proof"]["implementation"],
                "tests": criterion["proof"]["tests"],
                "evidence": evidence_status,
                "status": "passed" if passed else "failed",
            }
        )

    unique_findings: list[LoopFinding] = []
    seen_findings: set[tuple[Any, ...]] = set()
    for finding in findings:
        identity = (finding.phase, finding.code, finding.message, finding.criterionId, finding.path)
        if identity not in seen_findings:
            unique_findings.append(finding)
            seen_findings.add(identity)
    passed_count = sum(row["status"] == "passed" for row in criterion_rows)
    total_count = len(criterion_rows)
    coverage = round((passed_count / total_count) * 100, 2) if total_count else 0.0
    has_external_blocker = any(item.blocking for item in unique_findings)
    base_passed = not unique_findings and total_count > 0 and passed_count == total_count

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "status": "passed" if base_passed else "blocked" if has_external_blocker else "repair-required",
        "assessedAt": _now(),
        "extension": str(root),
        "sourceSha256": source_sha,
        "contractSha256": contract_sha,
        "requestSummary": contract.get("requestSummary"),
        "browserTargets": list(targets),
        "packagingRequested": packaging_requested,
        "coverage": {"passed": passed_count, "total": total_count, "percent": coverage},
        "proof": {
            "static": {"status": "passed" if static_passed else "failed"},
            **cheap_proof,
            "browsers": browser_proof,
            "package": package_proof,
        },
        "criteria": criterion_rows,
        "advisories": advisories,
        "findings": [asdict(item) for item in unique_findings],
    }
    if persist:
        report = _persist_assessment(root, contract, report)
    return report


def _persist_assessment(root: Path, contract: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    state_path = root / STATE_RELATIVE
    previous, _ = _read_object(state_path)
    previous = previous or {}
    fingerprint_payload = [
        [item["phase"], item["code"], item.get("criterionId"), item.get("path")]
        for item in report["findings"]
    ]
    fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")).hexdigest()
    unchanged_failure = (
        report["status"] != "passed"
        and previous.get("sourceSha256") == report["sourceSha256"]
        and previous.get("contractSha256") == report["contractSha256"]
        and previous.get("failureFingerprint") == fingerprint
    )
    repeat_count = int(previous.get("repeatCount", 0)) + 1 if unchanged_failure else (0 if report["status"] == "passed" else 1)
    policy = contract.get("qualityPolicy", {}) if isinstance(contract, dict) else {}
    threshold = policy.get("stallThreshold", 3) if isinstance(policy, dict) else 3
    if not isinstance(threshold, int) or isinstance(threshold, bool) or not 2 <= threshold <= 10:
        threshold = 3
    status = report["status"]
    if status == "repair-required" and repeat_count >= threshold:
        status = "strategy-change-required"
    report["status"] = status
    first = report["findings"][0] if report["findings"] else None
    blocker = next((item for item in report["findings"] if item.get("blocking") is True), None)
    next_action = (
        "All confirmed criteria passed. Use exact verified package or continue authorized installation step."
        if status == "passed"
        else blocker["repair"] if status == "blocked" and blocker is not None
        else "Stop unchanged retries. Isolate first failing gate, reproduce it separately, and change repair strategy."
        if status == "strategy-change-required"
        else first["repair"] if first else "Repair incomplete contract and reassess."
    )
    iteration = int(previous.get("iteration", 0)) + 1
    history = previous.get("history", [])
    if not isinstance(history, list):
        history = []
    history = [
        *history,
        {
            "iteration": iteration,
            "assessedAt": report["assessedAt"],
            "status": status,
            "sourceSha256": report["sourceSha256"],
            "contractSha256": report["contractSha256"],
            "failureFingerprint": fingerprint,
            "findingCodes": [item["code"] for item in report["findings"]],
        },
    ][-HISTORY_LIMIT:]
    state = {
        "schemaVersion": 1,
        "status": status,
        "iteration": iteration,
        "sourceSha256": report["sourceSha256"],
        "contractSha256": report["contractSha256"],
        "failureFingerprint": fingerprint,
        "repeatCount": repeat_count,
        "stallThreshold": threshold,
        "nextAction": next_action,
        "report": REPORT_RELATIVE.as_posix(),
        "updatedAt": report["assessedAt"],
        "history": history,
    }
    report["iteration"] = iteration
    report["repeatCount"] = repeat_count
    report["nextAction"] = next_action
    _atomic_write_json(root / REPORT_RELATIVE, report)
    _atomic_write_json(state_path, state)

    project_path = root / PROJECT_RELATIVE
    project, _ = _read_object(project_path)
    if project is not None:
        project["qualityLoop"] = {
            "status": status,
            "contract": CONTRACT_RELATIVE.as_posix(),
            "state": STATE_RELATIVE.as_posix(),
            "report": REPORT_RELATIVE.as_posix(),
            "coveragePercent": report["coverage"]["percent"],
            "sourceSha256": report["sourceSha256"],
        }
        _atomic_write_json(project_path, project)
    return report


def _browser_command(root: Path, browser: str) -> list[str]:
    scripts = Path(__file__).resolve().parent
    if browser == "chrome":
        wrapper = scripts / "verify-extension.ps1"
        scenario = root / "tests" / "e2e.cjs"
    else:
        wrapper = scripts / "verify-firefox-extension.ps1"
        scenario = root / "tests" / "firefox_e2e.py"
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(wrapper),
        "-ExtensionPath",
        str(root),
        "-ScenarioPath",
        str(scenario),
    ]


def cycle_quality(
    root: Path,
    *,
    runner: CommandRunner = _default_runner,
    browser_timeout_seconds: int = 300,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    preflight = assess_quality(root, persist=False, runner=runner)
    preflight_blocking_phases = {"contract", "integrity", "static", "syntax", "unit"}
    if any(item["phase"] in preflight_blocking_phases for item in preflight["findings"]):
        return assess_quality(root, persist=True, runner=runner)

    command_findings: list[LoopFinding] = []
    for browser in preflight["browserTargets"]:
        if preflight["proof"]["browsers"].get(browser, {}).get("status") == "passed":
            continue
        command = _browser_command(root, browser)
        try:
            result = runner(command, root, browser_timeout_seconds)
        except FileNotFoundError as error:
            command_findings.append(LoopFinding("browser", f"{browser}-gate-unavailable", str(error), f"Restore {browser} verification tooling or record external blocker.", blocking=True))
            continue
        except subprocess.TimeoutExpired as error:
            command_findings.append(LoopFinding("browser", f"{browser}-gate-timeout", str(error), f"Inspect hanging {browser} gate, change diagnosis strategy, then retry."))
            continue
        if result.returncode:
            command_findings.append(
                LoopFinding(
                    "browser",
                    f"{browser}-gate-command-failed",
                    _redact(result.stdout + result.stderr) or f"{browser} verifier exited {result.returncode}",
                    f"Inspect current {browser} evidence, repair lowest failure, then rerun quality cycle.",
                )
            )

    after_browser = assess_quality(root, persist=False, runner=runner, extra_findings=command_findings)
    non_package_findings = [
        item for item in after_browser["findings"]
        if item["phase"] not in {"package", "traceability"}
    ]
    criteria_ready_except_package = all(
        all(passed for kind, passed in row["evidence"].items() if kind != "package")
        for row in after_browser["criteria"]
    )
    if after_browser["packagingRequested"] and not non_package_findings and criteria_ready_except_package:
        try:
            package_extension(root, target="auto", overwrite=True, record=True)
        except (FileExistsError, OSError, RuntimeError, ValueError) as error:
            command_findings.append(LoopFinding("package", "package-command-failed", str(error), "Repair package input/output finding, then rerun quality cycle."))

    return assess_quality(root, persist=True, runner=runner, extra_findings=command_findings)


def record_blocker(root: Path, code: str, reason: str, *, runner: CommandRunner = _default_runner) -> dict[str, Any]:
    """Persist externally proven blocker without converting incomplete work to success."""
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", code) is None:
        raise ValueError("blocker code must use lower-case letters, digits, and single hyphens")
    if not reason.strip():
        raise ValueError("blocker reason is required")
    blocker = LoopFinding(
        "external",
        code,
        reason.strip(),
        "Resolve documented external blocker, then rerun quality cycle.",
        blocking=True,
    )
    return assess_quality(root, persist=True, runner=runner, extra_findings=[blocker])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    assess_parser = subparsers.add_parser("assess", help="Run deterministic cheap gates and account current proof")
    assess_parser.add_argument("extension_path", type=Path)
    cycle_parser = subparsers.add_parser("cycle", help="Run full requested browser/package gates, then account proof")
    cycle_parser.add_argument("extension_path", type=Path)
    cycle_parser.add_argument("--browser-timeout-seconds", type=int, default=300)
    block_parser = subparsers.add_parser("block", help="Record proven external blocker without claiming success")
    block_parser.add_argument("extension_path", type=Path)
    block_parser.add_argument("--code", required=True)
    block_parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    try:
        if args.command == "cycle":
            report = cycle_quality(args.extension_path, browser_timeout_seconds=args.browser_timeout_seconds)
        elif args.command == "block":
            report = record_blocker(args.extension_path, args.code, args.reason)
        else:
            report = assess_quality(args.extension_path)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
