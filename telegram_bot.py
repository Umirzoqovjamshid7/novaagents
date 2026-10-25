"""Telegram long-polling control interface. Run separately, one instance only."""
import json, os, time, urllib.parse, urllib.request, urllib.error
from integrations import api
TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','')
ALLOW={int(x.strip()) for x in os.getenv('TELEGRAM_ALLOWED_IDS','').split(',') if x.strip().isdigit()}
BASE=f'https://api.telegram.org/bot{TOKEN}/'
SESSIONS={}  # in-memory conversation drafts; tasks remain persisted in backend

def tg(method, data):
    req=urllib.request.Request(BASE+method,data=urllib.parse.urlencode(data).encode(),method='POST')
    with urllib.request.urlopen(req,timeout=45) as r: return json.load(r)

def send(chat,text):
    for n in range(0,len(text),3800):
        tg('sendMessage',{'chat_id':chat,'text':text[n:n+3800]})

def command_arg(raw, command):
    value=raw[len(command):].strip()
    if not value:
        raise ValueError(f'Format: {command} TASK_ID')
    return value

def menu(chat):
    data=api('/api/projects')
    projects=data['projects'][:20]
    if not projects:
        send(chat,'Workspace ichida hech qanday loyiha mavjud emas.');return
    keys=[[{'text':p,'callback_data':'proj:'+p}] for p in projects if len(p)<55]
    tg('sendMessage',{'chat_id':chat,'text':'Loyihani tanlang:','reply_markup':json.dumps({'inline_keyboard':keys})})

def callback(query):
    user=query.get('from',{}).get('id');chat=query['message']['chat']['id']
    tg('answerCallbackQuery',{'callback_query_id':query['id']})
    if user not in ALLOW:return
    value=query.get('data','');state=SESSIONS.setdefault(user,{})
    if value.startswith('proj:'):
        p=value[5:]
        if p not in api('/api/projects')['projects']:return
        state.clear();state['project']=p
        agents=api('/api/projects')['agents']
        keys=[[{'text':key,'callback_data':'agent:'+key}] for key in agents]
        tg('sendMessage',{'chat_id':chat,'text':f'{p}: agentni tanlang','reply_markup':json.dumps({'inline_keyboard':keys})})
    elif value.startswith('agent:') and state.get('project'):
        agent=value[6:]
        if agent not in api('/api/projects')['agents']:return
        state['agent']=agent
        keys=[[{'text':'Avtomatik handoff','callback_data':'mode:auto'},{'text':'Faqat shu agent','callback_data':'mode:manual'}]]
        tg('sendMessage',{'chat_id':chat,'text':'Ish tartibini tanlang:','reply_markup':json.dumps({'inline_keyboard':keys})})
    elif value.startswith('mode:') and state.get('agent'):
        state['auto']=value=='mode:auto';state['awaiting_prompt']=True
        send(chat,'Endi vazifa matnini yuboring. Bekor qilish uchun /new bosing.')

def fmt(task):
    t=task['task']
    return f"#{t['id']} | {t['status']}\nAgent: {t['agent']}\nLoyiha: {t['project']}\nBosqich: {t['step']}\n\n{(t.get('result') or '')[-2500:]}"

def process(msg):
    user=msg.get('from',{}).get('id'); chat=msg['chat']['id']; raw=(msg.get('text') or '').strip()
    if user not in ALLOW:
        send(chat,'Ruxsat yo‘q. Telegram user ID ni administratorga yuboring.');return
    if raw.startswith('/new'):
        SESSIONS.pop(user,None);menu(chat)
    elif raw.startswith('/start') or raw.startswith('/help'):
        send(chat,'Engineering Agents\n/new — tugmalar orqali yangi vazifa\n/projects — loyihalar\n/tasks — oxirgi vazifalar\n/status TASK_ID — holat\n/cancel TASK_ID — bekor qilish so‘rovi\n/run PROJECT AGENT auto|manual | VAZIFA — yangi vazifa\n\nMasalan:\n/run sample coding auto | FastAPI uchun test yoz')
    elif raw.startswith('/projects'):
        p=api('/api/projects');send(chat,'Loyihalar: '+', '.join(p['projects'])+'\nAgentlar: '+', '.join(p['agents']))
    elif raw.startswith('/tasks'):
        ts=api('/api/tasks'); send(chat,'\n'.join(f"{t['id']} {t['agent']} {t['project']} {t['status']}" for t in ts[:12]) or 'Hali vazifa yo‘q')
    elif raw.startswith('/status '):
        try:id=command_arg(raw,'/status')
        except ValueError as e:send(chat,str(e));return
        send(chat,fmt(api('/api/tasks/'+urllib.parse.quote(id,safe=''))))
    elif raw.startswith('/cancel '):
        try:id=command_arg(raw,'/cancel')
        except ValueError as e:send(chat,str(e));return
        result=api('/api/tasks/'+urllib.parse.quote(id,safe='')+'/cancel','POST');send(chat,f"#{id}: {result['status']}")
    elif raw.startswith('/run '):
        try:
            head,prompt=raw[5:].split('|',1)
            project,agent,mode=head.strip().split()
            if mode not in ('auto','manual'):raise ValueError()
            result=api('/api/tasks','POST',{'project':project,'agent':agent,'auto':mode=='auto','prompt':prompt.strip()})
            send(chat,'Vazifa yaratildi: '+result['id']+'\n/status '+result['id'])
        except (ValueError, KeyError):send(chat,'Format: /run PROJECT AGENT auto|manual | VAZIFA')
    elif SESSIONS.get(user,{}).get('awaiting_prompt') and not raw.startswith('/'):
        state=SESSIONS[user]
        if len(raw)<5 or len(raw)>4000:
            send(chat,'Vazifa matni 5–4000 belgi bo‘lishi kerak.');return
        result=api('/api/tasks','POST',{'project':state['project'],'agent':state['agent'],'auto':state['auto'],'prompt':raw})
        SESSIONS.pop(user,None)
        send(chat,'Vazifa yaratildi: '+result['id']+'\n/status '+result['id'])
    else:send(chat,'Noma’lum buyruq. /help')

def main():
    if not TOKEN or not ALLOW:raise SystemExit('TELEGRAM_BOT_TOKEN va TELEGRAM_ALLOWED_IDS kerak')
    print('Telegram bot ishga tushdi (allowed users:',len(ALLOW),')',flush=True)
    offset=None
    while True:
        try:
            data={'timeout':25,'allowed_updates':json.dumps(['message','callback_query'])}
            if offset is not None:data['offset']=offset
            for update in tg('getUpdates',data).get('result',[]):
                offset=update['update_id']+1
                if 'callback_query' in update:
                    try:callback(update['callback_query'])
                    except Exception as e:print('Callback error:',repr(e),flush=True)
                if 'message' in update:
                    try:process(update['message'])
                    except Exception as e:
                        print('Message error:',repr(e),flush=True)
                        try:send(update['message']['chat']['id'],'Xatolik: serverda tekshirish kerak')
                        except Exception:pass
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print('Polling network error:',str(e),flush=True);time.sleep(5)

if __name__=='__main__':main()
