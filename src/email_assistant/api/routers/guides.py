from fastapi import APIRouter, HTTPException

from email_assistant import guides

router = APIRouter(tags=["guides"])


@router.get("/guides/{step}")
async def guide(step: str):
    steps = guides.load()["steps"]
    if step not in steps:
        raise HTTPException(404, f"No guide for {step!r}")
    return steps[step]
