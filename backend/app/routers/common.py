import email
import email.policy

from fastapi import Request

from ..errors import APIError
from ..models import User
from ..services import permissions


def _user_dict(user: User, auth_mode: str) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "team_id": user.team_id,
        "permissions": permissions(user),
        "auth_mode": auth_mode,
    }


async def _extract_uploaded_file_and_revision(
    request: Request,
) -> tuple[str, bytes, str | None, int | None]:
    cl_header = request.headers.get("content-length")
    if cl_header:
        try:
            if int(cl_header) > 26_214_400:
                raise APIError("FILE_TOO_LARGE", "Размер файла превышает 25 МБ.", 413)
        except ValueError:
            pass

    body = await request.body()
    if len(body) > 26_214_400:
        raise APIError("FILE_TOO_LARGE", "Размер файла превышает 25 МБ.", 413)
    if not body:
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Передан пустой файл.", 422)

    exp_rev_raw: str | None = (
        request.query_params.get("expected_revision")
        or request.query_params.get("expected-revision")
        or request.headers.get("expected_revision")
        or request.headers.get("expected-revision")
        or request.headers.get("x-expected-revision")
    )

    ct = request.headers.get("content-type", "")
    if "multipart/form-data" in ct:
        msg = email.message_from_bytes(f"Content-Type: {ct}\r\n\r\n".encode("utf-8") + body, policy=email.policy.default)
        parts = list(msg.iter_parts())
        for part in parts:
            if part.get_param("name", header="content-disposition") in ("expected_revision", "expected-revision"):
                rev_payload = part.get_payload(decode=True) or part.get_payload()
                part_val = ""
                if isinstance(rev_payload, bytes):
                    part_val = rev_payload.decode("utf-8", errors="replace").strip()
                elif isinstance(rev_payload, str):
                    part_val = rev_payload.strip()
                if part_val:
                    exp_rev_raw = part_val

        file_part = None
        for part in parts:
            if part.get_param("name", header="content-disposition") in ("expected_revision", "expected-revision"):
                continue
            fn = part.get_filename()
            if fn:
                payload = part.get_payload(decode=True)
                file_part = (fn, payload or b"", part.get_content_type())
                break
        if not file_part:
            for part in parts:
                if part.get_param("name", header="content-disposition") == "file":
                    fn = part.get_filename() or "upload.bin"
                    payload = part.get_payload(decode=True)
                    file_part = (fn, payload or b"", part.get_content_type())
                    break
        if not file_part:
            raise APIError("FILE_TYPE_NOT_ALLOWED", "Файл не найден в multipart форме.", 422)
        fn, payload, content_type = file_part
    else:
        cd = request.headers.get("content-disposition", "")
        fn = None
        if cd:
            cd_msg = email.message.EmailMessage()
            cd_msg["content-disposition"] = cd
            fn = cd_msg.get_filename()
        fn = fn or request.headers.get("x-file-name") or request.query_params.get("filename") or "upload.bin"
        payload, content_type = body, ct or None

    exp_rev: int | None = None
    if exp_rev_raw is not None:
        val = str(exp_rev_raw).strip()
        if val != "":
            try:
                exp_rev = int(val)
            except (ValueError, TypeError):
                raise APIError("VALIDATION_ERROR", "Параметр expected_revision должен быть целым числом.", 422)
            if exp_rev < 1:
                raise APIError("VALIDATION_ERROR", "Параметр expected_revision должен быть >= 1.", 422)

    return fn, payload, content_type, exp_rev


async def _extract_uploaded_file(request: Request) -> tuple[str, bytes, str | None]:
    fn, payload, ct, _ = await _extract_uploaded_file_and_revision(request)
    return fn, payload, ct
