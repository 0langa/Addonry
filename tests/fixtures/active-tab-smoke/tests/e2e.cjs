'use strict';

const http = require('node:http');

exports.run = async ({ browser, openPopup, assert }) => {
  let page;
  const server = http.createServer((request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end('<!doctype html><title>Addonry Gesture Granted</title><h1>fixture</h1>');
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });

  try {
    const address = server.address();
    assert.equal(typeof address, 'object');
    page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${address.port}/fixture`, { waitUntil: 'domcontentloaded' });
    const popup = await openPopup(page);
    await popup.waitForFunction(() => document.querySelector('#result')?.textContent !== 'waiting');
    assert.equal(await popup.$eval('#result', (node) => node.textContent), 'Addonry Gesture Granted');
  } finally {
    if (page && !page.isClosed()) await page.close();
    if (typeof server.closeAllConnections === 'function') server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
};
