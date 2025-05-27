from fastapi import FastAPI, WebSocket, Depends, HTTPException, status, Path, Query, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, Union, List 
import json
import asyncio
from datetime import datetime, timedelta, date 
import time # For request timing

# Security imports
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.core.database import get_db
from app.core.models import User, Conversation, WorkStatus, WorkReport
from app.agent.companion_agent import CompanionAgent
from app.core.speech import AudioProcessor
from config.config import settings
from app.web import schemas 
from config.logging_config import get_logger 
from app.services import letta_service # Import Letta service
from fastapi import UploadFile, File # For file uploads

logger = get_logger(__name__)

# Global variable to store the Letta Knowledge Agent ID during runtime
# This is a simplification for this subtask. In a production scenario,
# this ID should be persisted more robustly (e.g., in DB or updated in .env).
runtime_letta_knowledge_agent_id: Optional[str] = None

app = FastAPI(title="元芳数字员工")

@app.on_event("startup")
async def startup_event():
    logger.info("Application startup: Initializing Letta client and knowledge agent...")
    letta_service.initialize_letta_client()
    client = letta_service.get_letta_client()
    if client:
        global runtime_letta_knowledge_agent_id
        # Try to get ID from settings first
        agent_id_from_settings = settings.LETTA_KNOWLEDGE_AGENT_ID
        if agent_id_from_settings:
            logger.info(f"Verifying Letta agent ID from settings: {agent_id_from_settings}")
            try:
                agent = client.agents.get(agent_id_from_settings)
                if agent:
                    runtime_letta_knowledge_agent_id = agent.id
                    logger.info(f"Successfully verified Letta agent from settings: {agent.name} (ID: {agent.id})")
                else: # Should not happen if get() raises for not found
                    logger.warning(f"Agent ID {agent_id_from_settings} from settings not found. Will attempt to find or create.")
                    runtime_letta_knowledge_agent_id = None # Clear it to trigger find_or_create
            except Exception as e:
                logger.warning(f"Failed to verify agent ID {agent_id_from_settings} from settings: {e}. Will attempt to find or create.")
                runtime_letta_knowledge_agent_id = None # Clear it to trigger find_or_create
        
        if not runtime_letta_knowledge_agent_id:
            logger.info(f"No valid agent ID from settings, attempting to find or create agent: {settings.LETTA_KNOWLEDGE_AGENT_NAME}")
            runtime_letta_knowledge_agent_id = letta_service.find_or_create_agent(
                agent_name=settings.LETTA_KNOWLEDGE_AGENT_NAME,
                llm_model=settings.LETTA_KNOWLEDGE_LLM_MODEL,
                embedding_model=settings.LETTA_KNOWLEDGE_EMBEDDING_MODEL
            )
        
        if runtime_letta_knowledge_agent_id:
            logger.info(f"Letta Knowledge Agent ID set to: {runtime_letta_knowledge_agent_id}")
            # For this subtask, we are not persisting it back to settings file directly.
            # In a real scenario, if LETTA_KNOWLEDGE_AGENT_ID was initially None and a new agent was created,
            # this ID should be stored persistently (e.g., update .env file or a config map).
            # For now, logging it is sufficient:
            if not settings.LETTA_KNOWLEDGE_AGENT_ID or settings.LETTA_KNOWLEDGE_AGENT_ID != runtime_letta_knowledge_agent_id:
                 logger.info(f"Consider updating your .env file with: LETTA_KNOWLEDGE_AGENT_ID={runtime_letta_knowledge_agent_id}")
        else:
            logger.error("Failed to find or create Letta knowledge agent during startup.")
    else:
        logger.error("Letta client could not be initialized. Knowledge management features via Letta will be unavailable.")


# Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    log_dict = {
        "method": request.method,
        "url": str(request.url),
        "headers": {k: v for k, v in request.headers.items() if k.lower() not in ['authorization']}, # Avoid logging sensitive headers
        "client_ip": request.client.host if request.client else "Unknown"
    }
    logger.info(f"Incoming request: {json.dumps(log_dict)}")
    
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    
    logger.info(
        f"Response: status_code={response.status_code}, process_time={process_time:.2f}ms, method={request.method}, url={request.url}"
    )
    return response

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception for request {request.method} {request.url}: {exc}", exc_info=True)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error" # Generic message to client
    )

# HTTPException logging (FastAPI already handles returning the response)
@app.exception_handler(HTTPException)
async def http_exception_logging_handler(request: Request, exc: HTTPException):
    logger.warning(
        f"HTTPException for request {request.method} {request.url}: status_code={exc.status_code}, detail='{exc.detail}'"
    )
    # Re-raise the original HTTPException to let FastAPI handle the response
    # Or construct and return a JSONResponse if you want to customize the structure
    # For now, let FastAPI's default handling proceed after logging.
    # This means we need to return the original response behavior.
    # The default handler for HTTPException will take care of sending the response.
    # So, we just log and then can let it propagate or return a new response.
    # To ensure FastAPI's default behavior is used after logging:
    return await request.app.default_exception_handlers[HTTPException](request, exc)


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

# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings from config
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# 活跃的WebSocket连接
active_connections: Dict[int, WebSocket] = {}

# 音频处理器
audio_processor = AudioProcessor()

# Dependency for CompanionAgent
def get_companion_agent(db: Session = Depends(get_db)) -> CompanionAgent:
    return CompanionAgent(db)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15) # Default expiry
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        # You might want to add a token_id to the payload to store and validate against a list of active tokens
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

@app.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "id": user.id}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id, # You might want to remove this or keep it depending on frontend needs
        "username": user.username
    }

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int,
    db: Session = Depends(get_db), # db is now accessed via get_companion_agent, but also used directly
    agent: CompanionAgent = Depends(get_companion_agent)
):
    await websocket.accept()
    active_connections[user_id] = websocket
    logger.info(f"WebSocket connection established for user_id: {user_id}, client: {websocket.client}")
    
    try:
        # AI代理 is now injected as 'agent'
        
        while True:
            # 接收音频数据
            audio_data = await websocket.receive_bytes()
            logger.debug(f"Received audio data from user_id: {user_id}, size: {len(audio_data)} bytes")
            
            # 语音识别
            async def handle_speech_recognition(text: str):
                logger.info(f"Recognized speech for user_id {user_id}: '{text}'")
                # 处理用户消息
                response = await agent.process_message(user_id, text)
                logger.info(f"Agent response for user_id {user_id}: '{response['content']}'")
                
                # 生成语音回复
                audio_file = f"temp/response_{datetime.utcnow().timestamp()}.wav"
                await audio_processor.synthesize_speech(response["content"], audio_file)
                logger.debug(f"Synthesized speech for user_id {user_id} to file: {audio_file}")
                
                # 发送文本和音频回复
                await websocket.send_json({
                    "type": "text",
                    "content": response["content"]
                })
                logger.debug(f"Sent text response to user_id {user_id}")
                
                with open(audio_file, "rb") as f:
                    audio_response = f.read()
                    await websocket.send_bytes(audio_response)
                logger.debug(f"Sent audio response to user_id {user_id}, size: {len(audio_response)} bytes")
            
            # 处理语音识别
            await audio_processor.recognize_speech(audio_data, handle_speech_recognition)
            
    except Exception as e:
        logger.error(f"WebSocket error for user_id {user_id}: {e}", exc_info=True)
    finally:
        # 清理连接
        if user_id in active_connections:
            del active_connections[user_id]
        logger.info(f"WebSocket connection closed for user_id: {user_id}")
        
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

@app.post("/tasks", response_model=Optional[schemas.TaskResponse]) # Assuming agent returns something convertible to TaskResponse
async def create_task(
    task_data: schemas.TaskCreate,
    current_user: User = Depends(get_current_user),
    agent: CompanionAgent = Depends(get_companion_agent)
):
    task_payload = task_data.model_dump()
    task_payload["user_id"] = current_user.id
    logger.info(f"User {current_user.username} creating task: {task_data.title}")
    task_tool = agent.get_tool("task_management")
    # The agent's _run method receives a dict. The Pydantic model ensures the structure before this.
    result = task_tool._run({"action": "create", **task_payload}) if task_tool else None 
    if result:
        logger.info(f"Task '{task_data.title}' created successfully for user {current_user.username} with ID: {result.get('id') if isinstance(result, dict) else result}")
    else:
        logger.warning(f"Task creation failed for user {current_user.username}, title: {task_data.title}")
    return result

@app.get("/tasks", response_model=Optional[List[schemas.TaskResponse]])
async def list_tasks(
    status: Optional[str] = Query(None, pattern=r"^(pending|in_progress|completed|cancelled)$", description="Filter tasks by status"),
    current_user: User = Depends(get_current_user),
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.debug(f"User {current_user.username} listing tasks with status: {status}")
    task_tool = agent.get_tool("task_management")
    result = task_tool._run({
        "action": "list",
        "user_id": current_user.id,
        "status": status
    })
    logger.debug(f"Found {len(result) if result else 0} tasks for user {current_user.username}")
    return result

@app.put("/tasks/{task_id}", response_model=Optional[schemas.TaskResponse])
async def update_task(
    task_id: int = Path(..., gt=0, description="The ID of the task to update"),
    task_data: schemas.TaskUpdate,
    current_user: User = Depends(get_current_user),
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} updating task ID: {task_id} with data: {task_data.model_dump(exclude_unset=True)}")
    task_tool = agent.get_tool("task_management")
    result = task_tool._run({
        "action": "update",
        "task_id": task_id,
        **task_data.model_dump(exclude_unset=True)
    }) if task_tool else None
    if result:
        logger.info(f"Task ID: {task_id} updated successfully for user {current_user.username}")
    else:
        logger.warning(f"Task ID: {task_id} update failed for user {current_user.username}")
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

@app.post("/work-status") # Define response model if agent returns structured data
async def update_work_status(
    status_data: schemas.WorkStatusUpdate,
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"Updating work status: {status_data.status} for user (agent context)") # Assuming agent context has user
    work_status_tool = agent.get_tool("work_status")
    result = work_status_tool._run(status_data.model_dump()) if work_status_tool else None
    logger.info(f"Work status update result: {result}")
    return result

@app.post("/reports") 
async def generate_report(
    report_req_data: schemas.ReportGenerate,
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"Generating report type: {report_req_data.report_type} from {report_req_data.start_time} to {report_req_data.end_time}")
    report_tool = agent.get_tool("report_generation")
    result = report_tool._run(report_req_data.model_dump()) if report_tool else None
    logger.info(f"Report generation result: {result.get('id') if isinstance(result, dict) else result}")
    return result

@app.get("/reports/{report_id}") 
async def get_report(
    report_id: int = Path(..., gt=0, description="The ID of the report to retrieve"),
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

@app.post("/schedules") # Define response model
async def create_schedule(
    schedule_req_data: schemas.ScheduleCreate,
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} creating schedule: {schedule_req_data.title}")
    schedule_tool = agent.get_tool("schedule_management")
    result = schedule_tool._run({
        "action": "create",
        **schedule_req_data.model_dump()
    })
    logger.info(f"Schedule creation for '{schedule_req_data.title}' by {current_user.username}, result: {result}")
    return result

@app.get("/schedules") # Define response model
async def list_schedules(
    start_time: datetime = Query(..., description="Start time for filtering schedules"),
    end_time: datetime = Query(..., description="End time for filtering schedules"),
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.debug(f"User {current_user.username} listing schedules from {start_time} to {end_time}")
    schedule_tool = agent.get_tool("schedule_management")
    result = schedule_tool._run({
        "action": "list",
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat()
    })
    logger.debug(f"Found {len(result) if isinstance(result, list) else 'N/A'} schedules for user {current_user.username}")
    return result

@app.put("/schedules/{schedule_id}") # Define response model
async def update_schedule(
    schedule_id: int = Path(..., gt=0, description="The ID of the schedule to update"),
    schedule_req_data: schemas.ScheduleUpdate,
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} updating schedule ID: {schedule_id} with data: {schedule_req_data.model_dump(exclude_unset=True)}")
    schedule_tool = agent.get_tool("schedule_management")
    result = schedule_tool._run({
        "action": "update",
        "schedule_id": schedule_id,
        **schedule_req_data.model_dump(exclude_unset=True)
    })
    logger.info(f"Schedule ID: {schedule_id} update by {current_user.username} result: {result}")
    return result

@app.post("/schedules/check-conflicts") # Define response model
async def check_schedule_conflicts(
    schedule_check_data: schemas.ScheduleConflictCheck,
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.debug(f"User {current_user.username} checking schedule conflicts for users: {schedule_check_data.user_ids} between {schedule_check_data.start_time} and {schedule_check_data.end_time}")
    schedule_tool = agent.get_tool("schedule_management")
    result = schedule_tool._run({
        "action": "check_conflicts",
        **schedule_check_data.model_dump()
    })
    logger.debug(f"Schedule conflict check by {current_user.username} result: {result}")
    return result

# 团队管理API
@app.post("/teams") # Define response model
async def create_team(team_req_data: schemas.TeamCreate, current_user: User = Depends(get_current_user), agent: CompanionAgent = Depends(get_companion_agent)):
    logger.info(f"User {current_user.username} creating team: {team_req_data.name}")
    team_tool = agent.get_tool("team_management")
    result = team_tool._run({
        "action": "create_team",
        **team_req_data.model_dump()
        # Consider adding created_by: current_user.id if tool supports/requires it
    }) if team_tool else None
    logger.info(f"Team '{team_req_data.name}' creation by {current_user.username} result: {result}")
    return result

@app.post("/teams/{team_id}/members") # Define response model
async def add_team_member(
    team_id: int = Path(..., gt=0, description="The ID of the team"),
    member_req_data: schemas.TeamMemberAdd, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} adding member {member_req_data.user_id} to team ID: {team_id} with role: {member_req_data.role}")
    team_tool = agent.get_tool("team_management")
    result = team_tool._run({
        "action": "add_member",
        "team_id": team_id,
        **member_req_data.model_dump()
    }) if team_tool else None
    logger.info(f"Add member to team ID: {team_id} by {current_user.username} result: {result}")
    return result

@app.post("/teams/{team_id}/projects") # Define response model
async def create_project(
    team_id: int = Path(..., gt=0, description="The ID of the team for the new project"),
    project_req_data: schemas.ProjectCreate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} creating project '{project_req_data.name}' for team ID: {team_id}")
    team_tool = agent.get_tool("team_management")
    result = team_tool._run({
        "action": "create_project",
        "team_id": team_id, 
        **project_req_data.model_dump()
    }) if team_tool else None
    logger.info(f"Project '{project_req_data.name}' creation by {current_user.username} result: {result}")
    return result

@app.put("/projects/{project_id}") # Define response model
async def update_project(
    project_id: int = Path(..., gt=0, description="The ID of the project to update"),
    project_req_data: schemas.ProjectUpdate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} updating project ID: {project_id} with data: {project_req_data.model_dump(exclude_unset=True)}")
    team_tool = agent.get_tool("team_management")
    result = team_tool._run({
        "action": "update_project",
        "project_id": project_id,
        **project_req_data.model_dump(exclude_unset=True)
    }) if team_tool else None
    logger.info(f"Project ID: {project_id} update by {current_user.username} result: {result}")
    return result

# 知识库API
@app.post("/knowledge") # Define response model
async def create_article(
    article_req_data: schemas.ArticleCreate, 
    current_user: User = Depends(get_current_user), # For created_by
    agent: CompanionAgent = Depends(get_companion_agent)
):
    payload = article_req_data.model_dump()
    payload["created_by"] = current_user.id 
    logger.info(f"User {current_user.username} creating article: {article_req_data.title}")
    kb_tool = agent.get_tool("knowledge_base")
    result = kb_tool._run({
        "action": "create",
        **payload
    }) if kb_tool else None
    logger.info(f"Article '{article_req_data.title}' creation by {current_user.username} result: {result}")
    return result

@app.put("/knowledge/{article_id}") # Define response model
async def update_article(
    article_id: int = Path(..., gt=0, description="The ID of the article to update"),
    article_req_data: schemas.ArticleUpdate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} updating article ID: {article_id} with data: {article_req_data.model_dump(exclude_unset=True)}")
    kb_tool = agent.get_tool("knowledge_base")
    result = kb_tool._run({
        "action": "update",
        "article_id": article_id,
        **article_req_data.model_dump(exclude_unset=True)
    }) if kb_tool else None
    logger.info(f"Article ID: {article_id} update by {current_user.username} result: {result}")
    return result

@app.get("/knowledge") # Define response model
async def search_articles(
    category: Optional[str] = Query(None, max_length=100, description="Category to filter articles"), 
    keyword: Optional[str] = Query(None, min_length=2, max_length=100, description="Keyword to search in articles"), 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.debug(f"User {current_user.username} searching articles with category: {category}, keyword: {keyword}")
    kb_tool = agent.get_tool("knowledge_base")
    result = kb_tool._run({
        "action": "search",
        "category": category,
        "keyword": keyword
    }) if kb_tool else None
    logger.debug(f"Found {len(result) if isinstance(result, list) else 'N/A'} articles for user {current_user.username}.")
    return result

@app.post("/knowledge/{article_id}/comments") # Define response model
async def add_comment(
    article_id: int = Path(..., gt=0, description="The ID of the article to comment on"),
    comment_req_data: schemas.CommentCreate, 
    current_user: User = Depends(get_current_user), 
    agent: CompanionAgent = Depends(get_companion_agent)
):
    payload = comment_req_data.model_dump()
    payload["created_by"] = current_user.id
    logger.info(f"User {current_user.username} adding comment to article ID: {article_id}")
    kb_tool = agent.get_tool("knowledge_base")
    result = kb_tool._run({
        "action": "add_comment",
        "article_id": article_id,
        **payload
    }) if kb_tool else None
    logger.info(f"Add comment to article ID: {article_id} by {current_user.username} result: {result}")
    return result

# Letta Knowledge Upload Endpoint
@app.post("/knowledge/upload_to_letta", tags=["Knowledge Base", "Letta"])
async def upload_document_to_letta_agent(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user) # For logging and potential future use
):
    logger.info(f"User '{current_user.username}' initiating document upload: {file.filename}")
    
    global runtime_letta_knowledge_agent_id
    if not runtime_letta_knowledge_agent_id:
        logger.error("Letta knowledge agent ID not available. Cannot upload document.")
        raise HTTPException(status_code=503, detail="Letta knowledge service not configured or unavailable.")

    client = letta_service.get_letta_client()
    if not client:
        logger.error("Letta client not available. Cannot upload document.")
        raise HTTPException(status_code=503, detail="Letta service unavailable.")

    try:
        file_content = await file.read()
        logger.debug(f"Read {len(file_content)} bytes from uploaded file: {file.filename}")
        
        success = letta_service.upload_document_to_agent(
            agent_id=runtime_letta_knowledge_agent_id,
            file_name=file.filename if file.filename else "uploaded_file",
            file_content=file_content
        )
        
        if success:
            logger.info(f"Document '{file.filename}' uploaded successfully to Letta agent by user '{current_user.username}'.")
            return {"message": f"Document '{file.filename}' uploaded successfully to Letta knowledge agent."}
        else:
            logger.error(f"Failed to upload document '{file.filename}' to Letta agent for user '{current_user.username}'.")
            raise HTTPException(status_code=500, detail=f"Failed to upload document '{file.filename}' to Letta agent.")
            
    except HTTPException as http_exc: # Re-raise HTTPExceptions to let FastAPI handle them
        raise http_exc
    except Exception as e:
        logger.error(f"An error occurred during file upload by user '{current_user.username}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
    finally:
        await file.close()
        logger.debug(f"Closed uploaded file: {file.filename}")


# 团队分析API
@app.post("/teams/{team_id}/metrics") # Define response model
async def calculate_team_metrics(
    team_id: int = Path(..., gt=0, description="The ID of the team for metrics calculation"),
    metrics_req_data: schemas.TeamMetricsCalculate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} calculating metrics for team ID: {team_id}, type: {metrics_req_data.metric_type}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "calculate_metrics",
        "team_id": team_id,
        **metrics_req_data.model_dump()
    }) if analytics_tool else None
    logger.info(f"Metrics calculation for team ID: {team_id} by {current_user.username} result: {result}")
    return result

@app.post("/teams/{team_id}/activities") # Define response model
async def track_team_activity(
    team_id: int = Path(..., gt=0, description="The ID of the team to track activity for"),
    activity_req_data: schemas.TeamActivityTrack, 
    current_user: User = Depends(get_current_user), 
    agent: CompanionAgent = Depends(get_companion_agent)
):
    payload = activity_req_data.model_dump()
    logger.info(f"User {current_user.username} tracking activity for team ID: {team_id}, type: {activity_req_data.activity_type}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "track_activity",
        "team_id": team_id,
        "created_by": current_user.id, # Assuming tool handles this if needed, or remove if tool sets it
        **payload
    }) if analytics_tool else None
    logger.info(f"Track activity for team ID: {team_id} by {current_user.username} result: {result}")
    return result

@app.post("/teams/{team_id}/collaboration") # Define response model
async def analyze_team_collaboration(
    team_id: int = Path(..., gt=0, description="The ID of the team for collaboration analysis"),
    collab_req_data: schemas.TeamCollaborationAnalyze, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} analyzing collaboration for team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "analyze_collaboration",
        "team_id": team_id,
        **collab_req_data.model_dump()
    }) if analytics_tool else None
    logger.info(f"Collaboration analysis for team ID: {team_id} by {current_user.username} result: {result}")
    return result

@app.post("/teams/{team_id}/members/{user_id}/review") # Define response model
async def generate_performance_review(
    team_id: int = Path(..., gt=0, description="The ID of the team"),
    user_id: int = Path(..., gt=0, description="The ID of the user for performance review"),
    review_req_data: schemas.PerformanceReviewGenerate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} generating performance review for user ID: {user_id} in team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "generate_review",
        "team_id": team_id,
        "user_id": user_id,
        **review_req_data.model_dump()
    }) if analytics_tool else None
    logger.info(f"Performance review generation by {current_user.username} for user ID: {user_id}, team ID: {team_id} result: {result}")
    return result

# 团队目标管理API
@app.post("/teams/{team_id}/goals") # Define response model
async def create_team_goal(
    team_id: int = Path(..., gt=0, description="The ID of the team for the new goal"),
    goal_req_data: schemas.TeamGoalCreate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} creating goal '{goal_req_data.title}' for team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "manage_goals",
        "sub_action": "create",
        "team_id": team_id,
        **goal_req_data.model_dump()
    }) if analytics_tool else None
    logger.info(f"Goal '{goal_req_data.title}' creation by {current_user.username} for team ID: {team_id} result: {result}")
    return result

@app.put("/teams/{team_id}/goals/{goal_id}") # Define response model
async def update_team_goal(
    team_id: int = Path(..., gt=0, description="The ID of the team"),
    goal_id: int = Path(..., gt=0, description="The ID of the goal to update"),
    goal_req_data: schemas.TeamGoalUpdate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} updating goal ID: {goal_id} for team ID: {team_id} with data: {goal_req_data.model_dump(exclude_unset=True)}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "manage_goals",
        "sub_action": "update",
        "team_id": team_id,
        "goal_id": goal_id,
        **goal_req_data.model_dump(exclude_unset=True)
    }) if analytics_tool else None
    logger.info(f"Goal ID: {goal_id} update by {current_user.username} for team ID: {team_id} result: {result}")
    return result

@app.get("/teams/{team_id}/goals") # Define response model
async def list_team_goals(
    team_id: int = Path(..., gt=0, description="The ID of the team whose goals are to be listed"),
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.debug(f"User {current_user.username} listing goals for team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "manage_goals",
        "sub_action": "list",
        "team_id": team_id
    }) if analytics_tool else None
    logger.debug(f"Found {len(result) if isinstance(result, list) else 'N/A'} goals for team ID: {team_id} by {current_user.username}")
    return result

# 团队资源管理API
@app.post("/teams/{team_id}/resources") # Define response model
async def create_team_resource(
    team_id: int = Path(..., gt=0, description="The ID of the team for the new resource"),
    resource_req_data: schemas.TeamResourceCreate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} creating resource '{resource_req_data.name}' for team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "manage_resources",
        "sub_action": "create",
        "team_id": team_id,
        **resource_req_data.model_dump()
    }) if analytics_tool else None
    logger.info(f"Resource '{resource_req_data.name}' creation by {current_user.username} for team ID: {team_id} result: {result}")
    return result

@app.put("/teams/{team_id}/resources/{resource_id}") # Define response model
async def update_team_resource(
    team_id: int = Path(..., gt=0, description="The ID of the team"),
    resource_id: int = Path(..., gt=0, description="The ID of the resource to update"),
    resource_req_data: schemas.TeamResourceUpdate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} updating resource ID: {resource_id} for team ID: {team_id} with data: {resource_req_data.model_dump(exclude_unset=True)}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "manage_resources",
        "sub_action": "update",
        "team_id": team_id,
        "resource_id": resource_id,
        **resource_req_data.model_dump(exclude_unset=True)
    }) if analytics_tool else None
    logger.info(f"Resource ID: {resource_id} update by {current_user.username} for team ID: {team_id} result: {result}")
    return result

@app.get("/teams/{team_id}/resources") # Define response model
async def list_team_resources(
    team_id: int = Path(..., gt=0, description="The ID of the team whose resources are to be listed"),
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.debug(f"User {current_user.username} listing resources for team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "manage_resources",
        "sub_action": "list",
        "team_id": team_id
    }) if analytics_tool else None
    logger.debug(f"Found {len(result) if isinstance(result, list) else 'N/A'} resources for team ID: {team_id} by {current_user.username}")
    return result

# 团队能力管理API
@app.put("/teams/{team_id}/capabilities") # Define response model
async def update_team_capability(
    team_id: int = Path(..., gt=0, description="The ID of the team whose capabilities are to be updated"),
    capability_req_data: schemas.TeamCapabilityUpdate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} updating capabilities for team ID: {team_id}, capability: {capability_req_data.name}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "analyze_capabilities", 
        "sub_action": "update", 
        "team_id": team_id,
        **capability_req_data.model_dump()
    }) if analytics_tool else None
    logger.info(f"Capability update for team ID: {team_id} by {current_user.username}, capability {capability_req_data.name} result: {result}")
    return result

@app.get("/teams/{team_id}/capabilities/analysis") # Define response model
async def analyze_team_capabilities(
    team_id: int = Path(..., gt=0, description="The ID of the team for capability analysis"),
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.debug(f"User {current_user.username} analyzing capabilities for team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "analyze_capabilities",
        "sub_action": "analyze",
        "team_id": team_id
    }) if analytics_tool else None
    logger.debug(f"Capability analysis for team ID: {team_id} by {current_user.username} result: {result}")
    return result

# 团队风险管理API
@app.post("/teams/{team_id}/risks") # Define response model
async def create_team_risk(
    team_id: int = Path(..., gt=0, description="The ID of the team for the new risk"),
    risk_req_data: schemas.TeamRiskCreate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} creating risk '{risk_req_data.title}' for team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "assess_risks",
        "sub_action": "create",
        "team_id": team_id,
        **risk_req_data.model_dump()
    }) if analytics_tool else None
    logger.info(f"Risk '{risk_req_data.title}' creation by {current_user.username} for team ID: {team_id} result: {result}")
    return result

@app.put("/teams/{team_id}/risks/{risk_id}") # Define response model
async def update_team_risk(
    team_id: int = Path(..., gt=0, description="The ID of the team"),
    risk_id: int = Path(..., gt=0, description="The ID of the risk to update"),
    risk_req_data: schemas.TeamRiskUpdate, 
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.info(f"User {current_user.username} updating risk ID: {risk_id} for team ID: {team_id} with data: {risk_req_data.model_dump(exclude_unset=True)}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "assess_risks",
        "sub_action": "update",
        "team_id": team_id,
        "risk_id": risk_id,
        **risk_req_data.model_dump(exclude_unset=True)
    }) if analytics_tool else None
    logger.info(f"Risk ID: {risk_id} update by {current_user.username} for team ID: {team_id} result: {result}")
    return result

@app.get("/teams/{team_id}/risks/analysis") # Define response model
async def analyze_team_risks(
    team_id: int = Path(..., gt=0, description="The ID of the team for risk analysis"),
    current_user: User = Depends(get_current_user), # Added for logging
    agent: CompanionAgent = Depends(get_companion_agent)
):
    logger.debug(f"User {current_user.username} analyzing risks for team ID: {team_id}")
    analytics_tool = agent.get_tool("team_analytics")
    result = analytics_tool._run({
        "action": "assess_risks",
        "sub_action": "analyze",
        "team_id": team_id
    }) if analytics_tool else None
    logger.debug(f"Risk analysis for team ID: {team_id} by {current_user.username} result: {result}")
    return result