import asyncio

from app.dependencies import issue_labels_collection
from app.streaming.connection_manager import ConnectionManager
from app.streaming.queue_manager import QueueManager
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets import ConnectionClosedOK

router = APIRouter()


class UiUpdatesHandler:
    def __init__(self):
        self.__manager = ConnectionManager()
        self.__buffer = QueueManager()

    async def handle_update(self, update):
        await self.__buffer.enqueue(update)

    async def handle_connection(self, websocket: WebSocket):
        await self.__manager.connect(websocket)
        uid = self.__buffer.new_queue()
        try:
            while True:
                data = await self.__buffer.dequeue(uid)
                await websocket.send_json(data)
        except (ConnectionClosedOK, WebSocketDisconnect):
            self.__manager.disconnect(websocket)
            await self.__buffer.unsubscribe(uid)


ui_updates_handler = UiUpdatesHandler()


def _send_ui_update(data):
    asyncio.run(ui_updates_handler.handle_update(data))


def send_ui_update_manual_label(issue_id):
    issue = issue_labels_collection.find_one(
        {"_id": issue_id}, ["existence", "property", "executive"]
    )
    updated_info = {
        "issue_id": issue_id,
        "manual_label": {
            "existence": issue["existence"],
            "property": issue["property"],
            "executive": issue["executive"],
        },
    }
    _send_ui_update(updated_info)


def send_ui_update_tags(issue_id):
    issue = issue_labels_collection.find_one({"_id": issue_id}, ["tags"])
    updated_info = {
        "issue_id": issue_id,
        "tags": issue["tags"],
    }
    _send_ui_update(updated_info)


def send_ui_update_comments(issue_id):
    issue = issue_labels_collection.find_one({"_id": issue_id}, ["comments"])
    updated_info = {
        "issue_id": issue_id,
        "comments": issue["comments"],
    }
    _send_ui_update(updated_info)


@router.websocket("/ws")
async def ui_updates_ws(websocket: WebSocket):
    await ui_updates_handler.handle_connection(websocket)
