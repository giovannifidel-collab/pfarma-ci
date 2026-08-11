#!/usr/bin/env python3
import base64, json, os, struct, subprocess, tempfile, time, urllib.request, zlib
from pathlib import Path
DRIVER=os.environ.get('CHROMEDRIVER_BIN','chromedriver'); BASE='http://127.0.0.1:4173'; WD='http://127.0.0.1:9515'; OUT=Path(os.environ.get('VISUAL_OUT','.')); OUT.mkdir(parents=True,exist_ok=True)
def http(method,url,payload=None,timeout=20):
    data=None if payload is None else json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,method=method,headers={'content-type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r: raw=r.read()
    return json.loads(raw or b'{}')
def wd(method,path,payload=None):
    result=http(method,WD+path,payload); value=result.get('value')
    if isinstance(value,dict) and value.get('error'): raise RuntimeError(f"webdriver {value.get('error')}: {value.get('message')}")
    return value
def execute(s,script,args=None,async_=False): return wd('POST',f'/session/{s}/execute/{"async" if async_ else "sync"}',{'script':script,'args':args or []})
def shot(s,name): (OUT/name).write_bytes(base64.b64decode(wd('GET',f'/session/{s}/screenshot')))
def wait(s,expr,timeout=15):
    end=time.time()+timeout
    while time.time()<end:
        if execute(s,f'return Boolean({expr});'): return
        time.sleep(.25)
    raise RuntimeError(f'timed out waiting for {expr}')
def png(w,h,rgb,accent):
    raw=b''.join(bytes([0])+b''.join(bytes(accent if ((x//48)+(y//48))%4==0 else rgb) for x in range(w)) for y in range(h))
    def chunk(k,d): return struct.pack('>I',len(d))+k+d+struct.pack('>I',zlib.crc32(k+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
def video_fixture():
    ffmpeg=subprocess.run(['bash','-lc','command -v ffmpeg || true'],capture_output=True,text=True,check=True).stdout.strip()
    if not ffmpeg: raise RuntimeError('ffmpeg unavailable')
    with tempfile.TemporaryDirectory() as tmp:
        target=Path(tmp)/'fixture.mp4'; subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=0x3568a8:s=320x240:d=0.7','-vf','format=yuv420p','-an','-c:v','libx264','-movflags','+faststart','-y',str(target)],check=True); return target.read_bytes()
def main():
    driver_log=open(OUT/'chromedriver.log','wb'); proc=subprocess.Popen([DRIVER,'--port=9515','--allowed-origins=*'],stdout=driver_log,stderr=subprocess.STDOUT); session=None
    try:
        for _ in range(80):
            try:
                if http('GET',WD+'/status',timeout=1).get('value',{}).get('ready'): break
            except Exception: time.sleep(.1)
        created=wd('POST','/session',{'capabilities':{'alwaysMatch':{'browserName':'chrome','goog:chromeOptions':{'args':['--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--autoplay-policy=no-user-gesture-required','--window-size=1440,1000']}}}}); session=created.get('sessionId')
        wd('POST',f'/session/{session}/url',{'url':BASE+'/'}); time.sleep(.7); email=f'visual-{int(time.time())}@example.test'
        auth=execute(session,"""const done=arguments[arguments.length-1],email=arguments[0];(async()=>{const password='family-cloud-visual-pass-123';await fetch('/api/auth/register',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify({email,password})});const r=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify({email,password})});done({status:r.status});})().catch(e=>done({error:String(e)}));""",[email],True)
        if auth.get('error') or auth.get('status',500)>=400: raise RuntimeError(f'auth failed {auth}')
        fixtures=[('vacanza-mare-2024.png','image/png',png(360,260,(46,115,175),(255,213,79)),['spiaggia','mare','vacanza','meta:data:2024-08-15','ai:spiaggia','ai:mare','ai:analizzato']),('famiglia-giardino.png','image/png',png(360,260,(70,133,83),(237,231,177)),['famiglia','giardino','meta:data:2025-05-04','ai:famiglia','ai:giardino','ai:persona','ai:analizzato']),('tramonto-viaggio.png','image/png',png(360,260,(151,84,94),(246,170,95)),['tramonto','viaggio','meta:data:2026-07-22','ai:tramonto','ai:analizzato']),('mare-sera.mp4','video/mp4',video_fixture(),['mare','video','meta:data:2026-07-22','ai:mare','ai:analizzato'])]
        script="""const done=arguments[arguments.length-1];(async()=>{const [name,type,b64,key,tags]=arguments,raw=atob(b64),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);const r=await fetch('/api/media',{method:'POST',credentials:'same-origin',headers:{'content-type':type,'idempotency-key':key,'x-original-name':name},body:bytes}),body=await r.json();if(!r.ok)throw new Error(JSON.stringify(body));const t=await fetch(`/api/media/${encodeURIComponent(body.media.id)}/tags`,{method:'PUT',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify({tags})});if(!t.ok)throw new Error(await t.text());done({ok:true});})().catch(e=>done({error:String(e)}));"""
        stamp=int(time.time())
        for i,(name,typ,data,tags) in enumerate(fixtures):
            result=execute(session,script,[name,typ,base64.b64encode(data).decode(),f'visual-{i}-{stamp}',tags],True)
            if result.get('error'): raise RuntimeError(result['error'])
        wd('POST',f'/session/{session}/url',{'url':BASE+'/'}); wait(session,"document.querySelectorAll('#media-grid [data-id]').length>=4"); wait(session,"document.querySelectorAll('.timeline-group').length>=2")
        desktop=execute(session,"return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,cards:document.querySelectorAll('#media-grid [data-id]').length,groups:document.querySelectorAll('.timeline-group').length,videos:document.querySelectorAll('.media-card-video').length,nav:getComputedStyle(document.querySelector('.media-primary-nav')).display,bulkHidden:document.querySelector('#bulk-album-organizer')?.hidden,sessionRight:document.querySelector('#library-session')?.getBoundingClientRect().right};")
        if desktop['scrollWidth']>desktop['width']+2 or desktop['cards']<4 or desktop['groups']<2 or desktop['videos']<1 or desktop['nav']=='none' or not desktop['bulkHidden'] or desktop['sessionRight']>desktop['width']+1: raise RuntimeError(f'desktop contract failed {desktop}')
        shot(session,'desktop-home.png')
        opened=execute(session,"const b=document.querySelector('#media-grid .thumb[data-action=\"detail\"]')||document.querySelector('#media-grid .thumb');if(!b)return false;b.click();return true;")
        if not opened: raise RuntimeError('detail trigger unavailable')
        wait(session,"document.querySelector('#detail-dialog')?.open===true"); wait(session,"document.querySelector('.consumer-detail-layout')"); shot(session,'desktop-detail.png'); execute(session,"document.querySelector('#close-detail')?.click();return true;")
        execute(session,"document.querySelector('.media-primary-nav [data-media-view=search]').click();return true;"); wait(session,"document.body.dataset.mediaView==='search'"); shot(session,'desktop-search.png')
        execute(session,"document.querySelector('.media-primary-nav [data-media-view=collections]').click();return true;"); wait(session,"document.body.dataset.mediaView==='collections'"); wait(session,"document.querySelectorAll('.collection-card').length>=8"); shot(session,'desktop-collections.png')
        wd('POST',f'/session/{session}/window/rect',{'width':390,'height':844}); execute(session,"document.querySelector('.mobile-media-nav [data-media-view=photos]').click();return true;"); wait(session,"document.body.dataset.mediaView==='photos'"); time.sleep(.4)
        mobile=execute(session,"return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,mobileNav:getComputedStyle(document.querySelector('.mobile-media-nav')).display,cards:document.querySelectorAll('#media-grid [data-id]').length};")
        if mobile['scrollWidth']>mobile['width']+2 or mobile['mobileNav']=='none' or mobile['cards']<4: raise RuntimeError(f'mobile contract failed {mobile}')
        shot(session,'mobile-home.png'); execute(session,"document.querySelector('.mobile-media-nav [data-media-view=search]').click();return true;"); wait(session,"document.body.dataset.mediaView==='search'"); shot(session,'mobile-search.png')
        (OUT/'visual-contract.json').write_text(json.dumps({'desktop':desktop,'mobile':mobile,'candidate':os.environ.get('FAMILY_CLOUD_REF')},indent=2)); print(json.dumps({'desktop':desktop,'mobile':mobile},indent=2))
    finally:
        if session:
            try: wd('DELETE',f'/session/{session}')
            except Exception: pass
        proc.terminate(); driver_log.close()
if __name__=='__main__': main()
