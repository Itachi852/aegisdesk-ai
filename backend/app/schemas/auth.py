import re

from pydantic import BaseModel, Field, model_validator


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


class RegisterRequest(BaseModel):
    email: str | None = None
    phone: str | None = None
    password: str = Field(min_length=6, max_length=64)

    @model_validator(mode="after")
    def validate_account(self):
        if self.email:
            self.email = self.email.strip().lower()
        if self.phone:
            self.phone = self.phone.strip()

        if not self.email and not self.phone:
            raise ValueError("Please provide email or phone")
        if self.email and not EMAIL_PATTERN.match(self.email):
            raise ValueError("Please enter a valid email address")
        if self.phone and not PHONE_PATTERN.match(self.phone):
            raise ValueError("Please enter a valid phone number")
        return self


class LoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=6, max_length=64)


class UserResponse(BaseModel):
    id: int
    email: str | None = None
    phone: str | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
