from pydantic import BaseModel, Field


class AuthUser(BaseModel):
    user_id: str
    display_name: str
    member_level: str = "Standard"
    recent_order_id: str | None = None


class LoginRequest(BaseModel):
    account: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    user_id: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=3, max_length=128)
    email: str | None = None
    phone: str | None = None


class AuthResponse(BaseModel):
    user: AuthUser
