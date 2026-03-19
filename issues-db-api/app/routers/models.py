import io
import json
import typing

import bson
from app.dependencies import fs, models_collection, issue_labels_collection
from app.exceptions import (
    model_not_found_exception,
    version_not_found_exception,
    performance_not_found_exception,
    issue_not_found_exception,
    bson_exception,
)
from app.routers.authentication import validate_token
from app.util import read_file_in_chunks
from bson import ObjectId
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/models", tags=["models"])


class PostModelIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ml_config: dict = Field(alias="model_config")
    model_name: typing.Optional[str] = None


class PostModelOut(BaseModel):
    model_id: str


class GetModelOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model_id: str
    model_name: typing.Optional[str] = None
    ml_config: dict = Field(alias="model_config")


class UpdateModelIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model_name: typing.Optional[str] = None
    ml_config: typing.Optional[dict] = Field(default=None, alias="model_config")


class SimpleModelOut(BaseModel):
    model_id: str
    model_name: str


class GetModelsOut(BaseModel):
    models: list[SimpleModelOut]


class PostPerformanceIn(BaseModel):
    performance: list


class PostPerformanceOut(BaseModel):
    performance_id: str


class PerformanceDescriptionOut(BaseModel):
    performance_id: str
    description: str


class PerformancesOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "performances": [{"performance_id": "string", "description": "string"}]
        }
    })

    performances: list[PerformanceDescriptionOut]


class PerformanceOut(BaseModel):
    performance_id: str
    description: str
    performance: list


class Prediction(BaseModel):
    prediction: bool
    confidence: float


class PostPredictionsIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "predictions": {
                "issue_id": {"existence": {"prediction": True, "confidence": 0.42}}
            }
        }
    })

    predictions: dict[str, dict[str, Prediction]]


class GetPredictionsIn(BaseModel):
    issue_ids: list[str] | None


class GetPredictionsOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "predictions": {
                "issue_id": {"existence": {"prediction": True, "confidence": 0.42}}
            }
        }
    })

    predictions: dict[str, dict[str, Prediction] | None]


class VersionOut(BaseModel):
    version_id: str
    description: str


class VersionIdOut(BaseModel):
    version_id: str


class VersionsOut(BaseModel):
    versions: list[VersionOut]


class UpdateDescriptionIn(BaseModel):
    description: str


def _get_model(model_id: str, attributes: list[str]):
    model = models_collection.find_one({"_id": ObjectId(model_id)}, attributes)
    if model is None:
        raise model_not_found_exception(model_id)
    return model


def _update_model(model_id: str, update: dict):
    result = models_collection.update_one({"_id": ObjectId(model_id)}, update)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f'Model "{model_id}" was not found')


def _delete_predictions(model_id: str, version_id: ObjectId):
    # Remove predictions
    issue_labels_collection.update_many(
        {}, {"$unset": {f"predictions.{model_id}-{version_id}": ""}}
    )
    # Remove indexes
    indexes = issue_labels_collection.index_information()
    for key, value in indexes.items():
        for col in value["key"]:
            if f"predictions.{model_id}-{version_id}" in col[0]:
                issue_labels_collection.drop_index(key)
                break


def _delete_version(model_id: str, version_id: ObjectId):
    # Remove file
    fs.delete(version_id)
    _delete_predictions(model_id, version_id)


@router.get("", response_model=GetModelsOut)
def get_all_models():
    """
    Returns a list of all models in the database.
    """
    models = models_collection.find({}, ["name"])
    response = []
    for model in models:
        response.append(
            SimpleModelOut(model_id=str(model["_id"]), model_name=model["name"])
        )
    return GetModelsOut(models=response)


@router.post("", response_model=PostModelOut)
def create_model(request: PostModelIn, token=Depends(validate_token)):
    """
    Creates a new model entry with the given config.
    """
    _id = models_collection.insert_one(
        {
            "name": "" if request.model_name is None else request.model_name,
            "config": request.ml_config,
            "versions": {},
            "performances": {},
        }
    ).inserted_id
    return PostModelOut(model_id=str(_id))


@router.get("/{model_id}", response_model=GetModelOut)
def get_model(model_id: str):
    """
    Return the model with the specified model id.
    """
    model = _get_model(model_id, ["name", "config"])
    return GetModelOut(
        model_id=model_id, model_name=model["name"], ml_config=model["config"]
    )


@router.post("/{model_id}")
def update_model(model_id: str, request: UpdateModelIn, token=Depends(validate_token)):
    """
    Update the name and/or config of the model with model_id.
    """
    updated_info = dict()
    if request.model_name is not None:
        updated_info["name"] = request.model_name
    if request.ml_config is not None:
        updated_info["config"] = request.ml_config
    _update_model(model_id, {"$set": updated_info})


@router.delete("/{model_id}")
def delete_model(model_id: str, token=Depends(validate_token)):
    model = models_collection.find_one({"_id": ObjectId(model_id)})
    if model is None:
        raise model_not_found_exception(model_id)

    # Delete versions and their predictions
    for version_id in model["versions"]:
        _delete_version(model_id, ObjectId(version_id))

    # Delete the model itself, including performances
    models_collection.delete_one({"_id": ObjectId(model_id)})


@router.post("/{model_id}/versions", response_model=VersionIdOut)
def create_model_version(
    model_id: str, file: UploadFile = Form(), token=Depends(validate_token)
):
    """
    Upload a new version for the given model-id.
    """
    version_id = fs.put(file.file, filename=file.filename)
    result = models_collection.update_one(
        {"_id": ObjectId(model_id)},
        {"$set": {f"versions.{version_id}": {"description": ""}}},
    )
    if result.matched_count == 0:
        fs.delete(version_id)
        raise model_not_found_exception(model_id)
    return VersionIdOut(version_id=str(version_id))


@router.get("/{model_id}/versions", response_model=VersionsOut)
def get_model_versions(model_id: str):
    """
    Get the model versions for the specified model.
    """
    model = _get_model(model_id, ["versions"])
    versions = []
    for version_id, version in model["versions"].items():
        versions.append(
            VersionOut(version_id=version_id, description=version["description"])
        )
    return VersionsOut(versions=versions)


@router.get("/{model_id}/versions/{version_id}")
def get_model_version(model_id: str, version_id: str):
    """
    Get the binary file for the given model version.
    """
    model = _get_model(model_id, ["versions"])
    for version_id_ in model["versions"]:
        if version_id == version_id_:
            mongo_file = fs.get(ObjectId(version_id_))
            return StreamingResponse(
                read_file_in_chunks(mongo_file), media_type="application/octet-stream"
            )
    raise version_not_found_exception(version_id, model_id)


@router.put("/{model_id}/versions/{version_id}")
def replace_model_version_file(
    model_id: str,
    version_id: str,
    file: UploadFile = Form(),
    token=Depends(validate_token),
):
    """
    Upload a new version for the given model-id.
    """
    fs.delete(ObjectId(version_id))
    fs.put(file.file, _id=ObjectId(version_id), filename=file.filename)


@router.delete("/{model_id}/versions/{version_id}")
def delete_model_version(model_id: str, version_id: str, token=Depends(validate_token)):
    result = models_collection.update_one(
        {"_id": ObjectId(model_id)}, {"$unset": {f"versions.{version_id}": ""}}
    )
    if result.matched_count == 0:
        raise model_not_found_exception(model_id)
    if result.modified_count == 0:
        raise version_not_found_exception(version_id, model_id)
    _delete_version(model_id, ObjectId(version_id))


@router.put("/{model_id}/versions/{version_id}/description")
def update_version_description(
    model_id: str,
    version_id: str,
    request: UpdateDescriptionIn,
    token=Depends(validate_token),
):
    result = models_collection.update_one(
        {"_id": ObjectId(model_id), f"versions.{version_id}": {"$exists": True}},
        {"$set": {f"versions.{version_id}": {"description": request.description}}},
    )
    if result.matched_count == 0:
        raise version_not_found_exception(version_id, model_id)


@router.post("/{model_id}/versions/{version_id}/predictions")
def post_predictions(
    model_id: str,
    version_id: str,
    file: UploadFile = Form(),
    token=Depends(validate_token),
):
    """
    Saves the predictions of the specified model version in the database. Predictions
    should have the following format:
    {
        "predictions": {
            "issue_id": {"existence": {"prediction": True, "confidence": 0.42}}
        }
    }
    """
    # Make sure the version of the model exists
    model = _get_model(model_id, ["versions"])
    if version_id not in model["versions"]:
        raise version_not_found_exception(version_id, model_id)
    # Convert file to json
    predictions = json.loads(file.file.read().decode("utf-8"))["predictions"]
    classes = set()
    for issue_id, predicted_classes in predictions.items():
        predictions = {}
        for predicted_class in predicted_classes:
            predictions[predicted_class] = {
                "prediction": predicted_classes[predicted_class]["prediction"],
                "confidence": predicted_classes[predicted_class]["confidence"],
            }
            classes.add(predicted_class)
        result = issue_labels_collection.update_one(
            {"_id": issue_id},
            {"$set": {f"predictions.{model_id}-{version_id}": predictions}},
        )
        if result.matched_count != 1:
            raise issue_not_found_exception(issue_id)
    for class_ in classes:
        # Make sure the predictions are indexed for speed
        issue_labels_collection.create_index(
            f"predictions.{model_id}-{version_id}.{class_}.confidence"
        )


@router.get("/{model_id}/versions/{version_id}/predictions")
def get_predictions(model_id: str, version_id: str, request: GetPredictionsIn):
    """
    Returns the predicted labels of the specified model version. Set issue_ids to null
    to get all predictions. It returns the predictions as a byte stream.
    """
    if request.issue_ids is None:
        filter_ = {f"predictions.{model_id}-{version_id}": {"$exists": True}}
    else:
        filter_ = {
            "$and": [
                {"_id": {"$in": request.issue_ids}},
                {f"predictions.{model_id}-{version_id}": {"$exists": True}},
            ]
        }
    issues = issue_labels_collection.find(
        filter_, [f"predictions.{model_id}-{version_id}"]
    )
    predictions = dict()
    if request.issue_ids is not None:
        remaining_ids = set(request.issue_ids)
    for issue in issues:
        issue_id = issue.pop("_id")
        predictions[issue_id] = issue["predictions"][f"{model_id}-{version_id}"]
        if request.issue_ids is not None:
            remaining_ids.remove(issue_id)
    if request.issue_ids is not None:
        for issue_id in remaining_ids:
            predictions[issue_id] = None
    file = io.BytesIO(bytes(json.dumps({"predictions": predictions}), "utf-8"))
    return StreamingResponse(
        read_file_in_chunks(file), media_type="application/octet-stream"
    )


@router.delete("/{model_id}/versions/{version_id}/predictions")
def delete_predictions(model_id: str, version_id: str, token=Depends(validate_token)):
    model = _get_model(model_id, ["versions"])
    if version_id not in model["versions"]:
        raise version_not_found_exception(version_id, model_id)
    _delete_version(model_id, ObjectId(version_id))


@router.post("/{model_id}/performances", response_model=PostPerformanceOut)
def post_performance(
    model_id: str, file: UploadFile = Form(), token=Depends(validate_token)
):
    """
    Add a performance result for the given model. The performances should be uploaded
    as a bytes file.
    """
    file_id = fs.put(file.file, filename=file.filename)
    result = models_collection.update_one(
        {"_id": ObjectId(model_id)},
        {"$set": {f"performances.{file_id}": {"description": ""}}},
    )
    if result.matched_count == 0:
        raise model_not_found_exception(model_id)
    return PostPerformanceOut(performance_id=str(file_id))


@router.get("/{model_id}/performances", response_model=PerformancesOut)
def get_performances(model_id: str):
    """
    Get a list of all performance results for the given model.
    """
    model = _get_model(model_id, ["performances"])
    performances = []
    for performance_id, performance in model["performances"].items():
        performances.append(
            PerformanceDescriptionOut(
                performance_id=performance_id, description=performance["description"]
            )
        )
    return PerformancesOut(performances=performances)


@router.get("/{model_id}/performances/{performance_id}", response_model=PerformanceOut)
def get_performance(model_id: str, performance_id: str):
    """
    Get the requested performance result. It returns the performance as a byte stream.
    """
    model = _get_model(model_id, ["performances"])
    try:
        ObjectId(performance_id)
    except bson.errors.BSONError as e:
        raise bson_exception(str(e))
    if performance_id not in model["performances"]:
        raise performance_not_found_exception(performance_id, model_id)
    file = fs.get(ObjectId(performance_id))
    payload = {
        "performance_id": performance_id,
        "description": model["performances"][performance_id]["description"],
        "performance": json.loads(file.read().decode("utf-8")),
    }
    file = io.BytesIO(bytes(json.dumps(payload), "utf-8"))
    return StreamingResponse(
        read_file_in_chunks(file), media_type="application/octet-stream"
    )


@router.delete("/{model_id}/performances/{performance_id}")
def delete_performance(
    model_id: str, performance_id: str, token=Depends(validate_token)
):
    try:
        result = models_collection.update_one(
            {"_id": ObjectId(model_id)},
            {"$unset": {f"performances.{performance_id}": ""}},
        )
    except bson.errors.BSONError as e:
        raise bson_exception(str(e))
    if result.matched_count == 0:
        raise model_not_found_exception(model_id)
    if result.modified_count == 0:
        raise performance_not_found_exception(performance_id, model_id)
    fs.delete(ObjectId(performance_id))


@router.put("/{model_id}/performances/{performance_id}/description")
def update_performance_description(
    model_id: str,
    performance_id: str,
    request: UpdateDescriptionIn,
    token=Depends(validate_token),
):
    result = models_collection.update_one(
        {
            "_id": ObjectId(model_id),
            f"performances.{performance_id}": {"$exists": True},
        },
        {
            "$set": {
                f"performances.{performance_id}": {"description": request.description}
            }
        },
    )
    if result.matched_count == 0:
        raise performance_not_found_exception(performance_id, model_id)
