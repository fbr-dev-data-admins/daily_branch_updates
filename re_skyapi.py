"""Session-only authentication client for the Raiser's Edge NXT SKY API."""

from datetime import datetime, timedelta
from typing import Any, MutableMapping
from urllib.parse import urlencode

import requests


AUTH_URL = "https://oauth2.sky.blackbaud.com/authorization"
TOKEN_URL = "https://oauth2.sky.blackbaud.com/token"
API_BASE_URL = "https://api.sky.blackbaud.com"


class RESkyAPI:
    """Manage Blackbaud OAuth tokens in a caller-provided session mapping.

    The client intentionally has no token-file support: access tokens, refresh
    tokens, and expiration timestamps exist only in the Streamlit session passed
    by the app.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        subscription_key: str,
        session_state: MutableMapping[str, Any],
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.subscription_key = subscription_key
        self.session_state = session_state

    def get_authorization_url(self) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, authorization_code: str) -> None:
        data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.post(TOKEN_URL, data=data)
        response.raise_for_status()
        self._store_token_response(response.json(), require_refresh_token=True)

    def refresh_access_token(self) -> bool:
        refresh_token = self.session_state.get("re_refresh_token")
        if not refresh_token:
            return False
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        response = requests.post(TOKEN_URL, data=data)
        response.raise_for_status()
        self._store_token_response(response.json(), require_refresh_token=False)
        return True

    def _store_token_response(self, token_data: dict, require_refresh_token: bool) -> None:
        self.session_state["re_access_token"] = token_data["access_token"]
        if require_refresh_token:
            self.session_state["re_refresh_token"] = token_data["refresh_token"]
        else:
            self.session_state["re_refresh_token"] = token_data.get(
                "refresh_token", self.session_state.get("re_refresh_token")
            )
        self.session_state["re_token_expires_at"] = datetime.now() + timedelta(
            seconds=token_data.get("expires_in", 3600)
        )

    def is_authenticated(self) -> bool:
        if not self.session_state.get("re_access_token"):
            return False
        expires_at = self.session_state.get("re_token_expires_at")
        if expires_at and datetime.now() >= expires_at - timedelta(minutes=5):
            return self.refresh_access_token()
        return True

    def get_headers(self) -> dict[str, str]:
        """Return SKY headers without Content-Type, which breaks SKY GETs."""
        return {
            "Authorization": f"Bearer {self.session_state['re_access_token']}",
            "Bb-Api-Subscription-Key": self.subscription_key,
            "Cache-Control": "no-cache",
        }
