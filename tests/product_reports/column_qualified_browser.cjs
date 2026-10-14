'use strict';
const fs=require('fs'),assert=require('assert'),crypto=require('crypto');
const o=JSON.parse(process.argv[2]),{chromium}=require(process.env.COLUMN_V2_PLAYWRIGHT_MODULE);
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const events=[],errors=[],downloads=[];
async function settle(p){await p.evaluate(()=>pending.catch(()=>{}));await p.waitForFunction(()=>!busy);}
async function snapshot(p){return p.evaluate(()=>({context:document.getElementById('context').value,status:document.getElementById('status').textContent,manifest:JSON.parse(document.getElementById('technical').textContent||'null'),pdfDisabled:document.getElementById('pdf').disabled,text:document.getElementById('result').textContent}));}
(async()=>{
const browser=await chromium.launch({executablePath:process.env.COLUMN_V2_BROWSER_BINARY,headless:true,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--single-process','--no-zygote','--disable-dev-shm-usage']});
try{
const p=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});p.on('pageerror',e=>errors.push(e.message));
await p.goto(o.url);await p.waitForFunction(()=>workspace!==null&&readyEpoch===epoch);
let baseline=null;
for(const [name,index] of [['Baseline',0],['Changed_Cage',2],['Owner_Blocked',1]]){
 await p.selectOption('#context','qualified:'+o.handles[index]);
 const invalid=await snapshot(p);assert(invalid.pdfDisabled);assert(!invalid.text.includes('ENGINE_SELECTED_REBAR'));
 await settle(p);await p.locator('#calculate').click();await settle(p);
 const s=await snapshot(p);events.push({name,...s});assert(s.manifest.schema==='column.qualified.owner-result.v1');
 if(name==='Baseline'){baseline=s.manifest;assert(s.manifest.selected_rebar.authority==='ENGINE_SELECTED_REBAR');assert.strictEqual(await p.locator('#sectionName').textContent(),'C50x80');assert(s.manifest.fnd2_status==='READY');}
 if(name==='Changed_Cage'){assert(s.manifest.result_id!==baseline.result_id);assert.notDeepStrictEqual(s.manifest.owner_outputs.transverse_confinement.data.shear_vr_by_direction_kn,baseline.owner_outputs.transverse_confinement.data.shear_vr_by_direction_kn);}
 if(name==='Owner_Blocked'){assert(s.manifest.selected_rebar===null);assert(s.manifest.application_blockers.some(x=>x.startsWith('A18:')));}
 for(const ext of ['json','pdf','html']){
  const promise=p.waitForEvent('download');await p.locator('#'+ext).click();const d=await promise;
  const path=o.output_dir+'/'+name+'.'+ext;await d.saveAs(path);const bytes=fs.readFileSync(path);downloads.push({name,format:ext,sha256:hash(bytes),bytes:bytes.length});
  if(ext==='json')assert.deepStrictEqual(JSON.parse(bytes),s.manifest);
 }
 await p.evaluate(()=>window.scrollTo(0,0));await p.screenshot({path:o.output_dir+'/'+name+'_Screen.png',fullPage:false});
}
await p.selectOption('#context','235-product');await settle(p);await p.locator('#calculate').click();await settle(p);
const actual=await snapshot(p);assert(actual.manifest.component_id==='235');assert(actual.manifest.canonical_rebar_authority==='NOT_PROVIDED');assert(!('selected_rebar' in actual.manifest));assert.deepStrictEqual(actual.manifest.invoked_owners,[]);assert(actual.manifest.checks.every(c=>c.status==='BLOCKED'));events.push({name:'Actual_235',...actual});
assert.deepStrictEqual(errors,[]);fs.writeFileSync(o.output_dir+'/Browser_Interaction.json',JSON.stringify({status:'PASS',events,downloads,page_errors:errors,native_calls:0},null,2));
}finally{await browser.close()}
})().catch(e=>{console.error(e.stack);process.exit(1)});
