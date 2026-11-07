"""Refresh on any day; issue only inside the frozen Friday/Saturday window.

Run with --download to fetch new public inputs first. Publishing the generated
public_site/treasury-signal directory is a separate authenticated operation.
"""
import argparse
import json
from datetime import datetime,timezone
import download_data as D
import production_signal as P
import paper_signal_preview as R
import build_public_page as B


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download',action='store_true')
    args=parser.parse_args();now=datetime.now(timezone.utc)
    if args.download:
        try:D.download_snapshot()
        except Exception as exc:
            P.write_json(P.M.OUT/'refresh_error.json',{'checked_at_utc':now.isoformat(),'error':str(exc)})
            B.build()
            raise
    page=P.main()
    try:R.preview()
    except Exception as exc:
        # Preserve the last complete illustration and report the failure separately.
        P.write_json(P.M.OUT/'refresh_error.json',{'checked_at_utc':now.isoformat(),'error':str(exc)})
    B.build()
    print('Built public page. Issue status:',page['status'])


if __name__=='__main__':main()
