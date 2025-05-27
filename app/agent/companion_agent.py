from typing import List, Dict, Any
from langchain.agents import AgentExecutor
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.llms import DeepSeek
from app.agent.tools import (
    EmotionAnalysisTool,
    MemoryRecallTool,
    SafetyCheckTool,
    EmotionLogTool,
    TaskManagementTool,
    WorkStatusTool,
    ReportGenerationTool,
    ScheduleManagementTool,
    TeamManagementTool,
    KnowledgeBaseTool,
    TeamAnalyticsTool
)
from app.agent.tools.letta_knowledge_tool import LettaKnowledgeTool # Import the new tool
from app.agent.prompts import SYSTEM_PROMPT, EMOTION_ANALYSIS_PROMPT, MEMORY_RECALL_PROMPT, SAFETY_CHECK_PROMPT
from app.core.models import User, Conversation, Message
from sqlalchemy.orm import Session
from datetime import datetime
from config.config import settings
from config.logging_config import get_logger
# Attempt to import runtime_letta_knowledge_agent_id. This might be problematic due to circular dependencies
# or module load order. A better approach might be to pass it during CompanionAgent instantiation if needed at runtime,
# or have LettaKnowledgeTool fetch it from a shared, reliable source (e.g., settings if it's updated there).
# For this task, we'll try direct import as specified by the prompt.
from app.web.server import runtime_letta_knowledge_agent_id


logger = get_logger(__name__)

class CompanionAgent:
    def __init__(self, db: Session):
        logger.info("Initializing CompanionAgent...")
        self.db = db
        self.llm = DeepSeek(api_key=settings.DEEPSEEK_API_KEY)
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            max_token_limit=2000
        )
        
        # 初始化工具
        self.tools_list = [
            EmotionAnalysisTool(db),
            MemoryRecallTool(db),
            SafetyCheckTool(),
            EmotionLogTool(db),
            TaskManagementTool(db),
            WorkStatusTool(db),
            ReportGenerationTool(db),
            ScheduleManagementTool(db),
            TeamManagementTool(db),
            KnowledgeBaseTool(db), # This is the old DB-backed one, Letta tool is separate
            TeamAnalyticsTool(db)
        ]
        
        # Initialize and add LettaKnowledgeTool if agent ID is available
        logger.info("Attempting to initialize LettaKnowledgeTool...")
        if runtime_letta_knowledge_agent_id:
            try:
                letta_tool = LettaKnowledgeTool(letta_knowledge_agent_id=runtime_letta_knowledge_agent_id)
                self.tools_list.append(letta_tool)
                logger.info(f"LettaKnowledgeTool initialized and added to agent with agent_id: {runtime_letta_knowledge_agent_id}")
            except Exception as e:
                logger.error(f"Failed to initialize LettaKnowledgeTool: {e}", exc_info=True)
        else:
            logger.warning("LettaKnowledgeTool not initialized: runtime_letta_knowledge_agent_id is not available.")

        self.tools_by_name = {tool.name: tool for tool in self.tools_list}
        
        # 创建代理执行器
        logger.info(f"Final tools list for AgentExecutor: {[tool.name for tool in self.tools_list]}")
        self.agent_executor = AgentExecutor.from_agent_and_tools(
            agent=self.create_agent(),
            tools=self.tools_list, # AgentExecutor expects a list
            memory=self.memory,
            verbose=True # Consider setting verbose based on log level or config
        )
        logger.info(f"AgentExecutor initialized with tools: {[tool.name for tool in self.tools_list]}")

    def get_tool(self, name: str) -> Any:
        """Retrieves a tool by its name."""
        tool = self.tools_by_name.get(name)
        if not tool:
            logger.warning(f"Tool with name '{name}' not found.")
        return tool
    
    def create_agent(self):
        """创建基于提示词的代理"""
        logger.debug("Creating agent prompt template.")
        prompt = PromptTemplate(
            template=SYSTEM_PROMPT + "\n\n{chat_history}\n\n用户: {input}\n助手: ",
            input_variables=["chat_history", "input"]
        )
        
        return prompt
    
    async def process_message(self, user_id: int, message: str) -> Dict[str, Any]:
        """处理用户消息并生成回复"""
        logger.info(f"Processing message for user_id: {user_id}, message: '{message}'")
        # 创建或获取对话
        conversation = self._get_or_create_conversation(user_id)
        logger.debug(f"Using conversation_id: {conversation.id} for user_id: {user_id}")
        
        # 分析情绪
        emotion_tool = self.get_tool("emotion_analysis")
        emotion_result = {"emotion": "neutral", "intensity": 0.5} # Default
        if emotion_tool:
            logger.debug(f"Running emotion_analysis tool for conversation_id: {conversation.id}")
            emotion_result = emotion_tool._run(conversation.id)
            logger.debug(f"Emotion analysis result: {emotion_result}")
        else:
            logger.warning("EmotionAnalysisTool not found, using default emotion.")
        
        # 记录用户消息
        user_message = Message(
            conversation_id=conversation.id,
            content=message,
            role="user",
            emotion=emotion_result["emotion"],
            timestamp=datetime.utcnow()
        )
        self.db.add(user_message)
        
        # 生成回复
        logger.debug(f"Generating response for user_id: {user_id}, message: '{message}', emotion: {emotion_result}")
        response = await self._generate_response(user_id, message, emotion_result)
        logger.debug(f"Initial agent response for user_id {user_id}: '{response['content']}'")
        
        # 检查安全性
        safety_tool = self.get_tool("safety_check")
        safety_result = {"is_safe": True} # Default
        if safety_tool:
            logger.debug(f"Running safety_check tool for response: '{response['content']}'")
            safety_result = safety_tool._run(response["content"])
            logger.debug(f"Safety check result: {safety_result}")
        else:
            logger.warning("SafetyCheckTool not found, assuming response is safe.")

        if not safety_result["is_safe"]:
            original_response_content = response["content"]
            response["content"] = "对不起，让我换个方式说。" + self._generate_safe_response()
            logger.warning(f"Safety check failed for response: '{original_response_content}'. Replaced with safe response: '{response['content']}'")
        
        # 记录助手回复
        assistant_message = Message(
            conversation_id=conversation.id,
            content=response["content"],
            role="assistant",
            timestamp=datetime.utcnow()
        )
        self.db.add(assistant_message)
        
        # 记录情绪日志
        emotion_log_tool = self.get_tool("emotion_log")
        if emotion_log_tool:
            log_payload = {
                "user_id": user_id,
                "emotion": emotion_result["emotion"],
                "intensity": emotion_result["intensity"],
                "context": message
            }
            logger.debug(f"Running emotion_log tool with payload: {log_payload}")
            emotion_log_tool._run(log_payload)
        else:
            logger.warning("EmotionLogTool not found, skipping emotion logging.")
        
        try:
            self.db.commit()
            logger.debug("User message, assistant message, and emotion log committed to database.")
        except Exception as e:
            logger.error(f"Database commit failed after processing message for user_id {user_id}: {e}", exc_info=True)
            self.db.rollback()
            # Depending on desired behavior, might re-raise or return an error response
        
        logger.info(f"Finished processing message for user_id: {user_id}. Final response: '{response['content']}'")
        return response
    
    def _get_or_create_conversation(self, user_id: int) -> Conversation:
        """获取或创建新的对话"""
        logger.debug(f"Getting or creating conversation for user_id: {user_id}")
        active_conversation = (
            self.db.query(Conversation)
            .filter(Conversation.user_id == user_id, Conversation.end_time.is_(None))
            .first()
        )
        
        if not active_conversation:
            logger.info(f"No active conversation found for user_id: {user_id}. Creating a new one.")
            active_conversation = Conversation(
                user_id=user_id,
                start_time=datetime.utcnow()
            )
            self.db.add(active_conversation)
            try:
                self.db.commit()
                self.db.refresh(active_conversation) # Ensure ID is loaded
                logger.info(f"Created new conversation_id: {active_conversation.id} for user_id: {user_id}")
            except Exception as e:
                logger.error(f"Database commit failed while creating new conversation for user_id {user_id}: {e}", exc_info=True)
                self.db.rollback()
                raise # Re-raise the exception as this is a critical step
        else:
            logger.debug(f"Found active conversation_id: {active_conversation.id} for user_id: {user_id}")
        
        return active_conversation
    
    async def _generate_response(self, user_id: int, message: str, emotion_result: Dict[str, Any]) -> Dict[str, Any]:
        """生成回复"""
        logger.debug(f"Generating LLM response for user_id: {user_id}. Current chat history for memory: {self.memory.chat_memory.messages}")
        # 获取记忆
        memory_recall_tool = self.get_tool("memory_recall")
        memory_result = {"topics": []} # Default
        if memory_recall_tool:
            logger.debug(f"Running memory_recall tool for user_id: {user_id}")
            memory_result = memory_recall_tool._run(user_id)
            logger.debug(f"Memory recall result: {memory_result}")
        else:
            logger.warning("MemoryRecallTool not found, using empty memory topics.")
        
        # 构建上下文
        context = {
            "recent_topics": memory_result["topics"][-3:],
            "emotion": emotion_result["emotion"],
            "emotion_intensity": emotion_result["intensity"]
        }
        
        # 使用代理生成回复
        logger.debug(f"Context for LLM for user_id {user_id}: {context}")
        
        try:
            response_content = await self.agent_executor.arun(
                input=message,
                context=context # Passed to the prompt
            )
            logger.debug(f"LLM response for user_id {user_id}: '{response_content}'")
        except Exception as e:
            logger.error(f"Error during agent_executor.arun for user_id {user_id}: {e}", exc_info=True)
            response_content = "抱歉，我在尝试处理您的请求时遇到了一些麻烦。" # Fallback response
        
        return {
            "content": response_content,
            "emotion": emotion_result # Keep original emotion or re-evaluate if needed
        }
    
    def _generate_safe_response(self) -> str:
        """生成安全的替代回复"""
        logger.debug("Generating a generic safe response.")
        safe_responses = [
            "这个问题可能涉及一些敏感信息，建议您直接咨询相关部门。",
            "作为数字员工，我需要遵守数据安全规定，建议您通过正式渠道获取这些信息。",
            "这个话题可能需要更专业的建议，建议您咨询主管或HR。",
            "让我们换个角度思考这个问题，关注更具建设性的方面。"
        ]
        # For now, returning the first one. Could be randomized.
        return safe_responses[0]
    
    def end_conversation(self, conversation_id: int):
        """结束对话"""
        logger.info(f"Ending conversation_id: {conversation_id}")
        conversation = self.db.query(Conversation).get(conversation_id)
        if conversation:
            if not conversation.end_time:
                conversation.end_time = datetime.utcnow()
                try:
                    self.db.commit()
                    logger.info(f"Conversation_id: {conversation_id} successfully marked as ended.")
                except Exception as e:
                    logger.error(f"Database commit failed while ending conversation_id {conversation_id}: {e}", exc_info=True)
                    self.db.rollback()
            else:
                logger.warning(f"Attempted to end conversation_id: {conversation_id} which was already ended at {conversation.end_time}.")
        else:
            logger.warning(f"Attempted to end non-existent conversation_id: {conversation_id}")