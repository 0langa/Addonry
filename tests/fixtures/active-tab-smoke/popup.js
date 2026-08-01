(async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.title,
  });
  document.querySelector('#result').textContent = result;
})().catch((error) => {
  console.error(error);
  document.querySelector('#result').textContent = 'failed';
});
