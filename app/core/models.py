from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    full_name = Column(String(100))
    email = Column(String(100), unique=True, index=True)
    department = Column(String(100))
    position = Column(String(100))
    employee_id = Column(String(50), unique=True)
    hashed_password = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    conversations = relationship("Conversation", back_populates="user")
    preferences = relationship("UserPreference", back_populates="user")
    tasks = relationship("Task", back_populates="user")
    team_memberships = relationship("TeamMember", back_populates="user")
    knowledge_articles = relationship("KnowledgeBase", back_populates="author")
    knowledge_revisions = relationship("KnowledgeRevision", back_populates="author")
    knowledge_comments = relationship("KnowledgeComment", back_populates="author")

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    emotion_score = Column(Float, nullable=True)
    
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    content = Column(Text)
    role = Column(String(20))  # user 或 assistant
    timestamp = Column(DateTime, default=datetime.utcnow)
    emotion = Column(String(50), nullable=True)
    
    conversation = relationship("Conversation", back_populates="messages")

class UserPreference(Base):
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    key = Column(String(100))
    value = Column(Text)
    
    user = relationship("User", back_populates="preferences")

class EmotionLog(Base):
    __tablename__ = "emotion_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    emotion = Column(String(50))
    intensity = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    context = Column(Text, nullable=True)

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(200))
    description = Column(Text)
    status = Column(String(50))  # pending, in_progress, completed, cancelled
    priority = Column(Integer)  # 1-5
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    
    user = relationship("User", back_populates="tasks")
    activities = relationship("TaskActivity", back_populates="task")
    project = relationship("Project", back_populates="tasks")

class TaskActivity(Base):
    __tablename__ = "task_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"))
    action = Column(String(50))  # created, updated, status_changed
    description = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    task = relationship("Task", back_populates="activities")

class WorkStatus(Base):
    __tablename__ = "work_status"
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50))  # available, busy, in_meeting, break, offline
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    description = Column(Text, nullable=True)
    current_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)

class WorkReport(Base):
    __tablename__ = "work_reports"
    
    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(50))  # daily, weekly, monthly
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    content = Column(Text)
    metrics = Column(Text)  # JSON格式存储的指标数据
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tasks = relationship("Task", secondary="report_tasks")
    activities = relationship("WorkActivity", back_populates="report")

class ReportTask(Base):
    __tablename__ = "report_tasks"
    
    report_id = Column(Integer, ForeignKey("work_reports.id"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), primary_key=True)

class WorkActivity(Base):
    __tablename__ = "work_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("work_reports.id"))
    activity_type = Column(String(50))  # task, meeting, break, etc.
    description = Column(Text)
    duration = Column(Integer)  # 以分钟为单位
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    report = relationship("WorkReport", back_populates="activities")

class Schedule(Base):
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200))
    event_type = Column(String(50))  # meeting, task, break, etc.
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    description = Column(Text, nullable=True)
    location = Column(String(200), nullable=True)
    is_recurring = Column(Boolean, default=False)
    recurrence_rule = Column(String(200), nullable=True)  # iCal格式的重复规则
    created_at = Column(DateTime, default=datetime.utcnow)
    
    attendees = relationship("ScheduleAttendee", back_populates="schedule")
    reminders = relationship("ScheduleReminder", back_populates="schedule")

class ScheduleAttendee(Base):
    __tablename__ = "schedule_attendees"
    
    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String(50))  # accepted, declined, tentative
    
    schedule = relationship("Schedule", back_populates="attendees")
    user = relationship("User")

class ScheduleReminder(Base):
    __tablename__ = "schedule_reminders"
    
    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"))
    reminder_time = Column(DateTime)
    is_sent = Column(Boolean, default=False)
    
    schedule = relationship("Schedule", back_populates="reminders")

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    members = relationship("TeamMember", back_populates="team")
    projects = relationship("Project", back_populates="team")

class TeamMember(Base):
    __tablename__ = "team_members"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String(50), default="member")  # owner, admin, member
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships")

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    name = Column(String(100), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="active")  # active, completed, on_hold, cancelled
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    team = relationship("Team", back_populates="projects")
    tasks = relationship("Task", back_populates="project")

class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(100))
    tags = Column(String(500), default="[]")  # JSON string of tags
    version = Column(Integer, default=1)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    revisions = relationship("KnowledgeRevision", back_populates="article")
    comments = relationship("KnowledgeComment", back_populates="article")
    author = relationship("User", back_populates="knowledge_articles")

class KnowledgeRevision(Base):
    __tablename__ = "knowledge_revisions"
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("knowledge_base.id"))
    content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    change_summary = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    article = relationship("KnowledgeBase", back_populates="revisions")
    author = relationship("User", back_populates="knowledge_revisions")

class KnowledgeComment(Base):
    __tablename__ = "knowledge_comments"
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("knowledge_base.id"))
    parent_id = Column(Integer, ForeignKey("knowledge_comments.id"))
    content = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    article = relationship("KnowledgeBase", back_populates="comments")
    author = relationship("User", back_populates="knowledge_comments")
    replies = relationship("KnowledgeComment", backref=backref("parent", remote_side=[id]))

class TeamMetrics(Base):
    __tablename__ = "team_metrics"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    metric_type = Column(String(50))  # performance, activity, collaboration
    metric_data = Column(Text)  # JSON格式存储的指标数据
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    team = relationship("Team", backref="metrics")

class TeamActivity(Base):
    __tablename__ = "team_activities"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    activity_type = Column(String(50))  # task_update, member_join, project_create, etc.
    description = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata = Column(Text)  # JSON格式存储的额外数据
    
    team = relationship("Team", backref="activities")
    creator = relationship("User")

class ProjectMetrics(Base):
    __tablename__ = "project_metrics"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    metric_type = Column(String(50))  # progress, performance, quality
    metric_data = Column(Text)  # JSON格式存储的指标数据
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", backref="metrics")

class TeamCollaboration(Base):
    __tablename__ = "team_collaborations"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    collaboration_type = Column(String(50))  # task_sharing, knowledge_sharing, etc.
    score = Column(Float)  # 协作评分
    details = Column(Text)  # JSON格式存储的详细信息
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    team = relationship("Team", backref="collaborations")
    user = relationship("User")

class PerformanceReview(Base):
    __tablename__ = "performance_reviews"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    review_period_start = Column(DateTime)
    review_period_end = Column(DateTime)
    metrics = Column(Text)  # JSON格式存储的评估指标
    feedback = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    team = relationship("Team")
    user = relationship("User")

class TeamGoal(Base):
    __tablename__ = "team_goals"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    title = Column(String(200), nullable=False)
    description = Column(Text)
    target_value = Column(Float)  # 目标数值
    current_value = Column(Float)  # 当前进度
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    status = Column(String(50), default="active")  # active, completed, cancelled
    priority = Column(Integer, default=1)  # 1-5
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    team = relationship("Team", backref="goals")

class TeamResource(Base):
    __tablename__ = "team_resources"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    name = Column(String(100), nullable=False)
    type = Column(String(50))  # human, equipment, budget, etc.
    capacity = Column(Float)  # 资源容量
    utilized = Column(Float)  # 已使用量
    unit = Column(String(20))  # 单位
    status = Column(String(50), default="available")
    allocation_data = Column(Text)  # JSON格式存储的分配详情
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    team = relationship("Team", backref="resources")

class TeamCapability(Base):
    __tablename__ = "team_capabilities"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    category = Column(String(50))  # technical, business, soft_skills
    name = Column(String(100), nullable=False)
    level = Column(Integer)  # 1-5
    members_data = Column(Text)  # JSON格式存储的成员能力详情
    development_plan = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    team = relationship("Team", backref="capabilities")

class TeamRisk(Base):
    __tablename__ = "team_risks"
    
    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    title = Column(String(200), nullable=False)
    description = Column(Text)
    risk_type = Column(String(50))  # technical, schedule, resource, etc.
    probability = Column(Integer)  # 1-5
    impact = Column(Integer)  # 1-5
    status = Column(String(50), default="active")
    mitigation_plan = Column(Text)
    contingency_plan = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    team = relationship("Team", backref="risks") 