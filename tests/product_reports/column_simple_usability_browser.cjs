'use strict';
const fs=require('fs'),assert=require('assert');
const {chromium}=require(process.env.COLUMN_V2_PLAYWRIGHT_MODULE);
const o=JSON.parse(process.argv[2]);
async function ready(p){await p.waitForFunction(()=>workspace&&readyEpoch===epoch&&!busy);await p.evaluate(()=>pending.catch(()=>{}));}
async function solved(p){await p.waitForFunction(()=>result&&result.run_envelope&&!busy);return p.evaluate(()=>result);}
(async()=>{
 fs.mkdirSync(o.output_dir,{recursive:true});
 const b=await chromium.launch({executablePath:process.env.COLUMN_V2_BROWSER_BINARY,headless:true,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--single-process','--no-zygote','--disable-dev-shm-usage']});
 const p=await b.newPage({viewport:{width:1440,height:1050},acceptDownloads:true});const errors=[];p.on('pageerror',e=>errors.push(e.message));const proof=[];
 try{
  await p.goto(o.url);await ready(p);assert.equal(await p.locator('#context').inputValue(),'235-product');
  const actual=await p.evaluate(()=>packet);assert.equal(actual.values.width_mm,800);assert.deepStrictEqual(actual.reviews,{});assert.strictEqual(actual.values.nd_i_kn,null);
  await p.locator('#loadExample').click();let m=await solved(p);let c=Object.fromEntries(m.checks.map(c=>[c.id,c]));
  assert.equal(c.axial.status,'OK');assert.equal(c.longitudinal.status,'OK');assert.equal(c.axial.value,1200);assert(Math.abs(c.longitudinal.value-.10773216688961827)<1e-12);
  assert(Object.values(m.input_packet.reviews).every(r=>r.origin==='SYNTHETIC_TEST'));assert(!m.real_235_design_ready);assert.equal(await p.locator('#section circle').count(),16);
  assert(await p.locator('#solutionSummary').isVisible());assert((await p.locator('#solutionSummary').textContent()).includes('uygun'));
  proof.push({scenario:'one_click_example_solves_without_json_or_manual_reviews',manifest:m});await p.screenshot({path:o.output_dir+'/Internal_Example_UI.png',fullPage:true});
  await p.locator('#product_m2_j_knm').fill('3000');await ready(p);assert(await p.locator('#pdf').isDisabled());await p.locator('#calculate').click();m=await solved(p);assert.equal(m.checks.find(c=>c.id==='longitudinal').status,'FAIL');assert((await p.locator('#solutionSummary').textContent()).includes('yeterli değil'));proof.push({scenario:'edit_recompute_actual_failure',manifest:m});
  await p.locator('#open235').click();await ready(p);assert.deepStrictEqual(await p.evaluate(()=>packet),actual);assert(await p.locator('#pdf').isDisabled());
  await p.locator('#packetFile').setInputFiles(o.synthetic_packet);await p.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Kaynak bağlı paket'));await ready(p);
  assert(await p.locator('#solveImported').isVisible());assert.deepStrictEqual(await p.evaluate(()=>packet.reviews),{});
  await p.locator('#solveImported').click();m=await solved(p);assert.equal(m.checks.find(c=>c.id==='longitudinal').status,'OK');proof.push({scenario:'uploaded_unreviewed_synthetic_json_one_click_solve',manifest:m});
  const wait=p.waitForEvent('download');await p.locator('#json').click();const d=await wait;await d.saveAs(o.output_dir+'/Solved_Example.json');assert.deepStrictEqual(JSON.parse(fs.readFileSync(o.output_dir+'/Solved_Example.json')),m);
  // User-entered declaration is supplied once, then the ordinary existing
  // review endpoints process only complete groups. No invented real reviewer.
  await p.locator('#open235').click();await ready(p);
  await p.locator('#packetFile').setInputFiles(o.synthetic_packet);await p.waitForFunction(()=>document.getElementById('status').textContent.startsWith('Kaynak bağlı paket'));await ready(p);
  await p.locator('#reviewer').fill('EXPLICIT OFFLINE USER-FLOW TEST');await p.locator('#reviewReference').fill('TEST INPUTS ONLY / NOT REAL PROJECT');await p.locator('#reviewOrigin').selectOption('USER_DECLARATION');await p.locator('#batchReview').check();
  await p.locator('#calculate').click();m=await solved(p);assert.equal(m.checks.find(c=>c.id==='longitudinal').status,'OK');assert(Object.values(m.input_packet.reviews).every(r=>r.origin==='USER_DECLARATION'));assert(!m.real_235_design_ready);proof.push({scenario:'single_user_declaration_records_complete_groups_and_computes',manifest:m});
  // A real input is never silently converted into an example or a review.
  await p.locator('#open235').click();await ready(p);await p.locator('#calculate').click();m=await solved(p);assert(m.checks.every(c=>c.status==='BLOCKED'));assert.deepStrictEqual(m.input_packet.reviews,{});proof.push({scenario:'actual_draft_kept_unreviewed_and_forces_empty',manifest:m});
  await p.setViewportSize({width:390,height:844});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepStrictEqual(errors,[]);fs.writeFileSync(o.output_dir+'/Usability_Proof.json',JSON.stringify({status:'PASS',scenarios:proof,page_errors:errors,native_calls:0},null,2));console.log('USABILITY_PASS',proof.length);
 }finally{await b.close();}
})().catch(e=>{console.error(e.stack);process.exit(1)});
