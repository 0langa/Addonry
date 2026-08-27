'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('shared manifest contains both target background declarations', () => {
  const manifest = JSON.parse(fs.readFileSync(path.resolve(__dirname, '..', '..', 'manifest.json'), 'utf8'));
  assert.equal(manifest.manifest_version, 3);
  assert.equal(typeof manifest.background.service_worker, 'string');
  assert.deepEqual(manifest.background.scripts, [manifest.background.service_worker]);
  assert.equal(typeof manifest.browser_specific_settings.gecko.id, 'string');
});
