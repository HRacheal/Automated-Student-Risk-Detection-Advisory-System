# backend/services/base.py
from dataclasses import dataclass, field
from typing import Any

# Source status values
OK = "ok"                      # reachable, data retrieved
NOT_CONFIGURED = "not_configured"
UNAVAILABLE = "unavailable"    # endpoint not reachable (service down / not installed)
ERROR = "error"                # reachable but returned an error (auth, permissions...)


class SourceError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class SourceResult:
    source: str
    status: str
    message: str = ""
    records: list[Any] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "students": len(self.records),
            "details": self.details,
        }
