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
    const current = document.querySelector('[data-signal-reference]')?.getAttribute('data-signal-reference');
    if (current !== data.reading.reference_friday) {
      status.textContent = 'A newer reading is available. Loading it…';
      location.reload();
    } else {
      const asOf = new Date(data.reading.reference_friday + 'T12:00:00Z').toLocaleDateString('en-US', {month:'long',day:'numeric',year:'numeric',timeZone:'America/New_York'});
      status.textContent = 'This is the latest complete published reading, based on the ' + asOf + ' close.';
    }
  } catch (error) {
    status.textContent = 'Could not check for an update. The dated reading above is unchanged.';
  } finally { button.disabled = false; }
});
