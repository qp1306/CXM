// Position display only. Motion approval and completion use the native jog endpoint.
(() => {
  const panel = document.querySelector('[data-panel="calibration"]');
  const label = document.getElementById('cxmPositionFeed');
  if (!panel || !label) return;
  let socket, retry, watchdog, streaming = false;
  window.CXMDockPosition = {streaming: () => streaming};
  const visible = () => !panel.hidden && !document.hidden;
  function stop() {
    clearTimeout(retry);
    clearTimeout(watchdog);
    const previous = socket;
    socket = null;
    previous?.close();
    streaming = false;
    label.textContent = 'Last reported position';
  }
  function connect() {
    if (!visible()) { stop(); return; }
    if (socket) return;
    const url = new URL('/websocket', location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(url);
    socket = ws;
    watchdog = setTimeout(() => ws.close(), 5000);
    ws.onopen = () => ws.send(JSON.stringify({jsonrpc:'2.0', id:1,
      method:'printer.objects.subscribe', params:{objects:{motion_report:['live_position']}}}));
    ws.onmessage = event => {
      if (socket !== ws) return;
      const data = JSON.parse(event.data);
      if (data.error || ['notify_klippy_shutdown','notify_klippy_disconnected'].includes(data.method)) {
        ws.close(); return;
      }
      const status = data.id === 1 ? data.result?.status :
        data.method === 'notify_status_update' ? data.params?.[0] : null;
      const pos = status?.motion_report?.live_position;
      if (!Array.isArray(pos) || pos.length < 3 || !pos.slice(0,3).every(Number.isFinite)) return;
      clearTimeout(watchdog);
      streaming = true;
      label.textContent = 'Live Klipper position';
      for (const [i, axis] of ['X','Y','Z'].entries())
        document.getElementById('cxmManual' + axis).textContent = pos[i].toFixed(i === 2 ? 2 : 3) + ' mm';
    };
    ws.onclose = () => {
      if (socket !== ws) return;
      stop();
      if (visible()) retry = setTimeout(connect, 3000);
    };
  }
  new MutationObserver(connect).observe(panel, {attributes:true, attributeFilter:['hidden']});
  document.addEventListener('visibilitychange', connect);
  connect();
})();
