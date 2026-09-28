import io
import re
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.importer import (
    _detect_file_type,
    _match_header,
    parse_tabular_file,
    preview_organizations_import,
    commit_organizations_import,
)
from app.models import User
from tests.test_vendors_import import make_test_xlsx


class TestChallengerAdversarial:
    """Empirical adversarial test suite challenging auto-detection,
    header matching, full-name assembly, phone cleaning, and organizer file parsing.
    """

    # =========================================================================
    # 1. Challenge _detect_file_type with various filenames & headers
    # =========================================================================

    @pytest.mark.parametrize(
        "fn",
        [
            "сотрудники.xlsx",
            "users_2026.csv",
            "кадры.xlsx",
            "пользователи.xlsx",
            "персонал_компании.csv",
            "СОТРУДНИКИ_ИТ.XLSX",
            "Новые_Users.csv",
            "отдел_кадров.xlsx",
        ],
    )
    def test_detect_file_type_user_markers_in_filename(self, fn: str):
        """Files with user keywords in filename must detect as 'users' even with minimal headers."""
        headers = ["Col1", "Col2", "Col3"]
        assert _detect_file_type(headers, filename=fn) == "users"

    @pytest.mark.parametrize(
        "fn",
        [
            "студенты_курса.xlsx",
            "слушатели_семестра.xlsx",
            "Список_студентов.xlsx",
        ],
    )
    def test_detect_file_type_learner_markers_in_filename(self, fn: str):
        """Files with learner/student keywords in filename must detect as 'lms_learners'."""
        headers = ["Col1", "Col2", "Col3"]
        assert _detect_file_type(headers, filename=fn) == "lms_learners"

    @pytest.mark.parametrize(
        "fn",
        [
            "вендоры.xlsx",
            "vendor_list.csv",
            "ВЕНДОРЫ_ПО.XLSX",
            "список_vendor_2026.xlsx",
        ],
    )
    def test_detect_file_type_vendor_markers_in_filename(self, fn: str):
        """Files with vendor keywords in filename must detect as 'vendors'."""
        headers = ["Col1", "Col2"]
        assert _detect_file_type(headers, filename=fn) == "vendors"

    def test_detect_file_type_generic_filename_with_user_headers(self):
        """Generic filename data.xlsx with user headers must detect as 'users'."""
        headers = ["Фамилия", "Имя", "Отчествопри наличии)", "Номер телефона", "Email"]
        assert _detect_file_type(headers, filename="data.xlsx") == "users"
        assert _detect_file_type(headers, filename=None) == "users"

    @pytest.mark.parametrize(
        "headers",
        [
            ["Фамилия", "Имя"],
            ["Фамилия", "Email"],
            ["Фамилия", "Номер телефона"],
            ["Фамилия", "тел."],
            ["Отчество", "Должность"],
        ],
    )
    def test_detect_file_type_user_attribute_combinations(self, headers: list[str]):
        """Individual/employee markers or surname pairs without explicit university must detect as 'users'."""
        assert _detect_file_type(headers, filename="unrelated_name.csv") == "users"

    @pytest.mark.parametrize(
        "headers",
        [
            ["СНИЛС", "Номер"],
            ["Паспорт", "Серия"],
            ["Регистрация", "Адрес"],
            ["Диплом", "Специальность"],
            ["Профессия", "Стаж"],
        ],
    )
    def test_detect_file_type_learner_attribute_combinations(self, headers: list[str]):
        """Individual learner/education markers must detect as 'lms_learners'."""
        assert _detect_file_type(headers, filename="unrelated_name.csv") == "lms_learners"

    @pytest.mark.parametrize(
        "headers",
        [
            ["Дата рождения", "Город"],
            ["Адрес регистрации", "Город"],
            ["Регион регистрации", "Город"],
        ],
    )
    def test_detect_file_type_learner_inflection_limitation(self, headers: list[str]):
        """Genitive case learner markers ('рождения', 'регистрации') detect as 'lms_learners'."""
        assert _detect_file_type(headers, filename="unrelated_name.csv") == "lms_learners"

    def test_detect_file_type_vendor_vs_org(self):
        """Disambiguation between vendor and organization headers."""
        # Vendors
        assert _detect_file_type(["Вендор", "ПО", "Контакт"], filename="table.xlsx") == "vendors"
        assert _detect_file_type(["Компания", "Продукт", "Email"], filename="data.csv") == "vendors"
        assert _detect_file_type(["Программное обеспечение", "Разработчик"], filename="items.xlsx") == "vendors"
        assert _detect_file_type(["ПО", "Сайт"], filename="items.xlsx") == "vendors"

        # Organizations
        assert _detect_file_type(["Название вуза", "Тип", "Ректор"], filename="table.xlsx") == "organizations"
        assert _detect_file_type(["Наименование организации", "Город"], filename="table.xlsx") == "organizations"
        assert _detect_file_type(["Университет", "Договор"], filename="table.xlsx") == "organizations"
        assert _detect_file_type(["Институт", "Кафедра"], filename="table.xlsx") == "organizations"

    def test_detect_file_type_org_with_user_contact_headers_stays_org(self):
        """A university table containing contact headers (Фамилия, Имя, Email) must detect as 'organizations'."""
        headers = ["Название вуза", "Фамилия", "Имя", "Email", "Номер телефона"]
        assert _detect_file_type(headers, filename="universities.xlsx") == "organizations"
        assert _detect_file_type(headers, filename="data.xlsx") == "organizations"

    # =========================================================================
    # 2. Challenge _match_header: exclusions and edge cases
    # =========================================================================

    def test_match_header_dative_and_diploma_exclusions(self):
        """Headers in dative case or diploma context must return None and NOT match last_name/first_name/patronymic."""
        # Dative case variants
        assert _match_header("Фамилиядательный падеж)", file_type="users") is None
        assert _match_header("Фамилия (в дательном падеже)", file_type="users") is None
        assert _match_header("Имядательный падеж)", file_type="users") is None
        assert _match_header("Имя (в дательном падеже)", file_type="users") is None
        assert _match_header("Отчестводательный падеж)", file_type="users") is None
        assert _match_header("Отчество (в дательном падеже)", file_type="users") is None

        # Diploma variants
        assert _match_header("Фамилия, указанная в дипломе", file_type="users") is None
        assert _match_header("Имя по диплому", file_type="users") is None
        assert _match_header("Отчество по диплому", file_type="users") is None
        assert _match_header("Фамилия в дипломе", file_type="users") is None

        # Primary names must match
        assert _match_header("Фамилия", file_type="users") == "last_name"
        assert _match_header("Имя", file_type="users") == "first_name"
        assert _match_header("Отчество", file_type="users") == "patronymic"
        assert _match_header("Отчествопри наличии)", file_type="users") == "patronymic"
        assert _match_header("Отчество (при наличии)", file_type="users") == "patronymic"

    # =========================================================================
    # 3. Challenge parse_tabular_file: Full name assembly (2 vs 3 parts), phones, roles
    # =========================================================================

    def test_parse_tabular_file_composite_fio_no_overwriting(self):
        """Ensure dative/diploma columns do NOT overwrite primary last_name in parsed rows."""
        rows = [
            [
                "Фамилия",
                "Имя",
                "Отчество",
                "Фамилиядательный падеж)",
                "Фамилия, указанная в дипломе",
                "Email",
                "Номер телефона",
            ],
            [
                "Сидоров",
                "Алексей",
                "Владимирович",
                "Сидорову",
                "Петров",
                "sidorov@test.ru",
                "+7 (999) 111-22-33",
            ],
        ]
        content = make_test_xlsx(rows)
        parsed = parse_tabular_file(content, filename="users.xlsx")
        assert len(parsed) == 1
        row = parsed[0]
        assert row["_file_type"] == "lms_learners"
        assert row["last_name"] == "Сидоров"
        assert row["first_name"] == "Алексей"
        assert row["patronymic"] == "Владимирович"
        assert row["name"] == "Сидоров Алексей Владимирович"
        assert row["full_name"] == "Сидоров Алексей Владимирович"
        assert row["phone"] == "79991112233"
        assert row["role"] == "learner"

    def test_parse_tabular_file_two_part_name_no_double_spaces(self):
        """Ensure 2-part name (Фамилия + Имя, no patronymic) joins cleanly with 1 space."""
        rows = [
            ["Фамилия", "Имя", "Email"],
            ["Ковалев", "Сергей", "kovalev@test.ru"],
        ]
        content = make_test_xlsx(rows)
        parsed = parse_tabular_file(content, filename="users.xlsx")
        assert len(parsed) == 1
        assert parsed[0]["name"] == "Ковалев Сергей"
        assert parsed[0]["full_name"] == "Ковалев Сергей"
        assert "  " not in parsed[0]["name"]

    def test_parse_tabular_file_empty_patronymic_cell_no_double_spaces(self):
        """Ensure row with patronymic column but empty cell value joins cleanly."""
        rows = [
            ["Фамилия", "Имя", "Отчество", "Email"],
            ["Смирнова", "Анна", "", "smirnova@test.ru"],
            ["Кузнецов", "Игорь", "   ", "kuznetsov@test.ru"],
        ]
        content = make_test_xlsx(rows)
        parsed = parse_tabular_file(content, filename="users.xlsx")
        assert len(parsed) == 2
        assert parsed[0]["name"] == "Смирнова Анна"
        assert parsed[1]["name"] == "Кузнецов Игорь"
        assert "  " not in parsed[0]["name"]
        assert "  " not in parsed[1]["name"]

    @pytest.mark.parametrize(
        "raw_phone, expected_digits",
        [
            ("+7 (999) 023-43-65", "79990234365"),
            ("8 (999) 023-43-65", "89990234365"),
            ("79990234365", "79990234365"),
            ("+7 999 023 43 65", "79990234365"),
            ("8-800-555-35-35", "88005553535"),
            ("  +7(912)3456789  ", "79123456789"),
        ],
    )
    def test_parse_tabular_file_phone_cleaning_adversarial(self, raw_phone: str, expected_digits: str):
        """Ensure phone numbers with various formatting are stripped to digits only."""
        rows = [
            ["Фамилия", "Имя", "Email", "Номер телефона"],
            ["Тестов", "Тест", "test@test.ru", raw_phone],
        ]
        content = make_test_xlsx(rows)
        parsed = parse_tabular_file(content, filename="users.xlsx")
        assert len(parsed) == 1
        assert parsed[0]["phone"] == expected_digits

    def test_parse_tabular_file_role_preservation_and_default(self):
        """Ensure explicit role is preserved, but missing/empty role defaults to 'manager'."""
        rows = [
            ["Фамилия", "Имя", "Email", "Роль"],
            ["Админов", "Админ", "admin@test.ru", "administrator"],
            ["Юзеров", "Юзер", "user@test.ru", ""],
        ]
        content = make_test_xlsx(rows)
        parsed = parse_tabular_file(content, filename="users.xlsx")
        assert len(parsed) == 2
        assert parsed[0]["role"] == "administrator"
        assert parsed[1]["role"] == "manager"

    # =========================================================================
    # 4. Challenge with real organizers' file
    # =========================================================================

    def test_real_organizer_xlsx_file_auto_detection_and_rows(self, client: TestClient):
        """Verify real organizers' file parses all 5 rows with exact FIOs and 0 errors."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        real_file_path = repo_root / "данные предоставленные организаторами" / "Загрузка пользователей.xlsx"
        assert real_file_path.exists()
        file_bytes = real_file_path.read_bytes()

        # Test A: auto-detection without filename (pure header inference)
        parsed_no_fn = parse_tabular_file(file_bytes, filename=None)
        assert len(parsed_no_fn) == 5
        assert parsed_no_fn[0]["_file_type"] == "lms_learners"

        # Test B: auto-detection with real filename
        parsed_with_fn = parse_tabular_file(file_bytes, filename="Загрузка пользователей.xlsx")
        assert len(parsed_with_fn) == 5
        assert parsed_with_fn[0]["_file_type"] == "lms_learners"

        expected_fios = [
            "Черепанова Светлана Васильевна",
            "Кричанов Максим Сергеевич",
            "Григорьев Станислав Семенович",
            "Осипенко Ирина Викторовна",
            "Иванов Михаил Петрович",
        ]
        expected_phones = [
            "79990234365",
            "79977361351",
            "79947392263",
            "79934253846",
            "79924583434",
        ]
        for idx, exp_name in enumerate(expected_fios):
            row = parsed_with_fn[idx]
            assert row["name"] == exp_name
            assert row["full_name"] == exp_name
            assert row["phone"] == expected_phones[idx]
            assert row["role"] == "learner"

        # Test C: full preview endpoint without import_type
        files = {
            "file": (
                "Загрузка пользователей.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        resp = client.post(
            "/api/v1/catalogs/organizations/import/preview",
            files=files,
            headers={"X-Demo-User": "administrator"},
        )
        assert resp.status_code == 200, resp.text
        preview = resp.json()
        assert preview["detected_type"] == "lms_learners"
        assert preview["total_rows"] == 5
        assert preview["valid_count"] == 5
        assert preview["error_count"] == 0
