from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from enum import Enum
from flask_login import UserMixin
from app.utils.db import db
from sqlalchemy.dialects.mysql import ENUM as MySQLEnum
from sqlalchemy import desc, Enum as SQLAlchemyEnum, Enum as SqlEnum, JSON
from calendar import month_abbr
from decimal import Decimal
from sqlalchemy.orm import class_mapper

class ApplicationStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    CALLED_FOR_INTERVIEW = "called_for_interview"

class OpportunityType(Enum):
    INTERNAL = "internal"  # Jobs at 3A CPA LLP
    EXTERNAL = "external"  # Jobs at client businesses

class OpportunityStatus(Enum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"

# Question type enum
class QuestionType(Enum):
    open_ended = "open_ended"
    multiple_choice = "multiple_choice"
    personality_test = "personality_test"

class StageType(Enum):
    technical_test = "technical_test"
    personality_test = "personality_test"
    physical_interview = "physical_interview"

# Association table for linking Stages and Questions
stage_questions_association_table = db.Table(
    'stage_questions_association',
    db.Column('stage_id', db.Integer, db.ForeignKey('stages.id'), primary_key=True),
    db.Column('question_id', db.Integer, db.ForeignKey('questions.id'), primary_key=True)
)
# Grade enum (optional, can be generated dynamically too)
class Grade(Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"

class PriorityEnum(Enum):
    LOW = 'Low'
    MEDIUM = 'Medium'
    HIGH = 'High'      
    URGENT = 'Urgent'

class LogStatusEnum(Enum):
    STARTED = 'started'
    PAUSED = 'paused'
    COMPLETED = 'completed'
                                                                            
class RoleEnum(Enum):
    OFFICER = 'officer' #employee
    SUPERVISOR = 'supervisor' #manager
    DIRECTOR = 'director' #director
    INTERN = 'intern' #intern
    ADMIN = 'admin' #admin
    INTERVIEWEE = 'interviewee'
    INTERVIEWER = 'interviewer'
    APPLICANT = 'applicant'

class TaskStatusEnum(Enum):
    ASSIGNED = "Assigned"
    RE_ASSIGNED = "Re assigned"
    IN_PROGRESS = "In Progress"
    PAUSED = "Paused"           
    SUBMITTED = "submited"
    REVIEW = "Under Review"
    MANAGER_REVIEW = "Manager Review"
    PARTNER_REVIEW = "Partner Review"
    COMPLETED = "Completed"

class DecisionEnum(Enum):
    APPROVED = 'approved'
    REDO = 'redo'

class RecurrenceEnum(Enum):
    NONE = "none"  
    
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    
department_reviewers = db.Table('department_reviewers',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('department_id', db.Integer, db.ForeignKey('departments.id'), primary_key=True)
)

# This table links Jobs (Engagements) to Services in a Many-to-Many relationship
job_services = db.Table('job_services',
    db.Column('job_id', db.Integer, db.ForeignKey('jobs.id'), primary_key=True),
    db.Column('service_id', db.Integer, db.ForeignKey('services.id'), primary_key=True)
)

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


        # --- FIX 1: Specify foreign_keys for the 'users' relationship ---
    users = db.relationship('User', backref='department', lazy=True,
                            foreign_keys='User.department_id')


    # --- ADDED Soft Delete ---
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='deleted_departments')
    # --- END ---

    # --- ADD THIS NEW RELATIONSHIP ---
    # This links the Department model to the User model via our new association table
    reviewers = db.relationship('User', secondary=department_reviewers, lazy='subquery',
                                backref=db.backref('reviewing_departments', lazy=True))


    __table_args__= (
        # Index for soft delete queries
        db.Index('idx_departments_deleted', 'deleted_at'),
        # Index for name lookups (already unique, but helps with LIKE queries)
        db.Index('idx_departments_name', 'name')
    )

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='OFFICER')
    phone_number = db.Column(db.String(15), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    profile_image_file = db.Column(db.String(255), nullable=False, default='default.png')
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    secondary_roles = db.Column(JSON, nullable=True, default=list)

    def generate_reset_token(self):
        """Generate a secure password reset token."""
        import secrets
        return secrets.token_urlsafe(32)

    # --- FIX 2 & 3: Specify foreign_keys for task relationships ---
    # These relationships look from User -> Task using Task's FKs
    assigned_tasks = db.relationship('Task', backref='assignee', lazy=True,
                                     foreign_keys='Task.assigned_to_id')
    created_tasks = db.relationship('Task', backref='creator', lazy=True,
                                    foreign_keys='Task.created_by_id')


    # --- Soft Delete ---
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # --- THIS IS THE FIX ---
    deleted_by = db.relationship(
        'User', 
        foreign_keys=[deleted_by_id], 
        backref='deleted_users',  # <-- 1. Renamed from 'deleted_tasks' to be unique
        remote_side=[id]         # <-- 2. Added remote_side to fix self-referential join
    )

    # Relationships
    biodata_entries = db.relationship("Biodata", back_populates="user", uselist=False)
    comments_made = db.relationship("Comment", foreign_keys="Comment.interviewer_id", back_populates="interviewer")
    candidate_stages = db.relationship("CandidateStage", back_populates="user")
    assessment_results = db.relationship("AssessmentResult", back_populates="user")


    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name} {self.middle_name}"
    
    def has_role(self, role):
        """Check if user has a specific role (primary or secondary)"""
        if isinstance(role, RoleEnum):
            role = role.value
        return self.role == role or (self.secondary_roles and role in self.secondary_roles)
    
    def add_secondary_role(self, role):
        """Add a secondary role to user"""
        if isinstance(role, RoleEnum):
            role = role.value
            
        if not self.secondary_roles:
            self.secondary_roles = []
            
        if role not in self.secondary_roles and role != self.role:
            self.secondary_roles.append(role)
    
    def remove_secondary_role(self, role):
        """Remove a secondary role from user"""
        if isinstance(role, RoleEnum):
            role = role.value
            
        if self.secondary_roles and role in self.secondary_roles:
            self.secondary_roles.remove(role)
    
    def get_all_roles(self):
        """Get all roles (primary + secondary)"""
        roles = [self.role]
        if self.secondary_roles:
            roles.extend(self.secondary_roles)
        return list(set(roles))  # Remove duplicates

        # Indexes using `__table_args__`
    __table_args__ = (
        # Composite index for department + soft delete (common in dashboards)
        db.Index('idx_users_department_deleted', 'department_id', 'deleted_at'),
        
        # Index for role-based queries
        db.Index('idx_users_role', 'role'),
        
        # Index for email lookups (already unique, but helps with partial searches)
        db.Index('idx_users_email', 'email'),
        
        # Index for name searches
        db.Index('idx_users_name', 'first_name', 'last_name'),
        
        # Index for reset token lookups
        db.Index('idx_users_reset_token', 'reset_token'),
        
        # --- Additional indexes from earlier ---
        # Index on `department_id` (for queries filtering by department)
        db.Index('idx_user_department_id', 'department_id'),

        # Index on `deleted_by_id` (for tracking who deleted a user)
        db.Index('idx_user_deleted_by_id', 'deleted_by_id'),

        # Index on `reset_token` (for password reset functionality)
        db.Index('idx_user_reset_token', 'reset_token'),

        # Index on `deleted_at` (for soft delete queries, like fetching active users)
        db.Index('idx_user_deleted_at', 'deleted_at')
    )

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    status = db.Column(db.Enum(TaskStatusEnum), default=TaskStatusEnum.ASSIGNED, nullable=False)
    recurrence = db.Column(db.Enum(RecurrenceEnum), default=RecurrenceEnum.NONE, nullable=False)
    
    deadline = db.Column(db.DateTime, nullable=True)
    estimated_minutes = db.Column(db.Integer, nullable=True)  # e.g., 120 for 2 hours
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    priority = db.Column(db.Enum(PriorityEnum), default=PriorityEnum.MEDIUM, nullable=False)


    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id])
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    task_template_id = db.Column(db.Integer, db.ForeignKey('task_templates.id'), nullable=True)
    task_template = db.relationship('TaskTemplate', foreign_keys=[task_template_id])

    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=True)

    logs = db.relationship('TaskLog', backref='task', lazy=True, cascade="all, delete-orphan")
    approvals = db.relationship('TaskApproval', backref='task', lazy=True, cascade="all, delete-orphan")
    requires_vat_form = db.Column(db.Boolean, default=False)

    # --- Soft Delete ---
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # --- FIX 4: Define deleted_by relationship explicitly ---
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='deleted_tasks')


    @property
    def last_completed_time(self):
        log = (
            TaskLog.query
            .filter_by(task_id=self.id, status=LogStatusEnum.COMPLETED)
            .order_by(desc(TaskLog.end_time))
            .first()
        )
        return log.end_time if log else None
    
    __table_args__ = (
        # MOST IMPORTANT: Composite index for assigned tasks queries (from get_assigned_tasks)
        db.Index('idx_tasks_assigned_status_deleted', 'assigned_to_id', 'status', 'deleted_at'),
        
        # Index for deadline-based queries (overdue tasks)
        db.Index('idx_tasks_deadline_status', 'deadline', 'status'),
        
        # Index for job-related queries
        db.Index('idx_tasks_job_deleted', 'job_id', 'deleted_at'),
        
        # Index for creator queries
        db.Index('idx_tasks_creator_deleted', 'created_by_id', 'deleted_at'),
        
        # Index for client queries
        db.Index('idx_tasks_client_deleted', 'client_id', 'deleted_at'),
        
        # Index for template queries
        db.Index('idx_tasks_template', 'task_template_id'),
        
        # Index for updated_at ordering (dashboard queries)
        db.Index('idx_tasks_updated_at', 'updated_at'),
        
        # Index for created_at ordering
        db.Index('idx_tasks_created_at', 'created_at'),
        
        # Index for priority queries
        db.Index('idx_tasks_priority', 'priority'),
        
        # Index for VAT form queries
        db.Index('idx_tasks_vat_form', 'requires_vat_form'),
        
        # Composite index for dashboard review queries
        db.Index('idx_tasks_review_status_updated', 'status', 'updated_at', 'deleted_at'),
        
        # Composite index for recurrence queries
        db.Index('idx_tasks_recurrence_deadline', 'recurrence', 'deadline', 'deleted_at'),
    )

class TaskLog(db.Model):
    __tablename__ = 'task_logs'
    id = db.Column(db.Integer, primary_key=True)
    
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    
    status = db.Column(db.Enum(LogStatusEnum), default=LogStatusEnum.STARTED, nullable=False)
    notes = db.Column(db.Text)

    vat_month_id = db.Column(db.Integer, db.ForeignKey('vat_filing_months.id'), nullable=True)
    vat_month = db.relationship('VatFilingMonth', backref='logs')


    user = db.relationship('User', backref='task_logs', foreign_keys=[user_id])

    def start_task(self):
        self.status = LogStatusEnum.STARTED
        self.start_time = datetime.utcnow()
    
    def pause_task(self):
        self.status = LogStatusEnum.PAUSED
        self.end_time = datetime.utcnow()
    
    def complete_task(self):
        self.status = LogStatusEnum.COMPLETED
        self.end_time = datetime.utcnow()

    __table_args__ = (
        # Composite index for task+user queries (from get_task route)
        db.Index('idx_task_logs_task_user', 'task_id', 'user_id'),
        
        # Index for task-specific queries
        db.Index('idx_task_logs_task', 'task_id'),
        
        # Index for user-specific queries
        db.Index('idx_task_logs_user', 'user_id'),
        
        # Index for time-based queries (ordering by start_time)
        db.Index('idx_task_logs_start_time', 'start_time'),
        
        # Index for status queries
        db.Index('idx_task_logs_status', 'status'),
        
        # Index for VAT month queries
        db.Index('idx_task_logs_vat_month', 'vat_month_id'),
        
        # Composite index for task completion queries
        db.Index('idx_task_logs_task_status_time', 'task_id', 'status', 'start_time'),
    )

class TaskApproval(db.Model):
    __tablename__ = 'task_approvals'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    decision = db.Column(db.Enum(DecisionEnum), nullable=False)
    remarks = db.Column(db.Text)

    approver = db.relationship('User', backref='task_approvals', foreign_keys=[approved_by_id])
    
    __table_args__ = (
        # Index for task approval lookups
        db.Index('idx_task_approvals_task', 'task_id'),
        
        # Index for approver queries
        db.Index('idx_task_approvals_approver', 'approved_by_id'),
        
        # Composite index for task+decision queries
        db.Index('idx_task_approvals_task_decision', 'task_id', 'decision'),
        
        # Index for decision queries
        db.Index('idx_task_approvals_decision', 'decision'),
    )

class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    contact_email = db.Column(db.String(120), nullable=True, unique=True)
    phone_number = db.Column(db.String(15), nullable=True)

    tasks = db.relationship('Task', backref='client', lazy=True)

    # --- ADDED Soft Delete ---
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='deleted_clients')

    # --- END ---
    __table_args__ = (
        # Index for name searches (autocomplete/search_clients route)
        db.Index('idx_clients_name', 'name'),
        
        # Index for email searches
        db.Index('idx_clients_email', 'contact_email'),
        
        # Index for soft delete
        db.Index('idx_clients_deleted', 'deleted_at'),
    )

class Service(db.Model):
    __tablename__ = 'services'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)


    # --- ADDED Soft Delete ---
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='deleted_services')
    # --- END ---

    # Relationship to templates
    task_templates = db.relationship('TaskTemplate', backref='service', lazy=True, cascade="all, delete-orphan",
                                     foreign_keys='TaskTemplate.service_id')
    
    __table_args__ = (
        # Index for name searches
        db.Index('idx_services_name', 'name'),
        
        # Index for soft delete
        db.Index('idx_services_deleted', 'deleted_at'),
    )

class TaskTemplate(db.Model):
    __tablename__ = 'task_templates'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)

    
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)

    # --- ADDED Soft Delete ---
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='deleted_templates')
    # --- END ---

    # Optionally preload default deadline span (e.g., 7 days after assignment)
    default_deadline_days = db.Column(db.Integer, nullable=True)
    tasks = db.relationship('Task', backref='template', lazy=True)

    __table_args__ = (
        # Index for service queries (create_task route)
        db.Index('idx_task_templates_service', 'service_id'),
        
        # Index for title searches
        db.Index('idx_task_templates_title', 'title'),
        
        # Index for soft delete
        db.Index('idx_task_templates_deleted', 'deleted_at'),
    )

class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    review_partner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


    # --- ADDED Soft Delete ---
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='deleted_jobs')
    # --- END ---

    # --- Relationships ---
    review_partner = db.relationship('User', foreign_keys=[review_partner_id], backref='review_jobs')
    client = db.relationship('Client', backref='jobs')

    services = db.relationship('Service', secondary=job_services, lazy='subquery', backref=db.backref('jobs', lazy=True))
    creator = db.relationship('User', foreign_keys=[created_by_id], backref='created_jobs')
    
    tasks = db.relationship(
        'Task',
        backref='job',
        lazy='select',
        cascade='all, delete-orphan'
    )

    # --- FINALIZED RELATIONSHIPS ---
    vat_filing_months = db.relationship('VatFilingMonth', back_populates='job', cascade='all, delete-orphan', passive_deletes=True)
    banking_summaries = db.relationship('BankingCreditSummary', back_populates='job', cascade='all, delete-orphan')
    salary_summaries = db.relationship('GrossSalarySummary', back_populates='job', cascade='all, delete-orphan')
    installment_tax_summary = db.relationship('InstallmentTaxSummary', back_populates='job', uselist=False, cascade='all, delete-orphan')
    tax_liabilities = db.relationship('TaxLiabilitySummary', back_populates='job', cascade='all, delete-orphan')
    vat_summaries = db.relationship('VatMonthlySummary', back_populates='job', cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        """
        Custom initializer to auto-populate job-level summary tables for a new Job.
        """
        super(Job, self).__init__(**kwargs)
        if not self.id:
            # Logic from first (overwritten) __init__
            current_year = datetime.utcnow().year
            months_with_year = [f"{month_abbr[i]}-{current_year}" for i in range(1, 13)]
            self.vat_summaries = [VatMonthlySummary(month=m) for m in months_with_year]

            # Logic from second (active) __init__
            months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
            self.banking_summaries = [BankingCreditSummary(month=m) for m in months]
            self.salary_summaries = [GrossSalarySummary(month=m) for m in months]
            self.installment_tax_summary = InstallmentTaxSummary()

    __table_args__ = (
        # Composite index for client queries with soft delete
        db.Index('idx_jobs_client_deleted', 'client_id', 'deleted_at'),
        
        # Index for creator queries
        db.Index('idx_jobs_creator', 'created_by_id'),
        
        # Index for partner review queries (task_dashboard route)
        db.Index('idx_jobs_review_partner', 'review_partner_id'),
        
        # Index for name searches
        db.Index('idx_jobs_name', 'name'),
        
        # Index for created_at ordering
        db.Index('idx_jobs_created_at', 'created_at'),
        
        # Index for soft delete
        db.Index('idx_jobs_deleted', 'deleted_at'),
    )

class TaskDocument(db.Model):
    __tablename__ = 'task_documents'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)  # path on disk or in cloud
    file_mime_type = db.Column(db.String(100), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship('Task', backref=db.backref('documents', cascade="all, delete-orphan"), foreign_keys=[task_id])
    uploaded_by = db.relationship('User', backref='uploaded_documents', foreign_keys=[uploaded_by_id])


    __table_args__ = (
        # Index for task document queries
        db.Index('idx_task_documents_task', 'task_id'),
        
        # Index for uploader queries
        db.Index('idx_task_documents_uploader', 'uploaded_by_id'),
        
        # Index for file path queries (download_file route)
        db.Index('idx_task_documents_file_path', 'file_path'),
        
        # Index for uploaded_at ordering
        db.Index('idx_task_documents_uploaded_at', 'uploaded_at'),
    )

class TaskNote(db.Model):
    __tablename__ = 'task_notes'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship('Task', backref=db.backref('notes', cascade="all, delete-orphan"), foreign_keys=[task_id])
    user = db.relationship('User', backref='task_notes', foreign_keys=[user_id])


    __table_args__ = (
        # Index for task note queries
        db.Index('idx_task_notes_task', 'task_id'),
        
        # Index for user queries
        db.Index('idx_task_notes_user', 'user_id'),
        
        # Composite index for task+user queries
        db.Index('idx_task_notes_task_user', 'task_id', 'user_id'),
        
        # Index for created_at ordering
        db.Index('idx_task_notes_created_at', 'created_at'),
    )

class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    # This is the RECIPIENT of the notification
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # This is the user who PERFORMED the action (the "actor")
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Nullable for system notifications
    
    message = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(255), nullable=True)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(50), default='info')

    # This relationship gets the recipient user object
    user = db.relationship('User', backref='notifications', foreign_keys=[user_id])
    actor = db.relationship('User', foreign_keys=[actor_id], backref='acted_notifications')
    
    def to_dict(self):
        return {
            'id': self.id,
            'message': self.message,
            'url': self.url,
            'read': self.read,
            'created_at': self.created_at.isoformat() + 'Z', # Format for JS
            'type': self.type # Include type
        }
    
    __table_args__ = (
        # Composite index for user notifications (most common query)
        db.Index('idx_notifications_user_read_created', 'user_id', 'read', 'created_at'),
        
        # Index for actor queries
        db.Index('idx_notifications_actor', 'actor_id'),
        
        # Index for read status
        db.Index('idx_notifications_read', 'read'),
        
        # Index for created_at ordering
        db.Index('idx_notifications_created_at', 'created_at'),
    )

class VatFilingMonth(db.Model):
    __tablename__ = 'vat_filing_months'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    month = db.Column(db.String(20), nullable=False)
    nature_of_business = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    comments = db.Column(db.Text, nullable=True)

    # User-Entered Data
    reg_customers_vatable_16 = db.Column(db.Numeric(15, 2), default=0)
    reg_customers_vatable_8 = db.Column(db.Numeric(15, 2), default=0)
    reg_customers_zero_rated = db.Column(db.Numeric(20, 2), default=0)
    reg_customers_exempt = db.Column(db.Numeric(20, 2), default=0)

    non_reg_customers_vatable_16 = db.Column(db.Numeric(15, 2), default=0)
    non_reg_customers_vatable_8 = db.Column(db.Numeric(15, 2), default=0)
    non_reg_customers_zero_rated = db.Column(db.Numeric(20, 2), default=0)
    non_reg_customers_exempt = db.Column(db.Numeric(20, 2), default=0)

    purchases_vatable_16 = db.Column(db.Numeric(15, 2), default=0)
    purchases_vatable_8 = db.Column(db.Numeric(15, 2), default=0)
    purchases_zero_rated = db.Column(db.Numeric(20, 2), default=0)
    purchases_exempt = db.Column(db.Numeric(20, 2), default=0)
    vat_wh_credit = db.Column(db.Numeric(20, 2), default=0)
    credit_bf = db.Column(db.Numeric(20, 2), default=0)
    vat_payable_override = db.Column(db.Numeric(20, 2), nullable=True)
    paye_employees = db.Column(db.Integer)
    paye_amount = db.Column(db.Numeric(20, 2))
    shif_employees = db.Column(db.Integer)
    shif = db.Column(db.Numeric(20, 2))
    nssf_employees = db.Column(db.Integer)
    nssf = db.Column(db.Numeric(20, 2))
    
    job = db.relationship('Job', back_populates='vat_filing_months')

    # --- FINALIZED CALCULATED PROPERTIES ---
    @property
    def reg_customers_vat(self):
        return (self.reg_customers_vatable_16 or 0) * Decimal('0.16') + \
            (self.reg_customers_vatable_8 or 0) * Decimal('0.08')

    @property
    def reg_customers_total(self):
        return (self.reg_customers_vatable_16 or 0) + \
            (self.reg_customers_vatable_8 or 0) + \
            (self.reg_customers_zero_rated or 0) + \
            (self.reg_customers_exempt or 0)

    @property
    def non_reg_customers_vat(self):
        return (self.non_reg_customers_vatable_16 or 0) * Decimal('0.16') + \
            (self.non_reg_customers_vatable_8 or 0) * Decimal('0.08')

    @property
    def non_reg_customers_total(self):
        return (self.non_reg_customers_vatable_16 or 0) + \
            (self.non_reg_customers_vatable_8 or 0) + \
            (self.non_reg_customers_zero_rated or 0) + \
            (self.non_reg_customers_exempt or 0)
    
    @property
    def total_sales_vatable(self):
        return (self.reg_customers_vatable_16 or 0) + \
            (self.reg_customers_vatable_8 or 0) + \
            (self.non_reg_customers_vatable_16 or 0) + \
            (self.non_reg_customers_vatable_8 or 0)    

    @property
    def vat_on_sales(self):
        return self.reg_customers_vat + self.non_reg_customers_vat
        
    @property
    def total_sales_zero_rated(self):
        return (self.reg_customers_zero_rated or 0) + (self.non_reg_customers_zero_rated or 0)

    @property
    def total_sales_exempt(self):
        return (self.reg_customers_exempt or 0) + (self.non_reg_customers_exempt or 0)

    @property
    def total_sales(self):
        return self.reg_customers_total + self.non_reg_customers_total

    @property
    def purchases_vat(self):
        return (self.purchases_vatable_16 or 0) * Decimal('0.16') + \
            (self.purchases_vatable_8 or 0) * Decimal('0.08')

    @property
    def purchases_total(self):
        return (self.purchases_vatable_16 or 0) + \
            (self.purchases_vatable_8 or 0) + \
            (self.purchases_zero_rated or 0) + \
            (self.purchases_exempt or 0)

    @property
    def vat_payable(self):
        if self.vat_payable_override is not None:
            return self.vat_payable_override
        
        output_vat = self.vat_on_sales
        input_vat = self.purchases_vat
        credits = (self.vat_wh_credit or 0) + (self.credit_bf or 0)
        
        return output_vat - input_vat - credits
    
    __table_args__ = (
        # Composite index for job+month queries (get_task route)
        db.Index('idx_vat_filing_months_job_month', 'job_id', 'month'),
        
        # Index for job queries
        db.Index('idx_vat_filing_months_job', 'job_id'),
        
        # Index for month queries
        db.Index('idx_vat_filing_months_month', 'month'),
        
        # Index for created_at ordering
        db.Index('idx_vat_filing_months_created_at', 'created_at'),
    )

class VatMonthlySummary(db.Model):
    __tablename__ = "vat_monthly_summary"

    id = db.Column(db.Integer, primary_key=True)
    vat_month_id = db.Column(db.Integer, db.ForeignKey('vat_filing_months.id'))
    month = db.Column(db.String(20))  # JAN, FEB, ...


    # --- ADD THESE TWO LINES ---
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    job = db.relationship('Job', back_populates='vat_summaries')
    # -------------------------

    # Raw inputs (user/invoice driven)
    sales_zero_rated = db.Column(db.Numeric(20, 2), default=0)
    sales_exempt = db.Column(db.Numeric(20, 2), default=0)
    sales_vatable_16 = db.Column(db.Numeric(20, 2), default=0)
    sales_vatable_8 = db.Column(db.Numeric(20, 2), default=0)

    output_vat_16 = db.Column(db.Numeric(20, 2), default=0)
    output_vat_8 = db.Column(db.Numeric(20, 2), default=0)

    purchases_zero_rated = db.Column(db.Numeric(20, 2), default=0)
    purchases_exempt = db.Column(db.Numeric(20, 2), default=0)
    purchases_vatable_16 = db.Column(db.Numeric(20, 2), default=0)
    purchases_vatable_8 = db.Column(db.Numeric(20, 2), default=0)

    input_vat_16 = db.Column(db.Numeric(20, 2), default=0)
    input_vat_8 = db.Column(db.Numeric(20, 2), default=0)

    withheld_vat = db.Column(db.Numeric(20, 2), default=0)
    balance_bf = db.Column(db.Numeric(20, 2), default=0)   # from prev month
    paid = db.Column(db.Numeric(20, 2), default=0)

    # ---- Properties (calculated like Excel formulas) ----
    @property
    def total_sales(self):
        return (self.sales_zero_rated or 0) + (self.sales_exempt or 0) + \
               (self.sales_vatable_16 or 0) + (self.sales_vatable_8 or 0)

    @property
    def total_output_vat(self):
        return (self.output_vat_16 or 0) + (self.output_vat_8 or 0)

    @property
    def total_purchases(self):
        return (self.purchases_zero_rated or 0) + (self.purchases_exempt or 0) + \
               (self.purchases_vatable_16 or 0) + (self.purchases_vatable_8 or 0)

    @property
    def total_input_vat(self):
        return (self.input_vat_16 or 0) + (self.input_vat_8 or 0)

    @property
    def net_vat(self):
        """Output VAT – Input VAT – Withheld VAT"""
        return (self.total_output_vat or 0) - (self.total_input_vat or 0) - (self.withheld_vat or 0)

    @property
    def balance_cf(self):
        """Balance C/F = Balance B/F + Net VAT – Paid"""
        return (self.balance_bf or 0) + (self.net_vat or 0) - (self.paid or 0)


    __table_args__ = (
        # Index for VAT month queries
        db.Index('idx_vat_monthly_summary_vat_month', 'vat_month_id'),
        
        # Index for job queries
        db.Index('idx_vat_monthly_summary_job', 'job_id'),
        
        # Index for month queries
        db.Index('idx_vat_monthly_summary_month', 'month'),
        
        # Composite index for job+month queries
        db.Index('idx_vat_monthly_summary_job_month', 'job_id', 'month'),
    )

class BankingCreditSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vat_month_id = db.Column(db.Integer, db.ForeignKey('vat_filing_months.id'))
    month = db.Column(db.String(20))
    total_credits = db.Column(db.Numeric(20, 2))
    net_credits = db.Column(db.Numeric(20, 2))
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)

    job = db.relationship('Job', back_populates='banking_summaries')

    @property
    def net_credits(self):
        """ Calculates Net Credits = 100/116 * Total Credits """
        return (Decimal('100') / Decimal('116')) * (self.total_credits or 0)


    __table_args__ = (
        # Index for VAT month queries
        db.Index('idx_banking_summaries_vat_month', 'vat_month_id'),
        
        # Index for job queries
        db.Index('idx_banking_summaries_job', 'job_id'),
        
        # Index for month queries
        db.Index('idx_banking_summaries_month', 'month'),
        
        # Composite index for job+month queries
        db.Index('idx_banking_summaries_job_month', 'job_id', 'month'),
    )

class GrossSalarySummary(db.Model):
    __tablename__ = 'gross_salary_summaries'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    month = db.Column(db.String(20))
    gross_salary = db.Column(db.Numeric(20, 2), default=0)
    job = db.relationship('Job', back_populates='salary_summaries')


    __table_args__ = (
        # Index for job queries
        db.Index('idx_salary_summaries_job', 'job_id'),
        
        # Index for month queries
        db.Index('idx_salary_summaries_month', 'month'),
        
        # Composite index for job+month queries
        db.Index('idx_salary_summaries_job_month', 'job_id', 'month'),
    )

class InstallmentTaxSummary(db.Model):
    __tablename__ = 'installment_tax_summaries'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    installment_tax_1 = db.Column(db.Numeric(20, 2), default=0)
    installment_paid_1 = db.Column(db.Boolean, default=False)
    installment_tax_2 = db.Column(db.Numeric(20, 2), default=0)
    installment_paid_2 = db.Column(db.Boolean, default=False)
    installment_tax_3 = db.Column(db.Numeric(20, 2), default=0)
    installment_paid_3 = db.Column(db.Boolean, default=False)
    installment_tax_4 = db.Column(db.Numeric(20, 2), default=0)
    installment_paid_4 = db.Column(db.Boolean, default=False)
    job = db.relationship('Job', back_populates='installment_tax_summary')

    @property
    def installment_total(self):
        return (self.installment_tax_1 or 0) + (self.installment_tax_2 or 0) + (self.installment_tax_3 or 0) + (self.installment_tax_4 or 0)

    # --- Indexes ---
    __table_args__ = (
        # Index for job lookups (most common query)
        db.Index('idx_installment_tax_summary_job_id', 'job_id'),

        # Composite index for job + installment paid (optimization for certain queries)
        db.Index('idx_installment_tax_summary_job_paid_1', 'job_id', 'installment_paid_1'),
        db.Index('idx_installment_tax_summary_job_paid_2', 'job_id', 'installment_paid_2'),
        db.Index('idx_installment_tax_summary_job_paid_3', 'job_id', 'installment_paid_3'),
        db.Index('idx_installment_tax_summary_job_paid_4', 'job_id', 'installment_paid_4'),

        # Optional: Composite index for job + tax amounts (if queries filter by tax amount)
        db.Index('idx_installment_tax_summary_job_tax_1', 'job_id', 'installment_tax_1'),
        db.Index('idx_installment_tax_summary_job_tax_2', 'job_id', 'installment_tax_2'),
        db.Index('idx_installment_tax_summary_job_tax_3', 'job_id', 'installment_tax_3'),
        db.Index('idx_installment_tax_summary_job_tax_4', 'job_id', 'installment_tax_4'),
    )

class TaxLiabilitySummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    period = db.Column(db.String(20))  # e.g., "Q4 2024"
    tax_head = db.Column(db.String(50))
    principal = db.Column(db.Numeric(20, 2))
    penalty = db.Column(db.Numeric(20, 2))
    interest = db.Column(db.Numeric(20, 2))
    total = db.Column(db.Numeric(20, 2))

    job = db.relationship('Job', back_populates='tax_liabilities')

    # --- Indexes ---
    __table_args__ = (
        # Index for job lookups
        db.Index('idx_tax_liability_summary_job_id', 'job_id'),

        # Index for period lookups
        db.Index('idx_tax_liability_summary_period', 'period'),

        # Index for tax head lookups
        db.Index('idx_tax_liability_summary_tax_head', 'tax_head'),

        # Composite index for job, period, and tax head queries
        db.Index('idx_tax_liability_summary_job_period_tax_head', 'job_id', 'period', 'tax_head'),
    )

class SheetVisibilityEnum(Enum):
    CREATOR_AND_DIRECTORS = "creator_and_directors"
    CREATOR_SUPERVISORS_DIRECTORS = "creator_supervisors_directors"
    CREATOR_ALL_EXCEPT_INTERNS = "creator_all_except_interns"
    EVERYONE = "everyone"
    DEPARTMENT_RESTRICTED = "department_restricted"  # only dept + creator + director + supervisor

class Sheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.JSON, default=[])

    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    visible_on_sheets_home = db.Column(db.Boolean, default=True)

    # Permissions
    visibility = db.Column(SqlEnum(SheetVisibilityEnum), default=SheetVisibilityEnum.CREATOR_ALL_EXCEPT_INTERNS)
    # --- ADDED Soft Delete ---
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='deleted_sheets')
    # --- END ---
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='created_sheets')
    task = db.relationship('Task', backref='sheets', foreign_keys=[task_id]) # Specify FK

    def is_task_only(self):
        return self.task_id is not None and not self.visible_on_sheets_home

    def can_user_view(self, user: "User") -> bool:
        if user.role == 'ADMIN':
            return True
        if self.created_by_id == user.id:
            return True

        if self.visibility == SheetVisibilityEnum.EVERYONE:
            return True

        elif self.visibility == SheetVisibilityEnum.CREATOR_AND_DIRECTORS:
            return user.role == 'DIRECTOR'

        elif self.visibility == SheetVisibilityEnum.CREATOR_SUPERVISORS_DIRECTORS:
            return user.role in ['SUPERVISOR', 'DIRECTOR']

        elif self.visibility == SheetVisibilityEnum.CREATOR_ALL_EXCEPT_INTERNS:
            return user.role != 'INTERN'

        elif self.visibility == SheetVisibilityEnum.DEPARTMENT_RESTRICTED:
            is_same_dept = self.created_by.department_id == user.department_id
            return (
                user.role in ['SUPERVISOR', 'DIRECTOR'] or
                is_same_dept
            )

        return False  # default deny
    
    def get_sheet_data(self):
        """
        Returns 2D array of sheet data (for view/edit).
        Supports both 'data' and 'celldata' formats.
        """
        if not self.content:
            return []

        try:
            entry = self.content[0]
            if 'data' in entry:
                return entry['data']
            elif 'celldata' in entry:
                return [
                    [cell.get('v', '') for cell in row]
                    for row in entry['celldata']
                ]
        except Exception:
            pass

        return self.content  # fallback
   
# ======================
# BIODATA
# ======================

class Biodata(db.Model):
    __tablename__ = "biodata"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    # Personal Information
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    date_of_birth = db.Column(db.Date)
    nationality = db.Column(db.String(100))
    
    # Education History (store as JSON for multiple entries)
    education_history = db.Column(db.JSON, default=[])
    """
    education_history structure:
    [
        {
            "institution": "University of Nairobi",
            "qualification": "Bachelor of Commerce",
            "field_of_study": "Accounting",
            "start_date": "2018-09-01",
            "end_date": "2022-06-30",
            "is_current": false,
            "grade": "First Class Honors",
            "description": "Specialized in Financial Accounting"
        }
    ]
    """
    
    # Work Experience (store as JSON for multiple entries)
    work_experience = db.Column(db.JSON, default=[])
    """
    work_experience structure:
    [
        {
            "company": "ABC Company Ltd",
            "position": "Junior Accountant",
            "start_date": "2022-07-01",
            "end_date": "2023-12-31",
            "is_current": false,
            "responsibilities": ["Bookkeeping", "Tax preparation", "Financial reporting"],
            "achievements": "Improved reporting efficiency by 30%"
        }
    ]
    """
    
    # Professional Qualifications
    professional_qualifications = db.Column(db.JSON, default=[])
    """
    professional_qualifications structure:
    [
        {
            "name": "CPA K",
            "institution": "ICPAK",
            "year_obtained": 2023,
            "license_number": "CPA12345"
        }
    ]
    """
    
    # Skills
    skills = db.Column(db.JSON, default=[])
    """
    skills structure: ["Accounting", "Tax Preparation", "QuickBooks", "Auditing"]
    """
    
    # References
    references = db.Column(db.JSON, default=[])
    """
    references structure:
    [
        {
            "name": "John Smith",
            "position": "Finance Manager",
            "company": "XYZ Corp",
            "email": "john@xyz.com",
            "phone": "+254712345678"
        }
    ]
    """
    
    # Additional info
    cover_letter = db.Column(db.Text)
    resume_path = db.Column(db.String(255))  # Path to uploaded resume file
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="biodata_entries")
    applications = db.relationship("Application", back_populates="biodata")

    def __repr__(self):
        return f"Biodata(User:{self.user_id}, Name:'{self.full_name}')"
    
    def add_education(self, education_data):
        """Helper method to add education entry"""
        if not self.education_history:
            self.education_history = []
        self.education_history.append(education_data)
    
    def add_work_experience(self, work_data):
        """Helper method to add work experience entry"""
        if not self.work_experience:
            self.work_experience = []
        self.work_experience.append(work_data)
    
    def add_skill(self, skill):
        """Helper method to add skill"""
        if not self.skills:
            self.skills = []
        if skill not in self.skills:
            self.skills.append(skill)
    
    @property
    def total_experience_years(self):
        """Calculate total years of work experience"""
        if not self.work_experience:
            return 0
        
        total_days = 0
        for job in self.work_experience:
            start_date = datetime.strptime(job['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(job['end_date'], '%Y-%m-%d').date() if job.get('end_date') else datetime.utcnow().date()
            total_days += (end_date - start_date).days
        
        return round(total_days / 365.25, 1)  # Account for leap years
# ======================
# PIPELINE + STAGES
# ======================
class Pipeline(db.Model):
    """
    A recruitment flow for a specific role (e.g., Audit Trainee 2025).
    """
    __tablename__ = "pipelines"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    stages = db.relationship("Stage", back_populates="pipeline", order_by="Stage.order")

class Stage(db.Model):
    """
    A single stage in a pipeline (Technical, Personality, etc.)
    """
    __tablename__ = "stages"
    id = db.Column(db.Integer, primary_key=True)
    pipeline_id = db.Column(db.Integer, db.ForeignKey("pipelines.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    stage_type = db.Column(db.Enum(StageType), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)

    pipeline = db.relationship("Pipeline", back_populates="stages")
    candidate_stages = db.relationship("CandidateStage", back_populates="stage")
    questions = db.relationship(
        "Question",
        secondary=stage_questions_association_table,
        backref="stages_it_is_in",
        lazy='dynamic'
    )

class CandidateStage(db.Model):
    __tablename__ = "candidate_stages"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stage_id = db.Column(db.Integer, db.ForeignKey("stages.id"), nullable=False)
    status = db.Column(db.String(50), default="not_started")
    scheduled_time = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    score = db.Column(db.Float)

    user = db.relationship("User", back_populates="candidate_stages")
    stage = db.relationship("Stage", back_populates="candidate_stages")
    result = db.relationship("StageResult", back_populates="candidate_stage", uselist=False)
# ======================
# QUESTIONS + CHOICES + ANSWERS
# ======================
class QuestionCategory(db.Model):
    __tablename__ = 'question_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    # Add type field if you want to categorize further
    category_type = db.Column(db.String(20), default='technical')  # technical, compliance, etc.
    questions = db.relationship('Question', backref='question_category', lazy='dynamic')

    def __repr__(self):
        return f"<QuestionCategory {self.name} ({self.category_type})>"

class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('question_categories.id'), nullable=True)
    question_type = db.Column(db.Enum(QuestionType), nullable=False)
    personality_trait_id = db.Column(db.Integer, db.ForeignKey('personality_traits.id'), nullable=True)
    choices = db.relationship("Choice", back_populates="question", cascade="all, delete-orphan")
    answers_to_this_question = db.relationship("Answer", back_populates="question_obj")
    personality_trait = db.relationship("PersonalityTrait", foreign_keys=[personality_trait_id])

    def __repr__(self):
        return f"Question('{self.text[:30]}...', Type:{self.question_type.value})"

class Choice(db.Model):
    __tablename__ = "choices"
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"))
    text = db.Column(db.String(200), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

    question = db.relationship("Question", back_populates="choices")
    trait_weights = db.relationship("TraitWeight", back_populates="choice", cascade="all, delete-orphan")

    def __repr__(self):
        return f"Choice('{self.text[:30]}...', Correct:{self.is_correct})"
    
    def __repr__(self):
        return f'<Choice {self.text}>' 

class Answer(db.Model):
    __tablename__ = "answers"
    id = db.Column(db.Integer, primary_key=True)
    candidate_stage_id = db.Column(db.Integer, db.ForeignKey("candidate_stages.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    choice_id = db.Column(db.Integer, db.ForeignKey("choices.id"), nullable=True)
    text_answer = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    time_taken_seconds = db.Column(db.Integer)
    is_correct = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float, default=0.0)

    question_obj = db.relationship("Question", back_populates="answers_to_this_question")
    choice_obj = db.relationship("Choice")
    candidate_stage = db.relationship("CandidateStage")

# ======================
# PERSONALITY TEST EXTENSION
# ======================

# This is the replacement for your 'Trait' model. We will re-use QuestionCategory.
class TraitWeight(db.Model):
    __tablename__ = "trait_weights"
    id = db.Column(db.Integer, primary_key=True)
    choice_id = db.Column(db.Integer, db.ForeignKey("choices.id"), nullable=False)
    trait_id = db.Column(db.Integer, db.ForeignKey("personality_traits.id"), nullable=False)  # CHANGED
    weight = db.Column(db.Float, nullable=False, default=0.0)

    choice = db.relationship("Choice", back_populates="trait_weights")
    trait = db.relationship("PersonalityTrait", back_populates="trait_weights")  # CHANGED

    def __repr__(self):
        return f"TraitWeight(Choice:{self.choice_id}, Trait:{self.trait.name}, Weight:{self.weight})"
    
class JobRole(db.Model):
    __tablename__ = "job_roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)  # e.g. Auditor, Tax Specialist
    description = db.Column(db.Text)

class RoleTraitWeight(db.Model):
    __tablename__ = "role_trait_weights"
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("job_roles.id"), nullable=False)
    trait_id = db.Column(db.Integer, db.ForeignKey("personality_traits.id"), nullable=False)  # CHANGED
    weight = db.Column(db.Integer, nullable=False)  # Importance 1–5

    role = db.relationship("JobRole")
    trait = db.relationship("PersonalityTrait", back_populates="role_trait_weights")

class AssessmentResult(db.Model):
    __tablename__ = "assessment_results"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    trait_scores = db.Column(db.Text)  # Store JSON as text
    best_fit_role_id = db.Column(db.Integer, db.ForeignKey("job_roles.id"))

    user = db.relationship("User", back_populates="assessment_results")
    best_fit_role = db.relationship("JobRole")

    @property
    def trait_scores_json(self):
        if self.trait_scores:
            return json.loads(self.trait_scores)
        return {}

    @trait_scores_json.setter
    def trait_scores_json(self, value):
        self.trait_scores = json.dumps(value)

class PersonalityTrait(db.Model):
    __tablename__ = 'personality_traits'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    
    # Relationships
    trait_weights = db.relationship("TraitWeight", back_populates="trait")
    role_trait_weights = db.relationship("RoleTraitWeight", back_populates="trait")

    def __repr__(self):
        return f"<PersonalityTrait {self.name}>"

# ======================
# COMMENTS (Interviewer notes)
# ======================
class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    candidate_stage_id = db.Column(db.Integer, db.ForeignKey("candidate_stages.id"))
    interviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    interviewer = db.relationship("User", foreign_keys=[interviewer_id], back_populates="comments_made")
    candidate_stage = db.relationship("CandidateStage")

    def __repr__(self):
        return f"Comment(Stage:{self.candidate_stage_id}, By:{self.interviewer_id})"

class StageResult(db.Model):  
    __tablename__ = "stage_results"
    id = db.Column(db.Integer, primary_key=True)
    candidate_stage_id = db.Column(db.Integer, db.ForeignKey("candidate_stages.id"), nullable=False)
    grade = db.Column(db.Enum(Grade))
    remarks = db.Column(db.String(500))

    candidate_stage = db.relationship("CandidateStage", back_populates="result")

    @staticmethod
    def calculate_grade(score: float) -> Grade:
        if score >= 80:
            return Grade.A
        elif score >= 70:
            return Grade.B
        elif score >= 60:
            return Grade.C
        elif score >= 50:
            return Grade.D
        else:
            return Grade.F
        
    def set_grade_from_score(self, score: float):
        self.grade = StageResult.calculate_grade(score)

    def __repr__(self):
        return f"StageResult(Stage:{self.candidate_stage_id}, Grade:{self.grade}, Remarks:{self.remarks[:20]}...)"
    
class Opportunity(db.Model):
    __tablename__ = "opportunities"
        
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.JSON)  # Store as list of strings
    benefits = db.Column(db.Text)
        
    opportunity_type = db.Column(db.Enum(OpportunityType), nullable=False, default=OpportunityType.INTERNAL)
        
        # Flexible client handling - can be FK or string
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)  # For existing clients
    client_name = db.Column(db.String(200), nullable=True)  # For external clients not in our system
        
    job_role_id = db.Column(db.Integer, db.ForeignKey("job_roles.id"), nullable=True)
    job_role_name = db.Column(db.String(200), nullable=True)
        
    opening_date = db.Column(db.DateTime, nullable=False)
    closing_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Enum(OpportunityStatus), default=OpportunityStatus.DRAFT)
        
        # Location info
    location = db.Column(db.String(200))
    is_remote = db.Column(db.Boolean, default=False)
        
        # Metadata
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    views_count = db.Column(db.Integer, default=0)

    pipeline_id = db.Column(db.Integer, db.ForeignKey('pipelines.id'), nullable=True)
        
        # Relationships
    client = db.relationship('Client', backref='opportunities')
    job_role = db.relationship("JobRole")
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    applications = db.relationship("Application", back_populates="opportunity", cascade="all, delete-orphan")
    pipeline = db.relationship('Pipeline', backref='opportunities') 
        # Soft delete
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='deleted_opportunities')

    @property
    def display_client(self):
            """Returns client name whether it's from Client model or direct string"""
            if self.client:
                return self.client.name
            return self.client_name
        
        
        
    @property
    def is_active(self):
        now = datetime.utcnow()
        return (self.status == OpportunityStatus.OPEN and 
                self.opening_date <= now <= self.closing_date)
        
    def increment_views(self):
        self.views_count += 1

class Application(db.Model):
    __tablename__ = "applications"
    
    id = db.Column(db.Integer, primary_key=True)
    opportunity_id = db.Column(db.Integer, db.ForeignKey("opportunities.id"), nullable=False)
    
    # Link to user and their biodata (single source of truth)
    applicant_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    applicant_user = db.relationship("User", foreign_keys=[applicant_user_id], backref="applications")
    biodata_id = db.Column(db.Integer, db.ForeignKey("biodata.id"), nullable=False)
    
    # Application-specific data
    cover_letter = db.Column(db.Text)
    status = db.Column(db.Enum(ApplicationStatus), default=ApplicationStatus.SUBMITTED)
    
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    opportunity = db.relationship("Opportunity", back_populates="applications")
    biodata = db.relationship("Biodata", back_populates="applications")
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id])
    
    @property
    def applicant_name(self):
        return self.biodata.full_name if self.biodata else self.applicant_user.full_name
    
    @property
    def applicant_email(self):
        return self.biodata.email if self.biodata else self.applicant_user.email
    
    @property
    def is_recent(self):
        """Check if application was submitted in the last 7 days"""
        return (datetime.utcnow() - self.submitted_at).days <= 7