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
from app.agent.prompts import SYSTEM_PROMPT, EMOTION_ANALYSIS_PROMPT, MEMORY_RECALL_PROMPT, SAFETY_CHECK_PROMPT
from app.core.models import User, Conversation, Message
from sqlalchemy.orm import Session
from datetime import datetime
from config.config import settings

class CompanionAgent:
    def __init__(self, db: Session):
        self.db = db
        self.llm = DeepSeek(api_key=settings.DEEPSEEK_API_KEY)
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            max_token_limit=2000
        )
        
        # 初始化工具
        self.tools = [
            EmotionAnalysisTool(db),
            MemoryRecallTool(db),
            SafetyCheckTool(),
            EmotionLogTool(db),
            TaskManagementTool(db),
            WorkStatusTool(db),
            ReportGenerationTool(db),
            ScheduleManagementTool(db),
            TeamManagementTool(db),
            KnowledgeBaseTool(db),
            TeamAnalyticsTool(db)
        ]
        
        # 创建代理执行器
        self.agent_executor = AgentExecutor.from_agent_and_tools(
            agent=self.create_agent(),
            tools=self.tools,
            memory=self.memory,
            verbose=True
        )
    
    def create_agent(self):
        """创建基于提示词的代理"""
        prompt = PromptTemplate(
            template=SYSTEM_PROMPT + "\n\n{chat_history}\n\n用户: {input}\n助手: ",
            input_variables=["chat_history", "input"]
        )
        
        return prompt
    
    async def process_message(self, user_id: int, message: str) -> Dict[str, Any]:
        """处理用户消息并生成回复"""
        # 创建或获取对话
        conversation = self._get_or_create_conversation(user_id)
        
        # 分析情绪
        emotion_result = self.tools[0]._run(conversation.id)
        
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
        response = await self._generate_response(user_id, message, emotion_result)
        
        # 检查安全性
        safety_result = self.tools[2]._run(response["content"])
        if not safety_result["is_safe"]:
            response["content"] = "对不起，让我换个方式说。" + self._generate_safe_response()
        
        # 记录助手回复
        assistant_message = Message(
            conversation_id=conversation.id,
            content=response["content"],
            role="assistant",
            timestamp=datetime.utcnow()
        )
        self.db.add(assistant_message)
        
        # 记录情绪日志
        self.tools[3]._run({
            "user_id": user_id,
            "emotion": emotion_result["emotion"],
            "intensity": emotion_result["intensity"],
            "context": message
        })
        
        self.db.commit()
        return response
    
    def _get_or_create_conversation(self, user_id: int) -> Conversation:
        """获取或创建新的对话"""
        active_conversation = (
            self.db.query(Conversation)
            .filter(Conversation.user_id == user_id, Conversation.end_time.is_(None))
            .first()
        )
        
        if not active_conversation:
            active_conversation = Conversation(
                user_id=user_id,
                start_time=datetime.utcnow()
            )
            self.db.add(active_conversation)
            self.db.commit()
        
        return active_conversation
    
    async def _generate_response(self, user_id: int, message: str, emotion_result: Dict[str, Any]) -> Dict[str, Any]:
        """生成回复"""
        # 获取记忆
        memory_result = self.tools[1]._run(user_id)
        
        # 构建上下文
        context = {
            "recent_topics": memory_result["topics"][-3:],
            "emotion": emotion_result["emotion"],
            "emotion_intensity": emotion_result["intensity"]
        }
        
        # 使用代理生成回复
        response = await self.agent_executor.arun(
            input=message,
            context=context
        )
        
        return {
            "content": response,
            "emotion": emotion_result
        }
    
    def _generate_safe_response(self) -> str:
        """生成安全的替代回复"""
        safe_responses = [
            "这个问题可能涉及一些敏感信息，建议您直接咨询相关部门。",
            "作为数字员工，我需要遵守数据安全规定，建议您通过正式渠道获取这些信息。",
            "这个话题可能需要更专业的建议，建议您咨询主管或HR。",
            "让我们换个角度思考这个问题，关注更具建设性的方面。"
        ]
        return safe_responses[0]  # 这里可以随机选择
    
    def end_conversation(self, conversation_id: int):
        """结束对话"""
        conversation = self.db.query(Conversation).get(conversation_id)
        if conversation and not conversation.end_time:
            conversation.end_time = datetime.utcnow()
            self.db.commit() 