from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel


_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _interpolate(value: str) -> str:
    """Replace ${VAR} placeholders with values from os.environ."""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        result = os.environ.get(var_name)
        if result is None:
            raise ValueError(
                f"Environment variable '{var_name}' referenced in config but not set."
            )
        return result

    return _ENV_VAR_RE.sub(_replace, value)


def _interpolate_dict(data: dict) -> dict:
    """Recursively interpolate env vars in all string values of a dict."""
    out = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = _interpolate(v)
        elif isinstance(v, dict):
            out[k] = _interpolate_dict(v)
        elif isinstance(v, list):
            out[k] = [
                _interpolate_dict(item) if isinstance(item, dict)
                else (_interpolate(item) if isinstance(item, str) else item)
                for item in v
            ]
        else:
            out[k] = v
    return out


class AccountConfig(BaseModel):
    name: str
    type: str  # "monobank" or "wise"
    token: str
    iban: Optional[str] = None
    card_type: Optional[str] = None
    profile_id: Optional[str] = None


class SpendeeSyncConfig(BaseModel):
    accounts: List[AccountConfig]

    @classmethod
    def from_yaml(cls, path: str) -> "SpendeeSyncConfig":
        """Load config from a YAML file, interpolating ${VAR} env references."""
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        raw = _interpolate_dict(raw)
        return cls(**raw)

    @classmethod
    def from_env(cls) -> "SpendeeSyncConfig":
        """Build a single-account config from legacy environment variables."""
        account_type = os.getenv("ACCOUNT_TYPE", "monobank").lower()
        if account_type == "wise":
            token = os.environ.get("WISE_TOKEN", "")
            accounts = [
                AccountConfig(
                    name="Wise",
                    type="wise",
                    token=token,
                    profile_id=os.getenv("WISE_PROFILE_ID"),
                )
            ]
        else:
            token = os.environ.get("MONOBANK_TOKEN", "")
            accounts = [
                AccountConfig(
                    name="Monobank",
                    type="monobank",
                    token=token,
                    iban=os.getenv("IBAN"),
                    card_type=os.getenv("CARD_TYPE"),
                )
            ]
        return cls(accounts=accounts)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "SpendeeSyncConfig":
        """
        Load configuration.

        Resolution order:
        1. Explicit ``config_path`` argument
        2. ``SPENDEE_SYNC_CONFIG`` environment variable
        3. ``config.yaml`` in the current working directory
        4. Fall back to single-account mode via legacy env vars
        """
        path = config_path or os.getenv("SPENDEE_SYNC_CONFIG")
        if path is None:
            default = Path("config.yaml")
            if default.exists():
                path = str(default)

        if path is not None:
            return cls.from_yaml(path)

        return cls.from_env()
