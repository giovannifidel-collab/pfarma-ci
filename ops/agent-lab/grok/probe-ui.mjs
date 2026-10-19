import { chromium } from 'playwright';

const CDP=process.env.GROK_LAB_CDP_URL||'http://127.0.0.1:9226';
const browser=await chromium.connectOverCDP(CDP);
const context=browser.contexts()[0];
if(!context) throw new Error('NO_CONTEXT');

const pages=context.pages();
const page=[...pages].reverse().find(p=>p.url().includes('grok.com'));
if(!page) throw new Error('NO_GROK_PAGE');

const editors=page.locator('textarea,[contenteditable="true"]');
let editor=null;
for(let i=(await editors.count())-1;i>=0;i--){
  const x=editors.nth(i);
  if(await x.isVisible().catch(()=>false)){
    const aria=await x.getAttribute('aria-label').catch(()=>null);
    if((aria||'').toLowerCase().includes('ask grok')){editor=x;break;}
    if(!editor)editor=x;
  }
}
if(!editor) throw new Error('NO_VISIBLE_EDITOR');

const state=await editor.evaluate(el=>{
  const form=el.closest('form');
  const attrs=o=>({
    tag:o?.tagName?.toLowerCase?.()||null,
    id:o?.id||null,
    class:o?.className||null,
    contenteditable:o?.getAttribute?.('contenteditable')||null,
    aria:o?.getAttribute?.('aria-label')||null,
    ariaDisabled:o?.getAttribute?.('aria-disabled')||null,
    ariaReadonly:o?.getAttribute?.('aria-readonly')||null,
    testid:o?.getAttribute?.('data-testid')||null,
    disabled:typeof o?.disabled==='boolean'?o.disabled:null,
  });
  return {
    editor:attrs(el),
    editorText:(el.value ?? el.innerText ?? '').slice(0,500),
    editorTextLength:(el.value ?? el.innerText ?? '').length,
    activeElement:attrs(document.activeElement),
    form:attrs(form),
    formHTML:form?form.outerHTML.slice(0,5000):null,
  };
});

const buttons=[];
const allButtons=page.locator('button');
for(let i=0;i<await allButtons.count();i++){
  const b=allButtons.nth(i);
  if(!await b.isVisible().catch(()=>false))continue;
  buttons.push(await b.evaluate(el=>({
    text:(el.innerText||'').trim().slice(0,100),
    disabled:!!el.disabled,
    ariaDisabled:el.getAttribute('aria-disabled'),
    aria:el.getAttribute('aria-label'),
    testid:el.getAttribute('data-testid'),
    type:el.getAttribute('type'),
    title:el.getAttribute('title'),
    class:String(el.className||'').slice(0,300),
  })));
}

const body=await page.locator('body').innerText().catch(()=> '');
const keywords=['limit','rate','wait','try again','error','quota','upgrade','subscribe','unavailable','disabled','verifica','verification','limite','attendi','riprova','errore'];
const interesting=body.split('\n').map(x=>x.trim()).filter(Boolean).filter(line=>keywords.some(k=>line.toLowerCase().includes(k))).slice(-80);

console.log('=== GROK UI PROBE ===');
console.log('URL='+page.url());
console.log('TITLE='+await page.title().catch(()=>''));
console.log('EDITOR_STATE='+JSON.stringify(state,null,2));
console.log('VISIBLE_BUTTONS='+JSON.stringify(buttons,null,2));
console.log('INTERESTING_LINES='+JSON.stringify(interesting,null,2));
console.log('BODY_TAIL='+JSON.stringify(body.slice(-8000)));

await page.screenshot({path:'certifications/grok-ui-probe.png',fullPage:false}).catch(()=>{});
console.log('SCREENSHOT=certifications/grok-ui-probe.png');
process.exit(0);
