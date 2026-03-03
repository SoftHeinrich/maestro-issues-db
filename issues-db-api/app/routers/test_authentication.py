from app.dependencies import users_collection

from .test_util import client
from .test_util import setup_users_db, restore_dbs, get_auth_header, auth_test_post


def test_authentication():
    restore_dbs()
    setup_users_db()

    # Get token
    response = client.post(
        "/token", files={"username": (None, "test2"), "password": (None, "test2")}
    )
    assert response.status_code == 401
    response = client.post(
        "/token", files={"username": (None, "test"), "password": (None, "test2")}
    )
    assert response.status_code == 401
    response = client.post(
        "/token", files={"username": (None, "test"), "password": (None, "test")}
    )
    assert response.status_code == 200

    # Create account
    auth_test_post("/create-account")
    headers = get_auth_header()
    payload = {"username": "test2", "password": "test2"}
    assert (
        client.post("/create-account", headers=headers, json=payload).status_code == 200
    )
    assert users_collection.find_one({"_id": "test2"}) is not None
    assert (
        client.post("/create-account", headers=headers, json=payload).status_code == 409
    )

    # Get token for new account
    response = client.post(
        "/token", files={"username": (None, "test2"), "password": (None, "test2")}
    )
    assert response.status_code == 200

    restore_dbs()


def test_refresh_token():
    restore_dbs()
    setup_users_db()

    headers = get_auth_header()
    token = client.post("/refresh-token", headers=headers).json()["access_token"]
    # Random token
    headers = {"Authorization": f"bearer random-token-here"}
    assert client.post("/refresh-token", headers=headers).status_code == 401
    # Refreshed token
    headers = {"Authorization": f"bearer {token}"}
    assert client.post("/refresh-token", headers=headers).status_code == 200

    restore_dbs()


def test_change_password():
    restore_dbs()
    setup_users_db()

    auth_test_post("/change-password")
    headers = get_auth_header()

    # Change password
    payload = {"password": "new-pw"}
    assert (
        client.post("/change-password", headers=headers, json=payload).status_code
        == 200
    )

    # Verify the new password works
    assert (
        client.post(
            "/token",
            files={"username": (None, "test"), "password": (None, "new-pw")},
        ).status_code
        == 200
    )

    # Verify the old password does not work anymore
    assert (
        client.post(
            "/token",
            files={"username": (None, "test"), "password": (None, "test")},
        ).status_code
        == 401
    )

    restore_dbs()
