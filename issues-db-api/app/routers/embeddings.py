from fastapi import APIRouter, Form, UploadFile, HTTPException, Depends
from fastapi.responses import StreamingResponse
from app.routers.authentication import validate_token
from app.dependencies import fs, embeddings_collection
from app.exceptions import embedding_not_found_exception, bson_exception, embedding_file_not_found_exception
from bson import ObjectId
import bson
from app.util import read_file_in_chunks
from pydantic import BaseModel

router = APIRouter(
    prefix='/embeddings',
    tags=['embeddings']
)


class EmbeddingOut(BaseModel):
    embedding_id: str
    name: str
    config: dict
    has_file: bool


class EmbeddingsOut(BaseModel):
    embeddings: list[EmbeddingOut]


class EmbeddingIdOut(BaseModel):
    embedding_id: str


class UpdateEmbedding(BaseModel):
    name: str
    config: dict


def _get_embedding(embedding_id: str, attributes: list[str]):
    try:
        embedding = embeddings_collection.find_one({'_id': ObjectId(embedding_id)}, attributes)
    except bson.errors.BSONError as e:
        raise bson_exception(str(e))
    if embedding is None:
        raise embedding_not_found_exception(embedding_id)
    return embedding


@router.get('', response_model=EmbeddingsOut)
def get_all_embeddings():
    """
    Get all embeddings and their configs.
    """
    embeddings = []
    for embedding in embeddings_collection.find({}):
        embeddings.append(EmbeddingOut(
            embedding_id=str(embedding['_id']),
            name=embedding['name'],
            config=embedding['config'],
            has_file=embedding['file_id'] is not None
        ))
    return EmbeddingsOut(embeddings=embeddings)


@router.post('', response_model=EmbeddingIdOut)
def create_embedding(request: UpdateEmbedding, token=Depends(validate_token)):
    """
    Create a new embedding with the given config.
    """
    _id = embeddings_collection.insert_one({
        'config': request.config,
        'name': request.name,
        'file_id': None
    }).inserted_id
    return {
        'embedding_id': str(_id)
    }


@router.get('/{embedding_id}', response_model=EmbeddingOut)
def get_embedding(embedding_id: str):
    embedding = _get_embedding(embedding_id, ['name', 'config', 'file_id'])
    return EmbeddingOut(
        embedding_id=str(embedding['_id']),
        name=embedding['name'],
        config=embedding['config'],
        has_file=embedding['file_id'] is not None
    )


@router.post('/{embedding_id}')
def update_embedding(embedding_id: str, request: UpdateEmbedding, token=Depends(validate_token)):
    """
    Update the config of the given embedding.
    """
    try:
        result = embeddings_collection.update_one(
            {'_id': ObjectId(embedding_id)},
            {'$set': {'name': request.name, 'config': request.config}}
        )
    except bson.errors.BSONError as e:
        raise bson_exception(str(e))
    if result.matched_count == 0:
        raise embedding_not_found_exception(embedding_id)


@router.delete('/{embedding_id}')
def delete_embedding(embedding_id: str, token=Depends(validate_token)):
    """
    Delete the embedding with the given embedding id
    """
    embedding = _get_embedding(embedding_id, ['file_id'])
    if embedding['file_id'] is not None:
        fs.delete(embedding['file_id'])
    embeddings_collection.delete_one({'_id': ObjectId(embedding_id)})


@router.post('/{embedding_id}/file')
def upload_embedding_file(embedding_id: str, file: UploadFile = Form(), token=Depends(validate_token)):
    """
    Upload embedding file for the given embedding.
    """
    embedding = _get_embedding(embedding_id, ['file_id'])
    if embedding['file_id'] is not None:
        # Delete existing embedding
        fs.delete(embedding['file_id'])
    # Upload new embedding
    file_id = fs.put(file.file, filename=file.filename)
    embeddings_collection.update_one(
        {'_id': ObjectId(embedding_id)},
        {'$set': {'file_id': file_id}}
    )


@router.get('/{embedding_id}/file')
def get_embedding_file(embedding_id: str):
    """
    Get the embedding file for the given embedding.
    """
    embedding = _get_embedding(embedding_id, ['file_id'])
    if embedding['file_id'] is None:
        raise embedding_file_not_found_exception(embedding_id)
    mongo_file = fs.get(embedding['file_id'])
    return StreamingResponse(read_file_in_chunks(mongo_file),
                             media_type='application/octet-stream')


@router.delete('/{embedding_id}/file')
def delete_embedding_file(embedding_id: str, token=Depends(validate_token)):
    """
    Delete embedding file for the given embedding.
    """
    embedding = _get_embedding(embedding_id, ['file_id'])
    if embedding['file_id'] is None:
        raise embedding_file_not_found_exception(embedding_id)
    # Delete existing embedding
    fs.delete(embedding['file_id'])
    embeddings_collection.update_one(
        {'_id': ObjectId(embedding_id)},
        {'$set': {'file_id': None}}
    )
