(() => {
  'use strict';
  const get = id => document.getElementById(id);
  const input = get('cxmFineDelta');
  const save = get('cxmFineSave');
  const test = get('cxmFineTest');
  const result = get('cxmFineResult');
  let snapshot, tool, busy = false;

  function render() {
    const entry = snapshot?.config.tools[tool];
    const accepted = entry?.dock_reference_accepted && !entry.maintenance_lockout && !snapshot.migration_required;
    const delta = input.valueAsNumber;
    const valid = Number.isFinite(delta) && input.validity.valid;
    input.disabled = busy || !accepted || tool === 1;
    save.disabled = input.disabled || !valid || delta === 0;
    test.disabled = busy || !accepted || !valid || delta !== 0;
    const x = entry?.dock_x + delta;
    get('cxmFinePreview').textContent = !accepted ? 'Select an accepted, unlocked dock.'
      : !valid ? 'Enter a correction in hundredths of a millimetre, up to ±1.00 mm.'
      : 'T' + tool + ' pickup entry X ' + x.toFixed(3) + ' · mounted X ' +
        (x + snapshot.config.globals.cxm_shift_x).toFixed(3) + ' · dock Y ' + entry.dock_y.toFixed(3) +
        (tool === 1 ? ' · Revision 6 fixes T1 at its measured coordinates.' : '');
  }
  window.CXMFineDock = {select(data, number) {
    if (tool !== number || snapshot?.revision !== data?.revision) {
      input.value = '0';
      result.textContent = '';
    }
    snapshot = data;
    tool = number;
    render();
  }};
  input.addEventListener('input', render);

  async function request(path, body) {
    const options = {cache:'no-store'};
    if (body) Object.assign(options, {method:'POST', headers:{
      'Content-Type':'application/json', 'X-Requested-With':'CXM'}, body:JSON.stringify(body)});
    const reply = await fetch('/cxm/api/v1' + path, options);
    const data = await reply.json();
    if (!reply.ok) throw Error(data.error || 'HTTP ' + reply.status);
    return data;
  }
  async function run(isTest) {
    if (busy || (isTest ? test : save).disabled) return;
    const selected = tool, revision = snapshot.revision;
    const hundredths = Math.round(input.valueAsNumber * 100);
    const entry = snapshot.config.tools[selected];
    if (isTest && !window.confirm('Run one Standard T' + selected +
        ' pickup and drop-off? Confirm the carriage is empty, the hotend is docked and the full path is clear.')) return;
    busy = true;
    render();
    try {
      if (isTest) {
        const ready = await request('/native/initialize', {expected_revision:revision, carriage_tool:-1});
        if (!ready.ready || ready.sensor !== 'RELEASED' || selected !== tool || revision !== snapshot.revision)
          throw Error('Carriage or selection changed. Review before starting.');
        const reply = await request('/tools/multi/start', {tools:[selected], cycles:1, travel_profile:'standard',
          expected_revision:revision, execution_mode:'native',
          acknowledgement:'I_CHECKED_EMPTY_CARRIAGE_ALL_SELECTED_DOCKS_AND_FULL_XY_PATH'});
        if (!reply.started) throw Error('Start was not confirmed');
        document.querySelector('[data-tab="tools"]')?.click();
        get('cxmMultiPanel')?.scrollIntoView();
      } else {
        const saved = await request('/dock/fine-x', {tool:selected, hundredths, expected_revision:revision});
        const after = await request('/config');
        const actual = after.config.tools[selected];
        if (!saved.saved || !saved.backup || after.revision !== saved.revision ||
            Math.abs(actual.dock_x - entry.dock_x - hundredths / 100) > 0.000006 || actual.dock_y !== entry.dock_y)
          throw Error('Saved coordinates or backup could not be verified');
        window.CXMFineDock.select(after, tool);
        window.dispatchEvent(new Event('cxm-dock-save-completed'));
        result.textContent = 'T' + selected + ' saved at X ' + actual.dock_x.toFixed(3) + ' · backup ' + saved.backup;
      }
    } catch (error) {
      result.textContent = error.message + '. Check the saved settings and Tools status before retrying.';
    } finally {
      busy = false;
      render();
    }
  }
  save.addEventListener('click', () => run(false));
  test.addEventListener('click', () => run(true));
})();
