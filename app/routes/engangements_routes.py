from flask import Blueprint, Response, request, jsonify, session, render_template, url_for, flash, redirect, current_app,abort
from app.models import *
from flask_login import login_required, current_user
from app.utils.db import db
from .task_routes import search_clients, can_assign_task, get_employee_ids
import pytz
from app.utils.helpers import make_task_from_data, can_assign_task, get_employee_ids, can_delete_job
from datetime import datetime, timedelta
from dateutil.parser import parse as date_parse
from calendar import month_abbr
from decimal import Decimal, InvalidOperation
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from  .engagement_service import update_historical_summaries, update_current_month_vat_data, update_historical_summaries, update_current_month_vat_data, update_banking_and_salary, update_installment_tax, update_tax_liabilities
import pandas as pd
import io
import csv
from app.utils.notification import run_async_in_background, send_new_engagement_notifications_async, send_review_partner_set_notification_async
from sqlalchemy.orm import joinedload, subqueryload
from sqlalchemy import or_

from .auth_routes import supervisors_admins_directors

job_bp= Blueprint('job', __name__)

@job_bp.route('/jobs/create', methods=['GET', 'POST'])
@login_required
def create_job():
    local_tz = pytz.timezone('Africa/Nairobi')

    # for the GET form
    users     = User.query.order_by(User.last_name).all()
    clients   = Client.query.order_by(Client.name).all()
    templates = TaskTemplate.query.all()
    services  = Service.query.order_by(Service.name).all()

    # --- FIX: The incorrect 'task = Task.query.all()' line has been removed ---

    # now-local for timestamp display
    now_local = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(local_tz)

    if request.method == 'POST':
        # 1) Basic job fields
        client_id = request.form.get('client_id')
        service_id = request.form.get('service_id')
        name       = request.form.get('name')
        engagement_assigned_to_id = int(request.form.get('assigned_to', 0))

        if not client_id or not service_id:
            flash('Client and service are required.', 'danger')
            return redirect(request.url)
        
        # --- NEW LOGIC: Get the Service object to check its name ---
        service = Service.query.get(service_id)
        if not service:
            flash('Invalid service selected.', 'danger')
            return redirect(request.url)

        # 2) Create the Job
        job = Job(
            client_id=int(client_id),
            name=name,
            created_by_id=current_user.id
        )
        # --- FIX: Save that single service as the first item in the NEW list ---
        job.services = [service]

        db.session.add(job)
        db.session.flush()  # so job.id is available

        first_vat_deadline = None

        # 3) Loop over each selected template
        for tpl_id_str in request.form.getlist('task_template_ids'):
            tpl_id = int(tpl_id_str)
            tpl   = TaskTemplate.query.get(tpl_id)

            # permission check once per template
            if not can_assign_task(engagement_assigned_to_id):
                flash(f"You cannot assign tasks to user {engagement_assigned_to_id}.", 'danger')
                return redirect(request.url)

            # collect namespaced form fields
            deadline_str     = request.form.get(f'deadline_{tpl_id}')
            description      = request.form.get(f'description_{tpl.id}', tpl.description)
            est_value        = request.form.get(f'estimated_value_{tpl_id}', 0)
            est_unit         = request.form.get(f'estimated_unit_{tpl_id}', 'minutes')
            priority_str     = request.form.get(f'priority_{tpl_id}', 'Normal')
            recurrence_str = request.form.get(f'recurrence_{tpl_id}', 'NONE')
            task_assigned_to_id_str = request.form.get(f'assigned_to_task_{tpl_id}')
            
            
            final_task_assignee_id = engagement_assigned_to_id # Start with the default
            if task_assigned_to_id_str:
                try:
                    final_task_assignee_id = int(task_assigned_to_id_str)
                except ValueError:
                    pass

            # --- FIX: Assign the result of the helper to a new variable ---
            newly_created_task = make_task_from_data(
                title=tpl.title,
                description=description,
                assigned_to_id=final_task_assignee_id,
                created_by_id=current_user.id,
                client_id=int(client_id),
                task_template_id=tpl_id,
                job_id=job.id,
                deadline_str=deadline_str,
                estimated_value=est_value,
                estimated_unit=est_unit,
                priority_str=priority_str,
                recurrence_str=recurrence_str
            )

            # --- FIX: Use the new variable to check the deadline ---
            if service.name == 'Tax Services' and tpl.title == 'VAT Returns':
                if newly_created_task and newly_created_task.deadline:
                    first_vat_deadline = newly_created_task.deadline
            
        # --- NEW LOGIC: After creating all tasks, create the initial VatFilingMonth ---
        if first_vat_deadline:
            vat_month_date = first_vat_deadline - relativedelta(months=1)
            month_str = vat_month_date.strftime('%b-%Y')
            
            existing_form = VatFilingMonth.query.filter_by(job_id=job.id, month=month_str).first()
            if not existing_form:
                new_vat_form = VatFilingMonth(
                    job_id=job.id,
                    month=month_str,
                    nature_of_business=job.client.name 
                )
                db.session.add(new_vat_form)

        # 4) commit everything
        db.session.commit()
        flash('Engagement and its tasks created successfully!', 'success')
        run_async_in_background(send_new_engagement_notifications_async, job.id)
        return redirect(url_for('job.view_job', job_id=job.id))

    # Serialize templates to plain dicts
    serialized_templates = [{
        'id': tpl.id,
        'service_id': tpl.service_id,
        'title': tpl.title,
        'description': tpl.description
    } for tpl in templates]

    serialized_users = [{
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name
    } for user in users]

    # GET: render the form
    return render_template(
        'engagements/create_job.html',
        users=serialized_users,
        clients=clients,
        services=services,
        templates=serialized_templates,
        now_local=now_local
    )

@job_bp.route('/api/task_templates/<int:service_id>')
@login_required
def get_task_templates(service_id):
    templates = TaskTemplate.query.filter_by(service_id=service_id).all()
    users = User.query.order_by(User.first_name).all()

    user_options = "".join([f'<option value="{u.id}">{u.full_name} ({u.role.value})</option>' for u in users])

    return jsonify([{
        'id': tpl.id,
        'title': tpl.title,
        'description': tpl.description,
        'user_options': user_options
    } for tpl in templates])

@job_bp.route('/jobs/<int:job_id>')
@login_required
def view_job(job_id):
    job = Job.query.get_or_404(job_id)

        # --- FIX IS HERE ---
    # 1. Define your local timezone
    local_tz = pytz.timezone('Africa/Nairobi')

    # 2. Convert the UTC time from the DB and add it as a new attribute
    #    (Assuming your DB field is named 'created_at'. Change if it's different.)
    if job.created_at:
        job.created_local = job.created_at.astimezone(local_tz)
    # --- END FIX ---
    
    # Assume 'users' for the modal is also queried here
    directors = User.query.filter_by(role='Director').all() # Or however you get partners

    # 1. Fetch all tasks and all VAT forms for this job.
    tasks = Task.query.filter_by(job_id=job_id).order_by(Task.deadline).all()
    vat_forms = VatFilingMonth.query.filter_by(job_id=job_id).all()

    # 2. Create a simple lookup map for the VAT forms.
    # The key is the month string ('Aug-2025'), the value is the form object.
    vat_forms_map = {form.month: form for form in vat_forms}

    # 3. Group TASKS by their deadline month. This is the primary grouping.
    monthly_data = defaultdict(lambda: {'tasks': [], 'vat_form': None})
    local_tz = pytz.timezone('Africa/Nairobi')

    for task in tasks:
        if task.deadline:
            # Group by the task's actual deadline month
            deadline_local = task.deadline.astimezone(local_tz)
            month_str = deadline_local.strftime('%b-%Y') # e.g., 'Sep-2025'
            monthly_data[month_str]['tasks'].append(task)

            # --- THIS IS THE KEY LOGIC ---
            # If this is a VAT task, find its corresponding form from the *previous* month.
            # --- FIX: Check if 'Tax Services' is in the job.services list ---
            is_tax_job = any(s.name == 'Tax Services' for s in job.services)
            if is_tax_job and task.task_template and task.task_template.title == 'VAT Returns':
                # Calculate the filing month (one month before the deadline)
                filing_month_date = deadline_local - relativedelta(months=1)
                filing_month_str = filing_month_date.strftime('%b-%Y') # e.g., 'Aug-2025'

                # Look up the correct form from our map
                correct_vat_form = vat_forms_map.get(filing_month_str)

                # Attach it to the CURRENT month's data bucket
                if correct_vat_form:
                    monthly_data[month_str]['vat_form'] = correct_vat_form

    # Sort the dictionary by date for chronological display
    # This is a bit complex, but ensures 'Jan-2025' comes before 'Feb-2025'
    sorted_monthly_data = dict(sorted(
        monthly_data.items(),
        key=lambda item: datetime.strptime(item[0], '%b-%Y'),
        reverse=True # Show most recent months first
    ))

    return render_template(
        'engagements/view_job.html',
        job=job,
        users=directors, # Pass the correct user list for the modal
        monthly_data=sorted_monthly_data
    )

@job_bp.route('/jobs')
@login_required
@supervisors_admins_directors
def list_jobs():
    # 1. Get the tab from the URL, default to 'ongoing'
    current_tab = request.args.get('tab', 'ongoing')
    page = request.args.get('page', 1, type=int)
    search_term = request.args.get('q', None)
    
    # 2. Set up common variables
    now_utc = datetime.utcnow()
    local_tz = pytz.timezone('Africa/Nairobi')
    today_start = datetime.combine(now_utc.date(), datetime.min.time())

    # 3. Define the one query we will use for all lists
    #    We add all the eager-loading (joinedload) here to prevent N+1 queries
    base_query = Job.query.options(
        joinedload(Job.client),
        joinedload(Job.creator),
        subqueryload(Job.services)
    ).filter(Job.deleted_at == None) # <-- Filter soft-deletes

    # 4. Filter the query based on the active tab

    if search_term:
        search_query = f"%{search_term}%"
        # We need to join the models we want to search on
        base_query = base_query.join(Job.client).join(Job.creator).filter(
            or_(
                Job.name.ilike(search_query),           # Search Engagement Name
                ## Job.description.ilike(search_query),    # Search Engagement Description
                Client.name.ilike(search_query),        # Search Client Name
                User.first_name.ilike(search_query),    # Search Creator First Name
                User.last_name.ilike(search_query)      # Search Creator Last Name
            )
        )

        
    if current_tab == 'ongoing':
        # Ongoing = All tasks are not 'COMPLETED'
        query = base_query.filter(
            Job.tasks.any(Task.status != TaskStatusEnum.COMPLETED)
        ).order_by(Job.created_at.desc())
                

    elif current_tab == 'completed_today':
        from sqlalchemy import func
    
        query = (
            base_query.join(Task, Job.id == Task.job_id)
            .filter(
                Task.status == TaskStatusEnum.COMPLETED,
                Task.updated_at >= today_start
            )
            .group_by(Job.id)  # Groups results so each Job appears once
            .order_by(func.max(Task.updated_at).desc()) # Orders by the most recent task update
        )

    elif current_tab == 'all':
        query = base_query.order_by(Job.created_at.desc())
        
    else: # Default to ongoing
        query = base_query.filter(
            Job.tasks.any(Task.status != TaskStatusEnum.COMPLETED)
        ).order_by(Job.created_at.desc())

    # 5. Paginate the final query
    pagination = query.paginate(page=page, per_page=15, error_out=False)

    # 6. Add task counts and local times (this is fast, in Python)
    for job in pagination.items:
        job.created_local = job.created_at.astimezone(local_tz)
        job.task_count = len(job.tasks) # Fast because tasks are pre-loaded
        
    return render_template(
        'engagements/list_jobs.html',
        pagination=pagination,
        current_tab=current_tab
    )

@job_bp.route('/jobs/<int:job_id>/vat-form/<month>')
@login_required
def view_vat_form_for_job(job_id, month):
    # --- Load Job and Related Summaries ---
    job = Job.query.options(
        db.joinedload(Job.client),
        # ... other joined loads ...
    ).get_or_404(job_id)

    # --- Load the SPECIFIC VAT FORM for the current month's data entry ---
    vat_form = VatFilingMonth.query.filter_by(job_id=job.id, month=month).first_or_404()
    
    # --- VAT SUMMARY: Query the VatMonthlySummary model ---
    all_months_abbr = [m.upper() for m in month_abbr[1:]]
    
    summaries = VatMonthlySummary.query.filter_by(job_id=job.id).all()
    # THIS IS THE CORRECTED LINE:
    summary_map = {s.month.upper()[:3]: s for s in summaries}

    vat_summary_data = []
    for m_abbr in all_months_abbr:
        summary = summary_map.get(m_abbr)
        if summary:
            vat_summary_data.append(summary)
        else:
            vat_summary_data.append(VatMonthlySummary(month=m_abbr)) 

    # --- Prepare Other Summaries ---
    banking_data_dict = {s.month: s for s in job.banking_summaries}
    salary_data_dict = {s.month: s for s in job.salary_summaries}


        # Calculate totals for VAT summary
    vat_totals = {
        'sales_zero_rated': sum(item.sales_zero_rated or 0 for item in vat_summary_data),
        'sales_exempt': sum(item.sales_exempt or 0 for item in vat_summary_data),
        'sales_vatable_16': sum(item.sales_vatable_16 or 0 for item in vat_summary_data),
        'sales_vatable_8': sum(item.sales_vatable_8 or 0 for item in vat_summary_data),
        'total_sales': sum(item.total_sales or 0 for item in vat_summary_data),
        'output_vat_16': sum(item.output_vat_16 or 0 for item in vat_summary_data),
        'output_vat_8': sum(item.output_vat_8 or 0 for item in vat_summary_data),
        'total_output_vat': sum(item.total_output_vat or 0 for item in vat_summary_data),
        'purchases_zero_rated': sum(item.purchases_zero_rated or 0 for item in vat_summary_data),
        'purchases_exempt': sum(item.purchases_exempt or 0 for item in vat_summary_data),
        'purchases_vatable_16': sum(item.purchases_vatable_16 or 0 for item in vat_summary_data),
        'purchases_vatable_8': sum(item.purchases_vatable_8 or 0 for item in vat_summary_data),
        'total_purchases': sum(item.total_purchases or 0 for item in vat_summary_data),
        'input_vat_16': sum(item.input_vat_16 or 0 for item in vat_summary_data),
        'input_vat_8': sum(item.input_vat_8 or 0 for item in vat_summary_data),
        'total_input_vat': sum(item.total_input_vat or 0 for item in vat_summary_data),
        'withheld_vat': sum(item.withheld_vat or 0 for item in vat_summary_data),
        'balance_bf': sum(item.balance_bf or 0 for item in vat_summary_data),
        'net_vat': sum(item.net_vat or 0 for item in vat_summary_data),
        'paid': sum(item.paid or 0 for item in vat_summary_data),
        'balance_cf': sum(item.balance_cf or 0 for item in vat_summary_data),
    }
    
    # Calculate banking totals
    total_banking_credits = sum(item.total_credits or 0 for item in job.banking_summaries)
    total_banking_net = sum(item.net_credits or 0 for item in job.banking_summaries)
    
    # Calculate salary totals
    total_salary = sum(item.gross_salary or 0 for item in job.salary_summaries)

    # --- Render Template ---
    return render_template(
        'tasks/_vat_form_partial.html',
        job=job,
        vat_form=vat_form,
        vat_summary_data=vat_summary_data,
        banking_data=banking_data_dict,
        salary_data=salary_data_dict,
        installment_summary=job.installment_tax_summary,
        tax_liabilities=job.tax_liabilities,
        total_banking_credits=total_banking_credits,
        total_banking_net=total_banking_net,
        total_salary=total_salary,
        vat_totals = vat_totals,
    )


@job_bp.route('/jobs/<int:job_id>/vat-form/<month>/autosave', methods=['POST'])
@login_required
def autosave_vat_form(job_id, month):
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data received'}), 400

    # Get the parent job object, which is needed by the new functions
    job = Job.query.get_or_404(job_id)

    try:
        vat_form = VatFilingMonth.query.filter_by(job_id=job_id, month=month).first_or_404()
        summary = VatMonthlySummary.query.filter_by(job_id=job_id, month=month).first()
        if not summary:
            summary = VatMonthlySummary(job_id=job_id, month=month)
            db.session.add(summary)

        # Delegate ALL the work
        update_historical_summaries(job_id=job_id, form_data=data)
        updated_summary = update_current_month_vat_data(vat_form=vat_form, summary=summary, form_data=data)
        update_banking_and_salary(job=job, form_data=data)
        update_installment_tax(job=job, form_data=data)
        update_tax_liabilities(job=job, form_data=data)
        # 3. As the manager, commit the transaction now that all work is done
        db.session.commit()
        
        # 4. Format and return the response
        # (This part is just for returning the nice, formatted numbers)
        return jsonify({
            'status': 'success',
            'message': 'Form and summary data saved successfully.',
            'updated_summary': {
                'month': updated_summary.month,
                'sales_zero_rated': f"{updated_summary.sales_zero_rated or 0:,.2f}",
                'sales_exempt': f"{updated_summary.sales_exempt or 0:,.2f}",
                'sales_vatable_16': f"{updated_summary.sales_vatable_16 or 0:,.2f}",
                'sales_vatable_8': f"{updated_summary.sales_vatable_8 or 0:,.2f}",
                'total_sales': f"{updated_summary.total_sales or 0:,.2f}",
                'output_vat_16': f"{updated_summary.output_vat_16 or 0:,.2f}",
                'output_vat_8': f"{updated_summary.output_vat_8 or 0:,.2f}",
                'total_output_vat': f"{updated_summary.total_output_vat or 0:,.2f}",
                'purchases_zero_rated': f"{updated_summary.purchases_zero_rated or 0:,.2f}",
                'purchases_exempt': f"{updated_summary.purchases_exempt or 0:,.2f}",
                'purchases_vatable_16': f"{updated_summary.purchases_vatable_16 or 0:,.2f}",
                'purchases_vatable_8': f"{updated_summary.purchases_vatable_8 or 0:,.2f}",
                'total_purchases': f"{updated_summary.total_purchases or 0:,.2f}",
                'input_vat_16': f"{updated_summary.input_vat_16 or 0:,.2f}",
                'input_vat_8': f"{updated_summary.input_vat_8 or 0:,.2f}",
                'total_input_vat': f"{updated_summary.total_input_vat or 0:,.2f}",
                'withheld_vat': f"{updated_summary.withheld_vat or 0:,.2f}",
                'balance_bf': f"{updated_summary.balance_bf or 0:,.2f}",
                'net_vat': f"{updated_summary.net_vat or 0:,.2f}",
                'paid': f"{updated_summary.paid or 0:,.2f}",
                'balance_cf': f"{updated_summary.balance_cf or 0:,.2f}",
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error during VAT form autosave: {e}")
        return jsonify({'status': 'error', 'message': 'A server error occurred.'}), 500


@job_bp.route('/jobs/<int:job_id>/vat-form/create', methods=['POST'])
@login_required
def create_vat_form(job_id):
    job = Job.query.get_or_404(job_id)

    month_from_form = request.form.get('month') # e.g., "Sep-2025"
    if not month_from_form:
        flash("Please provide a month.", "danger")
        return redirect(url_for('job.view_job', job_id=job.id))

    # --- FIX: Convert the received month string to a date and subtract one month ---
    try:
        # Create a datetime object from the task's deadline month string
        task_deadline_month_dt = datetime.strptime(month_from_form, '%b-%Y')
        # Calculate the actual month the VAT form is FOR
        vat_month_dt = task_deadline_month_dt - relativedelta(months=1)
        # Format it back to the consistent string format for the database
        correct_month_str = vat_month_dt.strftime('%b-%Y') # This will be "Aug-2025"
    except ValueError:
        flash("Invalid month format provided.", "danger")
        return redirect(url_for('job.view_job', job_id=job.id))

    # --- FIX: Use the CORRECT back-dated month string for checking and creating ---
    existing = VatFilingMonth.query.filter_by(job_id=job.id, month=correct_month_str).first()
    if existing:
        flash(f"VAT form for {correct_month_str} already exists.", "warning")
        return redirect(url_for('job.view_job', job_id=job.id))

    vat_form = VatFilingMonth(
        job_id=job.id,
        month=correct_month_str,
        nature_of_business=job.client.name
    )

    db.session.add(vat_form)
    db.session.commit()
    flash(f"VAT form for {correct_month_str} created successfully!", "success")
    return redirect(url_for('job.view_vat_form_for_job', job_id=job.id, month=correct_month_str))

@job_bp.route('/task/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    job_id = task.job_id # Store the job_id before deleting to redirect back

    # --- Authorization Check: Only creator or admin can delete ---
    if task.created_by_id != current_user.id and current_user.role != 'ADMIN':
        flash("You do not have permission to delete this task.", "danger")
        return redirect(url_for('job_bp.view_job_details', job_id=job_id))
    
    try:
        db.session.delete(task)
        db.session.commit()
        flash(f"Task '{task.title}' has been deleted.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting task: {e}", "danger")
    return redirect(url_for('job_bp.view_job_details', job_id=job_id))

@job_bp.route('/jobs/<int:job_id>/delete', methods=['POST'])
@login_required
def delete_job(job_id):
    """Deletes an entire engagement and all its related data."""
    job = Job.query.get_or_404(job_id)
    
    if not can_delete_job(job, current_user):
        flash('You are not authorised to perform this action.', 'danger')
        return redirect(url_for('job.view_job',job_id=job_id))
    try:
        
        now = datetime.utcnow()
        deleter_id = current_user.id

        # Mark the job as deleted
        job.deleted_at = now
        job.deleted_by_id = deleter_id

        # Mark associated tasks as deleted
        tasks_to_soft_delete = Task.query.filter(
            Task.job_id == job.id,
            Task.deleted_at.is_(None) # Only affect tasks not already soft-deleted
        ).all()
        for task in tasks_to_soft_delete:
            task.deleted_at = now
            task.deleted_by_id = deleter_id

        db.session.commit()
        flash(f"Engagement '{job.name}' has been moved to the trash.", 'success')

    except Exception as e:
        db.session.rollback()
        # Log the actual error for debugging
        current_app.logger.error(f"Error soft deleting job {job_id}: {e}", exc_info=True)
        flash("An error occurred while trying to move the engagement to trash.", "danger")
        # Redirect back to job view on error
        return redirect(url_for('job.view_job', job_id=job_id))

    # Redirect to the main list after successful soft delete
    return redirect(url_for('job.list_jobs'))

@job_bp.route('/jobs/<int:job_id>/download-vat-template')
@login_required
def download_vat_template(job_id):
    """Generates and serves a CSV template for importing VAT summary data."""
    
    # These are the exact column headers the user must fill
    # They match the fields in the VatMonthlySummary model
    headers = [
        'Month', 'sales_zero_rated', 'sales_exempt', 'sales_vatable_16', 
        'sales_vatable_8', 'output_vat_16', 'output_vat_8', 'purchases_zero_rated',
        'purchases_exempt', 'purchases_vatable_16', 'purchases_vatable_8', 
        'input_vat_16', 'input_vat_8', 'withheld_vat', 'balance_bf', 'paid'
    ]

    # Use io.StringIO to build the CSV in memory
    proxy = io.StringIO()
    writer = csv.writer(proxy)

    # Write the header row
    writer.writerow(headers)

    # Write an example row to guide the user
    example_row = [
        'Jan-2025', '10000.00', '5000.00', '150000.00', '25000.00', '24000.00',
        '2000.00', '0.00', '10000.00', '80000.00', '10000.00', '12800.00',
        '800.00', '2500.00', '0.00', '10500.00'
    ]
    writer.writerow(example_row)

    # Prepare the CSV for download
    mem = io.BytesIO()
    mem.write(proxy.getvalue().encode('utf-8'))
    mem.seek(0)
    proxy.close()

    return Response(
        mem,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=vat_summary_template.csv'}
    )

@job_bp.route('/jobs/<int:job_id>/import-vat-summary', methods=['POST'])
@login_required
def import_vat_summary(job_id):
    job = Job.query.get_or_404(job_id)
    
    # 1. Check if a file was uploaded
    if 'vat_summary_file' not in request.files:
        flash('No file part in the request.', 'danger')
        return redirect(url_for('job.view_job', job_id=job.id))
    
    file = request.files['vat_summary_file']
    if file.filename == '':
        flash('No file selected for uploading.', 'danger')
        return redirect(url_for('job.view_job', job_id=job.id))

    if file and file.filename.endswith('.csv'):
        try:
            # 2. Define the exact columns we expect from our template
            required_columns = {
                'Month', 'sales_zero_rated', 'sales_exempt', 'sales_vatable_16', 
                'paid' # Add all other required columns from the template here
            }

            # 3. Read the CSV file using pandas
            df = pd.read_csv(file)

            # 4. VALIDATE: Check if all required columns are present
            if not required_columns.issubset(df.columns):
                flash('The uploaded file is missing required columns. Please use the template.', 'danger')
                return redirect(url_for('job.view_job', job_id=job.id))

            # 5. PROCESS: Loop through each row and save the data
            for index, row in df.iterrows():
                month = row['Month']
                
                # Find existing record or create a new one
                summary = VatMonthlySummary.query.filter_by(job_id=job.id, month=month).first()
                if not summary:
                    summary = VatMonthlySummary(job_id=job.id, month=month)
                    db.session.add(summary)

                # Update fields from the CSV, converting to Decimal and handling potential errors
                for col in df.columns:
                    if hasattr(summary, col) and col != 'Month':
                        try:
                            # pd.to_numeric handles empty/NaN values gracefully
                            value = pd.to_numeric(row[col], errors='coerce')
                            if pd.notna(value):
                                setattr(summary, col, Decimal(value))
                        except (InvalidOperation, TypeError):
                            # Skip columns that can't be converted
                            pass
            
            # 6. COMMIT: Save all changes in a single transaction
            db.session.commit()
            flash(f'Successfully imported {len(df)} rows of VAT summary data!', 'success')

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"CSV Import Error: {e}")
            flash('An error occurred during the import process. Please check the file format.', 'danger')
            
        return redirect(url_for('job.view_job', job_id=job.id))

    else:
        flash('Invalid file type. Please upload a CSV file.', 'danger')
        return redirect(url_for('job.view_job', job_id=job.id))

@job_bp.route('/jobs/<int:job_id>/set-review-partner', methods=['POST'])
@login_required
def set_review_partner(job_id):
    job = Job.query.get_or_404(job_id)
    data = request.get_json()

    partner_id = data.get('review_partner_id')
    if not partner_id:
        return jsonify({'status': 'error', 'message': 'No partner selected'}), 400

    partner = User.query.get(partner_id)
    if not partner or partner.role != 'DIRECTOR':
        return jsonify({'status': 'error', 'message': 'Invalid partner selected'}), 400

    job.review_partner_id = partner.id
    db.session.commit()

    run_async_in_background(send_review_partner_set_notification_async, job.id)

    return jsonify({'status': 'success', 'message': 'Review partner set successfully'})