"""Support reports and replies for media members and the appliance administrator."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, StringConstraints

from core.auth import auth_manager
from core.support import Owner, SupportReports

router = APIRouter(prefix="/api/support", tags=["Support"])
Subject = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Reply(BaseModel):
    message: Message


class NewReport(Reply):
    subject: Subject


class ReportStatus(BaseModel):
    status: Literal["new", "in_progress", "resolved"]


def _store() -> SupportReports:
    return SupportReports(auth_manager.media_users.path.parent)


def _member(request: Request) -> Owner:
    auth_manager.authenticate_member_request(request)
    return request.state.media_account


def _owner(request: Request) -> Owner | None:
    try:
        auth_manager.authenticate_request(request)
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        return _member(request)
    return None


def _not_found():
    return HTTPException(404, "Support report not found.")


@router.get("")
def list_reports(request: Request, response: Response):
    owner = _owner(request)
    rows = _store().list(owner)
    response.headers["Cache-Control"] = "no-store"
    return {"reports": rows, "new_count": sum(row["status"] == "new" for row in rows) if owner is None else 0}


@router.post("", status_code=201)
def create_report(payload: NewReport, request: Request):
    owner = _member(request)
    store = _store()
    report_id = store.create(owner, payload.subject, payload.message)
    return store.detail(report_id, owner)


@router.get("/{report_id}")
def get_report(report_id: str, request: Request, response: Response):
    report = _store().detail(report_id, _owner(request))
    if report is None:
        raise _not_found()
    response.headers["Cache-Control"] = "no-store"
    return report


@router.post("/{report_id}/replies", status_code=201)
def reply_to_report(report_id: str, payload: Reply, request: Request):
    owner = _owner(request)
    store = _store()
    if not store.reply(report_id, owner, payload.message):
        raise _not_found()
    return store.detail(report_id, owner)


@router.patch("/{report_id}")
def change_report_status(report_id: str, payload: ReportStatus, request: Request):
    auth_manager.authenticate_request(request)
    store = _store()
    if not store.update_status(report_id, payload.status):
        raise _not_found()
    return store.detail(report_id, None)
