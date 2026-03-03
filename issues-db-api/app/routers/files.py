from app.dependencies import files_collection, fs
from app.exceptions import file_not_found_exception
from app.routers.authentication import validate_token
from app.util import read_file_in_chunks
from bson import ObjectId
from fastapi import APIRouter, Form, UploadFile, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/files", tags=["files"])


class FileOut(BaseModel):
    file_id: str
    description: str
    category: str


class FileIdOut(BaseModel):
    file_id: str


class Category(BaseModel):
    category: str | None


@router.get("", response_model=list[FileOut])
def get_files(request: Category):
    if request.category is None:
        files = files_collection.find()
    else:
        files = files_collection.find({"category": request.category})

    return [
        FileOut(
            file_id=str(file["_id"]),
            description=file["description"],
            category=file["category"],
        )
        for file in files
    ]


@router.post("", response_model=FileIdOut)
def create_file(
    file: UploadFile = Form(),
    description: str = Form(),
    category: str = Form(),
    token=Depends(validate_token),
):
    file_id = fs.put(file.file, filename=file.filename)
    files_collection.insert_one(
        {"_id": file_id, "description": description, "category": category}
    )
    return FileIdOut(file_id=str(file_id))


@router.get("/{file_id}", response_model=FileOut)
def get_file(file_id: str):
    file = files_collection.find_one({"_id": ObjectId(file_id)})
    if file is None:
        raise file_not_found_exception(file_id)
    return FileOut(
        file_id=str(file["_id"]),
        description=file["description"],
        category=file["category"],
    )


@router.delete("/{file_id}")
def delete_file(file_id: str, token=Depends(validate_token)):
    result = files_collection.delete_one({"_id": ObjectId(file_id)})
    if result.deleted_count != 1:
        raise file_not_found_exception(file_id)
    fs.delete(ObjectId(file_id))


@router.get("/{file_id}/file")
def get_file_file(file_id: str):
    file = files_collection.find_one({"_id": ObjectId(file_id)})
    if file is None:
        raise file_not_found_exception(file_id)
    fs_file = fs.get(file["_id"])
    return StreamingResponse(
        read_file_in_chunks(fs_file), media_type="application/octet-stream"
    )
