import uuid
from datetime import datetime

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


class SavedJobIn(BaseModel):
    source: str
    company: str
    title: str
    location: str | None = None
    url: str
    score: int | None = None
    reason: str | None = None
    raw: dict = {}


class SavedJobOut(BaseModel):
    id: uuid.UUID
    source: str
    company: str
    title: str
    location: str | None
    url: str
    score: int | None
    reason: str | None
    saved_at: datetime

    model_config = {"from_attributes": True}
