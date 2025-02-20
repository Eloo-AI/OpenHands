import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Protocol

import aiohttp
from socketio import AsyncClient

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class CodeAgentListenerIFC(Protocol):
    async def on_message(self, message: str): ...
    async def on_agent_state_update(self, new_state: str): ...
    async def on_preview_url_update(self, preview_url: str): ...
    async def on_error(self, error: str): ...
    async def on_action_performed(self, action: str): ...
    async def on_observation_performed(self, observation: str): ...


class CodeAgent:
    def __init__(self, base_url=None):
        self.base_url = base_url or 'http://127.0.0.1:3000'

        self.ws_url = self.base_url.replace('http://', 'ws://').replace(
            'https://', 'wss://'
        )
        logger.debug(f'Using base_url={self.base_url}, ws_url={self.ws_url}')

        # Use AsyncClient instead of Client
        self.sio = AsyncClient(
            reconnection=True,
            reconnection_attempts=3,
            logger=False,
            engineio_logger=False,
        )
        self.conversation_id = None
        self.agent_state = None
        self.can_accept_input = False
        self.session = None

        # Session State
        self.status = None
        self.agent_state = None
        self.environment_state = None
        self.preview_url = None

        # Set up socket.io event handlers
        self.sio.on('connect', self.on_connect)
        self.sio.on('disconnect', self.on_disconnect)
        self.sio.on('oh_event', self.on_event)

    def initial_message(self):
        return 'start the web server with the corresponding ports, using `npm run dev`. provide the server url without any other explanations.'

    async def initialize(self, listener: CodeAgentListenerIFC):
        """Initialize the CodeAgent"""
        self.listener = listener

        await self.create_conversation(self.initial_message())

        await self.connect_websocket()
        await self.wait_for_input_ready()
        logger.info('Agent initialized and ready for input')

    async def create_conversation(self, initial_msg: Optional[str] = None) -> str:
        """Create a new conversation and return the conversation ID"""
        if initial_msg is None:
            initial_msg = 'Wait for next command'

        if self.session is None:
            self.session = aiohttp.ClientSession()

        response = await self.session.post(
            f'{self.base_url}/api/conversations',
            json={
                'selected_repository': None,
                'initial_user_msg': initial_msg,
                'image_urls': None,
            },
        )
        data = await response.json()

        if data['status'] == 'ok':
            self.conversation_id = data['conversation_id']
            logger.debug(f'***** API_CONVERSATION_CREATED: {self.conversation_id}')
            return self.conversation_id
        raise Exception(f'Failed to create conversation: {data}')

    async def connect_websocket(self):
        """Connect to the WebSocket server"""
        if not self.conversation_id:
            raise Exception('Must create conversation before connecting')

        logger.debug(
            f'***** WS_CONNECTING to: {self.ws_url} with conversation_id={self.conversation_id}'
        )

        connection_url = f'{self.ws_url}/socket.io/?conversation_id={self.conversation_id}&latest_event_id=-1'

        try:
            await self.sio.connect(
                connection_url, transports=['websocket'], wait_timeout=10
            )
        except Exception as e:
            logger.error(f'***** WS_ERROR: Connection failed: {str(e)}')
            logger.error(f'***** WS_ERROR: Connection URL: {connection_url}')
            raise

    async def on_connect(self):
        """Handle socket connection"""
        logger.info('***** WS_CONNECTED')
        if self.conversation_id:
            # Initialize the session
            await self.sio.emit(
                'init',
                {
                    'action': 'init',
                    'conversation_id': self.conversation_id,
                    'latest_event_id': -1,
                },
            )

    def on_disconnect(self):
        """Handle socket disconnection"""
        logger.info('***** WS_DISCONNECTED')

    async def send_session_state(self):
        """Send the session state to the server"""
        await self.listener.on_agent_state_update(self.agent_state)
        await self.listener.on_preview_url_update(self.preview_url)

    async def on_event(self, data: Dict[str, Any]):
        """Handle events from the server"""

        # Handle different types of messages
        if 'status_update' in data:
            self.status_type = data.get('type', 'info')
            message = data.get('message', '')
            logger.debug(f'[Status {self.status_type}] {message}')
            await self.send_session_state()

        elif 'source' in data:
            source = data['source']
            message = data.get('message', '')
            action = data.get('action', '')
            observation = data.get('observation', '')

            if source == 'agent':
                if action == 'message':
                    logger.info(f'MESSAGE DATA: {data}')
                    if message.startswith(('http://', 'https://')):
                        logger.info(f'$$$$$ preview server in {message}')
                        self.preview_url = message
                        await self.listener.on_preview_url_update(message)
                    else:
                        logger.info(f'Agent: {message}')
                        await self.listener.on_message(message)

                elif action in ['edit', 'read', 'run']:
                    pass
                    # logger.debug(f"\nAgent Action ({action}): {message}")
                elif observation == 'agent_state_changed':
                    state = data.get('extras', {}).get('agent_state', 'unknown')
                    self.agent_state = state
                    logger.debug(f'Agent State Changed to: {state}')
                    await self.send_session_state()
                    # Update input readiness based on state
                    if state == 'awaiting_user_input':
                        self.can_accept_input = True
                    else:
                        self.can_accept_input = False
                else:
                    pass
                    # logger.debug(f"Agent Other: {message}")

            elif source == 'environment':
                if observation == 'agent_state_changed':
                    state = data.get('extras', {}).get('agent_state', 'unknown')
                    self.agent_state = state
                    logger.debug(f'Agent State Changed to {state}')
                    await self.send_session_state()
                    # Also check environment state changes
                    if state == 'awaiting_user_input':
                        self.can_accept_input = True
                        logger.info('Ready for user input!')
                        await self.send_session_state()
                    else:
                        self.can_accept_input = False
                else:
                    pass
                    # logger.debug(f"\nEnvironment: {message}")

        # logger.debug("=" * 25)

    async def run_prompt(self, prompt: str):
        """Run a prompt through the CodeAgent"""
        if not prompt or prompt == '':
            logger.error('Prompt is required')
            return

        self.can_accept_input = False

        await self._send_message(
            {
                'action': 'message',
                'args': {
                    'content': prompt,
                    'image_urls': [],
                    'timestamp': datetime.now().isoformat(),
                },
            }
        )

    async def _send_message(self, message: Dict):
        """Send a message through the WebSocket"""
        if not self.conversation_id:
            raise Exception('Must create conversation before sending messages')

        await self.sio.emit('oh_action', message)

    async def close(self):
        """Close the WebSocket connection and HTTP session"""
        if self.sio.connected:
            await self.sio.disconnect()
        if self.session is not None:
            await self.session.close()

    async def wait_for_input_ready(self):
        """Wait until agent is ready for input"""
        while not self.can_accept_input:
            await asyncio.sleep(0.1)
