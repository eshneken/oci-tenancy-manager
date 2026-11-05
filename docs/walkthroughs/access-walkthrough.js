/** Inert access-health examples: current evidence and repair scope, never cloud state. */
(() => {
 'use strict';
 /** Resolve stable controls within the standalone sample page. */
 const byId=id=>document.getElementById(id);
 let repairAccepted=false;
 const examples=Object.freeze({
  missing:{count:'1 of 2 match',message:'The recovery user is missing. Automation access is available to repair it.',automation:['Present','Verified signer','Qualified repair evidence','Console disabled by intent'],recovery:['Missing','Not applicable','Cannot verify without user','MFA exemption not verified'],status:'Confirmed missing user',detail:'Only the required recovery identity is confirmed absent. This condition remains open until verified repair.',expected:'Bound recovery identity exists in the verified identity domain.\nRequired recovery grants match accepted intent.',observed:'Authorized lookup confirmed absence of the bound recovery user.\nNo assertion about unrelated users or MFA factors.',coverage:'Authorized recovery-user absence; separate fresh qualified recovery-repair evidence receipt: repair-evidence-7 (illustrative).',ref:'automation-check-41 · repair profile; recovery-check-42 · confirmed absence',checks:{automation:'automation-check-41',recovery:'recovery-check-42'},assignment:'Automation profile · revision 4; recovery profile · revision 3',repair:true},
  unverified:{count:'0 of 2 verified',message:'Automation authentication failed. Current user presence and privileges cannot be verified. No automated repair is offered.',automation:['Unable to verify','Authentication failed','Unable to verify','Console disabled by intent'],recovery:['Unable to verify','Not applicable','Unable to verify','MFA exemption not verified'],status:'Unable to verify',detail:'A failed request does not prove that either user was removed. Preserve prior facts with their timestamps and investigate access.',expected:'Authenticate the bound automation signer.\nRead required identities and verify current grants.',observed:'Provider rejected authentication for the configured signer.\nCurrent identity inventory was not obtained.',coverage:'Incomplete · no authorized identity inventory; prior confirmation cannot be cleared.',ref:'automation-check-43 · unable; recovery-check-44 · unable; same rejected provider-attempt-8',checks:{automation:'automation-check-43',recovery:'recovery-check-44'},assignment:'Automation profile · revision 4; recovery profile · revision 3',repair:false},
  matching:{count:'2 of 2 match',message:'Required users and grants match. The recovery-only MFA exemption still needs verification.',automation:['Present','Verified signer','Required grants match','Console disabled by intent'],recovery:['Present','Not applicable','Required grants match','MFA exemption not verified'],status:'Identity checks match',detail:'Matching identity/grant facts do not establish operation-specific authorization or a working console recovery path. No repairable identity drift is observed.',expected:'Both bound users exist.\nAutomation signer and required grants match accepted intent.',observed:'Authorized user/grant reads match.\nAutomation signer probe succeeded. No emergency console login was tested.',coverage:'Complete for observed identity/grant facts; excludes operation-specific authorization, console sign-in and MFA possession.',ref:'automation-check-45 · signer/grant facts; recovery-check-46 · user/grant facts',checks:{automation:'automation-check-45',recovery:'recovery-check-46'},assignment:'Automation profile · revision 4; recovery profile · revision 3',repair:false}
 });
 /** Render provider-derived values as text while retaining explicit status labels. */
 function renderRow(type,name,values,sourceCheck,time){
  const row=document.createElement('tr'),label=document.createElement('td'),strong=document.createElement('strong'),identity=document.createElement('span');
  strong.textContent=type;identity.textContent=name;identity.className='small muted';const evidence=document.createElement('span');evidence.className='small muted';evidence.textContent=sourceCheck+' · 21 Oct 2026, '+time+' UTC';label.append(strong,identity,evidence);row.append(label);
  for(const value of values){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}return row;
 }
 /** Change only the local sample scenario; historical checks and provider state are untouched. */
 function render(focus=false){
  const key=Object.hasOwn(examples,location.hash.slice(1))?location.hash.slice(1):'missing',data=examples[key];
  // A prior scenario's repair scope must not remain open after its evidence changes.
  if(byId('repair-dialog').open)byId('repair-dialog').close();
  byId('screen').value=key;byId('matching-count').textContent=data.count;byId('condition-message').textContent=data.message;
  byId('condition-message').className='callout'+(key==='matching'?'':' warn');
  byId('access-rows').replaceChildren(renderRow('Automation user','otm-automation',data.automation,data.checks.automation,'13:58'),renderRow('Emergency recovery user','otm-recovery',data.recovery,data.checks.recovery,'14:00'));
  for(const [id,value] of [['issue-status',data.status],['issue-description',data.detail],['expected-value',data.expected],['observed-value',data.observed],['check-coverage',data.coverage],['check-reference',data.ref],['assignment-reference',data.assignment]])byId(id).textContent=value;
  byId('issue-status').className='badge '+(key==='matching'?'neutral':'warn');
  byId('observed-time').textContent='21 Oct 2026 · automation 13:58 UTC; recovery 14:00 UTC';byId('check-stamp').textContent='Last checked 21 Oct 2026, 14:00 UTC · Checked daily';
  repairAccepted=false;byId('repair').disabled=false;byId('repair').textContent='Repair';byId('repair').hidden=!data.repair;byId('repair-guidance').textContent=data.repair?'The issue stays open until repair is verified.':key==='unverified'?'Automated actions are unavailable. Use independent recovery or an authorized manual process to restore access.':'No user or grant repair is needed. Verify the recovery sign-in policy and credential separately.';
  byId('action-feedback').textContent='';window.DesignNavigation.render('design-navigation','tenancies');
  if(focus)byId('page-title').focus({preventScroll:true});
 }
 /** Present the exact hypothetical repair scope with no command acceptance or job submission. */
 function previewRepair(){
  const key=Object.hasOwn(examples,location.hash.slice(1))?location.hash.slice(1):'missing';
  // Guard the action itself: hidden controls and stale UI are not authorization evidence.
  if(!examples[key].repair||repairAccepted){const feedback=byId('action-feedback');feedback.textContent='Repair is unavailable for this condition. Restore automation access first.';feedback.focus();return;}
  const dialog=byId('repair-dialog');if(!dialog.open)dialog.showModal();byId('cancel-repair').focus();
 }
 /** Keep keyboard navigation inside the repair preview instead of allowing the browser-chrome boundary between its last and first controls. */
 function trapRepairFocus(event){
  if(event.key!=='Tab')return;
  const controls=[...byId('repair-dialog').querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled])')].filter(control=>control.getClientRects().length);
  const first=controls[0],last=controls[controls.length-1];
  if(!first)return;
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
 }
 byId('repair-dialog').addEventListener('keydown',trapRepairFocus);
 byId('screen').addEventListener('change',()=>{location.hash=byId('screen').value;});
 window.addEventListener('hashchange',()=>render(true));
 byId('repair').addEventListener('click',previewRepair);
 byId('close-repair').addEventListener('click',()=>byId('repair-dialog').close());
 byId('cancel-repair').addEventListener('click',()=>byId('repair-dialog').close());
 // Recheck the sample condition on confirmation; a stale hidden button cannot authorize repair.
 byId('confirm-repair').addEventListener('click',()=>{if(routeConditionCanRepair()&&!repairAccepted){repairAccepted=true;byId('repair').disabled=true;byId('repair').textContent='Repair requested';byId('repair-dialog').close();const feedback=byId('action-feedback');feedback.textContent='Repair requested. Waiting for verification.';feedback.focus();}});
 /** Enforce the current condition again when accepting the local repair preview. */
 function routeConditionCanRepair(){const key=Object.hasOwn(examples,location.hash.slice(1))?location.hash.slice(1):'missing';return examples[key].repair;}
 byId('recheck').addEventListener('click',()=>{const feedback=byId('action-feedback');feedback.textContent='Check requested. Results are unchanged in this preview.';feedback.focus();});
 render();
})();
