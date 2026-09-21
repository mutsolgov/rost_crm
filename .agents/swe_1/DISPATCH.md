## 2026-09-20T22:15:33Z

You are the SWE Light Orchestrator (`swe_1`) executing in `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/swe_1/`.

Your mission is to execute the user request recorded in `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md` under the latest section:
"Приведение обработки ошибок в backend/app/errors.py к контракту C01".

## Context and Requirements
1. **R1. Расширение класса APIError и стандартизация формата ошибок C01**:
   - В `backend/app/errors.py`:
     - Расширить сигнатуру конструктора `APIError`:
       ```python
       def __init__(self, code: str, message: str, status: int = 422, details=None, field_errors: list | None = None):
           self.code = code
           self.message = message
           self.status = status
           self.details = details
           self.field_errors = field_errors or []
       ```
     - В обработчике `domain_error` гарантировать наличие ключа `"field_errors": getattr(exc, "field_errors", []) or []` в конверте ответа `{"error": {...}}`.
     - Ключ `details` сохраняется (если `exc.details is not None`), обеспечивая полную обратную совместимость со всеми существующими проверками и клиентами.

2. **R2. Извлечение ошибок валидации Pydantic и нормализация полей**:
   - В обработчике `RequestValidationError`:
     - Извлекать ошибки полей с удалением префикса `"body"` из пути:
       ```python
       field_errors = [
           {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
           for e in exc.errors()
       ]
       ```
     - Передавать `field_errors` и в параметр `details`, и в `field_errors` экземпляра `APIError("VALIDATION_ERROR", "Проверьте поля запроса.", 422, details=field_errors, field_errors=field_errors)`.

3. **R3. Безопасная обработка непредвиденных исключений (500 Internal Error)**:
   - Добавить глобальный обработчик `@app.exception_handler(Exception)`:
     - Возвращает HTTP 500.
     - JSON-конверт:
       ```json
       {
         "error": {
           "code": "INTERNAL_ERROR",
           "message": "Внутренняя ошибка сервера. Обратитесь к администратору.",
           "request_id": "<correlation-id>",
           "details": null,
           "field_errors": []
         }
       }
       ```
     - Скрывать трассировку стека (traceback), детали SQL-запросов и чувствительные данные от внешнего клиента.

4. **R4. Регрессионный контроль и сохранение контрактов**:
   - Набор автотестов: `backend/.venv/bin/python -m pytest backend/tests/ -q` (139 тестов). 0 regressions!
   - 4 оракула верификации:
     * `python3 docs/checks/verify_infra.py`
     * `python3 docs/checks/verify_workflow.py`
     * `python3 docs/checks/verify_reports.py`
     * `python3 docs/checks/verify_plan.py`
   - Strict Ponytail principles: minimal clean diff, 0 new dependencies.

## Working Directory & Handoff
- Working directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/swe_1/`
- Maintain `progress.md` and `BRIEFING.md` in your working directory.
- Dispatch your implementer (`teamwork_preview_implementer` with flash) and reviewer (`teamwork_preview_reviewer` with flash) as specified in SWE Light loop.
- Deliver `handoff.md` and report back when finished.
