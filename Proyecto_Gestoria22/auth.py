from datetime import datetime, timedelta
import jwt
import bcrypt

# CONFIGURACIÓN DEL TOKEN
SECRET_KEY = "mi_clave_secreta_super_hiper_confidencial_12345"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def verificar_password(plain_password: str, hashed_password: str) -> bool:
    # Convierte los textos a bytes para que bcrypt los compare de forma segura
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)

def obtener_password_hasheada(password: str) -> str:
    # Genera la sal y encripta la contraseña convirtiéndola a bytes
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    # Devuelve el hash como un texto (string) para que se guarde fácil en la Base de Datos
    return hashed.decode('utf-8')

def crear_token_acceso(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt