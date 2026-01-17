# interview_app/app/routes/main.py (UPDATED)
from flask import Blueprint, render_template, url_for, abort, redirect, flash, request, jsonify
from flask_login import login_required, current_user
from app.utils.db import db
from app.models import *
from sqlalchemy.orm import joinedload
from datetime import date, datetime, time
from app.services.users.user_service import get_user_for_dashboard
from app.services.users.user_dashboard_factory import DASHBOARD_BUILDERS

main_bp = Blueprint('main', __name__)

PER_PAGE = 15

@main_bp.route('/')
def home ():
    return render_template('index.html', user=current_user)


@main_bp.route("/home")
@login_required
def dashboard():
    user = get_user_for_dashboard(current_user.id)

    context = {
        "user": user,
        "PriorityEnum": PriorityEnum,
        "TaskStatusEnum": TaskStatusEnum,
        "DecisionEnum": DecisionEnum,
    }
    builder = DASHBOARD_BUILDERS.get(user.role)

    if not builder:
        flash("Your role does not have a dashboard.", "warning")
        abort(404)

    template, result = builder(user, context)

    if template == "redirect":
        return redirect(url_for(result))

    return render_template(template, **result)


@main_bp.route('/notifications/read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({'read': True})
    db.session.commit()
    return jsonify({'status': 'success'})

@main_bp.route('/notifications')
@login_required
def get_notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id, read=False)\
                               .order_by(Notification.created_at.desc())\
                               .all()
    return jsonify([n.to_dict() for n in notifs])

@main_bp.route('/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def mark_single_notification_read(notif_id):
    notif = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first()
    if notif and not notif.read:
        notif.read = True
        db.session.commit()
    return jsonify({'status': 'success'})

@main_bp.route('/notifications/all')
@login_required
def view_all_notifications():
    """Renders the page with the first page of user's notifications, marking unread ones as read."""
        
    # 2. Paginate the full list of notifications (all are now 'read' for new viewers)
    # The first page will contain the 15 most recent notifications, which includes all unread ones.
    pagination = Notification.query.filter_by(user_id=current_user.id)\
                                   .order_by(Notification.created_at.desc())\
                                   .options(\
                                       joinedload(Notification.actor) \
                                   )\
                                   .paginate(page=1, per_page=PER_PAGE, error_out=False)

    return render_template('user/notifications.html', 
                           pagination=pagination, # Pass the paginated object
                           title="All Notifications")

@main_bp.route('/api/notifications', methods=['GET'])
@login_required
def api_get_notifications_page():
    """
    AJAX endpoint to load subsequent pages of notifications.
    This will be called by the 'Load more' button.
    """
    # Get the requested page number from query parameters, default to 1
    page = request.args.get('page', 1, type=int)
    
    pagination = Notification.query.filter_by(user_id=current_user.id)\
                                   .order_by(Notification.created_at.desc())\
                                   .options(joinedload(Notification.actor))\
                                   .paginate(page=page, per_page=PER_PAGE, error_out=False)

    # Convert notification objects to a list of dictionaries for JSON response
    # Assuming the Notification model has a .to_dict() method or a simple dict can be created.
    notifications_data = []
    for notif in pagination.items:
        notifications_data.append({
            'id': notif.id,
            'message': notif.message,
            # Use ISO format for easy parsing and formatting on the client side
            'created_at_iso': notif.created_at.isoformat(), 
            'url': notif.url,
            'read': notif.read,
        })

    return jsonify({
        'notifications': notifications_data,
        'has_next': pagination.has_next,
        'next_page': pagination.next_num,
        'current_page': pagination.page
    })

