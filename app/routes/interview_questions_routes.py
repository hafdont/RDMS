# interview_app/app/routes/interview_questions_routes.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import *
from datetime import datetime

interview_questions_bp = Blueprint('interview_questions', __name__)

# ======================
# QUESTION CATEGORIES MANAGEMENT
# ======================

@interview_questions_bp.route("/interview_questions/categories")
@login_required
def manage_categories():
    
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    categories = QuestionCategory.query.all()
    return render_template('interview_questions/manage_categories.html', categories=categories)

@interview_questions_bp.route("/interview_questions/categories/new", methods=['POST'])
@login_required
def new_category():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    name = request.form.get('name')
    if not name:
        flash('Category name is required.', 'danger')
        return redirect(url_for('interview_questions.manage_categories'))
    
    # Check if category already exists
    existing = QuestionCategory.query.filter_by(name=name).first()
    if existing:
        flash('Category already exists.', 'danger')
        return redirect(url_for('interview_questions.manage_categories'))
    
    try:
        category = QuestionCategory(name=name)
        db.session.add(category)
        db.session.commit()
        flash('Category created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating category: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.manage_categories'))

@interview_questions_bp.route("/interview_questions/categories/<int:category_id>/delete", methods=['POST'])
@login_required
def delete_category(category_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    category = QuestionCategory.query.get_or_404(category_id)
    
    # Check if category is used by any questions
    if category.questions.count() > 0:
        flash('Cannot delete category that has questions assigned to it.', 'danger')
        return redirect(url_for('interview_questions.manage_categories'))
    
    try:
        db.session.delete(category)
        db.session.commit()
        flash('Category deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting category: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.manage_categories'))

# ======================
# TECHNICAL QUESTIONS MANAGEMENT
# ======================

@interview_questions_bp.route("/interview_questions/technical")
@login_required
def technical_questions():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    categories = QuestionCategory.query.all()
    technical_questions = Question.query.filter(
        Question.question_type.in_([QuestionType.multiple_choice, QuestionType.open_ended])
    ).all()
    
    return render_template('interview_questions/technical_questions.html', 
                         questions=technical_questions, 
                         categories=categories)

@interview_questions_bp.route("/interview_questions/technical/new", methods=['GET', 'POST'])
@login_required
def new_technical_question():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    categories = QuestionCategory.query.all()
    
    if request.method == 'POST':
        try:
            text = request.form.get('text')
            question_type = request.form.get('question_type')
            category_id = request.form.get('category_id')
            
            if not text or not question_type:
                flash('Question text and type are required.', 'danger')
                return render_template('interview_questions/create_technical_question.html', 
                                     categories=categories)
            
            # Create question
            question = Question(
                text=text,
                question_type=QuestionType[question_type],
                category_id=category_id if category_id else None
            )
            db.session.add(question)
            db.session.flush()  # Get question ID
            
            # Handle choices for multiple choice questions
            if question_type == 'multiple_choice':
                choice_texts = request.form.getlist('choice_text[]')
                choice_correct = request.form.getlist('choice_correct[]')
                
                if len(choice_texts) < 2:
                    flash('Multiple choice questions require at least 2 choices.', 'danger')
                    return render_template('interview_questions/create_technical_question.html', 
                                         categories=categories)
                
                for i, choice_text in enumerate(choice_texts):
                    if choice_text.strip():  # Only add non-empty choices
                        is_correct = str(i) in choice_correct
                        choice = Choice(
                            question_id=question.id,
                            text=choice_text,
                            is_correct=is_correct
                        )
                        db.session.add(choice)
            
            db.session.commit()
            flash('Technical question created successfully!', 'success')
            return redirect(url_for('interview_questions.technical_questions'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating question: {str(e)}', 'danger')
    
    return render_template('interview_questions/create_technical_question.html', 
                         categories=categories)


@interview_questions_bp.route("/interview_questions/technical/<int:question_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_technical_question(question_id):
    # Ensure user has the correct role
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # Fetch the question and all categories
    question = Question.query.get_or_404(question_id)
    categories = QuestionCategory.query.all()
    
    if request.method == 'POST':
        try:
            # Update the question text
            question.text = request.form.get('text')
            
            # Get category_id from form, handle empty strings and invalid input
            category_id = request.form.get('category_id')

            if category_id == '' or category_id is None:
                question.category_id = None  # If category is not selected, set to None
            else:
                # Ensure the category exists before setting it
                category = QuestionCategory.query.get(category_id)
                if category:
                    question.category_id = category.id
                else:
                    flash('Invalid category selected.', 'danger')
                    return redirect(url_for('interview_questions.edit_technical_question', question_id=question.id))
            
            # Check if question type is being changed
            new_question_type = request.form.get('question_type')
            if QuestionType[new_question_type] != question.question_type:
                # If type changed, delete existing choices
                Choice.query.filter_by(question_id=question.id).delete()
                question.question_type = QuestionType[new_question_type]
            
            # Handle choices for multiple-choice questions
            if question.question_type == QuestionType.multiple_choice:
                choice_texts = request.form.getlist('choice_text[]')
                choice_correct = request.form.getlist('choice_correct[]')
                choice_ids = request.form.getlist('choice_id[]')
                
                # Update or create choices
                for i, choice_text in enumerate(choice_texts):
                    if choice_text.strip():  # Ensure no empty choices are added
                        choice_id = choice_ids[i] if i < len(choice_ids) else None
                        is_correct = str(i) in choice_correct
                        
                        if choice_id:
                            # Update existing choice
                            choice = Choice.query.get(choice_id)
                            if choice:
                                choice.text = choice_text
                                choice.is_correct = is_correct
                        else:
                            # Create new choice
                            choice = Choice(
                                question_id=question.id,
                                text=choice_text,
                                is_correct=is_correct
                            )
                            db.session.add(choice)
            
            # Commit the changes to the database
            db.session.commit()
            flash('Question updated successfully!', 'success')
            return redirect(url_for('interview_questions.technical_questions'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating question: {str(e)}', 'danger')
    
    # Render the edit page with the current question and available categories
    return render_template('interview_questions/edit_technical_question.html', 
                         question=question, 
                         categories=categories)


@interview_questions_bp.route("/interview_questions/technical/<int:question_id>/delete", methods=['POST'])
@login_required
def delete_technical_question(question_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    question = Question.query.get_or_404(question_id)
    
    try:
        # Delete associated choices first
        Choice.query.filter_by(question_id=question_id).delete()
        # Delete question
        db.session.delete(question)
        db.session.commit()
        flash('Question deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting question: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.technical_questions'))

# ======================
# PERSONALITY QUESTIONS MANAGEMENT
# ======================

@interview_questions_bp.route("/interview_questions/personality")
@login_required
def personality_questions():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    all_traits = PersonalityTrait.query.all()
    
    personality_questions = Question.query.filter_by(
        question_type=QuestionType.personality_test
    ).all()
    
    return render_template('interview_questions/personality_questions.html', 
                         questions=personality_questions, all_traits=all_traits)

@interview_questions_bp.route("/interview_questions/personality/new", methods=['GET', 'POST'])
@login_required
def new_personality_question():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # Get personality traits instead of categories
    personality_traits = PersonalityTrait.query.all()  # CHANGED
    
    if request.method == 'POST':
        try:
            text = request.form.get('text')
            trait_id = request.form.get('trait_id')  # CHANGED from category_id
            
            if not text or not trait_id:
                flash('Question text and trait are required.', 'danger')
                return render_template('interview_questions/create_personality_question.html', 
                                     personality_traits=personality_traits)  # CHANGED
            
            # Create personality question (NO category_id for personality questions)
            question = Question(
                text=text,
                question_type=QuestionType.personality_test,
                category_id=None  # Personality questions don't have category_id
            )
            db.session.add(question)
            db.session.flush()
            
            # Handle choices with trait weights
            choice_texts = request.form.getlist('choice_text[]')
            choice_weights = request.form.getlist('choice_weight[]')
            
            for i, choice_text in enumerate(choice_texts):
                if choice_text.strip():
                    weight = float(choice_weights[i]) if i < len(choice_weights) else 0.0
                    
                    choice = Choice(
                        question_id=question.id,
                        text=choice_text,
                        is_correct=False
                    )
                    db.session.add(choice)
                    db.session.flush()
                    
                    # Create trait weight linking to PersonalityTrait
                    trait_weight = TraitWeight(
                        choice_id=choice.id,
                        trait_id=trait_id,  # CHANGED from category_id
                        weight=weight
                    )
                    db.session.add(trait_weight)
            
            db.session.commit()
            flash('Personality question created successfully!', 'success')
            return redirect(url_for('interview_questions.personality_questions'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating personality question: {str(e)}', 'danger')
    
    return render_template('interview_questions/create_personality_question.html', 
                         personality_traits=personality_traits)  # CHANGED


@interview_questions_bp.route("/interview_questions/personality/<int:question_id>/edit", methods=['GET', 'POST'])
@login_required
def edit_personality_question(question_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # Retrieve the question and all personality traits
    question = Question.query.get_or_404(question_id)
    personality_traits = PersonalityTrait.query.all()  # Get all personality traits
    
    if request.method == 'POST':
        try:
            # Get form data
            question.text = request.form.get('text')
            trait_id = request.form.get('trait_id')  # Get selected personality trait ID from form
            
            # Validate that a trait was selected
            if not trait_id:
                flash('Personality trait is required for personality questions.', 'danger')
                return redirect(url_for('interview_questions.edit_personality_question', question_id=question_id))
            
            # 1. Associate the selected PersonalityTrait to the Question
            question.personality_trait_id = int(trait_id)  # Link the personality trait to the question

            # 2. Update existing choices
            choice_texts = request.form.getlist('choice_text[]')
            choice_weights = request.form.getlist('choice_weight[]')
            
            # Validate that at least 2 choices are provided
            if len(choice_texts) < 2:
                flash('Personality questions require at least 2 choices.', 'danger')
                return redirect(url_for('interview_questions.edit_personality_question', question_id=question_id))
            
            # Iterate over the current choices and update their text and trait weights if necessary
            for idx, choice in enumerate(question.choices):
                if idx < len(choice_texts):
                    new_text = choice_texts[idx].strip()
                    new_weight = float(choice_weights[idx]) if idx < len(choice_weights) else 0.0
                    
                    # If the text or weight has changed, update the choice and trait weight
                    if choice.text != new_text or (choice.trait_weights and choice.trait_weights[0].weight != new_weight):
                        choice.text = new_text
                        
                        if choice.trait_weights:
                            # Update existing trait weight (if exists)
                            choice.trait_weights[0].weight = new_weight
                            choice.trait_weights[0].trait_id = int(trait_id)  # Update trait_id if it's changed
                        else:
                            # If no trait weight exists, create a new TraitWeight
                            new_trait_weight = TraitWeight(
                                choice_id=choice.id, 
                                trait_id=int(trait_id),  # Ensure this is the selected trait
                                weight=new_weight
                            )
                            db.session.add(new_trait_weight)
            
            # If new choices are added, create them
            if len(choice_texts) > len(question.choices):
                for i in range(len(question.choices), len(choice_texts)):
                    if choice_texts[i].strip():
                        try:
                            weight = float(choice_weights[i]) if i < len(choice_weights) else 0.0
                        except (ValueError, IndexError):
                            weight = 0.0
                        
                        # Create a new choice
                        choice = Choice(
                            question_id=question.id,
                            text=choice_texts[i],
                            is_correct=False
                        )
                        db.session.add(choice)
                        db.session.flush()  # This will generate the choice ID
                        
                        # Create a new trait weight
                        trait_weight = TraitWeight(
                            choice_id=choice.id,
                            trait_id=int(trait_id),  # Set the selected trait_id for new choice
                            weight=weight
                        )
                        db.session.add(trait_weight)

            # Commit all changes
            db.session.commit()
            flash('Personality question updated successfully!', 'success')
            return redirect(url_for('interview_questions.personality_questions'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating personality question: {str(e)}', 'danger')
    
    # Render the form with the current question and list of personality traits
    return render_template('interview_questions/edit_personality_question.html', 
                           question=question, 
                           personality_traits=personality_traits)  # Pass the personality traits to the template


@interview_questions_bp.route("/interview_questions/personality/<int:question_id>/delete", methods=['POST'])
@login_required
def delete_personality_question(question_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    question = Question.query.get_or_404(question_id)
    
    try:
        # Delete associated choices and trait weights
        choices = Choice.query.filter_by(question_id=question_id).all()
        for choice in choices:
            TraitWeight.query.filter_by(choice_id=choice.id).delete()
        Choice.query.filter_by(question_id=question_id).delete()
        
        # Delete question
        db.session.delete(question)
        db.session.commit()
        flash('Personality question deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting question: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.personality_questions'))

# ======================
# STAGE QUESTION ASSIGNMENT
# ======================

@interview_questions_bp.route("/interview_questions/assign_to_stage/<int:stage_id>", methods=['GET', 'POST'])
@login_required
def assign_to_stage(stage_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    stage = Stage.query.get_or_404(stage_id)
    
    if request.method == 'POST':
        try:
            question_ids = request.form.getlist('question_ids')
            
            # Clear existing questions
            stage.questions = []
            
            # Add selected questions
            if question_ids:
                questions = Question.query.filter(Question.id.in_(question_ids)).all()
                for question in questions:
                    stage.questions.append(question)
            
            db.session.commit()
            flash(f'Questions assigned to {stage.name} successfully!', 'success')
            return redirect(url_for('pipeline.view_pipeline', pipeline_id=stage.pipeline_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error assigning questions: {str(e)}', 'danger')
    
    # Get appropriate questions based on stage type
    if stage.stage_type == StageType.technical_test:
        available_questions = Question.query.filter(
            Question.question_type.in_([QuestionType.multiple_choice, QuestionType.open_ended])
        ).all()
    elif stage.stage_type == StageType.personality_test:
        available_questions = Question.query.filter_by(
            question_type=QuestionType.personality_test
        ).all()
    else:
        available_questions = []
    
    return render_template('interview_questions/assign_to_stage.html',
                         stage=stage,
                         available_questions=available_questions)

# ======================
# JOB ROLES MANAGEMENT
# ======================

@interview_questions_bp.route("/interview_questions/job_roles")
@login_required
def job_roles():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    job_roles = JobRole.query.all()
    personality_traits = PersonalityTrait.query.all()
    
    return render_template('interview_questions/job_roles.html',
                         job_roles=job_roles,
                         personality_traits=personality_traits)

@interview_questions_bp.route("/interview_questions/job_roles/new", methods=['POST'])
@login_required
def new_job_role():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Job role name is required.', 'danger')
        return redirect(url_for('interview_questions.job_roles'))
    
    try:
        job_role = JobRole(name=name, description=description)
        db.session.add(job_role)
        db.session.commit()
        flash('Job role created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating job role: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.job_roles'))

@interview_questions_bp.route("/interview_questions/job_roles/<int:role_id>/trait_weights", methods=['POST'])
@login_required
def update_trait_weights(role_id):
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    job_role = JobRole.query.get_or_404(role_id)
    
    try:
        # Delete existing trait weights
        RoleTraitWeight.query.filter_by(role_id=role_id).delete()
        
        # Add new trait weights
        trait_ids = request.form.getlist('trait_id[]')
        weights = request.form.getlist('weight[]')
        
        for i, trait_id in enumerate(trait_ids):
            if trait_id and i < len(weights):
                trait_weight = RoleTraitWeight(
                    role_id=role_id,
                    trait_id=int(trait_id),
                    weight=int(weights[i])
                )
                db.session.add(trait_weight)
        
        db.session.commit()
        flash('Trait weights updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating trait weights: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.job_roles'))

# ======================
# ALL QUESTIONS VIEW
# ======================

@interview_questions_bp.route("/interview_questions/all")
@login_required
def all_questions():
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    # Get all questions with their categories and counts
    technical_questions = Question.query.filter(
        Question.question_type.in_([QuestionType.multiple_choice, QuestionType.open_ended])
    ).all()
    
    personality_questions = Question.query.filter_by(
        question_type=QuestionType.personality_test
    ).all()
    
    categories = QuestionCategory.query.all()
    
    # Count questions by category
    category_stats = []
    for category in categories:
        tech_count = Question.query.filter_by(
            category_id=category.id,
            question_type=QuestionType.open_ended
        ).count() + Question.query.filter_by(
            category_id=category.id,
            question_type=QuestionType.multiple_choice
        ).count()
        
        personality_count = Question.query.filter_by(
            category_id=category.id,
            question_type=QuestionType.personality_test
        ).count()
        
        category_stats.append({
            'category': category,
            'technical_count': tech_count,
            'personality_count': personality_count,
            'total_count': tech_count + personality_count
        })
    
    return render_template('interview_questions/all_questions.html',
                         technical_questions=technical_questions,
                         personality_questions=personality_questions,
                         categories=categories,
                         category_stats=category_stats,
                         QuestionType=QuestionType)


# ======================
# PERSONALITY TRAITS MANAGEMENT
# ======================

@interview_questions_bp.route("/interview_questions/personality_traits")
@login_required
def manage_personality_traits():
    """View and manage personality traits"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    traits = PersonalityTrait.query.all()
    return render_template('interview_questions/manage_traits.html', traits=traits)

@interview_questions_bp.route("/interview_questions/personality_traits/new", methods=['POST'])
@login_required
def new_personality_trait():
    """Create a new personality trait"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Trait name is required.', 'danger')
        return redirect(url_for('interview_questions.manage_personality_traits'))
    
    # Check if trait already exists
    existing = PersonalityTrait.query.filter_by(name=name).first()
    if existing:
        flash('Personality trait already exists.', 'danger')
        return redirect(url_for('interview_questions.manage_personality_traits'))
    
    try:
        trait = PersonalityTrait(
            name=name,
            description=description,
        )
        db.session.add(trait)
        db.session.commit()
        flash('Personality trait created successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating trait: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.manage_personality_traits'))

@interview_questions_bp.route("/interview_questions/personality_traits/<int:trait_id>/edit", methods=['POST'])
@login_required
def edit_personality_trait(trait_id):
    """Edit an existing personality trait"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    trait = PersonalityTrait.query.get_or_404(trait_id)
    
    name = request.form.get('name')
    description = request.form.get('description')
    
    if not name:
        flash('Trait name is required.', 'danger')
        return redirect(url_for('interview_questions.manage_personality_traits'))
    
    try:
        trait.name = name
        trait.description = description
        
        db.session.commit()
        flash('Personality trait updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating trait: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.manage_personality_traits'))

@interview_questions_bp.route("/interview_questions/personality_traits/<int:trait_id>/delete", methods=['POST'])
@login_required
def delete_personality_trait(trait_id):
    """Delete a personality trait"""
    if not current_user.has_role('ADMIN') and not current_user.has_role('DIRECTOR') and not current_user.has_role('INTERVIEWER'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.home'))
    
    trait = PersonalityTrait.query.get_or_404(trait_id)
    
    # Check if trait is used in any questions
    if trait.trait_weights.count() > 0:
        flash('Cannot delete trait that is used in personality questions.', 'danger')
        return redirect(url_for('interview_questions.manage_personality_traits'))
    
    # Check if trait is used in any job roles
    if trait.role_trait_weights.count() > 0:
        flash('Cannot delete trait that is assigned to job roles.', 'danger')
        return redirect(url_for('interview_questions.manage_personality_traits'))
    
    try:
        db.session.delete(trait)
        db.session.commit()
        flash('Personality trait deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting trait: {str(e)}', 'danger')
    
    return redirect(url_for('interview_questions.manage_personality_traits'))