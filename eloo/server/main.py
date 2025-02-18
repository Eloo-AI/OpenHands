import asyncio
import logging
from typing import Dict, Any
from eloo.server.config import config
from eloo.code_agent import CodeAgent
from eloo.server.websocket import WebSocketServer, MessageHandler
from eloo.server.logger import logger

class OpenHandsMessageHandler(MessageHandler):
    """Handles messages by delegating to OpenHands."""
    
    def __init__(self, code_agent: CodeAgent):
        self.code_agent = code_agent

    async def handle_message(self, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages from WebSocket."""
        if action == "code":
            state = await self.code_agent.run_prompt(data.get("prompt", ""))
            return self._extract_response(state)
        elif action in ["git_fetch", "git_push"]:
            # TODO: Implement git operations
            raise NotImplementedError(f"{action} not implemented")
        else:
            raise ValueError(f"Unknown action: {action}")

    def _extract_response(self, state):
        """Extract formatted response from OpenHands state."""
        return {
            "messages": [
                {
                    "source": event.source.value,
                    "content": event.content
                }
                for event in state.history
                if hasattr(event, "content")
            ]
        }

class ApplicationServer:
    """Main application server coordinator."""
    
    def __init__(self):
        self._code_agent: CodeAgent = None
        self._websocket: WebSocketServer = None

    async def initialize(self):
        """Initialize server components."""
        logger.debug("Initializing Application Server...")
        
        self._code_agent = CodeAgent()
        await self._code_agent.initialize()
        
        handler = OpenHandsMessageHandler(self._code_agent)
        self._websocket = WebSocketServer(handler)
        
        logger.info("Application Server initialized successfully")

    def run(self):
        """Start the server."""
        logger.info(f"Starting server on {config.host}:{config.port}")
        self._websocket.run(config.host, config.port)

def main():
    """Application entry point."""
    server = ApplicationServer()
    asyncio.run(server.initialize())
    server.run()

if __name__ == "__main__":
    main() 