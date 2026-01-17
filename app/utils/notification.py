from app.models import User, Task, DecisionEnum, RoleEnum
from app import mail  # Remove celery import
from flask_mail import Message
from flask import current_app
from app.models import Job, Department  # Added Department import
from app.utils.db import db
import asyncio
import threading  # ADD THIS IMPORT

# Helper function to run async functions in the background
def run_async_in_background(async_func, *args):
    # Capture the real app object
    app = current_app._get_current_object()

    def run_in_thread():
        # Push the original app context
        with app.app_context():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(async_func(*args))
            loop.close()

    thread = threading.Thread(target=run_in_thread)
    thread.daemon = True
    thread.start()


async def _send_email_message_async(subject, body, recipients):
    if not recipients:
        print("Error: No recipients provided for email.")
        return

    if isinstance(recipients, str):
        recipients = [recipients]

    msg = Message(subject, sender="administrator@3allp.com", recipients=recipients)
    msg.body = body

    try:
        # DO NOT use run_in_executor for Flask-Mail
        mail.send(msg)
        current_app.logger.info(f"Email sent successfully: '{subject}' to {recipients}")
    except Exception as e:
        current_app.logger.error(f"FATAL ERROR SENDING EMAIL: '{subject}' to {recipients}. Error: {e}")

# --- Async Email Functions Start Here ---
async def send_task_notification_async(task_id):
    """Sends an email notification to the assigned user."""
    task = Task.query.get(task_id)
    if not task:
        current_app.logger.warning(f"Task with ID {task_id} not found for notification.")
        return

    recipient = User.query.get(task.assigned_to_id)
    
    if not recipient or not recipient.email:
        current_app.logger.warning(f"No email found for assigned user ID {task.assigned_to_id}.")
        return

    subject = f"New Task Assigned: {task.title}"
    deadline_str = task.deadline.strftime('%Y-%m-%d %H:%M %Z') if task.deadline else 'No deadline set'

    body = f"""
    Dear {recipient.first_name},
    A new task has been assigned to you:
    Title: {task.title}
    Description: {task.description}
    Deadline: {deadline_str}
    Please log in to the system to manage your tasks.
    Best regards,
    3ALLP Admin Team
    """
    await _send_email_message_async(subject, body, [recipient.email])

async def send_task_submitted_notification_async(task_id):
    """Notifies the task creator that the task has been submitted for review."""
    task = Task.query.get(task_id)
    if not task:
        current_app.logger.warning(f"Task with ID {task_id} not found for submission notification.")
        return
        
    if task.assigned_to_id == task.created_by_id:
        current_app.logger.info("Creator and assignee are the same. No submission notification sent.")
        return

    creator = User.query.get(task.created_by_id)
    assignee = User.query.get(task.assigned_to_id)

    if not creator or not creator.email:
        current_app.logger.warning("No email found for task creator.")
        return

    subject = f"Task Submitted for Review: {task.title}"
    body = f"""
    Dear {creator.first_name},
    The following task assigned to {assignee.first_name} has been submitted for review:
    Title: {task.title}
    Description: {task.description}
    Please log in to the system to review and take the appropriate action.
    Regards,
    3ALLP System
    """
    await _send_email_message_async(subject, body, [creator.email])

async def send_task_review_decision_notification_async(task_id, decision_value, remarks=None):
    """Notifies the assignee about the review decision on their task."""
    task = Task.query.get(task_id)
    if not task:
        current_app.logger.warning(f"Task with ID {task_id} not found for review decision.")
        return
        
    assignee = User.query.get(task.assigned_to_id)

    if not assignee or not assignee.email:
        current_app.logger.warning("No email found for assignee.")
        return

    decision_text = "approved ✅" if decision_value == DecisionEnum.APPROVED.value else "sent back for redo 🔁"
    subject = f"Task Review Decision: {task.title} ({decision_text})"
    body = f"""
    Dear {assignee.first_name},
    Your task has been reviewed. Below are the details:
    Title: {task.title}
    Decision: {decision_text}
    Remarks: {remarks or 'No additional remarks provided.'}
    Please log in to the system to follow up.
    Regards,
    3ALLP System
    """
    await _send_email_message_async(subject, body, [assignee.email])

async def send_department_reviewer_notification_async(appointer_id, appointee_id, department_id):
    """Sends notification to the new reviewer and all directors."""
    appointer = User.query.get(appointer_id)
    appointee = User.query.get(appointee_id)
    department = Department.query.get(department_id)

    if not all([appointer, appointee, department]):
        current_app.logger.warning("Missing user or department for reviewer notification.")
        return

    # 1. Send personalized email to the appointee
    if appointee.email:
        appointee_subject = f"You have been appointed as a Reviewer for {department.name}!"
        appointee_body = f"""
        Hello {appointee.full_name},
        You have been appointed as a reviewer for the {department.name} department by {appointer.full_name}.
        As a reviewer, you will now be responsible for reviewing tasks and documents related to this department.
        This is an automated notification. Please log in to the system to see your new responsibilities.
        Regards,
        3ALLP System
        """
        await _send_email_message_async(appointee_subject, appointee_body, [appointee.email])

    # 2. Send a different notification to all directors
    director_emails = 'partners@3allp.com'
    if director_emails:
        director_subject = f"ACTION: {appointee.full_name} Appointed as Reviewer"
        director_body = f"""
        Dear Directors,
        {appointer.full_name} has appointed {appointee.full_name} as a reviewer for the {department.name} department.
        This is an automated notification. No action is required unless you wish to follow up.
        Regards,
        3ALLP System
        """
        await _send_email_message_async(director_subject, director_body, [director_emails])

async def send_new_engagement_notifications_async(job_id):
    """
    Sends two separate notifications when a new engagement is created.
    1. A personal message to all users assigned to tasks within the engagement.
    2. A summary message to all users with the 'Director' role.
    """
    job = Job.query.get(job_id)
    if not job:
        current_app.logger.warning(f"Job with ID {job_id} not found for engagement notification.")
        return

    # 1. Notify assigned task users
    assigned_users = set()
    for task in job.tasks:
        if task.assigned_to and task.assigned_to not in assigned_users:
            assigned_users.add(task.assigned_to)

    for user in assigned_users:
        if user.email:
            subject = f"New Engagement: {job.name} - A Task Has Been Assigned To You"
            body = f"""
            Hello {user.first_name},
            A new engagement titled "{job.name}" has been created, and you have been assigned one or more tasks under it.
            Please log in to the system to view your new tasks and their deadlines.
            Regards,
            3ALLP System
            """
            await _send_email_message_async(subject, body, [user.email])

    # 2. Notify all directors
    director_emails = 'partners@3allp.com'
    if director_emails:
        director_subject = f"New Engagement Created: {job.name}"
        director_body = f"""
        Hello Directors,
        A new engagement, "{job.name}," has been created by {job.creator.full_name}.
        You can view the engagement and its associated tasks in the system.
        Regards,
        3ALLP System
        """
        await _send_email_message_async(director_subject, director_body, director_emails)

async def send_review_partner_set_notification_async(job_id):
    """
    Sends a notification to the newly assigned review partner for an engagement.
    """
    job = Job.query.get(job_id)
    if not job or not job.review_partner or not job.review_partner.email:
        current_app.logger.warning(f"Job ID {job_id} missing or no review partner/email found.")
        return

    partner = job.review_partner
    subject = f"You Have Been Assigned as Review Partner for: {job.name}"
    body = f"""
    Hello {partner.first_name},
    You have been assigned as the review partner for the engagement: {job.name}.
    You are now responsible for reviewing and overseeing the tasks and progress of this engagement.
    Please log in to the system to view the engagement details.
    Regards,
    3ALLP System
    """
    await _send_email_message_async(subject, body, [partner.email])

async def send_password_reset_email_async(user_id, reset_link):
    """Sends a password reset email to the user."""
    user = User.query.get(user_id)
    if not user or not user.email:
        current_app.logger.warning(f"User ID {user_id} missing or no email provided for password reset.")
        return

    subject = "Password Reset Request"
    body = f"""
    Hello {user.first_name},
    You requested a password reset. Click the link below to set a new password:
    {reset_link}
    If you did not request this, please ignore this email. This link will expire in 30 minutes.
    Regards,
    3ALLP System
    """
    await _send_email_message_async(subject, body, [user.email])

async def send_welcome_and_password_notification_async(user_id, raw_password):
    """Sends a welcome email with the raw password to a new user."""
    user = User.query.get(user_id)
    if not user or not user.email:
        current_app.logger.warning(f"User ID {user_id} missing or no email provided for welcome email.")
        return

    subject = "Welcome to 3ALLP Workflow - Your Account is Ready"
    body = f"""
    Hello {user.first_name},
    An account has been created for you on the 3ALLP Workflow system by an administrator.
    You can now log in using the following credentials:
    
    Email: {user.email}
    Password: {raw_password}
    It is highly recommended that you log in and change your password at your earliest convenience.
    Regards,
    3ALLP System
    """
    await _send_email_message_async(subject, body, [user.email])


    """Runs an async function in the background without waiting for completion."""
    def run_in_thread():
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(async_func(*args))
            loop.close()
        except Exception as e:
            print(f"Error in async background task: {e}")
    
    thread = threading.Thread(target=run_in_thread)
    thread.daemon = True  # This allows the thread to exit when the main program exits
    thread.start()