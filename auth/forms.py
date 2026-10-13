from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    identifier = StringField(
        "Username or email",
        validators=[DataRequired(), Length(max=320)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(max=1024)],
    )
    remember = BooleanField("Remember me on this device")
    submit = SubmitField("Sign in")
