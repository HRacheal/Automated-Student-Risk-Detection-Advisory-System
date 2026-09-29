"""
Server-to-server link to My Coach (the risk engine). The LMS never computes risk itself:
it only asks My Coach for the signed-in student's OWN summary, using the student ID from
the server-side session (never from the browser).
"""
from typing import Optional

import httpx

from .config import settings


async def risk_summary(student_id: str, transport: Optional[httpx.AsyncBaseTransport] = None) -> dict:
    base = {"portal_url": settings.MYCOACH_PORTAL_URL}
    if not settings.MYCOACH_API_URL or not settings.MYCOACH_INTEGRATION_KEY:
        return {**base, "available": False, "message": "The My Coach connection is not configured."}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=3), transport=transport) as client:
            res = await client.get(f"{settings.MYCOACH_API_URL}/api/integration/lms/students/{student_id}/summary",
                                   headers={"X-Integration-Key": settings.MYCOACH_INTEGRATION_KEY})
    except httpx.HTTPError:
        return {**base, "available": False, "message": "My Coach is currently unavailable."}
    if res.status_code == 404:
        return {**base, "available": False, "message": "My Coach has not synchronised your record yet."}
    if res.status_code != 200:
        return {**base, "available": False, "message": f"My Coach could not provide your summary (HTTP {res.status_code})."}
    data = res.json()
    if str(data.get("student_id")) != str(student_id):   # defence in depth: never show someone else's summary
        return {**base, "available": False, "message": "My Coach returned an unexpected record."}
    return {**base, "available": True, **data}
