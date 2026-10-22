const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag) { this.tag=tag; this.children=[]; this.value=''; }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  replaceChildren(...children) { this.children=children; }
  setAttribute(name,value) { this[name]=value; }
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
  console.log('Capacity controls, unified arrival navigation and fail-closed arrival automation passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
