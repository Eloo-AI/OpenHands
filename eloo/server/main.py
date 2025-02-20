import asyncio
import logging

from eloo.code_agent import CodeAgent
from eloo.server.websocket import ClientMessageHandler, WebSocketServer

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ApplicationServer:
    """Main application server coordinator."""

    def __init__(self):
        self._code_agent: CodeAgent = None
        self._websocket: WebSocketServer = None

    async def initialize(self):
        """Initialize server components."""
        logger.debug('Initializing Application Server...')

        self._code_agent = CodeAgent()

        handler = ClientMessageHandler(
            self._code_agent.run_prompt, self._code_agent.send_session_state
        )
        self._websocket = WebSocketServer(handler)
        await self._websocket.initialize(self.cleanup)
        logger.info('WebSocket Server initialized successfully')

        await self._code_agent.initialize(self._websocket.code_agent_listener())

        logger.info('Application Server initialized successfully')

    async def cleanup(self):
        """Cleanup resources before shutdown"""
        logger.info('Cleaning up resources...')
        if self._code_agent:
            await self._code_agent.close()
        logger.info('Cleanup complete')


async def main():
    """Application entry point."""
    server = ApplicationServer()
    await server.initialize()


if __name__ == '__main__':
    asyncio.run(main())
