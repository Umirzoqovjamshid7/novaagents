"""Shared API client for Telegram and n8n adapters; stdlib only."""
import json, os, time, urllib.request, urllib.error
BASE=os.getenv('AGENT_API_URL','http://127.0.0.1:8765').rstrip('/')
KEY=os.getenv('AGENT_API_KEY','')

def api(path, method='GET', payload=None, retries=3):
    if not KEY: raise RuntimeError('AGENT_API_KEY missing')
    body=json.dumps(payload).encode() if payload is not None else None
    for attempt in range(retries+1):
        req=urllib.request.Request(BASE+path,data=body,method=method,headers={'X-Agent-Key':KEY,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code<500 or attempt>=retries:
                raise RuntimeError(f'API HTTP {e.code}: {e.read(300).decode(errors="replace")}') from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt>=retries: raise RuntimeError(f'API network error: {e}') from e
        time.sleep(min(2**attempt,8))
