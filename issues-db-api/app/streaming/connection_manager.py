from typing import List

from fastapi import WebSocket


class ConnectionManager:
    # Enable singleton pattern
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        print("Broadcasting to", len(self.active_connections), "peers")
        print("message:", message)
        for connection in self.active_connections:
            await connection.send_text(message)
