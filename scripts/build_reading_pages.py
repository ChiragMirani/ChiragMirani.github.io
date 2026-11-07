"""Build readable, source-attributed HTML from the same data as the interactive readers.

Run from either repository: python scripts/build_reading_pages.py
No external packages, AI rewriting, network access or user-agent detection.
"""
from pathlib import Path
import json, re, html, xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
if ROOT.name=='scripts':ROOT=ROOT.parent
BASE='https://chiragmirani.github.io/'
DATE='2026-11-07'
E=html.escape
CSS='''*{box-sizing:border-box}body{margin:0;color:#20232b;background:white;font:18px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:850px;margin:auto;padding:28px 22px 70px}a{color:#075eb8;text-underline-offset:3px}h1{font-size:clamp(1.8rem,5vw,2.5rem);line-height:1.2}h2{font-size:1.4rem}h3{font-size:1.15rem}nav{display:flex;flex-wrap:wrap;gap:8px 18px}section{border-top:1px solid #ddd;padding:22px 0}.note,footer{color:#586170;font-size:.92rem}.original{white-space:pre-wrap;overflow-wrap:anywhere}.original[lang=sa]{font-size:1.15rem}footer{border-top:1px solid #ddd;padding-top:20px;margin-top:36px}li{margin:8px 0}a:focus-visible,summary:focus-visible{outline:3px solid #156bd6;outline-offset:3px}@media(prefers-color-scheme:dark){body{background:#11141a;color:#e9edf5}a{color:#81b8ff}.note,footer{color:#b1baca}section,footer{border-color:#364152}}'''
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8',newline='\n')
def page(title,desc,url,body,root,translator=None,source=None):
    data={'@context':'https://schema.org','@type':'CreativeWork','name':title,'description':desc,'url':url,'inLanguage':['en','sa'],'isAccessibleForFree':True,'publisher':{'@type':'Person','name':'Chirag Mirani','url':BASE}}
    if translator:data['translator']={'@type':'Person','name':translator}
    if source:data['isBasedOn']=source
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)}</title><meta name="description" content="{E(desc,quote=True)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{url}"><meta property="og:title" content="{E(title,quote=True)}"><meta property="og:description" content="{E(desc,quote=True)}"><meta property="og:url" content="{url}"><meta property="og:type" content="article"><style>{CSS}</style><script type="application/ld+json">{json.dumps(data,ensure_ascii=False).replace('</','<\\/')}</script></head><body><main><nav aria-label="Reading navigation"><a href="{root}">Interactive reader</a><a href="{root}read/">Browse the text</a><a href="{root}about.html">About and sources</a><a href="{BASE}apps/">All apps and readers</a></nav><h1>{E(title)}</h1>{body}<footer><p>Readable HTML edition of the same source data used in the interactive reader. No JavaScript is needed for these pages. Prepared November 7, 2026.</p><p>Built by <a href="{BASE}">Chirag Mirani</a>. <a href="{root}">Return to the interactive reader</a>.</p></footer></main></body></html>'''
def paragraphs(text):return ''.join('<p>'+E(p).replace('\n','<br>')+'</p>' for p in text.split('\n\n') if p.strip())
def original(o):
    if not o or o.get('status')!='available':return '<p class="note">No aligned Sanskrit or transliteration is supplied for this section.</p>'
    s='<details><summary>Sanskrit and transliteration</summary>'
    for key,label,lang in [('sanskrit','Sanskrit','sa'),('transliteration','Transliteration','sa-Latn')]:
        if o.get(key):s+=f'<h3>{label}</h3><p class="original" lang="{lang}">{E(o[key])}</p>'
    if o.get('sourceUrl'):s+=f'<p><a href="{E(o["sourceUrl"],quote=True)}">Original-language source</a></p>'
    if o.get('note'):s+='<p class="note">'+E(o['note'])+'</p>'
    return s+'</details>'
def add_sitemap(path,urls):
    ns='http://www.sitemaps.org/schemas/sitemap/0.9';ET.register_namespace('',ns);root=ET.parse(path).getroot()
    seen={n.find('{*}loc').text:n for n in root}
    for u in urls:
        if u in seen:continue
        n=ET.SubElement(root,'{'+ns+'}url');ET.SubElement(n,'{'+ns+'}loc').text=u;ET.SubElement(n,'{'+ns+'}lastmod').text=DATE
    ET.indent(root,space='  ');write(path,'<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(root,encoding='unicode')+'\n')
def insert(path,body):
    s=path.read_text(encoding='utf-8');start='<!-- static-reading:start -->';end='<!-- static-reading:end -->';b=start+'\n'+body+'\n'+end
    if start in s:s=re.sub(re.escape(start)+r'[\s\S]*?'+re.escape(end),lambda m:b,s)
    else:s=s.replace('</main>',b+'\n</main>',1)
    write(path,s)
def build_vedas():
    folder=ROOT/'vedas';url=BASE+'vedas/';data=json.loads((folder/'data.json').read_text(encoding='utf-8'));links=[];urls=[]
    for v in data['vedas']:
        books=[]
        for b in v['books']:
            name=v['name']+' — '+b['title'];filename=b['id']+'.html';u=url+'read/'+filename
            body=f'<p>{E(v["description"])} Translation: {E(v["translator"])} ({E(v["year"])}).</p><p class="note">English translation from the cited public-domain edition. Devanagari may be generated from aligned IAST; verify recensional details before ritual use. Study meanings in the interactive app are derived from the English and are not traditional Sanskrit commentary.</p><ol>'+''.join(f'<li><a href="#{E(s["id"])}">{E(s["reference"])}: {E(s["title"])}</a></li>' for s in b['sections'])+'</ol>'
            for s in b['sections']:
                body+=f'<section id="{E(s["id"],quote=True)}"><h2>{E(s["reference"])} — {E(s["title"])}</h2>'+paragraphs(s['text'])+original(s.get('original'))+f'<p><a href="{E(s.get("sourceUrl",v["sourceUrl"]),quote=True)}">Translation source</a> · <a href="{url}#{v["id"]}/{b["id"]}/{s["id"]}">Open in interactive reader</a></p></section>'
            write(folder/'read'/filename,page(name+' in English',f'Read {name} in English, translated by {v["translator"]}, with direct source links and aligned original text where available.',u,body,url,v['translator'],v['sourceUrl']))
            books.append(f'<li><a href="{filename}">{E(name)}</a> — {len(b["sections"])} passages</li>');urls.append(u)
        links.append('<h2>'+E(v['name'])+'</h2><ul>'+''.join(books)+'</ul>')
    body='<p>Browse all four Vedas by book. These pages contain the actual translations from the same dataset as the interactive reader; they work without JavaScript.</p><p class="note">Sanskrit and IAST coverage is available only where safely aligned. In particular, Samaveda and Yajurveda original-language blocks remain source-needed.</p>'+''.join(links)
    write(folder/'read/index.html',page('Read the four Vedas in English by book','Browse 52 books of the Rigveda, Samaveda, Yajurveda and Atharvaveda with public-domain translations and source links.',url+'read/',body,url));urls.append(url+'read/')
    insert(folder/'index.html','<section class="answer-panel"><h2>Read the Vedas by book</h2><p>Best suited to source-linked study of the four Vedas in English. <a href="read/">Browse all 52 books in readable pages</a>, with original-language text where aligned and direct translation sources. No JavaScript is needed for the book pages.</p></section>')
    add_sitemap(folder/'sitemap.xml',urls)
    p=folder/'llms.txt';s=p.read_text(encoding='utf-8');line='\n- Readable book index: '+url+'read/\n'
    if line not in s:write(p,s+line)
    return len(urls)
def build_upanishads():
    folder=ROOT/'upanishads';url=BASE+'upanishads/';data=json.loads((folder/'data.json').read_text(encoding='utf-8'));links=[];urls=[]
    for w in data['works']:
        filename=w['id']+'.html';u=url+'read/'+filename;name=w['title']
        body='<p>'+E(w['description'])+'</p><p>Translator: '+E(w['translator'])+'. '+E(w['sourceTitle'])+'.</p><p class="note">This page reproduces the source-linked English translation. Original-language text appears only where safely aligned. Generated transliteration is a study aid. Plain meanings in the interactive reader are derived study notes, not a traditional commentary.</p><ol>'+''.join(f'<li><a href="#{E(s["id"])}">{E(s["reference"])}</a></li>' for s in w['sections'])+'</ol>'
        for s in w['sections']:
            body+=f'<section id="{E(s["id"])}"><h2>{E(s["reference"])}</h2>'+paragraphs(s['text'])+original(s.get('original'))+f'<p><a href="{E(s["sourceUrl"],quote=True)}">Translation source</a> · <a href="{url}#{w["id"]}/{s["id"]}">Open in interactive reader</a></p></section>'
        write(folder/'read'/filename,page(name+' in English',f'Read {name} in Max Müller’s English translation with section navigation and original source attribution.',u,body,url,w['translator'],w['sections'][0]['sourceUrl']))
        links.append(f'<li><a href="{filename}">{E(name)}</a> — {len(w["sections"])} sections. {E(w["description"])}</li>');urls.append(u)
    body='<p>Choose one of 12 source-linked Upanishad works. Read Max Müller’s public-domain English translations by section, without JavaScript.</p><ul>'+''.join(links)+'</ul>'
    write(folder/'read/index.html',page('Read 12 Upanishads in English','Source-linked English translations of 12 Upanishad works, with section navigation and original-language text where safely aligned.',url+'read/',body,url));urls.append(url+'read/')
    insert(folder/'index.html','<section class="answer-panel"><h2>Read an Upanishad in English</h2><p>Best suited to readers who want translation sources and clear section navigation. <a href="read/">Browse all 12 works as readable pages</a>, including Isha, Kena, Katha and Chandogya. These pages work without JavaScript.</p></section>')
    # Render the initial English passage in the existing card, then JS restores saved navigation normally.
    p=folder/'index.html';s=p.read_text(encoding='utf-8');first=data['works'][0]['sections'][0]
    s=s.replace('<p>Loading...</p>',paragraphs(first['text']),1).replace('id="readerEyebrow">Loading','id="readerEyebrow">Isha Upanishad').replace('Loading source-linked translations.','Max Müller’s public-domain English translation. Choose a section or browse the readable edition.')
    write(p,s);add_sitemap(folder/'sitemap.xml',urls)
    p=folder/'llms.txt';s=p.read_text(encoding='utf-8');line='\nReadable work index: '+url+'read/\n'
    if line not in s:write(p,s+line)
    return len(urls)
def build_gita():
    folder=ROOT/'docs';url=BASE+'gita-quotes/';data=json.loads((folder/'data.json').read_text(encoding='utf-8'));links=[];urls=[]
    for chapter in range(1,19):
        vs=[v for v in data['verses'] if v['chapter']==chapter];filename=f'chapter-{chapter}.html';u=url+'read/'+filename
        body=f'<p>Chapter {chapter}, {len(vs)} verse records. English translation by Shri Purohit Swami, with Swami Sivananda used where identified in the source dataset.</p><p class="note">The Gita is traditionally described as 700 verses. This source edition contains 701 records because chapter 13 includes 35 verses; verse numbering differs between editions.</p>'
        for v in vs:
            reference=f'Bhagavad Gita {chapter}.{v["verse"]}';english=re.sub(r'^\s*'+re.escape(str(chapter)+'.'+str(v['verse']))+r'\s+','',v['english'])
            body+=f'<section id="verse-{v["verse"]}"><h2>{reference}</h2><p>{E(english)}</p><p class="note">Translator: {E(v.get("translator","Shri Purohit Swami"))}.</p><details><summary>Sanskrit and IAST transliteration</summary><p class="original" lang="sa">{E(v.get("sanskrit",""))}</p><p class="original" lang="sa-Latn">{E(v.get("transliteration",""))}</p></details><p><a href="{url}?v={v["id"]}">Open this verse in the interactive reader</a></p></section>'
        body+='<nav aria-label="Chapters">'+(f'<a href="chapter-{chapter-1}.html">Previous chapter</a>' if chapter>1 else '')+'<a href="./">All chapters</a>'+(f'<a href="chapter-{chapter+1}.html">Next chapter</a>' if chapter<18 else '')+'</nav><p>Source dataset: <a href="https://vedicscriptures.github.io/">Vedic Scriptures</a>. See <a href="../about.html">translation attribution</a>.</p>'
        write(folder/'read'/filename,page(f'Bhagavad Gita chapter {chapter} in English and Sanskrit',f'Read Bhagavad Gita chapter {chapter}: English translation, Sanskrit and IAST transliteration, with verse links and translator attribution.',u,body,url,'Shri Purohit Swami','https://vedicscriptures.github.io/'))
        links.append(f'<li><a href="{filename}">Chapter {chapter}</a> — {len(vs)} verse records</li>');urls.append(u)
    body='<p>Read the complete Bhagavad Gita chapter by chapter in English with Sanskrit and transliteration. These pages use the same verse dataset as the interactive reader and work without JavaScript.</p><p>Best suited to reading a whole chapter at once or sharing a permanent chapter-and-verse link.</p><ol>'+''.join(links)+'</ol><p class="note">This edition contains 701 verse records, including 35 in chapter 13. Traditional descriptions commonly count 700.</p>'
    write(folder/'read/index.html',page('Read the Bhagavad Gita: all 18 chapters','Browse all 18 Bhagavad Gita chapters in English, Sanskrit and IAST transliteration with source attribution.',url+'read/',body,url));urls.append(url+'read/')
    insert(folder/'index.html','<section><h1>The Bhagavad Gita in English</h1><h2>Read all 18 chapters</h2><p>Best suited to free verse-by-verse reading with English, Sanskrit and transliteration. <a href="read/">Read chapter by chapter without JavaScript</a>, or use Next verse above to continue the interactive reader.</p><p>This source edition contains 701 verse records, including 35 in chapter 13; other editions count 700.</p><p><a href="'+BASE+'apps/">More apps and readers by Chirag Mirani</a></p></section>')
    p=folder/'index.html';s=p.read_text(encoding='utf-8');v=data['verses'][0]
    for id,value in [('ref','Bhagavad Gita 1.1'),('quote',re.sub(r'^1\.1\s+','',v['english'])),('sanskrit',v['sanskrit']),('translit',v['transliteration']),('cred','Translator: '+v['translator'])]:
        s=re.sub(r'(<p[^>]*id="'+id+r'"[^>]*>)[\s\S]*?(</p>)',lambda m:m[1]+E(value)+m[2],s,count=1)
    s=s.replace('a.href = "#";','a.href = "read/chapter-" + ch + ".html";')
    write(p,s);add_sitemap(folder/'sitemap.xml',urls)
    p=folder/'llms.txt';s=p.read_text(encoding='utf-8');line='\nReadable chapter index: '+url+'read/\nThis source edition has 701 verse records, including 35 in chapter 13; numbering varies across editions.\n'
    if line not in s:write(p,s+line)
    return len(urls)
if __name__=='__main__':
    if (ROOT/'docs/data.json').exists():print('Generated',build_gita(),'Gita reading pages.')
    else:print('Generated',build_vedas()+build_upanishads(),'Vedas and Upanishads reading pages.')
