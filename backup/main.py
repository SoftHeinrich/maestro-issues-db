from __future__ import print_function

import os.path
import json
import subprocess
import schedule
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


def get_drive_service():
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def upload_file():
    service = get_drive_service()
    with open("file_metadata.json") as file:
        file_metadata = json.load(file)
    media = MediaFileUpload(file_metadata["name"], resumable=True)
    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )
    print("file created:", file.get("id"))


def make_backup():
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "mongo",
            "mongodump",
            "--db=MiningDesignDecisions",
            "--gzip",
            "--archive=mongodump-MiningDesignDecisions.archive",
        ]
    )
    subprocess.run(
        [
            "docker",
            "cp",
            "mongo:mongodump-MiningDesignDecisions.archive",
            "./mongodump-MiningDesignDecisions.archive",
        ]
    )
    upload_file()


def main():
    schedule.every().day.at("04:00").do(make_backup)
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
