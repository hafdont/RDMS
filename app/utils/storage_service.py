# app/services/storage_service.py
import boto3
from botocore.exceptions import ClientError
from flask import current_app
import uuid
import os
from werkzeug.utils import secure_filename


class DigitalOceanStorage:
    """Production-ready DigitalOcean Spaces storage service"""
    
    def __init__(self, app=None):
        self.s3_client = None
        self.app = None
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize S3 client with DigitalOcean Spaces credentials"""
        self.app = app
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=app.config['S3_ENDPOINT_URL'],
                aws_access_key_id=app.config['S3_ACCESS_KEY'],
                aws_secret_access_key=app.config['S3_SECRET_KEY'],
                region_name=app.config['S3_REGION']
            )
            print(f"✅ DigitalOcean Spaces client initialized")
        except Exception as e:
            print(f"❌ Failed to initialize DigitalOcean Spaces: {e}")
            raise
    
    def upload_file(self, file, folder='documents', filename=None):
        if not self.s3_client:
            raise Exception("Storage service not initialized")
            
        # 1. Get filename and extension safely
        original_filename = filename or getattr(file, 'filename', 'uploaded_file.png')
        original_filename = secure_filename(original_filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
        
        # 2. Determine Mimetype safely (FIXES THE BYTESIO ERROR)
        mimetype = getattr(file, 'mimetype', None)
        if not mimetype:
            # Map common extensions if mimetype is missing from the object
            if file_extension in ['jpg', 'jpeg']: mimetype = 'image/jpeg'
            elif file_extension == 'png': mimetype = 'image/png'
            else: mimetype = 'application/octet-stream'

        unique_id = uuid.uuid4().hex
        unique_filename = f"{unique_id}.{file_extension}" if file_extension else unique_id
        s3_key = f"{folder}/{unique_filename}"
        
        try:
            current_position = file.tell()
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(current_position)

            # 3. Use our local 'mimetype' variable here
            self.s3_client.upload_fileobj(
                file,
                self.app.config['S3_BUCKET'],  
                s3_key, 
                ExtraArgs={'ContentType': mimetype} # Corrected
            )
            
            return {
                'key': s3_key,
                'original_filename': original_filename,
                'mimetype': mimetype,
                'size': file_size
            }
        except Exception as e:
            print(f"❌ Failed to upload file to Spaces: {e}")
            raise

    def get_file_url(self, file_key, expires_in=3600):
        if not file_key:
            return None
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.app.config['S3_BUCKET'],  
                    'Key': file_key
                },
                ExpiresIn=expires_in
            )
            return url
        except ClientError as e:
            print(f"❌ Failed to generate presigned URL: {e}")  
            return None

    # app/services/storage_service.py (Updated delete_file method)
    def delete_file(self, file_key):
        if not self.s3_client:
            raise Exception("Storage service not initialized")
            
        try:
            # S3 delete_object method. It doesn't throw an error if the key doesn't exist.
            self.s3_client.delete_object(
                Bucket=self.app.config['S3_BUCKET'],  
                Key=file_key
            )
            # We don't need to check the response; if no exception is raised, it was successful.
            if current_app:
                 current_app.logger.info(f"🗑️ File deleted from Spaces: {file_key}") 
            return True
            
        except ClientError as e:
            # Log the specific Boto3 client error
            if current_app:
                current_app.logger.error(f"❌ Failed to delete {file_key} from Spaces: {e}")
            # Do NOT re-raise if the file is just missing (Code 404), as it's already "deleted"
            # However, for critical errors (permissions), you might still want to return False.
            return False
        except Exception as e:
             if current_app:
                current_app.logger.error(f"❌ Unknown error deleting {file_key}: {e}")
             return 
        
    def file_exists(self, file_key):
        try:
            self.s3_client.head_object(
                Bucket=self.app.config['S3_BUCKET'], 
                Key=file_key
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise

    def get_file_metadata(self, file_key):
        try:
            response = self.s3_client.head_object(
                Bucket=self.app.config['S3_BUCKET'],  
                Key=file_key
            )
            return response['Metadata']
        except ClientError as e:
            print(f"❌ Failed to get file metadata: {e}")  
            return None
        
    def list_buckets(self):
        """List all available buckets in DigitalOcean Spaces"""
        try:
            response = self.s3_client.list_buckets()
            return [bucket['Name'] for bucket in response['Buckets']]
        except Exception as e:
            print(f"❌ Error listing buckets: {e}")
            return []
    
storage_service = DigitalOceanStorage()