from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_, and_
from datetime import datetime
from app.models import (
    User, Task, Job, Department, Client, Service, TaskTemplate, Sheet,
    RoleEnum, db
)

recycle_bin_bp = Blueprint('recycle_bin', __name__)

def get_soft_deletable_models():
    """Return models that have soft delete capability"""
    return [Task, Job, User, Department, Client, Service, TaskTemplate, Sheet]


@recycle_bin_bp.route('/recycle-bin')
@login_required
def view_recycle_bin():
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Changed to 10 per page as requested
    model_type = request.args.get('type', 'all')
    
    # Calculate pagination indices
    start_index = (page - 1) * per_page + 1
    
    # For regular users - only show their own deleted items
    if current_user.role not in ['DIRECTOR', 'ADMIN']:
        deleted_items = []
        stats = {'tasks': 0, 'jobs': 0}
        
        if model_type in ['all', 'tasks']:
            user_tasks = Task.query.filter(
                Task.deleted_at.isnot(None),
                Task.deleted_by_id == current_user.id
            ).all()
            stats['tasks'] = len(user_tasks)
            for task in user_tasks:
                deleted_items.append({
                    'type': 'Task',
                    'object': task,
                    'deleted_at': task.deleted_at,
                    'deleted_by': task.deleted_by
                })
        
        if model_type in ['all', 'jobs']:
            user_jobs = Job.query.filter(
                Job.deleted_at.isnot(None),
                Job.deleted_by_id == current_user.id
            ).all()
            stats['jobs'] = len(user_jobs)
            for job in user_jobs:
                deleted_items.append({
                    'type': 'Engagement',
                    'object': job,
                    'deleted_at': job.deleted_at,
                    'deleted_by': job.deleted_by
                })
        
        # Sort by deletion date
        deleted_items.sort(key=lambda x: x['deleted_at'], reverse=True)
        
        # Pagination
        total_count = len(deleted_items)
        total_pages = (total_count + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_items = deleted_items[start_idx:end_idx]
        end_index = min(start_idx + len(paginated_items), total_count)
        
        return render_template('recycle_bin.html',
                            deleted_items=paginated_items,
                            page=page,
                            per_page=per_page,
                            total_count=total_count,
                            total_pages=total_pages,
                            start_index=start_index,
                            end_index=end_index,
                            model_type=model_type,
                            stats=stats,
                            is_director=False)
    
    else:  # Directors/Admins - see everything
        stats = {
            'tasks': Task.query.filter(Task.deleted_at.isnot(None)).count(),
            'jobs': Job.query.filter(Job.deleted_at.isnot(None)).count(),
            'users': User.query.filter(User.deleted_at.isnot(None)).count(),
            'departments': Department.query.filter(Department.deleted_at.isnot(None)).count(),
            'clients': Client.query.filter(Client.deleted_at.isnot(None)).count(),
            'services': Service.query.filter(Service.deleted_at.isnot(None)).count(),
        }
        
        if model_type == 'tasks':
            query = Task.query.filter(Task.deleted_at.isnot(None))
            total_count = query.count()
            items = query.order_by(Task.deleted_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            deleted_items = [{
                'type': 'Task',
                'object': item,
                'deleted_at': item.deleted_at,
                'deleted_by': item.deleted_by
            } for item in items.items]
            
        elif model_type == 'jobs':
            query = Job.query.filter(Job.deleted_at.isnot(None))
            total_count = query.count()
            items = query.order_by(Job.deleted_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            deleted_items = [{
                'type': 'Engagement',
                'object': item,
                'deleted_at': item.deleted_at,
                'deleted_by': item.deleted_by
            } for item in items.items]
            
        elif model_type == 'users':
            query = User.query.filter(User.deleted_at.isnot(None))
            total_count = query.count()
            items = query.order_by(User.deleted_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            deleted_items = [{
                'type': 'User',
                'object': item,
                'deleted_at': item.deleted_at,
                'deleted_by': item.deleted_by
            } for item in items.items]
            
        elif model_type == 'departments':
            query = Department.query.filter(Department.deleted_at.isnot(None))
            total_count = query.count()
            items = query.order_by(Department.deleted_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            deleted_items = [{
                'type': 'Department',
                'object': item,
                'deleted_at': item.deleted_at,
                'deleted_by': item.deleted_by
            } for item in items.items]
            
        elif model_type == 'clients':
            query = Client.query.filter(Client.deleted_at.isnot(None))
            total_count = query.count()
            items = query.order_by(Client.deleted_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            deleted_items = [{
                'type': 'Client',
                'object': item,
                'deleted_at': item.deleted_at,
                'deleted_by': item.deleted_by
            } for item in items.items]
            
        elif model_type == 'services':
            query = Service.query.filter(Service.deleted_at.isnot(None))
            total_count = query.count()
            items = query.order_by(Service.deleted_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            deleted_items = [{
                'type': 'Service',
                'object': item,
                'deleted_at': item.deleted_at,
                'deleted_by': item.deleted_by
            } for item in items.items]
            
        else:  # 'all' - show all deleted items
            all_deleted = []
            
            # Get all deleted items from different models
            models_to_query = [
                (Task, 'Task'),
                (Job, 'Engagement'),
                (User, 'User'),
                (Department, 'Department'),
                (Client, 'Client'),
                (Service, 'Service')
            ]
            
            for model_class, item_type in models_to_query:
                items = model_class.query.filter(model_class.deleted_at.isnot(None))\
                                      .order_by(model_class.deleted_at.desc()).all()
                for item in items:
                    all_deleted.append({
                        'type': item_type,
                        'object': item,
                        'deleted_at': item.deleted_at,
                        'deleted_by': item.deleted_by
                    })
            
            # Sort all by deletion date
            all_deleted.sort(key=lambda x: x['deleted_at'], reverse=True)
            
            # Pagination
            total_count = len(all_deleted)
            total_pages = (total_count + per_page - 1) // per_page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            deleted_items = all_deleted[start_idx:end_idx]
            end_index = min(start_idx + len(deleted_items), total_count)
            
            return render_template('recycle_bin.html',
                                deleted_items=deleted_items,
                                page=page,
                                per_page=per_page,
                                total_count=total_count,
                                total_pages=total_pages,
                                start_index=start_index,
                                end_index=end_index,
                                model_type=model_type,
                                stats=stats,
                                is_director=True)
        
        # For single model type queries with SQLAlchemy pagination
        total_pages = items.pages
        end_index = min(start_index + len(deleted_items) - 1, total_count)
        
        return render_template('recycle_bin.html',
                            deleted_items=deleted_items,
                            page=page,
                            per_page=per_page,
                            total_count=total_count,
                            total_pages=total_pages,
                            start_index=start_index,
                            end_index=end_index,
                            model_type=model_type,
                            stats=stats,
                            is_director=True,
                            pagination=items)



@recycle_bin_bp.route('/recycle-bin/restore/<item_type>/<int:item_id>', methods=['POST'])
@login_required
def restore_item(item_type, item_id):
    """Restore a soft-deleted item"""
    model_map = {
        'task': Task,
        'job': Job,
        'user': User,
        'department': Department,
        'client': Client,
        'service': Service,
        'template': TaskTemplate,
        'sheet': Sheet
    }
    
    model_class = model_map.get(item_type.lower())
    if not model_class:
        flash('Invalid item type', 'error')
        return redirect(url_for('recycle_bin.view_recycle_bin'))
    
    item = model_class.query.get_or_404(item_id)
    
    # Check permissions
    if current_user.role not in ['DIRECTOR', 'ADMIN']:
        if item.deleted_by_id != current_user.id:
            flash('You can only restore items you deleted', 'error')
            return redirect(url_for('recycle_bin.view_recycle_bin'))
    
    # Restore the item
    item.deleted_at = None
    item.deleted_by_id = None
    db.session.commit()
    
    flash(f'{item_type.title()} restored successfully', 'success')
    return redirect(url_for('recycle_bin.view_recycle_bin'))

@recycle_bin_bp.route('/recycle-bin/permanent-delete/<item_type>/<int:item_id>', methods=['POST'])
@login_required
def permanent_delete(item_type, item_id):
    """Permanently delete an item (only for directors/admins)"""
    if current_user.role not in ['DIRECTOR', 'ADMIN']:
        flash('You do not have permission to permanently delete items', 'error')
        return redirect(url_for('recycle_bin.view_recycle_bin'))
    
    model_map = {
        'task': Task,
        'job': Job,
        'user': User,
        'department': Department,
        'client': Client,
        'service': Service,
        'template': TaskTemplate,
        'sheet': Sheet
    }
    
    model_class = model_map.get(item_type.lower())
    if not model_class:
        flash('Invalid item type', 'error')
        return redirect(url_for('recycle_bin.view_recycle_bin'))
    
    item = model_class.query.get_or_404(item_id)
    
    try:
        db.session.delete(item)
        db.session.commit()
        flash(f'{item_type.title()} permanently deleted', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting item: {str(e)}', 'error')
    
    return redirect(url_for('recycle_bin.view_recycle_bin'))

@recycle_bin_bp.route('/recycle-bin/stats')
@login_required
def get_recycle_bin_stats():
    """Get statistics for the recycle bin (used for the dashboard card)"""
    if current_user.role not in ['DIRECTOR', 'ADMIN']:
        # Regular users - only count their own deleted items
        user_deleted_count = (
            Task.query.filter(
                Task.deleted_at.isnot(None),
                Task.deleted_by_id == current_user.id
            ).count() +
            Job.query.filter(
                Job.deleted_at.isnot(None),
                Job.deleted_by_id == current_user.id
            ).count()
        )
        return jsonify({'count': user_deleted_count})
    else:
        # Directors/Admins - count all deleted items
        total_deleted = (
            Task.query.filter(Task.deleted_at.isnot(None)).count() +
            Job.query.filter(Job.deleted_at.isnot(None)).count() +
            User.query.filter(User.deleted_at.isnot(None)).count() +
            Department.query.filter(Department.deleted_at.isnot(None)).count() +
            Client.query.filter(Client.deleted_at.isnot(None)).count() +
            Service.query.filter(Service.deleted_at.isnot(None)).count() +
            TaskTemplate.query.filter(TaskTemplate.deleted_at.isnot(None)).count() +
            Sheet.query.filter(Sheet.deleted_at.isnot(None)).count()
        )
        return jsonify({'count': total_deleted})