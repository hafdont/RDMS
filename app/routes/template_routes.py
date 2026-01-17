from flask import Blueprint, request, redirect, url_for, flash
from app.models import *
from app.utils.db import db
from .auth_routes import supervisors_admins_directors
from flask_login import login_user, logout_user, login_required, current_user

template_bp = Blueprint('template', __name__)  # If not already defined

@template_bp.route('/services/<int:service_id>/templates/create', methods=['POST'])
@login_required
@supervisors_admins_directors
def create_task_template(service_id):
    service = Service.query.get_or_404(service_id)

    title = request.form.get('title')
    description = request.form.get('description')
    default_deadline_days = request.form.get('default_deadline_days')

    if not title:
        flash('Task title is required.', 'danger')
        return redirect(url_for('services.get_service', service_id=service.id))

    template = TaskTemplate(
        title=title,
        description=description,
        default_deadline_days=int(default_deadline_days) if default_deadline_days else None,
        service_id=service.id
    )

    db.session.add(template)
    db.session.commit()
    flash('Task template added successfully.', 'success')
    return redirect(url_for('services.get_service', service_id=service.id))

@template_bp.route('/templates/<int:template_id>/edit', methods=['POST'])
@login_required
@supervisors_admins_directors
def edit_task_template(template_id):
    template = TaskTemplate.query.get_or_404(template_id)

    template.title = request.form.get('title')
    template.description = request.form.get('description')
    template.estimated_minutes = request.form.get('estimated_minutes') or None
    template.default_deadline_days = request.form.get('default_deadline_days') or None

    db.session.commit()
    flash('Template updated successfully.', 'success')
    return redirect(url_for('services.get_service', service_id=template.service_id))


@template_bp.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@supervisors_admins_directors
def delete_task_template(template_id):
    template = TaskTemplate.query.get_or_404(template_id)
    service_id = template.service_id

    db.session.delete(template)
    db.session.commit()
    flash('Template deleted.', 'info')
    return redirect(url_for('services.get_service', service_id=service_id))
