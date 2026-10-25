import os, sys, json, sqlite3, secrets, subprocess, threading, time, uuid, shutil, signal, re
from pathlib import Path
from contextlib import contextmanager, asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from engineering_features import TASK_TEMPLATES, TRANSLATIONS, dependency_audit, git_info, project_health, quality_gate

ROOT=Path(__file__).resolve().parent
WORKSPACE=Path(os.getenv('AGENT_WORKSPACE',str(ROOT/'workspace'))).resolve()
WORKSPACE.mkdir(parents=True,exist_ok=True)
DB=Path(os.getenv('AGENT_DB',str(ROOT/'agent_tasks.sqlite3')))
DB.parent.mkdir(parents=True,exist_ok=True)
ADMIN=os.getenv('ADMIN_PASSWORD','')
DEMO=os.getenv('MOCK_CODEX','0')=='1'
API_KEY=os.getenv('AGENT_API_KEY','')
READONLY_API_KEY=os.getenv('AGENT_READONLY_API_KEY','')
MAX_QUEUE_SIZE=max(1,int(os.getenv('AGENT_MAX_QUEUE_SIZE','100')))
SECRET_PATTERN=re.compile(r'(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|bot[_-]?token)(\s*[:=]\s*)([^\s,;]+)')
BEARER_PATTERN=re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+')

@asynccontextmanager
async def lifespan(_app):
    start_worker()
    yield

app=FastAPI(title='Engineering Agents', lifespan=lifespan)
security=HTTPBasic()
LOCK=threading.Lock()
@app.middleware('http')
async def security_headers(request:Request, call_next):
    response=await call_next(request)
    response.headers.setdefault('X-Content-Type-Options','nosniff')
    response.headers.setdefault('X-Frame-Options','DENY')
    response.headers.setdefault('Referrer-Policy','no-referrer')
    response.headers.setdefault('Permissions-Policy','camera=(), microphone=(), geolocation=()')
    if request.url.path.startswith('/api/') or request.url.path=='/':
        response.headers.setdefault('Cache-Control','no-store')
    return response
AGENTS={'coding':'Kod yozish / refactoring','testing':'Test va kod sifati','debug':'Xatoni topish va tuzatish','database':'DB migratsiya va so‘rovlar','browser':'Frontend / browser tahlili','devops':'Deploy rejasi va infratuzilma tahlili'}

def auth(request:Request):
    supplied=request.headers.get('X-Agent-Key','')
    if API_KEY and supplied and secrets.compare_digest(supplied,API_KEY): return 'api'
    if READONLY_API_KEY and supplied and secrets.compare_digest(supplied,READONLY_API_KEY): return 'readonly'
    import base64
    raw=request.headers.get('Authorization','')
    if not raw.startswith('Basic '):raise HTTPException(401,'Authentication required',headers={'WWW-Authenticate':'Basic'})
    try:
        user,password=base64.b64decode(raw[6:]).decode().split(':',1)
    except Exception:raise HTTPException(401,'Invalid credentials',headers={'WWW-Authenticate':'Basic'})
    if not ADMIN: raise HTTPException(503,'ADMIN_PASSWORD sozlanmagan')
    if not (secrets.compare_digest(user,'admin') and secrets.compare_digest(password,ADMIN)):
        raise HTTPException(401,'Login yoki parol xato',headers={'WWW-Authenticate':'Basic'})
    return 'admin'

def require_operator(role=Depends(auth)):
    if role=='readonly':
        raise HTTPException(403,'Read-only API key bu amal uchun yetarli emas')
    return role

def redact(value):
    text=str(value)
    text=SECRET_PATTERN.sub(r'\1\2[REDACTED]',text)
    return BEARER_PATTERN.sub(r'\1[REDACTED]',text)

@contextmanager
def connect():
    db=sqlite3.connect(DB,timeout=15)
    db.row_factory=sqlite3.Row
    try: yield db; db.commit()
    except Exception:
        db.rollback()
        raise
    finally: db.close()

def init():
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, agent TEXT, project TEXT, prompt TEXT, auto INTEGER, status TEXT, step TEXT, created REAL, updated REAL, result TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, at REAL, role TEXT, detail TEXT)')
        for column, definition in (('approval_required','INTEGER NOT NULL DEFAULT 0'),('approval_status',"TEXT NOT NULL DEFAULT 'not_required'")):
            try: db.execute(f'ALTER TABLE tasks ADD COLUMN {column} {definition}')
            except sqlite3.OperationalError as error:
                if 'duplicate column name' not in str(error): raise
        db.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_events_task_id ON events(task_id, id)')
init()
# A single in-process queue consumer keeps queued jobs recoverable across restarts.
# Jobs interrupted while running are NOT replayed automatically (code edits are not idempotent).
WORKER_STARTED=False
WORKER_GUARD=threading.Lock()
PROCESS_LOCK=threading.Lock()
ACTIVE_PROCESSES={}

def worker_loop():
    while True:
        try:
            with LOCK, connect() as db:
                row=db.execute("SELECT id FROM tasks WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
                if row:
                    db.execute("UPDATE tasks SET status='starting',updated=? WHERE id=? AND status='queued'",(time.time(),row['id']))
            if row:
                execute(row['id'])
            else:
                time.sleep(0.4)
        except Exception:
            # A transient database/worker error must not permanently kill the queue.
            time.sleep(1)

def start_worker():
    global WORKER_STARTED
    with WORKER_GUARD:
        if WORKER_STARTED:return
        with LOCK,connect() as db:
            db.execute("UPDATE tasks SET status='interrupted',result='Server restarted during task; inspect changes before retrying',updated=? WHERE status IN ('running','starting')",(time.time(),))
            db.execute("UPDATE tasks SET status='cancelled',result='Cancel request preserved through restart',updated=? WHERE status='cancel_requested'",(time.time(),))
        WORKER_STARTED=True
        threading.Thread(target=worker_loop,daemon=True,name='agent-queue-worker').start()

def event(task_id,role,detail):
    with LOCK,connect() as db:
        db.execute('INSERT INTO events(task_id,at,role,detail) VALUES(?,?,?,?)',(task_id,time.time(),role,redact(detail)[-9000:]))
        db.execute('UPDATE tasks SET step=?,updated=? WHERE id=?',(role,time.time(),task_id))

def status(task_id,state,result=''):
    with LOCK,connect() as db: db.execute('UPDATE tasks SET status=?, result=?,updated=? WHERE id=?',(state,redact(result)[-16000:],time.time(),task_id))

def project_dir(name):
    if not name or '/' in name or '\\' in name or name in ('.','..') or name.startswith('.'):
        raise HTTPException(400,'Noto‘g‘ri loyiha nomi')
    candidate=WORKSPACE/name
    if candidate.is_symlink():
        raise HTTPException(400,'Symbolic link loyiha sifatida ruxsat etilmaydi')
    p=candidate.resolve()
    if p.parent!=WORKSPACE or not p.is_dir(): raise HTTPException(400,'Loyiha faqat workspace ichidagi mavjud papka bo‘lishi kerak')
    return p

def stop_process(task_id):
    with PROCESS_LOCK:
        process=ACTIVE_PROCESSES.get(task_id)
    if not process or process.poll() is not None:
        return False
    try:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=False)
        else:
            os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception:
        process.kill()
    return True

def run_process(task_id, command, cwd, input_text='', timeout=420, env=None):
    kwargs=dict(cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env)
    if os.name=='nt':
        kwargs['creationflags']=subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session']=True
    process=subprocess.Popen(command,**kwargs)
    with PROCESS_LOCK:
        ACTIVE_PROCESSES[task_id]=process
    started=time.monotonic()
    sent=False
    try:
        while True:
            if is_cancelled(task_id):
                stop_process(task_id)
                return False,'Cancellation requested; subprocess stopped'
            if time.monotonic()-started>timeout:
                stop_process(task_id)
                return False,f'Process {timeout} soniyalik chegaradan oshdi'
            try:
                output,_=process.communicate(input=input_text if not sent else None,timeout=0.5)
                return process.returncode==0,output or ''
            except subprocess.TimeoutExpired:
                sent=True
    finally:
        with PROCESS_LOCK:
            ACTIVE_PROCESSES.pop(task_id,None)

class TaskIn(BaseModel):
    agent:str
    project:str
    prompt:str=Field(min_length=5,max_length=4000)
    auto:bool=True
    approval:bool=False

def codex(role,path,prompt,task_id):
    event(task_id,role,'Boshlanmoqda')
    if DEMO:
        if role=='coding':
            (path/'agent_output.txt').write_text('Mock agent: '+prompt+'\n',encoding='utf-8')
            return True,'MOCK_CODEX: test uchun agent_output.txt yaratildi'
        return True,'MOCK_CODEX: '+role+' bosqichi yakunlandi'
    if not shutil.which('codex'):
        return False,'codex CLI topilmadi. Codex o‘rnating va codex login qiling.'
    policy={'coding':'Faqat loyiha doirasida kod yoz yoki tahrirla. Boshqa loyihalarga tegma. Git push/deploy qilmang.',
            'debug':'Test loglariga asoslanib faqat xatolarni tuzat. Testlarni yashirma yoki o‘chirma.',
            'testing':'Kod va testlarni tahlil qil, kerak bo‘lsa test yoz. Barcha topilmalarni qayd et.',
            'database':'DB o‘zgarishlarini loyiha ichida tayyorla; jonli DBni o‘zgartirma.',
            'browser':'UI kodini tekshir; tashqi servisga login qilma.',
            'devops':'Faqat infra konfiguratsiyasini loyiha ichida tayyorla; server xizmatlari va deployni o‘zgartirma.'}
    text=f'Sen {role} agentsan. {policy[role]}\nVazifa: {prompt}\nYakunida o‘zgarishlar va cheklovlarni aniq yoz.'
    cmd=['codex','exec','--skip-git-repo-check','--sandbox','workspace-write','--ask-for-approval','never','--cd',str(path),'-']
    try:
        ok,output=run_process(task_id,cmd,path,input_text=text,timeout=420)
        output=output[-9000:]
        event(task_id,role,output or ('Exit: success' if ok else 'Exit: failed'))
        return ok,output
    except Exception as e: return False,f'{type(e).__name__}: {e}'

def test_project(path,task_id):
    event(task_id,'testing','Python pytest tekshiruvini boshladi')
    if not (path/'tests').is_dir():
        return None,'tests/ papkasi mavjud emas — avtomatik test o‘tkazilmadi.'
    try:
        ok,output=run_process(task_id,[sys.executable,'-m','pytest','-q','tests'],path,timeout=120,env={**os.environ,'PYTHONPATH':str(path)})
        log=output[-8000:]
        event(task_id,'testing',log)
        return ok,log
    except Exception as e: return False,f'{type(e).__name__}: {e}'

def execute(task_id):
    with connect() as db: row=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
    try:
        path=project_dir(row['project'])
        if row['approval_required'] and row['approval_status']!='approved':
            status(task_id,'awaiting_approval','Admin tasdig‘i kutilmoqda')
            return
        status(task_id,'running')
        if is_cancelled(task_id): status(task_id,'cancelled','Canceled before start');return
        role=row['agent']; ok,out=codex(role,path,row['prompt'],task_id)
        if is_cancelled(task_id): status(task_id,'cancelled','Cancellation requested; current step finished');return
        if not ok: status(task_id,'failed',out);return
        report=[f'{role}: {out[-3000:]}']
        # Agent handoff only for coding/debug, not side-effectful deploy or DB jobs.
        if row['auto'] and role in ('coding','debug'):
            if is_cancelled(task_id): status(task_id,'cancelled','Cancelled');return
            passed,logs=test_project(path,task_id)
            report.append('TEST: '+logs[-3000:])
            for attempt in range(2):
                if passed is not False: break
                if is_cancelled(task_id): status(task_id,'cancelled','Cancelled');return
                event(task_id,'handoff',f'Debug Agentga avtomatik topshirildi: {attempt+1}/2')
                ok,fix=codex('debug',path,'Quyidagi test xatolarini tuzat. Asl vazifa: '+row['prompt']+'\nTEST LOG:\n'+logs[-3500:],task_id)
                report.append('DEBUG: '+fix[-2500:])
                if not ok: status(task_id,'failed','\n'.join(report));return
                passed,logs=test_project(path,task_id)
                report.append('RETEST: '+logs[-2000:])
            if passed is False: status(task_id,'failed','\n'.join(report));return
            if passed is None: event(task_id,'warning','Testlar mavjud emas; natija test bilan tasdiqlanmadi')
            gate=quality_gate(path)
            report.append('QUALITY GATE: '+json.dumps(gate,ensure_ascii=False))
            if not gate['passed']:
                status(task_id,'failed','\n\n'.join(report));return
        if is_cancelled(task_id): status(task_id,'cancelled','Cancellation requested');return
        status(task_id,'completed','\n\n'.join(report))
        event(task_id,'done','Jarayon yakunlandi; productionga deploy qilinmadi')
    except Exception as e:
        event(task_id,'error',str(e));status(task_id,'failed',str(e))

def is_cancelled(task_id):
    with connect() as db:
        row=db.execute('SELECT status FROM tasks WHERE id=?',(task_id,)).fetchone()
    return bool(row and row['status']=='cancel_requested')

@app.post('/api/tasks/{task_id}/cancel')
def cancel_task(task_id:str,_:str=Depends(require_operator)):
    with LOCK,connect() as db:
        row=db.execute('SELECT status FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row:raise HTTPException(404,'Topilmadi')
        if row['status'] in ('queued','running','starting'):
            state='cancelled' if row['status']=='queued' else 'cancel_requested'
            db.execute('UPDATE tasks SET status=?,updated=? WHERE id=?',(state,time.time(),task_id))
        else:state=row['status']
    if state=='cancel_requested':
        stop_process(task_id)
    return {'id':task_id,'status':state}

@app.post('/api/tasks/{task_id}/approve')
def approve_task(task_id:str,_:str=Depends(require_operator)):
    with LOCK,connect() as db:
        row=db.execute('SELECT approval_required,approval_status FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row: raise HTTPException(404,'Topilmadi')
        if not row['approval_required']: raise HTTPException(400,'Bu task approval talab qilmaydi')
        if row['approval_status']!='pending': raise HTTPException(409,'Task approval holati allaqachon yakunlangan')
        db.execute("UPDATE tasks SET approval_status='approved',status='queued',updated=? WHERE id=?",(time.time(),task_id))
    return {'id':task_id,'status':'queued','approval_status':'approved'}

@app.post('/api/tasks/{task_id}/reject')
def reject_task(task_id:str,_:str=Depends(require_operator)):
    with LOCK,connect() as db:
        row=db.execute('SELECT approval_required,approval_status FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row: raise HTTPException(404,'Topilmadi')
        if not row['approval_required']: raise HTTPException(400,'Bu task approval talab qilmaydi')
        if row['approval_status']!='pending': raise HTTPException(409,'Task approval holati allaqachon yakunlangan')
        db.execute("UPDATE tasks SET approval_status='rejected',status='rejected',result=?,updated=? WHERE id=?",('Admin tomonidan rad etildi',time.time(),task_id))
    return {'id':task_id,'status':'rejected','approval_status':'rejected'}

@app.post('/api/tasks/{task_id}/retry')
def retry_task(task_id:str,_:str=Depends(require_operator)):
    with LOCK,connect() as db:
        row=db.execute('SELECT status,approval_required FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not row: raise HTTPException(404,'Topilmadi')
        if row['status'] not in ('failed','cancelled','interrupted','rejected'):
            raise HTTPException(409,'Faqat terminal task’ni retry qilish mumkin')
        state='awaiting_approval' if row['approval_required'] else 'queued'
        approval='pending' if row['approval_required'] else 'not_required'
        db.execute('UPDATE tasks SET status=?,step=?,result=?,approval_status=?,updated=? WHERE id=?',(state,'queue','Retry navbatga qo‘yildi',approval,time.time(),task_id))
    return {'id':task_id,'status':state,'approval_status':approval}

@app.get('/')
def home(_:str=Depends(auth)):return FileResponse(ROOT/'static/index.html')
@app.get('/dashboard')
def dashboard_page(_:str=Depends(auth)):return FileResponse(ROOT/'static/dashboard.html')
def section_page(_:str=Depends(auth)):return FileResponse(ROOT/'static/section.html')
for _section in ('projects','tasks','agents','workflows','servers','activity','notifications','settings'):
    app.add_api_route('/'+_section, section_page, methods=['GET'])
@app.get('/api/projects')
def projects(_:str=Depends(auth)):
    return {'projects':sorted(p.name for p in WORKSPACE.iterdir() if p.is_dir() and not p.is_symlink()),'agents':AGENTS,'mock':DEMO}
@app.get('/api/templates')
def templates(_:str=Depends(auth)):
    return TASK_TEMPLATES
@app.get('/api/i18n/{language}')
def i18n(language:str,_:str=Depends(auth)):
    if language not in TRANSLATIONS:
        raise HTTPException(404,'Til topilmadi')
    return TRANSLATIONS[language]
@app.get('/api/projects/{project}/health')
def health(project:str,_:str=Depends(auth)):
    return project_health(project_dir(project))
@app.get('/api/projects/{project}/quality')
def quality(project:str,_:str=Depends(auth)):
    return quality_gate(project_dir(project))
@app.get('/api/projects/{project}/dependencies')
def dependencies(project:str,_:str=Depends(auth)):
    return dependency_audit(project_dir(project))
@app.get('/api/projects/{project}/diff')
def project_diff(project:str,_:str=Depends(auth)):
    return git_info(project_dir(project))
@app.get('/api/metrics')
def metrics(_:str=Depends(auth)):
    with connect() as db:
        totals=db.execute('SELECT status,COUNT(*) AS n FROM tasks GROUP BY status').fetchall()
        avg=db.execute("SELECT AVG(updated-created) AS seconds FROM tasks WHERE status IN ('completed','failed','cancelled')").fetchone()
    return {'tasks_by_status':{row['status']:row['n'] for row in totals},
            'average_terminal_seconds':avg['seconds'] or 0,
            'queue_limit':MAX_QUEUE_SIZE}
@app.get('/api/dashboard')
def dashboard(_:str=Depends(auth)):
    with connect() as db:
        counts=db.execute('SELECT status,COUNT(*) AS n FROM tasks GROUP BY status').fetchall()
        tasks=db.execute('SELECT id,agent,project,status,step,created,updated FROM tasks ORDER BY created DESC LIMIT 12').fetchall()
        approvals=db.execute("SELECT id,agent,project,status,created,updated FROM tasks WHERE status='awaiting_approval' ORDER BY created DESC LIMIT 10").fetchall()
        activity=db.execute('SELECT e.task_id,e.at,e.role,e.detail,t.project,t.agent FROM events e LEFT JOIN tasks t ON t.id=e.task_id ORDER BY e.id DESC LIMIT 20').fetchall()
        running=db.execute("SELECT agent,COUNT(*) AS n FROM tasks WHERE status IN ('queued','starting','running') GROUP BY agent").fetchall()
    count_map={row['status']:row['n'] for row in counts}
    active_agents={row['agent']:('running' if row['n'] else 'idle') for row in running}
    agent_state={key:active_agents.get(key,'idle') for key in AGENTS}
    return {
        'metrics': {
            'active_tasks':count_map.get('running',0)+count_map.get('starting',0),
            'queued_tasks':count_map.get('queued',0),
            'completed_tasks':count_map.get('completed',0),
            'failed_tasks':count_map.get('failed',0),
            'awaiting_approval':count_map.get('awaiting_approval',0),
        },
        'tasks':[dict(row) for row in tasks],
        'approvals':[dict(row) for row in approvals],
        'activity':[dict(row) for row in activity],
        'agents': [{'name':key,'label':label,'status':agent_state[key]} for key,label in AGENTS.items()],
        'workers':[{'name':'local-worker','status':'online' if WORKER_STARTED else 'offline','codex_available':bool(shutil.which('codex')),'current_tasks':count_map.get('running',0)+count_map.get('starting',0)}],
        'n8n': {'configured':bool(os.getenv('N8N_BASE_URL')),'status':'configured' if os.getenv('N8N_BASE_URL') else 'not_configured'},
    }
@app.get('/api/tasks')
def list_tasks(_:str=Depends(auth)):
    with connect() as db:return [dict(x) for x in db.execute('SELECT id,agent,project,status,step,created,updated FROM tasks ORDER BY created DESC LIMIT 30')]
@app.get('/api/tasks/terminal')
def terminal_tasks(after:float=0,_:str=Depends(auth)):
    with connect() as db:
        rows=db.execute("SELECT id,agent,project,status,step,created,updated,result FROM tasks WHERE status IN ('completed','failed','cancelled','interrupted') AND updated>? ORDER BY updated ASC LIMIT 100",(after,)).fetchall()
    return {'items':[dict(row) for row in rows],'cursor':max((row['updated'] for row in rows),default=after)}
@app.get('/api/tasks/{task_id}')
def get_task(task_id:str,_:str=Depends(auth)):
    with connect() as db:
        t=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not t:raise HTTPException(404,'Topilmadi')
        es=db.execute('SELECT at,role,detail FROM events WHERE task_id=? ORDER BY id',(task_id,)).fetchall()
        return {'task':dict(t),'events':[dict(x) for x in es]}
@app.get('/api/tasks/{task_id}/stream')
def stream_task(task_id:str,_:str=Depends(auth)):
    with connect() as db:
        if not db.execute('SELECT 1 FROM tasks WHERE id=?',(task_id,)).fetchone():
            raise HTTPException(404,'Topilmadi')
    def generate():
        last_updated=None
        for _ in range(120):
            with connect() as db:
                row=db.execute('SELECT status,step,updated,result FROM tasks WHERE id=?',(task_id,)).fetchone()
            if not row: break
            if row['updated']!=last_updated:
                last_updated=row['updated']
                payload=json.dumps(dict(row),ensure_ascii=False)
                yield f'event: task\\ndata: {payload}\\n\\n'
            if row['status'] in ('completed','failed','cancelled','interrupted'):
                break
            time.sleep(1)
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
@app.post('/api/tasks',status_code=201)
def submit(data:TaskIn,_:str=Depends(require_operator)):
    if data.agent not in AGENTS:raise HTTPException(400,'Agent noma’lum')
    project_dir(data.project)
    prompt=data.prompt.strip()
    if len(prompt)<5:raise HTTPException(422,'Vazifa matni kamida 5 ta belgi boвЂlishi kerak')
    tid=uuid.uuid4().hex[:14];now=time.time()
    initial_status='awaiting_approval' if data.approval else 'queued'
    approval_status='pending' if data.approval else 'not_required'
    with LOCK,connect() as db:
        active=db.execute("SELECT COUNT(*) AS n FROM tasks WHERE status IN ('queued','starting','running','cancel_requested')").fetchone()['n']
        if active>=MAX_QUEUE_SIZE:
            raise HTTPException(429,f'Vazifalar navbati to\u02bbldi. Limit: {MAX_QUEUE_SIZE}')
        db.execute('INSERT INTO tasks (id,agent,project,prompt,auto,status,step,created,updated,result,approval_required,approval_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(tid,data.agent,data.project,prompt,int(data.auto),initial_status,'queue',now,now,'',int(data.approval),approval_status))
    return {'id':tid,'status':initial_status,'approval_status':approval_status}
