from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import *
from app.utils.db import db
from .auth_routes import directors_and_admins, directors_only, supervisors_admins_directors

services_bp = Blueprint('services', __name__)

@services_bp.route('/services/create', methods=['GET', 'POST'])
@supervisors_admins_directors
def create_service():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')

        if not name:
            flash('Service name is required.', 'danger')
            return redirect(request.url)

        existing = Service.query.filter_by(name=name).first()
        if existing:
            flash('Service already exists.', 'warning')
            return redirect(request.url)

        new_service = Service(name=name, description=description)
        db.session.add(new_service)
        db.session.commit()
        flash('Service created successfully!', 'success')
        return redirect(url_for('services.list_services'))

    return render_template('services/create_service.html')

@services_bp.route('/services', methods=['GET', 'POST'])
@supervisors_admins_directors
def list_services():
    services = Service.query.all()
    return render_template('services/services_list.html', services=services)

@services_bp.route('/services/<int:service_id>', methods=['GET'])
@supervisors_admins_directors
def get_service(service_id):
    service = Service.query.get_or_404(service_id)

    # Manually serialize task templates
    templates_json = [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "default_deadline_days": t.default_deadline_days,
        }
        for t in service.task_templates
    ]

    return render_template(
        'services/service_view.html',
        service=service,
        templates_json=templates_json
    )

@services_bp.route('/services/<int:service_id>/edit', methods=['POST'])
@supervisors_admins_directors
def edit_service(service_id):
    service = Service.query.get_or_404(service_id)

    service.name = request.form.get('name')
    service.description = request.form.get('description')

    db.session.commit()
    flash("Service updated successfully.", "success")
    return redirect(url_for('services.get_service', service_id=service.id))

@services_bp.route('/services/<int:service_id>/delete', methods=['POST'])
@supervisors_admins_directors
def delete_service(service_id):
    service = Service.query.get_or_404(service_id)

    # Optional Safety: Prevent deletion if service is linked to task templates
    if service.task_templates and len(service.task_templates) > 0:
        flash('Cannot delete service because it has associated task templates.', 'danger')
        return redirect(url_for('services.get_service', service_id=service_id))

    try:
        db.session.delete(service)
        db.session.commit()
        flash('Service deleted successfully!', 'success')
    except Exception as e:
        current_app.logger.error(f"Error deleting service {service.id}: {e}")
        db.session.rollback()
        flash('An error occurred while deleting the service.', 'danger')

    return redirect(url_for('services.list_services'))



