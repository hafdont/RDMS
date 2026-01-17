from dotenv import load_dotenv
import os

load_dotenv()

def str_to_bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes")

class Config:

    # Cache Configuration
    CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")
    CACHE_DEFAULT_TIMEOUT = int(os.getenv("CACHE_DEFAULT_TIMEOUT", 300))
    

    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    MAIL_SERVER = os.getenv('MAIL_SERVER')
    MAIL_PORT = int(os.getenv('MAIL_PORT'))
    
    MAIL_USE_TLS = str_to_bool(os.getenv('MAIL_USE_TLS'), True)
    MAIL_USE_SSL = str_to_bool(os.getenv('MAIL_USE_SSL'), False)
    
    MAIL_USERNAME = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')

    # DigitalOcean Spaces Configuration (S3 Compatible)
    S3_BUCKET = os.getenv('S3_BUCKET')
    S3_REGION = os.getenv('S3_REGION', 'nyc3')
    S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL', f"https://{S3_REGION}.digitaloceanspaces.com")
    S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY')
    S3_SECRET_KEY = os.getenv('S3_SECRET_KEY')
    
    # Define Allowed Extensions
    ALLOWED_EXTENSIONS = {
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv',
        'odt', 'ods', 'odp', 'rtf', 'xml', 'json', 'zip', 'rar', '7z', 'tar', 'gz'
    }
    # Max file size (16MB)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

class ProductionConfig(Config):
    DEBUG = False
    PROPAGATE_EXCEPTIONS = False

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = True
