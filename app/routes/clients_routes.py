from flask import Blueprint, request, jsonify, session, render_template, url_for, flash, redirect, current_app
from app.models import *
from flask_login import login_required, current_user
from app.utils.db import db
import io, csv
from .auth_routes import supervisors_admins_directors, directors_and_admins

client_bp= Blueprint('client', __name__)

@client_bp.route('/new/client', methods=['POST', 'GET'])
@login_required
@supervisors_admins_directors
def create_client():
    if request.method == 'POST':
        contact_email = request.form.get('contact_email') or None
        phone_number = request.form.get('phone_number') or None 
        name = request.form.get('name')

        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for('client.create_client'))

        if Client.query.filter_by(name=name).first():
            flash("Client with this name already exists.", "danger")
            return redirect(url_for('client.create_client'))

        client = Client(
            name=name,
            contact_email=contact_email,
            phone_number=phone_number
        )

        try:
            db.session.add(client)
            db.session.commit()
            flash(f"Client '{client.name}' added successfully!", "success")
            return redirect(url_for('client.get_clients'))
        except Exception as e:
            db.session.rollback()
            flash("An unexpected database error occurred.", "danger")
            return redirect(url_for('client.create_client'))

    return render_template('/client/new_client.html')

@client_bp.route('/clients', methods=['GET'])
@login_required
@supervisors_admins_directors
def get_clients():
    clients = Client.query.all()
    return render_template('/client/clientList.html', clients=clients)

@client_bp.route('/clients/<int:client_id>', methods=['GET'])
@login_required
@supervisors_admins_directors
def get_client_details(client_id):
    client = Client.query.get_or_404(client_id)

    # 2a) VAT filing forms grouped by year and month
    vat_forms = {}
    for job in client.jobs:
        for form in job.vat_filing_months:
            year = form.created_at.year
            month = form.created_at.strftime('%B')
            if year not in vat_forms:
                vat_forms[year] = {}
            if month not in vat_forms[year]:
                vat_forms[year][month] = []
            vat_forms[year][month].append(form)

    # 2b) Engagements (Jobs) and their tasks
    engagements = client.jobs

    # 3) Tasks grouped by status
    # Note: 'In Progress' includes 'Paused' and 'In Progress' statuses
    tasks_by_status = {
        'Completed': [],
        'Assigned': [],
        'In Progress': [],
        'Under Review': []
    }
    
    for job in client.jobs:
        for task in job.tasks:
            if task.status == TaskStatusEnum.COMPLETED:
                tasks_by_status['Completed'].append(task)
            elif task.status in [TaskStatusEnum.ASSIGNED, TaskStatusEnum.RE_ASSIGNED]:
                tasks_by_status['Assigned'].append(task)
            elif task.status in [TaskStatusEnum.IN_PROGRESS, TaskStatusEnum.PAUSED]:
                tasks_by_status['In Progress'].append(task)
            elif task.status in [TaskStatusEnum.REVIEW, TaskStatusEnum.MANAGER_REVIEW, TaskStatusEnum.PARTNER_REVIEW]:
                tasks_by_status['Under Review'].append(task)

    # 4) Task Approvers
    approvers = {}
    for job in client.jobs:
        for task in job.tasks:
            approver = "Not specified"
            # The line below has been corrected from task.created_by to task.creator
            if task.creator:
                creator_department = task.creator.department
                if creator_department and creator_department.reviewers:
                    approver = creator_department.reviewers[0].full_name
            # The original request was to query who created the task OR the supervisor to the department of the user assigned to the task.
            elif task.assigned_to:
                supervisor = task.assigned_to.get_supervisor()
                if supervisor:
                    approver = supervisor.full_name

            approvers[task.id] = approver

    return render_template('client/client_details.html',
                           client=client,
                           vat_forms=vat_forms,
                           engagements=engagements,
                           tasks_by_status=tasks_by_status,
                           approvers=approvers)

@client_bp.route('/upload_csv', methods=['POST'])
@supervisors_admins_directors
def upload_clients_csv():
    clients = Client.query.all()
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        # Attempt to decode using UTF-8 first
        file_content = file.stream.read().decode("utf-8")
    except UnicodeDecodeError:
        # If UTF-8 fails, try a more permissive encoding like latin-1
        file.stream.seek(0)
        file_content = file.stream.read().decode("latin-1")

    stream = io.StringIO(file_content, newline=None)
    reader = csv.DictReader(stream)

    added = 0
    skipped = 0
    errors = []
    for i, row in enumerate(reader, start=1):
        name = row.get('name')
        
        # --- NEW CODE: CONVERT EMPTY STRINGS TO NONE ---
        contact_email = row.get('contact_email')
        if contact_email == '':
            contact_email = None

        phone_number = row.get('phone_number')
        if phone_number == '':
            phone_number = None
        # ------------------------------------------------

        if not name:
            errors.append(f"Row {i}: missing 'name' field")
            continue
        if Client.query.filter_by(name=name).first():
            skipped += 1
            continue
        
        client = Client(
            name=name,
            contact_email=contact_email, # Use the new variable
            phone_number=phone_number    # Use the new variable
        )
        db.session.add(client)
        added += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

    return render_template('/client/clientList.html', clients=clients)

@client_bp.route('/<int:client_id>', methods=['GET'])
def get_client(client_id):
    client = Client.query.get_or_404(client_id)
    return jsonify({
        'id': client.id,
        'name': client.name,
        'contact_email': client.contact_email,
        'phone_number': client.phone_number
    })

@client_bp.route('/clients/<int:client_id>', methods=['PUT'])
@login_required
@supervisors_admins_directors
def update_client(client_id):
    client = Client.query.get_or_404(client_id)

    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 400
    
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided in the request.'}), 400
    

    if 'name' in data:
        existing_client = Client.query.filter(
            Client.id != client_id,
            Client.name == data['name']
        ).first()
        if existing_client:
            return jsonify({'error': 'A client with this name already exists.'}), 400
        client.name = data['name']
        
    if 'contact_email' in data:
        client.contact_email = data['contact_email'] or None

    if 'phone_number' in data:
        client.phone_number = data['phone_number'] or None

    try:
        db.session.commit()
        return jsonify({
            'message': 'Client updated successfully!', 
            'client_id': client.id,
            'client': {
                'name': client.name,
                'contact_email': client.contact_email,
                'phone_number': client.phone_number
            }
        }), 200
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[Error] Client Update Failed: {e}")
        return jsonify({'error': 'An error occurred while updating the client.'}), 500

@client_bp.route('/clients/<int:client_id>', methods=['DELETE'])
@login_required
@directors_and_admins
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    
    try:
        db.session.delete(client)
        db.session.commit()
        return jsonify({
            'message': 'Client deleted successfully.',
            'deleted_client_id': client_id
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[Error] Client Deletion Failed: {e}")
        return jsonify({'error': 'Failed to delete client.'}), 500