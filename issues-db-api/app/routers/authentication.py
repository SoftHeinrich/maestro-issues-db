from datetime import datetime, timedelta

from app.settings import SECRET_KEY
from app.dependencies import users_collection
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, OAuth2
from fastapi.security.utils import get_authorization_scheme_param
from fastapi.openapi.models import OAuthFlows as OAuthFlowsModel
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError
from typing import Optional, Dict

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120


class OAuth2PasswordBearerWithCookie(OAuth2):
    def __init__(
        self,
        tokenUrl: str,
        scheme_name: Optional[str] = None,
        scopes: Optional[Dict[str, str]] = None,
        auto_error: bool = True,
    ):
        if not scopes:
            scopes = {}
        flows = OAuthFlowsModel(password={"tokenUrl": tokenUrl, "scopes": scopes})
        super().__init__(flows=flows, scheme_name=scheme_name, auto_error=auto_error)

    async def __call__(self, request: Request) -> Optional[str]:
        if request.headers.get("Authorization"):
            authorization: str = request.headers.get("Authorization")
        else:
            authorization: str = request.cookies.get("access_token")  #changed to accept access token from httpOnly Cookie
        
        scheme, param = get_authorization_scheme_param(authorization)
        if not authorization or scheme.lower() != "bearer":
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                return None
        return param


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str


class User(BaseModel):
    username: str
    password: str


class Password(BaseModel):
    password: str


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="token")
router = APIRouter(tags=["authentication"])


CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect username or password",
    headers={"WWW-Authenticate": "Bearer"},
)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def existing_user(username: str) -> bool:
    user = users_collection.find_one({"_id": username}, ["_id"])
    return user is not None


def authenticate_user(username: str, password: str) -> str | None:
    user = users_collection.find_one(
        {
            "_id": username,
        }
    )
    if user is None:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    # Return username
    return user["_id"]


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def validate_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    username: str = payload.get("username")
    if username is None or not existing_user(username):
        raise CREDENTIALS_EXCEPTION
    return {"username": username}


@router.post("/token", response_model=Token)
def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Provide your username and password as form data to get an access token.
    """
    username = authenticate_user(form_data.username, form_data.password)
    if username is None:
        raise CREDENTIALS_EXCEPTION
    access_token = create_access_token(data={"username": username})
    response.set_cookie(key="access_token",
                        value=f"bearer {access_token}",
                        httponly=True,
                        secure=True,
                        samesite="none")
    return {"access_token": access_token, "token_type": "bearer", "username": username}


@router.post("/refresh-token", response_model=Token)
def refresh_token(response: Response, token=Depends(validate_token)):
    """
    Endpoint for refreshing your access token.
    :param token: current access token
    :return: refreshed token
    """
    access_token = create_access_token(token)
    response.set_cookie(key="access_token",
                        value=f"bearer {access_token}",
                        httponly=True,
                        secure=True,
                        samesite="none")
    return {"access_token": access_token, "token_type": "bearer", "username": token["username"]}


@router.post("/create-account")
def create_account(new_account: User, token=Depends(validate_token)):
    """
    Create a new account with the provided username and password.
    """
    try:
        users_collection.insert_one(
            {
                "_id": new_account.username,
                "hashed_password": get_password_hash(new_account.password),
            }
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already exists"
        )


@router.post("/change-password")
def change_password(request: Password, token=Depends(validate_token)):
    """
    Change the password of your account.
    """
    users_collection.update_one(
        {"_id": token["username"]},
        {"$set": {"hashed_password": get_password_hash(request.password)}},
    )
