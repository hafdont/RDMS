📄 Copyright & Usage Notice

This application is the intellectual property of 3A CPA LLP.

Although the software was developed by me, it was created in my capacity as an IT Officer and Consultant for 3A CPA LLP. All rights, ownership, and associated intellectual property belong exclusively to 3A CPA LLP.

This repository and its contents are provided solely for evaluation and demonstration purposes, serving as a showcase of my technical skills and professional experience. The application is not intended for commercial use, redistribution, or deployment outside of this context without explicit written permission from 3A CPA LLP.

📌 Application Overview

This application is a role-based task management system designed to help management monitor, assign, and evaluate tasks performed by users across the firm.

Key Features

Task Management

Management can view, assign, and monitor tasks performed by users.

Users create tasks based on predefined task templates derived from the firm’s offered services.

Tasks follow a lifecycle:

Start

Pause / Resume

Completion

Submission for approval

Time Tracking

Users can log:

Task start time

Paused and resumed durations

Completion time

Enables accountability and performance tracking.

Approval Workflow

Completed tasks are submitted for review and approval.

Supervisors and managers can verify work before final approval.

Documents & Notes

Users can attach:

Supporting documents

Notes and explanations

These provide verification, audit trails, and insights into completed work.

File Storage

Uploaded documents and user profile images are securely stored on DigitalOcean Spaces.

Notifications

In-app notifications

Email notifications

Triggered by key application activities and sent to relevant users.

Spreadsheet-like Module

A built-in module that functions similarly to Google Sheets.

Allows users to input, save, and store structured data directly within the application.

Role & Permission Based Access

Access to data and actions is controlled by user roles and permissions.

Ensures data security and proper segregation of duties.

⚙️ Installation Guide
1. Clone the Repository
git clone https://github.com/hafdont/RDMS
cd RDMS

2. Create a Virtual Environment
python -m venv venv
source venv/bin/activate   # Linux / macOS
venv\Scripts\activate      # Windows

3. Install Dependencies
pip install flask


Copy the contents of requirements.ini into a new file named requirements.txt, then install all dependencies:

pip install -r requirements.txt

4. Environment Variables

Create a .env file in the project root with the following structure:

# Flask Configuration
FLASK_ENV=development
SECRET_KEY=

# Database Configuration
DATABASE_URL=

# Mail Server Configuration (SSL Recommended)
MAIL_SERVER=
MAIL_PORT=
MAIL_USE_TLS=False
MAIL_USE_SSL=True
MAIL_USERNAME=
MAIL_PASSWORD=

# DigitalOcean Spaces Configuration
S3_BUCKET=
S3_REGION=
S3_ENDPOINT_URL=
S3_ACCESS_KEY=
S3_SECRET_KEY=

# Application Environment
APP_ENV=production

# Error Monitoring
SENTRY_DSN=

🗄️ Database Setup
1. Create the Database

Create a new database using your preferred SQL tool (e.g., phpMyAdmin, MySQL Workbench, or CLI).

2. Import the Database Script

Import the db_setup.sql file provided in the repository.

This script will:

Create required tables

Set up departments

Create a default administrator account

👤 Default Administrator Account

After importing db_setup.sql, the following admin user will be available:

Name: Hafiz Yusuf

Email: hafizmasoud7@gmail.com

Role: ADMIN

passwped: test11234

⚠️ Important:
If you wish to change the admin name or email, edit the final INSERT INTO users statement in db_setup.sql before importing it into your database.

🚀 Final Steps

Run database migrations to initialize models (if applicable).

Start the Flask application.

Log in using the default administrator account.

Begin configuring users, roles, services, and task templates.

