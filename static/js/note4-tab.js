(() => {
  const frame = document.getElementById('note4-controller');
  const tab = document.getElementById('note4-tab');
  const loading = document.getElementById('note4-loading');
  const error = document.getElementById('note4-error');
  if (!frame || !tab) return;
  let observer;
  let pending;

  function resizeFrame() {
    if (!tab.classList.contains('active') || !frame.contentDocument?.body) return;
    const height = Math.ceil(frame.contentDocument.body.getBoundingClientRect().height);
    if (height > 0) frame.style.height = `${height + 2}px`;
  }

  function showError() {
    clearTimeout(pending);
    observer?.disconnect();
    loading.hidden = true;
    frame.hidden = true;
    error.hidden = false;
  }

  function loadFrame() {
    if (frame.getAttribute('src')) { resizeFrame(); return; }
    loading.hidden = false;
    error.hidden = true;
    frame.hidden = false;
    pending = setTimeout(showError, 20000);
    frame.src = frame.dataset.src;
  }

  frame.addEventListener('load', () => {
    if (!frame.getAttribute('src')) return;
    clearTimeout(pending);
    try {
      if (!frame.contentDocument?.querySelector('.hub-embedded')) { showError(); return; }
      loading.hidden = true;
      error.hidden = true;
      frame.hidden = false;
      observer?.disconnect();
      observer = new ResizeObserver(resizeFrame);
      observer.observe(frame.contentDocument.body);
      resizeFrame();
    } catch { showError(); }
  });
  frame.addEventListener('error', showError);
  tab.addEventListener('shown.bs.tab', loadFrame);
  document.getElementById('note4-retry').addEventListener('click', () => {
    frame.removeAttribute('src');
    loadFrame();
  });
  document.addEventListener('DOMContentLoaded', () => {
    if (tab.classList.contains('active')) loadFrame();
  });
})();
