const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

test('live coordinates arrive independently of jog responses and release the socket when hidden', () => {
  const nodes = {}, panel = {hidden:false}, window = {};
  let socket, change;
  const document = {hidden:false, querySelector:()=>panel, addEventListener:()=>{},
    getElementById:id=>nodes[id] ||= {}};
  class Socket {
    constructor(url) { socket=this; assert.equal(url.href,'wss://printer/websocket'); }
    send(data) { this.sent=JSON.parse(data); }
    close() { this.closed=true; }
  }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/cxm-dock-position.js'),'utf8'),
    {window,document, URL, location:new URL('https://printer/cxm/'), WebSocket:Socket,
     MutationObserver:class {constructor(fn){change=fn;} observe(){}},setTimeout:()=>1,clearTimeout:()=>{}});
  socket.onopen();
  assert.equal(socket.sent.method,'printer.objects.subscribe');
  for(const x of [15,15.1]) {
    socket.onmessage({data:JSON.stringify({method:'notify_status_update', params:[{motion_report:{live_position:[x,20,25,0]}}]})});
    assert.equal(nodes.cxmManualX.textContent,x.toFixed(3)+' mm');
  }
  assert.equal(window.CXMDockPosition.streaming(),true);
  panel.hidden=true;
  change();
  assert.equal(socket.closed,true);
  assert.equal(window.CXMDockPosition.streaming(),false);
  assert.equal(nodes.cxmPositionFeed.textContent,'Last reported position');
});
