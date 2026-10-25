# Rivojlantirish g‘oyalari

## 1. Durable job queue

Redis/SQLite lease yoki alohida worker service joriy qilinsin. Har bir job uchun lease timeout, retry policy, idempotency key va dead-letter holati bo‘lsin.

## 2. Izolyatsiyalangan bajarish

Har bir Codex/pytest vazifasi disposable container yoki OS-level sandbox ichida bajarilsin. CPU, RAM, disk, network va timeout limitlari majburiy bo‘lsin.

## 3. Rollback va preview

Vazifa boshlanishidan oldin git worktree yoki snapshot yaratiladi. Agent diff’ni preview qiladi; approve’dan keyin asosiy branch’ga qo‘llanadi.

## 4. Sifat pipeline’i

`ruff`, `mypy`, `pytest --cov`, dependency audit va secret scan bitta quality gate sifatida ishlasin. Natija task report’ida alohida ko‘rsatilsin.

## 5. Role-based access control

Admin, operator, reviewer va read-only rollari; loyiha bo‘yicha allowlist; Telegram user ID’lari uchun DB-backed authorization va audit log qo‘shilsin.

## 6. Observability

Structured JSON loglar, correlation/task ID, metrics (queue length, duration, failure rate) va alerting qo‘shilsin. Parol, token va prompt ichidagi secretlar redaction qilinsin.

## 7. Encoding va API contract

Barcha source/HTML/README matnlari UTF-8 ga tozalansin. OpenAPI schema’dan client contract testlari generatsiya qilinsin.

## 8. Test strategiyasi

Auth, project path traversal/symlink, cancellation race, restart reconciliation, Telegram command parser va API error response’lari uchun unit/integration testlar qo‘shilsin.

## Amalga oshirilgan qism

- Path traversal himoyasi uchun regression test qo‘shildi.
- Telegram task ID parser testi qo‘shildi.
- Workspace loyihasining to‘g‘ri resolve bo‘lishi testi qo‘shildi.
- Bazaviy HTTP security headerlari va SQLite indekslari qo‘shildi.
- Project health endpoint va dependency audit endpoint qo‘shildi.
- Quality gate endpoint va coding/debug workflow’iga quality gate qo‘shildi.
- Metrics endpoint, SSE task stream va task templates endpoint qo‘shildi.
- Read-only API key orqali minimal role-based access qo‘shildi.
- Integratsiya API client’iga exponential retry qo‘shildi.
- O‘zbekcha/ruscha/inglizcha UI tarjimalari uchun i18n API contract qo‘shildi.
- Task approval workflow (`approval`, approve/reject) va project git-diff endpointi qo‘shildi.
