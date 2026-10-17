'use strict';
const fs=require('fs'),assert=require('assert'),crypto=require('crypto');
const o=JSON.parse(process.argv[2]),{chromium}=require(process.env.COLUMN_V2_PLAYWRIGHT_MODULE);
const events=[],downloads=[],errors=[];
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
async function settle(p){await p.evaluate(()=>pending.catch(()=>{}));await p.waitForFunction(()=>!busy);}
async function manifest(p){return p.evaluate(()=>JSON.parse(document.getElementById('technical').textContent||'null'));}
async function calculate(p){await p.locator('#calculate').click();await settle(p);assert.equal(await p.locator('#error').textContent(),'');return await manifest(p);}
async function exports(p,name,m){for(const ext of ['json','pdf','html']){const wait=p.waitForEvent('download');await p.locator('#'+ext).click();const d=await wait;const path=o.output_dir+'/'+name+'.'+ext;await d.saveAs(path);const b=fs.readFileSync(path);downloads.push({path,sha256:hash(b),result_id:m.result_id});if(ext==='json')assert.deepStrictEqual(JSON.parse(b),m);if(ext==='html')assert(b.toString().includes(m.result_id));}}
(async()=>{const b=await chromium.launch({executablePath:process.env.COLUMN_V2_BROWSER_BINARY,headless:true,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--single-process','--no-zygote','--disable-dev-shm-usage']});try{
const p=await b.newPage({viewport:{width:1520,height:1100},acceptDownloads:true});p.on('pageerror',e=>errors.push(e.message));
await p.goto(o.url);await p.waitForFunction(()=>workspace!==null&&readyEpoch===epoch);
assert.equal(await p.evaluate(()=>workspace.qualified_catalog.length),0); // normal empty channel, not fixture publication
await p.locator('#context').selectOption('reference-owners');await settle(p);
assert.equal(await p.locator('#field_shear_spacing_mm').inputValue(),'100');
const first=await calculate(p);assert.equal(first.source_authority,'NUMERICAL_REFERENCE_ONLY');assert(first.selected_candidate);assert.equal(first.typed_transverse_output.shear_vr_by_direction_kn[0][1],428.5);assert.strictEqual(first.B5,null);assert.strictEqual(first.B6,null);
events.push({phase:'initial',workspace_id:await p.evaluate(()=>workspace.id),context:await p.locator('#context').inputValue(),manifest:first});await exports(p,'Editable_Reference_Baseline',first);
await p.locator('#field_shear_spacing_mm').fill('200');await settle(p);
assert(await p.locator('#pdf').isDisabled());assert(await p.locator('#result').textContent().then(x=>x.includes('geçersizleşti')));assert(!(await manifest(p))?.result_id);
events.push({phase:'edit_invalidated',field:'shear_spacing_mm',value:200,context:await p.locator('#context').inputValue(),workspace_id:await p.evaluate(()=>workspace.id)});
const changed=await calculate(p);assert.equal(await p.locator('#context').inputValue(),'reference-owners');assert.equal(changed.typed_transverse_output.shear_vr_by_direction_kn[0][1],264.25);assert.notEqual(changed.input_sha256,first.input_sha256);assert.notEqual(changed.result_id,first.result_id);assert.equal(changed.input_bundle.values.shear_spacing_mm,200);assert(changed.transverse_blockers.includes('SPECIAL_TIE_DETAILING_FACTS_NOT_AVAILABLE'));
events.push({phase:'recomputed',manifest:changed,workspace_id:await p.evaluate(()=>workspace.id)});await exports(p,'Editable_Reference_Changed',changed);await p.evaluate(()=>window.scrollTo(0,0));await p.screenshot({path:o.output_dir+'/Reference_Screen.png',fullPage:false});
await p.locator('#field_reference_ve_dir2_kn').fill('300');await settle(p);const fail=await calculate(p);assert.equal(fail.checks.find(c=>c.id==='COL_FINAL_SHEAR_VR_DIR2').status,'FAIL');events.push({phase:'calculated_fail',manifest:fail});
await p.locator('#field_shear_spacing_mm').fill('');await settle(p);assert(await p.locator('#pdf').isDisabled());assert(await p.locator('#calculate').isDisabled());assert((await p.locator('#error').textContent()).includes('sayı'));events.push({phase:'invalid_rejected',pdf_disabled:true,calculate_disabled:true});
await p.locator('#context').selectOption('235-product');await settle(p);assert(await p.locator('#pdf').isDisabled());assert.equal(await p.locator('#product_width_mm').inputValue(),'80');const actual=await calculate(p);assert(actual.checks.every(c=>c.status==='BLOCKED'));assert(!actual.real_235_design_ready);assert.equal(actual.canonical_rebar_authority,'NOT_PROVIDED');events.push({phase:'actual_235',manifest:actual});
assert.deepStrictEqual(errors,[]);fs.writeFileSync(o.output_dir+'/Browser_Interaction.json',JSON.stringify({events,downloads,page_errors:errors,native_calls:0,published_variants:0},null,2));
}finally{await b.close()}})().catch(e=>{console.error(e.stack);process.exit(1)});
