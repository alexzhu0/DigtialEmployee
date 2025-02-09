from typing import List, Dict, Any
from langchain.tools import BaseTool
from app.core.models import User, Conversation, Message, EmotionLog, Task, TaskActivity, WorkStatus, WorkReport, ReportTask, WorkActivity, Schedule, ScheduleAttendee, ScheduleReminder, Team, TeamMember, Project, KnowledgeBase, KnowledgeRevision, KnowledgeComment, TeamActivity, TeamCollaboration, TeamMetrics, PerformanceReview, TeamGoal, TeamResource, TeamCapability, TeamRisk
from sqlalchemy.orm import Session
from datetime import datetime
import json

class EmotionAnalysisTool(BaseTool):
    name = "emotion_analysis"
    description = "分析员工的情绪状态"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, conversation_id: int) -> Dict[str, Any]:
        # 获取对话内容
        messages = (self.db.query(Message)
                   .filter(Message.conversation_id == conversation_id)
                   .order_by(Message.timestamp.desc())
                   .limit(5)
                   .all())
        
        # 分析情绪（这里可以接入更复杂的情绪分析模型）
        emotions = []
        for msg in messages:
            if msg.emotion:
                emotions.append(msg.emotion)
        
        if not emotions:
            return {"emotion": "neutral", "intensity": 0.5}
        
        # 简单的情绪聚合
        return {
            "emotion": max(set(emotions), key=emotions.count),
            "intensity": len(set(emotions)) / len(emotions)
        }

class MemoryRecallTool(BaseTool):
    name = "memory_recall"
    description = "回忆与同事的历史互动"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, user_id: int) -> Dict[str, Any]:
        # 获取用户的历史对话
        conversations = (self.db.query(Conversation)
                        .filter(Conversation.user_id == user_id)
                        .order_by(Conversation.start_time.desc())
                        .limit(10)
                        .all())
        
        memory = {
            "topics": [],
            "emotions": [],
            "preferences": []
        }
        
        for conv in conversations:
            # 获取对话主题和情绪
            messages = (self.db.query(Message)
                       .filter(Message.conversation_id == conv.id)
                       .order_by(Message.timestamp)
                       .all())
            
            for msg in messages:
                if msg.role == "user":
                    memory["topics"].append(msg.content)
                if msg.emotion:
                    memory["emotions"].append(msg.emotion)
        
        return memory

class SafetyCheckTool(BaseTool):
    name = "safety_check"
    description = "检查回复是否适合工作场合"
    
    def _run(self, response: str) -> Dict[str, bool]:
        # 这里可以接入更复杂的内容审核系统
        unsafe_words = [
            "机密", "内幕", "隐私", "竞争对手",
            "违规", "违法", "歧视", "骚扰",
            "个人信息", "密码", "账号", "薪资",
            "辞职", "裁员", "投诉", "举报"
        ]
        
        is_safe = True
        for word in unsafe_words:
            if word in response:
                is_safe = False
                break
        
        return {"is_safe": is_safe}

class EmotionLogTool(BaseTool):
    name = "emotion_log"
    description = "记录用户的情绪变化"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, data: Dict[str, Any]) -> bool:
        try:
            emotion_log = EmotionLog(
                user_id=data["user_id"],
                emotion=data["emotion"],
                intensity=data["intensity"],
                context=data.get("context"),
                timestamp=datetime.utcnow()
            )
            self.db.add(emotion_log)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            return False

class TaskManagementTool(BaseTool):
    name = "task_management"
    description = "管理和追踪工作任务"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        action = data.get("action")
        if action == "create":
            return self._create_task(data)
        elif action == "update":
            return self._update_task(data)
        elif action == "list":
            return self._list_tasks(data)
        return {"error": "Invalid action"}
    
    def _create_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            task = Task(
                user_id=data["user_id"],
                title=data["title"],
                description=data.get("description", ""),
                status="pending",
                priority=data.get("priority", 3),
                due_date=data.get("due_date")
            )
            self.db.add(task)
            
            activity = TaskActivity(
                task=task,
                action="created",
                description="任务已创建"
            )
            self.db.add(activity)
            
            self.db.commit()
            return {"success": True, "task_id": task.id}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _update_task(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            task = self.db.query(Task).get(data["task_id"])
            if not task:
                return {"success": False, "error": "Task not found"}
            
            for key, value in data.items():
                if hasattr(task, key) and key != "id":
                    setattr(task, key, value)
            
            activity = TaskActivity(
                task=task,
                action="updated",
                description=f"任务状态更新为: {data.get('status', task.status)}"
            )
            self.db.add(activity)
            
            self.db.commit()
            return {"success": True}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _list_tasks(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = self.db.query(Task)
            if "user_id" in data:
                query = query.filter(Task.user_id == data["user_id"])
            if "status" in data:
                query = query.filter(Task.status == data["status"])
            
            tasks = query.order_by(Task.priority.desc(), Task.created_at.desc()).all()
            return {
                "success": True,
                "tasks": [
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status,
                        "priority": task.priority,
                        "due_date": task.due_date.isoformat() if task.due_date else None
                    }
                    for task in tasks
                ]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

class WorkStatusTool(BaseTool):
    name = "work_status"
    description = "管理数字员工的工作状态"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 结束当前状态
            current_status = (
                self.db.query(WorkStatus)
                .filter(WorkStatus.end_time.is_(None))
                .first()
            )
            if current_status:
                current_status.end_time = datetime.utcnow()
            
            # 创建新状态
            new_status = WorkStatus(
                status=data["status"],
                description=data.get("description"),
                current_task_id=data.get("task_id")
            )
            self.db.add(new_status)
            self.db.commit()
            
            return {
                "success": True,
                "status": new_status.status,
                "start_time": new_status.start_time.isoformat()
            }
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}

class ReportGenerationTool(BaseTool):
    name = "report_generation"
    description = "生成工作报告"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 获取时间范围内的任务和活动
            start_time = datetime.fromisoformat(data["start_time"])
            end_time = datetime.fromisoformat(data["end_time"])
            
            # 查询任务
            tasks = (
                self.db.query(Task)
                .filter(Task.created_at >= start_time, Task.created_at <= end_time)
                .all()
            )
            
            # 查询工作状态记录
            work_status = (
                self.db.query(WorkStatus)
                .filter(WorkStatus.start_time >= start_time, WorkStatus.start_time <= end_time)
                .all()
            )
            
            # 生成报告内容
            report_content = self._generate_report_content(tasks, work_status)
            metrics = self._calculate_metrics(tasks, work_status)
            
            # 创建报告
            report = WorkReport(
                report_type=data["report_type"],
                start_time=start_time,
                end_time=end_time,
                content=report_content,
                metrics=json.dumps(metrics)
            )
            self.db.add(report)
            
            # 关联任务
            for task in tasks:
                self.db.add(ReportTask(report_id=report.id, task_id=task.id))
            
            # 记录活动
            for status in work_status:
                activity = WorkActivity(
                    report=report,
                    activity_type=status.status,
                    description=status.description,
                    duration=int((status.end_time - status.start_time).total_seconds() / 60)
                    if status.end_time else 0
                )
                self.db.add(activity)
            
            self.db.commit()
            return {
                "success": True,
                "report_id": report.id,
                "content": report_content,
                "metrics": metrics
            }
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _generate_report_content(self, tasks: List[Task], work_status: List[WorkStatus]) -> str:
        # 这里可以实现更复杂的报告生成逻辑
        content = []
        content.append("工作任务完成情况：")
        for task in tasks:
            content.append(f"- {task.title}: {task.status}")
        
        content.append("\n工作时间分配：")
        status_summary = {}
        for status in work_status:
            if status.status not in status_summary:
                status_summary[status.status] = 0
            duration = (status.end_time - status.start_time).total_seconds() / 3600 if status.end_time else 0
            status_summary[status.status] += duration
        
        for status, hours in status_summary.items():
            content.append(f"- {status}: {hours:.1f}小时")
        
        return "\n".join(content)
    
    def _calculate_metrics(self, tasks: List[Task], work_status: List[WorkStatus]) -> Dict[str, Any]:
        return {
            "total_tasks": len(tasks),
            "completed_tasks": len([t for t in tasks if t.status == "completed"]),
            "work_hours": sum(
                (s.end_time - s.start_time).total_seconds() / 3600
                for s in work_status if s.end_time
            )
        }

class ScheduleManagementTool(BaseTool):
    name = "schedule_management"
    description = "管理日程安排"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        action = data.get("action")
        if action == "create":
            return self._create_schedule(data)
        elif action == "update":
            return self._update_schedule(data)
        elif action == "list":
            return self._list_schedules(data)
        elif action == "check_conflicts":
            return self._check_conflicts(data)
        return {"error": "Invalid action"}
    
    def _create_schedule(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            schedule = Schedule(
                title=data["title"],
                event_type=data["event_type"],
                start_time=datetime.fromisoformat(data["start_time"]),
                end_time=datetime.fromisoformat(data["end_time"]),
                description=data.get("description"),
                location=data.get("location"),
                is_recurring=data.get("is_recurring", False),
                recurrence_rule=data.get("recurrence_rule")
            )
            self.db.add(schedule)
            
            # 添加参与者
            for attendee_id in data.get("attendees", []):
                attendee = ScheduleAttendee(
                    schedule=schedule,
                    user_id=attendee_id,
                    status="pending"
                )
                self.db.add(attendee)
            
            # 添加提醒
            for reminder_time in data.get("reminders", []):
                reminder = ScheduleReminder(
                    schedule=schedule,
                    reminder_time=datetime.fromisoformat(reminder_time)
                )
                self.db.add(reminder)
            
            self.db.commit()
            return {"success": True, "schedule_id": schedule.id}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _update_schedule(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            schedule = self.db.query(Schedule).get(data["schedule_id"])
            if not schedule:
                return {"success": False, "error": "Schedule not found"}
            
            for key, value in data.items():
                if hasattr(schedule, key) and key not in ["id", "created_at"]:
                    if key in ["start_time", "end_time"] and isinstance(value, str):
                        value = datetime.fromisoformat(value)
                    setattr(schedule, key, value)
            
            self.db.commit()
            return {"success": True}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _list_schedules(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            start_time = datetime.fromisoformat(data["start_time"])
            end_time = datetime.fromisoformat(data["end_time"])
            
            schedules = (
                self.db.query(Schedule)
                .filter(
                    Schedule.start_time >= start_time,
                    Schedule.start_time <= end_time
                )
                .order_by(Schedule.start_time)
                .all()
            )
            
            return {
                "success": True,
                "schedules": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "event_type": s.event_type,
                        "start_time": s.start_time.isoformat(),
                        "end_time": s.end_time.isoformat(),
                        "location": s.location
                    }
                    for s in schedules
                ]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _check_conflicts(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            start_time = datetime.fromisoformat(data["start_time"])
            end_time = datetime.fromisoformat(data["end_time"])
            
            conflicts = (
                self.db.query(Schedule)
                .filter(
                    Schedule.id != data.get("schedule_id", -1),
                    Schedule.start_time < end_time,
                    Schedule.end_time > start_time
                )
                .all()
            )
            
            return {
                "success": True,
                "has_conflicts": len(conflicts) > 0,
                "conflicts": [
                    {
                        "id": s.id,
                        "title": s.title,
                        "start_time": s.start_time.isoformat(),
                        "end_time": s.end_time.isoformat()
                    }
                    for s in conflicts
                ]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

class TeamManagementTool(BaseTool):
    name = "team_management"
    description = "管理团队和项目"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        action = data.get("action")
        if action == "create_team":
            return self._create_team(data)
        elif action == "add_member":
            return self._add_team_member(data)
        elif action == "create_project":
            return self._create_project(data)
        elif action == "update_project":
            return self._update_project(data)
        return {"error": "Invalid action"}
    
    def _create_team(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            team = Team(
                name=data["name"],
                description=data.get("description")
            )
            self.db.add(team)
            
            # 添加创建者作为团队所有者
            owner = TeamMember(
                team=team,
                user_id=data["creator_id"],
                role="owner"
            )
            self.db.add(owner)
            
            self.db.commit()
            return {"success": True, "team_id": team.id}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _add_team_member(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            member = TeamMember(
                team_id=data["team_id"],
                user_id=data["user_id"],
                role=data.get("role", "member")
            )
            self.db.add(member)
            self.db.commit()
            return {"success": True}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _create_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            project = Project(
                team_id=data["team_id"],
                name=data["name"],
                description=data.get("description"),
                status="active",
                start_date=datetime.fromisoformat(data["start_date"]),
                end_date=datetime.fromisoformat(data["end_date"]) if data.get("end_date") else None
            )
            self.db.add(project)
            self.db.commit()
            return {"success": True, "project_id": project.id}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _update_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            project = self.db.query(Project).get(data["project_id"])
            if not project:
                return {"success": False, "error": "Project not found"}
            
            for key, value in data.items():
                if hasattr(project, key) and key not in ["id", "created_at", "team_id"]:
                    if key == "end_date" and isinstance(value, str):
                        value = datetime.fromisoformat(value)
                    setattr(project, key, value)
            
            self.db.commit()
            return {"success": True}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}

class KnowledgeBaseTool(BaseTool):
    name = "knowledge_base"
    description = "管理知识库文章"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        action = data.get("action")
        if action == "create":
            return self._create_article(data)
        elif action == "update":
            return self._update_article(data)
        elif action == "search":
            return self._search_articles(data)
        elif action == "add_comment":
            return self._add_comment(data)
        return {"error": "Invalid action"}
    
    def _create_article(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            article = KnowledgeBase(
                title=data["title"],
                content=data["content"],
                category=data["category"],
                tags=json.dumps(data.get("tags", [])),
                created_by=data["user_id"]
            )
            self.db.add(article)
            
            # 创建第一个版本
            revision = KnowledgeRevision(
                article=article,
                content=data["content"],
                version=1,
                created_by=data["user_id"],
                change_summary="初始版本"
            )
            self.db.add(revision)
            
            self.db.commit()
            return {"success": True, "article_id": article.id}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _update_article(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            article = self.db.query(KnowledgeBase).get(data["article_id"])
            if not article:
                return {"success": False, "error": "Article not found"}
            
            # 更新文章
            for key, value in data.items():
                if hasattr(article, key) and key not in ["id", "created_at", "created_by", "version"]:
                    if key == "tags" and isinstance(value, list):
                        value = json.dumps(value)
                    setattr(article, key, value)
            
            article.version += 1
            
            # 创建新版本
            revision = KnowledgeRevision(
                article=article,
                content=data["content"],
                version=article.version,
                created_by=data["user_id"],
                change_summary=data.get("change_summary", "更新内容")
            )
            self.db.add(revision)
            
            self.db.commit()
            return {"success": True}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _search_articles(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            query = self.db.query(KnowledgeBase)
            
            if "category" in data:
                query = query.filter(KnowledgeBase.category == data["category"])
            
            if "keyword" in data:
                keyword = f"%{data['keyword']}%"
                query = query.filter(
                    (KnowledgeBase.title.ilike(keyword)) |
                    (KnowledgeBase.content.ilike(keyword))
                )
            
            articles = query.order_by(KnowledgeBase.updated_at.desc()).all()
            
            return {
                "success": True,
                "articles": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "category": a.category,
                        "tags": json.loads(a.tags),
                        "created_at": a.created_at.isoformat(),
                        "updated_at": a.updated_at.isoformat()
                    }
                    for a in articles
                ]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _add_comment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            comment = KnowledgeComment(
                article_id=data["article_id"],
                content=data["content"],
                created_by=data["user_id"],
                parent_id=data.get("parent_id")
            )
            self.db.add(comment)
            self.db.commit()
            return {"success": True, "comment_id": comment.id}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}

class TeamAnalyticsTool(BaseTool):
    name = "team_analytics"
    description = "团队数据分析和统计"
    
    def __init__(self, db: Session):
        super().__init__()
        self.db = db
    
    def _run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        action = data.get("action")
        if action == "calculate_metrics":
            return self._calculate_team_metrics(data)
        elif action == "track_activity":
            return self._track_team_activity(data)
        elif action == "analyze_collaboration":
            return self._analyze_collaboration(data)
        elif action == "generate_review":
            return self._generate_performance_review(data)
        elif action == "manage_goals":
            return self._manage_team_goals(data)
        elif action == "manage_resources":
            return self._manage_team_resources(data)
        elif action == "analyze_capabilities":
            return self._analyze_team_capabilities(data)
        elif action == "assess_risks":
            return self._assess_team_risks(data)
        return {"error": "Invalid action"}
    
    def _calculate_team_metrics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            team_id = data["team_id"]
            start_time = datetime.fromisoformat(data["start_time"])
            end_time = datetime.fromisoformat(data["end_time"])
            
            # 计算任务完成情况
            tasks = (
                self.db.query(Task)
                .join(Project)
                .filter(
                    Project.team_id == team_id,
                    Task.created_at >= start_time,
                    Task.created_at <= end_time
                )
                .all()
            )
            
            task_metrics = {
                "total": len(tasks),
                "completed": len([t for t in tasks if t.status == "completed"]),
                "in_progress": len([t for t in tasks if t.status == "in_progress"]),
                "pending": len([t for t in tasks if t.status == "pending"]),
                "overdue": len([t for t in tasks if t.due_date and t.due_date < datetime.utcnow()])
            }
            
            # 计算项目进度
            projects = (
                self.db.query(Project)
                .filter(Project.team_id == team_id)
                .all()
            )
            
            project_metrics = {
                "total": len(projects),
                "active": len([p for p in projects if p.status == "active"]),
                "completed": len([p for p in projects if p.status == "completed"]),
                "on_hold": len([p for p in projects if p.status == "on_hold"])
            }
            
            # 计算团队活跃度
            activities = (
                self.db.query(TeamActivity)
                .filter(
                    TeamActivity.team_id == team_id,
                    TeamActivity.created_at >= start_time,
                    TeamActivity.created_at <= end_time
                )
                .all()
            )
            
            activity_metrics = {
                "total": len(activities),
                "by_type": {}
            }
            
            for activity in activities:
                if activity.activity_type not in activity_metrics["by_type"]:
                    activity_metrics["by_type"][activity.activity_type] = 0
                activity_metrics["by_type"][activity.activity_type] += 1
            
            # 保存指标
            metrics = TeamMetrics(
                team_id=team_id,
                metric_type="performance",
                metric_data=json.dumps({
                    "tasks": task_metrics,
                    "projects": project_metrics,
                    "activities": activity_metrics
                }),
                start_time=start_time,
                end_time=end_time
            )
            self.db.add(metrics)
            self.db.commit()
            
            return {
                "success": True,
                "metrics": {
                    "tasks": task_metrics,
                    "projects": project_metrics,
                    "activities": activity_metrics
                }
            }
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _track_team_activity(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            activity = TeamActivity(
                team_id=data["team_id"],
                activity_type=data["activity_type"],
                description=data["description"],
                created_by=data["user_id"],
                metadata=json.dumps(data.get("metadata", {}))
            )
            self.db.add(activity)
            self.db.commit()
            return {"success": True, "activity_id": activity.id}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _analyze_collaboration(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 分析团队成员之间的协作情况
            team_id = data["team_id"]
            start_time = datetime.fromisoformat(data["start_time"])
            end_time = datetime.fromisoformat(data["end_time"])
            
            # 获取团队成员
            members = (
                self.db.query(TeamMember)
                .filter(TeamMember.team_id == team_id)
                .all()
            )
            
            collaboration_data = []
            for member in members:
                # 分析任务协作
                tasks_shared = (
                    self.db.query(Task)
                    .join(Project)
                    .filter(
                        Project.team_id == team_id,
                        Task.user_id == member.user_id,
                        Task.created_at >= start_time,
                        Task.created_at <= end_time
                    )
                    .count()
                )
                
                # 分析知识分享
                knowledge_shared = (
                    self.db.query(KnowledgeBase)
                    .filter(
                        KnowledgeBase.created_by == member.user_id,
                        KnowledgeBase.created_at >= start_time,
                        KnowledgeBase.created_at <= end_time
                    )
                    .count()
                )
                
                # 计算协作分数
                collaboration_score = (tasks_shared * 0.6 + knowledge_shared * 0.4) / 10
                
                # 记录协作数据
                collaboration = TeamCollaboration(
                    team_id=team_id,
                    user_id=member.user_id,
                    collaboration_type="overall",
                    score=collaboration_score,
                    details=json.dumps({
                        "tasks_shared": tasks_shared,
                        "knowledge_shared": knowledge_shared
                    })
                )
                self.db.add(collaboration)
                
                collaboration_data.append({
                    "user_id": member.user_id,
                    "score": collaboration_score,
                    "details": {
                        "tasks_shared": tasks_shared,
                        "knowledge_shared": knowledge_shared
                    }
                })
            
            self.db.commit()
            return {
                "success": True,
                "collaborations": collaboration_data
            }
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _generate_performance_review(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 生成团队成员的绩效评估
            team_id = data["team_id"]
            user_id = data["user_id"]
            start_time = datetime.fromisoformat(data["start_time"])
            end_time = datetime.fromisoformat(data["end_time"])
            
            # 获取任务完成情况
            tasks = (
                self.db.query(Task)
                .filter(
                    Task.user_id == user_id,
                    Task.created_at >= start_time,
                    Task.created_at <= end_time
                )
                .all()
            )
            
            task_metrics = {
                "total": len(tasks),
                "completed": len([t for t in tasks if t.status == "completed"]),
                "completion_rate": len([t for t in tasks if t.status == "completed"]) / len(tasks) if tasks else 0,
                "on_time": len([t for t in tasks if t.status == "completed" and (not t.due_date or t.updated_at <= t.due_date)])
            }
            
            # 获取协作情况
            collaborations = (
                self.db.query(TeamCollaboration)
                .filter(
                    TeamCollaboration.team_id == team_id,
                    TeamCollaboration.user_id == user_id,
                    TeamCollaboration.timestamp >= start_time,
                    TeamCollaboration.timestamp <= end_time
                )
                .all()
            )
            
            collaboration_score = sum(c.score for c in collaborations) / len(collaborations) if collaborations else 0
            
            # 生成评估报告
            review = PerformanceReview(
                team_id=team_id,
                user_id=user_id,
                review_period_start=start_time,
                review_period_end=end_time,
                metrics=json.dumps({
                    "tasks": task_metrics,
                    "collaboration": {
                        "score": collaboration_score,
                        "total_collaborations": len(collaborations)
                    }
                }),
                feedback=self._generate_feedback(task_metrics, collaboration_score)
            )
            self.db.add(review)
            self.db.commit()
            
            return {
                "success": True,
                "review_id": review.id,
                "metrics": {
                    "tasks": task_metrics,
                    "collaboration": {
                        "score": collaboration_score,
                        "total_collaborations": len(collaborations)
                    }
                }
            }
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _generate_feedback(self, task_metrics: Dict[str, Any], collaboration_score: float) -> str:
        feedback = []
        
        # 任务完成情况反馈
        if task_metrics["completion_rate"] >= 0.8:
            feedback.append("任务完成情况非常出色，保持良好的工作效率。")
        elif task_metrics["completion_rate"] >= 0.6:
            feedback.append("任务完成情况良好，但仍有提升空间。")
        else:
            feedback.append("需要提高任务完成率，建议合理规划时间和优先级。")
        
        # 准时完成情况反馈
        on_time_rate = task_metrics["on_time"] / task_metrics["completed"] if task_metrics["completed"] > 0 else 0
        if on_time_rate >= 0.9:
            feedback.append("工作计划性强，任务都能按时完成。")
        elif on_time_rate >= 0.7:
            feedback.append("大部分任务能按时完成，建议进一步提高时间管理能力。")
        else:
            feedback.append("需要加强时间管理，确保任务按期完成。")
        
        # 协作情况反馈
        if collaboration_score >= 8:
            feedback.append("团队协作能力突出，是团队重要的贡献者。")
        elif collaboration_score >= 6:
            feedback.append("能够积极参与团队协作，建议进一步加强知识分享。")
        else:
            feedback.append("建议增加与团队成员的互动和协作。")
        
        return "\n".join(feedback)
    
    def _manage_team_goals(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = data.get("sub_action")
            if action == "create":
                goal = TeamGoal(
                    team_id=data["team_id"],
                    title=data["title"],
                    description=data.get("description"),
                    target_value=data.get("target_value"),
                    current_value=0,
                    start_date=datetime.fromisoformat(data["start_date"]),
                    end_date=datetime.fromisoformat(data["end_date"]) if data.get("end_date") else None,
                    priority=data.get("priority", 1)
                )
                self.db.add(goal)
                self.db.commit()
                return {"success": True, "goal_id": goal.id}
            
            elif action == "update":
                goal = self.db.query(TeamGoal).get(data["goal_id"])
                if not goal:
                    return {"success": False, "error": "Goal not found"}
                
                for key, value in data.items():
                    if hasattr(goal, key) and key not in ["id", "created_at", "team_id"]:
                        setattr(goal, key, value)
                
                self.db.commit()
                return {"success": True}
            
            elif action == "list":
                goals = (
                    self.db.query(TeamGoal)
                    .filter(TeamGoal.team_id == data["team_id"])
                    .order_by(TeamGoal.priority.desc(), TeamGoal.created_at.desc())
                    .all()
                )
                return {
                    "success": True,
                    "goals": [
                        {
                            "id": g.id,
                            "title": g.title,
                            "current_value": g.current_value,
                            "target_value": g.target_value,
                            "status": g.status,
                            "priority": g.priority
                        }
                        for g in goals
                    ]
                }
            
            return {"success": False, "error": "Invalid sub_action"}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _manage_team_resources(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = data.get("sub_action")
            if action == "create":
                resource = TeamResource(
                    team_id=data["team_id"],
                    name=data["name"],
                    type=data["type"],
                    capacity=data["capacity"],
                    utilized=0,
                    unit=data["unit"],
                    allocation_data=json.dumps([])
                )
                self.db.add(resource)
                self.db.commit()
                return {"success": True, "resource_id": resource.id}
            
            elif action == "update":
                resource = self.db.query(TeamResource).get(data["resource_id"])
                if not resource:
                    return {"success": False, "error": "Resource not found"}
                
                for key, value in data.items():
                    if hasattr(resource, key) and key not in ["id", "created_at", "team_id"]:
                        if key == "allocation_data" and isinstance(value, list):
                            value = json.dumps(value)
                        setattr(resource, key, value)
                
                self.db.commit()
                return {"success": True}
            
            elif action == "list":
                resources = (
                    self.db.query(TeamResource)
                    .filter(TeamResource.team_id == data["team_id"])
                    .all()
                )
                return {
                    "success": True,
                    "resources": [
                        {
                            "id": r.id,
                            "name": r.name,
                            "type": r.type,
                            "capacity": r.capacity,
                            "utilized": r.utilized,
                            "unit": r.unit,
                            "status": r.status,
                            "allocation_data": json.loads(r.allocation_data)
                        }
                        for r in resources
                    ]
                }
            
            return {"success": False, "error": "Invalid sub_action"}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _analyze_team_capabilities(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = data.get("sub_action")
            if action == "update":
                capability = (
                    self.db.query(TeamCapability)
                    .filter(
                        TeamCapability.team_id == data["team_id"],
                        TeamCapability.category == data["category"],
                        TeamCapability.name == data["name"]
                    )
                    .first()
                )
                
                if not capability:
                    capability = TeamCapability(
                        team_id=data["team_id"],
                        category=data["category"],
                        name=data["name"]
                    )
                    self.db.add(capability)
                
                capability.level = data["level"]
                capability.members_data = json.dumps(data["members_data"])
                capability.development_plan = data.get("development_plan")
                
                self.db.commit()
                return {"success": True, "capability_id": capability.id}
            
            elif action == "analyze":
                capabilities = (
                    self.db.query(TeamCapability)
                    .filter(TeamCapability.team_id == data["team_id"])
                    .all()
                )
                
                analysis = {
                    "technical": [],
                    "business": [],
                    "soft_skills": []
                }
                
                for cap in capabilities:
                    analysis[cap.category].append({
                        "name": cap.name,
                        "level": cap.level,
                        "members": json.loads(cap.members_data),
                        "development_plan": cap.development_plan
                    })
                
                return {
                    "success": True,
                    "analysis": analysis
                }
            
            return {"success": False, "error": "Invalid sub_action"}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)}
    
    def _assess_team_risks(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = data.get("sub_action")
            if action == "create":
                risk = TeamRisk(
                    team_id=data["team_id"],
                    title=data["title"],
                    description=data["description"],
                    risk_type=data["risk_type"],
                    probability=data["probability"],
                    impact=data["impact"],
                    mitigation_plan=data.get("mitigation_plan"),
                    contingency_plan=data.get("contingency_plan")
                )
                self.db.add(risk)
                self.db.commit()
                return {"success": True, "risk_id": risk.id}
            
            elif action == "update":
                risk = self.db.query(TeamRisk).get(data["risk_id"])
                if not risk:
                    return {"success": False, "error": "Risk not found"}
                
                for key, value in data.items():
                    if hasattr(risk, key) and key not in ["id", "created_at", "team_id"]:
                        setattr(risk, key, value)
                
                self.db.commit()
                return {"success": True}
            
            elif action == "analyze":
                risks = (
                    self.db.query(TeamRisk)
                    .filter(TeamRisk.team_id == data["team_id"])
                    .all()
                )
                
                risk_analysis = {
                    "high_risks": [],
                    "medium_risks": [],
                    "low_risks": []
                }
                
                for risk in risks:
                    risk_score = risk.probability * risk.impact
                    risk_data = {
                        "id": risk.id,
                        "title": risk.title,
                        "type": risk.risk_type,
                        "probability": risk.probability,
                        "impact": risk.impact,
                        "score": risk_score,
                        "status": risk.status
                    }
                    
                    if risk_score >= 16:
                        risk_analysis["high_risks"].append(risk_data)
                    elif risk_score >= 8:
                        risk_analysis["medium_risks"].append(risk_data)
                    else:
                        risk_analysis["low_risks"].append(risk_data)
                
                return {
                    "success": True,
                    "analysis": risk_analysis
                }
            
            return {"success": False, "error": "Invalid sub_action"}
        except Exception as e:
            self.db.rollback()
            return {"success": False, "error": str(e)} 