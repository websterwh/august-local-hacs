const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  get parentNode() { return this.parent?.children.includes(this)?this.parent:null; }
  constructor(tag) { this.tag=tag; this.children=[]; this.value=''; this.disabled=false; }
  append(...children) { for(const child of children)child.parent=this;this.children.push(...children); }
  prepend(...children) { for(const child of children)child.parent=this;this.children.unshift(...children); }
  replaceChildren(...children) { this.children=children; }
  setAttribute(name,value) { this[name]=value; }
  remove() { if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this); }
  scrollIntoView(){}
  focus(){}
  querySelector(selector) { return this.descendants().find(child=>child.id===selector.slice(1))||null; }
  querySelectorAll(selector) { return this.descendants().filter(child=>selector.split(',').includes(child.tag)); }
  descendants() { return this.children.flatMap(child=>[child,...child.descendants()]); }
}
const context=vm.createContext({HTMLElement:class {}, document:{createElement:tag=>new Element(tag)},customElements:{define(){}},console});
vm.runInContext(fs.readFileSync('custom_components/august_local/panel.js','utf8')+'\nthis.Panel=AugustPinManager; this.makeArrival=arrivalAutomation;',context);
function panel() {
  const p=new context.Panel();
  const hosts={'#settings-editor':new Element('div'),'#editor':new Element('div')};
  p.shadowRoot={querySelector:key=>hosts[key]};
  p.model={users:[{id:'one'},{id:'two'}]};
  p.message=()=>{};
  return [p,hosts];
}
async function main() {
  const [p,hosts]=panel();
  let nearby=0,arrival=0;
  p.nearby=()=>{nearby++;hosts['#settings-editor'].replaceChildren(new Element('form'));};
  p.arrival=()=>{arrival++;hosts['#settings-editor'].replaceChildren(new Element('form'));};
  p.arrivalSettings();
  assert.equal(nearby,1);
  let navigation=hosts['#settings-editor'].children[0];
  navigation.children.find(e=>e.tag==='button'&&e.textContent.startsWith('2.')).onclick();
  assert.equal(arrival,1);
  navigation=hosts['#settings-editor'].children[0];
  assert.equal(navigation.children.filter(e=>e.tag==='button').length,2);
  let submitted;
  p.run=async (action,data)=>{submitted={action,data};return {total:2,assigned:2};};
  p.provision();
  const form=hosts['#editor'].children[0];
  await form.onsubmit({preventDefault(){}});
  assert.equal(submitted.action,'provision');
  assert.equal(Object.keys(submitted.data).length,0);
  const labels=form.children.filter(e=>e.tag==='label');
  const mode=labels[0].children[0];
  const count=labels[1].children[0];
  mode.value='count';mode.onchange();count.value='4';
  await form.onsubmit({preventDefault(){}});
  assert.equal(submitted.data.count,4);
  const automation=context.makeArrival('person.test','lock.test',300,'binary_sensor.near');
  assert.equal(automation.initial_state,false);
  assert.equal(automation.actions[0].continue_on_timeout,false);
  assert.match(automation.actions[0].wait_template,/last_seen/);
  assert.match(automation.actions[0].wait_template,/>= as_timestamp\(trigger.to_state.last_changed\)/);
  assert.throws(()=>context.makeArrival('person.test','lock.test',300,''));
  function runner() {
    const ui=new context.Panel();
    ui.shadowRoot=new Element('root');ui.shadowRoot.host=new Element('host');
    const button=new Element('button');const input=new Element('input');
    const disabled=new Element('button');disabled.disabled=true;
    ui.shadowRoot.append(button,input,disabled);
    ui.render=()=>{
      ui.shadowRoot.replaceChildren();
      const next=new Element('button');const unavailable=new Element('select');unavailable.disabled=true;
      ui.shadowRoot.append(next,unavailable);
    };
    return {ui,button,input,disabled};
  }
  {
    const {ui,button,input,disabled}=runner();let finish,writes=0;
    ui.api=action=>action?(writes++,new Promise(resolve=>finish=resolve)):Promise.resolve({records:[]});
    const pending=ui.run('program',{slot:2});
    assert.equal(ui.shadowRoot.host['aria-busy'],'true');
    assert.ok(ui.shadowRoot.querySelector('#operation-progress'));
    assert.equal(button.disabled,true);assert.equal(input.disabled,true);
    await ui.run('program',{slot:2});assert.equal(writes,1);
    finish({ok:true});await pending;
    assert.equal(ui.busy,false);assert.equal(ui.shadowRoot.host['aria-busy'],'false');
    assert.equal(ui.shadowRoot.querySelector('#operation-progress'),null);
    assert.equal(button.disabled,false);assert.equal(input.disabled,false);assert.equal(disabled.disabled,true);
    const controls=ui.shadowRoot.querySelectorAll('button,select');
    assert.equal(controls[0].disabled,false);assert.equal(controls[1].disabled,true);
    assert.match(ui.shadowRoot.querySelector('#message').textContent,/Programming acknowledged/);
  }
  {
    const {ui,button}=runner();let writes=0;
    ui.api=async action=>{if(action){writes++;throw {body:{error:'PIN outcome is unconfirmed'}};}throw new Error('refresh unavailable');};
    await ui.run('delete',{slot:2});
    assert.equal(writes,1);assert.equal(ui.busy,false);assert.equal(button.disabled,false);
    assert.equal(ui.shadowRoot.querySelector('#operation-progress'),null);
    assert.match(ui.shadowRoot.querySelector('#message').textContent,/PIN outcome is unconfirmed/);
    assert.match(ui.shadowRoot.querySelector('#message').textContent,/Status refresh also failed/);
  }
  {
    const {ui,button}=runner();let writes=0;
    ui.api=async action=>{if(action){writes++;return {ok:true};}throw new Error('refresh unavailable');};
    await ui.run('create',{pin:'test-value-not-sent'});
    assert.equal(writes,1);assert.equal(ui.busy,false);assert.equal(button.disabled,false);
    assert.match(ui.shadowRoot.querySelector('#message').textContent,/Request completed, but PIN status could not be refreshed/);
    assert.equal(ui.shadowRoot.querySelector('#operation-progress'),null);
  }
  {
    const {ui,button}=runner();
    ui.api=async()=>({ok:true});ui.render=()=>{throw new Error('render failed');};
    await ui.run('program',{slot:2});
    assert.equal(ui.busy,false);assert.equal(button.disabled,false);
    assert.equal(ui.shadowRoot.querySelector('#operation-progress'),null);
    assert.match(ui.shadowRoot.querySelector('#message').textContent,/Do not repeat the write/);
  }
  {
    // autoLock: immediate shell, single API request for duplicate click
    const [p,hosts]=panel();let resolveRead,readCalls=0;const msgs=[];p.message=t=>msgs.push(t);
    p.api=action=>action==='auto_lock_read'?(readCalls++,new Promise(r=>resolveRead=r)):Promise.resolve({});
    const prom=p.autoLock();
    assert.ok(hosts['#settings-editor'].children.length>0,'shell rendered before read');
    const alForm=hosts['#settings-editor'].children[0];
    const saveBtn=alForm.descendants().find(e=>e.tag==='button'&&e.textContent==='Save to lock');
    assert.ok(saveBtn&&saveBtn.disabled,'save disabled during load');
    const closeBtn=alForm.descendants().find(e=>e.tag==='button'&&e.textContent==='Close');
    assert.ok(closeBtn&&!closeBtn.disabled,'close enabled immediately');
    assert.equal(readCalls,1,'one read started');
    p.autoLock();// duplicate click while reading
    assert.equal(readCalls,1,'duplicate click does not start second read');
    assert.equal(hosts['#settings-editor'].children[0],alForm,'same shell, not replaced');
    resolveRead({mode:'timer',seconds:300});await prom;
    assert.ok(!saveBtn.disabled,'save enabled after read success');
    assert.ok(!alForm.descendants().find(e=>e.textContent&&e.textContent.includes('Reading')),'loading note removed');
  }
  {
    // autoLock: late response after Close does not reopen editor
    const [p,hosts]=panel();let resolveRead;p.message=()=>{};
    p.api=action=>action==='auto_lock_read'?new Promise(r=>resolveRead=r):Promise.resolve({});
    const prom=p.autoLock();
    const closeBtn=hosts['#settings-editor'].children[0].descendants().find(e=>e.tag==='button'&&e.textContent==='Close');
    closeBtn.onclick();
    assert.equal(hosts['#settings-editor'].children.length,0,'editor cleared on close');
    resolveRead({mode:'off',seconds:30});await prom;
    assert.equal(hosts['#settings-editor'].children.length,0,'late read does not reopen editor');
  }
  {
    // autoLock: read failure leaves responsive UI with retry enabled
    const [p,hosts]=panel();const msgs=[];p.message=t=>msgs.push(t);
    p.api=action=>action==='auto_lock_read'?Promise.reject({message:'BLE timeout'}):Promise.resolve({});
    await p.autoLock();
    const alForm=hosts['#settings-editor'].children[0];
    const saveBtn=alForm.descendants().find(e=>e.tag==='button'&&e.textContent==='Save to lock');
    const readAgainBtn=alForm.descendants().find(e=>e.tag==='button'&&e.textContent==='Read again');
    assert.ok(saveBtn&&saveBtn.disabled,'save still disabled after failure');
    assert.ok(readAgainBtn&&!readAgainBtn.disabled,'read again enabled after failure');
    assert.ok(msgs.some(m=>/timeout|failed/i.test(m)),'error message shown');
  }
  {
    // autoLock: switching settings invalidates outstanding read (late response ignored)
    const [p,hosts]=panel();let resolveRead;p.message=()=>{};
    p.api=action=>action==='auto_lock_read'?new Promise(r=>resolveRead=r):Promise.resolve({});
    const nearbyForm=new Element('form');
    p.nearby=()=>{p._autoLockGen=(p._autoLockGen||0)+1;hosts['#settings-editor'].replaceChildren(nearbyForm);};
    const prom=p.autoLock();const genBefore=p._autoLockGen;
    p.nearby();
    assert.ok(p._autoLockGen>genBefore,'gen bumped on switch');
    resolveRead({mode:'timer',seconds:60});await prom;
    assert.equal(hosts['#settings-editor'].children[0],nearbyForm,'nearby form not replaced by late auto-lock read');
  }
  {
    // arrivalSettings: duplicate step click does not re-render
    const [p2,hosts2]=panel();let nc=0,ac=0;
    p2.nearby=()=>{nc++;hosts2['#settings-editor'].replaceChildren(new Element('form'));};
    p2.arrival=()=>{ac++;hosts2['#settings-editor'].replaceChildren(new Element('form'));};
    p2.arrivalSettings('nearby');assert.equal(nc,1,'first call renders nearby');
    p2.arrivalSettings('nearby');assert.equal(nc,1,'dedup: same step not re-rendered');
    p2.arrivalSettings('arrival');assert.equal(ac,1,'different step renders arrival');
    p2.arrivalSettings('arrival');assert.equal(ac,1,'dedup: arrival not re-rendered');
  }
  {
    const [ui,hosts]=panel();let finish,reads=0;
    ui.api=()=>{reads++;return new Promise(resolve=>finish=resolve);};
    const first=ui.autoLock();
    hosts['#settings-editor'].children[0].descendants().find(e=>e.tag==='button'&&e.textContent==='Close').onclick();
    const reopened=ui.autoLock();
    assert.equal(reads,1,'reopening uses the pending read instead of a second Bluetooth request');
    const shell=hosts['#settings-editor'].children[0];
    finish({mode:'timer',seconds:30});await Promise.all([first,reopened]);
    assert.equal(hosts['#settings-editor'].children[0],shell);
    assert.equal(shell.descendants().find(e=>e.tag==='button'&&e.textContent==='Save to lock').disabled,false);
  }
  {
    const [ui,hosts]=panel();let count=0;
    ui.nearby=()=>{count++;hosts['#settings-editor'].replaceChildren(new Element('form'));};
    ui.arrivalSettings();assert.equal(count,1);
    ui.api=async()=>({mode:'off',seconds:0});
    await ui.autoLock();
    ui.arrivalSettings();assert.equal(count,2,'arrival can reopen after switching to auto-lock');
  }
  {
    const [ui,hosts]=panel();let finish,writes=0;
    ui.setBusy=active=>{ui.busy=active;};
    ui.api=action=>action==='auto_lock_read'?Promise.resolve({mode:'timer',seconds:30}):(writes++,new Promise(resolve=>finish=resolve));
    await ui.autoLock();
    const form=hosts['#settings-editor'].children[0];
    const saving=form.onsubmit({preventDefault(){}});
    await form.onsubmit({preventDefault(){}});
    assert.equal(writes,1,'double submit must not repeat a lock setting write');
    finish({mode:'timer',seconds:30});await saving;
    assert.equal(ui.busy,false);
    assert.equal(hosts['#settings-editor'].children.length,0);
  }
  {
    const [ui,hosts]=panel();let request;
    ui.run=async(action,data)=>{request={action,data};};
    ui.recoverPin({slot:2,has_pin:true});
    const form=hosts['#editor'].children[0];
    const inputs=form.descendants().filter(e=>e.tag==='input');
    inputs[0].value='1234';inputs[1].value='1234';
    await form.onsubmit({preventDefault(){}});
    assert.equal(request,undefined,'recovery must be explicitly confirmed');
    inputs[2].checked=true;inputs[1].value='5678';
    await form.onsubmit({preventDefault(){}});
    assert.equal(request,undefined,'mismatched replacement PINs must not be sent');
    inputs[1].value='1234';
    await form.onsubmit({preventDefault(){}});
    assert.equal(request.action,'recover');assert.equal(request.data.slot,2);
    assert.equal(request.data.confirmed_clear,true);assert.equal(request.data.pin,'1234');
    assert.equal(inputs[0].value,'');assert.equal(inputs[1].value,'');
  }
  {
    const [ui,hosts]=panel();let request;
    ui.run=async(action,data)=>{request={action,data};};
    ui.recoverPin({slot:1,has_pin:false});
    const form=hosts['#editor'].children[0];const inputs=form.descendants().filter(e=>e.tag==='input');
    inputs[1].value='5678';inputs[2].value='5678';inputs[3].checked=true;
    await form.onsubmit({preventDefault(){}});
    assert.equal(request,undefined,'blocked legacy restoration needs the last known PIN');
    inputs[0].value='1234';await form.onsubmit({preventDefault(){}});
    assert.equal(request.action,'recover');assert.equal(request.data.previous_pin,'1234');
    assert.equal(request.data.pin,'5678');assert.equal(request.data.slot,1);
    assert.equal(inputs[0].value,'');
  }
  console.log('Capacity controls, unified arrival navigation and fail-closed arrival automation passed');
  console.log('Loading indicator, duplicate-submit guard, control restoration and refresh-failure feedback passed');
  console.log('autoLock immediate shell, dedup, gen guard, failure retry, arrivalSettings dedup passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
