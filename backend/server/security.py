import hashlib, hmac, secrets, time
import jwt
from .config import SECRET

ITER = 200_000


def hash_password(p: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", p.encode(), salt, ITER)
    return f"pbkdf2${ITER}${salt.hex()}${dk.hex()}"


def verify_password(p: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        new = hashlib.pbkdf2_hmac("sha256", p.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(new.hex(), dk)
    except Exception:
        return False


def make_token(uid: int, role: str, hours: int = 12) -> str:
    return jwt.encode({"sub": str(uid), "role": role, "exp": int(time.time()) + hours * 3600}, SECRET, algorithm="HS256")


def read_token(t: str) -> dict:
    return jwt.decode(t, SECRET, algorithms=["HS256"])


def code_hash(email: str, code: str) -> str:
    return hashlib.sha256((SECRET + email + code).encode()).hexdigest()
