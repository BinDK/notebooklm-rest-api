const statusBox = document.getElementById('status');
const exportButton = document.getElementById('export');

function storageCookie(cookie) {
  const result = {
    name: cookie.name,
    value: cookie.value,
    domain: cookie.domain,
    path: cookie.path,
    expires: cookie.session ? -1 : cookie.expirationDate,
    httpOnly: cookie.httpOnly,
    secure: cookie.secure,
  };
  const sameSite = {
    strict: 'Strict',
    lax: 'Lax',
    no_restriction: 'None',
  }[cookie.sameSite];
  if (sameSite) result.sameSite = sameSite;
  return result;
}

async function captureCookies() {
  const urls = [
    'https://notebook.google.com/',
    'https://notebooklm.google.com/',
    'https://accounts.google.com/',
  ];
  const found = await Promise.all(urls.map(url => chrome.cookies.getAll({url})));
  const unique = new Map();
  for (const cookie of found.flat()) {
    const key = [cookie.storeId, cookie.name, cookie.domain, cookie.path].join('|');
    unique.set(key, cookie);
  }
  return [...unique.values()];
}

exportButton.addEventListener('click', async () => {
  exportButton.disabled = true;
  statusBox.textContent = 'Checking the signed-in browser session…';
  try {
    const cookies = await captureCookies();
    if (!cookies.length) {
      throw new Error('Chrome returned no cookies for NotebookLM or Google sign-in. Check that the helper has permission to access Google sites.');
    }

    const state = {cookies: cookies.map(storageCookie), origins: []};
    const blob = new Blob([JSON.stringify(state, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    await chrome.downloads.download({url, filename: 'storage_state.json', saveAs: true});
    statusBox.textContent = 'Session file downloaded. Upload it on the setup page to verify and save it.';
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (error) {
    statusBox.textContent = error.message || 'Could not export the session.';
  } finally {
    exportButton.disabled = false;
  }
});
