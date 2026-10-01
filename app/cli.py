import click
from flask import current_app
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import User


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Create database tables for local development."""
        db.create_all()
        click.echo("GlassLedger database initialized.")

    @app.cli.command("create-owner")
    @click.option("--username", prompt=True)
    @click.option("--display-name", prompt="Display name")
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_owner(username, display_name, email, password):
        """Create the first owner account."""
        normalized_username = username.strip().lower()
        normalized_email = email.strip().lower()

        if User.query.filter_by(username=normalized_username).first():
            raise click.ClickException("That username already exists.")
        if User.query.filter_by(email=normalized_email).first():
            raise click.ClickException("That email already exists.")

        user = User(
            username=normalized_username,
            display_name=display_name.strip(),
            email=normalized_email,
            password_hash=generate_password_hash(password),
            role="OWNER",
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        current_app.logger.info("Owner account created: %s", normalized_username)
        click.echo("Owner account created.")
