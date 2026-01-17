from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import *
from datetime import datetime, timedelta
import json

pipelines_bp = Blueprint('pipeline', __name__)

@pipelines_bp.route("/pipelines/create", methods=['GET', 'POST'])
@login_required
def create_pipeline():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    if request.method == 'POST':
        try:
            # Create pipeline
            pipeline = Pipeline(
                name=request.form['name'],
                description=request.form['description']
            )
            db.session.add(pipeline)
            db.session.flush()  # Get pipeline ID
            
            # Create stages
            stage_names = request.form.getlist('stage_names')
            stage_types = request.form.getlist('stage_types')
            stage_orders = request.form.getlist('stage_orders')
            
            
            for i in range(len(stage_names)):
                stage = Stage(
                    pipeline_id=pipeline.id,
                    name=stage_names[i],
                    stage_type=StageType[stage_types[i]],
                    order=int(stage_orders[i]),
                    
                )
                db.session.add(stage)
            
            db.session.commit()
            flash('Pipeline created successfully!', 'success')
            return redirect(url_for('pipeline.view_pipeline', pipeline_id=pipeline.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating pipeline: {str(e)}', 'danger')
    
    return render_template('pipelines/create_pipeline.html')

@pipelines_bp.route("/pipelines")
@login_required
def list_pipelines():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    pipelines = Pipeline.query.order_by(Pipeline.created_at.desc()).all()
    return render_template('pipelines/pipelines.html', pipelines=pipelines)

@pipelines_bp.route("/pipeline/<int:pipeline_id>")
@login_required
def view_pipeline(pipeline_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    
    # Get opportunities data
    opportunities_using = pipeline.opportunities
    all_opportunities = Opportunity.query.filter(
        Opportunity.deleted_at.is_(None),
        (Opportunity.pipeline_id.is_(None) | (Opportunity.pipeline_id != pipeline_id))
    ).all()
    print(all_opportunities)
    
    return render_template('pipelines/pipeline_view.html', 
                         pipeline=pipeline,
                         opportunities_using=opportunities_using,
                         all_opportunities=all_opportunities)

@pipelines_bp.route("/pipeline/<int:pipeline_id>/candidates")
@login_required
def manage_candidates(pipeline_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    
    # Get candidates already in this pipeline
    assigned_candidates = CandidateStage.query.join(Stage).filter(
        Stage.pipeline_id == pipeline_id
    ).all()
    
    # Get available candidates (interviewees not in this pipeline)
    assigned_user_ids = [cs.user_id for cs in assigned_candidates]
    available_candidates = User.query.filter(
        User.role == RoleEnum.INTERVIEWEE.value,
        User.id.in_(assigned_user_ids) if assigned_user_ids else True
    ).all()
    
    return render_template('pipelines/assign_candidates.html',
                         pipeline=pipeline,
                         available_candidates=available_candidates,
                         assigned_candidates=assigned_candidates)

@pipelines_bp.route("/pipeline/<int:pipeline_id>/assign", methods=['POST'])
@login_required
def assign_candidates(pipeline_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    candidate_ids = request.form.getlist('candidate_ids')
    
    if not candidate_ids:
        flash('No candidates selected.', 'warning')
        return redirect(url_for('pipeline.manage_candidates', pipeline_id=pipeline_id))
    
    try:
        # Get first stage of pipeline
        first_stage = Stage.query.filter_by(
            pipeline_id=pipeline_id, order=1
        ).first()
        
        if not first_stage:
            flash('Pipeline has no stages configured.', 'danger')
            return redirect(url_for('pipeline.manage_candidates', pipeline_id=pipeline_id))
        
        assigned_count = 0
        for candidate_id in candidate_ids:
            candidate = User.query.get(candidate_id)
            if candidate and candidate.role == RoleEnum.INTERVIEWEE.value:
                # Check if candidate already has a stage in this pipeline
                existing = CandidateStage.query.join(Stage).filter(
                    Stage.pipeline_id == pipeline_id,
                    CandidateStage.user_id == candidate_id
                ).first()
                
                if not existing:
                    candidate_stage = CandidateStage(
                        user_id=candidate_id,
                        stage_id=first_stage.id,
                        status='not_started'
                    )
                    db.session.add(candidate_stage)
                    assigned_count += 1
        
        db.session.commit()
        flash(f'Successfully assigned {assigned_count} candidates to pipeline.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error assigning candidates: {str(e)}', 'danger')
    
    return redirect(url_for('pipeline.manage_candidates', pipeline_id=pipeline_id)) 

# ======================
# PIPELINE OPPORTUNITIES MANAGEMENT
# ======================

@pipelines_bp.route("/pipeline/<int:pipeline_id>/opportunities")
@login_required
def pipeline_opportunities(pipeline_id):
    """View all opportunities using this pipeline"""
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    
    # Get opportunities using this pipeline
    opportunities_using = pipeline.opportunities
    
    # Get other opportunities (not using this pipeline)
    all_opportunities = Opportunity.query.filter(
        Opportunity.pipeline_id != pipeline_id,
        Opportunity.deleted_at == None  # Not deleted
    ).all()
    
    return render_template('admin/pipeline_opportunities.html',
                         pipeline=pipeline,
                         opportunities_using=opportunities_using,
                         all_opportunities=all_opportunities)


## proll not used till here. these are the new ones ## 


@pipelines_bp.route("/pipeline/<int:pipeline_id>/opportunities/json")
@login_required
def get_pipeline_opportunities_json(pipeline_id):
    """Get opportunities for this pipeline as JSON (for AJAX)"""
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    
    opportunities = []
    for opp in pipeline.opportunities:
        opportunities.append({
            'id': opp.id,
            'title': opp.title,
            'client': opp.display_client,
            'status': opp.status.value,
            'is_active': opp.is_active
        })
    
    return jsonify({
        'success': True,
        'pipeline_id': pipeline_id,
        'pipeline_name': pipeline.name,
        'opportunities': opportunities,
        'count': len(opportunities)
    })

@pipelines_bp.route("/pipeline/<int:pipeline_id>/opportunities/add", methods=['POST'])
@login_required
def add_opportunity_to_pipeline_ajax(pipeline_id):
    """Add opportunity to pipeline via AJAX"""
    data = request.get_json()
    
    if not data or 'opportunity_id' not in data:
        return jsonify({'success': False, 'error': 'Missing opportunity_id'}), 400
    
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    opportunity = Opportunity.query.get(data['opportunity_id'])
    
    if not opportunity:
        return jsonify({'success': False, 'error': 'Opportunity not found'}), 404
    
    try:
        opportunity.pipeline_id = pipeline_id
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Added {opportunity.title} to pipeline',
            'opportunity': {
                'id': opportunity.id,
                'title': opportunity.title,
                'client': opportunity.display_client
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pipelines_bp.route("/pipeline/<int:pipeline_id>/opportunities/<int:opportunity_id>/remove", methods=['POST'])
@login_required
def remove_opportunity_from_pipeline_ajax(pipeline_id, opportunity_id):
    """Remove opportunity from pipeline via AJAX"""
    pipeline = Pipeline.query.get_or_404(pipeline_id)
    opportunity = Opportunity.query.get_or_404(opportunity_id)
    
    if opportunity.pipeline_id != pipeline_id:
        return jsonify({'success': False, 'error': 'Opportunity not in this pipeline'}), 400
    
    try:
        # Check for candidates (optional safety check)
        candidates_count = CandidateStage.query.join(Stage).filter(
            Stage.pipeline_id == pipeline_id,
            CandidateStage.user_id.in_([app.user_id for app in opportunity.applications])
        ).count()
        
        if candidates_count > 0:
            return jsonify({
                'success': False, 
                'error': f'Cannot remove. {candidates_count} candidates in pipeline.'
            }), 400
        
        opportunity.pipeline_id = None
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Removed {opportunity.title} from pipeline'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500