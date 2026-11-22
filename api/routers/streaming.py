"""Private streaming preferences and their Seerr-backed catalog."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from api.routers.media_users import _client
from core.auth import auth_manager
from core.integrations.streaming import ADMIN_STREAMING_ACCOUNT, streaming_providers, streaming_regions

router = APIRouter(prefix="/api/streaming", tags=["Streaming subscriptions"])
Scope = Literal["admin", "member"]
Country = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
ProviderId = Annotated[int, Field(gt=0, strict=True)]


class StreamingPreference(BaseModel):
    country: Country
    provider_ids: list[ProviderId] = Field(max_length=200)


def _account(scope: Scope, request: Request, response: Response) -> tuple[str, str, str]:
    response.headers["Cache-Control"] = "private, no-store"
    if scope == "member":
        auth_manager.authenticate_member_request(request)
        return request.state.media_account
    auth_manager.authenticate_request(request)
    return ADMIN_STREAMING_ACCOUNT


@router.get("/{scope}/preferences")
def get_preferences(scope: Scope, request: Request, response: Response):
    account = _account(scope, request, response)
    country, provider_ids = auth_manager.media_users.streaming(account)
    return {"country": country, "provider_ids": provider_ids}


@router.get("/{scope}/catalog")
def get_catalog(scope: Scope, request: Request, response: Response, country: Annotated[Country | None, Query()] = None):
    _account(scope, request, response)
    with _client() as seerr:
        if country is None:
            return {"regions": streaming_regions(seerr.watch_provider_regions())}
        return {"providers": streaming_providers(seerr.watch_provider_catalog(country))}


@router.put("/{scope}/preferences")
def save_preferences(scope: Scope, body: StreamingPreference, request: Request, response: Response):
    account = _account(scope, request, response)
    provider_ids = list(dict.fromkeys(body.provider_ids))
    with _client() as seerr:
        if body.country not in streaming_regions(seerr.watch_provider_regions()):
            raise HTTPException(422, "Unsupported streaming country.")
        if provider_ids:
            available = {row["id"] for row in streaming_providers(seerr.watch_provider_catalog(body.country))}
            if not available.issuperset(provider_ids):
                raise HTTPException(422, "Some services are unavailable in this streaming country.")
    auth_manager.media_users.set_streaming(account, body.country, provider_ids)
    return {"country": body.country, "provider_ids": provider_ids}
