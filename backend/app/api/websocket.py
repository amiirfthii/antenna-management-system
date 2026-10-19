#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List, Dict
from fastapi import WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
import json
import asyncio

from app.db.database import get_db


class ConnectionManager:
    """Manages WebSocket connections and broadcasts"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str = None):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)

        if user_id:
            self.user_connections[user_id] = websocket

        print(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, user_id: str = None):
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        if user_id and user_id in self.user_connections:
            del self.user_connections[user_id]

        print(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific client"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"Error sending personal message: {e}")

    async def broadcast(self, message: dict, exclude: WebSocket = None):
        """Broadcast message to all connected clients"""
        disconnected = []

        for connection in self.active_connections:
            if connection != exclude:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"Error broadcasting to client: {e}")
                    disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_to_users(self, message: dict, user_ids: List[str]):
        """Broadcast message to specific users"""
        for user_id in user_ids:
            if user_id in self.user_connections:
                try:
                    await self.user_connections[user_id].send_json(message)
                except Exception as e:
                    print(f"Error sending to user {user_id}: {e}")


# Global connection manager
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    user_id = None

    try:
        await manager.connect(websocket)

        # Send welcome message
        await manager.send_personal_message({
            "type": "connection",
            "status": "connected",
            "message": "Successfully connected to WebSocket"
        }, websocket)

        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types
            if message.get("type") == "auth":
                # Authenticate user
                user_id = message.get("user_id")
                if user_id:
                    manager.user_connections[user_id] = websocket
                    await manager.send_personal_message({
                        "type": "auth",
                        "status": "authenticated",
                        "user_id": user_id
                    }, websocket)

            elif message.get("type") == "ping":
                # Heartbeat response
                await manager.send_personal_message({
                    "type": "pong"
                }, websocket)

            else:
                # Echo or handle other message types
                await manager.send_personal_message({
                    "type": "echo",
                    "data": message
                }, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        print(f"Client {user_id} disconnected normally")

    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket, user_id)


# Helper functions for broadcasting updates

async def broadcast_repair_update(repair_data: dict, action: str = "update"):
    """Broadcast repair update to all clients"""
    await manager.broadcast({
        "type": "repair_update",
        "action": action,  # create, update, delete
        "data": repair_data
    })


async def broadcast_inventory_update(inventory_data: dict, action: str = "update"):
    """Broadcast inventory update to all clients"""
    await manager.broadcast({
        "type": "inventory_update",
        "action": action,  # create, update, delete, withdraw
        "data": inventory_data
    })


async def broadcast_user_update(user_data: dict, action: str = "update"):
    """Broadcast user update to all clients"""
    await manager.broadcast({
        "type": "user_update",
        "action": action,  # create, update, delete
        "data": user_data
    })


async def notify_user(user_id: str, notification: dict):
    """Send notification to specific user"""
    if user_id in manager.user_connections:
        await manager.send_personal_message({
            "type": "notification",
            "data": notification
        }, manager.user_connections[user_id])
