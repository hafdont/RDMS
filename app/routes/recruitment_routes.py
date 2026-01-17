# interview_app/app/routes/recruitment_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import *

recruitment_bp = Blueprint('recruitment', __name__)

@recruitment_bp.route("/recruitment_dashboard")
@login_required
def recruitment_dashboard():
    """Main recruitment hub dashboard"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # Get recruitment statistics
    pipelines = Pipeline.query.all()
    active_candidates = CandidateStage.query.filter(
        CandidateStage.status.in_(['not_started', 'in_progress'])
    ).count()
    
    total_candidates = CandidateStage.query.count()
    recent_applications = User.query.filter_by(
        role=RoleEnum.INTERVIEWEE.value
    ).order_by(User.id.desc()).limit(5).all()
    
    return render_template('recruitment/recruitment_dashboard.html',
                         pipelines=pipelines,
                         active_candidates=active_candidates,
                         total_candidates=total_candidates,
                         recent_applications=recent_applications)

@recruitment_bp.route("/recruitment/statistics")
@login_required
def recruitment_statistics():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # Detailed statistics
    pipeline_stats = []
    pipelines = Pipeline.query.all()
    
    for pipeline in pipelines:
        stages = Stage.query.filter_by(pipeline_id=pipeline.id).all()
        
        stage_stats = []
        for stage in stages:
            candidates = CandidateStage.query.filter_by(stage_id=stage.id).count()
            completed = CandidateStage.query.filter_by(
                stage_id=stage.id, status='completed'
            ).count()
            stage_stats.append({
                'name': stage.name,
                'total': candidates,
                'completed': completed,
                'completion_rate': (completed / candidates * 100) if candidates > 0 else 0
            })
        
        pipeline_stats.append({
            'pipeline': pipeline,
            'stages': stage_stats,
            'total_candidates': sum(s['total'] for s in stage_stats)
        })
    
    return render_template('recruitment/statistics.html',
                         pipeline_stats=pipeline_stats)

@recruitment_bp.route("/recruitment/candidates")
@login_required
def all_candidates():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    candidates = User.query.filter_by(role=RoleEnum.INTERVIEWEE.value).all()
    return render_template('recruitment/all_candidates.html',
                         candidates=candidates)