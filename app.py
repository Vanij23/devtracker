from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import (
    login_user, logout_user, login_required, current_user
)
from sqlalchemy import func

from config import Config
from extensions import db, login_manager
from models import User, Application, InterviewRound
from ai_helper import generate_ai_notes, parse_bulk_applications, answer_question


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ---------- Public pages ----------

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            name = request.form.get('name', '').strip()
            password = request.form.get('password', '')

            if not email or not password:
                flash('Email and password are required.', 'danger')
                return render_template('signup.html')

            if User.query.filter_by(email=email).first():
                flash('An account with that email already exists.', 'danger')
                return render_template('signup.html')

            user = User(email=email, name=name)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            login_user(user)
            flash('Account created. Welcome to DevTracker!', 'success')
            return redirect(url_for('dashboard'))

        return render_template('signup.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')

            user = User.query.filter_by(email=email).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('dashboard'))

            flash('Invalid email or password.', 'danger')

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    # ---------- Dashboard ----------

    @app.route('/dashboard')
    @login_required
    def dashboard():
        all_applications = (
            Application.query.filter_by(user_id=current_user.id)
            .order_by(Application.applied_date.desc().nullslast())
            .all()
        )

        columns = {s: [] for s in Application.STATUS_CHOICES}
        for app_obj in all_applications:
            columns.setdefault(app_obj.status, []).append(app_obj)

        total = len(all_applications)
        status_counts = {s: len(apps) for s, apps in columns.items()}
        beyond_applied = sum(v for k, v in status_counts.items() if k != 'applied')
        response_rate = round((beyond_applied / total) * 100, 1) if total else 0

        return render_template(
            'dashboard.html',
            columns=columns,
            total=total,
            status_counts=status_counts,
            response_rate=response_rate,
        )

    # ---------- Application CRUD ----------

    @app.route('/applications/new', methods=['GET', 'POST'])
    @login_required
    def new_application():
        if request.method == 'POST':
            applied_date_str = request.form.get('applied_date')
            applied_date = (
                datetime.strptime(applied_date_str, '%Y-%m-%d').date()
                if applied_date_str else None
            )

            app_obj = Application(
                user_id=current_user.id,
                company_name=request.form.get('company_name', '').strip(),
                role_title=request.form.get('role_title', '').strip(),
                applied_date=applied_date,
                job_link=request.form.get('job_link', '').strip() or None,
                location=request.form.get('location', '').strip() or None,
                notes=request.form.get('notes', '').strip() or None,
            )
            db.session.add(app_obj)
            db.session.commit()
            flash(f'Added application to {app_obj.company_name}.', 'success')
            return redirect(url_for('dashboard'))

        return render_template('application_form.html', application=None)

    @app.route('/applications/<int:app_id>')
    @login_required
    def view_application(app_id):
        app_obj = Application.query.filter_by(
            id=app_id, user_id=current_user.id
        ).first_or_404()
        return render_template('application_detail.html', application=app_obj)

    @app.route('/applications/<int:app_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_application(app_id):
        app_obj = Application.query.filter_by(
            id=app_id, user_id=current_user.id
        ).first_or_404()

        if request.method == 'POST':
            applied_date_str = request.form.get('applied_date')
            app_obj.company_name = request.form.get('company_name', '').strip()
            app_obj.role_title = request.form.get('role_title', '').strip()
            app_obj.applied_date = (
                datetime.strptime(applied_date_str, '%Y-%m-%d').date()
                if applied_date_str else None
            )
            app_obj.job_link = request.form.get('job_link', '').strip() or None
            app_obj.location = request.form.get('location', '').strip() or None
            app_obj.notes = request.form.get('notes', '').strip() or None

            db.session.commit()
            flash('Application updated.', 'success')
            return redirect(url_for('view_application', app_id=app_obj.id))

        return render_template('application_form.html', application=app_obj)

    @app.route('/applications/<int:app_id>/delete', methods=['POST'])
    @login_required
    def delete_application(app_id):
        app_obj = Application.query.filter_by(
            id=app_id, user_id=current_user.id
        ).first_or_404()
        db.session.delete(app_obj)
        db.session.commit()
        flash('Application deleted.', 'info')
        return redirect(url_for('dashboard'))

    @app.route('/applications/<int:app_id>/status', methods=['POST'])
    @login_required
    def update_status(app_id):
        app_obj = Application.query.filter_by(
            id=app_id, user_id=current_user.id
        ).first_or_404()

        new_status = request.form.get('status')
        if new_status in Application.STATUS_CHOICES:
            app_obj.status = new_status
            db.session.commit()
            flash(f'Status updated to {new_status.title()}.', 'success')

        return redirect(url_for('view_application', app_id=app_obj.id))

    # ---------- Interview rounds ----------

    @app.route('/applications/<int:app_id>/rounds/new', methods=['POST'])
    @login_required
    def new_round(app_id):
        app_obj = Application.query.filter_by(
            id=app_id, user_id=current_user.id
        ).first_or_404()

        scheduled_at_str = request.form.get('scheduled_at')
        scheduled_at = (
            datetime.strptime(scheduled_at_str, '%Y-%m-%dT%H:%M')
            if scheduled_at_str else None
        )

        round_obj = InterviewRound(
            application_id=app_obj.id,
            round_name=request.form.get('round_name', '').strip(),
            scheduled_at=scheduled_at,
            notes=request.form.get('notes', '').strip() or None,
        )
        db.session.add(round_obj)
        db.session.commit()
        flash(f'Added round: {round_obj.round_name}.', 'success')
        return redirect(url_for('view_application', app_id=app_obj.id))

    @app.route('/rounds/<int:round_id>/status', methods=['POST'])
    @login_required
    def update_round_status(round_id):
        round_obj = InterviewRound.query.join(Application).filter(
            InterviewRound.id == round_id,
            Application.user_id == current_user.id,
        ).first_or_404()

        new_status = request.form.get('status')
        if new_status in InterviewRound.STATUS_CHOICES:
            round_obj.status = new_status
            db.session.commit()

        return redirect(url_for('view_application', app_id=round_obj.application_id))

    @app.route('/applications/<int:app_id>/advance', methods=['POST'])
    @login_required
    def advance_status(app_id):
        app_obj = Application.query.filter_by(
            id=app_id, user_id=current_user.id
        ).first_or_404()

        next_status = {
            'applied': 'oa',
            'oa': 'interview',
            'interview': 'offer',
        }.get(app_obj.status)

        if next_status:
            app_obj.status = next_status
            db.session.commit()

        return redirect(url_for('dashboard'))

    # ---------- Bulk import ----------

    @app.route('/applications/import', methods=['GET', 'POST'])
    @login_required
    def bulk_import():
        if request.method == 'POST':
            raw_text = request.form.get('raw_text', '').strip()
            if not raw_text:
                flash('Paste something to import first.', 'danger')
                return render_template('bulk_import.html', parsed=None)

            parsed = parse_bulk_applications(raw_text)

            if not parsed:
                flash("Couldn't find any applications in that text.", 'danger')
                return render_template('bulk_import.html', parsed=None)

            created = 0
            for item in parsed:
                company = (item.get('company_name') or '').strip()
                if not company:
                    continue

                applied_date = None
                date_str = item.get('applied_date')
                if date_str:
                    try:
                        applied_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        applied_date = None

                db.session.add(Application(
                    user_id=current_user.id,
                    company_name=company,
                    role_title=(item.get('role_title') or 'Unspecified role').strip(),
                    location=(item.get('location') or None),
                    applied_date=applied_date,
                ))
                created += 1

            db.session.commit()
            flash(f'Imported {created} application(s).', 'success')
            return redirect(url_for('dashboard'))

        return render_template('bulk_import.html', parsed=None)

    # ---------- AI Copilot ----------

    @app.route('/applications/<int:app_id>/ai-notes', methods=['POST'])
    @login_required
    def generate_notes(app_id):
        app_obj = Application.query.filter_by(
            id=app_id, user_id=current_user.id
        ).first_or_404()

        app_obj.ai_notes = generate_ai_notes(
            company_name=app_obj.company_name,
            role_title=app_obj.role_title,
            status=app_obj.status,
            notes=app_obj.notes,
        )
        app_obj.ai_notes_generated_for_status = app_obj.status
        db.session.commit()

        return redirect(url_for('view_application', app_id=app_obj.id))

    # ---------- Ask DevTracker (floating assistant widget) ----------

    @app.route('/api/assistant', methods=['POST'])
    @login_required
    def assistant():
        data = request.get_json(silent=True) or {}
        question = (data.get('question') or '').strip()

        if not question:
            return jsonify({'answer': "Ask me something first!"}), 400

        status_counts = dict(
            db.session.query(Application.status, func.count(Application.id))
            .filter(Application.user_id == current_user.id)
            .group_by(Application.status)
            .all()
        )
        total = sum(status_counts.values())
        context = f"{total} applications tracked: " + ", ".join(
            f"{v} {k}" for k, v in status_counts.items()
        ) if total else "No applications tracked yet."

        answer = answer_question(question, context=context)
        return jsonify({'answer': answer})

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
