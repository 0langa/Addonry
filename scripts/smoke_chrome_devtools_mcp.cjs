#!/usr/bin/env node
'use strict';

const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const wrapper = path.join(root, 'scripts', 'start-chrome-devtools-mcp.ps1');

async function probeChromeDevtoolsMcp({ browserUrl = null, openPage = true } = {}) {
  const environment = { ...process.env };
  if (browserUrl) {
    environment.ADDONRY_CHROME_MODE = 'browser-url';
    environment.ADDONRY_CHROME_BROWSER_URL = browserUrl;
  }

  const child = spawn(
    'powershell.exe',
    ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', wrapper],
    { cwd: root, env: environment, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true },
  );
  const pending = new Map();
  let stdoutBuffer = '';
  let stderr = '';
  let protocolError = null;

  const send = (message) => child.stdin.write(`${JSON.stringify(message)}\n`);
  const handleLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let message;
    try {
      message = JSON.parse(trimmed);
    } catch {
      protocolError = new Error(`Non-JSON data on MCP stdout: ${trimmed}`);
      return;
    }
    if (message.id !== undefined && pending.has(message.id)) {
      const resolver = pending.get(message.id);
      pending.delete(message.id);
      resolver(message);
    }
  };

  child.stdout.setEncoding('utf8');
  child.stdout.on('data', (chunk) => {
    stdoutBuffer += chunk;
    const lines = stdoutBuffer.split(/\r?\n/);
    stdoutBuffer = lines.pop();
    for (const line of lines) handleLine(line);
  });
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => { stderr += chunk; });

  let nextId = 1;
  const request = (method, params = {}) => new Promise((resolve, reject) => {
    if (protocolError) {
      reject(protocolError);
      return;
    }
    const id = nextId;
    nextId += 1;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timed out waiting for ${method}. MCP stderr: ${stderr.trim()}`));
    }, 30000);
    pending.set(id, (message) => {
      clearTimeout(timer);
      if (message.error) reject(new Error(`${method} failed: ${JSON.stringify(message.error)}`));
      else resolve(message.result);
    });
    send({ jsonrpc: '2.0', id, method, params });
  });

  const callTool = async (name, args = {}) => {
    const result = await request('tools/call', { name, arguments: args });
    assert.notEqual(result.isError, true, `${name} returned MCP tool error: ${JSON.stringify(result.content)}`);
    return result;
  };

  try {
    const initialized = await request('initialize', {
      protocolVersion: '2025-06-18',
      capabilities: {},
      clientInfo: { name: 'addonry-smoke', version: '0.1.0' },
    });
    assert.ok(initialized.serverInfo && initialized.serverInfo.name, 'MCP serverInfo missing');
    send({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} });
    const listed = await request('tools/list');
    const names = listed.tools.map((tool) => tool.name);
    for (const required of ['list_pages', 'navigate_page', 'take_snapshot']) {
      assert.ok(names.includes(required), `Chrome DevTools MCP tool missing: ${required}`);
    }

    await callTool('list_pages');
    if (openPage) await callTool('new_page', { url: 'about:blank' });
    await callTool('take_snapshot');
    return {
      status: 'passed',
      server: initialized.serverInfo,
      protocolVersion: initialized.protocolVersion,
      toolCount: names.length,
      browserAttached: true,
      requiredTools: ['list_pages', 'navigate_page', 'take_snapshot'],
    };
  } finally {
    child.stdin.end();
    child.kill();
  }
}

module.exports = { probeChromeDevtoolsMcp };

if (require.main === module) {
  probeChromeDevtoolsMcp()
    .then((report) => process.stdout.write(`${JSON.stringify(report, null, 2)}\n`))
    .catch((error) => {
      process.stderr.write(`${error.stack || error}\n`);
      process.exitCode = 1;
    });
}
