'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto');
const {chromium}=require(process.env.COLUMN_V2_PLAYWRIGHT_MODULE);
const options=JSON.parse(process.argv[2]);
const out=options.output_dir;
const proof={transport:'NORMAL python tools/start_column_product.py; Chromium; HTTP; no injected qualified channel',scenarios:[],downloads:[],page_errors:[]};
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
async function settle(p){await p.evaluate(()=>pending.catch(()=>{}));await p.waitForFunction(()=>!busy);}
async function manifest(p){return p.evaluate(()=>JSON.parse(document.getElementById('technical').textContent||'null'));}
async function clean(p){assert.equal(await p.locator('#error').textContent(),'');}
async function calculate(p){await p.locator('#calculate').click();await settle(p);await clean(p);return manifest(p);}
async function upload(p,packet){await p.locator('#packetFile').setInputFiles({name:'EXPLICIT_OFFLINE_TEST_INPUTS.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(packet))});await p.waitForFunction(()=>readyEpoch===epoch&&document.getElementById('status').textContent.startsWith('Kaynak bağlı paket içeri alındı'));await settle(p);await clean(p);}
async function review(p,group,origin='SYNTHETIC_TEST'){
 await p.locator('[data-review="'+group+'"]').evaluate(el=>{for(let n=el.parentElement;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true});await p.locator('#reviewer').fill('OFFLINE TEST HARNESS / NO PROJECT SIGNATURE');
 await p.locator('#reviewReference').fill('EXPLICIT TEST ONLY / NOT ACTUAL PROJECT ACCEPTANCE');
 await p.locator('#reviewOrigin').selectOption(origin);await p.locator('[data-review="'+group+'"]').click();await settle(p);await clean(p);
}
async function edit(p,key,value){await p.locator('#product_'+key).evaluate(el=>{for(let n=el.parentElement;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true});await p.locator('#product_'+key).fill(String(value));await settle(p);await clean(p);assert(await p.locator('#pdf').isDisabled());}
async function exports(p,name,m){
 for(const ext of ['json','html','pdf']){
  const wait=p.waitForEvent('download');await p.locator('#'+ext).click();const d=await wait;const file=path.join(out,name+'.'+ext);await d.saveAs(file);const bytes=fs.readFileSync(file);
  proof.downloads.push({name,format:ext,bytes:bytes.length,sha256:hash(bytes),run_envelope:m.run_envelope});
  if(ext==='json')assert.deepStrictEqual(JSON.parse(bytes),m);
  if(ext==='html')assert(bytes.toString().includes(m.run_envelope.workspace_id)&&bytes.toString().includes(m.run_envelope.build_sha256));
  if(ext==='pdf')assert(bytes.subarray(0,4).equals(Buffer.from('%PDF')));
 }
}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({executablePath:process.env.COLUMN_V2_BROWSER_BINARY,headless:true,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--single-process','--no-zygote','--disable-dev-shm-usage']});
 try{
  const p=await browser.newPage({viewport:{width:1520,height:1100},acceptDownloads:true});p.on('pageerror',e=>proof.page_errors.push(e.message));
  await p.goto(options.url);await p.waitForFunction(()=>workspace&&readyEpoch===epoch);await p.locator('.mode-picker').evaluate(e=>e.open=true);await p.waitForFunction(()=>workspace&&readyEpoch===epoch);
  const workspace=await p.evaluate(()=>workspace);assert.equal(workspace.qualified_catalog.length,0);proof.build_manifest=workspace.build_manifest;
  await p.selectOption('#context','235-product');await settle(p);
  const known=(await manifest(p)).input_packet;assert.equal(known.values.width_mm,800);assert.equal(known.values.free_length_mm,4450);assert.equal(known.values.steel_name,'S500');assert.equal(known.values.concrete_name,'C35/45');assert.equal(known.values.k_m2,null);assert.equal(known.values.sway_classification,null);assert.equal(known.values.nd_i_kn,null);assert.deepStrictEqual(known.reviews,{});
  assert.equal(await p.locator('#product_width_mm').inputValue(),'80');assert.equal(await p.locator('#product_free_length_mm').inputValue(),'445');
  let m=await calculate(p);assert(m.checks.every(c=>c.status==='BLOCKED'));proof.scenarios.push({name:'actual_known_user_draft_no_review_or_forces',manifest:m});await exports(p,'Actual_235_Unreviewed_Draft',m);
  const full=JSON.parse(fs.readFileSync(options.synthetic_packet,'utf8'));
  let small=structuredClone(full);for(const f of workspace.product_fields)if(['transverse','transverse_cage','transverse_steel','shear_actions'].includes(f[3]))small.values[f[0]]=null;
  await upload(p,small);for(const g of ['geometry','concrete','longitudinal_steel','actions','cage'])await review(p,g);
  m=await calculate(p);let c=Object.fromEntries(m.checks.map(x=>[x.id,x]));assert.equal(c.axial.status,'OK');assert.equal(c.longitudinal.status,'OK');assert(Math.abs(c.longitudinal.value-.10773216688961827)<1e-12);assert.equal(c.longitudinal.governing_case,'TEST_CONCURRENT_COMBO');assert.equal(c.longitudinal.governing_end,'J');assert.equal(c.longitudinal.station_m,4.45);
  assert.equal(await p.locator('#section circle').count(),16);assert.equal(c.cage.display_unit,'cm²');assert(!m.real_235_design_ready);assert.strictEqual(m.current_analysis_result_epoch,null);
  proof.scenarios.push({name:'declared_axial_and_actual_coordinate_pmm',manifest:m});await exports(p,'Synthetic_Declared_Valid',m);
  const before=m;await edit(p,'m2_j_knm',3000);await review(p,'actions');m=await calculate(p);c=Object.fromEntries(m.checks.map(x=>[x.id,x]));assert.equal(c.longitudinal.status,'FAIL');assert(c.longitudinal.value>1);assert.notEqual(before.result_id,m.result_id);
  const badge=p.locator('[data-check="longitudinal"] .check-head .badge');assert.equal(await badge.evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 235, 231)');proof.scenarios.push({name:'declared_pmm_failure_not_green',manifest:m});await exports(p,'Synthetic_Declared_PMM_Fail',m);
  const stale=await p.request.post(options.url+'/api/report',{data:{workspace_id:m.run_envelope.workspace_id,revision:before.run_envelope.calculation_revision,result_id:before.result_id,format:'json'}});assert.equal(stale.status(),422);proof.scenarios.push({name:'stale_revision_export_rejected',http_status:stale.status()});
  await edit(p,'nd_j_kn',15000);await review(p,'actions');m=await calculate(p);assert.equal(m.checks.find(x=>x.id==='axial').status,'FAIL');proof.scenarios.push({name:'declared_axial_failure',manifest:m});
  await upload(p,full);for(const g of ['geometry','concrete','longitudinal_steel','actions','cage','transverse_steel','transverse_cage','transverse'])await review(p,g);
  m=await calculate(p);let transverse=m.checks.find(x=>x.id==='confinement');assert.equal(transverse.status,'PARTIAL');assert(transverse.subchecks.some(x=>x.status==='OK'));assert(transverse.subchecks.some(x=>x.status==='BLOCKED'));assert(await p.locator('[data-check="confinement"] table').count());proof.scenarios.push({name:'pure_transverse_actual_subchecks_without_canonical_rebar',manifest:m});await exports(p,'Synthetic_Transverse_Partial',m);
  await edit(p,'confinement_spacing_mm',30);await review(p,'transverse_cage');m=await calculate(p);assert.equal(m.checks.find(x=>x.id==='confinement').status,'FAIL');proof.scenarios.push({name:'pure_transverse_failure',manifest:m});
  // Three origins are exercised on separate explicit test packets.
  for(const origin of ['USER_DECLARATION','PROJECT_DOCUMENT','SYNTHETIC_TEST']){
   const q=structuredClone(full);q.reviews={};await upload(p,q);await review(p,'geometry',origin);m=await calculate(p);const e=m.checks.find(x=>x.id==='emin_M2');assert.deepStrictEqual(e.origins,[origin]);assert.equal(e.value,39);assert(!m.real_235_design_ready);proof.scenarios.push({name:'origin_'+origin,manifest:m});
  }
  let q=structuredClone(full);q.reviews={};Object.assign(q.values,{free_length_mm:4450,k_m2:1,k_m3:1,sway_classification:'SWAY_PREVENTED'});await upload(p,q);await review(p,'geometry');
  for(const [cm,status] of [[445,'SLENDERNESS_EFFECTS_NEGLIGIBLE'],[600,'SIGNED_END_MOMENT_RATIO_REQUIRED_FOR_SLENDERNESS_DECISION'],[1200,'MOMENT_MAGNIFICATION_REQUIRED']]){
   await edit(p,'free_length_mm',cm);await review(p,'slenderness');m=await calculate(p);const s=m.checks.find(x=>x.id==='slenderness_M2');assert.equal(s.status,status);assert(Math.abs(s.value-cm*10/240)<1e-12);assert((await p.locator('[data-check="slenderness_M2"]').textContent()).includes(s.display_status));proof.scenarios.push({name:'slenderness_'+cm+'cm',manifest:m});if(cm===1200)await exports(p,'Synthetic_Magnification_Required',m);
  }
  const saved=m.input_packet;await p.selectOption('#context','reference');await settle(p);assert(await p.locator('#pdf').isDisabled());await p.selectOption('#context','235-product');await settle(p);const restored=(await manifest(p)).input_packet;assert.deepStrictEqual(restored,saved);assert.equal(await p.locator('#product_free_length_mm').inputValue(),'1200');assert(await p.locator('#pdf').isDisabled());m=await calculate(p);assert.equal(m.result_id,proof.scenarios.at(-1).manifest.result_id);proof.scenarios.push({name:'draft_restoration_no_result_leak_cm_roundtrip',manifest:m});
  const packetWait=p.waitForEvent('download');await p.locator('#packetDownload').click();const d=await packetWait;const bytes=fs.readFileSync(await d.path());assert.deepStrictEqual(JSON.parse(bytes),saved);proof.scenarios.push({name:'canonical_packet_export_roundtrip',sha256:hash(bytes),native_coordinates_unchanged:JSON.stringify(saved.accepted_native_coordinates)===JSON.stringify(known.accepted_native_coordinates)});
  // Hold a completed calculation response while switching context.
  let entered,release;const gate=new Promise(r=>release=r),seen=new Promise(r=>entered=r);
  await p.route('**/api/calculate',async route=>{const response=await route.fetch();entered();await gate;await route.fulfill({response});});
  await p.locator('#calculate').click();await seen;await p.selectOption('#context','reference');release();await settle(p);assert(!(await manifest(p))?.result_id);assert(await p.locator('#pdf').isDisabled());proof.scenarios.push({name:'late_result_after_switch_rejected'});await p.unroute('**/api/calculate');
  await p.selectOption('#context','235-product');await settle(p);await edit(p,'width_mm',81.25);const typed=(await manifest(p)).input_packet;assert.equal(typed.values.width_mm,812.5);assert(!typed.reviews.geometry);assert.deepStrictEqual(typed.accepted_native_coordinates,known.accepted_native_coordinates);proof.scenarios.push({name:'812_5mm_to_81_25cm_canonical_edit',packet:typed});
  await p.screenshot({path:path.join(out,'Internal_UI_QA.png'),fullPage:false});assert.deepStrictEqual(proof.page_errors,[]);proof.status='PASS';proof.browser=browser.version();
 }finally{await browser.close();fs.writeFileSync(path.join(out,'Public_A01_A07_Browser_Evidence.json'),JSON.stringify(proof,null,2));}
})().catch(e=>{console.error(e.stack);process.exit(1)});
