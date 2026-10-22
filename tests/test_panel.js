const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag) { this.tag=tag; this.children=[]; this.value=''; this.disabled=false; }
  append(...children) { for(const child of children)child.parent=this;this.children.push(...children); }
  prepend(...children) { for(const child of children)child.parent=this;this.children.unshift(...children); }
  replaceChildren(...children) { this.children=children; }
  setAttribute(name,value) { this[name]=value; }
  remove() { if(this.parent)this.parent.children=this.parent.children.filter(child=>child!==this); }
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
  console.log('Capacity controls, unified arrival navigation and fail-closed arrival automation passed');
  console.log('Loading indicator, duplicate-submit guard, control restoration and refresh-failure feedback passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
