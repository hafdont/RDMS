# interview_app/app/routes/interview.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app import db
from app.models import *
import json # For handling JSON data in Question.options/choices

interview_bp = Blueprint('interview', __name__)



@interview_bp.route("/start_stage/<int:candidate_stage_id>")
@login_required
def start_stage(candidate_stage_id):
    if not current_user.has_role('INTERVIEWEE'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    
    # Verify ownership
    if candidate_stage.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.interviewee_dashboard'))
    
    # Check if previous stage is completed (if not first stage)
    if candidate_stage.stage.order > 1:
        previous_stage = Stage.query.filter_by(
            pipeline_id=candidate_stage.stage.pipeline_id,
            order=candidate_stage.stage.order - 1
        ).first()
        
        if previous_stage:
            previous_candidate_stage = CandidateStage.query.filter_by(
                user_id=current_user.id,
                stage_id=previous_stage.id
            ).first()
            
            if not previous_candidate_stage or previous_candidate_stage.status != 'completed':
                flash('You must complete the previous stage first.', 'warning')
                return redirect(url_for('main.interviewee_dashboard'))
    
    # Update stage status
    if candidate_stage.status == 'not_started':
        candidate_stage.status = 'in_progress'
        candidate_stage.scheduled_time = datetime.utcnow()
        db.session.commit()
    
    # Redirect based on stage type
    stage_type = candidate_stage.stage.stage_type
    
    if stage_type == StageType.technical_test:
        return redirect(url_for('interview.start_technical_test', candidate_stage_id=candidate_stage_id))
    elif stage_type == StageType.personality_test:
        return redirect(url_for('interview.start_personality_test', candidate_stage_id=candidate_stage_id))
    elif stage_type == StageType.physical_interview:
        return redirect(url_for('interview.physical_interview_info', candidate_stage_id=candidate_stage_id))
    else:
        flash('Unknown stage type.', 'danger')
        return redirect(url_for('main.interviewee_dashboard'))

@interview_bp.route("/stage_results/<int:candidate_stage_id>")
@login_required
def view_stage_results(candidate_stage_id):
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    
    # Verify ownership or admin access
    if not current_user.has_role('INTERVIEWEE') and candidate_stage.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    return render_template('interviewee/stage_results.html', candidate_stage=candidate_stage)


# ======================
# STAGE 1: TECHNICAL TEST
# ======================

@interview_bp.route("/technical_test/<int:candidate_stage_id>")
@login_required
def technical_test(candidate_stage_id):
    if not current_user.has_role('INTERVIEWEE'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    if candidate_stage.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # Get questions for this stage
    stage_questions = candidate_stage.stage.questions.order_by(Question.id.asc()).all()
    if not stage_questions:
        flash('No questions configured for this stage.', 'danger')
        return redirect(url_for('main.interviewee_dashboard'))
    
    # Get current question index
    question_index = request.args.get('question', 1, type=int)
    if question_index < 1 or question_index > len(stage_questions):
        question_index = 1
    
    current_question = stage_questions[question_index - 1]
    
    # Get answered questions
    answered_questions = Answer.query.filter_by(
        candidate_stage_id=candidate_stage_id
    ).with_entities(Answer.question_id).all()
    answered_question_ids = [aq.question_id for aq in answered_questions]
    
    # Get pre-filled answer if exists
    pre_filled_answer = Answer.query.filter_by(
        candidate_stage_id=candidate_stage_id,
        question_id=current_question.id
    ).first()
    
    # Calculate time remaining (60 minutes for technical test)
    time_remaining = 60 * 60  # 60 minutes in seconds
    if candidate_stage.scheduled_time:
        elapsed = (datetime.utcnow() - candidate_stage.scheduled_time).total_seconds()
        time_remaining = max(0, time_remaining - elapsed)
    
    return render_template('interview/technical_test.html',
                         candidate_stage_id=candidate_stage_id,
                         question=current_question,
                         current_index=question_index,
                         total_questions=len(stage_questions),
                         answered_questions=answered_question_ids,
                         pre_filled_answer=pre_filled_answer.text_answer if pre_filled_answer else None,
                         pre_selected_choice=pre_filled_answer.choice_id if pre_filled_answer else None,
                         time_remaining=int(time_remaining),
                         now_timestamp=int(datetime.utcnow().timestamp()))

@interview_bp.route("/submit_technical_answer/<int:candidate_stage_id>", methods=['POST'])
@login_required
def submit_technical_answer(candidate_stage_id):
    if current_user.role != UserRole.interviewee:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    if candidate_stage.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    question_id = request.form.get('question_id')
    selected_choice = request.form.get('selected_choice')
    open_ended_answer = request.form.get('open_ended_answer')
    action = request.form.get('action', 'next')
    
    question = Question.query.get_or_404(question_id)
    
    # Save answer
    answer = Answer.query.filter_by(
        candidate_stage_id=candidate_stage_id,
        question_id=question_id
    ).first()
    
    if not answer:
        answer = Answer(
            candidate_stage_id=candidate_stage_id,
            question_id=question_id,
            submitted_at=datetime.utcnow()
        )
        db.session.add(answer)
    
    if question.question_type == QuestionType.multiple_choice:
        answer.choice_id = selected_choice
        answer.text_answer = None
        
        # Auto-grade multiple choice
        selected_choice_obj = Choice.query.get(selected_choice)
        if selected_choice_obj and selected_choice_obj.is_correct:
            answer.is_correct = True
            answer.score = 1.0
        else:
            answer.is_correct = False
            answer.score = 0.0
    else:
        answer.text_answer = open_ended_answer
        answer.choice_id = None
        answer.is_correct = False  # Manual grading needed
        answer.score = 0.0
    
    db.session.commit()
    
    # Navigate to next question or finish
    if action == 'finish':
        return finish_technical_test(candidate_stage_id)
    else:
        next_question_index = int(request.args.get('question', 1)) + 1
        return redirect(url_for('interview.technical_test', 
                              candidate_stage_id=candidate_stage_id, 
                              question=next_question_index))

def finish_technical_test(candidate_stage_id):
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    candidate_stage.status = 'completed'
    candidate_stage.completed_at = datetime.utcnow()
    
    # Calculate score
    answers = Answer.query.filter_by(candidate_stage_id=candidate_stage_id).all()
    total_score = sum(answer.score for answer in answers)
    max_score = len(answers)
    
    candidate_stage.score = (total_score / max_score * 100) if max_score > 0 else 0
    
    db.session.commit()
    flash('Technical test completed successfully!', 'success')
    return redirect(url_for('main.interviewee_dashboard'))

# ======================
# STAGE 2: PERSONALITY TEST
# ======================

@interview_bp.route("/personality_test/<int:candidate_stage_id>")
@login_required
def personality_test(candidate_stage_id):
    if current_user.role != UserRole.interviewee:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    if candidate_stage.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # Get personality questions
    personality_questions = Question.query.filter_by(
        question_type=QuestionType.personality_test
    ).order_by(Question.id.asc()).all()
    
    if not personality_questions:
        flash('Personality test questions not configured.', 'danger')
        return redirect(url_for('main.interviewee_dashboard'))
    
    # Get current question index
    question_index = request.args.get('question_index', 1, type=int)
    if question_index < 1 or question_index > len(personality_questions):
        question_index = 1
    
    current_question = personality_questions[question_index - 1]
    
    return render_template('interview/personality_test.html',
                         candidate_stage_id=candidate_stage_id,
                         question=current_question,
                         current_question_index=question_index,
                         total_questions=len(personality_questions),
                         progress_percentage=(question_index / len(personality_questions)) * 100)

@interview_bp.route("/submit_personality_answer/<int:candidate_stage_id>", methods=['POST'])
@login_required
def submit_personality_answer(candidate_stage_id):
    if current_user.role != UserRole.interviewee:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    if candidate_stage.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    question_id = request.form.get('question_id')
    selected_choice_id = request.form.get('selected_choice')
    
    # Save personality answer
    answer = Answer.query.filter_by(
        candidate_stage_id=candidate_stage_id,
        question_id=question_id
    ).first()
    
    if not answer:
        answer = Answer(
            candidate_stage_id=candidate_stage_id,
            question_id=question_id,
            submitted_at=datetime.utcnow()
        )
        db.session.add(answer)
    
    answer.choice_id = selected_choice_id
    db.session.commit()
    
    # Calculate next question index
    total_questions = Question.query.filter_by(question_type=QuestionType.personality_test).count()
    current_index = int(request.args.get('question_index', 1))
    
    if current_index < total_questions:
        return redirect(url_for('interview.personality_test', 
                              candidate_stage_id=candidate_stage_id,
                              question_index=current_index + 1))
    else:
        return finish_personality_test(candidate_stage_id)

def finish_personality_test(candidate_stage_id):
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    candidate_stage.status = 'completed'
    candidate_stage.completed_at = datetime.utcnow()
    
    # Calculate personality traits and best-fit role
    calculate_personality_assessment(candidate_stage.user_id)
    
    db.session.commit()
    flash('Personality assessment completed! Your results are being analyzed.', 'success')
    return redirect(url_for('main.interviewee_dashboard'))

def calculate_personality_assessment(user_id):
    """Calculate personality traits and find best-fit role"""
    # Get all personality answers for this user
    answers = Answer.query.join(CandidateStage).filter(
        CandidateStage.user_id == user_id,
        Answer.question_id.in_(
            db.session.query(Question.id).filter_by(question_type=QuestionType.personality_test)
        )
    ).all()
    
    trait_scores = {}
    
    for answer in answers:
        if answer.choice_id:
            # Get trait weights for this choice
            trait_weights = TraitWeight.query.filter_by(choice_id=answer.choice_id).all()
            
            for tw in trait_weights:
                trait_name = tw.category.name
                if trait_name not in trait_scores:
                    trait_scores[trait_name] = 0
                trait_scores[trait_name] += tw.weight
    
    # Find best-fit role
    best_fit_role = find_best_fit_role(trait_scores)
    
    # Save assessment results
    assessment = AssessmentResult.query.filter_by(user_id=user_id).first()
    if not assessment:
        assessment = AssessmentResult(user_id=user_id)
        db.session.add(assessment)
    
    assessment.trait_scores_json = trait_scores
    assessment.best_fit_role_id = best_fit_role.id if best_fit_role else None
    
    db.session.commit()
    return trait_scores

def find_best_fit_role(trait_scores):
    """Find the role that best matches the candidate's trait scores"""
    roles = JobRole.query.all()
    best_role = None
    best_score = -1
    
    for role in roles:
        role_score = calculate_role_fit_score(role, trait_scores)
        if role_score > best_score:
            best_score = role_score
            best_role = role
    
    return best_role

def calculate_role_fit_score(role, trait_scores):
    """Calculate how well the candidate fits a specific role"""
    total_score = 0
    total_weight = 0
    
    # Get role trait requirements
    role_traits = RoleTraitWeight.query.filter_by(role_id=role.id).all()
    
    for rt in role_traits:
        trait_name = rt.trait.name
        if trait_name in trait_scores:
            # Calculate fit: (candidate_score * role_importance) / max_possible
            trait_fit = trait_scores[trait_name] * rt.weight
            total_score += trait_fit
            total_weight += rt.weight * 10  # Max possible trait score
    
    return (total_score / total_weight * 100) if total_weight > 0 else 0

# ======================
# STAGE 3: PHYSICAL INTERVIEW
# ======================

@interview_bp.route("/physical_interview/<int:candidate_stage_id>")
@login_required
def physical_interview_info(candidate_stage_id):
    if current_user.role != UserRole.interviewee:

        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    candidate_stage = CandidateStage.query.get_or_404(candidate_stage_id)
    if candidate_stage.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # In a real app, you'd have an InterviewSession model for physical interviews
    # For now, we'll use a placeholder
    interview_session = None
    
    return render_template('interview/physical_interview.html',
                         candidate_stage_id=candidate_stage_id,
                         candidate_stage=candidate_stage,
                         interview_session=interview_session)