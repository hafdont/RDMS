from flask import Flask
from .auth_routes import auth_bp
from .task_routes import task_bp
from .main import main_bp
from .clients_routes import client_bp
from .services_routes import services_bp
from .template_routes import template_bp 
from .users_routes import users_bp
from .engangements_routes import job_bp
from .sheets_routes import sheet_bp
from .department_routes import department_bp
from .recycle_bin_routes import recycle_bin_bp
from .opportunities import opportunities_bp
from .pipelines import pipelines_bp
from .interview_questions_routes import interview_questions_bp
from .recruitment_routes import recruitment_bp
from .error_routes import error_bp



def register_routes(app: Flask):
    """
    Registers all the blueprints for the application.
    :param app: The Flask application instance.
    """
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(client_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(template_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(job_bp)
    app.register_blueprint(sheet_bp)
    app.register_blueprint(department_bp)
    app.register_blueprint(recycle_bin_bp)
    app.register_blueprint(opportunities_bp)
    app.register_blueprint(interview_questions_bp)
    app.register_blueprint(pipelines_bp)
    app.register_blueprint(recruitment_bp)
    app.register_blueprint(error_bp)






