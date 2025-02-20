import asyncio
import logging
import signal
from dataclasses import dataclass
from typing import Any, Callable, Dict

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from eloo.server.code_agent import CodeAgentListenerIFC
from eloo.server.config import config

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@dataclass
class WebSocketMessage:
    """Represents a WebSocket message structure."""

    action: str
    data: Dict[str, Any]


class ClientMessageHandler:
    """Handles messages by delegating to OpenHands."""

    def __init__(
        self, run_prompt: Callable[[str], str], send_session_state: Callable[[str], str]
    ):
        self.run_prompt = run_prompt
        self.send_session_state = send_session_state

    async def handle_message(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages from WebSocket."""
        logger.debug(f'Handling message: action={action}, data={data}')
        try:
            if action == 'prompt':
                await self.run_prompt(data.get('prompt', ''))
            elif action == 'get_session_state':
                await self.send_session_state()
            else:
                raise ValueError(f'Unknown action: {action}')
        except Exception as e:
            logger.error(f'Error handling message: {str(e)}')
            raise


class CodeAgentListener(CodeAgentListenerIFC):
    def __init__(self, send_message: Callable[[str, Dict[str, Any]], None]):
        self._send_message = send_message

    async def on_message(self, message: str):
        logger.info(f'on_message: {message}')
        await self._send_message('message', {'source': 'agent', 'content': message})

    async def on_preview_url_update(self, preview_url: str):
        await self._send_message('preview_url_update', {'preview_url': preview_url})

    async def on_agent_state_update(self, agent_state: str):
        await self._send_message('agent_state_update', {'agent_state': agent_state})

    async def on_error(self, error: str):
        await self._send_message('error', {'message': error})

    async def on_action_performed(self, action: str):
        await self._send_message('action_performed', {'action': action})

    async def on_observation_performed(self, observation: str):
        await self._send_message('observation_performed', {'observation': observation})


class WebSocketServer:
    """Handles WebSocket communication."""

    def __init__(self, message_handler: ClientMessageHandler):
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
                await self._handler.handle_message(message.action, message.data)
        except WebSocketDisconnect:
            logger.info(f'Client {client_id} disconnected')
        except Exception as e:
            logger.error(f'Error handling message: {str(e)}')
            await self._send_error(client_id, str(e))

    async def send_message(self, type: str, data: Dict[str, Any]):
        """Send a message to all clients."""
        logger.info(f'send_message: {type} {data}')
        for client_id in self._connections:
            logger.info(f'sending to {client_id}')
            await self._send_response(client_id, type, data)

    async def send_client_message(self, client_id: str, data: Dict[str, Any]):
        """Send a message to the client."""
        await self._send_response(client_id, 'message', data['data'])

    async def send_status_update(self, client_id: str, data: Dict[str, Any]):
        """Send a status update to the client."""
        await self._send_response(client_id, 'status_update', data['data'])

    async def initialize(self, cleanup_callback: Callable[[], None]):
        """Initialize the server without blocking."""
        self._cleanup_callback = cleanup_callback
        logger.info(f'Starting server on {config.host}:{config.port}')

        # Configure uvicorn
        uvicorn_config = uvicorn.Config(
            self._app, host=config.host, port=config.port, loop='asyncio'
        )
        self._server = uvicorn.Server(uvicorn_config)

        # Handle graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.cleanup()))

        # Start server in background task
        self._serve_task = asyncio.create_task(self._server.serve())

        # Wait a moment for server to start
        await asyncio.sleep(0.5)

    async def _disconnect(self, client_id: str):
        """Clean up client connection."""
        if client_id in self._connections:
            del self._connections[client_id]

    async def _send_response(self, client_id: str, action: str, data: Dict[str, Any]):
        """Send success response to client."""
        if client_id in self._connections:
            await self._connections[client_id].send_json(
                {'action': action, 'data': data}
            )

    async def _send_error(self, client_id: str, message: str):
        """Send error response to client."""
        await self._send_response(client_id, 'error', {'message': message})

    async def run(self, host: str = '0.0.0.0', port: int = 8000):
        """Start the FastAPI server."""
        config = uvicorn.Config(self._app, host=host, port=port)
        server = uvicorn.Server(config)
        await server.serve()

    def code_agent_listener(self):
        return CodeAgentListener(self.send_message)
