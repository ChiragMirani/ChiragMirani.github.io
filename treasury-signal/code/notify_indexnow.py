"""Notify participating search engines after verifying a GitHub Pages deployment.

The public verification file is scoped to /treasury-signal/. This notification
requests discovery; acceptance is not a guarantee of indexing or AI citations.
No account credentials, private data or model inputs are transmitted.
"""
import argparse
import json
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parent
BASE='https://chiragmirani.github.io/treasury-signal/'
KEYFILE='indexnow-key.txt'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper',action='store_true',help='Also notify updates to the paper and its PDF')
    args=parser.parse_args()
    key=(ROOT/'public_site/treasury-signal'/KEYFILE).read_text().strip()
    with urlopen(BASE+KEYFILE,timeout=30) as response:
        if response.read().decode().strip()!=key:
            raise RuntimeError('Published verification file does not match; deploy before notifying.')
    urls=[BASE]
    if args.paper:urls += [BASE+'paper/',BASE+'paper/treasury-signal-preprint.pdf']
    payload={'host':'chiragmirani.github.io','key':key,'keyLocation':BASE+KEYFILE,'urlList':urls}
    request=Request('https://api.indexnow.org/indexnow',data=json.dumps(payload).encode(),
                    headers={'Content-Type':'application/json; charset=utf-8','User-Agent':'TreasuryResearchPublisher/1.0'},method='POST')
    with urlopen(request,timeout=30) as response:
        result={'http_status':response.status,'urls':urls,'meaning':'Notification received; indexing and citations are not guaranteed.'}
    (ROOT/'results/indexnow_receipt.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__=='__main__':main()
