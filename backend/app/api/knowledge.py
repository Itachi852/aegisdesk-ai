from fastapi import APIRouter, UploadFile

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/documents")
async def upload_document(file: UploadFile):
    return {"filename": file.filename, "status": "processing"}


@router.get("/documents")
def list_documents():
    return {"items": []}


@router.delete("/documents/{document_id}")
def delete_document(document_id: int):
    return {"id": document_id, "deleted": True}
