from dataclasses import dataclass
from typing import Any, Dict, Protocol

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from eloo.server.config import config
from eloo.server.logger import eloo_logger as logger


@dataclass
class WebSocketMessage:
    """Represents a WebSocket message structure."""

    action: str
    data: Dict[str, Any]


class MessageHandler(Protocol):
    """Protocol for message handling."""

    async def handle_message(
        self, action: str, data: Dict[str, Any]
    ) -> Dict[str, Any]: ...


class WebSocketServer:
    """Handles WebSocket communication."""

    def __init__(self, message_handler: MessageHandler):
        self._handler = message_handler
        self._app = FastAPI()
        self._connections: Dict[str, WebSocket] = {}
        self._setup()

    def _setup(self):
        """Initialize server configuration."""
        self._setup_cors()
        self._setup_routes()

    def _setup_cors(self):
        """Configure CORS middleware."""
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_credentials=True,
            allow_methods=['*'],
            allow_headers=['*'],
        )

    def _setup_routes(self):
        """Configure WebSocket routes."""

        @self._app.websocket('/ws/{client_id}')
        async def websocket_endpoint(websocket: WebSocket, client_id: str):
            await self._handle_connection(websocket, client_id)

    async def _handle_connection(self, websocket: WebSocket, client_id: str):
        """Handle WebSocket connection lifecycle."""
        try:
            await websocket.accept()
            self._connections[client_id] = websocket
            await self._handle_messages(client_id, websocket)
        except Exception as e:
            logger.error(f'Connection error: {str(e)}')
        finally:
            await self._disconnect(client_id)

    async def _handle_messages(self, client_id: str, websocket: WebSocket):
        """Handle incoming messages for a connection."""
        try:
            while True:
                data = await websocket.receive_json()
                logger.debug(f'Received message: {data}')
                message = WebSocketMessage(**data)
                response = await self._handler.handle_message(
                    message.action, message.data
                )
                logger.debug(f'Sending response: {response}')
                await self._send_response(
                    client_id, message.action + '_response', response
                )
        except WebSocketDisconnect:
            logger.info(f'Client {client_id} disconnected')
        except Exception as e:
            logger.error(f'Error handling message: {str(e)}')
            await self._send_error(client_id, str(e))

    async def _disconnect(self, client_id: str):
        """Clean up client connection."""
        if client_id in self._connections:
            del self._connections[client_id]

    def _extract_response(self, state):
        """Extract formatted response from CodeAgent state."""
        return {
            'messages': [
                {'source': event.source.value, 'content': event.content}
                for event in state.history
                if hasattr(event, 'content')
            ]
        }

    async def _send_response(self, client_id: str, action: str, data: Dict[str, Any]):
        """Send success response to client."""
        if client_id in self._connections:
            await self._connections[client_id].send_json(
                {'action': action, 'data': data}
            )

    async def _send_error(self, client_id: str, message: str):
        """Send error response to client."""
        await self._send_response(client_id, 'error', {'message': message})

    def run(self, host: str = '0.0.0.0', port: int = 8000):
        """Start the FastAPI server."""
        uvicorn.run(self._app, host=host, port=port)
