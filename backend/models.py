import os
import json
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
DB_FILE = os.path.join(DATA_DIR, 'users.db')

os.makedirs(DATA_DIR, exist_ok=True)

class UserModel:
    def __init__(self):
        self._init_json()

    def _init_json(self):
        if not os.path.exists(USERS_FILE) or os.path.getsize(USERS_FILE) == 0:
            with open(USERS_FILE, 'w') as f:
                json.dump([], f)

    def _read(self):
        with open(USERS_FILE, 'r') as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)

    def _write(self, data):
        with open(USERS_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def create_user(self, username, email, password):
        users = self._read()
        for u in users:
            if u['username'] == username:
                return None, 'Username already exists'
            if u['email'] == email:
                return None, 'Email already registered'
        user = {
            'id': str(uuid.uuid4()),
            'username': username,
            'email': email,
            'password': generate_password_hash(password),
            'is_first_login': True,
            'created_at': datetime.utcnow().isoformat(),
        }
        users.append(user)
        self._write(users)
        return user, None

    def authenticate(self, login, password):
        users = self._read()
        for u in users:
            if u['username'] == login or u['email'] == login:
                if check_password_hash(u['password'], password):
                    return u, None
                return None, 'Invalid password'
        return None, 'User not found'

    def get_by_id(self, user_id):
        users = self._read()
        for u in users:
            if u['id'] == user_id:
                return u
        return None

    def set_first_login_done(self, user_id):
        users = self._read()
        for u in users:
            if u['id'] == user_id:
                u['is_first_login'] = False
                self._write(users)
                return True
        return False

user_model = UserModel()
