import time
import jwt
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pansou_py.models.schemas import LoginRequest, LoginResponse
from pansou_py.core.config import settings

router = APIRouter()
security = HTTPBearer(auto_error=False)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    if not settings.AUTH_ENABLED:
        return {}
    if not credentials:
        raise HTTPException(status_code=401, detail={"error": "AUTH_TOKEN_MISSING", "code": "AUTH_TOKEN_MISSING"})
    try:
        payload = jwt.decode(credentials.credentials, settings.AUTH_JWT_SECRET, algorithms=["HS256"])
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "AUTH_TOKEN_INVALID", "code": "AUTH_TOKEN_INVALID"})

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    users = settings.auth_users_map
    if req.username not in users or users[req.username] != req.password:
        raise HTTPException(status_code=401, detail={"error": "用户名或密码错误"})
    
    expires_at = int(time.time()) + int(settings.AUTH_TOKEN_EXPIRY * 3600)
    token = jwt.encode(
        {"username": req.username, "exp": expires_at},
        settings.AUTH_JWT_SECRET,
        algorithm="HS256"
    )
    return LoginResponse(token=token, expires_at=expires_at, username=req.username)

@router.post("/verify")
def verify(token_payload: Dict[str, Any] = Depends(verify_token)):
    return {"valid": True, "username": token_payload.get("username", "anonymous")}

@router.post("/logout")
def logout():
    return {"message": "退出成功"}
