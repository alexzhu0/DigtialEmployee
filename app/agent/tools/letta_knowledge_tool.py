from langchain.tools import BaseTool
from typing import Any
from app.services.letta_service import query_letta_agent
from config.logging_config import get_logger

logger = get_logger(__name__) # Logger for the module

class LettaKnowledgeTool(BaseTool):
    name: str = "letta_knowledge_search"
    description: str = (
        "Searches and retrieves information from documents managed by the Letta AI platform. "
        "Use for queries about specific documents or topics that might be found in uploaded files."
    )
    letta_knowledge_agent_id: str

    def __init__(self, letta_knowledge_agent_id: str, **kwargs: Any):
        super().__init__(**kwargs) # Pass kwargs to parent
        if not letta_knowledge_agent_id:
            logger.error("LettaKnowledgeTool initialized without a letta_knowledge_agent_id.")
            # Although we check in _run, it's good to be aware at init.
            # Depending on strictness, could raise ValueError here.
        self.letta_knowledge_agent_id = letta_knowledge_agent_id
        self.logger = get_logger(__name__ + "." + self.__class__.__name__) # Specific logger for the class instance
        self.logger.info(f"LettaKnowledgeTool initialized with agent_id: {self.letta_knowledge_agent_id}")

    def _run(self, query: str) -> str:
        self.logger.info(f"LettaKnowledgeTool received query: '{query}' for agent_id: {self.letta_knowledge_agent_id}")
        if not self.letta_knowledge_agent_id:
            self.logger.error("LettaKnowledgeTool cannot run: letta_knowledge_agent_id is not configured.")
            return "Letta knowledge agent not configured. Cannot process query."

        try:
            response = query_letta_agent(agent_id=self.letta_knowledge_agent_id, query=query)
            if response is not None:
                self.logger.info(f"Response from Letta agent_id {self.letta_knowledge_agent_id} for query '{query}': '{response[:100]}...'")
                return response
            else:
                self.logger.warning(f"Received no response or an error from Letta agent_id {self.letta_knowledge_agent_id} for query: '{query}'")
                return "No response received from the Letta knowledge agent."
        except Exception as e: # Catching a generic exception, specific APIError would be better if known
            self.logger.error(f"Error querying Letta agent_id {self.letta_knowledge_agent_id} with query '{query}': {e}", exc_info=True)
            return f"An error occurred while querying the Letta knowledge agent: {str(e)}"

    async def _arun(self, query: str) -> str:
        self.logger.warning("Async execution not fully implemented for LettaKnowledgeTool, running sync version.")
        # In a real async implementation, query_letta_agent would need to be async
        # and awaited here.
        return self._run(query)
