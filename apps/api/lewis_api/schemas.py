import uuid

from pydantic import BaseModel, EmailStr


class SignupIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str

    model_config = {"from_attributes": True}


class ProfileOut(BaseModel):
    resume_text: str | None
    raw_prefs_text: str | None
    structured_prefs: dict

    model_config = {"from_attributes": True}


class PrefsIn(BaseModel):
    raw_prefs_text: str
