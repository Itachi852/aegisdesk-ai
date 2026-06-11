from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def get_stats():
    return {"daily_questions": [], "feedback": {"like": 0, "dislike": 0}}
