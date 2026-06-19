import os
import json
from typing import Dict, List, Any

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

SERVICE_ACCOUNT_INFO = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID")
STUDENTS_RANGE = os.getenv("GOOGLE_STUDENTS_RANGE", "roster!A:ZZ")


def get_credentials():
    if not SERVICE_ACCOUNT_INFO:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_FILE environment variable is missing."
        )

    try:
        service_account_info = json.loads(SERVICE_ACCOUNT_INFO)

        return service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )

    except json.JSONDecodeError as e:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_FILE contains invalid JSON."
        ) from e


def get_sheets_service():
    return build("sheets", "v4", credentials=get_credentials())


def quote_sheet_name(name: str) -> str:
    return f"'{name}'"


def normalize_range(range_name: str) -> str:
    if "!" in range_name:
        sheet_part, cell_part = range_name.split("!", 1)
        sheet_part = sheet_part.strip()

        if sheet_part.startswith("'") and sheet_part.endswith("'"):
            return range_name

        return f"{quote_sheet_name(sheet_part)}!{cell_part}"

    return range_name


def get_sheet_names() -> List[str]:
    service = get_sheets_service()

    spreadsheet = (
        service.spreadsheets()
        .get(spreadsheetId=SPREADSHEET_ID)
        .execute()
    )

    return [
        sheet["properties"]["title"]
        for sheet in spreadsheet.get("sheets", [])
    ]


def fetch_sheet_rows(range_name: str = None) -> List[List[str]]:
    if range_name is None:
        range_name = STUDENTS_RANGE

    range_name = normalize_range(range_name)

    service = get_sheets_service()

    candidates = [range_name]

    if "!" in range_name:
        sheet_part, cell_part = range_name.split("!", 1)
        sheet_name = sheet_part.strip("'")

        candidates.append(f"{quote_sheet_name(sheet_name)}!A1:ZZ1000")
        candidates.append(f"{quote_sheet_name(sheet_name)}!A:ZZ")

    for sheet in get_sheet_names():
        candidates.append(f"{quote_sheet_name(sheet)}!A1:ZZ1000")
        candidates.append(f"{quote_sheet_name(sheet)}!A:ZZ")

    seen = set()

    for candidate in candidates:
        if candidate in seen:
            continue

        seen.add(candidate)

        try:
            result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=SPREADSHEET_ID,
                    range=candidate,
                )
                .execute()
            )

            values = result.get("values", [])

            if values:
                return values

        except HttpError:
            continue

    return []


def normalize_header(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace(" ", "_")
        .replace("%", "percent")
    )


def row_to_dict(
    headers: List[str],
    row: List[str],
) -> Dict[str, Any]:
    row = row + [""] * (len(headers) - len(row))

    return {
        normalize_header(header): row[index]
        for index, header in enumerate(headers)
    }


def get_all_students() -> List[Dict[str, Any]]:
    rows = fetch_sheet_rows()

    if not rows:
        return []

    headers = rows[0]

    students = []

    for row in rows[1:]:
        if not any(str(cell).strip() for cell in row):
            continue

        record = row_to_dict(headers, row)

        student_id = str(
            record.get("student_id", "")
        ).strip()

        student_name = str(
            record.get("name", "")
        ).strip()

        if student_id and student_name:
            students.append(
                {
                    "student_id": student_id,
                    "student_name": student_name,
                    "raw": record,
                }
            )

    return students


def get_student_profile(student_id: str) -> Dict[str, Any]:
    """
    Fetch comprehensive student profile from all sheets:
    roster, exam_scores, attendance, exam_schedule
    """
    student_id = str(student_id).strip()
    
    profile = {
        "student_id": student_id,
        "roster": {},
        "exam_scores": [],
        "attendance": [],
        "exam_schedule": [],
    }
    
    # Fetch from roster sheet
    roster_data = fetch_sheet_rows("roster!A:ZZ")
    if roster_data:
        headers = roster_data[0]
        for row in roster_data[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            record = row_to_dict(headers, row)
            if str(record.get("student_id", "")).strip() == student_id:
                profile["roster"] = {
                    "student_id": record.get("student_id", ""),
                    "name": record.get("name", ""),
                    "program": record.get("program", ""),
                    "cohort": record.get("cohort", ""),
                    "manager_email": record.get("manager_email", ""),
                }
                break
    
    # Fetch from exam_scores sheet
    scores_data = fetch_sheet_rows("exam_scores!A:ZZ")
    if scores_data:
        headers = scores_data[0]
        for row in scores_data[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            record = row_to_dict(headers, row)
            if str(record.get("student_id", "")).strip() == student_id:
                try:
                    score = float(record.get("score", 0))
                    max_score = float(record.get("max_score", 100))
                    percentage = (score / max_score * 100) if max_score > 0 else 0
                except ValueError:
                    score = record.get("score", 0)
                    max_score = record.get("max_score", 100)
                    percentage = 0
                
                profile["exam_scores"].append({
                    "subject": record.get("subject", ""),
                    "score": score,
                    "max_score": max_score,
                    "percentage": round(percentage, 2),
                    "date": record.get("date", ""),
                })
    
    # Fetch from attendance sheet
    attendance_data = fetch_sheet_rows("attendance!A:ZZ")
    if attendance_data:
        headers = attendance_data[0]
        for row in attendance_data[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            record = row_to_dict(headers, row)
            if str(record.get("student_id", "")).strip() == student_id:
                profile["attendance"].append({
                    "week_of": record.get("week_of", ""),
                    "classes_scheduled": record.get("classes_scheduled", ""),
                    "classes_attended": record.get("classes_attended", ""),
                    "attendance_pct": record.get("attendance_pct", ""),
                })
    
    # Fetch from exam_schedule sheet
    schedule_data = fetch_sheet_rows("exam_schedule!A:ZZ")
    if schedule_data:
        headers = schedule_data[0]
        for row in schedule_data[1:]:
            if not any(str(cell).strip() for cell in row):
                continue
            record = row_to_dict(headers, row)
            if str(record.get("student_id", "")).strip() == student_id:
                profile["exam_schedule"].append({
                    "subject": record.get("subject", ""),
                    "exam_date": record.get("exam_date", ""),
                    "exam_type": record.get("exam_type", ""),
                })
    
    return profile