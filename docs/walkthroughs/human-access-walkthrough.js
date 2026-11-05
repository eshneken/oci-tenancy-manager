/** Single V1 human-access preview; persistent recovery credentials are never actually loaded or changed. */
(() => {
 'use strict';
 /** Resolve a control only within this static access page. */
 const byId=id=>document.getElementById(id);
 const fourHours=14400000;
 let firstAttempt=Date.parse('2026-10-24T14:00:00Z'),exposureGeneration=6,credentialVersion=12,sequence=0,pendingAction=null,returnFocus=null,navigationNotice=null;
 const aliases={'support-request':'access-ready','support-enrollment':'access-ready','support-granted':'access-ready','support-cleanup':'access-ready','support-expired':'access-ready','emergency-review':'access-blocked','emergency-ready':'access-ready','emergency-window':'access-window'};
 const identity=[['Account','otm-recovery'],['Identity domain','Default']];
 const states={
 'access-ready':{status:'Available',summary:'Use the managed recovery account for occasional console access.',facts:[...identity,['Authentication','MFA exempt · this account only'],['Credential storage','OCI Vault · unique per tenancy']],actions:[['Get password','retrieve'],['Recovery instructions','procedure']],note:'Each retrieval is audited and notifies other administrators and the tenancy owner/manager.',next:['Password rotation','The password rotates four hours after the first authorized retrieval request. Further retrievals do not extend that deadline.']},
 'access-window':{status:'Rotation scheduled',summary:'Access was recorded. Use the account below to sign in to this tenancy.',facts:[...identity,['First retrieval request','first'],['Password rotation due','due']],actions:[['Get password again','retrieve-again'],['Recovery instructions','procedure']],secret:true,note:'Further retrievals have their own audit and notifications. The original rotation deadline stays fixed.',next:['After use','The recovery account remains in place. OTM rotates its password in the tenancy and OCI Vault; no temporary user is created or removed.']},
 'access-blocked':{status:'Unavailable',kind:'warn',summary:'The recovery account or credential could not be fully verified.',alert:'Password retrieval is unavailable until the required access checks pass.',facts:[...identity,['Recovery sign-in policy','Exemption not verified'],['Current credential','Unable to verify']],actions:[['View required checks','requirements'],['Recovery instructions','procedure']],next:['Restore access','Use the approved recovery procedure if automation cannot complete the checks.']},
 'rotation-running':{status:'Rotating password',kind:'warn',summary:'The password is being changed in the tenancy and OCI Vault.',alert:'Password retrieval is temporarily unavailable.',facts:[...identity,['Original rotation deadline','due'],['Rotation status','In progress']],actions:[['Check rotation','check-rotation'],['Recovery instructions','procedure']],next:['Wait for verification','A new access window can start after rotation is verified.']},
 'rotation-unknown':{status:'Rotation needs attention',kind:'danger',summary:'The password change could not be confirmed.',alert:'Password retrieval is unavailable until the current credential is confirmed.',facts:[...identity,['Original rotation deadline','due'],['Rotation status','Not verified']],actions:[['Check rotation','check-rotation'],['Recovery instructions','procedure']],next:['Use the recovery procedure','Reconcile the recorded password-change attempt before another reset. Previous passwords are not offered as a fallback.']},
 'rotation-complete':{status:'Password rotated',summary:'The password change and matching Vault version are verified.',facts:[...identity,['Previous window began','first'],['Previous rotation deadline','due']],actions:[['Get password','retrieve-new'],['Recovery instructions','procedure']],note:'The recovery account remains available. The previous password is not offered.',next:['Need access again?','A new audited request starts a separate four-hour rotation window.']}
 };
 /** Render sample data as text rather than injecting markup. */
 function element(tag,text,cls){const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;}
 /** Format UTC instants without losing dates when later windows cross midnight. */
 function formatTime(instant){const time=new Date(instant),day=new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(time);return day+' · '+String(time.getUTCHours()).padStart(2,'0')+':'+String(time.getUTCMinutes()).padStart(2,'0')+' UTC';}
 /** Resolve captured window facts, never moving an existing deadline during retrieval or checking. */
 function valueOf(value){return value==='first'?formatTime(firstAttempt):value==='due'?formatTime(firstAttempt+fourHours):value;}
 /** Render labelled facts from the exact selected sample record. */
 function facts(target,rows){byId(target).replaceChildren(...rows.map(([label,value])=>{const row=document.createElement('div');row.append(element('dt',label),element('dd',valueOf(value)));return row;}));}
 /** Normalize historical named-support links to the single current flow without creating any user. */
 function route(){const key=location.hash.slice(1);return aliases[key]||(Object.hasOwn(states,key)?key:'access-ready');}
 /** Announce an inert local result without claiming a cloud effect. */
 function notify(message){byId('feedback').hidden=false;byId('feedback').textContent=message;byId('feedback').focus();}
 /** Navigate only inside the sample; production state must come from persisted operations and evidence. */
 function navigate(target,notice=null){navigationNotice=notice;if(route()===target)render(true);else location.hash=target;}
 /** Close a dialog and restore its initiating control's keyboard focus. */
 function closeDialog(){byId('action-dialog').close();pendingAction=null;if(returnFocus?.isConnected)returnFocus.focus();else byId('page-title').focus();}
 /** Present one decision with a read-only target and the exact original or new-window deadline. */
 function showDialog(title,copy,rows,notice,confirm,action){returnFocus=document.activeElement;pendingAction=action;byId('dialog-title').textContent=title;byId('dialog-copy').textContent=copy;facts('dialog-facts',rows);byId('dialog-notice').textContent=notice;byId('dialog-notice').hidden=!notice;byId('confirm-dialog').textContent=confirm||'Done';byId('confirm-dialog').hidden=!action;byId('cancel-dialog').textContent=action?'Cancel':'Done';byId('action-dialog').showModal();byId('cancel-dialog').focus();}
 /** Dispatch sample UI actions with no SDK, secret, email or clipboard operation. */
 function act(action,button){
  if(['retrieve','retrieve-again','retrieve-new'].includes(action)){
   if(!['access-ready','access-window','rotation-complete'].includes(route()))return;
   const deadline=route()==='access-window'?'due':'Four hours after this authorized request';
   showDialog('Get administrator password','Use the persistent recovery account for this tenancy.',[['Tenancy','lab-casey-01'],...identity,['Password rotation due',deadline]],'Your request is recorded. Other administrators and the tenancy owner/manager are notified.','Get password','disclose');
  }else if(action==='procedure')showDialog('Independent recovery','Use the approved credential procedure outside OTM if the application or automation is unavailable.',[['1','Retrieve this tenancy’s password through approved independent Vault access.'],['2','Sign in using the recovery account and restore normal access.'],['3','Record use and rotate the password in both the user account and Vault.']],'No recovery procedure is configured in this preview.',null,null);
  else if(action==='requirements')showDialog('Required access checks','The account, sign-in policy and credential must be verified before password retrieval.',[['Recovery user','Present with the required administrator grants'],['Sign-in policy','MFA exemption applies only to this recovery identity'],['Credential','Known usable password and matching Vault version'],['Recovery procedure','Approved independent credential access']],'Choosing an exemption does not itself verify the deployed sign-in policy.',null,null);
  else if(action==='check-rotation'){
   const own=++sequence,from=route();button.disabled=true;button.textContent='Checking…';
   setTimeout(()=>{if(own!==sequence||route()!==from)return;navigate('rotation-unknown','Rotation is still unconfirmed. Password retrieval remains unavailable.');},450);
  }
 }
 /** Render a compact single-flow screen; model and provider details stay in Markdown. */
 function render(focus=false){
  ++sequence;if(byId('action-dialog').open)closeDialog();const key=route(),state=states[key];
  if(location.hash!=='#'+key)history.replaceState(null,'',location.pathname+location.search+'#'+key);
  byId('access-tab').href='#'+key;byId('screen').value=key;byId('section-title').textContent='Administrator access';byId('status').textContent=state.status;byId('status').className='badge '+(state.kind||'');byId('summary').textContent=state.summary;byId('alert').textContent=state.alert||'';byId('alert').hidden=!state.alert;facts('facts',state.facts);byId('credential').hidden=!state.secret;byId('password').value='';byId('feedback').hidden=true;
  byId('actions').replaceChildren(...state.actions.map(([label,action],index)=>{const button=element('button',label,index===0?'primary':'');button.type='button';button.dataset.action=action;button.addEventListener('click',()=>act(action,button));return button;}));
  byId('action-note').textContent=state.note||'';byId('action-note').hidden=!state.note;byId('next-title').textContent=state.next[0];byId('next-copy').textContent=state.next[1];byId('preview-note').textContent='Simulated observations only · exposure '+exposureGeneration+' · credential version '+credentialVersion+'. No password is loaded.';
  window.DesignNavigation.render('design-navigation','tenancies');if(focus)byId('page-title').focus({preventScroll:true});if(navigationNotice){const notice=navigationNotice;navigationNotice=null;notify(notice);}
 }
 /** Accept only an eligible local retrieval; joining requests never restart the exposure clock. */
 function submit(event){event.preventDefault();const action=pendingAction;if(action!=='disclose')return;pendingAction=null;const from=route();byId('action-dialog').close();if(!['access-ready','access-window','rotation-complete'].includes(from))return;
  // Only a separately verified completed window permits the next version/generation and a new deadline.
  if(from==='rotation-complete'){firstAttempt+=fourHours+300000;++exposureGeneration;++credentialVersion;}
  navigate('access-window');
 }
 /** Keep keyboard focus inside the native modal until it closes. */
 function trapFocus(event){if(event.key!=='Tab')return;const controls=[...byId('action-dialog').querySelectorAll('button:not([disabled])')].filter(node=>node.getClientRects().length),first=controls[0],last=controls.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}
 byId('dialog-form').addEventListener('submit',submit);byId('cancel-dialog').addEventListener('click',closeDialog);byId('close-dialog').addEventListener('click',closeDialog);byId('action-dialog').addEventListener('keydown',trapFocus);byId('action-dialog').addEventListener('cancel',event=>{event.preventDefault();closeDialog();});byId('screen').addEventListener('change',()=>navigate(byId('screen').value));byId('reveal').addEventListener('click',()=>notify('No administrator password is loaded in this preview.'));window.addEventListener('hashchange',()=>render(true));render();
})();
