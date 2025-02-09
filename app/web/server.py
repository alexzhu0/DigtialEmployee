from fastapi import FastAPI, WebSocket, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import json
import asyncio
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.models import User, Conversation, WorkStatus, WorkReport
from app.agent.companion_agent import CompanionAgent
from app.core.speech import AudioProcessor
from config.config import settings

app = FastAPI(title="元芳数字员工")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# 活跃的WebSocket连接
active_connections: Dict[int, WebSocket] = {}

# 音频处理器
audio_processor = AudioProcessor()

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    try:
        user = db.query(User).filter(User.id == int(token)).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

@app.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 这里应该添加密码验证
    # if not verify_password(form_data.password, user.hashed_password):
    #     raise HTTPException(...)
    
    return {
        "access_token": str(user.id),
        "token_type": "bearer"
    }

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    db: Session = Depends(get_db)
):
    await websocket.accept()
    active_connections[user_id] = websocket
    
    try:
        # 创建AI代理
        agent = CompanionAgent(db)
        
        while True:
            # 接收音频数据
            audio_data = await websocket.receive_bytes()
            
            # 语音识别
            async def handle_speech_recognition(text: str):
                # 处理用户消息
                response = await agent.process_message(user_id, text)
                
                # 生成语音回复
                audio_file = f"temp/response_{datetime.utcnow().timestamp()}.wav"
                await audio_processor.synthesize_speech(response["content"], audio_file)
                
                # 发送文本和音频回复
                await websocket.send_json({
                    "type": "text",
                    "content": response["content"]
                })
                
                with open(audio_file, "rb") as f:
                    audio_response = f.read()
                    await websocket.send_bytes(audio_response)
            
            # 处理语音识别
            await audio_processor.recognize_speech(audio_data, handle_speech_recognition)
            
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # 清理连接
        if user_id in active_connections:
            del active_connections[user_id]
        
        # 结束当前对话
        current_conversation = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id, Conversation.end_time.is_(None))
            .first()
        )
        if current_conversation:
            agent.end_conversation(current_conversation.id)

@app.get("/conversations/{user_id}")
async def get_conversations(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this resource"
        )
    
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.start_time.desc())
        .all()
    )
    
    return conversations

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/tasks")
async def create_task(
    task: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    task["user_id"] = current_user.id
    result = agent.tools[4]._run({"action": "create", **task})
    return result

@app.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[4]._run({
        "action": "list",
        "user_id": current_user.id,
        "status": status
    })
    return result

@app.put("/tasks/{task_id}")
async def update_task(
    task_id: int,
    task_update: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[4]._run({
        "action": "update",
        "task_id": task_id,
        **task_update
    })
    return result

@app.get("/work-status")
async def get_work_status(
    db: Session = Depends(get_db)
):
    current_status = (
        db.query(WorkStatus)
        .filter(WorkStatus.end_time.is_(None))
        .first()
    )
    
    if not current_status:
        return {
            "status": "offline",
            "since": None
        }
    
    return {
        "status": current_status.status,
        "since": current_status.start_time.isoformat(),
        "description": current_status.description,
        "current_task_id": current_status.current_task_id
    }

@app.post("/work-status")
async def update_work_status(
    status_update: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[5]._run(status_update)
    return result

@app.post("/reports")
async def generate_report(
    report_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[6]._run(report_data)
    return result

@app.get("/reports/{report_id}")
async def get_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    report = db.query(WorkReport).get(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )
    
    return {
        "id": report.id,
        "type": report.report_type,
        "start_time": report.start_time.isoformat(),
        "end_time": report.end_time.isoformat(),
        "content": report.content,
        "metrics": json.loads(report.metrics),
        "created_at": report.created_at.isoformat()
    }

@app.post("/schedules")
async def create_schedule(
    schedule_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[7]._run({
        "action": "create",
        **schedule_data
    })
    return result

@app.get("/schedules")
async def list_schedules(
    start_time: str,
    end_time: str,
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[7]._run({
        "action": "list",
        "start_time": start_time,
        "end_time": end_time
    })
    return result

@app.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    schedule_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[7]._run({
        "action": "update",
        "schedule_id": schedule_id,
        **schedule_data
    })
    return result

@app.post("/schedules/check-conflicts")
async def check_schedule_conflicts(
    schedule_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[7]._run({
        "action": "check_conflicts",
        **schedule_data
    })
    return result

# 团队管理API
@app.post("/teams")
async def create_team(team_data: dict):
    result = companion_agent.run_tool("team_management", {
        "action": "create_team",
        **team_data
    })
    return result

@app.post("/teams/{team_id}/members")
async def add_team_member(team_id: int, member_data: dict):
    result = companion_agent.run_tool("team_management", {
        "action": "add_member",
        "team_id": team_id,
        **member_data
    })
    return result

@app.post("/teams/{team_id}/projects")
async def create_project(team_id: int, project_data: dict):
    result = companion_agent.run_tool("team_management", {
        "action": "create_project",
        "team_id": team_id,
        **project_data
    })
    return result

@app.put("/projects/{project_id}")
async def update_project(project_id: int, project_data: dict):
    result = companion_agent.run_tool("team_management", {
        "action": "update_project",
        "project_id": project_id,
        **project_data
    })
    return result

# 知识库API
@app.post("/knowledge")
async def create_article(article_data: dict):
    result = companion_agent.run_tool("knowledge_base", {
        "action": "create",
        **article_data
    })
    return result

@app.put("/knowledge/{article_id}")
async def update_article(article_id: int, article_data: dict):
    result = companion_agent.run_tool("knowledge_base", {
        "action": "update",
        "article_id": article_id,
        **article_data
    })
    return result

@app.get("/knowledge")
async def search_articles(category: str = None, keyword: str = None):
    result = companion_agent.run_tool("knowledge_base", {
        "action": "search",
        "category": category,
        "keyword": keyword
    })
    return result

@app.post("/knowledge/{article_id}/comments")
async def add_comment(article_id: int, comment_data: dict):
    result = companion_agent.run_tool("knowledge_base", {
        "action": "add_comment",
        "article_id": article_id,
        **comment_data
    })
    return result

# 团队分析API
@app.post("/teams/{team_id}/metrics")
async def calculate_team_metrics(
    team_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "calculate_metrics",
        "team_id": team_id,
        **data
    })
    return result

@app.post("/teams/{team_id}/activities")
async def track_team_activity(
    team_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "track_activity",
        "team_id": team_id,
        **data
    })
    return result

@app.post("/teams/{team_id}/collaboration")
async def analyze_team_collaboration(
    team_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "analyze_collaboration",
        "team_id": team_id,
        **data
    })
    return result

@app.post("/teams/{team_id}/members/{user_id}/review")
async def generate_performance_review(
    team_id: int,
    user_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "generate_review",
        "team_id": team_id,
        "user_id": user_id,
        **data
    })
    return result

# 团队目标管理API
@app.post("/teams/{team_id}/goals")
async def create_team_goal(
    team_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "manage_goals",
        "sub_action": "create",
        "team_id": team_id,
        **data
    })
    return result

@app.put("/teams/{team_id}/goals/{goal_id}")
async def update_team_goal(
    team_id: int,
    goal_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "manage_goals",
        "sub_action": "update",
        "team_id": team_id,
        "goal_id": goal_id,
        **data
    })
    return result

@app.get("/teams/{team_id}/goals")
async def list_team_goals(
    team_id: int,
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "manage_goals",
        "sub_action": "list",
        "team_id": team_id
    })
    return result

# 团队资源管理API
@app.post("/teams/{team_id}/resources")
async def create_team_resource(
    team_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "manage_resources",
        "sub_action": "create",
        "team_id": team_id,
        **data
    })
    return result

@app.put("/teams/{team_id}/resources/{resource_id}")
async def update_team_resource(
    team_id: int,
    resource_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "manage_resources",
        "sub_action": "update",
        "team_id": team_id,
        "resource_id": resource_id,
        **data
    })
    return result

@app.get("/teams/{team_id}/resources")
async def list_team_resources(
    team_id: int,
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "manage_resources",
        "sub_action": "list",
        "team_id": team_id
    })
    return result

# 团队能力管理API
@app.put("/teams/{team_id}/capabilities")
async def update_team_capability(
    team_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "analyze_capabilities",
        "sub_action": "update",
        "team_id": team_id,
        **data
    })
    return result

@app.get("/teams/{team_id}/capabilities/analysis")
async def analyze_team_capabilities(
    team_id: int,
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "analyze_capabilities",
        "sub_action": "analyze",
        "team_id": team_id
    })
    return result

# 团队风险管理API
@app.post("/teams/{team_id}/risks")
async def create_team_risk(
    team_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "assess_risks",
        "sub_action": "create",
        "team_id": team_id,
        **data
    })
    return result

@app.put("/teams/{team_id}/risks/{risk_id}")
async def update_team_risk(
    team_id: int,
    risk_id: int,
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "assess_risks",
        "sub_action": "update",
        "team_id": team_id,
        "risk_id": risk_id,
        **data
    })
    return result

@app.get("/teams/{team_id}/risks/analysis")
async def analyze_team_risks(
    team_id: int,
    db: Session = Depends(get_db)
):
    agent = CompanionAgent(db)
    result = agent.tools[10]._run({
        "action": "assess_risks",
        "sub_action": "analyze",
        "team_id": team_id
    })
    return result 