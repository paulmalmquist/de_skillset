/* Run with a local server and Playwright installed: node scripts/browser_smoke.cjs */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async()=>{
  const output=path.resolve('.flightcheck/browser');fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH}:{})});
  const page=await browser.newPage({viewport:{width:1512,height:1100},reducedMotion:'reduce'});
  const errors=[],checks=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  const url=process.env.FLIGHTCHECK_URL||'http://127.0.0.1:8000';
  try{
    await page.goto(url);await page.getByRole('heading',{name:'Trust the result. Prove the path.'}).waitFor();
    await page.locator('.graph-node').first().click();await page.locator('#graph-detail').filter({hasText:'downstream assets'}).waitFor();
    await page.screenshot({path:path.join(output,'mission-control.png'),fullPage:true});checks.push('Desktop dashboard and graph interaction');
    await page.getByRole('link',{name:'Investigation lab'}).click();
    for(const [scenario,expected] of [['masked-loss','mismatch'],['control-failure','blocked'],['stale','blocked'],['wrong-environment','blocked'],['clean','ready for review']]){
      await page.locator('#case-select').selectOption(scenario);await page.getByRole('button',{name:'Run all gates'}).click();
      await page.locator('.review-summary .status').filter({hasText:expected}).waitFor();
      await page.waitForFunction(()=>!document.querySelector('[data-action="run-case"]').disabled);
      if(scenario==='clean')assert.equal(await page.locator('.gate.pass').count(),4);
      if(scenario==='control-failure')assert.equal(await page.locator('.gate.not_run').count(),4);
      checks.push(`Investigation ${scenario}`);
    }
    await page.locator('#case-select').selectOption('masked-loss');await page.getByRole('button',{name:'Run all gates'}).click();await page.locator('.review-summary .status.mismatch').waitFor();
    await page.screenshot({path:path.join(output,'investigation.png'),fullPage:true});
    await page.getByRole('link',{name:'SQL & lineage'}).click();await page.getByRole('button',{name:'Audit SQL',exact:true}).click();
    await page.locator('#sql-results').getByText('SELECT STAR',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Load published example'}).click();await page.getByRole('button',{name:'Audit SQL',exact:true}).click();
    await page.locator('#sql-results .status.clear').waitFor();checks.push('SQL blocked and clear paths');
    await page.getByRole('link',{name:'Kimball studio'}).click();await page.getByRole('button',{name:'Validate & generate'}).click();
    await page.getByRole('button',{name:'Download ZIP'}).waitFor();
    const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Download ZIP'}).click()]);
    await download.saveAs(path.join(output,'model.zip'));checks.push('Model scaffold and actual ZIP download');
    await page.getByRole('link',{name:'Skill library'}).click();await page.getByRole('textbox',{name:'Search skills'}).fill('scd');
    await page.locator('#skill-grid [data-skill="handle-scd2"]').click();await page.locator('#detail-dialog[open]').waitFor();
    assert.ok((await page.locator('#dialog-body').textContent()).includes('half-open'));
    await page.getByRole('button',{name:'Close detail'}).click();checks.push('Skill search and modal');
    await page.getByRole('link',{name:'Run ledger'}).click();await page.getByRole('button',{name:'Run evaluations'}).click();
    await page.getByRole('heading',{name:'Regression evaluation'}).waitFor();checks.push('Evaluations and persistent ledger');
    await page.getByRole('link',{name:'Mission control'}).click();await page.waitForFunction(()=>!document.querySelector('#toast').classList.contains('visible'));await page.screenshot({path:path.join(output,'mission-control.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
    assert.equal(overflow,false,'Mobile page overflows horizontally');checks.push('390px mobile layout');
    assert.deepEqual(errors,[],'Browser console or page errors');
    fs.writeFileSync(path.join(output,'result.json'),JSON.stringify({status:'passed',checks,console_errors:errors},null,2));
    console.log(JSON.stringify({status:'passed',checks,console_errors:errors,screenshots:output},null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
