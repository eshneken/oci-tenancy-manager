/** Inert current-cycle financial design. Same-response costs never become live OCI observations. */
(() => {
 'use strict';
 /** Resolve controls only within this standalone financial preview. */
 const $=id=>document.getElementById(id);
 const fixtures=[
  {id:'alex',owner:'Alex Taylor',manager:'Riley Morgan',tenancy:'lab-alex-01',type:'Individual',members:1,baseline:'v1',overrides:[],issues:[],budget:20000,actual:11500,forecast:17000},
  {id:'jordan',owner:'Jordan Avery',manager:'Jamie Parker',tenancy:'lab-jordan-shared',type:'Shared',members:4,baseline:'v1',overrides:['Budget'],issues:['jordan-policy'],budget:50000,actual:43000,forecast:62000},
  {id:'casey',owner:'Casey Rowan',manager:'Taylor Quinn',tenancy:'lab-casey-01',type:'Individual',members:1,baseline:'v1',overrides:['Quota'],issues:['casey-quota','casey-budget'],budget:20000,actual:24000,forecast:32000},
  {id:'sam',owner:'Sam Ellis',manager:'Taylor Quinn',tenancy:'lab-sam-01',type:'Individual',members:1,baseline:'v1',overrides:['Policy'],issues:['sam-policy'],budget:20000,actual:15000,forecast:null}
 ];
 const state={query:'',lob:'all',size:4,page:1,sort:'tenancy',direction:1,scenario:'current',pending:new Set()};
 const lob='Platform Engineering';
 /** Create UI text safely; sample record content is never inserted as HTML. */
 function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
 /** Build one keyboard-native action without defining a second command authorization path. */
 function button(label,handler,cls){const n=el('button',label,cls);n.type='button';n.addEventListener('click',handler);return n;}
 /** Link only existing sample destinations, preserving exact tenancy identity. */
 function link(label,target,cls){const n=el('a',label,cls);n.href=target;return n;}
 /** Format integer-cent fixtures; production amounts use qualified decimal wire contracts. */
 function money(value,currency='USD'){if(value===null)return 'Unavailable';if(!currency)return (value/100).toFixed(2)+' · currency unverified';return new Intl.NumberFormat('en-US',{style:'currency',currency}).format(value/100);}
 /** Format actual UTC instants independently from their sortable persisted representation. */
 function time(instant,compact=false){if(!instant)return 'Unavailable';const date=new Date(instant),day=new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',...(compact?{}:{year:'numeric'}),timeZone:'UTC'}).format(date);return day+' · '+String(date.getUTCHours()).padStart(2,'0')+':'+String(date.getUTCMinutes()).padStart(2,'0')+' UTC';}
 /** Seed read-only observations, with explicit errors and source age rather than fabricated fresh data. */
 function rows(){return fixtures.map(base=>{
  const row={...base,lob,currency:'USD',computed:'2026-10-24T06:00:00Z',retrieved:'2026-10-24T08:00:00Z',period:'October 2026',data:base.forecast===null?'Forecast unavailable':'Current',qualified:true};
  const target=state.scenario==='pending'?'jordan':'sam';
  if(row.id===target){
   if(state.scenario==='stale'){row.computed='2026-10-22T06:00:00Z';row.forecast=19000;row.data='Calculation out of date';row.qualified=false;}
   if(state.scenario==='missing'){row.budget=null;row.actual=null;row.forecast=null;row.computed=null;row.data='Budget missing';row.qualified=false;}
   if(state.scenario==='empty'){row.budget=null;row.actual=null;row.forecast=null;row.computed=null;row.retrieved=null;row.data='Not collected';row.qualified=false;}
   if(state.scenario==='rollover'){row.computed='2026-09-30T06:00:00Z';row.period='September 2026';row.data='Previous cycle only';row.qualified=false;row.prior=true;}
   if(state.scenario==='currency'){row.currency=null;row.forecast=19000;row.data='Currency unverified';row.qualified=false;}
   if(state.scenario==='pending'){row.desired=75000;row.data='Budget change pending';}
  }
  return row;
 });}
 /** Separate a known overrun from independently missing forecasts; never label uncertain data healthy. */
 function spend(row){
  if(!row.qualified||row.budget===null||!row.currency)return {label:'Not evaluated',kind:'neutral',code:'unknown'};
  if(row.actual!==null&&row.actual>row.budget)return {label:'Actual over budget',kind:'danger',code:'actual'};
  if(row.forecast!==null&&row.forecast>row.budget)return {label:'Forecast over budget',kind:'warn',code:'forecast'};
  if(row.actual===null||row.forecast===null)return {label:'Not evaluated',kind:'neutral',code:'unknown'};
  if(row.actual===row.budget||row.forecast===row.budget)return {label:'At budget',kind:'neutral',code:'at'};
  return {label:'Within budget',kind:'',code:'within'};
 }
 /** Evaluate each amount independently so an actual overrun cannot hide a forecast overrun. */
 function amountStatus(row,key){
  const name=key==='actual'?'Actual spend':'Forecast';
  if(!row.qualified||row.prior||row.budget===null||!row.currency||row[key]===null)return {label:name+' not evaluated',kind:'neutral'};
  if(row[key]>row.budget)return {label:name+' over budget',kind:key==='actual'?'danger':'warn'};
  if(row[key]===row.budget)return {label:name+' at budget',kind:'neutral'};
  return {label:name+' within budget',kind:'good'};
 }
 /** Keep compact amount colors understandable to screen readers and on hover without a second visual row. */
 function amount(row,key){
  const status=amountStatus(row,key),node=el('span',undefined,'amount-highlight '+status.kind),visible=el('span',shown(row,key));
  visible.setAttribute('aria-hidden','true');node.title=status.label;node.dataset.amount=key;
  node.append(visible,el('span',shown(row,key)+', '+status.label,'finance-sr-only'));return node;
 }
 /** Derive a distinct data badge so availability cannot disappear behind a spend warning. */
 function dataBadge(row){return el('span',row.data,'badge '+(row.data==='Current'?'':'neutral'));}
 /** Display current-cycle amounts only; a prior-month observation is not a current-month fallback. */
 function shown(row,key){return row.prior?'Unavailable':money(row[key],row.currency);}
 /** Render a title and keep the correct context active in the shared menu. */
 function heading(title,description,action){const wrap=el('div',undefined,'titleline'),text=el('div'),h=el('h1',title);h.id='page-title';h.tabIndex=-1;text.append(h,el('p',description,'sub'));wrap.append(text);if(action)wrap.append(action);return wrap;}
 /** Mark one compact statistic with explicit scope and optional provenance. */
 function stat(value,label,detail){const box=el('div',undefined,'finance-stat');box.append(el('strong',value),el('span',label));if(detail)box.append(el('small',detail));return box;}
 /** Present definitions in semantic label/value pairs. */
 function facts(items){const dl=el('dl',undefined,'finance-facts');for(const [label,value]of items){const row=el('div');row.append(el('dt',label),el('dd',value));dl.append(row);}return dl;}
 /** Announce only local request acceptance; it does not claim that provider data changed. */
 function feedback(text){const box=$('feedback');box.textContent=text;box.hidden=false;box.focus();}
 /** Queue a simulated scoped read; existing pending children are joined, not re-requested. */
 function refresh(ids){
  const fresh=ids.filter(id=>!state.pending.has(id));if(!fresh.length)return;
  fresh.forEach(id=>state.pending.add(id));updatePending();
  feedback('Collection requested for '+fresh.length+' '+(fresh.length===1?'tenancy':'tenancies')+'. Displayed values and OCI calculation times are unchanged in this preview.');
 }
 /** Keep pending controls separate from preserved observed data and original source timestamps. */
 function updatePending(){
  const control=$('refresh');if(!control)return;const id=route().id,ids=id?[id]:fixtures.map(row=>row.id);
  const allPending=ids.every(key=>state.pending.has(key));control.disabled=allPending;control.textContent=allPending?'Collection requested':id?'Refresh costs':'Refresh all costs';
  for(const cell of document.querySelectorAll('[data-pending]')){cell.hidden=!state.pending.has(cell.dataset.pending);}
 }
 /** Read the two local routes without adopting an arbitrary external target. */
 function route(){const [name,query='']=location.hash.slice(1).split('?');return {name:name==='tenancy'?'tenancy':'tenancies',id:name==='tenancy'?new URLSearchParams(query).get('tenancy'):null};}
 /** Render the shared empty feedback surface; its data state remains transient. */
 function message(){const n=el('div',undefined,'callout finance-feedback');n.id='feedback';n.hidden=true;n.tabIndex=-1;n.setAttribute('role','status');return n;}
 /** Build a labeled select with native keyboard behavior. */
 function selectField(label,id,values,current,handler){const wrap=el('div',undefined,'field'),l=el('label',label),s=el('select');l.htmlFor=id;s.id=id;for(const [value,text]of values){const option=el('option',text);option.value=value;option.selected=String(current)===value;s.append(option);}s.addEventListener('change',handler);wrap.append(l,s);return wrap;}
 /** Keep search, sort and paging local to this view without replacing a focused search input. */
 function list(){
  const view=$('view'),refreshButton=button('Refresh all costs',()=>refresh(fixtures.map(row=>row.id)),'primary');refreshButton.id='refresh';
  view.append(heading('Tenancies','Ownership, configuration and current-cycle spending.',refreshButton));
  view.append(message());
  const stats=el('div',undefined,'finance-stats');stats.id='tenancy-stats';view.append(stats,el('p','October 2026 · USD sample billing context · Daily collection plus manual refresh','cost-context'));
  const panel=el('section',undefined,'panel'),toolbar=el('div',undefined,'finance-toolbar'),searchWrap=el('div',undefined,'field search-field'),label=el('label','Search tenancies or owners'),search=el('input');label.htmlFor='search';search.id='search';search.type='search';search.value=state.query;search.placeholder='Name, owner or manager';search.addEventListener('input',()=>{state.query=search.value;state.page=1;updateTable();});searchWrap.append(label,search);toolbar.append(searchWrap,selectField('LOB','lob',[['all','All LOBs'],[lob,lob]],state.lob,()=>{state.lob=$('lob').value;state.page=1;updateTable();}),selectField('Rows per page','page-size',[['2','2'],['4','4']],state.size,()=>{state.size=Number($('page-size').value);state.page=1;updateTable();}));panel.append(toolbar);
  const wrap=el('div',undefined,'tablewrap');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Scrollable tenancy dashboard');const table=el('table',undefined,'cost-table'),thead=el('thead'),header=el('tr');
  for(const [key,title]of [['tenancy','Tenancy'],['owner','Owner / LOB'],['issues','Configuration'],['actual','Actual / budget'],['forecast','Forecast']]){const th=el('th');th.scope='col';const control=sortButton(key,key==='actual'?'Actual':title);if(key==='issues')control.setAttribute('aria-label','Sort by configuration issue count');th.append(control);if(key==='actual')th.append(el('span',' / ','muted'),sortButton('budget','Budget'));header.append(th);}thead.append(header);const body=el('tbody');body.id='cost-rows';table.append(thead,body);wrap.append(table);panel.append(wrap);const pages=el('div',undefined,'pagination');pages.id='pagination';pages.setAttribute('aria-label','Cost table pagination');panel.append(pages);const summary=el('div',undefined,'finance-summary');summary.id='finance-summary';summary.setAttribute('role','status');panel.append(summary);view.append(panel);updateTable();
 }
 /** Keep both monetary sort keys accessible within the consolidated Actual/Budget header. */
 function sortButton(key,label){const control=button(label+' ↕',()=>{state.direction=state.sort===key?-state.direction:1;state.sort=key;state.page=1;updateTable();},'sort');control.dataset.sort=key;control.setAttribute('aria-label','Sort by '+label.toLowerCase());return control;}
 let freshnessTarget=null,freshnessPinned=false,freshnessTimer=null;
 /** Clear temporary tooltip state when its row changes, navigation occurs or Escape/light-dismiss closes it. */
 function hideFreshness(){clearTimeout(freshnessTimer);if($('freshness-tooltip').matches(':popover-open'))$('freshness-tooltip').hidePopover();if(freshnessTarget)freshnessTarget.setAttribute('aria-expanded','false');freshnessTarget=null;freshnessPinned=false;}
 /** Keep hover content inside the viewport, including after scrolling its table on a narrow screen. */
 function positionFreshness(){if(!freshnessTarget?.isConnected){hideFreshness();return;}const pop=$('freshness-tooltip'),anchor=freshnessTarget.getBoundingClientRect(),box=pop.getBoundingClientRect();if(anchor.bottom<0||anchor.top>innerHeight||anchor.right<0||anchor.left>innerWidth){hideFreshness();return;}pop.style.left=Math.max(12,Math.min(anchor.left,innerWidth-box.width-12))+'px';pop.style.top=Math.max(12,Math.min(innerHeight-box.height-12,anchor.bottom+8+box.height<=innerHeight?anchor.bottom+8:anchor.top-box.height-8))+'px';}
 /** Show retrieval time concisely while provider calculation age remains an internal qualification input. */
 function showFreshness(row,control,pin=false){clearTimeout(freshnessTimer);if(freshnessTarget!==control)hideFreshness();freshnessTarget=control;freshnessPinned=pin||freshnessPinned;const pop=$('freshness-tooltip');pop.replaceChildren(el('strong','Cost data · '+row.tenancy),facts([['Status',row.data],['OTM retrieved',row.retrieved?time(row.retrieved):'Not collected'],['Observed cycle',row.period]]));control.setAttribute('aria-expanded','true');if(!pop.matches(':popover-open'))pop.showPopover();positionFreshness();}
 /** Allow pointer transfer into the tooltip and keyboard focus without premature dismissal. */
 function deferFreshnessHide(){clearTimeout(freshnessTimer);freshnessTimer=setTimeout(()=>{if(!freshnessPinned&&!freshnessTarget?.matches(':focus')&&!$('freshness-tooltip').matches(':hover'))hideFreshness();},180);}
 /** Expose retrieval freshness on hover, keyboard focus and a pinned touch/click action. */
 function freshnessButton(row){const control=button('ⓘ',()=>{if(freshnessPinned&&freshnessTarget===control)hideFreshness();else showFreshness(row,control,true);},'freshness-button');control.setAttribute('aria-label','Cost data and freshness for '+row.tenancy);control.setAttribute('aria-describedby','freshness-tooltip');control.setAttribute('aria-controls','freshness-tooltip');control.setAttribute('aria-expanded','false');control.addEventListener('pointerenter',()=>showFreshness(row,control));control.addEventListener('pointerleave',deferFreshnessHide);control.addEventListener('focus',()=>showFreshness(row,control));control.addEventListener('blur',deferFreshnessHide);return control;}
 /** Apply the selected record filters across all pages. */
 function matches(){const q=state.query.toLowerCase().trim();return rows().filter(row=>(state.lob==='all'||row.lob===state.lob)&&[row.tenancy,row.owner,row.manager,row.lob].join(' ').toLowerCase().includes(q));}
 /** Sort unavailable numeric values last in either direction, never as zero spending. */
 function compare(a,b){
  const key=state.sort;let av=key==='spend'?spend(a).label:key==='issues'?a.issues.length:a[key],bv=key==='spend'?spend(b).label:key==='issues'?b.issues.length:b[key];if(key==='computed'){av=a.computed?Date.parse(a.computed):null;bv=b.computed?Date.parse(b.computed):null;}
  if(['budget','actual','forecast'].includes(key)){if(a.prior)av=null;if(b.prior)bv=null;}
  if(av===null||bv===null)return av===bv?0:av===null?1:-1;
  return (typeof av==='number'?av-bv:String(av).localeCompare(String(bv)))*state.direction;
 }
 /** Populate rows and coverage summaries from one coherent fixture per child. */
 function updateTable(focusPage=false){
  if(!$('cost-rows'))return;hideFreshness();const filtered=matches(),data=[...filtered].sort(compare),totalPages=Math.max(1,Math.ceil(data.length/state.size));state.page=Math.min(state.page,totalPages);
  $('tenancy-stats').replaceChildren(stat(String(filtered.length),'Total tenancies'),stat(String(filtered.filter(row=>row.type==='Individual').length),'Individual'),stat(String(filtered.filter(row=>row.type==='Shared').length),'Shared'));
  const body=$('cost-rows');body.replaceChildren();
  for(const row of data.slice((state.page-1)*state.size,state.page*state.size)){
   const tr=el('tr'),status=spend(row),name=el('td'),owner=el('td');tr.dataset.spend=status.code;tr.dataset.tenancy=row.id;
   const identity=el('div',undefined,'tenancy-identity');identity.append(link(row.tenancy,'#tenancy?tenancy='+row.id),freshnessButton(row));name.append(identity,el('small',row.type+' · '+row.members+' '+(row.members===1?'person':'people')));
   // Freshness details move to a tooltip; degraded data remains visible without opening it.
   if(row.data!=='Current')name.append(el('small',row.data,'visible-data-status'));
   const pending=el('small','Collection requested');pending.dataset.pending=row.id;pending.hidden=!state.pending.has(row.id);name.append(pending);
   owner.append(el('span',row.owner),el('small',row.lob));const config=el('td',undefined,'configuration-cell');const configMain=el('div',undefined,'configuration-main'),baselineLink=link('Baseline '+row.baseline,'configuration-walkthrough.html#tenancy?tenancy='+row.id),overrideLink=link(row.overrides.length?'Override':'Create override','configuration-walkthrough.html#overlay?tenancy='+row.id+'&return=tenancies','secondary-link');overrideLink.setAttribute('aria-label',(row.overrides.length?'Edit '+row.overrides.join(', ').toLowerCase()+' override':'Create override')+' for '+row.tenancy);configMain.append(baselineLink,overrideLink);config.append(configMain);
   if(row.issues.length){const target=row.issues.length===1?'issue?issue='+row.issues[0]:'tenancy-issues?tenancy='+row.id;const issue=link('⚠ '+row.issues.length+' '+(row.issues.length===1?'issue':'issues'),'configuration-walkthrough.html#'+target,'configuration-issue');issue.setAttribute('aria-label',row.issues.length+' configuration '+(row.issues.length===1?'issue':'issues')+' for '+row.tenancy);config.append(issue);}
   const actual=el('td',undefined,'money'),pair=el('div',undefined,'amount-pair');pair.append(amount(row,'actual'),el('span',' / '+shown(row,'budget'),'budget-value'));actual.append(pair);
   if(row.desired)actual.append(el('small','Budget '+money(row.desired,row.currency)+' pending'));
   const forecast=el('td',undefined,'money');forecast.append(amount(row,'forecast'));
   tr.append(name,owner,config,actual,forecast);body.append(tr);
  }
  if(!data.length){const tr=el('tr'),td=el('td','No tenancies match your search.','finance-empty');td.colSpan=5;tr.append(td);body.append(tr);}
  const range=el('span',data.length?((state.page-1)*state.size+1)+'–'+Math.min(state.page*state.size,data.length)+' of '+data.length+' tenancies':'0 matching tenancies'),pages=el('div',undefined,'pages');range.setAttribute('role','status');
  for(let n=1;n<=totalPages;n++){const control=button(String(n),()=>{state.page=n;updateTable(true);});control.setAttribute('aria-label','Page '+n);if(n===state.page)control.setAttribute('aria-current','page');pages.append(control);} $('pagination').replaceChildren(range,pages);
  for(const th of document.querySelectorAll('.cost-table th'))th.setAttribute('aria-sort',th.querySelector('[data-sort="'+state.sort+'"]')?(state.direction===1?'ascending':'descending'):'none');
  const summary=$('finance-summary');summary.replaceChildren(el('strong','Filtered totals · '+filtered.length+' tenancies'));
  for(const [key,title]of (filtered.length?[['budget','Budget'],['actual','Actual'],['forecast','Projected total']]:[])){const valid=filtered.filter(row=>row.qualified&&!row.prior&&row.currency==='USD'&&row[key]!==null),span=el('span');span.textContent=' · '+title+': '+(valid.length===filtered.length&&valid.length?money(valid.reduce((sum,row)=>sum+row[key],0)):'Unavailable ('+valid.length+' of '+filtered.length+' comparable)');summary.append(span);}
  summary.append(el('p','Totals cover all filtered pages. Missing data is not zero. Forecast is already the complete cycle-end estimate.','small'));updatePending();if(focusPage)$('pagination').querySelector('[aria-current=page]')?.focus();
 }
 /** Render normal tenancy detail and its independent provider/capture facts, without historical selectors. */
 function detail(id){
  const row=rows().find(item=>item.id===id),view=$('view');if(!row){view.append(heading('Tenancy not found','Choose a tenancy from the cost view.'),link('Back to tenancies','#tenancies','button'));return;}
  const refreshButton=button('Refresh costs',()=>refresh([row.id]),'primary');refreshButton.id='refresh';view.append(link('← Back to tenancies','#tenancies','costs-back'),heading(row.tenancy,'Costs · '+row.owner,refreshButton),message(),el('p','Current cycle · October 2026 · '+(row.currency||'Currency unverified'),'cost-context'));
  const badges=el('div',undefined,'finance-status-row'),status=spend(row);badges.append(el('span',status.label,'badge '+status.kind),dataBadge(row));const pending=el('span','Collection requested','badge neutral');pending.dataset.pending=row.id;badges.append(pending);view.append(badges);
  const cards=el('div',undefined,'finance-stats');cards.append(stat(shown(row,'budget'),'Observed monthly budget',row.desired?'Desired '+money(row.desired,row.currency)+' · change pending':'OTM-managed root budget'),stat(shown(row,'actual'),'Actual spend','Current cycle · provider calculated'),stat(shown(row,'forecast'),'Projected total','Full cycle-end estimate · includes actual spend'));cards.children[1].querySelector('strong').replaceChildren(amount(row,'actual'));cards.children[2].querySelector('strong').replaceChildren(amount(row,'forecast'));view.append(cards);
  if(row.prior)view.append(el('p','Only a previous-cycle observation is available. Current-cycle figures remain unavailable.','callout warn'));
  const panel=el('section',undefined,'panel');panel.append(el('h2','Cost details'),facts([['Owner',row.owner],['Direct manager',row.manager],['LOB',row.lob],['Tenancy type',row.type],['OCI spend calculated',time(row.computed)],['OTM last retrieved',row.retrieved?time(row.retrieved):'Not collected'],['Collection schedule','Daily; manual refresh available'],['Currency',row.currency?row.currency+' · verified sample billing profile':'Not verified']]));const actions=el('div',undefined,'actions');actions.append(link('Budget configuration','configuration-walkthrough.html#tenancy?tenancy='+row.id,'button'));panel.append(actions);view.append(panel);
  const source=el('details',undefined,'panel source-details');source.append(el('summary','Source details'),facts([['Source','Child-managed Budget · get_budget'],['Budget OCID (sample)','ocid1.budget.oc1..example.'+row.id],['Read scope','This child tenancy’s root compartment'],['Observed spend cycle',row.period],['Budget binding','budget/main · generation 1']]));view.append(source,el('p','Refresh reads the budget again; it does not force OCI to recalculate spending. Budget changes are made through the existing configuration override flow.','scope-hint'));updatePending();
 }
 /** Route locally and preserve the table's selection state when opening and returning from a tenancy. */
 function render(focus=false){hideFreshness();$('view').replaceChildren();const current=route();if(current.name==='tenancies'&&location.hash!=='#tenancies')history.replaceState(null,'',location.pathname+location.search+'#tenancies');if(current.name==='tenancy')detail(current.id);else list();window.DesignNavigation.render('design-navigation','tenancies');if(focus)$('page-title')?.focus({preventScroll:true});}
 $('freshness-tooltip').addEventListener('pointerenter',()=>clearTimeout(freshnessTimer));$('freshness-tooltip').addEventListener('pointerleave',deferFreshnessHide);$('freshness-tooltip').addEventListener('toggle',event=>{if(event.newState==='closed'&&!$('freshness-tooltip').matches(':popover-open')){if(freshnessTarget)freshnessTarget.setAttribute('aria-expanded','false');freshnessTarget=null;freshnessPinned=false;}});window.addEventListener('resize',()=>{if(freshnessTarget)positionFreshness();});window.addEventListener('scroll',()=>{if(freshnessTarget)positionFreshness();},true);
 $('scenario').addEventListener('change',()=>{state.scenario=$('scenario').value;state.page=1;render();});window.addEventListener('hashchange',()=>render(true));render();
})();
