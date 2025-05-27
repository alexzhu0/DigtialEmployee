from typing import Optional, Dict, Any
from letta.client import Letta, Agent # Assuming Agent type is available for type hinting
from letta.types import Message, MessageRole # Assuming these types for interaction
from config.config import settings
from config.logging_config import get_logger
import tempfile
import os
from pathlib import Path

logger = get_logger(__name__)

letta_client: Optional[Letta] = None
knowledge_agent_id: Optional[str] = settings.LETTA_KNOWLEDGE_AGENT_ID # Load from settings

def initialize_letta_client():
    """
    Initializes the global Letta client.
    """
    global letta_client
    if letta_client is not None:
        logger.info("Letta client already initialized.")
        return

    if not settings.LETTA_SERVER_URL:
        logger.error("LETTA_SERVER_URL is not configured. Cannot initialize Letta client.")
        return

    try:
        logger.info(f"Initializing Letta client with server URL: {settings.LETTA_SERVER_URL}")
        letta_client = Letta(
            server_url=settings.LETTA_SERVER_URL,
            token=settings.LETTA_SERVER_TOKEN,
        )
        # You might want to add a ping or a simple API call here to verify connection
        # For example: letta_client.agents.list(limit=1) 
        logger.info("Letta client initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Letta client: {e}", exc_info=True)
        letta_client = None

def get_letta_client() -> Optional[Letta]:
    """
    Returns the initialized Letta client, initializing it if necessary.
    """
    if letta_client is None:
        logger.info("Letta client not initialized. Attempting to initialize now.")
        initialize_letta_client()
    return letta_client

def find_or_create_agent(
    agent_name: str, 
    llm_model: str, 
    embedding_model: str, 
    human_notes: str = "Knowledge agent for Yuanfang.", 
    persona_notes: str = "I store and retrieve information from documents."
) -> Optional[str]:
    """
    Finds an agent by name or creates one if not found.
    Returns the agent ID or None if an error occurs.
    """
    global knowledge_agent_id
    client = get_letta_client()
    if not client:
        logger.error("Letta client not available. Cannot find or create agent.")
        return None

    if knowledge_agent_id: # If already loaded from settings and presumed valid
        logger.info(f"Using pre-configured LETTA_KNOWLEDGE_AGENT_ID: {knowledge_agent_id}")
        # Optionally, verify if this agent ID is still valid on the server
        try:
            agent = client.agents.get(knowledge_agent_id)
            if agent:
                logger.info(f"Agent with ID {knowledge_agent_id} found and is valid.")
                return knowledge_agent_id
            else: # Should not happen if get() raises exception for not found
                logger.warning(f"Pre-configured agent ID {knowledge_agent_id} not found on server. Attempting to find by name or create.")
                # Fall through to find_by_name_or_create logic
        except Exception as e: # Catch specific Letta client exceptions if known
            logger.warning(f"Error validating pre-configured agent ID {knowledge_agent_id}: {e}. Attempting to find by name or create.")
            # Fall through to find_by_name_or_create logic


    try:
        logger.info(f"Attempting to find agent by name: {agent_name}")
        agents = client.agents.list(name=agent_name, limit=1)
        if agents and len(agents.data) > 0:
            agent = agents.data[0]
            logger.info(f"Found existing agent: {agent.name} with ID: {agent.id}")
            knowledge_agent_id = agent.id
            # Persist this ID? For now, it's a global in this module and potentially updated in settings.
            # If settings.LETTA_KNOWLEDGE_AGENT_ID was None, this is where it would be "discovered"
            if settings.LETTA_KNOWLEDGE_AGENT_ID != agent.id :
                 logger.info(f"Updating runtime knowledge_agent_id to discovered ID: {agent.id}. Consider updating .env with LETTA_KNOWLEDGE_AGENT_ID={agent.id}")

            return agent.id
        else:
            logger.info(f"Agent '{agent_name}' not found. Creating a new one.")
            agent_config = {
                "name": agent_name,
                "llm_model_name": llm_model,
                "embedding_model_name": embedding_model,
                "human_notes": human_notes,
                "persona_notes": persona_notes,
                "plugins": [], # Add default plugins if necessary
                "sort_priority": 1, # Optional: set priority
            }
            # The Letta client example uses `agent = client.agents.create(**params)`.
            # Assuming `client.agents.create` takes these parameters directly.
            new_agent = client.agents.create(**agent_config) # type: ignore
            logger.info(f"Successfully created new agent: {new_agent.name} with ID: {new_agent.id}")
            knowledge_agent_id = new_agent.id
            # Persist this ID?
            logger.info(f"New agent created with ID: {new_agent.id}. Consider updating .env with LETTA_KNOWLEDGE_AGENT_ID={new_agent.id}")
            return new_agent.id
    except Exception as e:
        logger.error(f"Error finding or creating agent '{agent_name}': {e}", exc_info=True)
        return None

def upload_document_to_agent(
    agent_id: str, 
    file_name: str, 
    file_content: bytes
) -> bool:
    """
    Uploads a document (bytes) to the specified Letta agent.
    """
    client = get_letta_client()
    if not client:
        logger.error("Letta client not available. Cannot upload document.")
        return False

    try:
        logger.info(f"Uploading document '{file_name}' to agent_id: {agent_id}")
        
        # Create a temporary file to upload
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name
        
        logger.debug(f"Temporary file created at: {tmp_file_path}")

        # 1. Upload file to create a file source
        # The example uses `client.sources.files.upload(agent_id=agent_id, file=Path(tmp_file_path))`
        # However, the API might expect client.sources.upload_file or similar.
        # Let's assume client.sources.files.upload is correct as per example.
        # The example also shows: `source = client.sources.files.upload(agent_id=agent.id, file=file_path)`
        # And then `client.agents.add_source(agent_id=agent.id, source_id=source.id, auto_segment_enabled=True)`
        
        file_source = client.sources.files.upload(agent_id=agent_id, file=Path(tmp_file_path))
        logger.info(f"File '{file_name}' (temp: {tmp_file_path}) uploaded to sources, source_id: {file_source.id}")
        
        # 2. Add the file source to the agent
        client.agents.add_source(agent_id=agent_id, source_id=file_source.id, auto_segment_enabled=True)
        logger.info(f"Source {file_source.id} added to agent {agent_id} with auto-segmentation.")
        
        return True
    except Exception as e:
        logger.error(f"Error uploading document '{file_name}' to agent_id {agent_id}: {e}", exc_info=True)
        return False
    finally:
        if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
            try:
                os.remove(tmp_file_path)
                logger.debug(f"Temporary file {tmp_file_path} removed.")
            except Exception as e_rm:
                logger.error(f"Error removing temporary file {tmp_file_path}: {e_rm}", exc_info=True)


def query_letta_agent(agent_id: str, query: str, stream: bool = False) -> Optional[str]:
    """
    Sends a query to the specified Letta agent and returns the response.
    """
    client = get_letta_client()
    if not client:
        logger.error("Letta client not available. Cannot query agent.")
        return None

    try:
        logger.info(f"Querying agent_id: {agent_id} with query: '{query}' (stream={stream})")
        
        # Example uses: response = client.send_message(agent_id=agent.id, content=query, stream=False)
        # Assuming this is the correct method for querying.
        # The response structure might be like: {"assistant_message": {"content": "..."}}
        
        # Let's construct the message list as per typical Letta API usage
        messages = [Message(role=MessageRole.USER, content=query)]
        
        response_data = client.send_message(
            agent_id=agent_id,
            messages=messages,
            stream=stream
        )
        
        if stream:
            # Handle streaming response if necessary in the future
            # For now, let's assume we can collect it or it's an error for Phase 1
            logger.warning("Streaming response handling not fully implemented for query_letta_agent. Will attempt to read as non-streamed or may fail.")
            # This part would need to iterate through the stream and accumulate content.
            # For simplicity, if stream=True is passed and the client returns an iterator,
            # this will likely not work as expected without further implementation.
            # However, the `send_message` might internally handle stream=False correctly.
            # The example `client.send_message(..., stream=False)` implies it returns a complete response.
            # If it returns a generator even for stream=False, this needs adjustment.
            # Let's assume for stream=False, it's not a generator.
            full_response_content = ""
            if hasattr(response_data, '__iter__') and not isinstance(response_data, (dict, list)): # Basic check for stream
                 for chunk in response_data:
                     # Assuming chunk has a content attribute or similar structure
                     # This is a placeholder for actual stream handling logic
                     if hasattr(chunk, 'choices') and chunk.choices:
                         if hasattr(chunk.choices[0], 'delta') and chunk.choices[0].delta:
                             if hasattr(chunk.choices[0].delta, 'content'):
                                full_response_content += chunk.choices[0].delta.content or ""
                     elif hasattr(chunk, 'assistant_message') and chunk.assistant_message:
                         full_response_content += chunk.assistant_message.content or ""
                         break # Assuming last message in stream is the full one for assistant
            else: # Non-streamed or already aggregated response
                if hasattr(response_data, 'assistant_message') and response_data.assistant_message:
                    full_response_content = response_data.assistant_message.content
                else:
                    logger.warning(f"Unexpected response structure from Letta agent: {response_data}")
                    return None
            
            logger.info(f"Received response from agent_id {agent_id} (streamed and aggregated): '{full_response_content[:100]}...'")
            return full_response_content

        else: # Non-streaming
            # Assuming response_data has an 'assistant_message' attribute with 'content'
            if hasattr(response_data, 'assistant_message') and response_data.assistant_message:
                assistant_response = response_data.assistant_message.content
                logger.info(f"Received response from agent_id {agent_id}: '{assistant_response[:100]}...'")
                return assistant_response
            else:
                logger.warning(f"Unexpected response structure from Letta agent for non-streaming: {response_data}")
                return None

    except Exception as e:
        logger.error(f"Error querying Letta agent_id {agent_id}: {e}", exc_info=True)
        return None

# Example of how this service might be used (for testing or demonstration)
if __name__ == '__main__':
    logger.info("Running Letta service direct execution example...")
    
    # Initialize client (normally done at app startup)
    initialize_letta_client()
    
    # Ensure client is initialized
    test_client = get_letta_client()
    if not test_client:
        logger.error("Failed to get Letta client for example execution. Exiting.")
        exit(1)

    # Find or create agent
    agent_id = find_or_create_agent(
        agent_name=settings.LETTA_KNOWLEDGE_AGENT_NAME,
        llm_model=settings.LETTA_KNOWLEDGE_LLM_MODEL,
        embedding_model=settings.LETTA_KNOWLEDGE_EMBEDDING_MODEL
    )
    
    if agent_id:
        logger.info(f"Using Letta Agent ID: {agent_id}")
        
        # Example: Upload a dummy document
        dummy_file_name = "test_document.txt"
        dummy_file_content = b"This is a test document for Yuanfang's knowledge base, powered by Letta."
        
        upload_success = upload_document_to_agent(
            agent_id=agent_id,
            file_name=dummy_file_name,
            file_content=dummy_file_content
        )
        
        if upload_success:
            logger.info(f"Dummy document '{dummy_file_name}' uploaded successfully.")
            
            # Example: Query the agent (allow some time for processing if needed)
            import time
            logger.info("Waiting a few seconds for Letta to process the document...")
            time.sleep(5) # Give Letta a moment to process
            
            query = "What is this document about?"
            response = query_letta_agent(agent_id=agent_id, query=query)
            
            if response:
                logger.info(f"Query: '{query}'")
                logger.info(f"Response: '{response}'")
            else:
                logger.error("Failed to get a response from Letta agent.")
        else:
            logger.error(f"Failed to upload dummy document '{dummy_file_name}'.")
    else:
        logger.error("Failed to find or create Letta knowledge agent.")

    logger.info("Letta service direct execution example finished.")
