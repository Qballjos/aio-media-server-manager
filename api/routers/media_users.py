"""Administrator controls for Seerr imports and AIO media-account access."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from applications.catalog import ApplicationCatalog
from core.auth import auth_manager
from core.integrations.credentials import get_application_api_key
from core.integrations.seerr import SeerrClient

router = APIRouter(prefix="/api/settings/media-users", tags=["Media users"])
AccountId = Annotated[str, Field(pattern=r"^[a-zA-Z0-9-]{1,80}$")]


class Selection(BaseModel):
    account_ids: list[AccountId] = Field(min_length=1, max_length=100)


def _client() -> SeerrClient:
    plugin = ApplicationCatalog().get("seerr")
    key = get_application_api_key("seerr", plugin.config_dir)
    if not key:
        raise HTTPException(503, "Configure the Seerr API key first.")
    return SeerrClient(port=plugin.port, api_key=key)


@router.get("")
def list_media_users(request: Request):
    auth_manager.authenticate_request(request)
    with _client() as client:
        provider, server_id = client.media_user_source()
        candidates, imported = client.media_user_accounts(provider)
    grants = auth_manager.media_users.versions(provider, server_id)
    return {
        "provider": provider,
        "users": [
            {
                "id": account_id,
                "name": name,
                "imported": account_id in imported,
                "enabled": account_id in grants,
            }
            for account_id, name in (candidates | imported).items()
        ],
    }


@router.post("")
def grant_media_users(selection: Selection, request: Request):
    auth_manager.authenticate_request(request)
    with _client() as client:
        provider, server_id = client.media_user_source()
        candidates, imported = client.media_user_accounts(provider)
        selected = set(selection.account_ids)
        if not selected <= (candidates.keys() | imported.keys()):
            raise HTTPException(404, "One or more media accounts were not found.")
        pending = sorted(selected - imported.keys())
        if pending:
            client.import_media_users(provider, pending)
            _, imported = client.media_user_accounts(provider)
        if not selected <= imported.keys():
            raise HTTPException(409, "Seerr did not import all selected accounts.")
    for account_id in sorted(selected):
        auth_manager.media_users.grant(provider, server_id, account_id)
    return {"enabled": sorted(selected)}


@router.delete("/{account_id}", status_code=204)
def revoke_media_user(account_id: AccountId, request: Request):
    auth_manager.authenticate_request(request)
    with _client() as client:
        provider, server_id = client.media_user_source()
    auth_manager.media_users.revoke(provider, server_id, account_id)
