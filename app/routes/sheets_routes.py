from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from app.models import *
from app.utils.db import db
from flask_login import login_required, current_user
import csv, io
from flask import Response


sheet_bp = Blueprint('sheet', __name__)


@sheet_bp.route('/sheets')
@login_required
def list_sheets():
    sheets = Sheet.query.filter(
    Sheet.visible_on_sheets_home == True,
    Sheet.deleted_at.is_(None)
    ).all()
    visible_sheets = [s for s in sheets if s.can_user_view(current_user)]
    return render_template('sheets/list.html', sheets=visible_sheets)



@sheet_bp.route('/sheet/create', methods=['POST'])
@login_required
def create_sheet():
    form_title = request.form.get('title')
    form_visibility_str = request.form.get('visibility')

    if not form_title:
        flash("Sheet title is required", "danger")
        return redirect(request.referrer)

    try:
        visibility_enum = SheetVisibilityEnum(form_visibility_str)
    except ValueError:
        flash(f"Invalid visibility type: {form_visibility_str}", "danger")
        return redirect(request.referrer)

    initial_content = [["" for _ in range(26)] for _ in range(50)]

    new_sheet = Sheet(
        title=form_title,
        content=initial_content,
        created_by_id=current_user.id,
        visibility=visibility_enum
    )
    db.session.add(new_sheet)
    db.session.commit()
    flash("Sheet created successfully!", "success")
    return redirect(url_for('sheet.view_sheet', sheet_id=new_sheet.id))


@sheet_bp.route('/sheet/<int:sheet_id>')
def view_sheet(sheet_id):
    sheet = Sheet.query.get_or_404(sheet_id)

    
    if not sheet.can_user_view(current_user):
        abort(403, description="You do not have permission to view this sheet.")

    if sheet.deleted_at:
        abort(404, description="This sheet has been deleted.")

    return render_template(
        'sheets/view.html',
        sheet=sheet,
        sheet_data=sheet.get_sheet_data()
    )


@sheet_bp.route('/sheet/<int:sheet_id>/save', methods=['POST'])
def save_sheet(sheet_id):
    sheet = Sheet.query.get_or_404(sheet_id)

    if not sheet.can_user_view(current_user):
        abort(403, description="You do not have permission to edit this sheet.")

    new_sheet_content = request.get_json()

    if not new_sheet_content or 'content' not in new_sheet_content:
        return jsonify({"success": False, "error": "Invalid content"}), 400

    # Save it in standardized format
    sheet.content = [{
        ##"data": new_sheet_content["content"][0].get("data") if isinstance(new_sheet_content["content"], list) else new_sheet_content["content"]
        "data": new_sheet_content["content"][0].get("data") if isinstance(new_sheet_content["content"], list) and isinstance(new_sheet_content["content"][0], dict) else new_sheet_content["content"]

    }]
    db.session.commit()

    return jsonify({"success": True, "message": f"Sheet {sheet.title} saved successfully."})

 
@sheet_bp.route('/sheets/<int:sheet_id>/delete', methods=['POST'])
@login_required
def delete_sheet(sheet_id):
    sheet = Sheet.query.get_or_404(sheet_id)

    if current_user.id != sheet.created_by_id and current_user.role not in [
        'ADMIN', 'SUPERVISOR', 'DIRECTOR'
    ]:
        flash("You are not allowed to delete this sheet.", "danger")
        return jsonify({"error": "Unauthorized"}), 403

    if sheet.deleted_at:
        flash("This sheet is already deleted.", "warning")
        return jsonify({"error": "Already deleted"}), 400

    try:
        sheet.deleted_at = datetime.utcnow()
        sheet.deleted_by_id = current_user.id
        sheet.visible_on_sheets_home = False

        db.session.commit()
        flash("Sheet deleted successfully!", "success")
        return jsonify({"success": True}), 200

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting sheet: {str(e)}", "danger")
        return jsonify({"error": f"Error deleting sheet: {str(e)}"}), 500


@sheet_bp.route('/sheets/<int:sheet_id>/download')
@login_required
def download_sheet(sheet_id):
    sheet = Sheet.query.get_or_404(sheet_id)

    if not sheet.can_user_view(current_user):
        abort(403, description="You do not have permission to download this sheet.")

    # Use StringIO to build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    for row in sheet.content:
        writer.writerow(row)

    output.seek(0)  # Move to beginning of the StringIO buffer

    filename = f"{sheet.title.replace(' ', '_')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

@sheet_bp.route('/sheet/<int:sheet_id>/update_permissions', methods=['POST'])
@login_required
def update_permissions(sheet_id):
    sheet = Sheet.query.get_or_404(sheet_id)

    # Only creator or admin can update permissions
    if current_user.id != sheet.created_by_id and current_user.role != 'ADMIN':
        flash("You don't have permission to edit this sheet.", "danger")
        return redirect(request.referrer)

    form_visibility = request.form.get('visibility')
    try:
        sheet.visibility = SheetVisibilityEnum(form_visibility)
        db.session.commit()
        flash("Permissions updated successfully.", "success")
    except ValueError:
        flash(f"Invalid permission selected: {form_visibility}", "danger")

    return redirect(request.referrer)
