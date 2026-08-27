#!/usr/bin/env python3
"""Temporarily install an extension in real Firefox and run tailored Selenium evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import Any

from browser_targets import manifest_for_browser
from package_extension import package_extension
from validate_extension import contract_digest, source_digest


def _load_scenario(path: Path):
    spec = importlib.util.spec_from_file_location("addonry_firefox_scenario", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load Firefox scenario: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if not callable(run):
        raise ValueError("Firefox scenario must define run(context)")
    return run


def _extension_uuid(driver, addon_id: str) -> str:
    scripts = (
        "return Services.prefs.getStringPref('extensions.webextensions.uuids');",
        "return ChromeUtils.importESModule('resource://gre/modules/Services.sys.mjs').Services.prefs.getStringPref('extensions.webextensions.uuids');",
    )
    with driver.context(driver.CONTEXT_CHROME):
        value = None
        for script in scripts:
            try:
                value = driver.execute_script(script)
                break
            except Exception:
                continue
    if not isinstance(value, str):
        raise RuntimeError("Firefox did not expose temporary extension UUID mapping")
    mapping = json.loads(value)
    uuid_value = mapping.get(addon_id) if isinstance(mapping, dict) else None
    if not isinstance(uuid_value, str) or not uuid_value:
        raise RuntimeError(f"Firefox UUID mapping missing installed add-on ID: {addon_id}")
    return uuid_value


def _string_list(payload: dict[str, Any], name: str) -> list[str]:
    value = payload.get(name, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Firefox scenario result {name} must be a string array")
    return value


def verify(
    extension: Path,
    firefox: Path,
    scenario: Path,
    report_path: Path,
    artifacts_root: Path,
    *,
    headed: bool = False,
    keep_artifacts: bool = False,
) -> dict[str, Any]:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.support.ui import WebDriverWait

    extension = extension.expanduser().resolve()
    firefox = firefox.expanduser().resolve()
    scenario = scenario.expanduser().resolve()
    report_path = report_path.expanduser().resolve()
    artifacts_root = artifacts_root.expanduser().resolve()
    if not firefox.is_file():
        raise FileNotFoundError(f"Firefox executable not found: {firefox}")
    if not scenario.is_file():
        raise FileNotFoundError(f"Firefox scenario not found: {scenario}")
    if (artifacts_root / "KEEP").is_file():
        raise ValueError(f"KEEP blocks Firefox artifact root: {artifacts_root}")
    artifacts_root.mkdir(parents=True, exist_ok=True)
    digest = source_digest(extension)
    contract_sha = contract_digest(extension)
    manifest = json.loads((extension / "manifest.json").read_text(encoding="utf-8"))
    firefox_manifest = manifest_for_browser(manifest, "firefox")
    scenario_run = _load_scenario(scenario)

    run_root = Path(tempfile.mkdtemp(prefix="firefox-run-", dir=artifacts_root))
    driver = None
    addon_id = None
    cleanup_warnings: list[str] = []
    evidence: dict[str, Any] = {
        "schemaVersion": 1,
        "status": "failed",
        "sourceSha256": digest,
        "contractSha256": contract_sha,
        "scenario": str(scenario),
        "lint": {"status": "passed"},
        "limitations": [],
        "cleanupWarnings": cleanup_warnings,
        "consoleErrors": [],
        "pageErrors": [],
        "backgroundErrors": [],
    }
    try:
        package_report = package_extension(
            extension,
            target="firefox",
            output_dir=run_root,
            overwrite=True,
            record=False,
        )
        package_path = Path(package_report["packages"][0]["path"])
        xpi_path = run_root / (package_path.stem + ".xpi")
        shutil.copyfile(package_path, xpi_path)

        options = Options()
        options.binary_location = str(firefox)
        if not headed:
            options.add_argument("-headless")
        options.set_preference("browser.shell.checkDefaultBrowser", False)
        options.set_preference("browser.startup.homepage_override.mstone", "ignore")
        options.set_preference("datareporting.policy.dataSubmissionEnabled", False)
        options.set_preference("toolkit.telemetry.reportingpolicy.firstRun", False)
        service = Service(
            service_args=["--allow-system-access"],
            log_output=str(run_root / "geckodriver.log"),
        )
        driver = webdriver.Firefox(options=options, service=service)
        addon_id = driver.install_addon(str(xpi_path), temporary=True)
        expected_id = firefox_manifest["browser_specific_settings"]["gecko"]["id"]
        if addon_id != expected_id:
            raise AssertionError(f"Firefox installed add-on ID {addon_id!r}, expected {expected_id!r}")
        uuid_value = _extension_uuid(driver, addon_id)
        context = {
            "driver": driver,
            "addon_id": addon_id,
            "extension_uuid": uuid_value,
            "extension_origin": f"moz-extension://{uuid_value}",
            "manifest": firefox_manifest,
            "wait": WebDriverWait(driver, 10),
            "artifacts_dir": run_root,
        }
        result = scenario_run(context)
        if result is None:
            result = {}
        if not isinstance(result, dict):
            raise ValueError("Firefox scenario run(context) must return a dictionary or None")

        permissions = manifest.get("permissions", [])
        limitations = _string_list(result, "limitations")
        if isinstance(permissions, list) and "activeTab" in permissions and result.get("activeTabProven") is not True:
            limitations.append("activeTab behavior was not proven in Firefox")
        evidence.update(
            {
                "browserProduct": "Mozilla Firefox",
                "browserVersion": driver.capabilities.get("browserVersion"),
                "headless": not headed,
                "extensionRegistration": {
                    "id": addon_id,
                    "uuid": uuid_value,
                    "name": firefox_manifest.get("name"),
                    "version": firefox_manifest.get("version"),
                    "path": str(extension),
                    "enabled": True,
                    "temporary": True,
                },
                "limitations": limitations,
                "consoleErrors": _string_list(result, "consoleErrors"),
                "pageErrors": _string_list(result, "pageErrors"),
                "backgroundErrors": _string_list(result, "backgroundErrors"),
                "scenarioResult": {key: value for key, value in result.items() if key not in {"consoleErrors", "pageErrors", "backgroundErrors", "limitations"}},
            }
        )
        if not any(
            evidence[field]
            for field in ("limitations", "consoleErrors", "pageErrors", "backgroundErrors")
        ):
            evidence["status"] = "passed"
    except Exception as error:
        evidence["failure"] = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(limit=12),
        }
    finally:
        if driver is not None:
            if addon_id is not None:
                try:
                    driver.uninstall_addon(addon_id)
                except Exception as error:
                    cleanup_warnings.append(f"temporary add-on uninstall failed: {error}")
            try:
                driver.quit()
            except Exception as error:
                cleanup_warnings.append(f"Firefox cleanup failed: {error}")
        if cleanup_warnings:
            evidence["status"] = "failed"
        if not keep_artifacts:
            try:
                shutil.rmtree(run_root)
            except OSError as error:
                cleanup_warnings.append(f"artifact cleanup failed: {error}")
                evidence["status"] = "failed"
        else:
            evidence["artifactsPath"] = str(run_root)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension", required=True, type=Path)
    parser.add_argument("--firefox", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--artifacts-root", required=True, type=Path)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--keep-artifacts", action="store_true")
    args = parser.parse_args()
    evidence = verify(
        args.extension,
        args.firefox,
        args.scenario,
        args.report,
        args.artifacts_root,
        headed=args.headed,
        keep_artifacts=args.keep_artifacts,
    )
    print(json.dumps(evidence, indent=2))
    return 0 if evidence.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
