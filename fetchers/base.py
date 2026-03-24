from abc import ABC, abstractmethod

import requests

from schema.models import Company, Signal

_DEFAULT_TIMEOUT = 15
_DEFAULT_HEADERS = {"User-Agent": "Pemetiq/ProjectB contact@pemetiq.com"}


class BaseFetcher(ABC):
    """Contract all fetchers must satisfy: accept a Company, return list[Signal]."""

    @abstractmethod
    def fetch(self, company: Company) -> list[Signal]:
        ...

    # --- shared HTTP helpers ---

    def get(self, url: str, params: dict | None = None, timeout: int = _DEFAULT_TIMEOUT) -> requests.Response:
        resp = requests.get(url, params=params, headers=_DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp

    def get_json(self, url: str, params: dict | None = None, timeout: int = _DEFAULT_TIMEOUT) -> dict | list:
        return self.get(url, params=params, timeout=timeout).json()
