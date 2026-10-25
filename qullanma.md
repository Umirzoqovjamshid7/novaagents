# NOVA Engineering Agents — n8n ulash va ishga tushirish qo‘llanmasi

Bu qo‘llanma NOVA FastAPI backend’ini n8n bilan ulash, task yuborish va task tugaganda Telegram notification olish uchun yozilgan.

## 1. Ishlash sxemasi

```text
n8n Webhook / Schedule
        │
        │ X-Agent-Key
        ▼
NOVA FastAPI → SQLite task queue → Codex/pytest worker
        │
        ▼
n8n terminal-task polling → Telegram notification
```

n8n alohida task bazasidan foydalanmaydi. Telegram, admin panel va n8n bitta NOVA API hamda bitta SQLite bazasidan foydalanadi.

## 2. Kerakli komponentlar

- Python 3.10 yoki undan yangi
- NOVA loyiha papkasi
- FastAPI dependencies
- n8n instance
- Telegram bot va Telegram chat ID — notification kerak bo‘lsa
- `AGENT_API_KEY` — n8n backend’ga kirish uchun

## 3. NOVA backend’ni Windows’da ishga tushirish

PowerShell’da loyiha papkasiga kiring:

```powershell
cd D:\agent
```

Environment variable’larni belgilang:

```powershell
$env:ADMIN_PASSWORD = 'uzun-admin-parol'
$env:AGENT_API_KEY = 'uzun-random-api-key'
$env:AGENT_WORKSPACE = 'D:\agent\workspace'
$env:AGENT_MAX_QUEUE_SIZE = '100'
```

Test rejimi uchun:

```powershell
$env:MOCK_CODEX = '1'
```

`MOCK_CODEX=1` faqat local test uchun. Real Codex ishlatishda bu variable’ni o‘rnating yoki olib tashlang.

Dependencies o‘rnatish:

```powershell
python -m pip install -r requirements.txt
```

Backend’ni ishga tushirish:

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Panel:

```text
http://127.0.0.1:8765/
```

Dashboard:

```text
http://127.0.0.1:8765/dashboard
```

Swagger API:

```text
http://127.0.0.1:8765/docs
```

## 4. API key yaratish

PowerShell’da random key yaratish:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Chiqqan qiymatni `$env:AGENT_API_KEY` sifatida belgilang. API key’ni Git’ga, n8n workflow JSON’iga yoki frontend kodiga yozmang.

Read-only monitoring uchun alohida key:

```powershell
$env:AGENT_READONLY_API_KEY = 'boshqa-read-only-key'
```

Read-only key GET endpointlarga ishlaydi, lekin task yaratish, cancel, approve, reject va retry qila olmaydi.

## 5. Backend API’ni tekshirish

PowerShell:

```powershell
$headers = @{ 'X-Agent-Key' = $env:AGENT_API_KEY }
Invoke-RestMethod `
  -Uri 'http://127.0.0.1:8765/api/projects' `
  -Headers $headers
```

Kutiladigan natija ichida `sample` project va agentlar bo‘ladi.

Task yuborish testi:

```powershell
$body = @{
  project = 'sample'
  agent = 'coding'
  prompt = 'Calculator uchun testlarni tekshir'
  auto = $true
  approval = $false
} | ConvertTo-Json

$task = Invoke-RestMethod `
  -Uri 'http://127.0.0.1:8765/api/tasks' `
  -Method Post `
  -Headers $headers `
  -ContentType 'application/json' `
  -Body $body

$task
```

Task holatini ko‘rish:

```powershell
Invoke-RestMethod `
  -Uri ("http://127.0.0.1:8765/api/tasks/{0}" -f $task.id) `
  -Headers $headers
```

## 6. n8n’ni Docker’da ishga tushirish

Docker o‘rnatilgan bo‘lsa, oddiy local n8n:

```powershell
docker volume create n8n_data
docker run -it --rm `
  --name n8n `
  -p 5678:5678 `
  -e N8N_SECURE_COOKIE=false `
  -e AGENT_API_KEY=$env:AGENT_API_KEY `
  -e TELEGRAM_NOTIFY_CHAT_ID='TELEGRAM_CHAT_ID' `
  -v n8n_data:/home/node/.n8n `
  n8nio/n8n
```

n8n panel:

```text
http://127.0.0.1:5678
```

Windows Docker Desktop’da n8n container’dan host’dagi NOVA API manzili:

```text
http://host.docker.internal:8765
```

Linux’da `host.docker.internal` avtomatik ishlamasligi mumkin. Bunday holatda:

```bash
docker run --add-host=host.docker.internal:host-gateway ...
```

Yaxshiroq variant — NOVA va n8n’ni bitta Docker network’ga qo‘yish:

```bash
docker network create nova-net
```

Shunda backend service nomi, masalan, `nova-api` bo‘ladi va n8n URL’i:

```text
http://nova-api:8765
```

## 7. n8n’da task yuborish workflow’i

Loyihadagi fayl:

```text
n8n/task-submit-example.json
```

Import qilish:

1. n8n panelini oching.
2. `Workflows` → `Import from File` tanlang.
3. `D:\agent\n8n\task-submit-example.json` faylini tanlang.
4. `Submit to Python API` node’ni oching.
5. URL’ni muhitga moslang:
   - Windows Docker: `http://host.docker.internal:8765/api/tasks`
   - Bitta Docker network: `http://nova-api:8765/api/tasks`
6. `X-Agent-Key` header qiymatini n8n credential yoki environment expression bilan ulang.
7. Workflow’ni inactive holda manual test qiling.

Webhook body namunasi:

```json
{
  "project": "sample",
  "agent": "coding",
  "prompt": "FastAPI loyihasidagi testlarni tekshir",
  "auto": true,
  "approval": false
}
```

HTTP Request node sozlamasi:

```text
Method: POST
URL: http://host.docker.internal:8765/api/tasks
Header: X-Agent-Key = {{$env.AGENT_API_KEY}}
Content-Type: application/json
```

## 8. Approval talab qilinadigan task

Task yuborishda:

```json
{
  "project": "sample",
  "agent": "coding",
  "prompt": "Muhim kod o‘zgarishini tayyorla",
  "auto": true,
  "approval": true
}
```

Bunday task `awaiting_approval` holatida qoladi.

Tasdiqlash:

```text
POST /api/tasks/TASK_ID/approve
```

Rad etish:

```text
POST /api/tasks/TASK_ID/reject
```

Git diff ko‘rish:

```text
GET /api/projects/sample/diff
```

## 9. Task completion notification workflow’i

Duplicate notification’ni kamaytiradigan tayyor fayl:

```text
n8n/notification-dedup-example.json
```

Import qilish:

1. `Workflows` → `Import from File`.
2. `D:\agent\n8n\notification-dedup-example.json` faylini import qiling.
3. Telegram node’da Telegram credential tanlang.
4. `TELEGRAM_NOTIFY_CHAT_ID` environment variable’ni belgilang.
5. `AGENT_API_KEY` n8n environment variable sifatida mavjudligini tekshiring.
6. Backend URL’ni moslang.
7. Manual test qiling.
8. Natija to‘g‘ri bo‘lsa workflow’ni Activate qiling.

Workflow quyidagicha ishlaydi:

```text
Schedule Trigger
  → Read cursor
  → GET /api/tasks/terminal?after=cursor
  → Expand new tasks
  → Telegram notification
  → Save cursor
```

Cursor n8n workflow static data’da saqlanadi. Shu sababli bir xil completed task har 2 daqiqada qayta yuborilmaydi.

Backend endpoint:

```text
GET /api/tasks/terminal?after=0
```

Javob:

```json
{
  "items": [],
  "cursor": 0
}
```

## 10. Telegram credential sozlash

1. Telegram’da `@BotFather` orqali bot yarating.
2. Bot tokenni oling.
3. n8n’da `Credentials` → `Telegram API` oching.
4. Bot tokenni kiriting.
5. Bot’ni kerakli chat yoki group’ga qo‘shing.
6. Chat ID’ni aniqlang.
7. `TELEGRAM_NOTIFY_CHAT_ID` sifatida belgilang.

Bot tokenni chatga yoki Git repository’ga yubormang.

## 11. n8n task retry workflow’i

Failed task uchun HTTP Request node:

```text
Method: POST
URL: http://host.docker.internal:8765/api/tasks/{{$json.id}}/retry
Header: X-Agent-Key = {{$env.AGENT_API_KEY}}
```

Retry faqat quyidagi holatlarda ruxsat etiladi:

```text
failed
cancelled
interrupted
rejected
```

Task hali `running` yoki `queued` bo‘lsa retry qilishga API `409` qaytaradi.

## 12. Workflow’ni test qilish tartibi

1. NOVA backend’ni ishga tushiring.
2. `/api/projects` orqali API key’ni tekshiring.
3. n8n workflow’ni import qiling.
4. HTTP Request node’da backend URL’ni tekshiring.
5. `X-Agent-Key` header borligini tekshiring.
6. Webhook’ga test JSON yuboring.
7. NOVA admin panelda task paydo bo‘lganini tekshiring.
8. Task `completed` yoki `failed` bo‘lishini kuting.
9. `/api/tasks/terminal?after=0` orqali terminal taskni tekshiring.
10. Telegram notification kelganini tekshiring.
11. n8n execution log’ida barcha node’lar yashil bo‘lganini tekshiring.
12. Workflow’ni Activate qiling.

## 13. n8n connectivity diagnostika

### `ECONNREFUSED`

- NOVA backend ishlamayapti.
- URL noto‘g‘ri.
- Container backend’ga kira olmayapti.
- Linux’da `host.docker.internal` uchun `--add-host` qo‘shilmagan.

### `401 Authentication required`

- `X-Agent-Key` header yo‘q.
- API key noto‘g‘ri.
- n8n environment variable o‘qilmagan.

### `403 Read-only API key`

Task yaratish uchun `AGENT_API_KEY` ishlating. `AGENT_READONLY_API_KEY` faqat monitoring uchun.

### `404 Topilmadi`

- Project nomi workspace ichida yo‘q.
- Task ID noto‘g‘ri.
- URL path noto‘g‘ri yozilgan.

### Notification qayta-qayta kelmoqda

- Eski `notification-example.json` workflow’ini deactivate qiling.
- Cursor-based `notification-dedup-example.json` workflow’ini ishlating.
- n8n workflow static data o‘chirilmaganini tekshiring.
- Bitta notification workflow instance ishlayotganini tekshiring.

## 14. Production xavfsizligi

- Backend’ni internetga to‘g‘ridan-to‘g‘ri ochmang.
- HTTPS reverse proxy ishlating.
- `ADMIN_PASSWORD` va `AGENT_API_KEY` uzun random qiymat bo‘lsin.
- Webhook authentication va rate limit qo‘shing.
- n8n webhook URL’ini public qilishdan oldin IP allowlist qo‘ying.
- API key’ni workflow JSON’iga hardcode qilmang.
- `MOCK_CODEX=1` production’da ishlatilmasin.
- n8n va NOVA backend’ni alohida unprivileged user/container’da ishlating.
- Log va prompt ichiga secret yubormang.
- SQLite database’ning backup’ini saqlang.
- Telegram botning bitta polling instance’ini ishlating.

## 15. To‘xtatish

Backend oynasida `Ctrl+C` bosing.

n8n Docker container’ni to‘xtatish:

```powershell
docker stop n8n
```

Container’ni qayta ishga tushirish:

```powershell
docker start n8n
```

## 16. Yakuniy checklist

- [ ] Backend `8765` portda ishlayapti.
- [ ] `/docs` ochilyapti.
- [ ] `/api/projects` API key bilan javob qaytaryapti.
- [ ] n8n backend URL to‘g‘ri.
- [ ] `X-Agent-Key` header yuborilyapti.
- [ ] Task webhook’dan yaratilmoqda.
- [ ] Admin panelda task ko‘rinyapti.
- [ ] Task terminal holatga o‘tyapti.
- [ ] Notification cursor workflow import qilingan.
- [ ] Telegram credential tanlangan.
- [ ] Duplicate notification yo‘q.
- [ ] Workflow Activate qilingan.
- [ ] Production’da MOCK rejim o‘chirilgan.

## 17. Muhim tushunchalar

### NOVA API key nima?

`AGENT_API_KEY` n8n va NOVA backend o‘rtasidagi umumiy servis kalitidir. n8n har bir protected API request’da quyidagi header’ni yuboradi:

```text
X-Agent-Key: AGENT_API_KEY qiymati
```

Bu qiymat admin panel paroli bilan bir xil emas. Admin panel Basic Auth’dan, n8n esa API key’dan foydalanadi.

### Qaysi endpoint qaysi maqsad uchun?

| Endpoint | Method | Maqsad |
|---|---:|---|
| `/api/projects` | GET | Project va agentlarni olish |
| `/api/tasks` | GET | Oxirgi tasklar ro‘yxati |
| `/api/tasks` | POST | Yangi task yuborish |
| `/api/tasks/{id}` | GET | Bitta task va eventlar |
| `/api/tasks/{id}/stream` | GET | Real-time SSE stream |
| `/api/tasks/terminal?after=0` | GET | Yangi completed/failed tasklar |
| `/api/tasks/{id}/cancel` | POST | Task’ni bekor qilish |
| `/api/tasks/{id}/approve` | POST | Approval task’ni boshlash |
| `/api/tasks/{id}/reject` | POST | Approval task’ni rad etish |
| `/api/tasks/{id}/retry` | POST | Terminal task’ni qayta ishlatish |
| `/api/dashboard` | GET | Operational dashboard data |
| `/api/metrics` | GET | Queue va status statistikasi |
| `/api/projects/{project}/health` | GET | Project health check |
| `/api/projects/{project}/quality` | GET | Pytest/ruff quality gate |
| `/api/projects/{project}/dependencies` | GET | Dependency audit |
| `/api/projects/{project}/diff` | GET | Git diff statusi |

## 18. Windows environment’ni doimiy sozlash

PowerShell’da `$env:...` faqat joriy terminal uchun amal qiladi. Har safar qayta yozmaslik uchun project papkasida `run-nova.ps1` yaratish mumkin.

`run-nova.ps1` namunasi:

```powershell
$env:ADMIN_PASSWORD = 'UZUN_ADMIN_PAROLI'
$env:AGENT_API_KEY = 'UZUN_RANDOM_API_KEY'
$env:AGENT_WORKSPACE = 'D:\agent\workspace'
$env:AGENT_DB = 'D:\agent\agent_tasks.sqlite3'
$env:AGENT_MAX_QUEUE_SIZE = '100'
# Local test uchun yoqing, real Codex uchun olib tashlang:
# $env:MOCK_CODEX = '1'

Set-Location 'D:\agent'
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Ishga tushirish:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run-nova.ps1
```

`run-nova.ps1` faylini Git’ga joylamang, chunki unda secret bo‘lishi mumkin.

## 19. Virtual environment bilan tavsiya etilgan o‘rnatish

```powershell
cd D:\agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -q
```

Virtual environment faol ekanini tekshirish:

```powershell
python -c "import sys; print(sys.executable)"
```

U `D:\agent\.venv\Scripts\python.exe` ko‘rsatishi kerak.

## 20. Real Codex rejimini tekshirish

Local mock test:

```powershell
$env:MOCK_CODEX = '1'
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Real Codex rejimi:

```powershell
Remove-Item Env:MOCK_CODEX -ErrorAction SilentlyContinue
codex --version
codex login status
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Codex CLI backend’ni ishga tushirayotgan aynan shu Windows user bilan login qilingan bo‘lishi kerak. Real rejimda agent loyiha fayllarini o‘zgartirishi mumkin; avval disposable project’da test qiling.

## 21. n8n environment variable’larini tekshirish

n8n Code yoki HTTP Request node ichida `$env.AGENT_API_KEY` ishlatilayotganini tekshirish uchun vaqtinchalik Code node:

```javascript
return [{
  json: {
    keyConfigured: Boolean($env.AGENT_API_KEY),
    keyLength: ($env.AGENT_API_KEY || '').length
  }
}];
```

Secret’ning o‘zini output’ga chiqarish mumkin emas.

Docker orqali n8n ishga tushirilgan bo‘lsa, environment variable container ichida borligini tekshirish:

```powershell
docker exec -it n8n sh -lc 'test -n "$AGENT_API_KEY" && echo configured || echo missing'
```

`AGENT_API_KEY` o‘zgarsa, n8n container’ni qayta yaratish kerak. Faqat `docker restart` ba’zan eski environment bilan qoladi.

## 22. n8n task submit workflow’ini qo‘lda yaratish

Agar JSON import ishlamasa, quyidagi node’larni qo‘lda yarating.

### Node 1 — Webhook

```text
Node: Webhook
HTTP Method: POST
Path: nova-agent-task
Response Mode: Immediately
```

Webhook test URL’ini copy qiling. Production’da test URL emas, production URL ishlatiladi.

### Node 2 — Set yoki Code

Code node:

```javascript
const body = $json.body || $json;

if (!body.project || !body.agent || !body.prompt) {
  throw new Error('project, agent va prompt majburiy');
}

return [{
  json: {
    project: String(body.project),
    agent: String(body.agent),
    prompt: String(body.prompt),
    auto: body.auto !== false,
    approval: body.approval === true
  }
}];
```

### Node 3 — HTTP Request

```text
Method: POST
URL: http://host.docker.internal:8765/api/tasks
Authentication: None
Send Headers: On
Send Body: On
Body Content Type: JSON
```

Headers:

```text
Name: X-Agent-Key
Value: {{$env.AGENT_API_KEY}}
```

JSON body:

```javascript
={{ JSON.stringify($json) }}
```

### Node 4 — Respond to Webhook

Response body:

```javascript
={{ JSON.stringify({
  accepted: true,
  taskId: $json.id,
  status: $json.status,
  approvalStatus: $json.approval_status
}) }}
```

## 23. Webhook’ni curl bilan test qilish

n8n webhook URL’ini `WEBHOOK_URL` o‘rniga qo‘ying:

```powershell
$body = @{
  project = 'sample'
  agent = 'coding'
  prompt = 'Calculator uchun regression test yoz'
  auto = $true
  approval = $false
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri 'WEBHOOK_URL' `
  -Method Post `
  -ContentType 'application/json' `
  -Body $body
```

Kutiladigan n8n javobi:

```json
{
  "accepted": true,
  "taskId": "abc123...",
  "status": "queued",
  "approvalStatus": "not_required"
}
```

Approval yoqilgan bo‘lsa `status` `awaiting_approval` bo‘ladi.

## 24. n8n notification workflow’ini tushunish

`notification-dedup-example.json` ikki daqiqada bir ishlaydi. U:

1. Oldingi cursor’ni o‘qiydi.
2. `/api/tasks/terminal?after=cursor` endpoint’ini chaqiradi.
3. Faqat cursor’dan keyingi terminal tasklarni oladi.
4. Telegram’ga har bir task haqida notification yuboradi.
5. Eng katta `updated` timestamp’ni cursor sifatida saqlaydi.

Terminal holatlar:

```text
completed
failed
cancelled
interrupted
```

Agar Telegram node xato bersa, cursor keyingi node’ga o‘tmasligi kerak. Shu sababli notification node’dan keyin cursor saqlanadi.

## 25. Telegram chat ID olish

### Usul 1 — Bot API

1. Bot’ga Telegram’da xabar yuboring.
2. Quyidagi URL’ni browser’da oching:

```text
https://api.telegram.org/botBOT_TOKEN/getUpdates
```

3. Javob ichidan quyidagini toping:

```json
"chat": {
  "id": 123456789
}
```

4. `123456789` qiymatini `TELEGRAM_NOTIFY_CHAT_ID` qiling.

Bot tokenni URL’ni boshqa odamlarga yubormang.

### Usul 2 — Telegram bot adapter

Backend bilan birga Telegram adapter ishlatilsa:

```powershell
$env:AGENT_API_URL = 'http://127.0.0.1:8765'
$env:AGENT_API_KEY = 'YOUR_API_KEY'
$env:TELEGRAM_BOT_TOKEN = 'BOT_TOKEN'
$env:TELEGRAM_ALLOWED_IDS = '123456789'
python telegram_bot.py
```

Bir bot token bilan ikki polling process ishlatmang. Aks holda Telegram `409 Conflict` qaytaradi.

## 26. n8n orqali task holatini kutish

Agar submit workflow task tugashini kutishi kerak bo‘lsa:

```text
HTTP Request POST /api/tasks
  ↓
Wait 5 seconds
  ↓
HTTP Request GET /api/tasks/TASK_ID
  ↓
IF status in completed/failed/cancelled
  ├─ true  → notification
  └─ false → Wait → status check
```

Task ID expression:

```text
{{$node["Submit to Python API"].json.id}}
```

Loop uchun maksimal urinish qo‘ying. Masalan, 60 ta tekshiruvdan keyin timeout qiling. Infinite loop qilmang.

## 27. n8n approval workflow’i

Approval request uchun:

```text
NOVA terminal task
  ↓
IF status = awaiting_approval
  ↓
Telegram inline button / admin decision
  ↓
POST /api/tasks/{id}/approve yoki /reject
```

Approve HTTP Request:

```text
Method: POST
URL: http://host.docker.internal:8765/api/tasks/{{$json.id}}/approve
Header: X-Agent-Key = {{$env.AGENT_API_KEY}}
```

Reject URL’da faqat oxirgi qism o‘zgaradi:

```text
/reject
```

## 28. Health-check workflow’i

n8n Schedule Trigger’ni har 5 daqiqaga qo‘ying.

HTTP Request node:

```text
GET http://host.docker.internal:8765/api/dashboard
Header X-Agent-Key: {{$env.AGENT_READONLY_API_KEY}}
```

IF node:

```javascript
={{ $json.workers && $json.workers[0].status !== 'online' }}
```

True branch’da Telegram alert yuboring. Read-only key ishlatish xavfsizroq, chunki health-check task o‘zgartirmaydi.

## 29. Error handling workflow’i

Har bir HTTP Request node’da:

- `Continue On Fail` faqat keyingi error branch mavjud bo‘lsa yoqilsin.
- HTTP 401/403 uchun credential alert yuborilsin.
- HTTP 429 uchun Wait + retry ishlatilsin.
- HTTP 5xx uchun 3 martagacha exponential retry ishlatilsin.
- Noma’lum 4xx xatolarni qayta-qayta yubormang.

Tavsiya etilgan oqim:

```text
HTTP Request
  ↓
IF success?
  ├─ yes → next step
  └─ no  → Switch status code
          ├─ 401/403 → security alert
          ├─ 429     → wait and retry
          ├─ 5xx     → retry up to 3
          └─ other   → failed notification
```

## 30. Docker tarmoq muammosini aniqlash

n8n container ichidan backend’ga tekshiruv:

```powershell
docker exec -it n8n sh
```

Container ichida:

```sh
wget -qO- http://host.docker.internal:8765/docs
```

Agar `wget` mavjud bo‘lmasa, n8n image ichida shell tool bo‘lmasligi mumkin. Alohida debug container:

```powershell
docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl:latest `
  http://host.docker.internal:8765/docs
```

Windows Firewall connection’ni bloklasa, backend bind address va firewall policy’ni tekshiring. Backend’ni public internetga ochmang.

## 31. Linux Docker uchun docker-compose namunasi

```yaml
services:
  nova-api:
    build: .
    command: python -m uvicorn app:app --host 0.0.0.0 --port 8765
    environment:
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      AGENT_API_KEY: ${AGENT_API_KEY}
      AGENT_WORKSPACE: /app/workspace
      MOCK_CODEX: "0"
    volumes:
      - ./workspace:/app/workspace
      - ./agent_tasks.sqlite3:/app/agent_tasks.sqlite3
    networks: [nova]

  n8n:
    image: n8nio/n8n:latest
    ports:
      - "5678:5678"
    environment:
      AGENT_API_KEY: ${AGENT_API_KEY}
      TELEGRAM_NOTIFY_CHAT_ID: ${TELEGRAM_NOTIFY_CHAT_ID}
    volumes:
      - n8n_data:/home/node/.n8n
    networks: [nova]

networks:
  nova:

volumes:
  n8n_data:
```

Bunda n8n backend’ga quyidagi URL bilan ulanadi:

```text
http://nova-api:8765
```

Production’da `latest` o‘rniga tekshirilgan n8n version pin qiling.

## 32. Backup va tiklash

Backend’ni to‘xtatib SQLite backup oling:

```powershell
Copy-Item D:\agent\agent_tasks.sqlite3 D:\agent\backups\agent_tasks.sqlite3
```

Backup papkasini oldindan yarating:

```powershell
New-Item -ItemType Directory -Force D:\agent\backups
```

Backup’dan tiklashdan oldin backend process’ni to‘xtating va hozirgi database’ni boshqa nom bilan saqlang.

## 33. Ishga tushirishdan oldingi yakuniy tekshiruv

```powershell
cd D:\agent
python -m py_compile app.py engineering_features.py integrations.py telegram_bot.py
python -m pytest -q
Get-Content -Raw n8n\notification-dedup-example.json | ConvertFrom-Json | Out-Null
```

Kutiladigan natija:

```text
8 passed
```

Keyin:

1. Backend’ni ishga tushiring.
2. `/docs` ni oching.
3. `/api/projects` ni API key bilan tekshiring.
4. n8n’ni ishga tushiring.
5. Task submit workflow’ini import qiling.
6. Test task yuboring.
7. Admin panelda taskni tekshiring.
8. Notification workflow’ini import qiling.
9. Telegram credential va chat ID’ni tanlang.
10. Manual execute qiling.
11. Duplicate notification bo‘lmasligini tekshiring.
12. Faqat shundan keyin workflow’larni Activate qiling.

