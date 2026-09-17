"""WebSocket streaming for real-time prediction updates."""

import asyncio
import json
from datetime import datetime
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.prediction_buffer: list[dict] = []
        self.max_buffer_size = 100

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected client."""
        self.active_connections.remove(websocket)
        print(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_prediction(self, prediction: dict):
        """Broadcast a new prediction to all clients."""
        message = {
            "type": "prediction",
            "timestamp": datetime.utcnow().isoformat(),
            "data": prediction,
        }
        self.prediction_buffer.append(message)
        if len(self.prediction_buffer) > self.max_buffer_size:
            self.prediction_buffer = self.prediction_buffer[-self.max_buffer_size:]

        await self.broadcast(message)

    async def broadcast_status(self, status: dict):
        """Broadcast a status update."""
        message = {
            "type": "status",
            "timestamp": datetime.utcnow().isoformat(),
            "data": status,
        }
        await self.broadcast(message)

    async def broadcast_drift_alert(self, drift_report: dict):
        """Broadcast a drift detection alert."""
        message = {
            "type": "drift_alert",
            "timestamp": datetime.utcnow().isoformat(),
            "data": drift_report,
        }
        await self.broadcast(message)

    def get_recent_predictions(self, n: int = 50) -> list[dict]:
        """Get recent predictions from buffer."""
        return self.prediction_buffer[-n:]


class PredictionStreamer:
    """Stream predictions from scheduled ingestion."""

    def __init__(self, connection_manager: ConnectionManager):
        self.manager = connection_manager
        self._running = False

    async def start_streaming(self, scheduler, predictor, interval_seconds: int = 3600):
        """Start streaming predictions from scheduled checks."""
        self._running = True

        while self._running:
            try:
                # Check for new data
                if scheduler.should_check():
                    df = scheduler.run_check()
                    if df is not None:
                        # Make predictions
                        from ..models.impact_predictor import prepare_features
                        df = prepare_features(df)

                        # Predict for each closure
                        for _, row in df.iterrows():
                            prediction = {
                                "road": row.get("Road", "Unknown"),
                                "type": row.get("Type", "Unknown"),
                                "latitude": float(row.get("Latitude", 0)),
                                "longitude": float(row.get("Longitude", 0)),
                                "impact": "Unknown",
                                "confidence": 0.0,
                            }
                            await self.manager.broadcast_prediction(prediction)

                        await self.manager.broadcast_status({
                            "event": "data_update",
                            "restrictions": len(df),
                            "timestamp": datetime.utcnow().isoformat(),
                        })

            except Exception as e:
                print(f"Streaming error: {e}")
                await self.manager.broadcast_status({
                    "event": "error",
                    "message": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                })

            await asyncio.sleep(interval_seconds)

    def stop(self):
        """Stop streaming."""
        self._running = False
