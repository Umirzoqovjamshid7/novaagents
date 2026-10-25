# Kod auditi: kamchiliklar va bajarilgan tuzatishlar

Audit sanasi: 2026-10-25

## Tuzatilgan muammolar

1. Root katalogdan `pytest` ishga tushirilganda `calculator` import qilinmas edi. `pytest.ini` va test `conftest.py` qo‘shilib, testlar barqaror ishga tushadigan qilindi.
2. SQLite kontekst menejeri xatolik paytida aniq `rollback` qilmas edi. Endi xato bo‘lsa rollback, muvaffaqiyatli yakunda commit qilinadi.
3. `AGENT_DB` ota katalogi mavjud bo‘lmasa servis ishga tushmasligi mumkin edi. DB katalogi avtomatik yaratiladi.
4. Workspace ichidagi symlink orqali ruxsat etilmagan katalogga yo‘l ochilishi mumkin edi. Loyiha tanlashda symlink qat’iy rad etiladi.
5. Telegram `/status` va `/cancel` buyruqlari argumentsiz yuborilsa `IndexError` yuz berardi. Endi foydalanuvchiga to‘g‘ri format ko‘rsatiladi.
6. Telegram polling HTTP xatosida bot jarayoni to‘xtab qolishi mumkin edi. HTTP xatolari qayta ulanish sikliga qo‘shildi.
7. Navbat workeridagi vaqtinchalik SQLite/xizmat xatosi worker thread’ni butunlay o‘ldirishi mumkin edi. Endi worker xatoni yutib yubormasdan, qisqa pauzadan keyin ishlashda davom etadi.
8. Vazifa faqat bo‘sh joylardan iborat bo‘lsa Pydantic’ning uzunlik tekshiruvidan o‘tib ketardi. Vazifa matni trim qilinadi va qayta tekshiriladi.
9. Browser/API javoblarida bazaviy security headerlari yo‘q edi. `nosniff`, `DENY`, `no-referrer`, `Permissions-Policy` va API uchun `no-store` qo‘shildi.
10. Queue va event jadvallarida tez-tez ishlatiladigan ustunlar indekslanmagan edi. Status/created va task_id indekslari qo‘shildi.
11. Path traversal va Telegram parser uchun regression testlar mavjud emas edi. Alohida testlar qo‘shildi.
12. FastAPI startup hook deprecated API’dan foydalanardi. Startup jarayoni `lifespan` lifecycle’iga o‘tkazildi.
13. Event va task natijalarida token/parol ko‘rinib qolishi mumkin edi. Umumiy secret redaction qo‘shildi.
14. Queue hajmi cheklanmagan edi. `AGENT_MAX_QUEUE_SIZE` bilan active task limiti qo‘shildi; limit oshsa API `429` qaytaradi.
15. Project health, quality gate, dependency audit, metrics, SSE stream va task template API’lari mavjud emas edi; MVP endpointlari qo‘shildi.
16. Integratsiya client’ida vaqtinchalik network/5xx xatolari uchun retry yo‘q edi; exponential retry qo‘shildi.
17. Shared API key uchun read-only monitoring roli yo‘q edi; `AGENT_READONLY_API_KEY` qo‘shildi.
18. Agent o‘zgarishlarini review’dan oldin tasdiqlash workflow’i yo‘q edi. `approval` task rejimi, approve/reject endpointlari va git diff endpointi qo‘shildi.
19. Eski admin panel MVP ko‘rinishida va funksiyalar tarqoq edi. UI reference dizayn asosida to‘liq responsive NOVA control center ko‘rinishida qayta yozildi; task, approval, cancel, diff, log va test controls API bilan ulandi.
20. n8n notification workflow duplicate xabar yuborishi mumkin edi. Terminal task cursor endpointi va cursor-based inactive workflow namunasi qo‘shildi.
21. Failed/cancelled/interrupted task’larni qayta ishga tushirish endpointi yo‘q edi. Validated `retry` transition qo‘shildi.

## Hali mavjud bo‘lgan muhim cheklovlar

- Worker in-process daemon thread; bir nechta Uvicorn worker bilan ishlatish xavfli va durable queue yo‘q.
- Ishlayotgan Codex yoki pytest subprocess’ini cancel qilishda darhol to‘xtatish/rollback kafolatlanmagan.
- Har bir loyiha uchun alohida sandbox/container va resource limitlari yo‘q; testlar arbitrary kod bajaradi.
- SQLite katta parallel yuklama va production audit trail uchun yetarli emas.
- API key barcha integratsiyalar uchun umumiy; user/role darajasida authorization yo‘q.
- Telegram `SESSIONS` restart bo‘lsa yo‘qoladi va botda webhook/polling observability cheklangan.
- Rate limit, CSRF himoyasi, security headers, audit log retention va secret rotation mexanizmlari yo‘q.
- Real Codex, Telegram va n8n integratsiyalari credential’siz end-to-end tekshirilmagan.
- `README.md`, `app.py` va UI matnlarida ayrim o‘zbekcha belgilar mojibake ko‘rinishida saqlangan; encodingni tozalash alohida ish sifatida bajarilishi kerak.

> Eslatma: yuqoridagi subprocess cancellation cheklovi endi qisman tuzatildi. Active Codex/pytest jarayoni task cancel qilinganda process-tree bilan to‘xtatiladi; git rollback hali ham avtomatik emas.

## Tekshiruv natijasi

- `python -m pytest -q`: **6 passed**
- `python -m py_compile app.py integrations.py telegram_bot.py`: **muvaffaqiyatli**

