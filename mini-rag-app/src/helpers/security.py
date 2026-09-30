from fastapi import Depends, Header, HTTPException
from helpers.config import get_settings, Settings
import secrets


async def verify_api_key(x_api_key: str = Header(default=None),
                         settings: Settings = Depends(get_settings)):
    if not settings.APP_API_KEY:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.APP_API_KEY):
        raise HTTPException(status_code=401, detail="invalid api key")
