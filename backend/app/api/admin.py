from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def get_stats():
    """
    获取后台统计数据占位接口。

    :return: 每日提问和反馈统计数据。
    """
    return {"daily_questions": [], "feedback": {"like": 0, "dislike": 0}}
