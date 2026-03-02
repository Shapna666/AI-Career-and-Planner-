from flask import Flask, render_template, redirect, url_for, request, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config
from extensions import db
import os
import json

# AI utilities
from utils.resume_parser import parse_resume
from utils.skill_extractor import extract_skills
from utils.skill_gap_analysis import compare_skills
from utils.roadmap_generator import generate_roadmap


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # Ensure instance and upload folders exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(os.path.join(app.root_path, "static", "uploads"), exist_ok=True)

    db.init_app(app)

    from models.user_model import User, Analysis, SkillProgress
    from models.career_model import Career

    with app.app_context():
        # create tables if they don't exist
        db.create_all()

        # simple migration: if user table lacks created_at column, drop and recreate the database
        try:
            result = db.engine.execute("PRAGMA table_info(user)")
            columns = [row[1] for row in result.fetchall()]
            if 'created_at' not in columns:
                # remove the database file to force recreate
                db_path = os.path.join(app.instance_path, 'database.db')
                if os.path.exists(db_path):
                    os.remove(db_path)
                db.create_all()
        except Exception:
            # if anything goes wrong, just ignore; user can delete manually
            pass

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "POST":
            email = request.form.get("email")
            password = request.form.get("password")

            if not email or not password:
                flash("Email and password are required.", "danger")
                return redirect(url_for("signup"))

            if User.query.filter_by(email=email).first():
                flash("Email already registered. Please log in.", "warning")
                return redirect(url_for("login"))

            hashed = generate_password_hash(password)
            user = User(email=email, password_hash=hashed)
            db.session.add(user)
            db.session.commit()
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email")
            password = request.form.get("password")

            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                session["user_id"] = user.id
                flash("Logged in successfully.", "success")
                return redirect(url_for("dashboard"))

            flash("Invalid credentials.", "danger")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for("index"))

    @app.route("/dashboard")
    def dashboard():
        if "user_id" not in session:
            return redirect(url_for("login"))
        return render_template("dashboard.html")

    @app.route("/upload-resume", methods=["GET", "POST"])
    def upload_resume():
        if "user_id" not in session:
            return redirect(url_for("login"))

        if request.method == "POST":
            file = request.files.get("resume")
            if not file or not file.filename:
                flash("Please upload a resume file.", "warning")
                return redirect(url_for("upload_resume"))

            upload_folder = os.path.join(app.root_path, "static", "uploads")
            os.makedirs(upload_folder, exist_ok=True)

            # Sanitize and validate filename to prevent path traversal
            filename = secure_filename(file.filename)
            if not filename:
                flash("Invalid file name. Please rename your resume and try again.", "warning")
                return redirect(url_for("upload_resume"))

            allowed_extensions = {".pdf", ".doc", ".docx", ".jpg", ".jpeg"}
            _, ext = os.path.splitext(filename)
            if ext.lower() not in allowed_extensions:
                flash("Unsupported file type. Please upload a PDF or Word document.", "warning")
                return redirect(url_for("upload_resume"))

            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)

            # parse resume and extract skills
            text = parse_resume(filepath)
            careers_file = os.path.join(app.root_path, "database", "careers.json")
            with open(careers_file, "r", encoding="utf-8") as f:
                careers = json.load(f)
            all_skills = [skill for c in careers for skill in c.get("skills", [])]
            user_skills = extract_skills(text, all_skills)

            session["uploaded_resume_path"] = filepath
            session["uploaded_resume_name"] = filename
            session["user_skills"] = user_skills
            flash(f"Resume uploaded and skills detected: {', '.join(user_skills)}", "success")
            if session.get("target_career"):
                flash(f"Your current target career is: {session['target_career']}", "info")
            return redirect(url_for("career_selection"))

        return render_template("upload_resume.html")

    @app.route("/career-selection", methods=["GET", "POST"])
    def career_selection():
        if "user_id" not in session:
            return redirect(url_for("login"))
        careers_file = os.path.join(app.root_path, "database", "careers.json")
        with open(careers_file, "r", encoding="utf-8") as f:
            careers = json.load(f)

        if request.method == "POST":
            chosen = request.form.get("career")
            session["target_career"] = chosen
            return redirect(url_for("results"))
        return render_template("career_selection.html", careers=careers)

    @app.route("/results")
    def results():
        if "user_id" not in session:
            return redirect(url_for("login"))
        target = session.get("target_career")
        user_skills = session.get("user_skills", [])
        career = None
        required_skills = []
        if target:
            careers_file = os.path.join(app.root_path, "database", "careers.json")
            with open(careers_file, "r", encoding="utf-8") as f:
                careers = json.load(f)
            career = next((c for c in careers if c["name"] == target), None)
            if career:
                required_skills = career.get("skills", [])
        existing, missing = [], []
        if career:
            existing, missing = compare_skills(user_skills, required_skills)
        
        user_id = session.get("user_id")
        # Include completed skills from progress tracking
        effective_existing = list(existing)
        if user_id and career:
            completed_progress = SkillProgress.query.filter_by(
                user_id=user_id, career_name=target, is_completed=True
            ).all()
            completed_names = {p.skill_name for p in completed_progress}
            for skill_name in completed_names:
                if skill_name in missing and skill_name not in effective_existing:
                    effective_existing.append(skill_name)

        # Calculate readiness score using effective_existing
        total_skills = len(required_skills) if required_skills else 1
        readiness_score = int((len(set(effective_existing)) / total_skills * 100)) if total_skills > 0 else 0
        
        # Save analysis to database
        if user_id and career:
            existing_analysis = Analysis.query.filter_by(user_id=user_id, career_name=target).first()
            if not existing_analysis:
                analysis = Analysis(
                    user_id=user_id,
                    career_name=target,
                    extracted_skills=json.dumps(user_skills),
                )
                db.session.add(analysis)
                db.session.commit()
        
        return render_template(
            "results.html",
            career=career,
            existing=existing,
            missing=missing,
            readiness_score=readiness_score,
            total_skills=total_skills,
            completed_skills=len(set(effective_existing)),
        )

    @app.route("/roadmap")
    def roadmap():
        if "user_id" not in session:
            return redirect(url_for("login"))
        target = session.get("target_career")
        missing = []
        if target:
            careers_file = os.path.join(app.root_path, "database", "careers.json")
            with open(careers_file, "r", encoding="utf-8") as f:
                careers = json.load(f)
            career = next((c for c in careers if c["name"] == target), None)
            if career:
                user_skills = session.get("user_skills", [])
                _, missing = compare_skills(user_skills, career.get("skills", []))
        roadmap = generate_roadmap(missing)
        return render_template("roadmap.html", roadmap=roadmap)

    @app.route("/profile")
    def profile():
        if "user_id" not in session:
            return redirect(url_for("login"))
        user_id = session["user_id"]
        user = User.query.get(user_id)
        analyses = Analysis.query.filter_by(user_id=user_id).all()
        return render_template("profile.html", user=user, analyses=analyses)

    @app.route("/courses")
    def courses():
        if "user_id" not in session:
            return redirect(url_for("login"))
        target = session.get("target_career")
        user_skills = session.get("user_skills", [])
        career = None
        missing = []
        courses_list = {}
        
        if target:
            careers_file = os.path.join(app.root_path, "database", "careers.json")
            with open(careers_file, "r", encoding="utf-8") as f:
                careers = json.load(f)
            career = next((c for c in careers if c["name"] == target), None)
            if career:
                _, missing = compare_skills(user_skills, career.get("skills", []))
                
                # Load courses
                courses_file = os.path.join(app.root_path, "database", "courses.json")
                with open(courses_file, "r", encoding="utf-8") as f:
                    all_courses = json.load(f)
                
                for skill in missing:
                    if skill in all_courses:
                        courses_list[skill] = all_courses[skill]
        
        return render_template("courses.html", career=career, courses_list=courses_list, missing=missing)

    @app.route("/track-progress", methods=["GET", "POST"])
    def track_progress():
        if "user_id" not in session:
            return redirect(url_for("login"))
        
        user_id = session["user_id"]
        target = session.get("target_career")
        
        if request.method == "POST":
            skill_name = request.form.get("skill")
            is_completed = request.form.get("is_completed") == "true"
            
            if target and skill_name:
                progress = SkillProgress.query.filter_by(user_id=user_id, career_name=target, skill_name=skill_name).first()
                if progress:
                    progress.is_completed = is_completed
                else:
                    progress = SkillProgress(user_id=user_id, career_name=target, skill_name=skill_name, is_completed=is_completed)
                    db.session.add(progress)
                db.session.commit()
                flash(f"Skill '{skill_name}' marked as {'completed' if is_completed else 'incomplete'}.", "success")
            return redirect(url_for("track_progress"))
        
        # Get user's skill progress
        user_skills = session.get("user_skills", [])
        career = None
        missing = []
        progress_data = {}
        
        if target:
            careers_file = os.path.join(app.root_path, "database", "careers.json")
            with open(careers_file, "r", encoding="utf-8") as f:
                careers = json.load(f)
            career = next((c for c in careers if c["name"] == target), None)
            if career:
                _, missing = compare_skills(user_skills, career.get("skills", []))
                
                for skill in missing:
                    progress = SkillProgress.query.filter_by(user_id=user_id, career_name=target, skill_name=skill).first()
                    progress_data[skill] = progress.is_completed if progress else False
        
        return render_template("track_progress.html", career=career, missing=missing, progress_data=progress_data)

    return app


if __name__ == "__main__":
    application = create_app()
    debug_flag = application.config.get("DEBUG", False)
    application.run(debug=debug_flag)


