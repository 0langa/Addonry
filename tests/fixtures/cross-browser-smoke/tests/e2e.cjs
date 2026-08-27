exports.run = async ({ manifest, openPopup, assert }) => {
  const popup = await openPopup();
  await popup.waitForSelector('[data-testid="ready"][data-initialized="true"]');
  const heading = await popup.$eval('h1', (node) => node.textContent);
  const status = await popup.$eval('[data-testid="ready"]', (node) => node.textContent);
  assert.equal(heading, manifest.name);
  assert.equal(status, 'Shared extension runtime ready.');
  return { criteriaPassed: ['REQ-001'] };
};
