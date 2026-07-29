const status = document.querySelector('[data-testid="ready"]');

if (status) {
  status.dataset.initialized = 'true';
}
