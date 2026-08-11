#!/usr/bin/env python3
import base64
import json
import os
import struct
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path

DRIVER = os.environ.get('CHROMEDRIVER_BIN', 'chromedriver')
BASE = 'http://127.0.0.1:4173'
WD = 'http://127.0.0.1:9515'
OUT = Path(os.environ.get('VISUAL_OUT', '.'))
OUT.mkdir(parents=True, exist_ok=True)


def http(method, url, payload=None, timeout=20):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw or b'{}')


def wd(method, path, payload=None):
    result = http(method, WD + path, payload)
    value = result.get('value')
    if isinstance(value, dict) and value.get('error'):
        raise RuntimeError(f"webdriver {value.get('error')}: {value.get('message')}")
    return value


def execute(session, script, args=None, asynchronous=False):
    endpoint = 'async' if asynchronous else 'sync'
    return wd('POST', f'/session/{session}/execute/{endpoint}', {'script': script, 'args': args or []})


def screenshot(session, name):
    encoded = wd('GET', f'/session/{session}/screenshot')
    (OUT / name).write_bytes(base64.b64decode(encoded))


def png(width, height, rgb, accent):
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            use_accent = ((x // 48) + (y // 48)) % 4 == 0
            color = accent if use_accent else rgb
            row.extend(color)
        rows.append(bytes(row))
    raw = b''.join(rows)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')


def wait_for(session, expression, timeout=12):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if execute(session, f'return Boolean({expression});'):
            return
        time.sleep(0.25)
    raise RuntimeError(f'timed out waiting for: {expression}')


def main():
    driver_log = open(OUT / 'chromedriver.log', 'wb')
    process = subprocess.Popen([DRIVER, '--port=9515', '--allowed-origins=*'], stdout=driver_log, stderr=subprocess.STDOUT)
    session = None
    try:
        for _ in range(80):
            try:
                if http('GET', WD + '/status', timeout=1).get('value', {}).get('ready'):
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError('chromedriver did not become ready')

        created = wd('POST', '/session', {'capabilities': {'alwaysMatch': {'browserName': 'chrome', 'goog:chromeOptions': {'args': ['--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--window-size=1440,1000']}}}})
        session = created.get('sessionId') if isinstance(created, dict) else None
        if not session:
            raise RuntimeError(f'no webdriver session id: {created!r}')

        wd('POST', f'/session/{session}/url', {'url': BASE + '/'})
        time.sleep(0.8)
        email = f'visual-{int(time.time())}@example.test'
        auth = execute(session, """
          const done=arguments[arguments.length-1], email=arguments[0];
          (async()=>{
            const password='family-cloud-visual-pass-123';
            const reg=await fetch('/api/auth/register',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify({email,password})});
            const login=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify({email,password})});
            done({register:reg.status,login:login.status,loginText:await login.text()});
          })().catch(error=>done({error:String(error)}));
        """, [email], True)
        if auth.get('error') or auth.get('login', 500) >= 400:
            raise RuntimeError(f'authentication failed: {auth}')

        fixtures = [
            ('vacanza-mare-2024.png', 'image/png', png(360, 260, (46, 115, 175), (255, 213, 79)), ['spiaggia','mare','vacanza','meta:data:2024-08-15','ai:spiaggia','ai:mare','ai:analizzato']),
            ('famiglia-giardino.png', 'image/png', png(360, 260, (70, 133, 83), (237, 231, 177)), ['famiglia','giardino','meta:data:2025-05-04','ai:famiglia','ai:giardino','ai:persona','ai:analizzato']),
            ('tramonto-viaggio.png', 'image/png', png(360, 260, (151, 84, 94), (246, 170, 95)), ['tramonto','viaggio','meta:data:2026-07-22','ai:tramonto','ai:analizzato']),
            ('mare-sera.mp4', 'video/mp4', b'\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2', ['mare','video','meta:data:2026-07-22','ai:mare','ai:analizzato']),
        ]
        upload_script = """
          const done=arguments[arguments.length-1];
          (async()=>{
            const [name,type,b64,key,tags]=arguments;
            const raw=atob(b64), bytes=new Uint8Array(raw.length); for(let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
            const response=await fetch('/api/media',{method:'POST',credentials:'same-origin',headers:{'content-type':type,'idempotency-key':key,'x-original-name':name},body:bytes});
            const body=await response.json(); if(!response.ok) throw new Error(JSON.stringify(body));
            const media=body.media; const tagged=await fetch(`/api/media/${encodeURIComponent(media.id)}/tags`,{method:'PUT',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify({tags})});
            if(!tagged.ok) throw new Error(await tagged.text()); done({id:media.id,status:response.status});
          })().catch(error=>done({error:String(error)}));
        """
        for index, (name, media_type, data, tags) in enumerate(fixtures):
            result = execute(session, upload_script, [name, media_type, base64.b64encode(data).decode(), f'visual-{index}-{int(time.time())}', tags], True)
            if result.get('error'):
                raise RuntimeError(f'fixture upload failed: {result}')

        wd('POST', f'/session/{session}/url', {'url': BASE + '/'})
        wait_for(session, "document.querySelectorAll('#media-grid [data-id]').length >= 4")
        wait_for(session, "document.querySelectorAll('.timeline-group').length >= 2")
        desktop = execute(session, "return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,cards:document.querySelectorAll('#media-grid [data-id]').length,groups:document.querySelectorAll('.timeline-group').length,videos:document.querySelectorAll('.media-card-video').length,nav:getComputedStyle(document.querySelector('.media-primary-nav')).display};")
        if desktop['scrollWidth'] > desktop['width'] + 2 or desktop['cards'] < 4 or desktop['groups'] < 2 or desktop['videos'] < 1 or desktop['nav'] == 'none':
            raise RuntimeError(f'desktop layout contract failed: {desktop}')
        screenshot(session, 'desktop-home.png')

        opened = execute(session, "const b=document.querySelector('#media-grid [data-id] [data-action=details]'); if(b){b.click(); return true;} return false;")
        if not opened:
            raise RuntimeError('detail trigger unavailable')
        wait_for(session, "document.querySelector('#detail-dialog')?.open === true")
        screenshot(session, 'desktop-detail.png')
        execute(session, "document.querySelector('#close-detail')?.click(); return true;")

        execute(session, "document.querySelector('.media-primary-nav [data-media-view=search]')?.click(); return true;")
        wait_for(session, "document.body.dataset.mediaView === 'search'")
        screenshot(session, 'desktop-search.png')

        execute(session, "document.querySelector('.media-primary-nav [data-media-view=collections]')?.click(); return true;")
        wait_for(session, "document.body.dataset.mediaView === 'collections'")
        wait_for(session, "document.querySelectorAll('.collection-card').length >= 8")
        screenshot(session, 'desktop-collections.png')

        wd('POST', f'/session/{session}/window/rect', {'width': 390, 'height': 844})
        execute(session, "document.querySelector('.mobile-media-nav [data-media-view=photos]')?.click(); return true;")
        wait_for(session, "document.body.dataset.mediaView === 'photos'")
        time.sleep(0.5)
        mobile = execute(session, "return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,mobileNav:getComputedStyle(document.querySelector('.mobile-media-nav')).display,cards:document.querySelectorAll('#media-grid [data-id]').length};")
        if mobile['scrollWidth'] > mobile['width'] + 2 or mobile['mobileNav'] == 'none' or mobile['cards'] < 4:
            raise RuntimeError(f'mobile layout contract failed: {mobile}')
        screenshot(session, 'mobile-home.png')

        execute(session, "document.querySelector('.mobile-media-nav [data-media-view=search]')?.click(); return true;")
        wait_for(session, "document.body.dataset.mediaView === 'search'")
        screenshot(session, 'mobile-search.png')

        (OUT / 'visual-contract.json').write_text(json.dumps({'desktop': desktop, 'mobile': mobile, 'candidate': os.environ.get('FAMILY_CLOUD_REF')}, indent=2), encoding='utf-8')
        print(json.dumps({'desktop': desktop, 'mobile': mobile}, indent=2))
    finally:
        if session:
            try: wd('DELETE', f'/session/{session}')
            except Exception: pass
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill()
        driver_log.close()


if __name__ == '__main__':
    main()
