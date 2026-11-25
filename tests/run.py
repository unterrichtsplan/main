import base64, json, hashlib, os, re, sys, time, zipfile, io
from urllib.parse import urlparse, unquote
from playwright.sync_api import sync_playwright

SITE = 'http://localhost:8765/'
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE)
OUT = os.path.join(HERE, 'out')
FILES = os.path.join(OUT, 'files')
os.makedirs(OUT, exist_ok=True)
repo = {}       # path -> bytes  (simuliertes Repository)
stale = None    # eingefrorener Stand der Seite (simuliert verzögertes GitHub Pages)
log = []
def sha(b): return hashlib.sha1(b).hexdigest()

def gh_handler(route, request):
    u = urlparse(request.url)
    m = re.match(r'^/repos/[^/]+/[^/]+(/contents/(.*))?$', u.path)
    if not m: return route.fulfill(status=404, body='{}')
    if not m.group(1):
        size = sum(len(v) for v in repo.values()) // 1024
        return route.fulfill(status=200, content_type='application/json', body=json.dumps({'permissions': {'push': True}, 'size': size}))
    path = unquote(m.group(2))
    meth = request.method
    if meth == 'GET':
        if path not in repo:
            kids = sorted(k for k in repo if k.startswith(path.rstrip('/') + '/') and '/' not in k[len(path.rstrip('/')) + 1:])
            if kids:   # Ordner-Inhalt wie bei GitHub
                return route.fulfill(status=200, content_type='application/json', body=json.dumps([{'path': k, 'name': k.split('/')[-1], 'type': 'file', 'sha': sha(repo[k])} for k in kids]))
            return route.fulfill(status=404, content_type='application/json', body='{"message":"Not Found"}')
        b = repo[path]
        if 'raw' in (request.headers.get('accept') or ''):
            return route.fulfill(status=200, body=b)
        return route.fulfill(status=200, content_type='application/json', body=json.dumps({'sha': sha(b), 'content': base64.b64encode(b).decode()}))
    body = json.loads(request.post_data or '{}')
    if meth == 'PUT':
        if path in repo and body.get('sha') != sha(repo[path]):
            return route.fulfill(status=409, content_type='application/json', body='{"message":"sha does not match"}')
        repo[path] = base64.b64decode(body['content'])
        log.append(('PUT', path))
        return route.fulfill(status=200, content_type='application/json', body=json.dumps({'content': {'sha': sha(repo[path])}}))
    if meth == 'DELETE':
        repo.pop(path, None); log.append(('DEL', path))
        return route.fulfill(status=200, content_type='application/json', body='{}')
    route.fulfill(status=405, body='{}')

def site_handler(route, request):
    p = unquote(urlparse(request.url).path).lstrip('/') or 'index.html'
    src = stale if stale is not None else repo   # GitHub Pages hängt nach dem Speichern hinterher
    if p in src: return route.fulfill(status=200, body=src[p])
    f = os.path.join(ROOT, p)
    if os.path.isfile(f) and not p.startswith(('data/', 'material/')):
        ct = 'text/html' if p.endswith('.html') else ('text/javascript' if p.endswith('.js') else None)
        return route.fulfill(status=200, body=open(f, 'rb').read(), **({'content_type': ct} if ct else {}))
    route.fulfill(status=404, body='nf')

# Hilfsfunktionen im Browser (eigene Krypto, um ALTE Daten einzuspielen)
JS_HELPERS = r'''
window.T = {
  b64: b => { let s=''; for(const x of b) s+=String.fromCharCode(x); return btoa(s); },
  unb64: s => Uint8Array.from(atob(s), c => c.charCodeAt(0)),
  async kek(secret, salt, iter){ const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), 'PBKDF2', false, ['deriveBits']);
    return new Uint8Array(await crypto.subtle.deriveBits({name:'PBKDF2', hash:'SHA-256', salt:T.unb64(salt), iterations:iter}, base, 256)); },
  async key(raw){ return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt','decrypt']); },
  async seal(k, bytes){ const iv = crypto.getRandomValues(new Uint8Array(12)); const ct = new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM', iv}, k, bytes));
    const o = new Uint8Array(16+ct.length); o.set([85,77,67,49],0); o.set(iv,4); o.set(ct,16); return o; },
  async unseal(k, b){ return new Uint8Array(await crypto.subtle.decrypt({name:'AES-GCM', iv:b.subarray(4,16)}, k, b.subarray(16))); },
  async keys(code, pw){
    const z = await (await fetch('data/zugang.json?t='+Date.now())).json();
    const kb = await T.key(await T.kek(code, z.basis.salt, z.iter)); const dekB = await T.unseal(kb, T.unb64(z.basis.dek));
    const kp = await T.key(await T.kek(pw, z.pruefung.salt, z.iter)); const dekP = await T.unseal(kp, T.unb64(z.pruefung.dek));
    return { B: await T.key(dekB), P: await T.key(dekP) };
  },
  async put(path, bytes){ let sha=null; const g = await fetch('https://api.github.com/repos/o/r/contents/'+path);
    if(g.ok) sha = (await g.json()).sha;
    const r = await fetch('https://api.github.com/repos/o/r/contents/'+path, {method:'PUT', body:JSON.stringify({message:'t', content:T.b64(bytes), sha})}); return r.ok; },
  async getData(K){ const b = new Uint8Array(await (await fetch('data/inhalt.enc?t='+Date.now())).arrayBuffer()); return JSON.parse(new TextDecoder().decode(await T.unseal(K.B, b))); },
  async putData(K, d){ return T.put('data/inhalt.enc', await T.seal(K.B, new TextEncoder().encode(JSON.stringify(d)))); },
  async file(K, path, text, schutz){ const enc = await T.seal(schutz==='pruefung'?K.P:K.B, new TextEncoder().encode(text)); await T.put(path, enc); return {pfad:path, name:path.split('/').pop().replace('.enc',''), ext:path.split('.').slice(-2)[0], mb:0.01, schutz}; }
};
'''

# kleine Testdateien
PDF = b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
os.makedirs(FILES + '', exist_ok=True)
open(FILES + '/AB Spiegel-Parcours.pdf', 'wb').write(PDF)
# Ersatz für eine Schritt-Seite wie „Camera obscura“ (echtes Material gehört nicht unverschlüsselt ins Repository)
open(FILES + '/camera-obscura.html', 'w', encoding='utf-8').write("""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><title>Camera obscura</title>
<style>.app-only{display:none}.in-app .bar .app-only{display:inline-flex}</style></head><body>
<header><div class="bar"><a class="home app-only" href="#zurueck">‹ Übersicht</a><b>Physik 8</b></div>
<nav><a class="step" href="#auftrag" data-page="auftrag">1</a> <a class="step" href="#bauen" data-page="bauen">2</a></nav></header>
<article id="auftrag"><h1>Auftrag</h1></article><article id="bauen" hidden><h1>Bauen</h1></article>
<script>if(window.Plattform)document.documentElement.classList.add('in-app');
function show(n){if(n==='zurueck'||n==='weiter')return;if(['auftrag','bauen'].indexOf(n)<0)n='auftrag';
['auftrag','bauen'].forEach(function(p){document.getElementById(p).hidden=p!==n;});}
addEventListener('hashchange',function(){show(location.hash.slice(1));});show(location.hash.slice(1));</script></body></html>""")

open(FILES + '/AB Spiegel-Parcours.docx', 'wb').write(b'PK fake docx')
open(FILES + '/Klausur Optik.pdf', 'wb').write(PDF)
open(FILES + '/Film.mp4', 'wb').write(b'0' * 100)
# großes PNG für Verkleinerung
import struct, zlib
def png(w, h):
    raw = b''.join(b'\x00' + os.urandom(w * 3) for _ in range(h))
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 1)) + chunk(b'IEND', b'')
open(FILES + '/Conceptmap.png', 'wb').write(png(2600, 1400))

def paths_of(o):
    out = []
    if isinstance(o, dict):
        if isinstance(o.get('pfad'), str): out.append(o['pfad'])
        for v in o.values(): out += paths_of(v)
    elif isinstance(o, list):
        for v in o: out += paths_of(v)
    return out

results = []
def check(name, cond, info=''):
    results.append((name, bool(cond), info)); print(('OK   ' if cond else 'FAIL ') + name + ('  ' + str(info) if info and not cond else ''))

with sync_playwright() as p:
    chrome = os.environ.get('CHROME') or ('/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None)
    br = p.chromium.launch(executable_path=chrome, args=['--no-sandbox']) if chrome else p.chromium.launch(args=['--no-sandbox'])
    ctx = br.new_context(service_workers='block', viewport={'width': 1024, 'height': 1300}, accept_downloads=True)
    ctx.route('https://api.github.com/**', gh_handler)
    ctx.route(SITE + '**', site_handler)
    page = ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    dialogs = []
    def on_dialog(d):
        dialogs.append(d.message)
        # „auch aus dem Speicher löschen?“ -> ja; sonst bestätigen
        d.accept()
    page.on('dialog', on_dialog)
    def wait_saved():
        page.wait_for_selector('#toast.on', timeout=20000); page.wait_for_selector('#busy:not(.on)', state='attached', timeout=60000); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=60000); time.sleep(0.3)
        page.evaluate("document.querySelector('#toast').classList.remove('on')")
    def shot(n): page.screenshot(path=f'{OUT}/{n}.png', full_page=True)

    # ---- Ersteinrichtung ----
    page.goto(SITE)
    page.evaluate("localStorage.setItem('um-github', JSON.stringify({owner:'o', repo:'r', branch:'main', token:'x'}))")
    page.goto(SITE + '#/einrichtung'); page.reload()
    page.wait_for_selector('#setup-form')
    page.fill('input[name=code]', '1234'); page.fill('input[name=pw]', 'pruefung123'); page.fill('input[name=jgPhysik]', '8')
    page.click('#setup-form button[type=submit]')
    page.wait_for_selector('.fach', timeout=60000)
    check('Ersteinrichtung', 'data/inhalt.enc' in repo and 'data/zugang.json' in repo)

    # ---- ALTE Daten einspielen (Board + nurLK + sus/lk + Prüfung) ----
    page.evaluate(JS_HELPERS); page.add_init_script(JS_HELPERS)
    page.evaluate('''async () => {
      const K = await T.keys('1234', 'pruefung123'); const d = await T.getData(K);
      delete d.version;
      const f = d.faecher.find(x => x.id === 'physik'), j = f.jahrgaenge[0], r = j.reihen.find(x => x.id === 'optische-instrumente');
      const dir = 'material/physik/8/optische-instrumente/';
      r.board = { nodes:[{id:'a', x:50, y:50, t:'Licht', art:'thema'}], edges:[], bild: await T.file(K, dir+'bild.jpg.enc', 'BILD', 'basis') };
      r.vorhaben = [
        { id:'v1', titel:'Camera obscura', notiz:'', materialien:[
          { id:'m1', typ:'ab', titel:'Nachricht an Lena', nurLK:false, sus: await T.file(K, dir+'ab-lena.pdf.enc', 'PDF-LENA', 'basis'), lk: await T.file(K, dir+'ab-lena.docx.enc', 'DOCX-LENA', 'basis'), url:null },
          { id:'m2', typ:'loesung', titel:'Lösung Lena', nurLK:true, sus: await T.file(K, dir+'loes.pdf.enc', 'LOES', 'basis'), lk:null, url:null },
          { id:'m3', typ:'video', titel:'Erklärvideo', nurLK:false, sus:null, lk:null, url:'https://www.youtube.com/watch?v=x' },
          { id:'m4', typ:'pruefung', titel:'Test Optik', nurLK:true, sus: await T.file(K, dir+'test.pdf.enc', 'TEST', 'pruefung'), lk:null, url:null } ]},
        { id:'v2', titel:'Linsen', notiz:'', ausgeblendet:true, materialien:[
          { id:'m5', typ:'ab', titel:'AB Linsen', nurLK:false, sus: await T.file(K, dir+'linsen.pdf.enc', 'LINSEN', 'basis'), lk:null, url:null } ]}
      ];
      await T.putData(K, d);
    }''')

    # ---- Lehrkraft-Ansicht nach Migration ----
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.reload()
    page.wait_for_selector('.rows')
    time.sleep(0.8)
    row1 = page.locator('.row').nth(0)
    sus_titles = row1.locator('.row-main > .chips .chip').all_inner_texts()
    check('Migration: SuS-Chips (AB + Video)', any('Nachricht an Lena' in t for t in sus_titles) and any('Erklärvideo' in t for t in sus_titles) and not any('Lösung' in t for t in sus_titles), sus_titles)
    check('Migration: Lehrkraft-Material (DOCX, Lösung, Test)', 'Lehrkraft-Material (3)' in row1.inner_text(), row1.inner_text())
    check('Titelbild sichtbar (aus board.bild)', page.locator('img.titelbild').count() == 1 and page.locator('.board').count() == 0)
    page.wait_for_function("document.querySelector('img.titelbild') && document.querySelector('img.titelbild').src.startsWith('blob:')", timeout=5000)
    shot('01-lehrkraft-migriert')

    # ---- Bearbeiten-Modus: Auge pro Material ----
    page.click('#edit-toggle'); page.wait_for_selector('body.editing')
    shot('02-bearbeiten')
    check('Zwei Knöpfe pro Vorhaben', page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=sus]').count() == 1 and page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=lk]').count() == 1)
    check('Concept-Map-Editor entfernt', page.locator('[data-act=edit-board]').count() == 0 and page.locator('[data-act=edit-bild]').count() >= 1)
    page.locator('.row').nth(0).locator('[data-act=vis-m]').nth(1).click()   # Erklärvideo ausblenden
    wait_saved()
    check('Material ausblenden speichert', page.locator('.row').nth(0).locator('.chip.aus').count() == 1)
    shot('03-material-ausgeblendet')

    # ---- Upload SuS-Material (PDF) ----
    page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=sus]').click()
    page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/AB Spiegel-Parcours.pdf')
    check('Titel aus Dateiname', page.input_value('input[name=titel]') == 'AB Spiegel-Parcours', page.input_value('input[name=titel]'))
    shot('04-dialog-sus')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    # ---- Upload Lehrkraft-Material (DOCX) ----
    page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=lk]').click()
    page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/AB Spiegel-Parcours.docx')
    check('LK-Dialog: Sichtbarkeit verborgen', page.locator('#sichtbar-row').is_hidden())
    shot('05-dialog-lk')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    # ---- Klausur im SuS-Feld -> wird automatisch Lehrkraft/Prüfung ----
    page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=sus]').click()
    page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/Klausur Optik.pdf')
    check('Klausur erkannt -> Prüfung + Lehrkraft', page.input_value('select[name=typ]') == 'pruefung' and page.is_checked('input[name=bereich][value=lk]'))
    page.click('dialog#sheet button[value=ok]')
    page.wait_for_selector('dialog#sheet[open] input[name=pw]'); page.fill('input[name=pw]', 'pruefung123'); page.click('dialog#sheet button[value=ok]')
    wait_saved()
    # ---- Video-Datei wird abgelehnt ----
    n_before = len(dialogs)
    page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=sus]').click()
    page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/Film.mp4')
    page.click('dialog#sheet button[value=ok]'); time.sleep(1.5); shot('dbg-video'); print('DBG', dialogs[-3:], page.locator('dialog#sheet[open]').count())
    check('Video-Upload abgelehnt', any('Videos bitte nicht hochladen' in d for d in dialogs[n_before:]), dialogs[n_before:])
    # ---- Titelbild ändern (großes PNG wird verkleinert) ----
    page.click('[data-act=edit-bild]'); page.wait_for_selector('dialog#sheet[open]')
    page.click('input[name=bild__mode][value=file]')
    page.set_input_files('input[name=bild__file]', FILES + '/Conceptmap.png')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    tb = [k for k in repo if 'conceptmap' in k]
    check('Titelbild hochgeladen + alte Datei gelöscht', len(tb) == 1 and 'material/physik/8/optische-instrumente/bild.jpg.enc' not in repo, tb)
    check('Titelbild verkleinert (JPEG)', tb and tb[0].endswith('.jpg.enc') and len(repo[tb[0]]) < os.path.getsize(FILES + '/Conceptmap.png'), [(k, len(repo[k])) for k in tb])
    page.click('#edit-toggle')
    time.sleep(0.5)
    shot('06-lehrkraft-nach-upload')

    # ---- Datenmodell prüfen ----
    d = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    r = [x for x in d['faecher'][1]['jahrgaenge'][0]['reihen'] if x['id'] == 'optische-instrumente'][0]
    mats = r['vorhaben'][0]['materialien']
    check('Datenmodell v2', d.get('version') == 2 and 'board' not in r and r['titelbild'] and all('bereich' in m and 'sus' not in m and 'nurLK' not in m for m in mats), json.dumps(mats)[:400])
    check('Prüfung mit Prüfungsschlüssel', all(m['datei']['schutz'] == 'pruefung' for m in mats if m['typ'] == 'pruefung'))
    check('Lösung + DOCX im LK-Bereich', [m['bereich'] for m in mats if m['titel'] == 'Lösung Lena'] == ['lk'] and len([m for m in mats if m['titel'] == 'Nachricht an Lena']) == 2)

    # ---- Speicheranzeige ----
    page.goto(SITE + '#/einstellungen/speicher'); page.wait_for_selector('.store-list')
    page.wait_for_function("document.querySelector('#repo-size').textContent.indexOf('ca.') >= 0", timeout=5000)
    check('Speicheranzeige', 'Physik' in page.inner_text('.store-list') and 'Jahrgang 8' in page.inner_text('.store-list'))
    shot('07-speicher')

    # ---- Kursansicht ----
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.wait_for_selector('.rows')
    time.sleep(0.5)
    txt = page.inner_text('main')
    check('Kurs: kein „Ganze Sammlung öffnen“', 'Ganze Sammlung' not in txt)
    check('Kurs: kein LK-Material, keine Lösung/Klausur', 'Lösung Lena' not in txt and 'Klausur' not in txt and 'Lehrkraft' not in txt)
    check('Kurs: ausgeblendetes Material/Vorhaben fehlt', 'Erklärvideo' not in txt and 'Linsen' not in txt and 'Nachricht an Lena' in txt)
    check('Kurs: Titelbild', page.locator('img.titelbild').count() == 1)
    check('Kurs: Lehrkraft-Knopf (Gerät mit Token)', page.locator('#kurs-exit').is_visible())
    shot('08-kurs')
    with page.expect_download() as dl:
        page.click('[data-act=dl-reihe]')
    zpath = OUT + '/sus.zip'; dl.value.save_as(zpath)
    names = zipfile.ZipFile(zpath).namelist()
    check('SuS-ZIP: nur SuS-Inhalte', any('Nachricht an Lena.pdf' in n for n in names) and any('AB Spiegel-Parcours.pdf' in n for n in names)
          and not any(x in ' '.join(names) for x in ['docx', 'Lösung', 'Klausur', 'Test Optik', 'Linsen']), names)
    check('SuS-ZIP: Inhalt entschlüsselt', zipfile.ZipFile(zpath).read([n for n in names if 'Lena' in n][0]) == b'PDF-LENA')
    page.click('#kurs-exit'); page.wait_for_selector('.crumbs')
    check('Lehrkraft-Knopf führt zur Reihe', '#/f/physik/8/optische-instrumente' in page.url)

    # ---- Export -> Reihe löschen -> Import ----
    page.goto(SITE + '#/f/physik/8'); page.wait_for_selector('.reihe-card')
    with page.expect_download() as dl:
        page.click('[data-act=export-j]')
    epath = OUT + '/export.zip'; dl.value.save_as(epath)
    plan = json.loads(zipfile.ZipFile(epath).read('import.json'))
    pr = [x for x in plan['eintraege'][0]['reihen'] if x['titel'] == 'Sehhilfen für nah und fern'][0]
    check('Export v2 mit Titelbild/bereich/ausgeblendet', plan['version'] == 2 and pr.get('titelbild') and any(m.get('ausgeblendet') for m in pr['vorhaben'][0]['materialien']) and all('bereich' in m for m in pr['vorhaben'][0]['materialien']))
    # Reihe löschen
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows')
    page.click('#edit-toggle'); page.wait_for_selector('body.editing')
    page.evaluate("document.querySelector('#toast').classList.remove('on')"); page.click('.page-head [data-act=del-r]'); wait_saved()
    # Import
    page.goto(SITE + '#/einstellungen/verwaltung'); page.wait_for_selector('[data-act=import]')
    with page.expect_file_chooser() as fc:
        page.click('[data-act=import]')
    fc.value.set_files(epath)
    page.wait_for_selector('dialog#sheet[open]'); page.click('dialog#sheet button[value=ok]')
    wait_saved()
    d2 = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    r2 = [x for x in d2['faecher'][1]['jahrgaenge'][0]['reihen'] if x['titel'] == 'Sehhilfen für nah und fern'][0]
    m2 = r2['vorhaben'][0]['materialien']
    check('Import: Reihen-ID bleibt (Kurs-Link)', r2['id'] == 'optische-instrumente', r2['id'])
    check('Import: Titelbild wieder da', bool(r2.get('titelbild')))
    check('Import: Bereiche + Ausblenden erhalten', sorted((m['titel'], m['bereich'], m['ausgeblendet']) for m in m2) == sorted((m['titel'], m['bereich'], m['ausgeblendet']) for m in mats) , [(m['titel'], m['bereich'], m['ausgeblendet']) for m in m2])

    # ---- Import einer ALTEN import.json (v1, board.bild) ----
    v1 = {'format': 'unterrichtsmaterial-import', 'version': 1, 'fach': 'Physik', 'jahrgang': '9', 'reihen': [{'titel': 'Alt', 'board': {'nodes': [], 'edges': [], 'bild': 'dateien/b.png'},
          'vorhaben': [{'titel': 'V', 'materialien': [{'typ': 'ab', 'titel': 'X', 'sicht': 'alle', 'sus': 'dateien/x.pdf', 'lk': 'dateien/x.docx'}]}]}]}
    zb = io.BytesIO(); z = zipfile.ZipFile(zb, 'w')
    z.writestr('import.json', json.dumps(v1)); z.writestr('dateien/x.pdf', PDF); z.writestr('dateien/x.docx', b'D'); z.writestr('dateien/b.png', open(FILES + '/Conceptmap.png', 'rb').read()); z.close()
    open(OUT + '/v1.zip', 'wb').write(zb.getvalue())
    with page.expect_file_chooser() as fc:
        page.click('[data-act=import]')
    fc.value.set_files(OUT + '/v1.zip')
    page.wait_for_selector('dialog#sheet[open]'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    d3 = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    j9 = [j for j in d3['faecher'][1]['jahrgaenge'] if j['name'] == '9'][0]
    ms = j9['reihen'][0]['vorhaben'][0]['materialien']
    check('Import v1: aufgeteilt in SuS + LK, Titelbild', sorted(m['bereich'] for m in ms) == ['lk', 'sus'] and j9['reihen'][0].get('titelbild'))

    # ---- SuS-Gerät ohne Token: Kursmodus + versteckter Rückweg ----
    page2 = ctx.new_page(); page2.on('dialog', lambda d: d.accept()); page2.on('pageerror', lambda e: errors.append(str(e)))
    page2.goto(SITE); page2.evaluate("localStorage.clear()")
    page2.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page2.reload()
    page2.wait_for_selector('#pad')
    check('Laptop: Sperrseite ohne GoodNotes-Tipp', page2.locator('#lock-tipp').count() == 0)
    for k in '1234': page2.click(f'#pad [data-k="{k}"]')
    page2.wait_for_selector('.rows', timeout=30000)
    check('SuS: kein Lehrkraft-Knopf', page2.locator('#kurs-exit').is_hidden())
    page2.goto(SITE); page2.wait_for_selector('.rows')
    check('SuS: Start merkt Kursansicht', '#/kurs/' in page2.url)
    for _ in range(5): page2.click('[data-kurs-pill]')
    page2.wait_for_selector('[data-act=leave-kurs]')
    page2.screenshot(path=f'{OUT}/09-sus-einstellungen.png')
    check('SuS: Einstellungen ohne Speicher', page2.locator('.tabs a').all_inner_texts() == ['Info', 'Zugang', 'Verwaltung'], page2.locator('.tabs a').all_inner_texts())
    page2.click('[data-act=leave-kurs]'); page2.wait_for_selector('.faecher')
    page2.goto(SITE); page2.wait_for_selector('.faecher')
    check('SuS: Kursmodus beendet', '#/kurs/' not in page2.url)


    # ================= A: Sammel-Upload (Ordnerstruktur wie am Laptop) =================
    import shutil
    base = OUT + '/GSQ/Schuljahr 2526/2526 M 6'
    shutil.rmtree(OUT + '/GSQ', ignore_errors=True)
    rd = base + '/M 6 Brüche'; os.makedirs(rd)
    names = ['M 6 Brüche - 1 Addition ungleichnamiger Brüche.docx', 'M 6 Brüche - 1 Addition ungleichnamiger Brüche.pdf',
             'M 6 Brüche - 2 AB Bruchrechnung Fehler.docx', 'M 6 Brüche - 2 Bruchrechnung Fehler.pdf', 'M 6 Brüche - 2 Fehler und unechte Brüche.docx',
             'M 6 Brüche - 5 AB Bruchrechnung.docx', 'M 6 Brüche - 5 Sachaufgaben Bruchrechnung.docx', 'Klausur Brüche.pdf', '~$temp.docx']
    for n in names: open(rd + '/' + n, 'wb').write((PDF if n.endswith('.pdf') else b'PK docx ') + n.encode())
    page.bring_to_front(); page2.close()
    # ================= iPad: Teilen statt Herunterladen =================
    ipad = br.new_context(service_workers='block', viewport={'width': 820, 'height': 1180}, has_touch=True,
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')
    ipad.route('https://api.github.com/**', gh_handler); ipad.route(SITE + '**', site_handler)
    ipad.add_init_script("""window.__geteilt = []; navigator.canShare = () => true;
      navigator.share = async d => { window.__geteilt.push((d.files || []).map(f => f.name).join(',') || d.url || ''); };""")
    pi = ipad.new_page(); pi.on('pageerror', lambda e: errors.append(str(e)))
    pi.goto(SITE + '#/kurs/physik/8/optische-instrumente'); pi.wait_for_selector('#pad')
    check('iPad: Sperrseite mit GoodNotes-Tipp', pi.locator('#lock-tipp').is_visible() and 'GoodNotes' in pi.inner_text('#lock-tipp'))
    for k in '1234': pi.click(f'#pad [data-k="{k}"]')
    pi.wait_for_selector('.rows', timeout=30000); time.sleep(0.4)
    fchip = pi.locator('.chip[data-slot=datei]').first
    if fchip.count():
        fchip.click(); pi.wait_for_selector('.viewer [data-v=share]:not([hidden])', timeout=20000)
        check('iPad: Viewer ohne Herunterladen, mit Teilen', pi.locator('.viewer [data-v=dl]').is_hidden() and pi.locator('.viewer [data-v=share]').is_visible())
        check('iPad: Teilen-Knopf hervorgehoben', 'teilen' in (pi.get_attribute('.viewer [data-v=share]', 'class') or ''))
        pi.click('.viewer [data-v=share]'); time.sleep(0.3)
        check('iPad: Teilen übergibt die Datei', len(pi.evaluate('window.__geteilt')) == 1 and '.' in pi.evaluate('window.__geteilt')[0], pi.evaluate('window.__geteilt'))
        pi.click('.viewer [data-v=close]'); time.sleep(0.4)
    else: check('iPad: Material in Kursansicht für Test', False)
    if pi.locator('[data-act=dl-reihe]').count():
        pi.click('[data-act=dl-reihe]'); pi.wait_for_selector('dialog#sheet[open] [data-x=teilen]', timeout=60000)
        pi.click('dialog#sheet [data-x=teilen]'); time.sleep(0.3)
        check('iPad: ZIP über Teilen', pi.evaluate('window.__geteilt')[-1].endswith('.zip'), pi.evaluate('window.__geteilt'))
    ipad.close()

    page.evaluate("localStorage.setItem('um-github', JSON.stringify({owner:'o', repo:'r', branch:'main', token:'x'}))")
    def open_sync_dir(path):
        page.goto(SITE + '#/einstellungen/verwaltung'); page.wait_for_selector('[data-act=sync]')
        page.click('[data-act=sync]'); page.wait_for_selector('dialog#sheet[open] [data-pick=dir]')
        with page.expect_file_chooser() as fc:
            page.click('[data-pick=dir]')
        fc.value.element.set_input_files(path)
        page.wait_for_selector('.sync-body .sync-box', timeout=30000); time.sleep(0.3)
    open_sync_dir(base)
    shot('11-sync-vorschau')
    grp = page.locator('.sync-box').nth(1)
    check('A: Reihe aus Ordner, Fach + Jahrgang erkannt', grp.locator('h3').inner_text() == 'M 6 Brüche' and page.input_value('select[data-k=fach]') == 'mathe'
          and page.input_value('input[data-k=jgnew]') == '6' and page.input_value('input[data-k=rtitel]') == 'Brüche',
          [grp.locator('h3').inner_text(), page.input_value('select[data-k=fach]')])
    vrows = grp.locator('table.sync').nth(0).locator('tbody tr')
    check('A: Vorhaben nach Nummer (1, 2, 5, ohne Nr.)', vrows.count() == 4 and 'Nr. 1' in vrows.nth(0).inner_text() and 'ohne Nr.' in vrows.nth(3).inner_text(), vrows.all_inner_texts())
    vt = [page.input_value('input[data-k=vtitel][data-v="%s"]' % k) for k in ['nr:1', 'nr:2', 'nr:5']]
    check('A: Vorhaben-Titel aus Dateien', vt == ['Addition ungleichnamiger Brüche', 'Bruchrechnung Fehler', 'Bruchrechnung'], vt)
    frows = grp.locator('table.sync').nth(1).locator('tbody tr')
    def rowinfo(i):
        r = frows.nth(i); return (r.locator('.fname').inner_text(), r.locator('select[data-k=typ]').input_value(), r.locator('select[data-k=bereich]').input_value(), r.locator('input[data-k=titel]').input_value())
    info = [rowinfo(i) for i in range(frows.count())]
    check('A: ~$-Datei ignoriert, 8 Dateien', frows.count() == 8, info)
    d_ = {x[0]: x for x in info}
    check('A: PDF+DOCX-Paar: PDF SuS, Word LK', d_['M 6 Brüche - 1 Addition ungleichnamiger Brüche.pdf'][2] == 'sus' and d_['M 6 Brüche - 1 Addition ungleichnamiger Brüche.docx'][2] == 'lk'
          and d_['M 6 Brüche - 1 Addition ungleichnamiger Brüche.docx'][3] == 'Addition ungleichnamiger Brüche', info)
    check('A: Klausur -> Prüfung/LK', d_['Klausur Brüche.pdf'][1] == 'pruefung' and d_['Klausur Brüche.pdf'][2] == 'lk', d_['Klausur Brüche.pdf'])
    check('A: Zähler', page.inner_text('[data-s=go]') == '8 hochladen', page.inner_text('[data-s=go]'))
    page.click('[data-s=go]'); wait_saved()
    d4 = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    mj = [j for j in d4['faecher'][0]['jahrgaenge'] if j['name'] == '6']
    rb = mj[0]['reihen'][0] if mj else None
    check('A: Mathe 6 / Brüche mit 4 Vorhaben, 8 Materialien', rb and rb['titel'] == 'Brüche' and rb.get('ordner') == 'M 6 Brüche' and len(rb['vorhaben']) == 4
          and sum(len(v['materialien']) for v in rb['vorhaben']) == 8 and all(m.get('hash') and m.get('quelle') for v in rb['vorhaben'] for m in v['materialien']),
          json.dumps(rb)[:600] if rb else d4)
    check('A: Seite springt zur neuen Reihe', '#/f/mathe/6/brueche' in page.url, page.url)
    shot('12-nach-sync')
    open_sync_dir(base)
    sts = page.locator('.sync-box').nth(1).locator('.st').all_inner_texts()
    check('A: Abgleich – alles unverändert', all(x == 'unverändert' for x in sts) and page.locator('[data-s=go]').is_disabled(), sts)
    page.click('[data-s=close]'); time.sleep(0.3)
    open(rd + '/M 6 Brüche - 2 Bruchrechnung Fehler.pdf', 'wb').write(PDF + b'% neu')
    alt = [m['datei']['pfad'] for v in rb['vorhaben'] for m in v['materialien'] if m['quelle'].endswith('2 Bruchrechnung Fehler.pdf')][0]
    open_sync_dir(base)
    sts = page.locator('.sync-box').nth(1).locator('.st').all_inner_texts()
    check('A: Abgleich – 1 geändert', sts.count('ersetzt alte Datei') == 1 and page.inner_text('[data-s=go]') == '1 hochladen', sts)
    page.click('[data-s=go]'); wait_saved()
    d5 = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    rb5 = [j for j in d5['faecher'][0]['jahrgaenge'] if j['name'] == '6'][0]['reihen'][0]
    neu = [m for v in rb5['vorhaben'] for m in v['materialien'] if m['quelle'].endswith('2 Bruchrechnung Fehler.pdf')]
    check('A: geänderte Datei ersetzt, alte gelöscht', len(neu) == 1 and neu[0]['datei']['pfad'] != alt and alt not in repo and sum(len(v['materialien']) for v in rb5['vorhaben']) == 8, (alt, neu))

    # ================= B =================
    page.goto(SITE + '#/f/mathe/6/brueche'); page.wait_for_selector('.rows')
    if not page.locator('body.editing').count():
        page.click('#edit-toggle'); page.wait_for_selector('body.editing')
    page.evaluate("""() => { const dt = new DataTransfer();
      dt.items.add(new File(['%PDF-1.4 a'], 'Übung A.pdf', {type:'application/pdf'})); dt.items.add(new File(['%PDF-1.4 b'], 'Übung A Lösung.pdf', {type:'application/pdf'}));
      const row = document.querySelectorAll('.row[data-v]')[0];
      row.dispatchEvent(new DragEvent('dragover', {bubbles:true, cancelable:true, dataTransfer:dt}));
      row.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:dt})); }""")
    page.wait_for_selector('.sync-body .sync-box', timeout=15000); time.sleep(0.3)
    check('B: Ablegen auf Zeile -> Vorschau ohne Schema, Ziel = Vorhaben 1', page.locator('input[data-schema]').count() == 0
          and page.locator('select[data-k=vt]').first.input_value() == rb5['vorhaben'][0]['id'], page.locator('select[data-k=vt]').first.input_value())
    check('B: Lösung erkannt', page.locator('table.sync').nth(1).locator('tbody tr', has_text='Übung A Lösung.pdf').locator('select[data-k=typ]').input_value() == 'loesung')
    shot('13-drop-vorschau')
    page.click('[data-s=go]'); wait_saved()
    d6 = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    v1 = [j for j in d6['faecher'][0]['jahrgaenge'] if j['name'] == '6'][0]['reihen'][0]['vorhaben'][0]
    check('B: 2 Dateien im Vorhaben 1', sum(1 for m in v1['materialien'] if m['titel'].startswith('Übung A')) == 2, [m['titel'] for m in v1['materialien']])
    page.goto(SITE + '#/f/mathe/6/brueche'); page.wait_for_selector('.rows')
    if not page.locator('body.editing').count():
        page.click('#edit-toggle'); page.wait_for_selector('body.editing')
    page.locator('.row').nth(1).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', [FILES + '/AB Spiegel-Parcours.pdf', FILES + '/AB Spiegel-Parcours.docx'])
    page.wait_for_selector('.sync-body .sync-box', timeout=15000)
    b2 = page.locator('table.sync').nth(1).locator('select[data-k=bereich]').all()
    check('B: Mehrfachauswahl im Dialog -> Vorschau mit Paar', len(b2) == 2 and sorted(x.input_value() for x in b2) == ['lk', 'sus'])
    page.click('[data-s=close]'); time.sleep(0.3)
    if page.locator('body.editing').count(): page.click('#edit-toggle'); time.sleep(0.3)


    # ================= HTML-Seiten: Brücke zur Oberfläche =================
    open(FILES + '/Camera Seite.html', 'w').write('''<!DOCTYPE html><html><head><title>Cam</title></head><body>
<p id="v"></p><button id="s" onclick="localStorage.setItem('x', String((+localStorage.getItem('x')||0)+1)); document.getElementById('v').textContent=localStorage.getItem('x')">+</button>
<a id="z" href="#zurueck">Zurück</a> <a id="w" href="#weiter">Weiter</a>
<script>document.getElementById('v').textContent = localStorage.getItem('x')||'0'; var sicher='nein'; try{ parent.localStorage.getItem('um-github'); }catch(e){ sicher='ja'; } document.body.setAttribute('data-sicher', sicher);</script></body></html>''')
    page.goto(SITE + '#/f/mathe/6/brueche'); page.wait_for_selector('.rows')
    if not page.locator('body.editing').count():
        page.click('#edit-toggle'); page.wait_for_selector('body.editing')
    page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/Camera Seite.html')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    page.click('#edit-toggle'); time.sleep(0.4)
    page.locator('.chip', has_text='Camera Seite').click()
    fr = page.frame_locator('.viewer iframe')
    fr.locator('#s').wait_for(timeout=10000)
    check('HTML: läuft abgeschottet (kein Zugriff auf Token/Schlüssel)', fr.locator('body').get_attribute('data-sicher') == 'ja')
    fr.locator('#s').click(); fr.locator('#s').click()
    check('HTML: localStorage funktioniert', fr.locator('#v').inner_text() == '2')
    check('HTML: Weiter-Knopf in der Leiste', page.locator('.viewer [data-v=next]').count() == 1)
    fr.locator('#z').click(); time.sleep(0.6)
    check('HTML: #zurueck schließt die Seite', page.locator('.viewer').count() == 0 and '#/f/mathe/6/brueche' in page.url)
    page.locator('.chip', has_text='Camera Seite').click()
    fr = page.frame_locator('.viewer iframe'); fr.locator('#s').wait_for(timeout=10000); time.sleep(0.3)
    check('HTML: Fortschritt bleibt gespeichert', fr.locator('#v').inner_text() == '2', fr.locator('#v').inner_text())
    fr.locator('#w').click(); time.sleep(1)
    t2 = page.locator('.viewer .viewer-bar b').inner_text() if page.locator('.viewer').count() else ''
    check('HTML: #weiter öffnet nächstes Material', page.locator('.viewer').count() == 1 and t2 and t2 != 'Camera Seite', t2)
    shot('17-weiter')
    page.go_back(); time.sleep(0.5)
    check('HTML: Zurück nach Weiter landet in der Reihe', page.locator('.viewer').count() == 0)


    # ================= Freischalten ab Datum, Hinweis, Checkliste, Suche, Camera, Vorlage =================
    import datetime
    morgen = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    gestern = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    R = '#/f/physik/8/optische-instrumente'
    def edit_on():
        if not page.locator('body.editing').count():
            page.click('#edit-toggle'); page.wait_for_selector('body.editing')
    def edit_off():
        if page.locator('body.editing').count(): page.click('#edit-toggle'); time.sleep(0.3)
    def pen(scope, text):   # Stift am Material (Bearbeiten-Modus) – Antippen des Chips öffnet das Material
        return scope.locator('.mwrap', has=page.locator('.chip', has_text=text)).first.locator('[data-act=edit-m]')
    def sus_ansicht():
        page.click('[data-act=share-r]'); page.wait_for_selector('dialog#sheet[open] [data-x=open]'); page.click('dialog#sheet [data-x=open]')
    page.goto(SITE + R); page.wait_for_selector('.rows'); edit_on()
    # Vorhaben 1 erst ab morgen
    page.locator('.row').nth(0).locator('[data-act=edit-v]').click(); page.wait_for_selector('dialog#sheet[open] input[name=ab]')
    page.fill('dialog#sheet input[name=ab]', morgen); page.click('dialog#sheet button[value=ok]'); wait_saved()
    check('Datum: Badge „für SuS ab“ in Lehrkraft-Ansicht', 'für SuS ab' in page.locator('.row').nth(0).inner_text())
    # Material in Vorhaben 2 (Linsen ist ausgeblendet) -> nimm die Camera-Zeile? Material „Erklärvideo“-Link ist ausgeblendet; nimm „AB Spiegel-Parcours“ (Vorhaben 1) – stattdessen neues Material in Vorhaben 2:
    page.locator('.row').nth(1).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/camera-obscura.html')
    page.fill('dialog#sheet input[name=ab]', gestern)
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    page.locator('.row').nth(1).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/AB Spiegel-Parcours.pdf')
    check('Ersetzen: gleicher Dateiname → Haken „ersetzen“ angeboten', page.is_visible('#ersetzen-row') and 'ersetzen' in page.inner_text('#ersetzen-row'))
    page.uncheck('dialog#sheet input[name=ersetzen]')
    page.fill('dialog#sheet input[name=titel]', 'Lösungsblatt später')
    page.select_option('dialog#sheet select[name=typ]', 'dokument')
    page.fill('dialog#sheet input[name=ab]', morgen)
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    check('Datum: Material-Chip zeigt „ab …“', page.locator('.row').nth(1).locator('.chip.aus', has_text='Lösungsblatt später').count() == 1)
    # Vorhaben 2 einblenden (war ausgeblendet), damit Kursansicht es zeigt
    page.locator('.row').nth(1).locator('[data-act=vis-v]').click(); wait_saved()
    # Hinweis
    page.click('[data-act=edit-hinweis]'); page.wait_for_selector('dialog#sheet[open] textarea[name=text]')
    page.fill('dialog#sheet textarea[name=text]', 'Test am Freitag: Spiegel und Schatten'); page.fill('dialog#sheet input[name=bis]', morgen)
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    # Checkliste aus Word-Datei
    import zipfile as _zf
    dx = FILES + '/Checkliste.docx'
    with _zf.ZipFile(dx, 'w', _zf.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<w:document><w:body><w:p><w:r><w:t># Licht</w:t></w:r></w:p><w:p><w:r><w:t>Ich kann erklären, </w:t></w:r><w:r><w:t xml:space="preserve">wie wir sehen.</w:t></w:r></w:p><w:p></w:p><w:p><w:r><w:t>• Ich kann den Strahlengang zeichnen &amp; beschriften.</w:t></w:r></w:p></w:body></w:document>')
    page.click('[data-act=edit-check]'); page.wait_for_selector('dialog#sheet[open] textarea[name=liste]')
    with page.expect_file_chooser() as fc:
        page.click('dialog#sheet [data-x=datei]')
    fc.value.set_files(dx); time.sleep(0.8)
    lv = page.input_value('dialog#sheet textarea[name=liste]')
    check('Checkliste: aus Word übernommen', lv.split('\n')[:2] == ['# Licht', 'Ich kann erklären, wie wir sehen.'] and '&' in lv, lv)
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    edit_off()
    shot('18-lehrkraft-hinweis-checkliste')
    # Kursansicht
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.4)
    txt = page.inner_text('main')
    vt = page.locator('.row-title b').all_inner_texts()
    check('Datum: Vorhaben ab morgen in Kursansicht unsichtbar', 'Camera obscura' not in vt and 'Linsen' in vt, vt)
    check('Datum: Material ab morgen unsichtbar, ab gestern sichtbar', 'Lösungsblatt später' not in txt and 'camera-obscura' in txt, txt[:400])
    check('Hinweis in Kursansicht', page.locator('.hinweis').count() == 1 and 'Test am Freitag' in page.inner_text('.hinweis'))
    check('Checkliste in Kursansicht', page.locator('details.checkbox').count() == 1)
    page.click('details.checkbox > summary'); time.sleep(0.2)
    b = page.locator('.ck').first; b.click(); b.click()
    check('Checkliste: zweimal tippen = sicher, Zähler', 'sicher' in b.get_attribute('class') and page.inner_text('[data-checkcount]') == '1 / 2 sicher', page.inner_text('[data-checkcount]'))
    page.reload(); page.wait_for_selector('details.checkbox')
    check('Checkliste: bleibt gespeichert und offen', page.locator('details.checkbox[open]').count() == 1 and 'sicher' in page.locator('.ck').first.get_attribute('class'))
    shot('19-kurs-hinweis-checkliste')
    # Camera-Seite in der App
    page.locator('.chip', has_text='camera-obscura').first.click()
    fr = page.frame_locator('.viewer iframe'); fr.locator('h1').first.wait_for(timeout=15000)
    fr.locator('a.step[data-page=bauen]').click(); time.sleep(0.4)
    check('Camera: Schritt-Navigation funktioniert in der App', fr.locator('#bauen').is_visible() and not fr.locator('#auftrag').is_visible())
    check('Camera: „‹ Übersicht“ sichtbar', fr.locator('.bar .home').is_visible())
    shot('20-camera-in-app')
    fr.locator('.bar .home').click(); time.sleep(0.5)
    check('Camera: „‹ Übersicht“ führt zurück', page.locator('.viewer').count() == 0)
    # Abgelaufener Hinweis verschwindet
    page.goto(SITE + R); page.wait_for_selector('.rows'); edit_on()
    page.click('.hinweis [data-act=edit-hinweis]'); page.wait_for_selector('dialog#sheet[open] input[name=bis]')
    page.fill('dialog#sheet input[name=bis]', gestern); page.click('dialog#sheet button[value=ok]'); wait_saved()
    edit_off()
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)
    check('Hinweis: nach Ablauf nicht mehr sichtbar', page.locator('.hinweis').count() == 0)
    page.click('#kurs-exit'); page.wait_for_selector('.crumbs')
    # Suche
    page.click('#search-btn'); page.wait_for_selector('#such-feld')
    page.fill('#such-feld', 'lena'); time.sleep(0.3)
    check('Suche: findet Material „Nachricht an Lena“', page.locator('#such-treffer .chip', has_text='Nachricht an Lena').count() >= 1)
    page.fill('#such-feld', 'bruche'); time.sleep(0.3)
    check('Suche: ohne Umlaute („bruche“ → Brüche)', 'Brüche' in page.inner_text('#such-treffer'))
    shot('21-suche')
    page.locator('#such-treffer a.ziel').first.click(); page.wait_for_selector('.rows')
    check('Suche: Treffer führt zur Reihe', '#/f/mathe/6/brueche' in page.url, page.url)
    # Vorlage: herunterladbar und in der App lauffähig
    page.goto(SITE + '#/einstellungen/verwaltung'); page.wait_for_selector('[data-act=vorlage]')
    with page.expect_download() as dl:
        page.click('[data-act=vorlage][data-typ=lernpfad]')
    vp = OUT + '/vorlage.html'; dl.value.save_as(vp)
    vtxt = open(vp, encoding='utf-8').read()
    check('Vorlage: Download', 'data-quiz' in vtxt)
    check('Vorlage: schmale Kopfzeile mit Pfad, ohne externe Ressourcen', 'class="pfad"' in vtxt and 'fonts.googleapis' not in vtxt and '<script src=' not in vtxt)
    with page.expect_download() as dl2:
        page.click('[data-act=vorlage][data-typ=simulation]')
    sp = OUT + '/vorlage-sim.html'; dl2.value.save_as(sp)
    stxt = open(sp, encoding='utf-8').read()
    check('Vorlage Simulation: Download', 'data-weiter-schritt' in stxt and 'class="pfad"' in stxt and 'Vorlage Simulation' in dl2.value.suggested_filename)
    _sh2 = __import__('shutil'); _sh2.copy(sp, FILES + '/Vorlage Sim.html')
    import shutil as _sh; _sh.copy(vp, FILES + '/Vorlage Seite.html')
    page.goto(SITE + R); page.wait_for_selector('.rows'); edit_on()
    page.locator('.row').nth(1).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/Vorlage Seite.html')
    page.click('dialog#sheet button[value=ok]'); wait_saved(); edit_off()
    page.locator('.chip', has_text='Vorlage Seite').click()
    fr = page.frame_locator('.viewer iframe'); fr.locator('h1').first.wait_for(timeout=10000)
    check('Vorlage: Pfad mit Rückpfeil in der App', fr.locator('.pfad .zur').is_visible())
    fr.locator('.punkte a[data-page=aufgaben]').click(); time.sleep(0.3)
    fr.locator('[data-quiz] button').nth(1).click()
    check('Vorlage: Quiz gibt Rückmeldung', 'richtig' in (fr.locator('[data-quiz] button').nth(1).get_attribute('class') or ''))
    fr.locator('.punkte a[data-page=sichern]').click(); time.sleep(0.3)
    fr.locator('textarea[data-antwort]').fill('Meine Antwort'); time.sleep(0.8)
    fr.locator('.fertig:visible').first.click(); time.sleep(0.6)
    check('Vorlage: Fertig-Knopf verlässt die Seite', page.locator('.viewer').count() == 0 or 'Vorlage Seite' not in page.inner_text('.viewer .viewer-bar b'))
    if page.locator('.viewer').count(): page.go_back(); time.sleep(0.4)
    page.locator('.chip', has_text='Vorlage Seite').click()
    fr = page.frame_locator('.viewer iframe'); fr.locator('h1').first.wait_for(timeout=10000)
    fr.locator('.punkte a[data-page=sichern]').click(); time.sleep(0.3)
    check('Vorlage: Antwort bleibt gespeichert', fr.locator('textarea[data-antwort]').input_value() == 'Meine Antwort')
    shot('22-vorlage')
    page.go_back(); time.sleep(0.4)
    # Simulations-Vorlage: ein Bildschirm, Schritte, Pfad führt zurück
    page.goto(SITE + R); page.wait_for_selector('.rows'); edit_on()
    page.locator('.row').nth(1).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/Vorlage Sim.html')
    page.click('dialog#sheet button[value=ok]'); wait_saved(); edit_off()
    page.locator('.chip', has_text='Vorlage Sim').click()
    fr = page.frame_locator('.viewer iframe'); fr.locator('.pfad').wait_for(timeout=10000)
    check('Simulation: Steuerleiste sichtbar ohne Scrollen', fr.locator('.leiste').evaluate('e => e.getBoundingClientRect().bottom <= window.innerHeight + 1'))
    check('Simulation: Schritt-2-Elemente zunächst verborgen', not fr.locator('#eintragen').is_visible())
    fr.locator('[data-weiter-schritt]').click(); time.sleep(0.2)
    check('Simulation: Weiter wechselt zu Schritt 2', fr.locator('#eintragen').is_visible() and fr.locator('.punkte button[data-s="2"]').get_attribute('aria-current') == 'step')
    shot('22b-vorlage-simulation')
    fr.locator('.pfad').click(); time.sleep(0.6)
    check('Simulation: Pfad oben führt zurück zur Reihe', page.locator('.viewer').count() == 0 or 'Vorlage Sim' not in page.inner_text('.viewer .viewer-bar b'))
    if page.locator('.viewer').count(): page.go_back(); time.sleep(0.4)

    # ================= D: Notizen pro Vorhaben + Niveau =================
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.4)
    if page.locator('body.editing').count() == 0: page.click('#edit-toggle'); page.wait_for_selector('body.editing')
    row0 = page.locator('.row').nth(0)
    row0.locator('[data-act=notiz-v]').click(); page.wait_for_selector('dialog#sheet[open] textarea[name=ziel]')
    page.fill('textarea[name=ziel]', 'SuS erklären die Bildentstehung'); page.fill('textarea[name=verlauf]', 'Einstieg\nErarbeitung\nSicherung')
    page.fill('textarea[name=reflexion]', 'Gruppenphase lief gut')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    d = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    v0 = [x for x in d['faecher'][1]['jahrgaenge'][0]['reihen'] if x['id'] == 'optische-instrumente'][0]['vorhaben'][0]
    check('D: Notizen gespeichert (Ziel, Verlauf, Reflexion)', v0.get('planung') == {'ziel': 'SuS erklären die Bildentstehung', 'verlauf': 'Einstieg\nErarbeitung\nSicherung', 'reflexion': 'Gruppenphase lief gut'}, v0.get('planung'))
    pen(page.locator('.row').nth(0).locator('.row-main > .chips'), 'Nachricht an Lena').click()
    page.wait_for_selector('dialog#sheet[open] select[name=niveau]')
    page.select_option('select[name=niveau]', '2'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    pen(page.locator('.row').nth(0), 'AB Spiegel-Parcours').click()
    page.wait_for_selector('dialog#sheet[open] select[name=niveau]')
    check('D: Niveau-Auswahl im Dialog (ohne/Basis/Standard/Erweiterung)', page.locator('select[name=niveau] option').count() == 4 and page.input_value('select[name=niveau]') == '')
    page.select_option('select[name=niveau]', '3'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    d = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    ms0 = [x for x in d['faecher'][1]['jahrgaenge'][0]['reihen'] if x['id'] == 'optische-instrumente'][0]['vorhaben'][0]['materialien']
    check('D: Niveau gespeichert', sorted((m['titel'], m.get('niveau')) for m in ms0 if m.get('niveau')) == [('AB Spiegel-Parcours', 3), ('Nachricht an Lena', 2)], [(m['titel'], m.get('niveau')) for m in ms0])
    pen(page.locator('.row').nth(1), 'AB Linsen').click()   # Vorhaben 2 ist in der Kursansicht sichtbar
    page.wait_for_selector('dialog#sheet[open] select[name=niveau]'); page.select_option('select[name=niveau]', '1'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    page.click('#edit-toggle'); time.sleep(0.4)
    row0 = page.locator('.row').nth(0)
    check('D: Sterne am Chip', '★★' in row0.locator('.chip', has_text='Nachricht an Lena').first.inner_text() and '★★★' in row0.locator('.chip', has_text='AB Spiegel-Parcours').first.inner_text())
    tg = row0.locator('.lk-toggle')
    check('D: LK-Bereich nennt Notizen', 'Notizen' in tg.inner_text(), tg.inner_text())
    if tg.get_attribute('aria-expanded') != 'true': tg.click(); time.sleep(0.2)
    check('D: Notizen im LK-Bereich sichtbar', 'Gruppenphase lief gut' in row0.locator('.lk-notizen').inner_text() and 'Schwerpunktziel' in row0.locator('.lk-notizen').inner_text())
    shot('23-notizen-niveau')
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.5)
    txt = page.inner_text('main')
    check('D: Kurs ohne Notizen', 'Gruppenphase' not in txt and 'Bildentstehung' not in txt and 'Notizen' not in txt)
    check('D: Kurs mit Sternen, ohne Legende', '★' in page.locator('.chip', has_text='AB Linsen').inner_text() and 'Erweiterung' not in txt)
    shot('24-kurs-niveau')
    page.click('#kurs-exit'); page.wait_for_selector('.crumbs')
    page.goto(SITE + '#/suche'); page.wait_for_selector('#such-feld'); page.fill('#such-feld', 'Gruppenphase'); time.sleep(0.6)
    check('D: Suche findet Notizen (Lehrkraft)', 'Spiegel' in page.inner_text('#such-treffer') or page.locator('#such-treffer .chip, #such-treffer a').count() > 0, page.inner_text('#such-treffer')[:200])

    # ================= E: Parallelkurse + neues Schuljahr =================
    def data_now(): return page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    def reihe(d, rid='optische-instrumente'): return [x for x in d['faecher'][1]['jahrgaenge'][0]['reihen'] if x['id'] == rid][0]
    def stand_items(r): return [v for v in r['vorhaben']] + [m for v in r['vorhaben'] for m in v['materialien'] if m['bereich'] != 'lk']
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)
    if 'editing' not in (page.get_attribute('body', 'class') or ''): page.click('#edit-toggle'); time.sleep(0.3)
    page.click('.btnline [data-act=add-k]'); page.wait_for_selector('dialog#sheet[open] input[name=name]')
    page.fill('input[name=name]', '8a'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    page.click('.kursbar [data-act=add-k]'); page.wait_for_selector('dialog#sheet[open] input[name=name]')
    page.fill('input[name=name]', '8b'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    d = data_now(); r = reihe(d)
    check('E: zwei Parallelkurse angelegt', [k['id'] for k in r.get('kurse', [])] == ['8a', '8b'], r.get('kurse'))
    check('E: Kurse übernehmen aktuellen Stand', all(x.get('kurse', {}).get('8b', {}).get('ausgeblendet') == bool(x.get('ausgeblendet')) for x in stand_items(r)))
    check('E: Kursleiste mit Standard/8a/8b, 8b gewählt', page.locator('.kursbar .kchip.on').inner_text().strip() == '8b' and page.locator('.kursbar [data-act=kurs-wahl]').count() == 3)
    # 8b: Vorhaben 2 ausblenden, eigener Hinweis
    page.locator('.row').nth(1).locator('[data-act=vis-v]').click(); wait_saved()
    page.click('[data-act=edit-hinweis][data-k="8b"]'); page.wait_for_selector('dialog#sheet[open] textarea[name=text]')
    page.fill('textarea[name=text]', 'Test 8b am Montag'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    # 8a: Vorhaben 2 erst ab 2099
    page.click('.kursbar [data-act=kurs-wahl][data-k="8a"]'); time.sleep(0.3)
    check('E: Hinweis zeigt Kurs-Hinweis nur bei gewähltem Kurs', 'Test 8b am Montag' not in page.inner_text('main'))
    page.locator('.row').nth(1).locator('[data-act=edit-v]').click(); page.wait_for_selector('dialog#sheet[open] input[name=ab]')
    check('E: Termin-Feld nennt den Kurs', 'nur 8a' in page.inner_text('dialog#sheet'))
    page.fill('input[name=ab]', '2099-01-01'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    d = data_now(); r = reihe(d); v1 = r['vorhaben'][1]
    check('E: Stand pro Kurs gespeichert', v1['kurse']['8b']['ausgeblendet'] is True and v1['kurse']['8a'].get('ab') == '2099-01-01' and not v1.get('ausgeblendet') and not v1.get('ab'), (v1.get('kurse'), v1.get('ausgeblendet'), v1.get('ab')))
    check('E: Kurs-Hinweis gespeichert', [k.get('hinweis', {}).get('text') for k in r['kurse']] == [None, 'Test 8b am Montag'])
    page.locator('.row').nth(1).locator('.row-main > .chips [data-act=edit-m]').first.click(); page.wait_for_selector('dialog#sheet[open] input[name=sichtbar]')
    check('E: Material-Dialog nennt den Kurs', 'nur 8a' in page.inner_text('dialog#sheet'))
    page.keyboard.press('Escape'); time.sleep(0.3)
    page.click('[data-act=share-r]'); page.wait_for_selector('dialog#sheet[open] .linkbox')
    check('E: Teilen-Link pro Kurs', page.inner_text('.linkbox').strip().endswith('#/kurs/physik/8/optische-instrumente/8a'), page.inner_text('.linkbox'))
    page.click('dialog#sheet button[value=ok]'); time.sleep(0.3)
    shot('25-parallelkurse')
    t1 = v1['titel']
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente/8b'); page.wait_for_selector('.rows'); time.sleep(0.4); txt = page.inner_text('main')
    check('E: Kursansicht 8b: eigenes Tempo + eigener Hinweis', t1 not in txt and 'Test 8b am Montag' in txt and '8b' in page.inner_text('[data-kurs-pill]'))
    shot('26-kurs-8b')
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente/8a'); page.wait_for_selector('.rows'); time.sleep(0.4); txt = page.inner_text('main')
    check('E: Kursansicht 8a: Termin greift, kein 8b-Hinweis', t1 not in txt and 'Test 8b' not in txt)
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.4); txt = page.inner_text('main')
    check('E: Standard-Link unverändert', t1 in txt and 'Test 8b' not in txt)
    page.click('#kurs-exit'); page.wait_for_selector('.crumbs')

    # Neues Schuljahr: Kopie in denselben Jahrgang
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)
    if 'editing' not in (page.get_attribute('body', 'class') or ''): page.click('#edit-toggle'); time.sleep(0.3)
    files_orig = set(paths_of(reihe(data_now())))
    page.click('[data-act=neu-r]'); page.wait_for_selector('dialog#sheet[open] select[name=ziel]')
    check('E: Schuljahr-Dialog mit Ziel + Optionen', page.locator('select[name=ziel] option[value="physik|8"]').count() == 1 and page.is_checked('input[name=kurse]') and page.is_checked('input[name=aus]'))
    page.select_option('select[name=ziel]', 'physik|8'); page.click('dialog#sheet button[value=ok]'); wait_saved(); time.sleep(0.4)
    d = data_now(); rs = d['faecher'][1]['jahrgaenge'][0]['reihen']; orig = reihe(d)
    cp = [x for x in rs if x['titel'].endswith('(Kopie)')]
    check('E: Kopie angelegt und geöffnet', len(cp) == 1 and page.url.endswith('/' + cp[0]['id']), page.url)
    cp = cp[0] if cp else {'vorhaben': []}
    check('E: Kopie: alles ausgeblendet, keine Termine/Hinweise/Kurse', all(v.get('ausgeblendet') for v in cp['vorhaben']) and not any(x.get('ab') or x.get('kurse') for x in stand_items(cp)) and not cp.get('hinweis') and not cp.get('kurse'))
    check('E: Kopie: Lösungen ausgeblendet, Notizen/Niveau bleiben', all(m.get('ausgeblendet') for v in cp['vorhaben'] for m in v['materialien'] if m['typ'] == 'loesung' and m['bereich'] == 'sus')
          and [json.dumps(v.get('planung')) for v in cp['vorhaben']] == [json.dumps(v.get('planung')) for v in orig['vorhaben']])
    check('E: Kopie nutzt dieselben Dateien, neue IDs', set(paths_of(cp)) == files_orig and not ({m['id'] for v in cp['vorhaben'] for m in v['materialien']} & {m['id'] for v in orig['vorhaben'] for m in v['materialien']}))
    check('E: Original unverändert', [k['id'] for k in orig.get('kurse', [])] == ['8a', '8b'] and orig['vorhaben'][1]['kurse']['8a'].get('ab') == '2099-01-01')
    page.click('[data-act=del-r]'); wait_saved(); time.sleep(0.4)
    check('E: Kopie gelöscht, gemeinsame Dateien bleiben', all(f in repo for f in files_orig), sorted(f for f in files_orig if f not in repo))
    # Zurücksetzen an Ort und Stelle, Kurse behalten
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)
    page.click('[data-act=neu-r]'); page.wait_for_selector('dialog#sheet[open] select[name=ziel]')
    page.uncheck('input[name=kurse]'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    r = reihe(data_now())
    check('E: Zurücksetzen mit Kursen: alles aus, Termine + Hinweise weg', [k['id'] for k in r.get('kurse', [])] == ['8a', '8b'] and not any(k.get('hinweis') for k in r['kurse'])
          and all(v.get('ausgeblendet') and all(z.get('ausgeblendet') for z in v.get('kurse', {}).values()) for v in r['vorhaben'])
          and not any(x.get('ab') or any(z.get('ab') for z in x.get('kurse', {}).values()) for x in stand_items(r)) and not r.get('hinweis'))
    # 8b für die Sicherung wieder etwas freischalten
    page.click('.kursbar [data-act=kurs-wahl][data-k="8b"]'); time.sleep(0.3)
    page.locator('.row').nth(0).locator('[data-act=vis-v]').click(); wait_saved()
    page.click('.kursbar [data-act=kurs-wahl]:not([data-k])'); time.sleep(0.2)
    page.click('#edit-toggle'); time.sleep(0.3)
    # Hinweis/Termine für die Sicherungs-Prüfung wieder setzen (wurden eben zurückgesetzt)
    page.evaluate("""async () => { const K = await T.keys('1234','pruefung123'); const d = await T.getData(K);
      const r = d.faecher[1].jahrgaenge[0].reihen.find(x => x.id === 'optische-instrumente');
      r.hinweis = { text:'Test am Freitag', bis:'2099-12-31' }; r.vorhaben[1].ab = '2099-02-01';
      const m = r.vorhaben[1].materialien.find(x => x.bereich === 'sus'); m.ab = '2099-02-02'; await T.putData(K, d); }""")

    # ================= F: Fach NW + Sonstiges (Lehrplan-Vorlagen), Reihe im Bearbeitungsmodus öffnen =================
    page.goto(SITE + '#/'); page.reload(); page.wait_for_selector('.fach'); time.sleep(0.3)
    if 'editing' not in (page.get_attribute('body', 'class') or ''): page.click('#edit-toggle'); page.wait_for_selector('body.editing')
    page.click('[data-act=add-f]'); page.wait_for_selector('dialog#sheet[open] input[name=name]')
    check('F: Fach-Dialog mit Vorlage-Auswahl', page.locator('dialog#sheet select[name=vorlage] option[value=nw]').count() == 1)
    page.fill('dialog#sheet input[name=name]', 'NW'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    nw = [f for f in data_now()['faecher'] if f['name'] == 'NW']
    check('F: NW angelegt mit Vorlage nw', len(nw) == 1 and nw[0].get('vorlage') == 'nw', nw)
    nwid = nw[0]['id'] if nw else 'nw'
    check('F: NW hat eigenes Symbol', 'M9.5 3h5' in page.inner_html('.fach:has(h2:text-is("NW")) .fach-icon'))
    page.click(f'[data-act=add-j][data-f="{nwid}"]'); page.wait_for_selector('dialog#sheet[open] input[name=name]')
    page.fill('dialog#sheet input[name=name]', '6'); page.click('dialog#sheet button[value=ok]')
    page.wait_for_selector('dialog#sheet[open] .checklist, dialog#sheet[open] input[type=checkbox]'); time.sleep(0.3)
    txt = page.inner_text('dialog#sheet')
    check('F: KLP-Vorschläge NW 5/6', 'Sinne und Wahrnehmung' in txt and 'Stoffe im Alltag' in txt and 'Körper und Bewegung' in txt, txt[:200])
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    j6 = [f for f in data_now()['faecher'] if f['id'] == nwid][0]['jahrgaenge'][0]
    check('F: NW 6 mit 10 Reihen', j6['name'] == '6' and len(j6['reihen']) == 10, len(j6['reihen']))
    page.goto(SITE + f'#/f/{nwid}/{j6["id"]}'); page.wait_for_selector('.reihe-card'); time.sleep(0.3)
    check('F: Bearbeitungsmodus aktiv, Werkzeuge sichtbar', 'editing' in (page.get_attribute('body', 'class') or '') and page.locator('.reihe-card [data-act=edit-r]').count() == 10)
    page.locator('.reihe-card').nth(0).locator('.reihe-nr').click(); page.wait_for_selector('.rows, .empty-state', timeout=5000); time.sleep(0.3)
    check('F: Reihe im Bearbeitungsmodus öffnen', page.url.endswith('/' + j6['reihen'][0]['id']) and 'editing' in (page.get_attribute('body', 'class') or ''), page.url)
    page.goto(SITE + f'#/f/{nwid}/{j6["id"]}'); page.wait_for_selector('.reihe-card'); time.sleep(0.3)
    page.locator('.reihe-card').nth(1).locator('[data-act=edit-r]').click(); page.wait_for_selector('dialog#sheet[open]')
    check('F: Stift in der Karte öffnet Dialog statt Reihe', page.url.endswith(f'/f/{nwid}/{j6["id"]}'), page.url)
    page.keyboard.press('Escape'); time.sleep(0.3)
    page.goto(SITE + '#/'); page.wait_for_selector('.fach'); time.sleep(0.3)
    page.click('[data-act=add-f]'); page.wait_for_selector('dialog#sheet[open] input[name=name]')
    page.fill('dialog#sheet input[name=name]', 'Sonstiges'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    so = [f for f in data_now()['faecher'] if f['name'] == 'Sonstiges'][0]
    check('F: Sonstiges mit Vorlage klasse + Symbol', so.get('vorlage') == 'klasse' and 'cx="17"' in page.inner_html('.fach:has(h2:text-is("Sonstiges")) .fach-icon'), so)
    page.click(f'[data-act=add-j][data-f="{so["id"]}"]'); page.wait_for_selector('dialog#sheet[open] input[name=name]')
    page.fill('dialog#sheet input[name=name]', '6'); page.click('dialog#sheet button[value=ok]')
    page.wait_for_selector('dialog#sheet[open] .checklist'); time.sleep(0.3)
    txt = page.inner_text('dialog#sheet'); bo = page.locator('dialog#sheet .checklist label:has-text("Berufsorientierung") input')
    check('F: Klassenleitungs-Vorschläge (BO erst ab 8 abgewählt)', 'Klassenrat' in txt and bo.count() == 1 and not bo.is_checked(), txt[:150])
    page.click('dialog#sheet button[value=cancel]'); time.sleep(0.3)
    page.click(f'[data-act=edit-f][data-f="{nwid}"]'); page.wait_for_selector('dialog#sheet[open] select[name=vorlage]')
    check('F: Fach bearbeiten zeigt gespeicherte Vorlage', page.eval_on_selector('dialog#sheet select[name=vorlage]', 'e => e.value') == 'nw')
    page.select_option('dialog#sheet select[name=vorlage]', 'keine'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    check('F: Vorlage „keine“ → Buch-Symbol', [f for f in data_now()['faecher'] if f['id'] == nwid][0].get('vorlage') == 'keine' and 'M9.5 3h5' not in page.inner_html(f'.fach:has(h2:text-is("NW")) .fach-icon'))
    page.click(f'[data-act=edit-f][data-f="{nwid}"]'); page.wait_for_selector('dialog#sheet[open] select[name=vorlage]')
    page.select_option('dialog#sheet select[name=vorlage]', 'nw'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    shot('27-nw-sonstiges')
    page.click('#edit-toggle'); time.sleep(0.3)

    # ================= E: Aufgeräumt + Einstellungen in Kategorien =================
    page.goto(SITE + '#/einstellungen'); page.wait_for_selector('.tabs')
    tabs = page.locator('.tabs a').all_inner_texts()
    check('E: Einstellungen-Kategorien', tabs == ['Info', 'Zugang', 'Verwaltung', 'Speicher'] and page.locator('.tabs a.on').inner_text() == 'Zugang', tabs)
    check('E: Zugang ohne Verwaltung/Speicher', page.locator('#cfg-form').count() == 1 and page.locator('[data-act=sync]').count() == 0 and page.locator('.store-list').count() == 0)
    page.click('.tabs a[data-tab=info]'); page.wait_for_selector('.info-list')
    check('E: Info in wenigen Gruppen', 4 <= page.locator('.info-list > details').count() <= 8 and page.locator('.info-list dt').count() >= 20)
    page.locator('.info-list > details > summary', has_text='Im Unterricht').click(); time.sleep(0.2)
    check('E: Info-Gruppe aufklappbar mit Fragen', page.locator('.info-list details[open] dt', has_text='QR-Code').count() == 1)
    shot('25-einstellungen-info')
    page.click('.tabs a[data-tab=verwaltung]'); page.wait_for_selector('[data-act=sync]')
    check('E: Verwaltung', page.locator('[data-act=export-all]').count() == 1 and page.locator('[data-act=vorlage]').count() == 2 and page.locator('#cfg-form').count() == 0)
    shot('26-einstellungen-verwaltung')
    check('E: Zahnrad-Symbol', 'M19.4 15' in page.inner_html('#settings-link'))
    page.goto(SITE + '#/suche'); page.wait_for_selector('#such-feld'); page.fill('#such-feld', ''); time.sleep(0.3)
    check('E: Suche ohne Erklärtext', page.inner_text('#such-treffer').strip() == '' and page.locator('.page-head .sub').count() == 0)
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)
    check('E: Keine Niveau-Legende', 'Erweiterung' not in page.inner_text('main'))

    # ================= Verschieben per Ziehen =================
    def getd(): return page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    def reihe_of(d, rid='optische-instrumente'):
        for f in d['faecher']:
            for j in f['jahrgaenge']:
                for r in j['reihen']:
                    if r['id'] == rid: return r
    def ziehe(src, dst, oben=True, dx=0):
        dst.scroll_into_view_if_needed(); src.scroll_into_view_if_needed(); time.sleep(0.1)
        a = src.bounding_box(); b = dst.bounding_box()
        page.mouse.move(a['x'] + a['width'] / 2, a['y'] + a['height'] / 2); page.mouse.down()
        ty = b['y'] + (4 if oben else b['height'] - 4); tx = (b['x'] + 6 if oben else b['x'] + b['width'] - 6) if dx else b['x'] + b['width'] / 2
        for i in range(1, 13): page.mouse.move(a['x'] + a['width'] / 2 + (tx - a['x'] - a['width'] / 2) * i / 12, a['y'] + a['height'] / 2 + (ty - a['y'] - a['height'] / 2) * i / 12); time.sleep(0.03)
        # Ziel kann sich verschoben haben (Quelle wurde kleiner) → wie ein Mensch nachführen
        time.sleep(0.1); b2 = dst.bounding_box()
        if b2 and abs(b2['y'] - b['y']) > 2:
            ty = b2['y'] + (4 if oben else b2['height'] - 4); tx = (b2['x'] + 6 if oben else b2['x'] + b2['width'] - 6) if dx else b2['x'] + b2['width'] / 2
            page.mouse.move(tx, ty + 1); time.sleep(0.05); page.mouse.move(tx, ty); time.sleep(0.05)
        time.sleep(0.15); page.mouse.up()
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    check('Ziehen: Griff statt Pfeile', page.locator('.row [data-act=up-v]').count() == 0 and page.locator('.row .grip').count() >= 2)
    vor = [v['id'] for v in reihe_of(getd())['vorhaben']]
    n = len(vor)
    ziehe(page.locator('.row[data-sort-item]').nth(n - 1).locator('.grip'), page.locator('.row[data-sort-item]').nth(0), oben=True)
    wait_saved()
    nach = [v['id'] for v in reihe_of(getd())['vorhaben']]
    check('Ziehen: letztes Vorhaben nach ganz oben', nach == [vor[-1]] + vor[:-1], (vor, nach))
    check('Ziehen: Nummern neu', page.locator('.row[data-sort-item] .nr').first.inner_text().strip() == '1' and page.locator('.row[data-sort-item]').nth(0).get_attribute('data-v') == vor[-1])
    # Tastatur am Griff
    page.locator('.row[data-sort-item]').nth(0).locator('.grip').focus(); page.keyboard.press('ArrowDown'); wait_saved()
    nach2 = [v['id'] for v in reihe_of(getd())['vorhaben']]
    check('Ziehen: Pfeiltaste am Griff', nach2 == [nach[1], nach[0]] + nach[2:], nach2)
    # Material innerhalb eines Vorhabens (SuS-Bereich), LK-Material bleibt an seinem Platz
    d = getd(); vi = next(i for i, v in enumerate(reihe_of(d)['vorhaben']) if sum(1 for m in v['materialien'] if m['bereich'] != 'lk') >= 2)
    v = reihe_of(d)['vorhaben'][vi]; sus0 = [m['id'] for m in v['materialien'] if m['bereich'] != 'lk']; lkpos0 = [(i, m['id']) for i, m in enumerate(v['materialien']) if m['bereich'] == 'lk']
    row = page.locator('.row[data-sort-item]').nth(vi); chips = row.locator('[data-sort=m][data-bereich=sus] > [data-sort-item]')
    ziehe(chips.nth(chips.count() - 1).locator('.chip'), chips.nth(0), oben=True, dx=1); wait_saved()
    v2 = reihe_of(getd())['vorhaben'][vi]; sus1 = [m['id'] for m in v2['materialien'] if m['bereich'] != 'lk']
    check('Ziehen: Material nach vorne', sus1 == [sus0[-1]] + sus0[:-1], (sus0, sus1))
    check('Ziehen: Lehrkraft-Material unverändert', [(i, m['id']) for i, m in enumerate(v2['materialien']) if m['bereich'] == 'lk'] == lkpos0)
    check('Ziehen: kein Dialog nach dem Ziehen', page.locator('dialog#sheet[open]').count() == 0)
    page.locator('.row[data-sort-item]').nth(vi).locator('[data-sort=m] [data-act=edit-m]').first.click(); page.wait_for_selector('dialog#sheet[open]')
    check('Ziehen: Stift öffnet weiter den Dialog', page.locator('dialog#sheet[open]').count() == 1)
    page.keyboard.press('Escape'); time.sleep(0.3)
    page.locator('.row[data-sort-item]').nth(vi).locator('[data-sort=m][data-bereich=sus] > .mwrap > .chip[data-open=file]').first.click(); page.wait_for_selector('.viewer', timeout=10000)
    check('Bearbeiten-Modus: Antippen öffnet das Material', page.locator('.viewer').count() == 1 and page.locator('dialog#sheet[open]').count() == 0)
    page.go_back(); time.sleep(0.4)
    check('Bearbeiten-Modus bleibt nach dem Ansehen', page.locator('body.editing').count() == 1)
    shot('27-ziehen-reihe')
    # Reihen im Jahrgang
    page.goto(SITE + '#/f/physik/8'); page.wait_for_selector('.reihen'); time.sleep(0.3)
    jr = [r['id'] for r in getd()['faecher'][1]['jahrgaenge'][0]['reihen']]
    if len(jr) >= 2:
        ziehe(page.locator('.reihe-card').nth(len(jr) - 1).locator('.grip'), page.locator('.reihe-card').nth(0), oben=True); wait_saved()
        jr2 = [r['id'] for r in getd()['faecher'][1]['jahrgaenge'][0]['reihen']]
        check('Ziehen: Reihe nach oben', jr2 == [jr[-1]] + jr[:-1], (jr, jr2))
        check('Ziehen: Reihe öffnet sich nicht beim Ziehen', page.url.endswith('#/f/physik/8'), page.url)
    else: check('Ziehen: mind. 2 Reihen für Test', False, jr)
    edit_off()

    # ================= Buchaufgabe, Arten, Verschieben zwischen Bereichen, SuS-Ansicht =================
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    page.locator('.row[data-sort-item]').nth(0).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open] select[name=typ]')
    arten = page.eval_on_selector_all('dialog#sheet select[name=typ] option', 'o => o.map(x => x.value)')
    check('Arten: Material/Tafelbild/Lösung/Prüfung/Buch', arten == ['dokument', 'tafelbild', 'loesung', 'pruefung', 'buch'], arten)
    check('Arten: heißt „Material“ statt „Dokument“', page.eval_on_selector('dialog#sheet select[name=typ] option', 'o => o.textContent') == 'Material')
    page.select_option('dialog#sheet select[name=typ]', 'buch')
    check('Buch: kein Datei-Feld, Hinweis-Feld', page.locator('dialog#sheet fieldset[data-slot=datei]').is_hidden() and page.locator('dialog#sheet textarea[name=text]').is_visible())
    page.fill('dialog#sheet input[name=titel]', 'S. 112 Nr. 4 a–c'); page.fill('dialog#sheet textarea[name=text]', '**Tipp:** Merkkasten S. 110 nutzen\n- erst *skizzieren*\n- dann rechnen <script>x</script>')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    page.locator('.row[data-sort-item]').nth(0).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open] select[name=typ]')
    page.select_option('dialog#sheet select[name=typ]', 'buch'); page.fill('dialog#sheet input[name=titel]', 'S. 113 Nr. 7')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    v0 = reihe_of(getd())['vorhaben'][0]; bs = [m for m in v0['materialien'] if m['typ'] == 'buch']
    check('Buch: gespeichert ohne Datei', len(bs) == 2 and all(m['datei'] is None and m['url'] is None for m in bs) and bs[0].get('text', '').startswith('**Tipp:** Merkkasten') and 'text' not in bs[1], bs)
    # Dokument: Art bleibt beim Bearbeiten erhalten (HTML-Seite bleibt html)
    edit_off(); time.sleep(0.3)
    check('LK-Bereich in der normalen Ansicht zugeklappt', page.locator('.lk-area').count() > 0 and not page.locator('.lk-area').first.is_visible())
    page.locator('.lk-toggle').first.click(); time.sleep(0.2)
    check('LK-Bereich einzeln aufklappbar', page.locator('.lk-area').first.is_visible())
    edit_on(); time.sleep(0.2)
    check('LK-Bereich im Bearbeiten-Modus offen', all(page.locator('.lk-area').nth(i).is_visible() for i in range(page.locator('.lk-area').count())))
    edit_off(); time.sleep(0.2)
    check('Nach „Fertig“ wieder alles zugeklappt', not any(page.locator('.lk-area').nth(i).is_visible() for i in range(page.locator('.lk-area').count())))
    bchip = page.locator('.row').nth(0).locator('.chip.t-buch', has_text='S. 112')
    check('Buch: Titel + „Hinweis ›“ sichtbar', bchip.count() == 1 and 'Hinweis' in bchip.inner_text())
    bchip.click(); page.wait_for_selector('dialog#sheet[open] .buch-text')
    check('Buch: Antippen zeigt Hinweis', 'Merkkasten' in page.inner_text('dialog#sheet .buch-text'))
    bh = page.inner_html('dialog#sheet .buch-text')
    check('Format: **fett**, *kursiv*, Liste', '<b>Tipp:</b>' in bh and '<i>skizzieren</i>' in bh and bh.count('<li>') == 2, bh)
    check('Format: kein HTML eingeschleust', '<script>' not in bh and '&lt;script&gt;' in bh, bh)
    shot('28-buch-hinweis')
    page.click('dialog#sheet button[value=ok]'); time.sleep(0.3)
    check('Buch: ohne Hinweis nicht antippbar', page.locator('.row').nth(0).locator('span.chip.t-buch.still', has_text='S. 113').count() == 1)
    # SuS-Ansicht
    check('Kein eigener Knopf „SuS-Ansicht“ mehr', page.locator('#sus-ansicht').count() == 0)
    sus_ansicht(); page.wait_for_selector('body.kurs .rows'); time.sleep(0.4)
    check('SuS-Ansicht: Kursansicht ohne Lehrkraft-Bereich', '#/kurs/physik/8/optische-instrumente' in page.url and page.locator('.lk-area').count() == 0 and page.locator('#kurs-exit').is_visible())
    page.click('#kurs-exit'); page.wait_for_selector('.rows'); time.sleep(0.3)
    check('SuS-Ansicht: zurück zur Lehrkraft-Ansicht', page.url.endswith('#/f/physik/8/optische-instrumente') or '/f/physik/8/optische-instrumente' in page.url)
    # Suche findet Hinweistext
    page.goto(SITE + '#/suche'); page.wait_for_selector('#such-feld'); page.fill('#such-feld', 'Merkkasten'); time.sleep(0.5)
    check('Buch: Suche findet Hinweis', page.locator('#such-treffer .chip.t-buch').count() >= 1)
    # Verschieben zwischen Bereichen / Vorhaben
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    d = getd(); v0 = reihe_of(d)['vorhaben'][0]; v1 = reihe_of(d)['vorhaben'][1]
    loes = next(m for m in v0['materialien'] if m['bereich'] == 'lk' and m['typ'] != 'pruefung')
    n_dlg = len(dialogs)
    row0 = page.locator('.row[data-sort-item]').nth(0)
    ziehe(row0.locator('[data-sort=m][data-bereich=lk] > [data-sort-item]', has_text=loes['titel']).first, row0.locator('[data-sort=m][data-bereich=sus] > [data-sort-item]').nth(0), oben=True, dx=1); wait_saved()
    v0b = reihe_of(getd())['vorhaben'][0]; mm = next(m for m in v0b['materialien'] if m['id'] == loes['id'])
    check('Verschieben: Lehrkraft → SuS mit Rückfrage', mm['bereich'] == 'sus' and len(dialogs) > n_dlg and 'SuS sichtbar' in dialogs[-1], dialogs[-1:])
    check('Verschieben: an die Zielstelle', [m['id'] for m in v0b['materialien'] if m['bereich'] == 'sus'][0] == loes['id'])
    pr = next((m for m in v0b['materialien'] if m['typ'] == 'pruefung'), None)
    if pr:
        row0 = page.locator('.row[data-sort-item]').nth(0)
        ziehe(row0.locator('[data-sort=m][data-bereich=lk] > [data-sort-item]', has_text=pr['titel']).first, row0.locator('[data-sort=m][data-bereich=sus] > [data-sort-item]').nth(0), oben=True, dx=1); time.sleep(1)
        pr2 = next(m for m in reihe_of(getd())['vorhaben'][0]['materialien'] if m['id'] == pr['id'])
        check('Verschieben: Prüfung bleibt Lehrkraft-Material', pr2['bereich'] == 'lk' and 'Klassenarbeiten' in dialogs[-1], dialogs[-1:])
    row0 = page.locator('.row[data-sort-item]').nth(0); row1 = page.locator('.row[data-sort-item]').nth(1)
    ziehe(row0.locator('[data-sort=m][data-bereich=sus] > [data-sort-item]', has_text='S. 113').first.locator('.chip'), row1.locator('[data-sort=m][data-bereich=sus] > [data-sort-item]').nth(0), oben=True, dx=1); wait_saved()
    d = getd(); v0c, v1c = reihe_of(d)['vorhaben'][0], reihe_of(d)['vorhaben'][1]
    check('Verschieben: in anderes Vorhaben', any(m['titel'] == 'S. 113 Nr. 7' for m in v1c['materialien']) and not any(m['titel'] == 'S. 113 Nr. 7' for m in v0c['materialien']))
    check('Verschieben: dort an erster Stelle', [m['titel'] for m in v1c['materialien'] if m['bereich'] == 'sus'][0] == 'S. 113 Nr. 7', [m['titel'] for m in v1c['materialien'] if m['bereich'] == 'sus'])
    shot('29-verschoben')
    edit_off()
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)

    # ================= Trenner für mehrere Tage innerhalb eines Vorhabens =================
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)
    check('Tage: ohne Trenner nichts zu sehen', page.locator('.trenner').count() == 0 and not page.locator('[data-act=add-t]').first.is_visible())
    edit_on(); time.sleep(0.3)
    row0 = page.locator('.row[data-sort-item]').nth(0)
    check('Tage: „+ Tag“ im Bearbeiten-Modus', row0.locator('[data-act=add-t]').is_visible())
    row0.locator('[data-act=add-t]').click(); wait_saved()
    sus0 = [m for m in reihe_of(getd())['vorhaben'][0]['materialien'] if m['bereich'] == 'sus']
    check('Tage: Trenner „Tag 2“ hinten angefügt', sus0[-1]['typ'] == 'tag' and sus0[-1]['titel'] == 'Tag 2' and sus0[-1]['datei'] is None, [m['titel'] for m in sus0])
    tid = sus0[-1]['id']
    # Trenner nach vorne ziehen (hinter das erste Material)
    row0 = page.locator('.row[data-sort-item]').nth(0)
    ziehe(row0.locator('.trenner'), row0.locator('[data-sort=m][data-bereich=sus] > [data-sort-item]').nth(1), oben=True, dx=1); wait_saved()
    ids = [m['id'] for m in reihe_of(getd())['vorhaben'][0]['materialien'] if m['bereich'] == 'sus']
    check('Tage: Trenner verschiebbar', ids.index(tid) == 1, ids)
    # Beschriftung ändern
    page.locator('.row[data-sort-item]').nth(0).locator('.trenner').click(); page.wait_for_selector('dialog#sheet[open] input[name=titel]')
    page.fill('dialog#sheet input[name=titel]', 'Do 20.11.'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    check('Tage: Beschriftung geändert', next(m for m in reihe_of(getd())['vorhaben'][0]['materialien'] if m['id'] == tid)['titel'] == 'Do 20.11.')
    # zweiter Trenner ohne Material dahinter
    page.locator('.row[data-sort-item]').nth(0).locator('[data-act=add-t]').click(); wait_saved()
    t2 = [m for m in reihe_of(getd())['vorhaben'][0]['materialien'] if m['typ'] == 'tag']
    check('Tage: zweiter Trenner heißt „Tag 3“', len(t2) == 2 and t2[1]['titel'] == 'Tag 3', [m['titel'] for m in t2])
    # nicht in den Lehrkraft-Bereich
    row0 = page.locator('.row[data-sort-item]').nth(0)
    ziehe(row0.locator('.trenner', has_text='Tag 3'), row0.locator('[data-sort=m][data-bereich=lk] > [data-sort-item]').nth(0), oben=True, dx=1); time.sleep(1)
    check('Tage: Trenner bleibt beim Unterrichtsmaterial', all(m['bereich'] == 'sus' for m in reihe_of(getd())['vorhaben'][0]['materialien'] if m['typ'] == 'tag'))
    edit_off(); time.sleep(0.3)
    tx = page.locator('.row').nth(0).locator('.trenner').all_inner_texts()
    check('Tage: Lehrkraft sieht beide Trenner', tx == ['Do 20.11.', 'Tag 3'], tx)
    check('Tage: andere Vorhaben ohne Trenner', page.locator('.row').nth(1).locator('.trenner').count() == 0)
    shot('30-tage-trenner')
    page.evaluate("""async () => { const K = await T.keys('1234','pruefung123'); const d = await T.getData(K);
      const r = d.faecher[1].jahrgaenge[0].reihen.find(x => x.id === 'optische-instrumente'); const v = r.vorhaben[0];
      v.ausgeblendet = false; delete v.ab; delete v.kurse;
      v.materialien.forEach(m => { if(m.bereich === 'sus'){ m.ausgeblendet = false; delete m.ab; delete m.kurse; } });
      await T.putData(K, d); }""")
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.reload(); page.wait_for_selector('body.kurs .rows'); time.sleep(0.5)
    kt = page.locator('.row').nth(0).locator('.trenner').all_inner_texts()
    check('Tage: SuS sehen nur Trenner mit Material danach', kt == ['Do 20.11.'], kt)
    page.goto(SITE + '#/suche'); page.wait_for_selector('#such-feld'); page.fill('#such-feld', 'Tag 3'); time.sleep(0.5)
    check('Tage: Suche zeigt keine Trenner', 'Tag 3' not in page.inner_text('#such-treffer'))
    # löschen
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    page.locator('.row[data-sort-item]').nth(0).locator('.trenner', has_text='Tag 3').click(); page.wait_for_selector('dialog#sheet[open]')
    page.click('dialog#sheet button[value=delete]'); wait_saved()
    check('Tage: Trenner gelöscht', [m['titel'] for m in reihe_of(getd())['vorhaben'][0]['materialien'] if m['typ'] == 'tag'] == ['Do 20.11.'])
    edit_off()

    # ================= Ersetzen, Speichern im Hintergrund, verzögerte Seite =================
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    stale = dict(repo)   # ab hier liefert die Seite den alten Stand (wie GitHub Pages direkt nach dem Speichern)
    d = getd(); n_vor = sum(len(v['materialien']) for v in reihe_of(d)['vorhaben'])
    page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    check('Ersetzen: Hinweis im Upload-Feld', 'Gleicher Dateiname ersetzt' in page.inner_text('#multi-hint'))
    page.set_input_files('input[name=datei__file]', FILES + '/AB Spiegel-Parcours.pdf')
    mid = page.get_attribute('#ersetzen-row', 'data-m')
    m_alt = next(m for v in reihe_of(d)['vorhaben'] for m in v['materialien'] if m['id'] == mid)
    log_n = len(log)
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    stale = None; d2 = getd(); stale = dict(repo)
    m_neu = next(m for v in reihe_of(d2)['vorhaben'] for m in v['materialien'] if m['id'] == mid)
    check('Ersetzen: kein neuer Eintrag, Titel bleibt', sum(len(v['materialien']) for v in reihe_of(d2)['vorhaben']) == n_vor and m_neu['titel'] == m_alt['titel'], m_neu['titel'])
    check('Ersetzen: neue Datei unter neuem Namen', m_neu['datei']['pfad'] != m_alt['datei']['pfad'] and m_neu['datei']['pfad'] in repo and re.search(r'-[a-z0-9]{4}\.pdf\.enc$', m_neu['datei']['pfad']), m_neu['datei']['pfad'])
    neu_log = log[log_n:]
    i_data = max(i for i, x in enumerate(neu_log) if x == ('PUT', 'data/inhalt.enc'))
    check('Ersetzen: alte Datei erst nach dem Speichern gelöscht', m_alt['datei']['pfad'] not in repo and ('DEL', m_alt['datei']['pfad']) in neu_log[i_data:], neu_log)
    # Neu geladen, obwohl die Seite noch den alten Stand liefert: Lehrkraft sieht den neuen Stand (über die API)
    page.locator('.row').nth(0).locator('[data-act=edit-v]').click(); page.wait_for_selector('dialog#sheet[open] input[name=titel]')
    alt_titel = page.input_value('dialog#sheet input[name=titel]')
    page.fill('dialog#sheet input[name=titel]', alt_titel + ' (neu)'); page.click('dialog#sheet button[value=ok]')
    try: page.wait_for_function("t => document.querySelector('.rows').innerText.includes(t)", arg=alt_titel + ' (neu)', timeout=1500); sofort = True
    except Exception: sofort = False
    check('Hintergrund: Änderung sofort sichtbar', sofort)
    check('Hintergrund: keine blockierende Sperre', not page.is_visible('#busy'))
    wait_saved()
    page.reload(); page.wait_for_selector('.rows'); time.sleep(0.5)
    check('Neu laden: Lehrkraft sieht gespeicherten Stand trotz verzögerter Seite', (alt_titel + ' (neu)') in page.inner_text('.rows'))
    page.click('#reload'); time.sleep(1)
    check('Aktualisieren: Stand bleibt', (alt_titel + ' (neu)') in page.inner_text('.rows'))
    # frisch hochgeladene Datei öffnen, obwohl sie auf der Seite noch fehlt
    edit_off(); time.sleep(0.3)
    page.locator('.row').nth(0).locator('.chip', has_text=m_alt['titel']).first.click(); page.wait_for_selector('.viewer'); time.sleep(1.5)
    check('Neue Datei: Lehrkraft kann sie sofort öffnen', 'Fehler' not in page.inner_text('.viewer'), page.inner_text('.viewer')[:200])
    page.go_back(); time.sleep(0.4)
    # Löschen: sofort weg, Datei danach im Hintergrund gelöscht
    edit_on(); time.sleep(0.3)
    stale = None; d3 = getd(); stale = dict(repo)
    weg = next(m for v in reihe_of(d3)['vorhaben'] for m in v['materialien'] if m['titel'] == 'Lösungsblatt später')
    pen(page, 'Lösungsblatt später').click(); page.wait_for_selector('dialog#sheet[open]')
    page.click('dialog#sheet button[value=delete]')
    page.wait_for_function("() => !document.querySelector('.rows').innerText.includes('Lösungsblatt später')", timeout=5000)
    check('Löschen: Eintrag sofort weg', True)
    wait_saved(); time.sleep(0.5)
    stale = None
    d_k = getd()
    check('Löschen: in den Papierkorb, Datei bleibt', weg['datei']['pfad'] in repo and any(e['m']['id'] == weg['id'] for e in d_k.get('papierkorb', [])))
    page.locator('.row').nth(0).locator('[data-act=edit-v]').click(); page.wait_for_selector('dialog#sheet[open] input[name=titel]')
    page.fill('dialog#sheet input[name=titel]', alt_titel); page.click('dialog#sheet button[value=ok]'); wait_saved()
    edit_off()
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)

    # ================= Titelbild mit interaktiver Seite (Advance Organizer) =================
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)
    d = getd(); ziel = next(m['titel'] for v in reihe_of(d)['vorhaben'] for m in v['materialien'] if m['bereich'] == 'sus' and m.get('datei') and m['typ'] != 'html')
    open(FILES + '/AO Optik.html', 'w').write('<!DOCTYPE html><html><body><h1 id="ao">Advance Organizer</h1><a id="mat" href="um:material:' + ziel + '">Material</a></body></html>')
    check('AO: ohne Seite kein Knopf', page.locator('.titelseite-btn').count() == 0)
    edit_on()
    page.click('[data-act=edit-bild]'); page.wait_for_selector('dialog#sheet[open]')
    page.click('input[name=seite__mode][value=file]')
    page.set_input_files('input[name=seite__file]', FILES + '/AB Spiegel-Parcours.pdf')
    n_d = len(dialogs); page.click('dialog#sheet button[value=ok]')
    for _ in range(50):
        if len(dialogs) > n_d: break
        page.wait_for_timeout(100)
    check('AO: nur HTML erlaubt', any('HTML-Datei' in x for x in dialogs[n_d:]) and not reihe_of(getd()).get('titelseite'), dialogs[n_d:])
    page.click('[data-act=edit-bild]'); page.wait_for_selector('dialog#sheet[open]')
    page.click('input[name=seite__mode][value=file]')
    page.set_input_files('input[name=seite__file]', FILES + '/AO Optik.html')
    tb_vor = reihe_of(getd())['titelbild']['pfad']
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    r_ = reihe_of(getd()); ts = r_.get('titelseite') or {}
    check('AO: Seite gespeichert, Titelbild bleibt', ts.get('datei') and ts['datei']['pfad'] in repo and ts['datei']['ext'] == 'html' and r_['titelbild']['pfad'] == tb_vor, ts)
    edit_off()
    check('AO: Knopf auf dem Titelbild', page.locator('.titelbild-box .titelseite-btn').is_visible() and page.locator('img.titelbild').count() == 1)
    page.click('.titelbild-btn'); page.wait_for_selector('.viewer'); time.sleep(0.5)
    check('AO: Bild antippen vergrößert weiter', 'Titelbild' in page.inner_text('.viewer .viewer-bar b') and page.locator('.viewer img').count() == 1)
    page.go_back(); time.sleep(0.4)
    page.click('.titelseite-btn'); fr = page.frame_locator('.viewer iframe'); fr.locator('#ao').wait_for(timeout=10000)
    check('AO: „Interaktiv öffnen“ zeigt die Seite (ohne „Weiter“)', page.locator('.viewer [data-v=next]').count() == 0)
    fr.locator('#mat').click(); time.sleep(1)
    check('AO: Link um:material öffnet Material der Reihe', page.locator('.viewer').count() == 1 and page.inner_text('.viewer .viewer-bar b') == ziel, page.inner_text('.viewer .viewer-bar b') if page.locator('.viewer').count() else '')
    page.go_back(); time.sleep(0.4)
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.4)
    check('AO: auch in der Kursansicht', page.locator('.titelseite-btn').is_visible())
    shot('20-ao-kurs')
    with page.expect_download() as dl:
        page.click('[data-act=dl-reihe]')
    zp = OUT + '/sus-ao.zip'; dl.value.save_as(zp); zn = zipfile.ZipFile(zp).namelist()
    check('AO: im SuS-Download', any('Titelbild (interaktiv).html' in n for n in zn) and 'Interaktiv öffnen' in zipfile.ZipFile(zp).read([n for n in zn if n.endswith('Übersicht.html')][0]).decode(), zn)
    page.click('#kurs-exit'); page.wait_for_selector('.crumbs')
    # Reihe ohne Titelbild: nur Seite → eigener Knopf; leeres Bild-Feld stört nicht
    page.goto(SITE + '#/f/mathe/6/brueche'); page.wait_for_selector('.rows'); edit_on()
    check('AO: Hinzufügen-Knopf nennt Advance Organizer', 'Advance Organizer' in page.inner_text('[data-act=edit-bild]'))
    page.click('[data-act=edit-bild]'); page.wait_for_selector('dialog#sheet[open]')
    page.click('input[name=seite__mode][value=file]'); page.set_input_files('input[name=seite__file]', FILES + '/AO Optik.html')
    n_d = len(dialogs); page.click('dialog#sheet button[value=ok]'); wait_saved()
    check('AO: ohne Bild keine Rückfrage', not dialogs[n_d:], dialogs[n_d:])
    edit_off()
    check('AO: ohne Titelbild nur Knopf', page.locator('.titelseite-btn.solo').is_visible() and page.locator('img.titelbild').count() == 0)
    alt_ao = reihe_of(getd(), 'brueche')['titelseite']['datei']['pfad']
    edit_on(); page.click('[data-act=edit-bild]'); page.wait_for_selector('dialog#sheet[open]')
    page.click('input[name=seite__mode][value=link]'); page.fill('input[name=seite__url]', 'https://example.org/ao')
    page.click('dialog#sheet button[value=ok]'); wait_saved(); edit_off()
    a_ = page.locator('a.titelseite-btn')
    check('AO: Link öffnet in neuem Tab, alte Datei gelöscht', a_.count() == 1 and a_.get_attribute('href') == 'https://example.org/ao' and a_.get_attribute('target') == '_blank' and alt_ao not in repo)
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)

    # ================= Einfügen, Kurztitel, Enter/Entf, Papierkorb, Import-Fenster =================
    PASTE_JS = """(a) => { const dt = new DataTransfer();
      for (const f of (a.files || [])) dt.items.add(new File([f.c], f.n, { type: f.t || '' }));
      if (a.text) dt.setData('text/plain', a.text);
      (document.activeElement && document.activeElement !== document.body ? document.activeElement : document.body)
        .dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }"""
    def paste(files=None, text=None): page.evaluate(PASTE_JS, {'files': files or [], 'text': text})
    def mats_of(d, vi): return reihe_of(d)['vorhaben'][vi]['materialien']
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    # Kurztitel aus Pauls Dateinamen
    open(FILES + '/P9 Stromkreis - 3 Blitz-Check - Stationskarten.pdf', 'wb').write(b'%PDF-BLITZ')
    page.locator('.row').nth(1).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    page.set_input_files('input[name=datei__file]', FILES + '/P9 Stromkreis - 3 Blitz-Check - Stationskarten.pdf')
    check('Kurztitel: „Blitz-Check - Stationskarten“', page.input_value('dialog#sheet input[name=titel]') == 'Blitz-Check - Stationskarten', page.input_value('dialog#sheet input[name=titel]'))
    n_d = len(dialogs)
    page.focus('dialog#sheet input[name=titel]'); page.keyboard.press('Enter'); wait_saved()
    bl = [m for m in mats_of(getd(), 1) if m['titel'] == 'Blitz-Check - Stationskarten']
    check('Enter im neuen Material speichert', len(bl) == 1 and bl[0]['datei']['name'] == 'P9 Stromkreis - 3 Blitz-Check - Stationskarten.pdf', [m['titel'] for m in mats_of(getd(), 1)])
    # Enter beim Bearbeiten: speichern statt löschen
    pen(page.locator('.row').nth(1), 'Blitz-Check').click(); page.wait_for_selector('dialog#sheet[open] button[value=delete]')
    page.fill('dialog#sheet input[name=titel]', 'Blitz-Check - Stationen'); page.focus('dialog#sheet input[name=titel]'); page.keyboard.press('Enter'); wait_saved()
    bl = [m for m in mats_of(getd(), 1) if m['titel'].startswith('Blitz-Check')]
    check('Enter beim Bearbeiten speichert (nicht löschen)', len(bl) == 1 and bl[0]['titel'] == 'Blitz-Check - Stationen' and len(dialogs) == n_d, [m['titel'] for m in bl] + dialogs[n_d:])
    bid = bl[0]['id']; pos = [m['id'] for m in mats_of(getd(), 1)].index(bid)
    # Entf löscht → Papierkorb, ein Hinweis mit „Rückgängig“, keine Rückfragen
    pen(page.locator('.row').nth(1), 'Blitz-Check').click(); page.wait_for_selector('dialog#sheet[open] button[value=delete]')
    page.locator('dialog#sheet select').first.focus(); page.keyboard.press('Delete')
    page.wait_for_selector('#toast.on .toast-btn', timeout=5000)
    check('Entf löscht ohne Rückfrage, Hinweis mit „Rückgängig“', len(dialogs) == n_d and 'Papierkorb' in page.inner_text('#toast') and not page.locator('.row').nth(1).locator('.chip', has_text='Blitz-Check').count(), dialogs[n_d:])
    page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000); time.sleep(0.3)
    dk = getd(); ek = [e for e in dk.get('papierkorb', []) if e['m']['id'] == bid]
    check('Papierkorb: Eintrag mit Ort, Datei bleibt', len(ek) == 1 and ek[0]['m']['datei']['pfad'] in repo and 'Sehhilfen' in ek[0]['ort']['text'], dk.get('papierkorb'))
    page.click('#toast .toast-btn'); time.sleep(0.4); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000); time.sleep(0.3)
    dk = getd()
    check('Rückgängig: wieder an derselben Stelle', [m['id'] for m in mats_of(dk, 1)].index(bid) == pos and not any(e['m']['id'] == bid for e in dk.get('papierkorb', [])))
    # Papierkorb in den Einstellungen: wiederherstellen
    pen(page.locator('.row').nth(1), 'Blitz-Check').click(); page.wait_for_selector('dialog#sheet[open] button[value=delete]')
    page.click('dialog#sheet button[value=delete]'); time.sleep(0.4); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000)
    page.goto(SITE + '#/einstellungen/speicher'); page.wait_for_selector('#papierkorb')
    check('Papierkorb in Einstellungen → Speicher', 'Blitz-Check - Stationen' in page.inner_text('#papierkorb') and 'Papierkorb leeren' in page.inner_text('#papierkorb'))
    shot('21-papierkorb')
    page.locator('#papierkorb li', has_text='Blitz-Check').locator('[data-act=korb-zurueck]').click(); time.sleep(0.4); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000); time.sleep(0.3)
    check('Papierkorb: Wiederherstellen', any(m['id'] == bid for m in mats_of(getd(), 1)))
    # Vorhaben löschen → Material in den Papierkorb, wiederherstellen legt das Vorhaben neu an (ausgeblendet)
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    pen(page.locator('.row').nth(1), 'Blitz-Check').click(); page.wait_for_selector('dialog#sheet[open] button[value=delete]')
    page.click('dialog#sheet button[value=delete]'); time.sleep(0.4); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000); time.sleep(0.3)
    pf = next(e for e in getd()['papierkorb'] if e['m']['id'] == bid)['m']['datei']['pfad']
    # Leeren: Datei endgültig weg
    page.goto(SITE + '#/einstellungen/speicher'); page.wait_for_selector('#papierkorb [data-act=korb-leeren]')
    page.click('[data-act=korb-leeren]'); wait_saved(); time.sleep(0.8)
    check('Papierkorb leeren: Einträge und Dateien weg', not getd().get('papierkorb') and pf not in repo and 'Leer' in page.inner_text('#papierkorb'))
    # Automatisch nach 30 Tagen
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    page.locator('.row').nth(0).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    open(FILES + '/Alt.pdf', 'wb').write(b'%PDF-ALT'); page.set_input_files('input[name=datei__file]', FILES + '/Alt.pdf')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    pen(page.locator('.row').nth(0), 'Alt').click(); page.wait_for_selector('dialog#sheet[open] button[value=delete]')
    page.click('dialog#sheet button[value=delete]'); time.sleep(0.4); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000); time.sleep(0.3)
    alt_pf = getd()['papierkorb'][0]['m']['datei']['pfad']
    page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); const d = await T.getData(K); d.papierkorb[0].am = '2020-01-01'; await T.putData(K, d); }")
    page.reload(); page.wait_for_selector('.rows'); time.sleep(1.5); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000); time.sleep(1)
    check('Papierkorb: nach 30 Tagen automatisch gelöscht', not getd().get('papierkorb') and alt_pf not in repo, getd().get('papierkorb'))
    # Text einfügen über einem Vorhaben → Notiz
    edit_off(); page.hover('.row >> nth=0 >> .row-title'); paste(text='Stationen aufbauen\n- Netzgerät prüfen')
    page.wait_for_selector('dialog#sheet[open] textarea[name=text]')
    v0 = reihe_of(getd())['vorhaben'][0]
    check('Text: Dialog mit Vorhaben unter der Maus', page.input_value('dialog#sheet select[name=v]') == v0['id'] and 'Netzgerät' in page.input_value('dialog#sheet textarea[name=text]'))
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    check('Text: als Notiz (Verlaufsplan) gespeichert', 'Stationen aufbauen' in ((reihe_of(getd())['vorhaben'][0].get('planung') or {}).get('verlauf') or ''))
    # Datei einfügen über einem Vorhaben → direkt dorthin
    page.hover('.row >> nth=1 >> .row-title')
    paste(files=[{'n': 'P9 Stromkreis - 4 Kurzschluss - AB.pdf', 'c': '%PDF-KURZ', 't': 'application/pdf'}]); wait_saved()
    ks = [m for m in mats_of(getd(), 1) if m['titel'] == 'Kurzschluss - AB']
    check('Datei über Vorhaben eingefügt: direkt, Kurztitel', len(ks) == 1 and ks[0]['bereich'] == 'sus' and page.locator('.sync-modal').count() == 0, [m['titel'] for m in mats_of(getd(), 1)])
    # Screenshot ohne Ziel → Fenster zum Zuordnen (vor der Seite), Vorhaben pro Datei
    page.mouse.move(5, 5)
    paste(files=[{'n': 'P9 Stromkreis - 1 Reihenschaltung.pdf', 'c': '%PDF-R', 't': 'application/pdf'}, {'n': 'image.png', 'c': 'PNGDATA', 't': 'image/png'}])
    page.wait_for_selector('.sync-modal .sync-panel', timeout=10000); time.sleep(0.3)
    bb = page.locator('.sync-panel').bounding_box(); vp = page.viewport_size
    check('Import-Fenster liegt vor der Seite (nicht ganzseitig)', bb['width'] < vp['width'] and bb['x'] > 0)
    names = page.locator('.sync-panel td.fname').all_inner_texts()
    check('Screenshot bekommt Namen', any(n.startswith('Screenshot ') and n.endswith('.png') for n in names), names)
    zs = page.locator('.sync-panel select[data-k=ziel]')
    check('Vorhaben pro Datei wählbar', zs.count() == 2)
    vs = reihe_of(getd())['vorhaben']
    zs.nth(0).select_option('v:' + vs[0]['id']); time.sleep(0.2); zs.nth(1).select_option('v:' + vs[1]['id']); time.sleep(0.2)
    page.screenshot(path=f'{OUT}/22-import-fenster.png')
    page.click('.sync-panel [data-s=go]'); wait_saved()
    d2 = getd()
    check('Zwei Dateien in verschiedene Vorhaben', any(m['titel'] == 'Reihenschaltung' for m in mats_of(d2, 0)) and any(m['titel'].startswith('Screenshot') for m in mats_of(d2, 1)),
          ([m['titel'] for m in mats_of(d2, 0)], [m['titel'] for m in mats_of(d2, 1)]))
    # Einfügen in offenen Dialog: Datei-Feld wird gefüllt
    edit_on(); page.click('[data-act=edit-bild]'); page.wait_for_selector('dialog#sheet[open]')
    paste(files=[{'n': 'image.png', 'c': 'PNGDATA2', 't': 'image/png'}])
    check('Einfügen im Dialog füllt das Bild-Feld', page.is_checked('input[name=bild__mode][value=file]') and page.evaluate("document.querySelector('input[name=bild__file]').files.length") == 1)
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    check('Titelbild aus Zwischenablage', reihe_of(getd())['titelbild']['name'].startswith('Screenshot'), reihe_of(getd())['titelbild']['name'])
    edit_off()
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)

    # ================= Schneller vorbereiten / Im Unterricht =================
    import json as _json
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_off(); time.sleep(0.3)
    rows = page.locator('.rows > .row[data-v]')
    nrows = rows.count()
    check('Auge + Menü ohne Bearbeiten-Modus', rows.nth(0).locator('.row-acts [data-act=vis-v]').is_visible() and rows.nth(0).locator('.row-acts [data-act=menu-v]').is_visible())
    # letztes Vorhaben ausblenden (ohne Bearbeiten)
    last = rows.nth(nrows - 1)
    if 'aus' not in (last.get_attribute('class') or ''):
        last.locator('.row-acts [data-act=vis-v]').click(); wait_saved()
    check('Auge ohne Bearbeiten blendet aus', 'aus' in (rows.nth(nrows - 1).get_attribute('class') or ''))
    # „Bis hier freischalten“ an Vorhaben 3
    bi = max(0, nrows - 2)
    rows.nth(bi).locator('[data-act=menu-v]').click(); page.wait_for_selector('.popmenu')
    page.locator('.popmenu button', has_text='Bis hier freischalten').click()
    try: wait_saved()
    except Exception: pass
    check('Bis hier freischalten', all('aus' not in (rows.nth(i).get_attribute('class') or '') for i in range(bi + 1)), (nrows, bi))
    akt = [i for i in range(rows.count()) if 'aktuell' in (rows.nth(i).get_attribute('class') or '')]
    vis = [i for i in range(rows.count()) if 'aus' not in (rows.nth(i).get_attribute('class') or '')]
    check('Aktuelle Einheit = letzte sichtbare', akt == [vis[-1]] and 'aktuell' in rows.nth(vis[-1]).inner_text().lower(), (akt, vis))
    # Material-Auge ohne Bearbeiten
    mw = page.locator('.rows .mwrap [data-act=vis-m]').first
    mid = mw.get_attribute('data-m'); mw.click(); wait_saved()
    mm = [m for v in reihe_of(getd())['vorhaben'] for m in v['materialien'] if m['id'] == mid][0]
    check('Material-Auge ohne Bearbeiten', page.locator('.rows [data-act=vis-m][data-m="' + mid + '"]').count() == 1 and _json.dumps(mm).count('true') >= 1)
    page.locator('.rows [data-act=vis-m][data-m="' + mid + '"]').click(); wait_saved()
    # „heute“
    rows.nth(0).locator('[data-act=menu-v]').click(); page.wait_for_selector('.popmenu')
    page.locator('.popmenu button', has_text='heute').click(); wait_saved()
    check('Als „heute“ markieren', 'aktuell' in (rows.nth(0).get_attribute('class') or '') and 'heute' in rows.nth(0).locator('.akt-badge').inner_text().lower())
    shot('23-aktuell')
    rows.nth(0).locator('[data-act=menu-v]').click(); page.wait_for_selector('.popmenu')
    page.locator('.popmenu button', has_text='Nicht mehr').click(); wait_saved()
    check('„heute“ wieder entfernen', 'aktuell' not in (rows.nth(0).get_attribute('class') or '') or vis[-1] == 0)
    # Kursansicht: hervorgehoben; Direktlink auf ein Material
    sus_ansicht()
    page.wait_for_selector('body.kurs .rows'); time.sleep(0.4)
    check('Kursansicht: aktuelle Einheit hervorgehoben', page.locator('.row.aktuell').count() == 1)
    kurs_hash = page.evaluate('location.hash')
    fid = page.locator('.rows [data-open=file][data-m]').first.get_attribute('data-m')
    ftitel = page.locator('.rows [data-open=file][data-m]').first.locator('span').first.inner_text()
    page.goto(SITE + kurs_hash + '?m=' + fid); page.wait_for_selector('.viewer', timeout=10000); time.sleep(0.5)
    check('Direktlink öffnet das Material', page.inner_text('.viewer .viewer-bar b') == ftitel and '?m=' not in page.evaluate('location.hash'), page.evaluate('location.hash'))
    page.go_back(); time.sleep(0.5)
    check('Zurück → Gesamtansicht', page.locator('.viewer').count() == 0 and page.locator('body.kurs .rows').count() == 1)
    page.click('#kurs-exit'); page.wait_for_selector('.crumbs'); time.sleep(0.3)
    # QR + Arbeitsauftrag im Viewer, Pfeiltasten
    page.locator('.rows [data-open=file][data-m]').first.click(); page.wait_for_selector('.viewer [data-v=qr]', timeout=10000)
    t1 = page.inner_text('.viewer .viewer-bar b')
    page.click('.viewer [data-v=qr]'); page.wait_for_selector('.qr-aside .qr-box svg', timeout=10000)
    page.fill('.qr-aside textarea', 'Bearbeitet A1, A2')
    check('QR neben dem Material, Arbeitsauftrag', page.locator('.viewer-main .viewer-body').is_visible() and page.locator('.qr-aside textarea').input_value() == 'Bearbeitet A1, A2')
    page.keyboard.press('ArrowRight'); time.sleep(0.3)
    check('Pfeiltaste im Arbeitsauftrag schreibt (kein Wechsel)', page.inner_text('.viewer .viewer-bar b') == t1)
    shot('24-qr-auftrag')
    page.locator('.viewer-bar b').click(); page.keyboard.press('ArrowRight'); time.sleep(0.8)
    t2 = page.inner_text('.viewer .viewer-bar b')
    check('Pfeiltaste → nächstes Material, QR + Auftrag bleiben', t2 != t1 and page.locator('.qr-aside textarea').input_value() == 'Bearbeitet A1, A2', (t1, t2))
    page.keyboard.press('ArrowLeft'); time.sleep(0.8)
    check('Pfeiltaste ← vorheriges Material', page.inner_text('.viewer .viewer-bar b') == t1)
    check('Arbeitsauftrag wird nicht gespeichert', 'Bearbeitet A1' not in _json.dumps(getd()) and not any('Bearbeitet A1' in (page.evaluate('k => localStorage.getItem(k)', k) or '') for k in page.evaluate('Object.keys(localStorage)')))
    page.click('.viewer [data-v=qr]'); time.sleep(0.2)
    check('QR wieder ausblenden', page.locator('.qr-aside').count() == 0)
    page.go_back(); time.sleep(0.5)
    # Tafelbild
    edit_on()
    rows.nth(1).locator('[data-act=add-m][data-bereich=sus]').click(); page.wait_for_selector('dialog#sheet[open]')
    page.select_option('dialog#sheet select[name=typ]', 'tafelbild'); time.sleep(0.2)
    fi = page.locator('input[name=datei__file]')
    check('Tafelbild: Kamera am iPad, Titel mit Datum', fi.get_attribute('capture') == 'environment' and fi.get_attribute('accept') == 'image/*' and page.input_value('dialog#sheet input[name=titel]').startswith('Tafelbild '))
    open(FILES + '/tafel.png', 'wb').write(b'\x89PNG\r\n\x1a\nTAFEL')
    page.set_input_files('input[name=datei__file]', FILES + '/tafel.png'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    tb = [m for m in reihe_of(getd())['vorhaben'][1]['materialien'] if m['titel'].startswith('Tafelbild ')]
    check('Tafelbild gespeichert (Mitschrift)', len(tb) == 1 and tb[0]['typ'] == 'mitschrift', [(m['titel'], m['typ']) for m in reihe_of(getd())['vorhaben'][1]['materialien']])
    # Kopieren in eine andere Reihe
    page.locator('[data-act=edit-m][data-m="' + tb[0]['id'] + '"]').click(); page.wait_for_selector('dialog#sheet[open] input[name=kopie]')
    page.select_option('dialog#sheet select[name=o_f]', 'mathe'); time.sleep(0.2)
    page.select_option('dialog#sheet select[name=o_j]', '6'); time.sleep(0.2)
    page.select_option('dialog#sheet select[name=o_r]', 'brueche'); time.sleep(0.2)
    page.check('dialog#sheet input[name=kopie]'); page.click('dialog#sheet button[value=ok]'); wait_saved()
    d3 = getd(); orig = [m for m in reihe_of(d3)['vorhaben'][1]['materialien'] if m['id'] == tb[0]['id']]
    kop = [m for v in reihe_of(d3, 'brueche')['vorhaben'] for m in v['materialien'] if m['titel'] == tb[0]['titel']]
    check('Kopie: Original bleibt, Kopie mit gleicher Datei', len(orig) == 1 and len(kop) == 1 and kop[0]['id'] != tb[0]['id'] and kop[0]['datei']['pfad'] == tb[0]['datei']['pfad'])
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_on(); time.sleep(0.3)
    # Mehrfachauswahl
    chips = page.locator('.rows .row[data-v] [data-sort=m][data-bereich=sus] > .mwrap[data-m]')
    ids2 = [chips.nth(0).get_attribute('data-m'), chips.nth(1).get_attribute('data-m')]
    chips.nth(0).locator('.chip').click(modifiers=['Control']); page.wait_for_selector('#auswahl-bar')
    chips.nth(1).locator('.chip').click(); time.sleep(0.2)
    check('Auswahl: 2 markiert, kein Dialog', '2 ausgewählt' in page.inner_text('#auswahl-bar') and page.locator('dialog#sheet[open]').count() == 0 and page.locator('.chip.gewaehlt').count() == 2)
    shot('25-auswahl')
    page.click('#auswahl-bar [data-a=aus]'); wait_saved()
    check('Auswahl: zusammen ausgeblendet, Auswahl bleibt', all('aus' in (page.locator('.mwrap[data-m="' + x + '"] > .chip').get_attribute('class') or '') for x in ids2) and page.locator('.chip.gewaehlt').count() == 2)
    page.click('#auswahl-bar [data-a=ein]'); wait_saved()
    page.click('#auswahl-bar [data-a=del]'); page.wait_for_selector('#toast.on .toast-btn'); time.sleep(0.3); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000)
    pk = [e['m']['id'] for e in getd().get('papierkorb', [])]
    check('Auswahl: zusammen in den Papierkorb', all(x in pk for x in ids2) and page.locator('#auswahl-bar').count() == 0)
    page.click('#toast .toast-btn'); time.sleep(0.5); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000); time.sleep(0.3)
    alle = [m['id'] for v in reihe_of(getd())['vorhaben'] for m in v['materialien']]
    check('Auswahl: Rückgängig holt alle zurück', all(x in alle for x in ids2))
    chips = page.locator('.rows .row[data-v] [data-sort=m][data-bereich=sus] > .mwrap[data-m]')
    chips.nth(0).locator('.chip').click(modifiers=['Control']); time.sleep(0.2)
    check('Strg + Klick markiert', page.locator('#auswahl-bar').count() == 1 and '1 ausgewählt' in page.inner_text('#auswahl-bar'))
    page.locator('body').press('Escape'); time.sleep(0.2)
    check('Esc beendet die Auswahl', page.locator('#auswahl-bar').count() == 0 and page.locator('.chip.gewaehlt').count() == 0)
    # Tastenkürzel
    edit_off(); page.locator('h1').first.click()
    page.keyboard.press('e'); time.sleep(0.3)
    on = page.locator('body.editing').count() == 1
    page.keyboard.press('e'); time.sleep(0.3)
    check('Taste E: Bearbeiten an/aus', on and page.locator('body.editing').count() == 0)
    page.hover('.rows > .row[data-v] >> nth=1 >> .row-title'); page.keyboard.press('n'); page.wait_for_selector('dialog#sheet[open] select[name=o_v]')
    check('Taste N: neues Material im Vorhaben unter der Maus', page.input_value('dialog#sheet select[name=o_v]') == reihe_of(getd())['vorhaben'][1]['id'])
    page.click('dialog#sheet button[value=cancel]'); time.sleep(0.2)
    page.keyboard.press('/'); page.wait_for_selector('#such-feld'); time.sleep(0.2)
    check('Taste /: Suche', page.evaluate('location.hash') == '#/suche' and page.evaluate("document.activeElement && document.activeElement.id") == 'such-feld')
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.3)

    # ================= Planung pro Reihe, „+ Material“-Menü =================
    page.goto(SITE + '#/f/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); edit_off(); time.sleep(0.3)
    check('Planung: ohne Inhalt in der normalen Ansicht unsichtbar', page.locator('.plan-box').count() == 0 and not page.locator('[data-act=edit-plan]').first.is_visible())
    check('Unten kein „Auswählen“/„Ordner hochladen“ mehr', page.locator('[data-act=auswahl-an]').count() == 0 and page.locator('.rows ~ .btnline [data-act=sync-r], .btnline [data-act=sync-r]').count() == 0)
    edit_on()
    page.click('[data-act=edit-plan]'); page.wait_for_selector('dialog#sheet[open] textarea[name=plan]')
    page.fill('dialog#sheet textarea[name=plan]', '# Nächste Woche\n[ ] AB Reihenschaltung erstellen\n[x] Versuch testen\n# Nächstes Mal\n- mehr Zeitpuffer einplanen')
    page.click('dialog#sheet button[value=ok]'); wait_saved()
    check('Planung gespeichert', reihe_of(getd()).get('plan', '').startswith('# Nächste Woche\n[ ] AB Reihenschaltung'))
    edit_off(); time.sleep(0.3)
    pbx = page.locator('.plan-box')
    check('Planung: Kasten unten, To-dos als Kästchen', pbx.count() == 1 and pbx.locator('input[type=checkbox]').count() == 2 and '1 offen' in pbx.inner_text() and pbx.locator('h4').count() == 2 and pbx.locator('.plan-todo.fertig').count() == 1)
    shot('26-planung')
    pbx.locator('input[type=checkbox]').first.click(); wait_saved()
    check('Planung: abhaken speichert', '[x] AB Reihenschaltung' in reihe_of(getd()).get('plan', '') and 'offen' not in page.locator('.plan-box .plan-head').inner_text())
    page.hover('.plan-box .plan-body'); paste(text='[ ] Klausur vorbereiten')
    page.wait_for_selector('#toast.on'); page.wait_for_selector('#saving:not(.on)', state='attached', timeout=30000); time.sleep(0.4)
    check('Planung: Strg+V über dem Kasten hängt an', reihe_of(getd()).get('plan', '').endswith('\n[ ] Klausur vorbereiten') and page.locator('dialog#sheet[open]').count() == 0)
    page.click('#search-btn'); page.wait_for_selector('#such-feld'); page.fill('#such-feld', 'Zeitpuffer'); time.sleep(0.6)
    check('Suche findet Planung', 'Sehhilfen' in page.inner_text('#such-treffer'))
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.wait_for_selector('body.kurs .rows'); time.sleep(0.3)
    check('Planung nie in der Kursansicht', page.locator('.plan-box').count() == 0 and 'Zeitpuffer' not in page.inner_text('#app'))
    page.click('#kurs-exit'); page.wait_for_selector('.crumbs'); time.sleep(0.3)
    edit_on()
    page.click('#add-material'); page.wait_for_selector('.popmenu')
    check('„+ Material“: Material oder Ordner', page.locator('.popmenu button').count() == 2 and 'Ordner' in page.inner_text('.popmenu'))
    page.locator('.popmenu button', has_text='Material').first.click(); page.wait_for_selector('dialog#sheet[open] select[name=o_r]')
    check('„+ Material“ → Material in dieser Reihe', page.input_value('dialog#sheet select[name=o_r]') == 'optische-instrumente')
    page.click('dialog#sheet button[value=cancel]'); time.sleep(0.2)
    check('Notizen-Knopf mit eigenem Symbol', page.locator('[data-act=notiz-v] svg').first.inner_html() != page.locator('[data-act=edit-m] svg').first.inner_html())
    edit_off()

    # ================= C: Sicherung -> „Alles ersetzen“ =================
    page.evaluate("""async () => { const K = await T.keys('1234','pruefung123'); const d = await T.getData(K);
      const r = d.faecher[1].jahrgaenge[0].reihen.find(x => x.id === 'optische-instrumente');
      r.uebersicht = { sus: await T.file(K, 'material/physik/8/optische-instrumente/lernlandkarte.pdf.enc', 'LLK', 'basis'), lk:null, url:null };
      d.faecher[1].farbe = 'lila'; d.faecher.push({ id:'chemie', name:'Chemie', farbe:'rot', vorlage:null, extern:'https://x.github.io/chemie/', jahrgaenge:[] });
      await T.putData(K, d); }""")
    page.goto(SITE + '#/einstellungen/verwaltung'); page.reload(); page.wait_for_selector('[data-act=unlock-p]')
    page.click('[data-act=unlock-p]'); page.wait_for_selector('dialog#sheet[open] input[name=pw]'); page.fill('input[name=pw]', 'pruefung123'); page.click('dialog#sheet button[value=ok]')
    time.sleep(0.8); page.wait_for_selector('[data-act=export-all]')
    before = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    page.evaluate("document.querySelector('#toast').classList.remove('on')")
    with page.expect_download() as dl:
        page.click('[data-act=export-all]')
    spath = OUT + '/sicherung.zip'; dl.value.save_as(spath)
    znames = zipfile.ZipFile(spath).namelist()
    check('Export: Originalname der Datei', any(n.endswith('/P9 Stromkreis - 4 Kurzschluss - AB.pdf') for n in znames), [n for n in znames if 'Kurz' in n])
    page.evaluate("""async () => { const K = await T.keys('1234','pruefung123'); const d = await T.getData(K); d.faecher[0].jahrgaenge = []; d.faecher[1].jahrgaenge[0].reihen.reverse(); await T.putData(K, d); }""")
    page.reload()
    page.wait_for_selector('[data-act=import]')
    page.click('[data-act=unlock-p]'); page.wait_for_selector('dialog#sheet[open] input[name=pw]'); page.fill('input[name=pw]', 'pruefung123'); page.click('dialog#sheet button[value=ok]'); time.sleep(0.8)
    cur = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    def paths(o):
        out = set()
        if isinstance(o, dict):
            if isinstance(o.get('pfad'), str): out.add(o['pfad'])
            for v in o.values(): out |= paths(v)
        elif isinstance(o, list):
            for v in o: out |= paths(v)
        return out
    files_before = paths(cur)
    page.evaluate("document.querySelector('#toast').classList.remove('on')")
    with page.expect_file_chooser() as fc:
        page.click('[data-act=import]')
    fc.value.set_files(spath)
    page.wait_for_selector('dialog#sheet[open] input[name=modus]'); page.click('input[name=modus][value=ersetzen]')
    shot('15-ersetzen-dialog')
    page.click('dialog#sheet button[value=ok]')
    page.wait_for_function("document.querySelector('#toast').textContent.indexOf('Alte Dateien gelöscht') >= 0", timeout=120000); time.sleep(0.5)
    after = page.evaluate("async () => { const K = await T.keys('1234','pruefung123'); return T.getData(K); }")
    def norm(d):
        out = []
        for f in d['faecher']:
            out.append(('F', f['id'], f['name'], f.get('farbe'), f.get('extern'), f.get('vorlage')))
            for j in f['jahrgaenge']:
                out.append(('J', j['id'], j['name']))
                for r in j['reihen']:
                    out.append(('R', r['id'], r['titel'], r.get('ordner'), bool(r.get('titelbild')), bool(r.get('uebersicht') and r['uebersicht'].get('sus')), json.dumps(r.get('hinweis')), json.dumps(r.get('checkliste')), json.dumps(r.get('kurse'))))
                    for v in r['vorhaben']:
                        out.append(('V', v['titel'], bool(v.get('ausgeblendet')), v.get('ab'), json.dumps(v.get('planung')), json.dumps(v.get('kurse'), sort_keys=True)))
                        for m in v['materialien']:
                            out.append(('M', m['titel'], m['typ'], m['bereich'], bool(m.get('ausgeblendet')), bool(m.get('datei')), m.get('url'), (m.get('datei') or {}).get('schutz'), m.get('hash'), m.get('ab'), m.get('niveau'), json.dumps(m.get('kurse'), sort_keys=True)))
        return out
    nb, na = norm(before), norm(after)
    check('C: „Alles ersetzen“ stellt Stand verlustfrei wieder her', nb == na, [x for x in nb if x not in na][:5] + ['---'] + [x for x in na if x not in nb][:5])
    check('C: Datum/Hinweis/Checkliste in Sicherung', any(x[0]=='R' and x[7] != 'null' for x in na) and any(x[0]=='V' and x[3] for x in na) and any(x[0]=='M' and x[9] for x in na))
    check('C: Parallelkurse in Sicherung', any(x[0]=='R' and x[8] != 'null' for x in na) and any(x[0]=='V' and x[5] != 'null' for x in na))
    check('C: Notizen + Niveau in Sicherung', any(x[0]=='V' and x[4] != 'null' for x in na) and any(x[0]=='M' and x[10] for x in na))
    check('C: Buchaufgabe mit Hinweis in Sicherung', any(m.get('typ') == 'buch' and m.get('text') for f in after['faecher'] for j in f['jahrgaenge'] for r in j['reihen'] for v in r['vorhaben'] for m in v['materialien']))
    check('C: Trenner in Sicherung', any(m.get('typ') == 'tag' and m.get('titel') == 'Do 20.11.' for f in after['faecher'] for j in f['jahrgaenge'] for r in j['reihen'] for v in r['vorhaben'] for m in v['materialien']))
    check('C: Prüfung wiederhergestellt', any(x[0] == 'M' and x[2] == 'pruefung' and x[7] == 'pruefung' for x in na))
    ao_r = [r for f in after['faecher'] for j in f['jahrgaenge'] for r in j['reihen'] if r.get('titelseite')]
    check('C: Titelbild-Seite (Datei + Link) in Sicherung', any((r['titelseite'].get('datei') or {}).get('ext') == 'html' for r in ao_r) and any(r['titelseite'].get('url') == 'https://example.org/ao' for r in ao_r), [r.get('titelseite') for r in ao_r])
    check('C: alte Dateien gelöscht', not (files_before & set(k for k in repo if k.startswith('material/'))), sorted(files_before & set(repo)))
    shot('16-nach-ersetzen')


    # iPad-Größe Screenshot
    page.set_viewport_size({'width': 820, 'height': 1180})
    page.goto(SITE + '#/kurs/physik/8/optische-instrumente'); page.wait_for_selector('.rows'); time.sleep(0.6)
    shot('10-kurs-ipad')
    errors = [x for x in errors if 'serviceWorker' not in x]; check('Keine JS-Fehler', not errors, errors)
    br.close()

print('\n%d/%d bestanden' % (sum(1 for r in results if r[1]), len(results)))
