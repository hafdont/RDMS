from flask import Blueprint, render_template, request,session, current_app
from app.models import User
from flask_login import current_user

# Create the error blueprint
error_bp = Blueprint('error_bp', __name__)

# Handle 400 - Bad Request
@error_bp.app_errorhandler(400)
def bad_request_error(error):
    current_app.logger.error(f"400 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=400, error_message="Bad Request"), 400

# Handle 403 - Forbidden
@error_bp.app_errorhandler(403)
def forbidden_error(error):
    current_app.logger.error(f"403 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=403, error_message="Forbidden"), 403

# Handle 404 - Not Found
@error_bp.app_errorhandler(404)
def not_found_error(error):
      
    current_app.logger.error(f"404 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=404, error_message="Page Not Found"), 404

# Handle 405 - Method Not Allowed
@error_bp.app_errorhandler(405)
def method_not_allowed_error(error):
      
    current_app.logger.error(f"405 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=405, error_message="Method Not Allowed"), 405

# Handle 408 - Request Timeout
@error_bp.app_errorhandler(408)
def request_timeout_error(error):
      
    current_app.logger.error(f"408 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=408, error_message="Request Timeout"), 408

# Handle 500 - Internal Server Error
@error_bp.app_errorhandler(500)
def internal_error(error):
      
    current_app.logger.error(f"500 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=500, error_message="Internal Server Error"), 500

# Handle 502 - Bad Gateway
@error_bp.app_errorhandler(502)
def bad_gateway_error(error):
      
    current_app.logger.error(f"502 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user,  error_code=502, error_message="Bad Gateway"), 502

# Handle 503 - Service Unavailable
@error_bp.app_errorhandler(503)
def service_unavailable_error(error):
      
    current_app.logger.error(f"503 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=503, error_message="Service Unavailable"), 503

# Handle 504 - Gateway Timeout
@error_bp.app_errorhandler(504)
def gateway_timeout_error(error):
      
    current_app.logger.error(f"504 Error: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=504, error_message="Gateway Timeout"), 504

# Catch any uncaught exceptions
@error_bp.app_errorhandler(Exception)
def handle_exception(error):
      
    current_app.logger.error(f"Unhandled Exception: {request.url} - {error}")
    return render_template('errors/error_page.html', user=current_user, error_code=500, error_message="An unexpected error occurred"), 500
