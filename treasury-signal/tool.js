'use strict';
const button = document.getElementById('refresh');
const status = document.getElementById('refresh-status');
button?.addEventListener('click', async () => {
  button.disabled = true;
  status.textContent = 'Checking the latest published data…';
  try {
    const response = await fetch('data/latest.json?t=' + Date.now(), {cache:'no-store'});
    if (!response.ok) throw new Error('Data request failed');
    const data = await response.json();
    if (data.schema_version !== 1 || !data.reading) throw new Error('No complete reading in the published data');
    const current = document.querySelector('.dates time')?.getAttribute('datetime');
    if (current !== data.reading.reference_friday) {
      status.textContent = 'A newer reading is available. Loading it…';
      location.reload();
    } else {
      status.textContent = 'Latest published reference: ' + data.reading.reference_friday + '. This page is showing that reading.';
    }
  } catch (error) {
    status.textContent = 'Could not check for an update. The dated reading above is unchanged.';
  } finally { button.disabled = false; }
});
