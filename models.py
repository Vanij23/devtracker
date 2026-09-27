from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    applications = db.relationship(
        'Application', backref='user', lazy=True, cascade='all, delete-orphan'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Application(db.Model):
    __tablename__ = 'applications'

    STATUS_CHOICES = ['applied', 'oa', 'interview', 'offer', 'rejected']

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    company_name = db.Column(db.String(150), nullable=False)
    role_title = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(20), default='applied', nullable=False)
    applied_date = db.Column(db.Date)
    job_link = db.Column(db.String(500))
    location = db.Column(db.String(150))
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # AI Copilot output: prep tips (OA/interview), feedback (rejected), or
    # negotiation pointers (offer). Regenerated whenever the user asks or
    # the status changes.
    ai_notes = db.Column(db.Text)
    ai_notes_generated_for_status = db.Column(db.String(20))

    rounds = db.relationship(
        'InterviewRound', backref='application', lazy=True, cascade='all, delete-orphan'
    )


class InterviewRound(db.Model):
    __tablename__ = 'interview_rounds'

    STATUS_CHOICES = ['pending', 'cleared', 'failed']

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('applications.id'), nullable=False)

    round_name = db.Column(db.String(150), nullable=False)
    scheduled_at = db.Column(db.DateTime)  # date + time of the round
    status = db.Column(db.String(20), default='pending', nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
