const REQUIRED_COOKIES = new Set(['SID', '__Secure-1PSIDTS']);
const GOOGLE_SESSION_COOKIES = new Set([
  'SID', 'HSID', 'SSID', 'APISID', 'SAPISID',
  '__Secure-1PSID', '__Secure-1PSIDCC', '__Secure-1PSIDTS',
  '__Secure-3PSID', '__Secure-3PSIDCC', '__Secure-3PSIDTS',
  '__Host-1PLSID', 'LSID', 'OSID', '__Secure-OSID',
]);
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
  const filters = [
    {domain: 'google.com'},
    {domain: 'notebook.google.com'},
  ];
  const found = await Promise.all(filters.map(filter => chrome.cookies.getAll(filter)));
  const unique = new Map();
  for (const cookie of found.flat().filter(cookie => GOOGLE_SESSION_COOKIES.has(cookie.name))) {
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
    const names = new Set(cookies.map(cookie => cookie.name));
    const missing = [...REQUIRED_COOKIES].filter(name => !names.has(name));
    if (missing.length) {
      throw new Error('No NotebookLM session found. Sign in at notebook.google.com, wait for it to load, then try again.');
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
