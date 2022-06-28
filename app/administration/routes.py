"""
Copyright (c) 2021 - present Orange Cyberdefense
"""

from distutils.command.build_scripts import first_line_re


from requests import session
from app.rules.util import clone_rule_repo, pull_rule_repo, remove_rule_repo
import json

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db
from app.administration import blueprint
from app.administration.forms import RepositoryForm, UserForm, LdapForm
from app.rules.models import RuleRepository
from app.administration.util import validate_user_form
from app.base import util
from app.base.models import User
from flask_principal import Principal, Permission, RoleNeed


@blueprint.route("/users")
@login_required

def users_list():
    admin = util.is_admin(current_user.role)
    if admin:
        users = User.query.all()
        return render_template(
            "users_list.html", users=users, user=current_user, segment="users"
        )
    else :
        return render_template("403.html"),403
        


@blueprint.route("/users/add", methods=["GET", "POST"])
@login_required
def users_add():
    admin = util.is_admin(current_user.role)
    if admin:
        user_form = UserForm()
        # POST / Form submitted
        if "save-user" in request.form:
            # Form is valid
            if user_form.validate_on_submit()and user_form.role.data == '0' or user_form.role.data=='1':
            # Perform additional custom checks
                err = validate_user_form(user_form)
                if err is not None :
                    flash(err, "error")
                    return render_template(
                        "users_edit.html",
                        edit=False,
                        form=user_form,
                        user=current_user,
                        segment="users",
                    )
                # We can create the user
                user = User(**request.form)
                # Remove id attribute to let the DB set it
                delattr(user, "id")
                db.session.add(user)
                db.session.commit()
                current_app.logger.info("New user added (user.id=%i)", user.id)
                flash("New user successfully added", "success")
                return redirect(url_for("administration_blueprint.users_list"))
            # Form is invalid, form.error is populated
            else:
                current_app.logger.warning(
                    "User add form invalid entries: %s", json.dumps(user_form.errors)
                )
                flash(str(user_form.errors), "error")
                return render_template(
                    "users_edit.html",
                    edit=False,
                    form=user_form,
                    user=current_user,
                    segment="users",
                )
        # GET / Display form
        else:
            return render_template(
                "users_edit.html",
                edit=False,
                form=user_form,
                user=current_user,
                segment="users",
            )
    else :
        return render_template("403.html"),403


@blueprint.route("/users/edit/<user_id>", methods=["GET", "POST"])
@login_required
def users_edit(user_id):
    admin = util.is_admin(current_user.role)
    if admin:
        edit_user = User.query.filter_by(id=user_id).first()
        # POST / Form submitted
        if "save-user" in request.form:
            user_form = UserForm()
            # Form is valid
            if user_form.validate_on_submit():
                # Perform additional custom validation
                err = validate_user_form(
                    form=user_form,
                    skip_username=(edit_user.username == user_form.username.data),
                    skip_email=(edit_user.email == user_form.email.data),
                    skip_password=(user_form.password.data == ""),
                )
                if err is not None:
                    flash(err, "error")
                    return render_template(
                        "users_edit.html",
                        edit=True,
                        form=UserForm(obj=edit_user),
                        user=current_user,
                        segment="users",
                    )
                # Change the password if needed only
                if user_form.password.data == "":
                    edit_password = edit_user.password
                else:
                    edit_password = util.hash_pass(user_form.password.data)
                # User can be updated
                user_form.populate_obj(edit_user)
                edit_user.password = edit_password
                db.session.commit()
                current_app.logger.info("User updated (user.id=%i)", user_form.id.data)
                flash("User successfully updated", "success")
                return redirect(url_for("administration_blueprint.users_list"))
            # Form is invalid, form.error is populated
            else:
                current_app.logger.warning(
                    "User edit form invalid entries: %s", json.dumps(user_form.errors)
                )
                flash(str(user_form.errors), "error")
                return render_template(
                    "users_edit.html",
                    edit=True,
                    form=UserForm(obj=edit_user),
                    user=current_user,
                    segment="users",
                )
        # GET / Display form
        else:
            return render_template(
                "users_edit.html",
                edit=True,
                form=UserForm(obj=edit_user),
                user=current_user,
                segment="users",
            )
    else:
        return render_template("403.html"),403


@blueprint.route("/users/remove/<user_id>")
@login_required
def users_remove(user_id):
    admin = util.is_admin(current_user.role)
    if admin:
        user = User.query.filter_by(id=user_id).first_or_404()
        db.session.delete(user)
        db.session.commit()
        current_app.logger.info("User removed (user.id=%i)", user.id)
        flash("User successfully deleted", "success")
        return redirect(url_for("administration_blueprint.users_list"))
    else:
        return render_template("403.html"),403


@blueprint.route("/ldap")
@login_required
def ldap_engine():
    admin = util.is_admin(current_user.role)
    if admin:
        return render_template(
            "ldap_engine.html",
            form=LdapForm()
        )
    else :
        return render_template("403.html"),403
        


@blueprint.route("/repos")
@login_required
def repos_list():
    rule_repos = RuleRepository.query.all()
    return render_template(
        "repos_list.html",
        rule_repos=rule_repos,
        user=current_user,
        segment="repos",
    )


@blueprint.route("/repos/add", methods=["GET", "POST"])
@login_required
def repos_add():
    repo_form = RepositoryForm()
    # POST / Form submitted
    if "save-repo" in request.form:
        # Form is valid
        if repo_form.validate_on_submit():
            # Repo name should be unique
            if RuleRepository.query.filter_by(name=repo_form.name.data).first() is not None:
                flash("Name is already registered for another repository", "error")
                return render_template(
                    "repos_edit.html",
                    edit=False,
                    form=repo_form,
                    user=current_user,
                    segment="users",
                )
            # We can create the repo
            repo = RuleRepository(
                name=repo_form.name.data,
                description=repo_form.description.data,
                uri=repo_form.uri.data,
            )
            username = repo_form.git_username.data
            token= repo_form.git_token.data
           
            # Clone the repo
            clone_rule_repo(repo, username, token)
            # Save repo in DB
            db.session.add(repo)
            db.session.commit()
            current_app.logger.info("New repo added (repo.id=%i)", repo.id)
            flash("New repository successfully added", "success")
            return redirect(url_for("administration_blueprint.repos_list"))
        # Form is invalid, form.error is populated
        else:
            current_app.logger.warning(
                "Repository add form invalid entries: %s", json.dumps(repo_form.errors)
            )
            flash(str(repo_form.errors), "error")
            return render_template(
                "repos_edit.html",
                edit=False,
                form=repo_form,
                user=current_user,
                segment="repos",
            )
    # GET / Display form
    else:
        return render_template(
            "repos_edit.html",
            edit=False,
            form=repo_form,
            user=current_user,
            segment="repos",
        )


@blueprint.route("/repos/edit/<repo_id>", methods=["GET", "POST"])
@login_required
def repos_edit(repo_id):
    edit_repo = RuleRepository.query.filter_by(id=repo_id).first()
    # POST / Form submitted
    if "save-repo" in request.form:
        repo_form = RepositoryForm()
        # Form is valid
        if repo_form.validate_on_submit():
            # Repo can be updated
            repo_form.populate_obj(edit_repo)
            db.session.commit()
            current_app.logger.info("Repo updated (repo.id=%i)", repo_form.id.data)
            flash("Repository successfully updated", "success")
            return redirect(url_for("administration_blueprint.repos_list"))
        # Form is invalid, form.error is populated
        else:
            current_app.logger.warning(
                "Repository edit form invalid entries: %s", json.dumps(repo_form.errors)
            )
            flash(str(repo_form.errors), "error")
            return render_template(
                "repos_edit.html",
                edit=True,
                form=RepositoryForm(obj=edit_repo),
                user=current_user,
                segment="repos",
            )
    # GET / Display form
    else:
        return render_template(
            "repos_edit.html",
            edit=True,
            form=RepositoryForm(obj=edit_repo),
            user=current_user,
            segment="repos",
        )


@blueprint.route("/repos/remove/<repo_id>")
@login_required
def repos_remove(repo_id):
    repo = RuleRepository.query.filter_by(id=repo_id).first_or_404()
    remove_rule_repo(repo)
    current_app.logger.info("Repository removed (repo.id=%i)", repo.id)
    flash("Repository successfully deleted", "success")
    return redirect(url_for("administration_blueprint.repos_list"))


@blueprint.route("/repos/pull/<repo_id>")
@login_required
def repos_pull(repo_id):
    repo = RuleRepository.query.filter_by(id=repo_id).first_or_404()
    pull_rule_repo(repo)
    current_app.logger.info("Git pull on repository (repo.id=%i)", repo.id)
    flash("Latest rules were successfully pulled for the repository", "success")
    return redirect(url_for("administration_blueprint.repos_list"))