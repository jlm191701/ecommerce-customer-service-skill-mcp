from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import pymysql
from fastapi import APIRouter, HTTPException
from pymysql.cursors import DictCursor

from app.core.config import settings
from app.schemas.auth import AuthResponse, AuthUser, LoginRequest, RegisterRequest

router = APIRouter(tags=["auth"])

ACCOUNT_ALIASES = {
    "小蒋": "user_test",
    "xiaojiang": "user_test",
    "林小北": "user_demo",
    "linxiaobei": "user_demo",
    "周明": "user_vip",
    "zhouming": "user_vip",
}


def _password_hash(password: str) -> str:
    return hashlib.sha256(f"aurora-demo:{password}".encode("utf-8")).hexdigest()


def _connection_kwargs() -> dict[str, Any]:
    return {
        "host": settings.mysql_host,
        "port": settings.mysql_port,
        "user": settings.mysql_user,
        "password": settings.mysql_password.get_secret_value()
        if settings.mysql_password
        else "",
        "database": settings.mysql_database,
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


def _mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        return f"{name[0]}***@{domain}"
    return f"{name[:2]}***@{domain}"


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 7:
        return phone
    return f"{digits[:3]}****{digits[-4:]}"


def _ensure_credentials_table(connection: pymysql.connections.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_credentials (
              user_id VARCHAR(64) PRIMARY KEY,
              password_hash VARCHAR(128) NOT NULL,
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              CONSTRAINT fk_credentials_user FOREIGN KEY (user_id) REFERENCES users(user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        for user in users:
            cursor.execute(
                """
                INSERT IGNORE INTO user_credentials (user_id, password_hash)
                VALUES (%s, %s)
                """,
                (user["user_id"], _password_hash("123456")),
            )


def _load_auth_user(
    connection: pymysql.connections.Connection,
    user_id: str,
) -> AuthUser:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT u.user_id, u.display_name, COALESCE(m.member_level, 'Standard') AS member_level
            FROM users u
            LEFT JOIN memberships m ON m.user_id = u.user_id
            WHERE u.user_id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        cursor.execute(
            """
            SELECT order_id
            FROM orders
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        latest_order = cursor.fetchone()
    return AuthUser(
        user_id=user["user_id"],
        display_name=user["display_name"],
        member_level=user["member_level"],
        recent_order_id=latest_order["order_id"] if latest_order else None,
    )


def _login(request: LoginRequest) -> AuthResponse:
    account = request.account.strip()
    canonical_account = ACCOUNT_ALIASES.get(account, ACCOUNT_ALIASES.get(account.lower(), account))
    connection = pymysql.connect(**_connection_kwargs())
    try:
        _ensure_credentials_table(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.user_id, c.password_hash
                FROM user_credentials c
                JOIN users u ON u.user_id = c.user_id
                WHERE c.user_id = %s OR u.display_name = %s
                LIMIT 1
                """,
                (canonical_account, account),
            )
            credential = cursor.fetchone()
            if not credential or credential["password_hash"] != _password_hash(request.password):
                raise HTTPException(status_code=401, detail="invalid_credentials")
        user = _load_auth_user(connection, credential["user_id"])
        connection.commit()
        return AuthResponse(user=user)
    except HTTPException:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise HTTPException(status_code=500, detail=type(exc).__name__) from exc
    finally:
        connection.close()


def _register(request: RegisterRequest) -> AuthResponse:
    user_id = request.user_id.strip()
    display_name = request.display_name.strip()
    connection = pymysql.connect(**_connection_kwargs())
    try:
        _ensure_credentials_table(connection)
        with connection.cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="user_exists")
            cursor.execute(
                """
                INSERT INTO users (user_id, display_name, phone_masked, email_masked)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user_id,
                    display_name,
                    _mask_phone(request.phone),
                    _mask_email(request.email),
                ),
            )
            cursor.execute(
                """
                INSERT INTO memberships (user_id, member_level, points, growth_value)
                VALUES (%s, 'Standard', 0, 0)
                """,
                (user_id,),
            )
            cursor.execute(
                """
                INSERT INTO user_credentials (user_id, password_hash)
                VALUES (%s, %s)
                """,
                (user_id, _password_hash(request.password)),
            )
        user = _load_auth_user(connection, user_id)
        connection.commit()
        return AuthResponse(user=user)
    except HTTPException:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise HTTPException(status_code=500, detail=type(exc).__name__) from exc
    finally:
        connection.close()


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest) -> AuthResponse:
    return await asyncio.to_thread(_login, request)


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest) -> AuthResponse:
    return await asyncio.to_thread(_register, request)
