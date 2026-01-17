# routes/opportunities.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
import json
from datetime import datetime
from functools import wraps
from .auth_routes import directors_and_admins
from app.utils.storage_service import storage_service

from app.models import (
    db, Opportunity, OpportunityStatus, OpportunityType, 
    Client, JobRole, Application, ApplicationStatus, Biodata, User, RoleEnum, Pipeline
)

opportunities_bp = Blueprint('opportunities', __name__)

# Helper function for role checking
def requires_roles(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'error')
                return redirect(url_for('auth.login'))
            
            user_has_role = False
            for role in roles:
                if current_user.has_role(role):
                    user_has_role = True
                    break
            
            if not user_has_role:
                flash('Access denied. Insufficient permissions.', 'error')
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

# function for evryone to see opportunities/careers
@opportunities_bp.route('/careers')
def careers():
    """Public careers page showing active opportunities"""
    opportunities = Opportunity.query.filter(
        Opportunity.status == OpportunityStatus.OPEN,
        Opportunity.deleted_at.is_(None),
        Opportunity.closing_date >= datetime.utcnow()
    ).order_by(Opportunity.created_at.desc()).all()
    
    # Increment views for each opportunity
    for opportunity in opportunities:
        opportunity.increment_views()
    db.session.commit()
    
    return render_template('opportunities/careers.html', opportunities=opportunities)

# endpoint to see a opportuity/
@opportunities_bp.route('/opportunity/<int:opportunity_id>')
def opportunity_detail(opportunity_id):
    """Detailed view of a single opportunity"""
    opportunity = Opportunity.query.get_or_404(opportunity_id)
    
    if opportunity.deleted_at or not opportunity.is_active:
        flash('This opportunity is no longer available.', 'warning')
        return redirect(url_for('opportunities.careers'))
    
    opportunity.increment_views()
    db.session.commit()
    
    return render_template('opportunities/opportunity_detail.html', opportunity=opportunity)

# endpoint to see a opportuity/
@opportunities_bp.route('/apply/<int:opportunity_id>', methods=['GET', 'POST'])
@login_required
def apply_opportunity(opportunity_id):
    """Apply for an opportunity"""
    opportunity = Opportunity.query.get_or_404(opportunity_id)
    
    if not opportunity.is_active:
        flash('This opportunity is no longer accepting applications.', 'warning')
        return redirect(url_for('opportunities.careers'))
    
    # Check if user already applied
    existing_application = Application.query.filter_by(
        opportunity_id=opportunity_id,
        applicant_user_id=current_user.id
    ).first()
    
    if existing_application:
        flash('You have already applied for this opportunity.', 'info')
        return redirect(url_for('opportunities.application_status', application_id=existing_application.id))
    
    if request.method == 'POST':
        try:
            # Handle file upload for the resume
            resume_path = None
            if 'resume' in request.files:
                resume_file = request.files['resume']
                if resume_file and resume_file.filename:
                    # Secure the filename
                    filename = secure_filename(resume_file.filename)
                    # Specify the folder for the CV
                    resume_path = f"applicants_cv/{current_user.id}_{int(datetime.utcnow().timestamp())}_{filename}"
                    
                    # Upload to DigitalOcean Spaces
                    from app.utils.storage_service import storage_service
                    upload_result = storage_service.upload_file(resume_file, folder='applicants_cv')
                    resume_path = upload_result['key']  # Store the key returned from the upload

            # Parse education history from form
            education_history = []
            education_count = int(request.form.get('education_count', 0))
            for i in range(education_count):
                institution = request.form.get(f'education_{i}_institution')
                if institution:  # Only add if institution is provided
                    education_history.append({
                        'institution': institution,
                        'qualification': request.form.get(f'education_{i}_qualification', ''),
                        'field_of_study': request.form.get(f'education_{i}_field_of_study', ''),
                        'start_date': request.form.get(f'education_{i}_start_date', ''),
                        'end_date': request.form.get(f'education_{i}_end_date', ''),
                        'is_current': bool(request.form.get(f'education_{i}_is_current')),
                        'grade': request.form.get(f'education_{i}_grade', ''),
                        'description': request.form.get(f'education_{i}_description', '')
                    })
            
            # Parse work experience from form
            work_experience = []
            work_count = int(request.form.get('work_count', 0))
            for i in range(work_count):
                company = request.form.get(f'work_{i}_company')
                if company:  # Only add if company is provided
                    work_experience.append({
                        'company': company,
                        'position': request.form.get(f'work_{i}_position', ''),
                        'start_date': request.form.get(f'work_{i}_start_date', ''),
                        'end_date': request.form.get(f'work_{i}_end_date', ''),
                        'is_current': bool(request.form.get(f'work_{i}_is_current')),
                        'responsibilities': request.form.get(f'work_{i}_responsibilities', ''),
                        'achievements': request.form.get(f'work_{i}_achievements', '')
                    })
            
            # Parse skills (comma-separated)
            skills = [skill.strip() for skill in request.form.get('skills', '').split(',') if skill.strip()]
            
            # Create or update biodata
            if current_user.biodata_entries:
                biodata = current_user.biodata_entries
            else:
                biodata = Biodata(user_id=current_user.id)
            
            biodata.full_name = request.form.get('full_name')
            biodata.email = request.form.get('email')
            biodata.phone = request.form.get('phone')
            biodata.address = request.form.get('address')
            biodata.date_of_birth = datetime.strptime(request.form.get('date_of_birth'), '%Y-%m-%d').date() if request.form.get('date_of_birth') else None
            biodata.nationality = request.form.get('nationality')
            biodata.education_history = education_history
            biodata.work_experience = work_experience
            biodata.skills = skills
            biodata.resume_path = resume_path  # Store the path from DigitalOcean Spaces

            db.session.add(biodata)
            db.session.flush()  # Ensure the biodata ID is available
            
            # Create application
            application = Application(
                opportunity_id=opportunity_id,
                applicant_user_id=current_user.id,
                biodata_id=biodata.id,
                cover_letter=request.form.get('cover_letter'),
                status=ApplicationStatus.SUBMITTED
            )
            
            db.session.add(application)
            db.session.commit()
            
            flash('Your application has been submitted successfully!', 'success')
            return redirect(url_for('opportunities.application_status', application_id=application.id))
            
        except Exception as e:
            db.session.rollback()
            flash('Error submitting application. Please try again.', 'error')
            current_app.logger.error(f'Application submission error: {str(e)}')
    
    # Pre-populate form data if user has existing biodata
    form_data = {}
    if current_user.biodata_entries:
        biodata = current_user.biodata_entries
        form_data = {
            'full_name': biodata.full_name,
            'email': biodata.email,
            'phone': biodata.phone,
            'address': biodata.address,
            'date_of_birth': biodata.date_of_birth.isoformat() if biodata.date_of_birth else '',
            'nationality': biodata.nationality,
            'skills': ', '.join(biodata.skills) if biodata.skills else ''
        }
    
    return render_template('opportunities/apply.html', 
                         opportunity=opportunity, 
                         form_data=form_data)

@opportunities_bp.route('/application/<int:application_id>')
@login_required
def application_status(application_id):
    """View application status"""
    application = Application.query.get_or_404(application_id)
    
    # Ensure user owns this application or is admin/director
    if application.applicant_user_id != current_user.id and not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'error')
        return redirect(url_for('main.index'))
    
    return render_template('opportunities/application_status.html', application=application)

# Admin routes for opportunity management
@opportunities_bp.route('/admin/opportunities')
@login_required
def admin_opportunities():
    """Admin view of all opportunities"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'error')
        return redirect(url_for('main.home'))
    
    opportunities = Opportunity.query.filter_by(deleted_at=None).order_by(Opportunity.created_at.desc()).all()
    clients = Client.query.filter_by(deleted_at=None).all()
    job_roles = JobRole.query.all()
    
    return render_template('opportunities/admin_opportunities.html', 
                         opportunities=opportunities, 
                         clients=clients, 
                         job_roles=job_roles)

@opportunities_bp.route('/admin/opportunity/new', methods=['GET', 'POST'])
@login_required
@directors_and_admins
def admin_create_opportunity():
    """Create new opportunity"""
    clients = Client.query.filter_by(deleted_at=None).all()
    job_roles = JobRole.query.all()
    pipelines = Pipeline.Query.all
    
    if request.method == 'POST':
        try:
            # Parse requirements from textarea
            requirements = [req.strip() for req in request.form.get('requirements', '').split('\n') if req.strip()]
            
            client_id = request.form.get('client_id')
            job_role_id = request.form.get('job_role_id')
            pipeline_id = request.form.get('pipeline_id')
            
            opportunity = Opportunity(
                title=request.form.get('title'),
                description=request.form.get('description'),
                requirements=requirements,
                benefits=request.form.get('benefits'),
                opportunity_type=OpportunityType(request.form.get('opportunity_type')),
                client_id=int(client_id) if client_id and client_id != '0' else None,
                client_name=request.form.get('client_name') if not client_id or client_id == '0' else None,
                job_role_id=int(job_role_id) if job_role_id and job_role_id != '0' else None,
                job_role_name=request.form.get('job_role_name') if not job_role_id or job_role_id == '0' else None,
                opening_date=datetime.strptime(request.form.get('opening_date'), '%Y-%m-%d'),
                closing_date=datetime.strptime(request.form.get('closing_date'), '%Y-%m-%d'),
                location=request.form.get('location'),
                is_remote=bool(request.form.get('is_remote')),
                status=OpportunityStatus.OPEN,
                created_by_id=current_user.id,
                pipeline_id=int(pipeline_id) if pipeline_id else None,
            )
            
            db.session.add(opportunity)
            db.session.commit()
            
            flash('Opportunity created successfully!', 'success')
            return redirect(url_for('opportunities.admin_opportunities'))
            
        except Exception as e:
            db.session.rollback()
            flash('Error creating opportunity. Please try again.', 'error')
            current_app.logger.error(f'Opportunity creation error: {str(e)}')
    
    return render_template('opportunities/create_opportunity.html', 
                         clients=clients, 
                         job_roles=job_roles,
                         pipelines=pipelines)

@opportunities_bp.route('/admin/opportunity/<int:opportunity_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_opportunity(opportunity_id):
    """Edit existing opportunity"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'): 
        flash('Access denied.', 'error')
        return redirect(url_for('main.index'))
    
    opportunity = Opportunity.query.get_or_404(opportunity_id)
    clients = Client.query.filter_by(deleted_at=None).all()
    job_roles = JobRole.query.all()
    pipelines = Pipeline.query.all()
    
    if request.method == 'POST':
        try:
            # Parse requirements from textarea
            requirements = [req.strip() for req in request.form.get('requirements', '').split('\n') if req.strip()]
            
            client_id = request.form.get('client_id')
            job_role_id = request.form.get('job_role_id')
            pipeline_id = request.form.get('pipeline_id')
            
            opportunity.title = request.form.get('title')
            opportunity.description = request.form.get('description')
            opportunity.requirements = requirements
            opportunity.benefits = request.form.get('benefits')
            opportunity.opportunity_type = OpportunityType(request.form.get('opportunity_type'))
            opportunity.client_id = int(client_id) if client_id and client_id != '0' else None
            opportunity.client_name = request.form.get('client_name') if not client_id or client_id == '0' else None
            opportunity.job_role_id = int(job_role_id) if job_role_id and job_role_id != '0' else None
            opportunity.job_role_name = request.form.get('job_role_name') if not job_role_id or job_role_id == '0' else None
            opportunity.opening_date = datetime.strptime(request.form.get('opening_date'), '%Y-%m-%d')
            opportunity.closing_date = datetime.strptime(request.form.get('closing_date'), '%Y-%m-%d')
            opportunity.location = request.form.get('location')
            opportunity.is_remote = bool(request.form.get('is_remote'))
            opportunity.status = OpportunityStatus(request.form.get('status'))
            opportunity.pipeline_id = int(pipeline_id) if pipeline_id else None
            
            db.session.commit()
            
            flash('Opportunity updated successfully!', 'success')
            return redirect(url_for('opportunities.admin_opportunities'))
            
        except Exception as e:
            db.session.rollback()
            flash('Error updating opportunity. Please try again.', 'error')
            current_app.logger.error(f'Opportunity update error: {str(e)}')
    
    return render_template('opportunities/edit_opportunity.html', 
                         opportunity=opportunity,
                         clients=clients, 
                         job_roles=job_roles, pipelines=pipelines)

@opportunities_bp.route('/admin/opportunity/<int:opportunity_id>/delete', methods=['POST'])
@login_required
def admin_delete_opportunity(opportunity_id):
    """Soft delete an opportunity"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'error')
        return redirect(url_for('main.index'))
    
    opportunity = Opportunity.query.get_or_404(opportunity_id)
    
    try:
        opportunity.deleted_at = datetime.utcnow()
        opportunity.deleted_by_id = current_user.id
        db.session.commit()
        
        flash('Opportunity deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting opportunity. Please try again.', 'error')
        current_app.logger.error(f'Opportunity deletion error: {str(e)}')
    
    return redirect(url_for('opportunities.admin_opportunities'))

@opportunities_bp.route('/admin/applications')
@login_required
def admin_applications():
    """Admin view of all applications"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'error')
        return redirect(url_for('main.index'))
    
    applications = Application.query.order_by(Application.submitted_at.desc()).all()
    
    return render_template('opportunities/applications.html', applications=applications)

@opportunities_bp.route('/admin/application/<int:application_id>/update_status', methods=['POST'])
@login_required
def admin_update_application_status(application_id):
    """Update application status"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    application = Application.query.get_or_404(application_id)
    
    try:
        new_status = request.form.get('status')
        application.status = ApplicationStatus(new_status)
        application.reviewed_at = datetime.utcnow()
        application.reviewed_by_id = current_user.id
        
        # If status is "called_for_interview", add INTERVIEWEE role to user
        if new_status == ApplicationStatus.CALLED_FOR_INTERVIEW.value:
            applicant_user = application.applicant_user
            if not applicant_user.has_role('INTERVIEWEE'):
                applicant_user.add_secondary_role('INTERVIEWEE')
        
        db.session.commit()
        
        flash('Application status updated successfully!', 'success')
        return jsonify({'success': True, 'message': 'Status updated'})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Application status update error: {str(e)}')
        return jsonify({'success': False, 'message': 'Error updating status'}), 500

@opportunities_bp.route('/admin/application/<int:application_id>/details')
@login_required
def admin_application_details(application_id):
    """Get application details for modal"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        return "Access denied", 403
    
    application = Application.query.get_or_404(application_id)
    return render_template('partials/application_details.html', application=application)

@opportunities_bp.route('/admin/biodata/<int:biodata_id>/details')
@login_required
def admin_biodata_details(biodata_id):
    """Get biodata details for modal"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        return "Access denied", 403
    
    biodata = Biodata.query.get_or_404(biodata_id)
    return render_template('partials/biodata_details.html', biodata=biodata)


@opportunities_bp.route('/my-applications')
@login_required
def my_applications():
    """View all applications submitted by the current user"""
    applications = Application.query.filter_by(
        applicant_user_id=current_user.id
    ).order_by(Application.submitted_at.desc()).all()
    
    return render_template('opportunities/my_applications.html', applications=applications)