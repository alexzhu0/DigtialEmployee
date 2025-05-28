from pydantic import BaseModel, Field, EmailStr, HttpUrl, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date

class BaseResponse(BaseModel):
    message: Optional[str] = None

# User Schemas (example, if needed for responses or specific inputs not covered by User model)
class UserDisplay(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool

    class Config:
        orm_mode = True

# Task Schemas
class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Title of the task")
    description: Optional[str] = Field(None, description="Detailed description of the task")
    status: Optional[str] = Field("pending", max_length=50, pattern=r"^(pending|in_progress|completed|cancelled)$", description="Status of the task")
    priority: Optional[int] = Field(1, ge=1, le=5, description="Priority of the task (1-5)")
    due_date: Optional[datetime] = Field(None, description="Due date for the task")
    project_id: Optional[int] = Field(None, gt=0, description="Associated project ID, if any")

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel): # Using BaseModel directly for full optionality
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="Title of the task")
    description: Optional[str] = Field(None, description="Detailed description of the task")
    status: Optional[str] = Field(None, max_length=50, pattern=r"^(pending|in_progress|completed|cancelled)$", description="Status of the task")
    priority: Optional[int] = Field(None, ge=1, le=5, description="Priority of the task (1-5)")
    due_date: Optional[datetime] = Field(None, description="Due date for the task")
    project_id: Optional[int] = Field(None, gt=0, description="Associated project ID, if any")


class TaskResponse(TaskBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

# Work Status Schemas
class WorkStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(available|busy|in_meeting|break|offline)$", description="New work status")
    description: Optional[str] = Field(None, max_length=500, description="Optional description for the status")
    current_task_id: Optional[int] = Field(None, gt=0, description="ID of the current task, if any")

# Report Schemas
class ReportGenerate(BaseModel):
    report_type: str = Field(..., pattern=r"^(daily|weekly|monthly)$", description="Type of report")
    start_time: datetime = Field(..., description="Start time for the report period")
    end_time: datetime = Field(..., description="End time for the report period")
    # content: Optional[str] = None # Agent will generate this
    # metrics: Optional[Dict[str, Any]] = None # Agent will generate this

    @field_validator('end_time')
    def end_time_must_be_after_start_time(cls, v, values):
        if 'start_time' in values.data and v <= values.data['start_time']:
            raise ValueError('End time must be after start time')
        return v

# Schedule Schemas
class ScheduleBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Title of the schedule/event")
    event_type: str = Field(..., max_length=50, description="Type of event (e.g., meeting, task, break)")
    start_time: datetime = Field(..., description="Start time of the event")
    end_time: datetime = Field(..., description="End time of the event")
    description: Optional[str] = Field(None, description="Optional description for the event")
    location: Optional[str] = Field(None, max_length=200, description="Location of the event, if any")
    is_recurring: Optional[bool] = Field(False, description="Is the event recurring?")
    recurrence_rule: Optional[str] = Field(None, max_length=200, description="iCal format recurrence rule, if recurring")

    @field_validator('end_time')
    def schedule_end_time_must_be_after_start_time(cls, v, values):
        if 'start_time' in values.data and v <= values.data['start_time']:
            raise ValueError('End time must be after start time')
        return v

class ScheduleCreate(ScheduleBase):
    attendee_user_ids: Optional[List[int]] = Field(None, description="List of user IDs to attend the event")

class ScheduleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    event_type: Optional[str] = Field(None, max_length=50)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = Field(None, max_length=200)
    is_recurring: Optional[bool] = None
    recurrence_rule: Optional[str] = Field(None, max_length=200)
    attendee_user_ids: Optional[List[int]] = None

    @field_validator('end_time')
    def schedule_update_end_time_must_be_after_start_time(cls, v, values):
        # This validator needs to be careful if start_time is not being updated
        # For simplicity, if end_time is provided, start_time should also be considered or fetched.
        # This might require more complex validation logic depending on how partial updates are handled.
        if v and 'start_time' in values.data and values.data['start_time'] and v <= values.data['start_time']:
            raise ValueError('End time must be after start time')
        return v

class ScheduleConflictCheck(BaseModel):
    start_time: datetime
    end_time: datetime
    user_ids: List[int] = Field(..., min_items=1)
    schedule_id_to_exclude: Optional[int] = None # For checking conflicts when updating an existing schedule

# Team Management Schemas
class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name of the team")
    description: Optional[str] = Field(None, description="Optional description for the team")

class TeamMemberAdd(BaseModel):
    user_id: int = Field(..., gt=0, description="User ID of the member to add")
    role: Optional[str] = Field("member", pattern=r"^(owner|admin|member)$", description="Role of the member in the team")

class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name of the project")
    description: Optional[str] = Field(None, description="Optional description for the project")
    status: Optional[str] = Field("active", pattern=r"^(active|completed|on_hold|cancelled)$", description="Status of the project")
    start_date: date = Field(..., description="Start date of the project")
    end_date: Optional[date] = Field(None, description="End date of the project, if any")

    @field_validator('end_date')
    def project_end_date_must_be_after_start_date(cls, v, values):
        if v and 'start_date' in values.data and v < values.data['start_date']:
            raise ValueError('End date must be on or after start date')
        return v

class ProjectCreate(ProjectBase):
    team_id: int = Field(..., gt=0, description="Team ID to associate the project with")

class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(active|completed|on_hold|cancelled)$")
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @field_validator('end_date')
    def project_update_end_date_must_be_after_start_date(cls, v, values):
        # Similar to schedule update, needs care for partial updates
        if v and 'start_date' in values.data and values.data['start_date'] and v < values.data['start_date']:
            raise ValueError('End date must be on or after start date')
        return v


# Knowledge Base Schemas
class ArticleBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200, description="Title of the knowledge base article")
    content: str = Field(..., min_length=10, description="Content of the article")
    category: Optional[str] = Field(None, max_length=100, description="Category of the article")
    tags: Optional[List[str]] = Field(None, description="List of tags for the article")

class ArticleCreate(ArticleBase):
    created_by: int = Field(..., gt=0, description="User ID of the author") # Should be set from current_user

class ArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    content: Optional[str] = Field(None, min_length=10)
    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = None

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, description="Content of the comment")
    parent_id: Optional[int] = Field(None, gt=0, description="ID of the parent comment, if replying")
    created_by: int = Field(..., gt=0, description="User ID of the commenter") # Should be set from current_user

# Team Analytics Schemas
class TeamMetricsCalculate(BaseModel):
    metric_type: str = Field(..., pattern=r"^(performance|activity|collaboration)$", description="Type of metric to calculate")
    start_time: datetime
    end_time: datetime
    # specific filters can be added, e.g., user_ids: Optional[List[int]] = None

class TeamActivityTrack(BaseModel):
    activity_type: str = Field(..., max_length=50, description="Type of activity, e.g., task_update")
    description: str = Field(..., description="Description of the activity")
    # created_by: int # will be from current_user
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata for the activity")

class TeamCollaborationAnalyze(BaseModel):
    # Define fields specific to collaboration analysis if any, e.g., time_period
    start_time: datetime
    end_time: datetime
    user_ids: Optional[List[int]] = None

class PerformanceReviewGenerate(BaseModel):
    review_period_start: date
    review_period_end: date
    # metrics_to_include: Optional[List[str]] = None
    # user_id is a path param

class TeamGoalBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = Field(0.0)
    start_date: date
    end_date: Optional[date] = None
    status: Optional[str] = Field("active", pattern=r"^(active|completed|cancelled|on_hold)$")
    priority: Optional[int] = Field(1, ge=1, le=5)

    @field_validator('end_date')
    def goal_end_date_must_be_after_start_date(cls, v, values):
        if v and 'start_date' in values.data and v < values.data['start_date']:
            raise ValueError('End date must be on or after start date')
        return v

class TeamGoalCreate(TeamGoalBase):
    pass

class TeamGoalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = Field(None, pattern=r"^(active|completed|cancelled|on_hold)$")
    priority: Optional[int] = Field(None, ge=1, le=5)

    @field_validator('end_date')
    def goal_update_end_date_must_be_after_start_date(cls, v, values):
        if v and 'start_date' in values.data and values.data['start_date'] and v < values.data['start_date']:
            raise ValueError('End date must be on or after start date')
        return v

class TeamResourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., max_length=50, description="Type of resource, e.g., human, equipment, budget")
    capacity: Optional[float] = Field(None, ge=0)
    utilized: Optional[float] = Field(0.0, ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field("available", pattern=r"^(available|allocated|unavailable)$")
    allocation_data: Optional[Dict[str, Any]] = None

class TeamResourceCreate(TeamResourceBase):
    pass

class TeamResourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[str] = Field(None, max_length=50)
    capacity: Optional[float] = Field(None, ge=0)
    utilized: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, pattern=r"^(available|allocated|unavailable)$")
    allocation_data: Optional[Dict[str, Any]] = None

class TeamCapabilityUpdate(BaseModel): # This was a PUT
    category: str = Field(..., max_length=50, description="Capability category, e.g., technical, business")
    name: str = Field(..., max_length=100, description="Name of the capability")
    level: int = Field(..., ge=1, le=5, description="Capability level (1-5)")
    members_data: Optional[Dict[str, Any]] = Field(None, description="JSON data about member capabilities") # UserID to level mapping?
    development_plan: Optional[str] = None

class TeamRiskBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    risk_type: str = Field(..., max_length=50, description="Type of risk, e.g., technical, schedule")
    probability: int = Field(..., ge=1, le=5, description="Probability of risk (1-5)")
    impact: int = Field(..., ge=1, le=5, description="Impact of risk (1-5)")
    status: Optional[str] = Field("active", pattern=r"^(active|mitigated|avoided|transferred|accepted)$")
    mitigation_plan: Optional[str] = None
    contingency_plan: Optional[str] = None

class TeamRiskCreate(TeamRiskBase):
    pass

class TeamRiskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    risk_type: Optional[str] = Field(None, max_length=50)
    probability: Optional[int] = Field(None, ge=1, le=5)
    impact: Optional[int] = Field(None, ge=1, le=5)
    status: Optional[str] = Field(None, pattern=r"^(active|mitigated|avoided|transferred|accepted)$")
    mitigation_plan: Optional[str] = None
    contingency_plan: Optional[str] = None

# General purpose ID validation model if needed for some agent actions
class ItemId(BaseModel):
    id: int = Field(..., gt=0)

class GeneralTextPayload(BaseModel):
    text: str = Field(..., min_length=1)

class UserInteraction(BaseModel):
    user_id: int = Field(..., gt=0)
    text: str = Field(..., min_length=1)

class FilePath(BaseModel):
    file_path: str = Field(..., min_length=1)
