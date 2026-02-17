import io
import json

from app.dependencies import issue_labels_collection, models_collection, fs
from bson import ObjectId

from .models import get_predictions, GetPredictionsIn, GetPredictionsOut
from .test_util import client
from .test_util import (
    setup_users_db,
    restore_dbs,
    get_auth_header,
    auth_test_post,
    auth_test_delete,
    auth_test_put,
)


def setup_db():
    version_id = fs.put(io.BytesIO(bytes("mock data", "utf-8")), filename="filename")
    performance_id = fs.put(io.BytesIO(bytes(json.dumps([{"key": "value"}]), "utf-8")))
    model_id = ObjectId()
    models_collection.insert_one(
        {
            "_id": model_id,
            "name": "model_name",
            "config": {"key": "value"},
            "versions": {str(version_id): {"description": "version description"}},
            "performances": {
                str(performance_id): {"description": "performance description"}
            },
        }
    )

    issue_labels_collection.insert_one(
        {
            "_id": "Apache-01",
            "predictions": {
                f"{model_id}-{version_id}": {
                    "existence": {"confidence": 0.42, "prediction": False}
                }
            },
        }
    )
    issue_labels_collection.create_index(
        f"predictions.{model_id}-{version_id}.existence.confidence"
    )

    return model_id, version_id, performance_id


def test_get_all_models():
    restore_dbs()
    model_id, version_id, _ = setup_db()

    assert client.get("/models").json() == {
        "models": [{"model_id": str(model_id), "model_name": "model_name"}]
    }

    restore_dbs()


def test_create_model():
    restore_dbs()
    setup_users_db()

    auth_test_post("/models")
    headers = get_auth_header()

    # Create model with no name
    payload = {"model_name": None, "model_config": {"key": "value"}}
    model_id = client.post("/models", headers=headers, json=payload).json()["model_id"]
    assert models_collection.find_one({"_id": ObjectId(model_id)}) == {
        "_id": ObjectId(model_id),
        "name": "",
        "config": {"key": "value"},
        "versions": {},
        "performances": {},
    }

    # Create model with name
    payload = {"model_name": "model_name", "model_config": {"key": "value"}}
    model_id = client.post("/models", headers=headers, json=payload).json()["model_id"]
    assert models_collection.find_one({"_id": ObjectId(model_id)}) == {
        "_id": ObjectId(model_id),
        "name": "model_name",
        "config": {"key": "value"},
        "versions": {},
        "performances": {},
    }

    restore_dbs()


def test_get_model():
    restore_dbs()
    model_id, version_id, _ = setup_db()

    # Get model
    assert client.get(f"/models/{model_id}").json() == {
        "model_id": str(model_id),
        "model_name": "model_name",
        "model_config": {"key": "value"},
    }

    # Non-existing model
    assert client.get(f"/models/{ObjectId()}").status_code == 404

    restore_dbs()


def test_update_model():
    restore_dbs()
    setup_users_db()
    model_id, version_id, _ = setup_db()

    auth_test_post(f"/models/{model_id}")
    headers = get_auth_header()

    # Update model
    payload = {"model_name": "new-name", "model_config": {"new-key": "new-value"}}
    assert (
        client.post(f"/models/{model_id}", headers=headers, json=payload).status_code
        == 200
    )
    assert models_collection.find_one(
        {"_id": ObjectId(model_id)}, ["name", "config"]
    ) == {
        "_id": ObjectId(model_id),
        "name": "new-name",
        "config": {"new-key": "new-value"},
    }

    # Non-existing model
    assert (
        client.post(f"/models/{ObjectId()}", headers=headers, json=payload).status_code
        == 404
    )

    restore_dbs()


def test_delete_model():
    restore_dbs()
    setup_users_db()
    model_id, version_id, _ = setup_db()

    auth_test_delete(f"/models/{model_id}")
    headers = get_auth_header()

    # Delete model
    assert client.delete(f"/models/{model_id}", headers=headers).status_code == 200
    assert models_collection.find_one({"_id": model_id}) is None
    assert fs.exists(version_id) is False

    # Non-existing model
    assert client.delete(f"/models/{model_id}", headers=headers).status_code == 404

    restore_dbs()


def test_create_model_version():
    restore_dbs()
    setup_users_db()
    model_id, _, _ = setup_db()

    auth_test_post(f"/models/{model_id}/versions")
    headers = get_auth_header()

    # Create version
    files = {"file": ("filename", io.BytesIO(bytes("mock data", "utf-8")))}
    version_id = client.post(
        f"/models/{model_id}/versions", headers=headers, files=files
    ).json()["version_id"]
    assert models_collection.find_one({"_id": model_id})["versions"][version_id] == {
        "description": ""
    }
    assert fs.get(ObjectId(version_id)).read() == bytes("mock data", "utf-8")

    # Non-existing model
    assert (
        client.post(
            f"/models/{ObjectId()}/versions", headers=headers, files=files
        ).status_code
        == 404
    )

    restore_dbs()


def test_get_model_versions():
    restore_dbs()
    model_id, version_id, _ = setup_db()

    # Get version
    assert client.get(f"/models/{model_id}/versions").json() == {
        "versions": [
            {"version_id": str(version_id), "description": "version description"}
        ]
    }

    restore_dbs()


def test_get_model_version():
    restore_dbs()
    model_id, version_id, _ = setup_db()

    # Get version
    assert client.get(f"/models/{model_id}/versions/{version_id}").content == bytes(
        "mock data", "utf-8"
    )

    # Non-existing version
    assert client.get(f"/models/{model_id}/versions/{ObjectId()}").status_code == 404

    restore_dbs()


def test_delete_model_version():
    restore_dbs()
    setup_users_db()
    model_id, version_id, _ = setup_db()

    auth_test_delete(f"/models/{model_id}/versions/{version_id}")
    headers = get_auth_header()

    # Delete version
    assert (
        client.delete(
            f"/models/{model_id}/versions/{version_id}", headers=headers
        ).status_code
        == 200
    )
    assert models_collection.find_one({"_id": model_id})["versions"] == {}
    assert fs.exists(version_id) is False

    # Non-existing version
    assert (
        client.delete(
            f"/models/{model_id}/versions/{ObjectId()}", headers=headers
        ).status_code
        == 404
    )

    restore_dbs()


def test_update_version_description():
    restore_dbs()
    setup_users_db()
    model_id, version_id, _ = setup_db()

    auth_test_put(f"/models/{model_id}/versions/{version_id}/description")
    headers = get_auth_header()

    # update description
    payload = {"description": "new-description"}
    client.put(
        f"/models/{model_id}/versions/{version_id}/description",
        json=payload,
        headers=headers,
    )
    model = models_collection.find_one({"_id": model_id})
    assert model["versions"][str(version_id)]["description"] == "new-description"

    # model not found
    response = client.put(
        f"/models/{ObjectId()}/versions/{version_id}/description",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 404

    # version not found
    response = client.put(
        f"/models/{model_id}/versions/{ObjectId()}/description",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 404

    restore_dbs()


def test_post_predictions():
    restore_dbs()
    setup_users_db()
    model_id, version_id, _ = setup_db()

    auth_test_post(f"/models/{model_id}/versions/{version_id}/predictions")
    headers = get_auth_header()

    # Post predictions
    payload = {
        "predictions": {
            "Apache-01": {"property": {"confidence": 0.42, "prediction": False}}
        }
    }
    files = {"file": ("filename", io.BytesIO(bytes(json.dumps(payload), "utf-8")))}
    response = client.post(
        f"/models/{model_id}/versions/{version_id}/predictions",
        headers=headers,
        files=files,
    )
    assert response.status_code == 200
    assert issue_labels_collection.find_one({"_id": "Apache-01"})["predictions"] == {
        f"{model_id}-{version_id}": {
            "property": {"confidence": 0.42, "prediction": False}
        }
    }
    assert len(issue_labels_collection.index_information()) == 3

    # Non-existing version
    response = client.post(
        f"/models/{model_id}/versions/{ObjectId()}/predictions",
        headers=headers,
        files=files,
    )
    assert response.status_code == 404

    # Non-existing issue
    payload = {
        "predictions": {
            "Non-existing-id": {"property": {"confidence": 0.42, "prediction": False}}
        }
    }
    files = {"file": ("filename", io.BytesIO(bytes(json.dumps(payload), "utf-8")))}
    response = client.post(
        f"/models/{model_id}/versions/{version_id}/predictions",
        headers=headers,
        files=files,
    )
    assert response.status_code == 404

    restore_dbs()


def _read_streaming_response(response):
    """Read a StreamingResponse body and return parsed JSON."""
    import asyncio

    async def _read():
        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                body += chunk
            else:
                body += chunk.encode()
        return body

    body = asyncio.get_event_loop().run_until_complete(_read())
    return json.loads(body)


def test_get_predictions():
    restore_dbs()
    model_id, version_id, _ = setup_db()

    # Get predictions
    desired_result = {
        "predictions": {
            "Apache-01": {"existence": {"confidence": 0.42, "prediction": False}}
        }
    }
    result = _read_streaming_response(
        get_predictions(
            str(model_id), str(version_id), GetPredictionsIn(issue_ids=None)
        )
    )
    assert result == desired_result
    result = _read_streaming_response(
        get_predictions(
            str(model_id), str(version_id), GetPredictionsIn(issue_ids=["Apache-01"])
        )
    )
    assert result == desired_result
    result = _read_streaming_response(
        get_predictions(
            str(model_id), str(version_id), GetPredictionsIn(issue_ids=["Apache-02"])
        )
    )
    assert result == {"predictions": {"Apache-02": None}}

    restore_dbs()


def test_delete_predictions():
    restore_dbs()
    setup_users_db()
    model_id, version_id, _ = setup_db()

    auth_test_delete(f"/models/{model_id}/versions/{version_id}/predictions")
    headers = get_auth_header()

    # Delete version
    assert (
        client.delete(
            f"/models/{model_id}/versions/{version_id}/predictions", headers=headers
        ).status_code
        == 200
    )
    assert issue_labels_collection.find_one({"_id": "Apache-01"})["predictions"] == {}

    # Non-existing version
    assert (
        client.delete(
            f"/models/{model_id}/versions/{ObjectId()}/predictions", headers=headers
        ).status_code
        == 404
    )

    restore_dbs()


def test_post_performance():
    restore_dbs()
    setup_users_db()
    model_id, version_id, _ = setup_db()

    auth_test_post(f"/models/{model_id}/performances")
    headers = get_auth_header()

    # Post performance
    payload = [{"key": "value"}]
    files = {"file": ("filename", io.BytesIO(bytes(json.dumps(payload), "utf-8")))}
    performance_id = client.post(
        f"/models/{model_id}/performances", headers=headers, files=files
    ).json()["performance_id"]
    assert (
        performance_id in models_collection.find_one({"_id": model_id})["performances"]
    )
    file = fs.get(ObjectId(performance_id)).read()
    assert json.loads(file.decode("utf-8")) == [{"key": "value"}]

    # Non-existing model
    assert (
        client.post(
            f"/models/{ObjectId()}/performances", headers=headers, files=files
        ).status_code
        == 404
    )

    restore_dbs()


def test_get_performances():
    restore_dbs()
    model_id, version_id, performance_id = setup_db()

    # Get performance
    desired_result = {
        "performances": [
            {
                "performance_id": str(performance_id),
                "description": "performance description",
            }
        ]
    }
    assert client.get(f"/models/{model_id}/performances").json() == desired_result

    restore_dbs()


def test_get_performance():
    restore_dbs()
    model_id, version_id, performance_id = setup_db()

    # Get performance
    desired_result = {
        "performance_id": str(performance_id),
        "description": "performance description",
        "performance": [{"key": "value"}],
    }
    desired_result = bytes(json.dumps(desired_result), "utf-8")
    assert (
        client.get(f"/models/{model_id}/performances/{performance_id}").content
        == desired_result
    )

    # Performance not found
    assert (
        client.get(f"/models/{model_id}/performances/{ObjectId()}").status_code == 404
    )
    assert (
        client.get(f"/models/{model_id}/performances/non-existing").status_code == 422
    )

    restore_dbs()


def test_delete_performance():
    restore_dbs()
    setup_users_db()
    model_id, version_id, performance_id = setup_db()

    auth_test_delete(f"/models/{model_id}/performances/{performance_id}")
    headers = get_auth_header()

    # Delete version
    assert (
        client.delete(
            f"/models/{model_id}/performances/{performance_id}", headers=headers
        ).status_code
        == 200
    )
    assert models_collection.find_one({"_id": model_id})["performances"] == {}
    assert not fs.exists(performance_id)

    # Non-existing model
    assert (
        client.delete(
            f"/models/{ObjectId()}/performances/{performance_id}", headers=headers
        ).status_code
        == 404
    )

    # Non-existing performance
    assert (
        client.delete(
            f"/models/{model_id}/performances/non-existing", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/models/{model_id}/performances/{ObjectId()}", headers=headers
        ).status_code
        == 404
    )

    restore_dbs()


def test_update_performance_description():
    restore_dbs()
    setup_users_db()
    model_id, version_id, performance_id = setup_db()

    auth_test_put(f"/models/{model_id}/performances/{performance_id}/description")
    headers = get_auth_header()

    # update description
    payload = {"description": "new-description"}
    client.put(
        f"/models/{model_id}/performances/{performance_id}/description",
        json=payload,
        headers=headers,
    )
    assert (
        models_collection.find_one({"_id": model_id})["performances"][
            str(performance_id)
        ]["description"]
        == "new-description"
    )

    # model not found
    response = client.put(
        f"/models/{ObjectId()}/performances/{performance_id}/description",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 404

    # version not found
    response = client.put(
        f"/models/{model_id}/performances/{ObjectId()}/description",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 404

    restore_dbs()
