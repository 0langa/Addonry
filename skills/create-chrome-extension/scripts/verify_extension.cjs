#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const puppeteer = require('puppeteer-core');
const { probeChromeDevtoolsMcp } = require(path.resolve(__dirname, '..', '..', '..', 'scripts', 'smoke_chrome_devtools_mcp.cjs'));

function parseArgs(argv) {
  const result = { headed: false, keepProfile: false, screenshot: false };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--headed') result.headed = true;
    else if (value === '--keep-profile') result.keepProfile = true;
    else if (value === '--screenshot') result.screenshot = true;
    else if (value.startsWith('--')) {
      const key = value.slice(2);
      const next = argv[index + 1];
      if (!next || next.startsWith('--')) throw new Error(`Missing value for ${value}`);
      result[key] = next;
      index += 1;
    } else throw new Error(`Unexpected argument: ${value}`);
  }
  return result;
}

function redact(value) {
  return String(value)
    .replace(/(api[_-]?key|access[_-]?token|client[_-]?secret|password)(\s*[:=]\s*)[^\s,;]+/gi, '$1$2[REDACTED]')
    .replace(/\b(?:eyJ[a-zA-Z0-9_-]{16,}|[a-f0-9]{40,})\b/g, '[REDACTED_TOKEN]');
}

function sourceDigest(root) {
  const hash = crypto.createHash('sha256');
  const visit = (directory) => {
    const entries = fs.readdirSync(directory, { withFileTypes: true })
      .filter((entry) => !['.addonry', '.git', '__pycache__', 'artifacts', 'node_modules', 'web-ext-artifacts'].includes(entry.name))
      .sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (entry.isFile()) {
        hash.update(path.relative(root, full).replaceAll('\\', '/'));
        hash.update('\0');
        hash.update(fs.readFileSync(full));
        hash.update('\0');
      }
    }
  };
  visit(root);
  return hash.digest('hex');
}

function confirmedContractDigest(root) {
  const contractPath = path.join(root, '.addonry', 'contract.json');
  if (!fs.existsSync(contractPath)) return null;
  const payload = fs.readFileSync(contractPath);
  let contract;
  try {
    contract = JSON.parse(payload.toString('utf8'));
  } catch {
    return null;
  }
  if (contract.status !== 'confirmed' || !Array.isArray(contract.criteria) || contract.criteria.length === 0) return null;
  return crypto.createHash('sha256').update(payload).digest('hex');
}

async function run() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.extension || !args.chrome) throw new Error('--extension and --chrome are required');

  const extensionRoot = path.resolve(args.extension);
  const chromePath = path.resolve(args.chrome);
  const manifestPath = path.join(extensionRoot, 'manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  assert.equal(manifest.manifest_version, 3, 'Manifest V3 required');
  const sourceSha256 = sourceDigest(extensionRoot);
  const contractSha256 = confirmedContractDigest(extensionRoot);

  const profileParent = path.resolve(process.env.ADDONRY_TEST_PROFILES_ROOT || os.tmpdir());
  fs.mkdirSync(profileParent, { recursive: true });
  const profile = fs.mkdtempSync(path.join(profileParent, 'addonry-'));
  const artifactDir = path.join(extensionRoot, '.addonry', 'artifacts');
  fs.mkdirSync(artifactDir, { recursive: true });
  const reportPath = path.resolve(args.report || path.join(extensionRoot, '.addonry', 'verification.json'));
  const consoleErrors = [];
  const pageErrors = [];
  const workerErrors = [];
  const cleanupWarnings = [];
  const startedAt = new Date().toISOString();
  let browser;
  let report;
  let failureError;

  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, `${JSON.stringify({ status: 'running', startedAt, extension: extensionRoot, sourceSha256, contractSha256 }, null, 2)}\n`, 'utf8');

  try {
    browser = await puppeteer.launch({
      executablePath: chromePath,
      headless: args.headed ? false : true,
      pipe: false,
      userDataDir: profile,
      enableExtensions: true,
      args: ['--no-first-run', '--no-default-browser-check'],
    });

    const extensionId = await browser.installExtension(extensionRoot);
    assert.ok(extensionId, 'Chrome did not return installed extension ID');
    const extensions = await browser.extensions();
    const installedExtension = extensions.get(extensionId);
    assert.ok(installedExtension, 'Installed extension missing from browser.extensions()');
    assert.equal(installedExtension.enabled, true, 'Installed extension is disabled');
    assert.equal(installedExtension.name, manifest.name, 'Installed extension name differs from manifest');
    assert.equal(installedExtension.version, manifest.version, 'Installed extension version differs from manifest');
    const canonicalPath = (value) => {
      const resolved = fs.realpathSync.native(path.resolve(value));
      return process.platform === 'win32' ? resolved.toLowerCase() : resolved;
    };
    assert.equal(canonicalPath(installedExtension.path), canonicalPath(extensionRoot), 'Installed extension source path differs from requested durable path');
    const extensionRegistration = {
      id: installedExtension.id,
      name: installedExtension.name,
      version: installedExtension.version,
      path: installedExtension.path,
      enabled: installedExtension.enabled,
    };

    const getServiceWorkerTarget = async () => browser.waitForTarget(
      (target) => target.type() === 'service_worker' && target.url().startsWith(`chrome-extension://${extensionId}/`),
      { timeout: 15000 },
    );
    const attachedWorkers = new WeakSet();
    const attachedPages = new WeakSet();

    const attachWorkerDiagnostics = (worker) => {
      if (attachedWorkers.has(worker)) return worker;
      attachedWorkers.add(worker);
      worker.on('console', (message) => {
        if (message.type() === 'error') workerErrors.push(redact(message.text()));
      });
      worker.on('error', (error) => workerErrors.push(redact(error)));
      return worker;
    };

    const attachPageDiagnostics = (page) => {
      if (attachedPages.has(page)) return page;
      attachedPages.add(page);
      page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(redact(message.text()));
      });
      page.on('pageerror', (error) => pageErrors.push(redact(error)));
      return page;
    };

    const getServiceWorker = async () => {
      const target = await getServiceWorkerTarget();
      const worker = await target.worker();
      assert.ok(worker, 'Extension service worker unavailable');
      return attachWorkerDiagnostics(worker);
    };

    if (manifest.background && manifest.background.service_worker) await getServiceWorker();

    let activeTabGestureTriggered = false;
    const triggerAction = async (targetPage) => {
      assert.ok(targetPage, 'triggerAction(targetPage) requires representative page');
      attachPageDiagnostics(targetPage);
      await targetPage.bringToFront();
      let timeout;
      try {
        await Promise.race([
          installedExtension.triggerAction(targetPage),
          new Promise((_, reject) => {
            timeout = setTimeout(() => reject(new Error('Puppeteer Extension.triggerAction timed out after 15000 ms')), 15000);
          }),
        ]);
      } finally {
        clearTimeout(timeout);
      }
      activeTabGestureTriggered = true;
    };

    const openPopup = async (targetPage = null) => {
      const popupPath = manifest.action && manifest.action.default_popup;
      assert.ok(popupPath, 'Manifest has no action.default_popup');
      let existing = browser.targets().find((target) => target.type() === 'page' && target.url().endsWith(`/${popupPath}`));
      if (existing && targetPage) {
        const existingPage = await existing.asPage();
        if (existingPage) await existingPage.close();
        existing = null;
      }
      if (existing) {
        const existingPage = await existing.asPage();
        return attachPageDiagnostics(existingPage);
      }
      let popup;
      if (targetPage) {
        const popupTarget = browser.waitForTarget(
          (candidate) => candidate.type() === 'page' && candidate.url().endsWith(`/${popupPath}`),
          { timeout: 10000 },
        );
        await triggerAction(targetPage);
        popup = await (await popupTarget).asPage();
      } else if (manifest.background && manifest.background.service_worker) {
        const worker = await getServiceWorker();
        await worker.evaluate(() => chrome.action.openPopup());
        const target = await browser.waitForTarget(
          (candidate) => candidate.type() === 'page' && candidate.url().endsWith(`/${popupPath}`),
          { timeout: 10000 },
        );
        popup = await target.asPage();
      } else {
        popup = await browser.newPage();
        await popup.goto(`chrome-extension://${extensionId}/${popupPath}`);
      }
      assert.ok(popup, 'Popup page unavailable');
      attachPageDiagnostics(popup);
      if (args.screenshot) await popup.screenshot({ path: path.join(artifactDir, 'popup.png') });
      return popup;
    };

    let scenario = 'generic-popup';
    let scenarioResult = {};
    if (args.scenario) {
      scenario = path.resolve(args.scenario);
      delete require.cache[require.resolve(scenario)];
      const loaded = require(scenario);
      assert.equal(typeof loaded.run, 'function', 'Scenario must export run(context)');
      const returned = await loaded.run({
        browser,
        extension: installedExtension,
        extensionId,
        manifest,
        openPopup,
        triggerAction,
        getServiceWorker,
        attachPageDiagnostics,
        assert,
        artifactDir,
      });
      assert.ok(returned === undefined || (returned && typeof returned === 'object' && !Array.isArray(returned)), 'Scenario result must be object when returned');
      scenarioResult = returned || {};
    } else {
      const popup = await openPopup();
      await popup.waitForSelector('body');
    }

    assert.deepEqual(consoleErrors, [], `Console errors: ${consoleErrors.join(' | ')}`);
    assert.deepEqual(pageErrors, [], `Page errors: ${pageErrors.join(' | ')}`);
    assert.deepEqual(workerErrors, [], `Service-worker errors: ${workerErrors.join(' | ')}`);

    const endpoint = new URL(browser.wsEndpoint());
    const mcpProbe = await probeChromeDevtoolsMcp({ browserUrl: `http://${endpoint.host}`, openPage: false });

    const limitations = [];
    const usesActiveTab = ['permissions', 'optional_permissions'].some(
      (key) => Array.isArray(manifest[key]) && manifest[key].includes('activeTab'),
    );
    if (usesActiveTab && !activeTabGestureTriggered) {
      limitations.push('activeTab declared but tailored scenario did not invoke openPopup(targetPage) or triggerAction(targetPage).');
    }

    report = {
      status: 'passed',
      startedAt,
      finishedAt: new Date().toISOString(),
      extension: extensionRoot,
      extensionId,
      extensionName: manifest.name,
      manifestVersion: manifest.manifest_version,
      chromeVersion: await browser.version(),
      scenario,
      consoleErrors,
      pageErrors,
      workerErrors,
      limitations,
      cleanupWarnings,
      sourceSha256,
      contractSha256,
      scenarioResult,
      extensionRegistration,
      activeTabGestureTriggered,
      chromeDevtoolsMcp: mcpProbe,
      profileRetained: Boolean(args.keepProfile),
    };
  } catch (error) {
    failureError = error;
    report = {
      status: 'failed',
      startedAt,
      finishedAt: new Date().toISOString(),
      extension: extensionRoot,
      sourceSha256,
      contractSha256,
      error: redact(error && (error.stack || error)),
      cleanupWarnings,
    };
  } finally {
    if (browser) {
      try {
        await browser.close();
      } catch (error) {
        cleanupWarnings.push(`Browser close failed: ${redact(error && (error.message || error))}`);
      }
    }
    if (!args.keepProfile) {
      const resolvedParent = path.resolve(profileParent) + path.sep;
      const resolvedProfile = path.resolve(profile);
      if (!resolvedProfile.startsWith(resolvedParent)) {
        cleanupWarnings.push('Refused to remove profile outside configured test root.');
      } else {
        try {
          fs.rmSync(resolvedProfile, { recursive: true, force: true, maxRetries: 8, retryDelay: 250 });
        } catch (error) {
          cleanupWarnings.push(`Profile cleanup failed: ${redact(error && (error.message || error))}`);
        }
      }
    }
  }

  report.cleanupWarnings = cleanupWarnings;
  report.profileRetained = Boolean(args.keepProfile || cleanupWarnings.some((warning) => warning.startsWith('Profile cleanup')));
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  if (cleanupWarnings.length) {
    process.stderr.write(`${cleanupWarnings.join('\n')}\n`);
  }
  if (failureError) throw failureError;
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}

run().catch((error) => {
  process.stderr.write(`${redact(error && (error.stack || error))}\n`);
  process.exitCode = 1;
});
