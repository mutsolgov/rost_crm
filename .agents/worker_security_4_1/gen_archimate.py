import xml.etree.ElementTree as ET

def build_model():
    NS = "http://www.opengroup.org/xsd/archimate/3.0/"
    XSI = "http://www.w3.org/2001/XMLSchema-instance"
    SCHEMA_LOC = "http://www.opengroup.org/xsd/archimate/3.0/ http://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd"

    ET.register_namespace('', NS)
    ET.register_namespace('xsi', XSI)

    model = ET.Element(f"{{{NS}}}model", {
        f"{{{XSI}}}schemaLocation": SCHEMA_LOC,
        "identifier": "id-rost-crm-model"
    })

    name = ET.SubElement(model, f"{{{NS}}}name", {"xml:lang": "ru"})
    name.text = "ИТ Школа Ростелекома — CRM (Архитектурная модель ArchiMate 3.1)"

    doc = ET.SubElement(model, f"{{{NS}}}documentation", {"xml:lang": "ru"})
    doc.text = (
        "Комплексная архитектурная модель системы «ИТ Школа Ростелекома — CRM» (rost_crm), "
        "разработанная в соответствии со стандартом The Open Group ArchiMate 3.1 Model Exchange File. "
        "Охватывает Бизнес-слой (акторы, роли, процессы воронки партнерств, объекты), "
        "Слой приложений (SPA, FastAPI ядро, движки воронки, отчетов, файлов, интеграций, шина Keycloak, LMS Zion, Сайт Laravel) "
        "и Технологический слой (Linux, Docker, PostgreSQL 16, Python 3.12, Nginx, сетевые периметры DMZ/LAN)."
    )

    elements_elem = ET.SubElement(model, f"{{{NS}}}elements")

    # Define all elements: (id, xsi_type, name, doc)
    elements_data = [
        # --- Business Layer ---
        ("id-elem-ba-manager", "BusinessActor", "Менеджер партнерств", "Сотрудник ПАО «Ростелеком», ведущий взаимодействия с образовательными организациями."),
        ("id-elem-ba-supervisor", "BusinessActor", "Руководитель направления", "Куратор региональной команды менеджеров, контролирующий воронку партнерств и аналитику."),
        ("id-elem-ba-admin", "BusinessActor", "Системный администратор", "Администратор платформы, управляющий пользователями, миграциями процессов и сверкой заявок."),
        ("id-elem-ba-unirep", "BusinessActor", "Представитель образовательной организации", "Контактное лицо вуза/колледжа: ректор, декан, преподаватель."),
        
        ("id-elem-br-operator", "BusinessRole", "Оператор воронки партнерств", "Роль ведения карточек взаимодействия, согласования и фиксации этапов."),
        ("id-elem-br-curator", "BusinessRole", "Куратор регионального портфеля", "Роль распределения вузов и мониторинга аналитики команды."),
        ("id-elem-br-secadmin", "BusinessRole", "Администратор безопасности и конфигурации", "Роль управления каталогами, миграции версий workflow и разрешения заявок."),
        
        ("id-elem-bc-partnership", "BusinessCollaboration", "Сотрудничество в проекте «ИТ Школа»", "Совместная деятельность Ростелекома и образовательных организаций."),
        
        ("id-elem-bp-initiation", "BusinessProcess", "Инициация партнерства", "Этапы: 1. Поиск контактов -> 2. Уточнение потребности -> 3. Встреча с вузом."),
        ("id-elem-bp-contracting", "BusinessProcess", "Договорная кампания", "Этапы: 4. Обмен документами -> 5. Корректировка -> 6. Подписание документов."),
        ("id-elem-bp-transfer", "BusinessProcess", "Внедрение ПО и передача материалов", "Этапы: 7. Передача материалов -> 8. Сопровождение -> 9. Обучение преподавателей."),
        ("id-elem-bp-study", "BusinessProcess", "Учебный процесс и сопровождение", "Этапы: 10. Актуализация -> 11. Ведение занятий -> 12. Обновление материалов -> 13. Повышение квалификации."),
        ("id-elem-bp-analytics", "BusinessProcess", "Формирование управленческой аналитики", "Построение срезов портфеля на дату (snapshot), динамики активности (activity) и привлечения (created)."),
        
        ("id-elem-bo-interaction", "BusinessObject", "Карточка взаимодействия", "Центральная бизнес-сущность сотрудничества по образовательной программе."),
        ("id-elem-bo-contract", "BusinessObject", "Договор о сотрудничестве", "Двусторонний юридический договор между Ростелекомом и вузом."),
        ("id-elem-bo-license", "BusinessObject", "Лицензия на ИТ-продукт", "Лицензионное соглашение на программные продукты Ростелекома."),
        ("id-elem-bo-contact", "BusinessObject", "Контактные данные представителя", "Персональные данные представителя образовательной организации (ФИО, телефон, email)."),
        ("id-elem-bo-report", "BusinessObject", "Аналитический отчет", "Сводные отчетные материалы в форматах XLSX, PDF и JSON."),

        # --- Application Layer ---
        ("id-elem-ac-crm", "ApplicationComponent", "ИТ Школа Ростелекома — CRM", "Централизованная система управления взаимодействиями с вузами."),
        ("id-elem-ac-frontend", "ApplicationComponent", "Single-Page Application (React UI)", "Клиентское веб-приложение в дизайн-системе Rostelecom Gen2 Light (React 18, Vite). In-memory JWT."),
        ("id-elem-ac-backend", "ApplicationComponent", "FastAPI Backend Core API", "Высокопроизводительное асинхронное ядро бизнес-логики и REST API (Python 3.12+)."),
        ("id-elem-ac-workflow", "ApplicationComponent", "Workflow Engine & Migrator", "Движок управления 15 статусами воронки, валидации переходов и транзакционной миграции v1 -> v2."),
        ("id-elem-ac-reports", "ApplicationComponent", "Analytical Reports Engine", "Модуль расчета срезов и бинарной генерации XLSX (OOXML) и векторных PDF с символикой Ростелекома."),
        ("id-elem-ac-files", "ApplicationComponent", "Secure File Service", "Изолированное хранилище 10 форматов ТЗ с валидацией magic bytes, защитой от Path Traversal и SHA-256."),
        ("id-elem-ac-import", "ApplicationComponent", "Two-Phase Import Wizard", "Двухфазный мастер пакетного импорта каталогов (Dry-Run Preview и транзакционный Commit)."),
        ("id-elem-ac-integrations", "ApplicationComponent", "Integrations Gateway & Reconciliation Inbox", "Шлюз адаптеров LMS Zion и Сайта Laravel с очередью сверки коллизий заявок."),
        ("id-elem-ac-audit", "ApplicationComponent", "Audit & Event Sourcing Store", "Неизменяемое хранилище событий InteractionEvent с монотонным sequence и полными снимками состояния."),
        
        ("id-elem-ac-keycloak", "ApplicationComponent", "Keycloak Identity Provider", "Корпоративный сервер федеративной аутентификации (OIDC PKCE S256)."),
        ("id-elem-ac-lms", "ApplicationComponent", "LMS Zion (rtkb.zion-lms.ru)", "Внешняя образовательная платформа (активные потоки, зачисленные студенты)."),
        ("id-elem-ac-website", "ApplicationComponent", "Внешний сайт заявок (Laravel)", "Публичный портал приема входящих заявок образовательных организаций."),
        
        ("id-elem-ai-rest", "ApplicationInterface", "REST API v1 Interface (/api/v1/)", "Стандартизированный программный интерфейс JSON REST API с CAS и Idempotency-Key."),
        ("id-elem-ai-oidc", "ApplicationInterface", "Keycloak OIDC PKCE S256 Interface", "Интерфейс авторизации OAuth2/OIDC."),
        ("id-elem-ai-lms", "ApplicationInterface", "LMS Adapter Interface (DTO v1.0)", "Нормализованный интеграционный конверт сбора метрик."),
        ("id-elem-ai-web", "ApplicationInterface", "Website Webhook Interface (DTO v1.0)", "Интерфейс приема пакетов заявок с внешнего сайта."),
        ("id-elem-ai-gui", "ApplicationInterface", "Web GUI Interface", "Пользовательский интерфейс в веб-браузере."),
        
        ("id-elem-as-interaction", "ApplicationService", "Сервис управления взаимодействиями", "API CRUD карточек, переходы статусов, CAS-обновление ревизий."),
        ("id-elem-as-auth", "ApplicationService", "Сервис контроля доступа и Scope 152-ФЗ", "Проверка подписи JWT, расчет scope_clause, скрытие записей через 404 Not Found."),
        ("id-elem-as-reports", "ApplicationService", "Сервис аналитических отчетов", "Построение срезов портфеля, генерация XLSX и векторных PDF."),
        ("id-elem-as-files", "ApplicationService", "Сервис безопасного хранения файлов", "Фильтрация расширений, проверка magic bytes, потоковая отдача FileResponse."),
        ("id-elem-as-sync", "ApplicationService", "Сервис синхронизации и сверки заявок", "Дедупликация DTO v1.0 и ручное сопоставление вузов."),
        
        ("id-elem-do-interaction", "DataObject", "Сущность Interaction", "Модель данных карточки партнерства в реляционной БД."),
        ("id-elem-do-event", "DataObject", "Сущность InteractionEvent", "Модель темпорального события с sequence и snapshot."),
        ("id-elem-do-attachment", "DataObject", "Сущность Attachment", "Модель метаданных файла с контрольной суммой SHA-256."),
        ("id-elem-do-inbox", "DataObject", "Сущность IntegrationInbox", "Модель очереди входящих заявок с композитным ключом дедупликации."),
        ("id-elem-do-metric", "DataObject", "Сущность LearningMetric", "Модель образовательных показателей востребованности программ."),
        ("id-elem-do-token", "DataObject", "In-Memory JWT Access Token", "Аутентификационный токен, удерживаемый в оперативной памяти JavaScript."),

        # --- Technology Layer ---
        ("id-elem-node-app", "Node", "Сервер приложений CRM", "Выделенный вычислительный узел хостинга бэкенда и веб-сервера."),
        ("id-elem-node-db", "Node", "Сервер баз данных", "Выделенный сервер реляционной СУБД."),
        ("id-elem-dev-client", "Device", "Клиентское рабочее место сотрудника", "Рабочая станция / ноутбук пользователя с веб-браузером."),
        
        ("id-elem-ss-linux", "SystemSoftware", "Linux OS (Ubuntu 22.04 LTS / RHEL 9)", "Базовая серверная операционная система с настроенными политиками безопасности."),
        ("id-elem-ss-docker", "SystemSoftware", "Docker Engine & Compose", "Среда контейнеризации прикладных сервисов."),
        ("id-elem-ss-python", "SystemSoftware", "Python 3.12+ Runtime", "Среда исполнения бэкенда с AnyIO и Uvicorn."),
        ("id-elem-ss-postgres", "SystemSoftware", "PostgreSQL 16 RDBMS", "Транзакционная реляционная СУБД с поддержкой ACID."),
        ("id-elem-ss-nginx", "SystemSoftware", "Nginx Web Server / Reverse Proxy", "Веб-сервер терминации TLS 1.3, статики SPA и проксирования."),
        ("id-elem-ss-browser", "SystemSoftware", "Modern Web Browser", "Браузер с поддержкой стандартов HTML5, ES2022, Web Crypto API."),
        ("id-elem-ss-keycloak", "SystemSoftware", "Keycloak 24+ Server", "Сервер управления доступом и аутентификацией."),
        
        ("id-elem-net-corp", "CommunicationNetwork", "Корпоративная сеть ПАО «Ростелеком»", "Защищенный внутренний периметр LAN / IPsec VPN."),
        ("id-elem-net-dmz", "CommunicationNetwork", "Периметр безопасности DMZ", "Демилитаризованная зона внешних сетевых интерфейсов."),
        ("id-elem-net-internal", "CommunicationNetwork", "Изолированная сеть контейнеров", "Внутренняя сеть взаимодействия бэкенда и СУБД."),
        
        ("id-elem-art-spa", "Artifact", "Дистрибутив React SPA (Static Bundle)", "Скомпилированные статические файлы клиентского интерфейса."),
        ("id-elem-art-backend", "Artifact", "Пакет Backend API Core", "Исполняемый дистрибутив FastAPI приложения."),
        ("id-elem-art-storage", "Artifact", "Том хранилища (storage/attachments/)", "Изолированный том постоянного хранения проверенных файлов."),
        ("id-elem-art-dbdata", "Artifact", "Файлы данных PostgreSQL", "Физические файлы табличных пространств СУБД.")
    ]

    for eid, etype, ename, edoc in elements_data:
        el = ET.SubElement(elements_elem, f"{{{NS}}}element", {
            "identifier": eid,
            f"{{{XSI}}}type": etype
        })
        n = ET.SubElement(el, f"{{{NS}}}name", {"xml:lang": "ru"})
        n.text = ename
        d = ET.SubElement(el, f"{{{NS}}}documentation", {"xml:lang": "ru"})
        d.text = edoc

    # Define Relationships: (id, rel_type, source_id, target_id, name, doc)
    relationships_elem = ET.SubElement(model, f"{{{NS}}}relationships")

    relationships_data = [
        # Business Actor -> Role Assignments
        ("id-rel-01", "Assignment", "id-elem-ba-manager", "id-elem-br-operator", "Назначение", "Менеджер исполняет роль оператора воронки."),
        ("id-rel-02", "Assignment", "id-elem-ba-supervisor", "id-elem-br-curator", "Назначение", "Руководитель исполняет роль куратора портфеля."),
        ("id-rel-03", "Assignment", "id-elem-ba-admin", "id-elem-br-secadmin", "Назначение", "Администратор исполняет роль администратора безопасности."),
        
        # Business Roles -> Processes (Assignments / Serving)
        ("id-rel-04", "Assignment", "id-elem-br-operator", "id-elem-bp-initiation", "Выполняет", "Оператор ведет стадию инициации."),
        ("id-rel-05", "Assignment", "id-elem-br-operator", "id-elem-bp-contracting", "Выполняет", "Оператор ведет договорную кампанию."),
        ("id-rel-06", "Assignment", "id-elem-br-operator", "id-elem-bp-transfer", "Выполняет", "Оператор организует передачу материалов и ПО."),
        ("id-rel-07", "Assignment", "id-elem-br-curator", "id-elem-bp-analytics", "Контролирует", "Куратор анализирует сводные отчеты."),
        ("id-rel-08", "Assignment", "id-elem-br-secadmin", "id-elem-bp-analytics", "Администрирует", "Администратор аудирует действия пользователей."),
        
        # Process Flow / Triggering
        ("id-rel-09", "Triggering", "id-elem-bp-initiation", "id-elem-bp-contracting", "Переход к договорам", "Успешная встреча инициирует оформление договоров."),
        ("id-rel-10", "Triggering", "id-elem-bp-contracting", "id-elem-bp-transfer", "Переход к внедрению", "Подписание договора и лицензии открывает передачу материалов."),
        ("id-rel-11", "Triggering", "id-elem-bp-transfer", "id-elem-bp-study", "Запуск обучения", "Передача материалов и обучение педагогов активирует занятия."),
        
        # Business Collaboration
        ("id-rel-12", "Aggregation", "id-elem-bc-partnership", "id-elem-ba-manager", "Участник", "Ростелеком представлен менеджером."),
        ("id-rel-13", "Aggregation", "id-elem-bc-partnership", "id-elem-ba-unirep", "Участник", "Вуз представлен контактным лицом."),
        
        # Processes -> Business Objects (Access)
        ("id-rel-14", "Access", "id-elem-bp-initiation", "id-elem-bo-interaction", "Создание и изменение", "Инициация создает карточку взаимодействия."),
        ("id-rel-15", "Access", "id-elem-bp-contracting", "id-elem-bo-contract", "Формирование", "Процесс оформляет договор."),
        ("id-rel-16", "Access", "id-elem-bp-contracting", "id-elem-bo-license", "Формирование", "Процесс оформляет лицензию."),
        ("id-rel-17", "Access", "id-elem-bp-initiation", "id-elem-bo-contact", "Ввод данных", "Процесс фиксирует контактные данные представителя."),
        ("id-rel-18", "Access", "id-elem-bp-analytics", "id-elem-bo-report", "Генерация", "Процесс генерирует отчетные срезы."),

        # Application Component Composition
        ("id-rel-19", "Composition", "id-elem-ac-crm", "id-elem-ac-frontend", "Содержит", "CRM включает клиентское SPA приложение."),
        ("id-rel-20", "Composition", "id-elem-ac-crm", "id-elem-ac-backend", "Содержит", "CRM включает ядро FastAPI бэкенда."),
        ("id-rel-21", "Composition", "id-elem-ac-backend", "id-elem-ac-workflow", "Подсистема", "Движок воронки и версионирования workflow."),
        ("id-rel-22", "Composition", "id-elem-ac-backend", "id-elem-ac-reports", "Подсистема", "Движок аналитических отчетов XLSX/PDF."),
        ("id-rel-23", "Composition", "id-elem-ac-backend", "id-elem-ac-files", "Подсистема", "Служба безопасного хранения файлов."),
        ("id-rel-24", "Composition", "id-elem-ac-backend", "id-elem-ac-import", "Подсистема", "Мастер двухфазного импорта каталогов."),
        ("id-rel-25", "Composition", "id-elem-ac-backend", "id-elem-ac-integrations", "Подсистема", "Шлюз интеграций и очередь сверки коллизий."),
        ("id-rel-26", "Composition", "id-elem-ac-backend", "id-elem-ac-audit", "Подсистема", "Служба неизменяемого темпорального аудита."),

        # Components -> Interfaces
        ("id-rel-27", "Realization", "id-elem-ac-backend", "id-elem-ai-rest", "Реализует", "Бэкенд предоставляет REST API v1."),
        ("id-rel-28", "Realization", "id-elem-ac-frontend", "id-elem-ai-gui", "Реализует", "SPA предоставляет графический интерфейс пользователя."),
        ("id-rel-29", "Realization", "id-elem-ac-keycloak", "id-elem-ai-oidc", "Реализует", "Keycloak предоставляет OIDC эндпоинты."),
        ("id-rel-30", "Realization", "id-elem-ac-integrations", "id-elem-ai-lms", "Реализует", "Шлюз интеграций принимает пакеты LMS DTO v1.0."),
        ("id-rel-31", "Realization", "id-elem-ac-integrations", "id-elem-ai-web", "Реализует", "Шлюз интеграций принимает вебхуки сайта."),

        # Frontend -> Backend & External Flows
        ("id-rel-32", "Serving", "id-elem-ai-rest", "id-elem-ac-frontend", "Обслуживает", "REST API обслуживает фронтенд вызовы."),
        ("id-rel-33", "Serving", "id-elem-ai-oidc", "id-elem-ac-frontend", "Аутентификация", "Keycloak аутентифицирует пользователя в SPA."),
        ("id-rel-34", "Serving", "id-elem-ai-oidc", "id-elem-ac-backend", "Валидация", "Keycloak поставляет JWKS для валидации токенов бэкендом."),
        ("id-rel-35", "Flow", "id-elem-ac-lms", "id-elem-ai-lms", "Поток метрик", "LMS Zion поставляет данные успеваемости и потоков."),
        ("id-rel-36", "Flow", "id-elem-ac-website", "id-elem-ai-web", "Поток заявок", "Сайт Laravel поставляет входящие заявки вузов."),

        # Components -> Application Services
        ("id-rel-37", "Realization", "id-elem-ac-workflow", "id-elem-as-interaction", "Реализует", "Движок реализует сервис взаимодействия."),
        ("id-rel-38", "Realization", "id-elem-ac-backend", "id-elem-as-auth", "Реализует", "Бэкенд реализует проверку прав и Scope 152-ФЗ."),
        ("id-rel-39", "Realization", "id-elem-ac-reports", "id-elem-as-reports", "Реализует", "Модуль отчетов реализует сервис аналитики."),
        ("id-rel-40", "Realization", "id-elem-ac-files", "id-elem-as-files", "Реализует", "Файловый сервис реализует защищенное хранение."),
        ("id-rel-41", "Realization", "id-elem-ac-integrations", "id-elem-as-sync", "Реализует", "Интеграционный шлюз реализует очередь сверки."),

        # Services -> Business Processes (Serving)
        ("id-rel-42", "Serving", "id-elem-as-interaction", "id-elem-bp-initiation", "Поддерживает", "Сервис поддерживает процесс инициации."),
        ("id-rel-43", "Serving", "id-elem-as-interaction", "id-elem-bp-contracting", "Поддерживает", "Сервис поддерживает процесс договоров."),
        ("id-rel-44", "Serving", "id-elem-as-reports", "id-elem-bp-analytics", "Поддерживает", "Сервис формирует управленческую аналитику."),

        # Components -> Data Objects (Access)
        ("id-rel-45", "Access", "id-elem-ac-workflow", "id-elem-do-interaction", "Чтение и запись", "Движок обновляет ревизии карточки."),
        ("id-rel-46", "Access", "id-elem-ac-audit", "id-elem-do-event", "Append-Only запись", "Аудит фиксирует неизменяемые события."),
        ("id-rel-47", "Access", "id-elem-ac-files", "id-elem-do-attachment", "Чтение и запись", "Файловая служба хранит метаданные и SHA-256."),
        ("id-rel-48", "Access", "id-elem-ac-integrations", "id-elem-do-inbox", "Дедупликация и запись", "Очередь сверки нормализует заявки."),
        ("id-rel-49", "Access", "id-elem-ac-integrations", "id-elem-do-metric", "Запись показателей", "Шлюз сохраняет учебные метрики."),
        ("id-rel-50", "Access", "id-elem-ac-frontend", "id-elem-do-token", "In-Memory удержание", "SPA хранит токен только в памяти."),

        # Technology Layer Relationships
        ("id-rel-51", "Assignment", "id-elem-dev-client", "id-elem-ss-browser", "Развернут", "Браузер выполняется на клиентском месте."),
        ("id-rel-52", "Assignment", "id-elem-node-app", "id-elem-ss-linux", "Установлена", "Linux развернут на сервере приложений."),
        ("id-rel-53", "Assignment", "id-elem-node-app", "id-elem-ss-docker", "Установлен", "Docker развернут на сервере приложений."),
        ("id-rel-54", "Assignment", "id-elem-node-app", "id-elem-ss-nginx", "Развернут", "Nginx обслуживает внешние запросы."),
        ("id-rel-55", "Assignment", "id-elem-node-app", "id-elem-ss-python", "Развернут", "Python исполняет бэкенд."),
        ("id-rel-56", "Assignment", "id-elem-node-db", "id-elem-ss-postgres", "Развернута", "PostgreSQL развернута на сервере БД."),
        
        ("id-rel-57", "Realization", "id-elem-art-spa", "id-elem-ac-frontend", "Воплощает", "Дистрибутив SPA реализует фронтенд компонент."),
        ("id-rel-58", "Realization", "id-elem-art-backend", "id-elem-ac-backend", "Воплощает", "Пакет бэкенда реализует FastAPI компонент."),
        ("id-rel-59", "Realization", "id-elem-art-storage", "id-elem-ac-files", "Хранилище", "Файловый том обеспечивает хранение вложений."),
        ("id-rel-60", "Association", "id-elem-art-dbdata", "id-elem-ss-postgres", "Файлы данных", "Табличные пространства СУБД."),
        
        ("id-rel-61", "Association", "id-elem-node-app", "id-elem-net-dmz", "Сетевое подключение", "Сервер приложений подключен к DMZ."),
        ("id-rel-62", "Association", "id-elem-node-app", "id-elem-net-internal", "Сетевое подключение", "Сервер приложений подключен к внутренней сети."),
        ("id-rel-63", "Association", "id-elem-node-db", "id-elem-net-internal", "Сетевое подключение", "Сервер БД подключен к внутренней сети."),
        ("id-rel-64", "Association", "id-elem-dev-client", "id-elem-net-corp", "Сетевое подключение", "Клиентские ПК подключены к корпоративной сети.")
    ]

    for rid, rtype, rsrc, rtgt, rname, rdoc in relationships_data:
        rel = ET.SubElement(relationships_elem, f"{{{NS}}}relationship", {
            "identifier": rid,
            "source": rsrc,
            "target": rtgt,
            f"{{{XSI}}}type": rtype
        })
        n = ET.SubElement(rel, f"{{{NS}}}name", {"xml:lang": "ru"})
        n.text = rname
        d = ET.SubElement(rel, f"{{{NS}}}documentation", {"xml:lang": "ru"})
        d.text = rdoc

    # Views & Diagrams
    views_elem = ET.SubElement(model, f"{{{NS}}}views")
    diagrams_elem = ET.SubElement(views_elem, f"{{{NS}}}diagrams")

    def add_node(view, nid, eref, x, y, w, h, fill_rgb=(255, 255, 255), line_rgb=(100, 100, 100)):
        node = ET.SubElement(view, f"{{{NS}}}node", {
            "identifier": nid,
            "elementRef": eref,
            f"{{{XSI}}}type": "Element",
            "x": str(x), "y": str(y), "w": str(w), "h": str(h)
        })
        style = ET.SubElement(node, f"{{{NS}}}style")
        ET.SubElement(style, f"{{{NS}}}fillColor", {"r": str(fill_rgb[0]), "g": str(fill_rgb[1]), "b": str(fill_rgb[2]), "a": "100"})
        ET.SubElement(style, f"{{{NS}}}lineColor", {"r": str(line_rgb[0]), "g": str(line_rgb[1]), "b": str(line_rgb[2]), "a": "100"})
        return node

    def add_conn(view, cid, relref, src_node, tgt_node, line_rgb=(100, 100, 100)):
        conn = ET.SubElement(view, f"{{{NS}}}connection", {
            "identifier": cid,
            "relationshipRef": relref,
            "source": src_node,
            "target": tgt_node,
            f"{{{XSI}}}type": "Relationship"
        })
        style = ET.SubElement(conn, f"{{{NS}}}style")
        ET.SubElement(style, f"{{{NS}}}lineColor", {"r": str(line_rgb[0]), "g": str(line_rgb[1]), "b": str(line_rgb[2]), "a": "100"})
        return conn

    # View 1: System Context & Business Process View
    v1 = ET.SubElement(diagrams_elem, f"{{{NS}}}view", {
        "identifier": "id-view-1-context",
        f"{{{XSI}}}type": "Diagram"
    })
    v1_name = ET.SubElement(v1, f"{{{NS}}}name", {"xml:lang": "ru"})
    v1_name.text = "1. Контекст системы и бизнес-процессы воронки (Context & Business View)"
    v1_doc = ET.SubElement(v1, f"{{{NS}}}documentation", {"xml:lang": "ru"})
    v1_doc.text = "Связь бизнес-акторов, ролей, этапов воронки партнерств и центральной системы CRM."

    add_node(v1, "v1-n-manager", "id-elem-ba-manager", 50, 50, 160, 60, (255, 255, 180))
    add_node(v1, "v1-n-supervisor", "id-elem-ba-supervisor", 250, 50, 160, 60, (255, 255, 180))
    add_node(v1, "v1-n-admin", "id-elem-ba-admin", 450, 50, 160, 60, (255, 255, 180))
    add_node(v1, "v1-n-unirep", "id-elem-ba-unirep", 650, 50, 180, 60, (255, 255, 180))

    add_node(v1, "v1-n-operator", "id-elem-br-operator", 50, 150, 160, 55, (255, 240, 160))
    add_node(v1, "v1-n-curator", "id-elem-br-curator", 250, 150, 160, 55, (255, 240, 160))
    add_node(v1, "v1-n-secadmin", "id-elem-br-secadmin", 450, 150, 160, 55, (255, 240, 160))

    add_node(v1, "v1-n-bp-init", "id-elem-bp-initiation", 50, 250, 170, 65, (255, 225, 140))
    add_node(v1, "v1-n-bp-cont", "id-elem-bp-contracting", 260, 250, 170, 65, (255, 225, 140))
    add_node(v1, "v1-n-bp-tran", "id-elem-bp-transfer", 470, 250, 170, 65, (255, 225, 140))
    add_node(v1, "v1-n-bp-stud", "id-elem-bp-study", 680, 250, 170, 65, (255, 225, 140))
    add_node(v1, "v1-n-bp-an", "id-elem-bp-analytics", 260, 350, 170, 65, (255, 225, 140))

    add_node(v1, "v1-n-crm", "id-elem-ac-crm", 260, 460, 380, 80, (180, 220, 255))
    add_node(v1, "v1-n-bo-card", "id-elem-bo-interaction", 50, 350, 170, 55, (255, 255, 200))
    add_node(v1, "v1-n-bo-rep", "id-elem-bo-report", 470, 350, 170, 55, (255, 255, 200))

    add_conn(v1, "v1-c-01", "id-rel-01", "v1-n-manager", "v1-n-operator")
    add_conn(v1, "v1-c-02", "id-rel-02", "v1-n-supervisor", "v1-n-curator")
    add_conn(v1, "v1-c-03", "id-rel-03", "v1-n-admin", "v1-n-secadmin")
    add_conn(v1, "v1-c-04", "id-rel-04", "v1-n-operator", "v1-n-bp-init")
    add_conn(v1, "v1-c-05", "id-rel-05", "v1-n-operator", "v1-n-bp-cont")
    add_conn(v1, "v1-c-06", "id-rel-06", "v1-n-operator", "v1-n-bp-tran")
    add_conn(v1, "v1-c-07", "id-rel-07", "v1-n-curator", "v1-n-bp-an")
    add_conn(v1, "v1-c-09", "id-rel-09", "v1-n-bp-init", "v1-n-bp-cont")
    add_conn(v1, "v1-c-10", "id-rel-10", "v1-n-bp-cont", "v1-n-bp-tran")
    add_conn(v1, "v1-c-11", "id-rel-11", "v1-n-bp-tran", "v1-n-bp-stud")
    add_conn(v1, "v1-c-14", "id-rel-14", "v1-n-bp-init", "v1-n-bo-card")
    add_conn(v1, "v1-c-18", "id-rel-18", "v1-n-bp-an", "v1-n-bo-rep")

    # View 2: Application Component Architecture View
    v2 = ET.SubElement(diagrams_elem, f"{{{NS}}}view", {
        "identifier": "id-view-2-application",
        f"{{{XSI}}}type": "Diagram"
    })
    v2_name = ET.SubElement(v2, f"{{{NS}}}name", {"xml:lang": "ru"})
    v2_name.text = "2. Компонентная структура приложений (Application Component View)"
    v2_doc = ET.SubElement(v2, f"{{{NS}}}documentation", {"xml:lang": "ru"})
    v2_doc.text = "Декомпозиция SPA, FastAPI ядра, движков воронки, отчетов, файлов, адаптеров и сервисов данных."

    add_node(v2, "v2-n-spa", "id-elem-ac-frontend", 50, 100, 200, 70, (180, 220, 255))
    add_node(v2, "v2-n-ai-rest", "id-elem-ai-rest", 320, 105, 180, 50, (190, 230, 255))
    add_node(v2, "v2-n-backend", "id-elem-ac-backend", 560, 90, 240, 90, (160, 200, 255))
    
    add_node(v2, "v2-n-keycloak", "id-elem-ac-keycloak", 50, 220, 190, 65, (210, 210, 255))
    add_node(v2, "v2-n-ai-oidc", "id-elem-ai-oidc", 50, 310, 190, 45, (220, 220, 255))

    add_node(v2, "v2-n-wf", "id-elem-ac-workflow", 320, 220, 180, 60, (170, 210, 255))
    add_node(v2, "v2-n-rep", "id-elem-ac-reports", 530, 220, 180, 60, (170, 210, 255))
    add_node(v2, "v2-n-files", "id-elem-ac-files", 740, 220, 180, 60, (170, 210, 255))
    
    add_node(v2, "v2-n-import", "id-elem-ac-import", 320, 310, 180, 60, (170, 210, 255))
    add_node(v2, "v2-n-int", "id-elem-ac-integrations", 530, 310, 180, 60, (170, 210, 255))
    add_node(v2, "v2-n-audit", "id-elem-ac-audit", 740, 310, 180, 60, (170, 210, 255))

    add_node(v2, "v2-n-lms", "id-elem-ac-lms", 430, 430, 170, 60, (220, 230, 240))
    add_node(v2, "v2-n-web", "id-elem-ac-website", 630, 430, 170, 60, (220, 230, 240))

    add_node(v2, "v2-n-do-card", "id-elem-do-interaction", 320, 520, 160, 50, (190, 240, 220))
    add_node(v2, "v2-n-do-ev", "id-elem-do-event", 510, 520, 160, 50, (190, 240, 220))
    add_node(v2, "v2-n-do-att", "id-elem-do-attachment", 700, 520, 160, 50, (190, 240, 220))
    add_node(v2, "v2-n-do-tok", "id-elem-do-token", 50, 400, 180, 50, (190, 240, 220))

    add_conn(v2, "v2-c-20", "id-rel-20", "v2-n-backend", "v2-n-spa")
    add_conn(v2, "v2-c-27", "id-rel-27", "v2-n-backend", "v2-n-ai-rest")
    add_conn(v2, "v2-c-32", "id-rel-32", "v2-n-ai-rest", "v2-n-spa")
    add_conn(v2, "v2-c-21", "id-rel-21", "v2-n-backend", "v2-n-wf")
    add_conn(v2, "v2-c-22", "id-rel-22", "v2-n-backend", "v2-n-rep")
    add_conn(v2, "v2-c-23", "id-rel-23", "v2-n-backend", "v2-n-files")
    add_conn(v2, "v2-c-24", "id-rel-24", "v2-n-backend", "v2-n-import")
    add_conn(v2, "v2-c-25", "id-rel-25", "v2-n-backend", "v2-n-int")
    add_conn(v2, "v2-c-26", "id-rel-26", "v2-n-backend", "v2-n-audit")
    add_conn(v2, "v2-c-29", "id-rel-29", "v2-n-keycloak", "v2-n-ai-oidc")
    add_conn(v2, "v2-c-33", "id-rel-33", "v2-n-ai-oidc", "v2-n-spa")
    add_conn(v2, "v2-c-45", "id-rel-45", "v2-n-wf", "v2-n-do-card")
    add_conn(v2, "v2-c-46", "id-rel-46", "v2-n-audit", "v2-n-do-ev")
    add_conn(v2, "v2-c-47", "id-rel-47", "v2-n-files", "v2-n-do-att")
    add_conn(v2, "v2-c-50", "id-rel-50", "v2-n-spa", "v2-n-do-tok")

    # View 3: Technology Infrastructure & Deployment View
    v3 = ET.SubElement(diagrams_elem, f"{{{NS}}}view", {
        "identifier": "id-view-3-technology",
        f"{{{XSI}}}type": "Diagram"
    })
    v3_name = ET.SubElement(v3, f"{{{NS}}}name", {"xml:lang": "ru"})
    v3_name.text = "3. Технологическая инфраструктура и развертывание (Technology Deployment View)"
    v3_doc = ET.SubElement(v3, f"{{{NS}}}documentation", {"xml:lang": "ru"})
    v3_doc.text = "Серверные узлы, операционные системы, Docker контейнеры, СУБД, Nginx и сетевые контуры."

    add_node(v3, "v3-n-dev", "id-elem-dev-client", 50, 80, 200, 70, (210, 235, 210))
    add_node(v3, "v3-n-browser", "id-elem-ss-browser", 50, 180, 200, 60, (200, 230, 200))
    add_node(v3, "v3-n-art-spa", "id-elem-art-spa", 50, 270, 200, 55, (230, 240, 230))

    add_node(v3, "v3-n-net-corp", "id-elem-net-corp", 300, 80, 180, 50, (240, 240, 200))
    add_node(v3, "v3-n-net-dmz", "id-elem-net-dmz", 300, 150, 180, 50, (240, 220, 200))
    add_node(v3, "v3-n-net-int", "id-elem-net-internal", 300, 220, 180, 50, (240, 200, 200))

    add_node(v3, "v3-n-node-app", "id-elem-node-app", 530, 60, 250, 90, (210, 235, 210))
    add_node(v3, "v3-n-linux-app", "id-elem-ss-linux", 530, 170, 250, 60, (200, 230, 200))
    add_node(v3, "v3-n-docker", "id-elem-ss-docker", 530, 250, 250, 60, (200, 230, 200))
    add_node(v3, "v3-n-nginx", "id-elem-ss-nginx", 530, 330, 250, 55, (190, 225, 190))
    add_node(v3, "v3-n-python", "id-elem-ss-python", 530, 405, 250, 55, (190, 225, 190))
    add_node(v3, "v3-n-art-be", "id-elem-art-backend", 530, 480, 250, 55, (230, 240, 230))

    add_node(v3, "v3-n-node-db", "id-elem-node-db", 830, 60, 220, 90, (210, 235, 210))
    add_node(v3, "v3-n-pg", "id-elem-ss-postgres", 830, 170, 220, 60, (190, 225, 190))
    add_node(v3, "v3-n-dbdata", "id-elem-art-dbdata", 830, 250, 220, 55, (230, 240, 230))
    add_node(v3, "v3-n-storage", "id-elem-art-storage", 830, 330, 220, 55, (230, 240, 230))

    add_conn(v3, "v3-c-51", "id-rel-51", "v3-n-dev", "v3-n-browser")
    add_conn(v3, "v3-c-52", "id-rel-52", "v3-n-node-app", "v3-n-linux-app")
    add_conn(v3, "v3-c-53", "id-rel-53", "v3-n-node-app", "v3-n-docker")
    add_conn(v3, "v3-c-54", "id-rel-54", "v3-n-node-app", "v3-n-nginx")
    add_conn(v3, "v3-c-55", "id-rel-55", "v3-n-node-app", "v3-n-python")
    add_conn(v3, "v3-c-56", "id-rel-56", "v3-n-node-db", "v3-n-pg")
    add_conn(v3, "v3-c-58", "id-rel-58", "v3-n-art-be", "v3-n-node-app")
    add_conn(v3, "v3-c-60", "id-rel-60", "v3-n-dbdata", "v3-n-pg")
    add_conn(v3, "v3-c-61", "id-rel-61", "v3-n-node-app", "v3-n-net-dmz")
    add_conn(v3, "v3-c-62", "id-rel-62", "v3-n-node-app", "v3-n-net-int")
    add_conn(v3, "v3-c-63", "id-rel-63", "v3-n-node-db", "v3-n-net-int")
    add_conn(v3, "v3-c-64", "id-rel-64", "v3-n-dev", "v3-n-net-corp")

    # Serialize to string with indentation
    tree = ET.ElementTree(model)
    ET.indent(tree, space="  ", level=0)
    
    out_path = "docs/architecture/rost_crm_architecture.archimate"
    tree.write(out_path, encoding="UTF-8", xml_declaration=True)
    print(f"Successfully generated ArchiMate 3.1 Model Exchange XML at: {out_path}")

    # Validate parsing
    parsed = ET.parse(out_path)
    root = parsed.getroot()
    print("Verification: parsed root tag:", root.tag)
    
    elems = root.find(f"{{{NS}}}elements")
    rels = root.find(f"{{{NS}}}relationships")
    views = root.find(f"{{{NS}}}views").find(f"{{{NS}}}diagrams")
    
    print(f"Total elements: {len(elems)}")
    print(f"Total relationships: {len(rels)}")
    print(f"Total views: {len(views)}")
    
    # Verify all references
    elem_ids = {e.attrib["identifier"] for e in elems}
    rel_ids = {r.attrib["identifier"] for r in rels}
    
    for r in rels:
        src = r.attrib["source"]
        tgt = r.attrib["target"]
        assert src in elem_ids, f"Unknown rel source: {src}"
        assert tgt in elem_ids, f"Unknown rel target: {tgt}"
        
    for v in views:
        node_ids = set()
        for n in v.findall(f"{{{NS}}}node"):
            nid = n.attrib["identifier"]
            eref = n.attrib["elementRef"]
            assert eref in elem_ids, f"Unknown node elementRef: {eref} in view {v.attrib['identifier']}"
            node_ids.add(nid)
        for c in v.findall(f"{{{NS}}}connection"):
            rref = c.attrib["relationshipRef"]
            csrc = c.attrib["source"]
            ctgt = c.attrib["target"]
            assert rref in rel_ids, f"Unknown conn relationshipRef: {rref} in view {v.attrib['identifier']}"
            assert csrc in node_ids, f"Unknown conn source node: {csrc} in view {v.attrib['identifier']}"
            assert ctgt in node_ids, f"Unknown conn target node: {ctgt} in view {v.attrib['identifier']}"
            
    print("ALL INTEGRITY CHECKS PASSED!")

if __name__ == "__main__":
    build_model()
