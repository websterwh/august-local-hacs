function parseDuration(value) {
  const match=String(value).trim().match(/^(\d+)\s*([smh]?)$/i);
  if(!match)throw new Error('Use a duration like 30s, 5m, or 1h.');
  const seconds=Number(match[1])*({s:1,m:60,h:3600}[match[2].toLowerCase()]||1);
  if(!Number.isSafeInteger(seconds)||seconds<1||seconds>65534)throw new Error('Use a delay from 1 second to 18h 12m 14s (65534 seconds).');
  return seconds;
}
function formatDuration(seconds) {
  if(seconds>0&&seconds%3600===0)return `${seconds/3600}h`;
  if(seconds>0&&seconds%60===0)return `${seconds/60}m`;
  return `${seconds}s`;
}
function arrivalAutomation(source, lock, awaySeconds, nearby) {
  if(!/^(person|device_tracker)\.[a-z0-9_]+$/.test(source)||!/^lock\.[a-z0-9_]+$/.test(lock))throw new Error('Select a person or phone and the configured lock.');
  if(!Number.isInteger(awaySeconds)||awaySeconds<1||awaySeconds>65534)throw new Error('Choose a valid minimum time away.');
  if(!/^binary_sensor\.[a-z0-9_]+$/.test(nearby))throw new Error('Set up and select nearby phone detection first.');
  const away=`states('${source}') not in ['home', 'unknown', 'unavailable']`;
  const trigOk=`trigger is defined and trigger is not none and trigger.id is defined and trigger.id == 'away_ready' and trigger.platform == 'template' and trigger.from_state is defined and trigger.from_state is not none and trigger.to_state is defined and trigger.to_state is not none and trigger.from_state.state == 'home' and trigger.to_state.state not in ['home', 'unknown', 'unavailable']`;
  const lastSeen=`as_timestamp(state_attr('${nearby}', 'last_seen'), none)`;
  const nearbyFresh=`arrival_at is defined and is_number(arrival_at) and is_state('${nearby}', 'on') and ${lastSeen} is not none and (as_timestamp(now()) - ${lastSeen}) >= 0 and (as_timestamp(now()) - ${lastSeen}) < 10 and ${lastSeen} >= (arrival_at | float)`;
  return {
    alias:'Door PINs: unlock when arriving near the door',
    description:'Created by Door PINs. Observes a departure and continuous minimum time away before accepting a return. Enabling or restarting while already away does not arm unlocking.',
    initial_state:false,
    // Template truth stays stable across forced GPS reports and named away zones.
    // Cancellation triggers must reach actions: rejected top-level conditions do not restart a run.
    triggers:[{trigger:'template',value_template:`{{ ${away} }}`,for:{seconds:awaySeconds},id:'away_ready'},{trigger:'state',entity_id:source,from:'home',not_to:'home',id:'cancel_departure'},{trigger:'state',entity_id:source,to:['unknown','unavailable'],id:'cancel_invalid'}],
    conditions:[],
    actions:[{condition:'template',value_template:`{{ ${trigOk} and ${away} }}`},{wait_template:`{{ states('${source}') in ['home', 'unknown', 'unavailable'] }}`},{condition:'state',entity_id:source,state:'home'},{variables:{arrival_at:'{{ as_timestamp(now()) }}'}},{wait_template:`{{ not is_state('${source}', 'home') or (${nearbyFresh}) }}`,timeout:'00:30:00',continue_on_timeout:false},{condition:'template',value_template:`{{ is_state('${source}', 'home') and ${nearbyFresh} }}`},{condition:'state',entity_id:source,state:'home'},{condition:'state',entity_id:lock,state:'locked'},{action:'lock.unlock',target:{entity_id:lock}}],
    mode:'restart'
  };
}
class AugustPinManager extends HTMLElement {
  set hass(value) { this._hass=value; if(!this.started){this.started=true; this.attachShadow({mode:'open'}); this.refresh();} }
  async api(action,data={}) { return await this._hass.callApi(action?'POST':'GET','august_local_keypad/manage',action?{action,...data}:undefined); }
  element(tag,text,attrs={}) { const n=document.createElement(tag);if(text!==null)n.textContent=text;Object.assign(n,attrs);return n; }
  button(text,fn,host) { const b=this.element('button',text);b.onclick=fn;host.append(b);return b; }
  async refresh(){
    try{
      const model=await this.api();if(model.error)throw model;
      this.model=model;this.render();
      if(this.busy)this.setBusy(true,this.busyLabel);
      return true;
    }catch(e){this.message('Could not refresh PIN status. Check the connection before submitting another operation.');return false;}
  }
  message(text){
    let status=this.shadowRoot.querySelector('#message');
    if(!status){status=this.element('div','',{id:'message'});status.setAttribute('role','status');status.setAttribute('aria-live','polite');this.shadowRoot.append(status);}
    status.textContent=text;
  }
  setBusy(active,label='Working…'){
    this.busy=active;this.busyLabel=label;
    this.shadowRoot.host.setAttribute('aria-busy',String(active));
    if(active){
      this.disabledControls??=new Map();
      for(const control of this.shadowRoot.querySelectorAll('button,input,select')){
        if(!this.disabledControls.has(control))this.disabledControls.set(control,control.disabled);
        control.disabled=true;
      }
      if(!this.shadowRoot.querySelector('#operation-progress')){
        const style=this.element('style',`#operation-progress{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:1000;display:flex;gap:12px;align-items:center;max-width:85vw;padding:16px;border-radius:10px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#222);box-shadow:0 2px 12px #0005}.operation-spinner{width:22px;height:22px;flex-shrink:0;border:3px solid var(--divider-color,#ccc);border-top-color:var(--primary-color,#03a9f4);border-radius:50%;animation:pin-progress 1s linear infinite}@keyframes pin-progress{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.operation-spinner{animation:none}}`,{id:'operation-progress-style'});
        const progress=this.element('div','',{id:'operation-progress'});progress.setAttribute('role','status');progress.setAttribute('aria-live','polite');
        const spinner=this.element('span','',{className:'operation-spinner'});spinner.setAttribute('aria-hidden','true');
        progress.append(spinner,this.element('span',label,{id:'operation-progress-label'}));
        this.shadowRoot.append(style,progress);
      }else this.shadowRoot.querySelector('#operation-progress-label').textContent=label;
    }else{
      for(const [control,disabled] of this.disabledControls||[])control.disabled=disabled;
      this.disabledControls=null;
      this.shadowRoot.querySelector('#operation-progress')?.remove();
      this.shadowRoot.querySelector('#operation-progress-style')?.remove();
    }
  }
  async run(action,data,success){
    if(this.busy)return;
    const label=['create','program','delete','provision','recover','probe','initialize'].includes(action)?'Waiting for Bluetooth… This can take over a minute. Do not submit again.':'Working…';
    this.setBusy(true,label);this.message(label);
    try{
      let result,failure;
      try{result=await this.api(action,data);if(result.error)throw result;}
      catch(error){failure=error;}
      const refreshed=await this.refresh();
      if(failure){
        this.message((failure.body?.error||failure.message||failure.error||'Operation outcome could not be confirmed. Do not retry blindly.')+(refreshed?'':' Status refresh also failed; the displayed record may be stale.'));
        return;
      }
      if(!refreshed){this.message('Request completed, but PIN status could not be refreshed. Do not repeat the write; refresh status after checking the connection.');return;}
      this.message(['create','program','recover'].includes(action)?'Programming acknowledged. Keypad acceptance is unverified; check pairing and physically test only when unlocking is safe.':success||'Completed.');
      return result;
    }finally{this.setBusy(false);}
  }
  render(){
    this._autoLockGen=(this._autoLockGen||0)+1;this._arrivalStep=null;
    const root=this.shadowRoot;root.innerHTML=`<style>:host{display:block;padding:28px;color:var(--primary-text-color);background:var(--primary-background-color);min-height:100vh;box-sizing:border-box;font:15px system-ui}header{display:flex;align-items:center;height:56px;margin:-28px -28px 20px;padding:0 12px;background:var(--app-header-background-color);color:var(--app-header-text-color)}h1{font-size:20px;margin:0 0 0 12px}.note{color:var(--secondary-text-color);line-height:1.5;max-width:900px}.card{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:12px;padding:20px;margin-top:22px;overflow:auto}table{border-collapse:collapse;width:100%;min-width:700px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--divider-color)}button{border:0;border-radius:7px;padding:10px 14px;margin:4px;background:var(--primary-color);color:var(--text-primary-color);cursor:pointer}button:disabled{opacity:.5}input,select{font:inherit;padding:10px;border:1px solid var(--divider-color);border-radius:6px;background:var(--card-background-color);color:var(--primary-text-color);margin:6px}label{display:block;margin:10px 0}#message{white-space:pre-wrap;margin:15px 0}form{max-width:620px}.section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}h2{font-size:18px;margin:0}h3{font-size:16px;margin:0 0 12px}.section-head button{margin:0 0 0 8px}.subtle{color:var(--secondary-text-color);line-height:1.5}.secondary{background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color)}details{margin-top:18px}summary{cursor:pointer;color:var(--secondary-text-color)}.card form.card{margin:16px 0;padding:16px}.layout{max-width:1100px;margin:auto}.settings-card{margin-bottom:24px}.actions{white-space:nowrap}.mask{font-family:monospace}.pin-box{background:#3b3b3b;color:#fff;font-family:monospace;min-width:94px;letter-spacing:2px}a{color:var(--primary-color)}@media(max-width:700px){:host{padding:16px}header{margin:-16px -16px 20px}table{min-width:0}thead{display:none}tbody tr{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--divider-color);padding:8px 0}td{display:block;border:0;overflow-wrap:anywhere}td::before{content:attr(data-label);display:block;font-size:12px;color:var(--secondary-text-color);margin-bottom:5px}td:last-child{grid-column:1/-1;white-space:normal}}</style><header><ha-menu-button></ha-menu-button><h1>Door PINs</h1></header><main class="layout"><div id="message" role="status" aria-live="polite"></div><section class="card"><div class="section-head"><h2>PIN management</h2><div id="toolbar"></div></div><div id="editor"></div><table><thead></thead><tbody></tbody></table><p id="empty"></p><details id="advanced"><summary>Advanced PIN setup</summary><div id="advanced-tools"></div></details></section><section class="card settings-card" id="settings"><div class="section-head"><h2>Lock settings</h2></div><p class="subtle">Auto-lock timing saved directly on your lock.</p><div id="settings-tools"></div><div id="settings-editor"></div></section></main>`;
    const tools=root.querySelector('#toolbar');this.button('Refresh',()=>this.refresh(),tools).className='secondary';this.button('Add PIN',()=>this.edit(null),tools);
    root.querySelector('#editor').before(this.element('p','Programmed means the lock acknowledged a write, not that the physical keypad has been tested. Confirm keypad pairing. Day/time restrictions are not yet verified; manage scheduled codes in the August app.',{className:'note'}));
    if(this.model.admin)this.button('Configure auto-lock',()=>this.autoLock(),root.querySelector('#settings-tools'));else root.querySelector('#settings').remove();
    if(this.model.admin)this.button('Arrival unlock',()=>this.arrivalSettings(),root.querySelector('#settings-tools')).className='secondary';
    if(this.model.admin)this.button('Provision PIN capacity',()=>this.provision(),tools).className='secondary';else root.querySelector('#advanced').remove();
    if(this.model.admin)this.button('Import existing August codes',()=>this.run('import',{},'Import completed. Existing local PINs were preserved.'),root.querySelector('#advanced-tools')).className='secondary';
    if(this.model.admin){
      this.button('Read slot occupancy',()=>this.probeSlot(),root.querySelector('#advanced-tools')).className='secondary';
      this.button('HA-only initialization (last resort)',()=>this.initializeHA(),root.querySelector('#advanced-tools')).className='secondary';
    }
    const tr=document.createElement('tr');for(const h of ['Slot','Name','HA account','PIN','Status','Actions'])tr.append(this.element('th',h));root.querySelector('thead').append(tr);
    const records=this.model.records.filter(r=>r.has_pin || !['reserved','cleared'].includes(r.status));
    if(records.some(record=>record.status==='needs_attention'||record.status==='pending'))root.querySelector('#editor').before(this.element('p','Needs recovery means a previous PIN operation was not confirmed. It does not prove the PIN is absent or invalid. Retained values are kept for recovery; do not repeatedly delete and re-add the code.',{className:'note'}));
    for(const record of records){const row=document.createElement('tr');row.append(this.element('td',String(record.slot)),this.element('td',record.name||''));const owner=this.model.users.find(u=>u.id===record.owner_id);row.append(this.element('td',owner?.name || (record.owner_id?'Assigned account':'Admin only')));const pinCell=this.element('td',record.has_pin?null:'None',{className:'mask'});if(record.has_pin){const box=this.button('••••••',async()=>{if(box.dataset.shown){box.textContent='••••••';delete box.dataset.shown;return;}try{const r=await this.api('reveal',{slot:record.slot});box.textContent=r.pin;box.dataset.shown='1';setTimeout(()=>{box.textContent='••••••';delete box.dataset.shown;},10000);}catch(e){this.message('PIN unavailable.');}},pinCell);box.className='pin-box';box.setAttribute('aria-label','Show or hide PIN');}row.append(pinCell);row.append(this.element('td',({active:'Active',imported:'Active',needs_attention:'Needs recovery',programming:'Saving',deleting:'Deleting'})[record.status]||record.status));const actions=this.element('td','',{className:'actions'});this.button(record.has_pin?'Change PIN':'Set PIN',()=>this.edit(record),actions);if(record.has_pin){this.button('Delete',()=>{if(confirm(`Delete the keypad PIN in slot ${record.slot}? The door will not be operated.`))this.run('delete',{slot:record.slot},`Slot ${record.slot} deleted. Confirm that the keypad rejects the old PIN.`);},actions);}if(this.model.admin)this.button('Assign / rename',()=>this.assign(record),actions);row.append(actions);Array.from(row.children).forEach((cell,i)=>cell.setAttribute('data-label',['Slot','Name','HA account','PIN','Status','Actions'][i]));root.querySelector('tbody').append(row);}
    root.querySelector('#empty').textContent=records.length?'':'Use Add PIN to reuse an acknowledged HA-cleared slot. New unknown slots require verified capacity. For an old blocked record, use Restore known HA slot with its last known code.';
    for(const record of records.filter(r=>r.source==='local'&&r.has_pin&&['needs_attention','pending'].includes(r.status)))this.button(`Recover / replace slot ${record.slot}`,()=>this.recoverPin(record),tools);
    if(this.model.admin)for(const record of this.model.records.filter(r=>r.source==='local_discovered'&&r.status==='reserved'&&!r.has_pin&&!r.verified_empty))this.button(`Restore known HA slot ${record.slot}`,()=>this.recoverPin(record),tools);

  }
  edit(record){const host=this.shadowRoot.querySelector('#editor');host.replaceChildren();const form=this.element('form','',{className:'card'});form.append(this.element('h2',record?`Set PIN · slot ${record.slot}`:'Add PIN'),this.element('p',record?.has_pin?'Enter 4–6 digits. This replaces the current code.':'Enter 4–6 digits to set a new PIN.'));const name=this.element('input',null,{type:'text',maxLength:80,value:'',placeholder:'e.g. Guest or cleaner'});if(!record){name.setAttribute('aria-label','PIN name');const l=this.element('label','Name');l.append(name);form.append(l);}const first=this.element('input',null,{type:'password',inputMode:'numeric',minLength:4,maxLength:6,required:true,autocomplete:'new-password'});first.setAttribute('aria-label','New PIN');const second=this.element('input',null,{type:'password',inputMode:'numeric',minLength:4,maxLength:6,required:true,autocomplete:'new-password'});second.setAttribute('aria-label','Confirm new PIN');for(const [label,input] of [['New PIN',first],['Confirm new PIN',second]]){const l=this.element('label',label);l.append(input);form.append(l);}const b=this.element('button','Save PIN',{type:'submit'});form.append(b);form.onsubmit=async e=>{e.preventDefault();if(first.value!==second.value){this.message('The PINs do not match.');return;}if(!/^[0-9]{4,6}$/.test(first.value)){this.message('Enter 4–6 ASCII digits.');return;}const pin=first.value;const label=name.value;first.value='';second.value='';host.replaceChildren();await this.run(record?'program':'create',record?{slot:record.slot,pin}:{pin,name:label},'PIN saved.');};this.button('Cancel',()=>host.replaceChildren(),form).type='button';host.append(form);first.focus();}
  recoverPin(record){
    const host=this.shadowRoot.querySelector('#editor');host.replaceChildren();
    const form=this.element('form','',{className:'card'});
    form.append(this.element('h3',`Recover HA slot ${record.slot}`),this.element('p','Clear only the retained HA-created PIN candidates in this slot, then set a replacement. Each clear must be acknowledged before programming continues. This does not discover other slots or move the deadbolt. Keep this slot exclusive to HA.'));
    const pin=this.element('input',null,{type:'password',inputMode:'numeric',minLength:4,maxLength:6,required:true,autocomplete:'new-password'});
    const repeat=this.element('input',null,{type:'password',inputMode:'numeric',minLength:4,maxLength:6,required:true,autocomplete:'new-password'});
    const confirmClear=this.element('input',null,{type:'checkbox',required:true});
    let previous;
    if(!record.has_pin){
      previous=this.element('input',null,{type:'password',inputMode:'numeric',minLength:4,maxLength:6,required:true,autocomplete:'off'});
      previous.setAttribute('aria-label','Last known HA PIN');const label=this.element('label','Last known HA PIN');label.append(previous);form.append(label);
      form.append(this.element('p','The old failed preflight no longer retains a PIN for this slot. Only restore it if it was dedicated to HA and you know its last code. The supplied code must be successfully cleared before a replacement is sent. This is not automatic occupancy discovery.'));
    }
    for(const [text,input]of[['Replacement PIN',pin],['Confirm replacement PIN',repeat],['Clear retained HA-created codes in this slot',confirmClear]]){const label=this.element('label',text);input.setAttribute('aria-label',text);label.append(input);form.append(label);}
    form.append(this.element('button','Recover and replace PIN',{type:'submit'}));
    form.onsubmit=async event=>{
      event.preventDefault();
      if(!confirmClear.checked){this.message('Confirm clearing the retained HA-created codes first.');return;}
      if(!/^[0-9]{4,6}$/.test(pin.value)||pin.value!==repeat.value){this.message('Enter matching PINs of 4–6 ASCII digits.');return;}
      if(previous&&!/^[0-9]{4,6}$/.test(previous.value)){this.message('Enter the last known HA-created PIN for this slot.');return;}
      const value=pin.value;pin.value='';repeat.value='';
      const oldValue=previous?.value;if(previous)previous.value='';
      await this.run('recover',{slot:record.slot,pin:value,confirmed_clear:true,...(previous?{previous_pin:oldValue}:{})});
    };
    this.button('Cancel',()=>host.replaceChildren(),form).type='button';host.append(form);pin.focus();
  }
  async autoLock(forceRead=false){
    if(this.busy)return;
    if(!forceRead&&this._autoLockVisibleGen===this._autoLockGen&&this._autoLockForm?.parentNode)return;
    this._arrivalStep=null;
    const host=this.shadowRoot.querySelector('#settings-editor');
    const myGen=this._autoLockGen=(this._autoLockGen||0)+1;
    const current=()=>this._autoLockGen===myGen;
    host.replaceChildren();this.message('');
    const form=this.element('form','',{className:'card'});
    this._autoLockForm=form;this._autoLockVisibleGen=myGen;
    const card=this.element('ha-card','');card.style='display:block;padding:16px';form.append(card);
    card.append(this.element('h3','Auto-lock'),this.element('p','Runs on the lock, even when Home Assistant is offline.'));
    const loading=this.element('p','Reading current setting from lock…',{className:'subtle'});
    loading.setAttribute('role','status');
    loading.prepend(this.element('ha-circular-progress',null,{indeterminate:true}));card.append(loading);
    const mode=this.element('select',null,{disabled:true});mode.setAttribute('aria-label','Auto-lock mode');
    for(const [value,label]of[['off','Off'],['timer','Timed relock'],['instant','Door-close relock']])mode.append(this.element('option',label,{value}));
    const seconds=this.element('input',null,{type:'text',value:'',placeholder:'30s, 5m, or 10m',autocomplete:'off',disabled:true});seconds.setAttribute('aria-label','Auto-lock delay');
    for(const [text,input]of[['Mode',mode],['Delay',seconds]]){const label=this.element('label',text);label.append(input);card.append(label);}
    card.append(this.element('p','Use s for seconds, m for minutes, or h for hours.',{className:'subtle'}));
    const save=this.element('button','Save to lock',{type:'submit',disabled:true});card.append(save);
    const read=this.button('Read again',()=>this.autoLock(true),card);read.type='button';read.disabled=true;
    this.button('Close',()=>{this._autoLockGen++;this._autoLockVisibleGen=null;host.replaceChildren();},card).type='button';
    let ready=false,saving=false;
    mode.onchange=()=>seconds.disabled=!ready||mode.value==='off';
    form.onsubmit=async event=>{
      event.preventDefault();if(!ready||saving||this.busy||!current())return;
      let delay=0;
      try{if(mode.value!=='off')delay=parseDuration(seconds.value);}
      catch(error){this.message(error.message);seconds.focus();return;}
      saving=true;this.setBusy(true,'Saving auto-lock… Wait for confirmation before trying again.');
      try{
        const result=await this.api('auto_lock_save',{mode:mode.value,seconds:delay});if(result.error)throw result;
        if(current()){this._autoLockGen++;host.replaceChildren();this.message(result.mode==='off'?'Auto-lock is off; confirmed on the lock.':`Auto-lock saved and read back: ${result.mode}, ${formatDuration(result.seconds)}.`);}
      }catch(error){if(current())this.message(error.body?.error||error.message||error.error||'Save could not be confirmed. Read the setting before retrying.');}
      finally{saving=false;this.setBusy(false);if(current())mode.onchange();}
    };
    host.append(form);
    if(!this._autoLockRead){
      this._autoLockRead=this.api('auto_lock_read');
      this._autoLockReading=true;
    }
    const request=this._autoLockRead;
    try{
      const state=await request;if(state.error)throw state;
      if(!current())return;
      loading.remove();ready=true;mode.value=state.mode;mode.disabled=false;
      seconds.value=formatDuration(state.seconds||30);mode.onchange();save.disabled=false;read.disabled=false;
    }catch(error){if(current()){loading.textContent='Reading failed. No setting change was requested.';this.message(error.body?.error||error.message||error.error||'Auto-lock reading failed.');read.disabled=false;}}
    finally{if(this._autoLockRead===request){this._autoLockRead=null;this._autoLockReading=false;}}
  }
  arrival(){this._autoLockGen=(this._autoLockGen||0)+1;const host=this.shadowRoot.querySelector('#settings-editor');host.replaceChildren();this.message('');const form=this.element('form','',{className:'card'});form.append(this.element('h3','Arrival unlock'),this.element('p','Create a Home Assistant automation using location and nearby Bluetooth detection. It starts disabled so you can review and enable it.'));const source=this.element('select',null);source.setAttribute('aria-label','Person or phone');source.append(this.element('option','Select a person or phone',{value:''}));const choices=Object.values(this._hass.states).filter(s=>s.entity_id.startsWith('person.')||(s.entity_id.startsWith('device_tracker.')&&s.attributes.source_type==='gps'));for(const state of choices.sort((a,b)=>(a.attributes.friendly_name||a.entity_id).localeCompare(b.attributes.friendly_name||b.entity_id)))source.append(this.element('option',`${state.attributes.friendly_name||state.entity_id} (${state.entity_id})`,{value:state.entity_id}));const lock=this.element('select',null);lock.setAttribute('aria-label','Arrival unlock lock');for(const row of this.model.locks||[])lock.append(this.element('option',row.name,{value:row.entity_id}));const near=this.element('select',null);near.setAttribute('aria-label','Nearby phone sensor');near.append(this.element('option','Select nearby detection',{value:''}));for(const p of this.model.nearby_profiles||[])if(p.entity_id)near.append(this.element('option',p.name,{value:p.entity_id}));const away=this.element('input',null,{type:'text',value:'5m',placeholder:'5m',required:true});away.setAttribute('aria-label','Minimum time away');for(const [label,input]of[['Person or phone',source],['Lock',lock],['Nearby phone detection',near],['Minimum time away',away]]){const l=this.element('label',label);l.append(input);form.append(l);}form.append(this.element('p','Arms after time away, then waits up to 30 minutes for fresh nearby phone detection at the door. Unlocks once while the phone is home and the lock is locked. BLE proximity is a signal, not authenticated phone-to-lock pairing.',{className:'subtle'}));const result=this.element('p','',{role:'status'});form.append(result);const save=this.element('button','Create automation',{type:'submit'});form.append(save);form.onsubmit=async e=>{e.preventDefault();let config,id;try{const secs=parseDuration(away.value);config=arrivalAutomation(source.value,lock.value,secs,near.value);id=`${this.model.arrival_prefix}_near_${source.value.replace('.','_')}_${lock.value.replace('.','_')}`;}catch(e){result.textContent=e.message;return;}let existing=Object.values(this._hass.states).find(s=>s.entity_id.startsWith('automation.')&&s.attributes.id===id);if(!existing){try{existing=await this._hass.callApi('GET',`config/automation/config/${id}`);}catch(e){if(e.status_code!==404&&e.status!==404){result.textContent='Could not check for an existing automation. No changes were made.';return;}}}if(existing){result.textContent='This arrival automation already exists. Open it to change its settings.';}else{save.disabled=true;try{await this._hass.callApi('POST',`config/automation/config/${id}`,config);result.textContent='Automation created, disabled. Review it in Home Assistant, then use Enable arrival unlock below when ready.';}catch(e){result.textContent=e.body?.message||'Automation could not be created. Check that HA automation editing is available.';save.disabled=false;return;}}save.disabled=true;const link=this.element('a','Open automation',{href:`/config/automation/edit/${id}`});result.append(document.createElement('br'),link);const enable=this.button('Enable arrival unlock',async()=>{if(!confirm('Enable automatic unlocking when this selected person or phone returns home?'))return;enable.disabled=true;try{const current=await this._hass.callApi('GET',`config/automation/config/${id}`);delete current.initial_state;await this._hass.callApi('POST',`config/automation/config/${id}`,current);await this._hass.callService('automation','reload',{});const states=await this._hass.callWS({type:'get_states'});const entity=states.find(s=>s.entity_id.startsWith('automation.')&&s.attributes.id===id);if(!entity)throw new Error('Automation not loaded yet. Try again after HA finishes loading.');await this._hass.callService('automation','turn_on',{entity_id:entity.entity_id});result.textContent='Arrival unlock enabled. You can manage it in HA Automations.';}catch(e){result.textContent=e.message||'Could not confirm enabling. Check HA Automations.';enable.disabled=false;}},form);};this.button('Cancel',()=>{this._arrivalStep=null;host.replaceChildren();},form).type='button';host.append(form);form.scrollIntoView({behavior:'smooth',block:'nearest'});}
  nearby(){this._autoLockGen=(this._autoLockGen||0)+1;const host=this.shadowRoot.querySelector('#settings-editor');host.replaceChildren();this.message('');const form=this.element('form','',{className:'card'});form.append(this.element('h3','Nearby phone detection'),this.element('p','Select the phone BLE Transmitter and the Bluetooth proxy beside the door.'));const sensor=this.element('select',null);sensor.setAttribute('aria-label','Phone BLE Transmitter');sensor.append(this.element('option','Select phone transmitter',{value:''}));for(const state of Object.values(this._hass.states).filter(s=>s.entity_id.startsWith('sensor.')&&s.entity_id.includes('ble_transmitter')))sensor.append(this.element('option',state.attributes.friendly_name||state.entity_id,{value:state.entity_id}));const receiver=this.element('select',null);receiver.setAttribute('aria-label','Door Bluetooth receiver');for(const r of this.model.receivers||[])receiver.append(this.element('option',r.name||r.source,{value:r.source}));const threshold=this.element('input',null,{type:'number',min:-90,max:-30,step:1,value:'-65',required:true});threshold.setAttribute('aria-label','Nearby signal threshold');if(sensor.options.length===2)sensor.selectedIndex=1;const loadProfile=()=>{const p=(this.model.nearby_profiles||[]).find(p=>p.sensor===sensor.value);threshold.value=String(p?.threshold??-65);if(p)receiver.value=p.source;};sensor.onchange=loadProfile;loadProfile();for(const [label,input]of[['Phone',sensor],['Door receiver',receiver],['Nearby threshold (dBm)',threshold]]){const l=this.element('label',label);l.append(input);form.append(l);}form.append(this.element('p','Less negative means closer: −55 is stricter than −65. Detection requires fresh strong broadcasts for at least 2 seconds and expires after 10 seconds. Test both at the door and farther away before enabling unlock.',{className:'subtle'}));const result=this.element('p','',{role:'status'});form.append(result,this.element('button','Save detection',{type:'submit'}));form.onsubmit=async e=>{e.preventDefault();try{const r=await this.api('nearby_save',{sensor:sensor.value,source:receiver.value,threshold:Number(threshold.value)});if(r.error)throw new Error(r.error);this.model=await this.api();result.textContent='Detection saved. Refresh status to calibrate; this does not unlock the door.';}catch(e){result.textContent=e.body?.error||e.message||'Detection could not be saved.';}};this.button('Refresh status',async()=>{this.model=await this.api();const p=(this.model.nearby_profiles||[]).find(p=>p.sensor===sensor.value);const state=p?.entity_id?this._hass.states[p.entity_id]:null;const age=state?.attributes.last_seen?Math.max(0,Math.round((Date.now()-Date.parse(state.attributes.last_seen))/1000)):null;result.textContent=state?`${state.state==='on'?'Near door':'Not near door'} · signal ${state.attributes.rssi??'not received'} dBm · threshold ${state.attributes.threshold} dBm${age===null?'':` · last received ${age}s ago`}`:'Save detection first, then refresh when the sensor has loaded.';},form).type='button';this.button('Close',()=>{this._arrivalStep=null;host.replaceChildren();},form).type='button';host.append(form);form.scrollIntoView({behavior:'smooth',block:'nearest'});}
  provision(){
    const host=this.shadowRoot.querySelector('#editor');host.replaceChildren();
    const form=this.element('form','',{className:'card'});
    form.append(this.element('h2','Provision PIN capacity'),this.element('p',this.model.initialization?.exclusive?'Expand capacity using unused slots from the acknowledged HA-only clear. No discovery read or additional erase is needed. All keypad code writes on this lock must remain exclusive to HA, including slots not yet allocated. This does not create a PIN or unlock the door.':'Discover empty slots without overwriting existing codes. If the lock cannot confirm occupancy, provisioning stops. This does not create a PIN or unlock the door.'));
    const mode=this.element('select',null);mode.setAttribute('aria-label','Provisioning mode');
    mode.append(this.element('option',`Automatic: one slot per HA user (${this.model.users.length})`,{value:'users'}),this.element('option','Choose total HA PIN capacity',{value:'count'}));
    const count=this.element('input',null,{type:'number',min:1,max:50,value:String(Math.max(1,this.model.users.length)),disabled:true});count.setAttribute('aria-label','Total HA PIN capacity');
    mode.onchange=()=>{count.disabled=mode.value!=='count';count.required=mode.value==='count';};
    for(const [text,input] of [['Provisioning mode',mode],['Total capacity (not slot numbers)',count]]){const label=this.element('label',text);label.append(input);form.append(label);}
    form.append(this.element('p','Automatic mode assigns capacity only, not a generated code. Use Add PIN afterwards. Extra capacity allows additional manually named PINs.'));
    form.append(this.element('button',this.model.initialization?.exclusive?'Provision HA-only capacity':'Discover and provision',{type:'submit'}));
    form.onsubmit=async event=>{event.preventDefault();const result=await this.run('provision',mode.value==='count'?{count:Number(count.value)}:{},'Verified PIN capacity provisioned. Use Add PIN to set a code.');if(result)this.message(`Provisioned ${result.total} HA slots; ${result.assigned} assigned to users. No PINs were generated.`);};
    this.button('Cancel',()=>host.replaceChildren(),form).type='button';host.append(form);
  }
  probeSlot(){
    if(this.busy||!this.model.admin)return;
    const host=this.shadowRoot.querySelector('#editor');host.replaceChildren();
    const form=this.element('form','',{className:'card'});
    form.append(this.element('h2','Read slot occupancy'),this.element('p','Read-only diagnostic: no PIN writes, slot allocation or motor operation. A timeout is unknown, not empty or full.'));
    const slot=this.element('input',null,{type:'number',min:1,max:255,value:String(this.model.records?.[0]?.slot||1),required:true});slot.setAttribute('aria-label','Slot to inspect');
    const label=this.element('label','Slot to inspect');label.append(slot);form.append(label,this.element('button','Read slot',{type:'submit'}));
    form.onsubmit=async event=>{
      event.preventDefault();if(this.busy)return;
      const value=Number(slot.value);
      if(!Number.isInteger(value)||value<1||value>255){this.message('Choose a slot from 1 through 255.');return;}
      const result=await this.run('probe',{slot:value});
      if(result){
        const state=result.slots?.find(record=>record.slot===value)?.state;
        const status=['occupied','empty'].includes(state)?state:'unknown';
        this.message(`Slot ${value}: ${status}. ${status==='unknown'?(result.reason||'Occupancy was not confirmed.')+' ':''}No slots allocated or PIN changes sent.`);
      }
    };
    this.button('Cancel',()=>host.replaceChildren(),form).type='button';host.append(form);slot.focus();
  }
  initializeHA(){
    if(this.busy||!this.model.admin)return;
    const host=this.shadowRoot.querySelector('#editor');host.replaceChildren();
    const form=this.element('form','',{className:'card'});
    form.append(this.element('h2','HA-only initialization — last resort'),this.element('p',`Erases ALL keypad PINs on ${this.model.locks?.[0]?.name||'the configured lock'}, including August-created codes. Keep another way to enter. This does not reset the lock, unpair the keypad, change ownership or move the deadbolt. Clear-all hardware behaviour has not yet been verified.`),this.element('p','Use existing-code import or known-slot replacement first. This action is never an automatic fallback for failed discovery. Afterwards, keep code writes exclusive to HA: local clearing does not delete cloud PIN records, and official-app Bluetooth synchronization may restore August codes or reuse slots.'));
    const mode=this.element('select',null);mode.setAttribute('aria-label','Initialization capacity mode');
    mode.append(this.element('option',`Automatic: one per HA user (${this.model.users.length})`,{value:'users'}),this.element('option','Choose total HA capacity',{value:'count'}));mode.value='users';
    const count=this.element('input',null,{type:'number',min:1,max:50,value:String(Math.max(1,this.model.users.length)),disabled:true});count.setAttribute('aria-label','Initialization total capacity');
    mode.onchange=()=>{count.disabled=mode.value!=='count';count.required=mode.value==='count';};
    const confirmation=this.element('input',null,{type:'text',value:'',required:true,autocomplete:'off'});confirmation.setAttribute('aria-label','Type ERASE ALL KEYPAD CODES');
    for(const [text,input]of[['Capacity mode',mode],['Total HA capacity',count],['Type ERASE ALL KEYPAD CODES',confirmation]]){const label=this.element('label',text);label.append(input);form.append(label);}
    form.append(this.element('p','This chooses HA capacity, not a measured hardware limit. No PINs are generated; use Add PIN after a confirmed clear. Interrupted operations retain recovery data and are never automatically retried.'),this.element('button','Erase all keypad codes and initialize HA',{type:'submit'}));
    let operationId;
    form.onsubmit=async event=>{
      event.preventDefault();if(this.busy)return;
      if(confirmation.value!=='ERASE ALL KEYPAD CODES'){this.message('Type ERASE ALL KEYPAD CODES exactly before sending a clear-all request.');return;}
      const total=mode.value==='count'?Number(count.value):this.model.users.length;
      if(!Number.isInteger(total)||total<1||total>50){this.message('Choose total HA capacity from 1 through 50.');return;}
      if(!operationId){
        if(!globalThis.crypto?.getRandomValues){this.message('Secure browser randomness is unavailable; no initialization request sent.');return;}
        operationId=Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
      }
      const result=await this.run('initialize',{confirmation:confirmation.value,operation_id:operationId,...(mode.value==='count'?{count:total}:{})});
      if(result)this.message(result.replayed?'This initialization request was already processed. No new clear was sent; review the refreshed status.':`Clear-all acknowledged. Prepared ${result.total} HA slots; ${result.assigned} assigned. No PINs generated. Use Add PIN; physical keypad acceptance still needs checking when safe.`);
    };
    this.button('Cancel',()=>host.replaceChildren(),form).type='button';host.append(form);confirmation.focus();
  }
  arrivalSettings(step='nearby'){
    if(this.busy)return;
    if(this._arrivalStep===step)return;
    this._arrivalStep=step;
    this._autoLockGen=(this._autoLockGen||0)+1;
    if(step==='arrival')this.arrival();else this.nearby();
    const navigation=this.element('div','');
    navigation.append(this.element('h3','Arrival unlock'),this.element('p','Configure phone proximity first, then combine it with arrival detection. Creating a profile does not enable unlocking.'));
    this.button('1. Phone proximity',()=>this.arrivalSettings('nearby'),navigation).className='secondary';
    this.button('2. Arrival automation',()=>this.arrivalSettings('arrival'),navigation).className='secondary';
    this.shadowRoot.querySelector('#settings-editor').prepend(navigation);
  }
  assign(record){const host=this.shadowRoot.querySelector('#editor');host.replaceChildren();const form=this.element('form','',{className:'card'});form.append(this.element('h2',`Assign / rename · slot ${record.slot}`));const name=this.element('input',null,{value:record.name||'',maxLength:80});name.setAttribute('aria-label','PIN label');const select=this.element('select',null);select.setAttribute('aria-label','HA account');select.append(this.element('option','Admin only',{value:''}));for(const user of this.model.users)select.append(this.element('option',user.name,{value:user.id}));select.value=record.owner_id||'';for(const [label,input]of[['PIN label',name],['HA account',select]]){const l=this.element('label',label);l.append(input);form.append(l);}form.append(this.element('p','Assignment grants that account access to reveal, change, and delete this slot’s code. Other slots stay private.'));form.append(this.element('button','Save assignment',{type:'submit'}));form.onsubmit=e=>{e.preventDefault();const target=select.options[select.selectedIndex].textContent;if(confirm(`Grant ${target} management of slot ${record.slot}?`))this.run('assign',{slot:record.slot,name:name.value,owner_id:select.value},'Assignment saved.');};this.button('Cancel',()=>host.replaceChildren(),form).type='button';host.append(form);form.scrollIntoView({behavior:'smooth',block:'nearest'});}
}
customElements.define('august-pin-manager',AugustPinManager);
for(const tag of['august-pin-manager-v28','august-pin-manager-v27']){
  try{customElements.define(tag,class extends AugustPinManager{});}catch(_){}
}
