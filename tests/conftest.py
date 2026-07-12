from __future__ import annotations

import shutil

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="session")
def chrome_available() -> bool:
    return shutil.which("chromedriver") is not None or shutil.which("google-chrome") is not None or shutil.which("chromium") is not None
