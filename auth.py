from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from decorators import roles_required
from extensions import db
from models import User

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.username}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard.index"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/users")
@login_required
@roles_required("admin")
def user_list():
    users = User.query.order_by(User.id.desc()).all()
    return render_template("users.html", users=users)


@bp.route("/users/add", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def add_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "receptionist")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("user_form.html")

        if User.query.filter_by(username=username).first():
            flash("That username is already taken.", "danger")
            return render_template("user_form.html")

        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("User created successfully!", "success")
        return redirect(url_for("auth.user_list"))

    return render_template("user_form.html")


@bp.route("/users/delete/<int:id>", methods=["POST"])
@login_required
@roles_required("admin")
def delete_user(id):
    user = User.query.get_or_404(id)

    if user.id == current_user.id:
        flash("You can't delete your own account while logged in.", "danger")
        return redirect(url_for("auth.user_list"))

    db.session.delete(user)
    db.session.commit()
    flash("User removed.", "warning")
    return redirect(url_for("auth.user_list"))
