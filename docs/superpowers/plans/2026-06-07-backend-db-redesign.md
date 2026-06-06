# 后端 + 数据库重构实现计划（scope A：先跑通采集）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把后端从旧「单用户/无密码/6 维」模型净重设为「医护口令认证 + 患者(含 subject_id) + PII 分表 + 采集归属到医护/患者/设备 + 按患者历史」的临床模型，先跑通数据采集端到端。

**Architecture:** Flask 改为 app-factory + 蓝图（blueprint）结构以便测试；`db = SQLAlchemy()` 不再绑定在 import 期。新建 6 张表，medico 口令用 bcrypt 哈希、JWT 携带 `clinician_id`。采集上传内联跑 SVM（scope A 仍只落 6 维）。所有接口 pytest + SQLite 内存库做 TDD。

**Tech Stack:** Flask 2.3、Flask-SQLAlchemy 3.0、PyJWT、bcrypt、scikit-learn（SVM 内联）、pytest + SQLite(内存) 测试。

**配套文档：** 设计 `docs/superpowers/specs/2026-06-07-backend-db-redesign-design.md`；前后端对齐 `docs/superpowers/specs/2026-06-07-frontend-backend-alignment.md`。

**范围：** 仅后端。前端接入（App 改 enable/login/患者/上传/设备）是独立计划，见末尾「后续计划」。

**延后（不在本计划）：** 6→38 维落库、批量/会话上传、去标识化导出、SVM 异步化、admin 管理台重做。

---

## 文件结构

```
back/
  config.py            # 改：app-factory，db=SQLAlchemy() 不绑定
  app.py               # 改：create_app() 注册蓝图，删旧 import
  utils.py             # 改：Response 不变；token_required 改基于 clinician_id
  auth.py              # 新：bcrypt 哈希/校验 + JWT 签发/解析
  models/models.py     # 改：净重设 6 张表模型
  api/
    clinician.py       # 新：enable / login / me（蓝图 clinician_bp）
    patient.py         # 新：患者 CRUD + 历史（蓝图 patient_bp）
    device.py          # 改：设备 CRUD + raw_data 上传（蓝图 device_bp）
    analysis.py        # 新：SVM 推理（从 device.py 抽出）
    admin.py           # 删
    user.py            # 删
    weekly_schedule.py # 删
  tests/
    conftest.py        # 新：app/client/db fixtures + auth helper
    test_clinician.py
    test_patients.py
    test_devices.py
    test_raw_data.py
    test_history.py
  database_schema_mysql.sql  # 改：重写为新 6 表
  requirements.txt           # 改：加 bcrypt
  requirements-dev.txt       # 新：pytest
```

---

## Phase 0 — 依赖与测试地基

### Task 1: 加依赖（bcrypt + pytest）

**Files:**
- Modify: `back/requirements.txt`
- Create: `back/requirements-dev.txt`

- [ ] **Step 1: 在 requirements.txt 末尾追加 bcrypt**

在 `back/requirements.txt` 文件末尾追加：

```
# 口令哈希（医护口令，禁止明文）
bcrypt==4.1.2
```

- [ ] **Step 2: 创建 requirements-dev.txt**

`back/requirements-dev.txt`：

```
-r requirements.txt
pytest==8.0.0
```

- [ ] **Step 3: 安装**

Run: `cd back && pip install -r requirements-dev.txt`
Expected: 成功安装 bcrypt 与 pytest（已装的跳过）。

- [ ] **Step 4: Commit**

```bash
git add back/requirements.txt back/requirements-dev.txt
git commit -m "build: 加 bcrypt 与 pytest 依赖"
```

### Task 2: config.py 改 app-factory + db 解绑

**Files:**
- Modify: `back/config.py`

**背景：** 现 `config.py` 在 import 期就 `app = create_app()` 且 `db = SQLAlchemy(app)`，无法注入测试配置。改为 `db = SQLAlchemy()` 不绑定，`create_app(test_config=None)` 内 `db.init_app(app)`。

- [ ] **Step 1: 重写 config.py**

把 `back/config.py` 整体替换为：

```python
import os
from urllib.parse import quote_plus
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# 不在 import 期绑定 app：测试用 create_app(test_config) 注入 SQLite
db = SQLAlchemy()


def _require(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，请在 back/.env 或部署环境中配置（参考 .env.example）"
        )
    return value


def create_app(test_config=None):
    app = Flask(__name__, static_folder='uploads', static_url_path='/uploads')

    if test_config is not None:
        app.config.update(test_config)
    else:
        db_user = _require('DB_USER')
        db_pass = _require('DB_PASS')
        db_host = _require('DB_HOST')
        db_port = os.environ.get('DB_PORT', '3306')
        db_name = os.environ.get('DB_NAME', 'lanya')
        app.config['SQLALCHEMY_DATABASE_URI'] = (
            f'mysql+pymysql://{quote_plus(db_user)}:{quote_plus(db_pass)}@{db_host}:{db_port}/{db_name}'
        )
        app.config['SECRET_KEY'] = _require('SECRET_KEY')

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.static_folder = UPLOAD_FOLDER

    db.init_app(app)
    CORS(app)

    # 蓝图在 create_app 内注册，避免循环 import（Task 16 接入）
    from api.clinician import clinician_bp
    from api.patient import patient_bp
    from api.device import device_bp
    app.register_blueprint(clinician_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(device_bp)

    return app
```

> 注：此时蓝图模块尚未建（Task 6/10/12），先注释掉末尾 import+register 三行，等 Task 16 再打开。本步先只保留到 `CORS(app)` + `return app`，把蓝图注册段落用 `#` 注释。

- [ ] **Step 2: 临时注释蓝图注册**

把上面「蓝图在 create_app 内注册」那段 4 行（from import ×3 + register ×3）暂时注释掉，留 `CORS(app)` 后直接 `return app`。Task 16 再启用。

- [ ] **Step 3: Commit**

```bash
git add back/config.py
git commit -m "refactor: config 改 app-factory，db 解绑以支持测试注入"
```

### Task 3: pytest conftest（测试地基 + 冒烟）

**Files:**
- Create: `back/tests/__init__.py`
- Create: `back/tests/conftest.py`
- Create: `back/tests/test_smoke.py`

- [ ] **Step 1: 写冒烟测试（先失败）**

`back/tests/__init__.py`：空文件。

`back/tests/test_smoke.py`：

```python
def test_app_and_db_ready(client):
    # 应用能起、SQLite 内存库能建表
    resp = client.get('/__nonexistent__')
    assert resp.status_code == 404
```

- [ ] **Step 2: 运行，确认 fixture 缺失而失败**

Run: `cd back && python -m pytest tests/test_smoke.py -v`
Expected: FAIL —— `fixture 'client' not found`。

- [ ] **Step 3: 写 conftest.py**

`back/tests/conftest.py`：

```python
import os
import sys
import pytest

# 让 tests 能 import 到 back 根下的 config/app/models
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import create_app, db as _db


@pytest.fixture
def app():
    test_config = {
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret',
        'TESTING': True,
    }
    app = create_app(test_config)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db
```

- [ ] **Step 4: 运行冒烟，确认通过**

Run: `cd back && python -m pytest tests/test_smoke.py -v`
Expected: PASS。（此时 create_app 蓝图注册仍注释，models 仍是旧表也能建。）

- [ ] **Step 5: Commit**

```bash
git add back/tests/
git commit -m "test: pytest conftest（SQLite 内存库）+ 冒烟"
```

---

## Phase 1 — 数据模型

### Task 4: 净重设 SQLAlchemy 模型

**Files:**
- Modify: `back/models/models.py`
- Create: `back/tests/test_models.py`

- [ ] **Step 1: 写模型测试（先失败）**

`back/tests/test_models.py`：

```python
from models.models import Clinician, Device, Patient, PatientPII, DeviceRawData, DeviceTransformedData


def test_clinician_patient_pii_chain(db):
    c = Clinician(hospital='H', dept='D', name='Dr', phone='13800000000',
                  terminal_code='term-1', passcode_hash='x')
    db.session.add(c); db.session.commit()

    p = Patient(clinician_id=c.id, subject_id='#00001', gender='F', age=30)
    db.session.add(p); db.session.commit()

    pii = PatientPII(patient_id=p.id, name='张三', phone='13900000000')
    db.session.add(pii); db.session.commit()

    assert p.clinician_id == c.id
    assert pii.patient_id == p.id
    # 关系可回查
    assert c.patients[0].subject_id == '#00001'


def test_raw_and_transformed_attribution(db):
    c = Clinician(hospital='H', dept='D', name='Dr', phone='1', terminal_code='t', passcode_hash='x')
    db.session.add(c); db.session.commit()
    dev = Device(device_code='DEV1', device_name='insole', clinician_id=c.id)
    p = Patient(clinician_id=c.id, subject_id='#00002')
    db.session.add_all([dev, p]); db.session.commit()

    raw = DeviceRawData(device_id=dev.id, patient_id=p.id, clinician_id=c.id,
                        ax=1, ay=2, az=3, gx=4, gy=5, gz=6)
    db.session.add(raw); db.session.commit()
    tr = DeviceTransformedData(raw_data_id=raw.id, T1=0.1, T2=0.2, T3=0.3, T4=0.4, T5=0.5)
    db.session.add(tr); db.session.commit()

    assert raw.clinician_id == c.id and raw.patient_id == p.id and raw.device_id == dev.id
    assert tr.raw_data_id == raw.id
```

- [ ] **Step 2: 运行，确认 import 失败**

Run: `cd back && python -m pytest tests/test_models.py -v`
Expected: FAIL —— `ImportError: cannot import name 'Clinician'`。

- [ ] **Step 3: 重写 models.py**

把 `back/models/models.py` 整体替换为：

```python
from config import db
import datetime


class Clinician(db.Model):
    __tablename__ = 'clinicians'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    hospital = db.Column(db.String(100), nullable=False)
    dept = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    terminal_code = db.Column(db.String(100), nullable=False)
    passcode_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('phone', 'terminal_code', name='uq_clinician_phone_terminal'),
    )


class Device(db.Model):
    __tablename__ = 'devices'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    device_code = db.Column(db.String(50), unique=True, nullable=False)
    device_name = db.Column(db.String(100))
    is_enabled = db.Column(db.Boolean, default=True)
    clinician_id = db.Column(db.Integer, db.ForeignKey('clinicians.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    clinician = db.relationship('Clinician', backref='devices')


class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    clinician_id = db.Column(db.Integer, db.ForeignKey('clinicians.id'), nullable=False, index=True)
    subject_id = db.Column(db.String(20), unique=True, nullable=False)
    gender = db.Column(db.String(10))
    age = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_collected_at = db.Column(db.DateTime)

    clinician = db.relationship('Clinician', backref='patients')


class PatientPII(db.Model):
    __tablename__ = 'patient_pii'
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    address = db.Column(db.String(255))

    patient = db.relationship('Patient', backref=db.backref('pii', uselist=False))


class DeviceRawData(db.Model):
    __tablename__ = 'device_raw_data'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False, index=True)
    clinician_id = db.Column(db.Integer, db.ForeignKey('clinicians.id'), nullable=False, index=True)
    # scope A：暂存 6 维，38 维扩展见后续 spec
    ax = db.Column(db.Float, nullable=False)
    ay = db.Column(db.Float, nullable=False)
    az = db.Column(db.Float, nullable=False)
    gx = db.Column(db.Float, nullable=False)
    gy = db.Column(db.Float, nullable=False)
    gz = db.Column(db.Float, nullable=False)
    collected_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    device = db.relationship('Device', backref='raw_data')
    patient = db.relationship('Patient', backref='raw_data')


class DeviceTransformedData(db.Model):
    __tablename__ = 'device_transformed_data'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    raw_data_id = db.Column(db.Integer, db.ForeignKey('device_raw_data.id'), nullable=False, index=True)
    T1 = db.Column(db.Float, nullable=False)
    T2 = db.Column(db.Float, nullable=False)
    T3 = db.Column(db.Float, nullable=False)
    T4 = db.Column(db.Float, nullable=False)
    T5 = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    raw_data = db.relationship('DeviceRawData', backref=db.backref('transformed_data', uselist=False))
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_models.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add back/models/models.py back/tests/test_models.py
git commit -m "feat: 净重设数据模型（医护/设备/患者/PII/原始/分析 6 表）"
```

### Task 5: 重写 database_schema_mysql.sql

**Files:**
- Modify: `back/database_schema_mysql.sql`

> 此为 MySQL 权威 schema，与模型一致；无单测，靠 Task 4 模型测试 + 人工核对。

- [ ] **Step 1: 整体替换 schema 文件**

把 `back/database_schema_mysql.sql` 整体替换为：

```sql
-- 后端重构 scope A 权威 schema（与 back/models/models.py 一致）
-- 绿场净重设：无历史数据迁移。字符集 utf8mb4。

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS device_transformed_data;
DROP TABLE IF EXISTS device_raw_data;
DROP TABLE IF EXISTS patient_pii;
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS devices;
DROP TABLE IF EXISTS clinicians;
-- 旧模型表一并废弃
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS weekly_schedules;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE clinicians (
  id INT AUTO_INCREMENT PRIMARY KEY,
  hospital VARCHAR(100) NOT NULL,
  dept VARCHAR(100) NOT NULL,
  name VARCHAR(50) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  terminal_code VARCHAR(100) NOT NULL,
  passcode_hash VARCHAR(255) NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_clinician_phone_terminal (phone, terminal_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE devices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_code VARCHAR(50) NOT NULL UNIQUE,
  device_name VARCHAR(100),
  is_enabled TINYINT(1) DEFAULT 1,
  clinician_id INT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_devices_clinician (clinician_id),
  CONSTRAINT fk_devices_clinician FOREIGN KEY (clinician_id) REFERENCES clinicians(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE patients (
  id INT AUTO_INCREMENT PRIMARY KEY,
  clinician_id INT NOT NULL,
  subject_id VARCHAR(20) NOT NULL UNIQUE,
  gender VARCHAR(10),
  age INT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_collected_at DATETIME,
  KEY idx_patients_clinician (clinician_id),
  CONSTRAINT fk_patients_clinician FOREIGN KEY (clinician_id) REFERENCES clinicians(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE patient_pii (
  patient_id INT PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  email VARCHAR(100),
  address VARCHAR(255),
  CONSTRAINT fk_pii_patient FOREIGN KEY (patient_id) REFERENCES patients(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE device_raw_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id INT NOT NULL,
  patient_id INT NOT NULL,
  clinician_id INT NOT NULL,
  ax FLOAT NOT NULL, ay FLOAT NOT NULL, az FLOAT NOT NULL,
  gx FLOAT NOT NULL, gy FLOAT NOT NULL, gz FLOAT NOT NULL,
  collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_raw_device (device_id),
  KEY idx_raw_clinician (clinician_id),
  KEY idx_raw_patient_collected (patient_id, collected_at),
  CONSTRAINT fk_raw_device FOREIGN KEY (device_id) REFERENCES devices(id),
  CONSTRAINT fk_raw_patient FOREIGN KEY (patient_id) REFERENCES patients(id),
  CONSTRAINT fk_raw_clinician FOREIGN KEY (clinician_id) REFERENCES clinicians(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE device_transformed_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  raw_data_id INT NOT NULL,
  T1 FLOAT NOT NULL, T2 FLOAT NOT NULL, T3 FLOAT NOT NULL, T4 FLOAT NOT NULL, T5 FLOAT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_tr_raw (raw_data_id),
  CONSTRAINT fk_tr_raw FOREIGN KEY (raw_data_id) REFERENCES device_raw_data(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

- [ ] **Step 2: Commit**

```bash
git add back/database_schema_mysql.sql
git commit -m "feat: 重写 MySQL schema 为新 6 表，废弃 users/weekly_schedules"
```

---

## Phase 2 — 认证（bcrypt + JWT）

### Task 6: auth.py 口令哈希 + token 签发/解析

**Files:**
- Create: `back/auth.py`
- Create: `back/tests/test_auth.py`

- [ ] **Step 1: 写 auth 单测（先失败）**

`back/tests/test_auth.py`：

```python
from auth import hash_passcode, verify_passcode, issue_token, decode_token


def test_passcode_hash_roundtrip():
    h = hash_passcode('1234')
    assert h != '1234'              # 不存明文
    assert verify_passcode('1234', h) is True
    assert verify_passcode('9999', h) is False


def test_token_roundtrip(app):
    with app.app_context():
        token = issue_token(clinician_id=42)
        payload = decode_token(token)
        assert payload['clinician_id'] == 42
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_auth.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'auth'`。

- [ ] **Step 3: 写 auth.py**

`back/auth.py`：

```python
import datetime
import bcrypt
import jwt
from flask import current_app

TOKEN_TTL_DAYS = 7


def hash_passcode(passcode: str) -> str:
    return bcrypt.hashpw(passcode.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_passcode(passcode: str, passcode_hash: str) -> bool:
    try:
        return bcrypt.checkpw(passcode.encode('utf-8'), passcode_hash.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def issue_token(clinician_id: int) -> str:
    payload = {
        'clinician_id': clinician_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def decode_token(token: str) -> dict:
    return jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_auth.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add back/auth.py back/tests/test_auth.py
git commit -m "feat: auth 模块（bcrypt 口令哈希 + JWT 签发/解析）"
```

### Task 7: token_required 改基于 clinician

**Files:**
- Modify: `back/utils.py`
- Create: `back/tests/test_token_required.py`

- [ ] **Step 1: 写装饰器单测（先失败）**

`back/tests/test_token_required.py`：

```python
from flask import g
from auth import issue_token
from utils import token_required
from models.models import Clinician
from config import db


def _make_clinician():
    c = Clinician(hospital='H', dept='D', name='Dr', phone='1',
                  terminal_code='t', passcode_hash='x')
    db.session.add(c); db.session.commit()
    return c


def test_token_required_sets_clinician_id(app):
    with app.app_context():
        c = _make_clinician()
        token = issue_token(c.id)

        @token_required()
        def view():
            return {'cid': g.clinician_id}

        with app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            assert view()['cid'] == c.id


def test_token_required_missing_token(app):
    with app.app_context():
        @token_required()
        def view():
            return 'ok'

        with app.test_request_context():
            resp, status = view()
            assert status == 401
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_token_required.py -v`
Expected: FAIL —— 现 `token_required` 还在用 `User`/`g.user_id`，import `User` 已删会报错或断言不符。

- [ ] **Step 3: 重写 utils.py 的 token_required**

把 `back/utils.py` 整体替换为：

```python
from functools import wraps
import jwt
from flask import request, jsonify, g
from auth import decode_token
from models.models import Clinician


class Response:
    @staticmethod
    def success(data=None, msg="操作成功"):
        return {'code': 200, 'msg': msg, 'data': data}

    @staticmethod
    def error(code, msg="操作失败", data=None):
        return {'code': code, 'msg': msg, 'data': data}


def token_required():
    """校验 Bearer token，解析 clinician_id 存入 g.clinician_id。"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = None
            auth_header = request.headers.get('Authorization')
            if auth_header:
                parts = auth_header.split()
                if len(parts) == 2 and parts[0] == 'Bearer':
                    token = parts[1]

            if not token:
                return jsonify(Response.error(401, "Token缺失")), 401

            try:
                payload = decode_token(token)
                clinician_id = payload.get('clinician_id')
                if not clinician_id:
                    return jsonify(Response.error(401, "Token无效: 缺少医护信息")), 401
                clinician = Clinician.query.get(clinician_id)
                if not clinician:
                    return jsonify(Response.error(401, "医护不存在")), 401
                g.clinician_id = clinician.id
            except jwt.ExpiredSignatureError:
                return jsonify(Response.error(401, "Token已过期")), 401
            except jwt.InvalidTokenError:
                return jsonify(Response.error(401, "Token无效")), 401

            return f(*args, **kwargs)
        return decorated
    return decorator
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_token_required.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add back/utils.py back/tests/test_token_required.py
git commit -m "refactor: token_required 改基于 clinician_id，去掉 role/User"
```

---

## Phase 3 — 医护 API（clinician_bp）

### Task 8: /clinician/enable 启用注册

**Files:**
- Create: `back/api/clinician.py`
- Create: `back/tests/test_clinician.py`

- [ ] **Step 1: 写 enable 测试（先失败）**

`back/tests/test_clinician.py`：

```python
def _enable_payload(**over):
    p = {'hospital': '协和', 'dept': '骨科', 'name': '王医生',
         'phone': '13800000000', 'terminal_code': 'term-1', 'passcode': '1234'}
    p.update(over)
    return p


def test_enable_creates_clinician_and_returns_token(client):
    resp = client.post('/clinician/enable', json=_enable_payload())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    assert body['data']['token']
    assert body['data']['clinician']['name'] == '王医生'
    assert 'passcode' not in body['data']['clinician']  # 不回传口令


def test_enable_missing_field_rejected(client):
    resp = client.post('/clinician/enable', json=_enable_payload(passcode=''))
    assert resp.get_json()['code'] == 400
```

- [ ] **Step 2: 运行，确认失败（蓝图未注册）**

Run: `cd back && python -m pytest tests/test_clinician.py -v`
Expected: FAIL —— 404（路由不存在）。

- [ ] **Step 3: 创建 clinician.py 并写 enable**

`back/api/clinician.py`：

```python
from flask import Blueprint, request, jsonify, g
from config import db
from models.models import Clinician
from utils import Response, token_required
from auth import hash_passcode, verify_passcode, issue_token

clinician_bp = Blueprint('clinician', __name__)


def _clinician_public(c):
    return {'id': c.id, 'hospital': c.hospital, 'dept': c.dept,
            'name': c.name, 'phone': c.phone}


@clinician_bp.route('/clinician/enable', methods=['POST'])
def enable():
    data = request.json or {}
    required = ['hospital', 'dept', 'name', 'phone', 'terminal_code', 'passcode']
    if not all(data.get(k) for k in required):
        return jsonify(Response.error(400, "医院/科室/医生/手机/终端标识/口令均为必填")), 400

    existing = Clinician.query.filter_by(
        phone=data['phone'], terminal_code=data['terminal_code']).first()
    if existing:
        # 同手机同终端已启用：直接重发 token（幂等），口令不改
        return jsonify(Response.success(
            data={'token': issue_token(existing.id), 'clinician': _clinician_public(existing)},
            msg="该终端已启用"))

    c = Clinician(
        hospital=data['hospital'], dept=data['dept'], name=data['name'],
        phone=data['phone'], terminal_code=data['terminal_code'],
        passcode_hash=hash_passcode(data['passcode']))
    db.session.add(c)
    db.session.commit()
    return jsonify(Response.success(
        data={'token': issue_token(c.id), 'clinician': _clinician_public(c)},
        msg="启用成功"))
```

- [ ] **Step 4: 在 create_app 启用蓝图注册（仅 clinician_bp 先）**

打开 `back/config.py` 中 Task 2 注释掉的蓝图段，但**此阶段只注册已存在的蓝图**。把该段改为：

```python
    from api.clinician import clinician_bp
    app.register_blueprint(clinician_bp)
```

（patient_bp / device_bp 等 Task 11/14 再加；保持只 import 已存在模块，避免 ImportError。）

- [ ] **Step 5: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_clinician.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 6: Commit**

```bash
git add back/api/clinician.py back/tests/test_clinician.py back/config.py
git commit -m "feat: /clinician/enable 启用注册（bcrypt + 返回 token，幂等）"
```

### Task 9: /clinician/login 口令刷新 token

**Files:**
- Modify: `back/api/clinician.py`
- Modify: `back/tests/test_clinician.py`

- [ ] **Step 1: 追加 login 测试（先失败）**

在 `back/tests/test_clinician.py` 末尾追加：

```python
def test_login_with_correct_passcode(client):
    client.post('/clinician/enable', json=_enable_payload())
    resp = client.post('/clinician/login', json={
        'phone': '13800000000', 'terminal_code': 'term-1', 'passcode': '1234'})
    assert resp.get_json()['data']['token']


def test_login_wrong_passcode_rejected(client):
    client.post('/clinician/enable', json=_enable_payload())
    resp = client.post('/clinician/login', json={
        'phone': '13800000000', 'terminal_code': 'term-1', 'passcode': '0000'})
    assert resp.get_json()['code'] != 200
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_clinician.py -k login -v`
Expected: FAIL —— 404。

- [ ] **Step 3: 在 clinician.py 追加 login**

在 `back/api/clinician.py` 末尾追加：

```python
@clinician_bp.route('/clinician/login', methods=['POST'])
def login():
    data = request.json or {}
    if not all(data.get(k) for k in ('phone', 'terminal_code', 'passcode')):
        return jsonify(Response.error(400, "手机/终端标识/口令均为必填")), 400

    c = Clinician.query.filter_by(
        phone=data['phone'], terminal_code=data['terminal_code']).first()
    if not c or not verify_passcode(data['passcode'], c.passcode_hash):
        return jsonify(Response.error(401, "口令或终端不匹配")), 401

    return jsonify(Response.success(
        data={'token': issue_token(c.id), 'clinician': _clinician_public(c)},
        msg="登录成功"))
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_clinician.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
git add back/api/clinician.py back/tests/test_clinician.py
git commit -m "feat: /clinician/login 口令校验刷新 token"
```

### Task 10: /clinician/me 读/改资料

**Files:**
- Modify: `back/api/clinician.py`
- Modify: `back/tests/test_clinician.py`

- [ ] **Step 1: 追加 me 测试（先失败）**

在 `back/tests/test_clinician.py` 顶部加一个取 token 的 helper，并追加测试：

```python
def _token(client):
    resp = client.post('/clinician/enable', json=_enable_payload())
    return resp.get_json()['data']['token']


def test_get_me(client):
    token = _token(client)
    resp = client.get('/clinician/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.get_json()['data']['name'] == '王医生'


def test_put_me_updates_dept(client):
    token = _token(client)
    resp = client.put('/clinician/me', headers={'Authorization': f'Bearer {token}'},
                      json={'dept': '康复科'})
    assert resp.get_json()['data']['dept'] == '康复科'


def test_me_requires_token(client):
    resp = client.get('/clinician/me')
    assert resp.status_code == 401
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_clinician.py -k me -v`
Expected: FAIL —— 404 / 断言不符。

- [ ] **Step 3: 在 clinician.py 追加 me**

在 `back/api/clinician.py` 末尾追加：

```python
@clinician_bp.route('/clinician/me', methods=['GET'])
@token_required()
def get_me():
    c = Clinician.query.get(g.clinician_id)
    return jsonify(Response.success(data=_clinician_public(c)))


@clinician_bp.route('/clinician/me', methods=['PUT'])
@token_required()
def update_me():
    c = Clinician.query.get(g.clinician_id)
    data = request.json or {}
    for field in ('hospital', 'dept', 'name', 'phone'):
        if data.get(field):
            setattr(c, field, data[field])
    db.session.commit()
    return jsonify(Response.success(data=_clinician_public(c), msg="资料已更新"))
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_clinician.py -v`
Expected: PASS（7 passed）。

- [ ] **Step 5: Commit**

```bash
git add back/api/clinician.py back/tests/test_clinician.py
git commit -m "feat: /clinician/me 读/改医护资料"
```

---

## Phase 4 — 患者 API（patient_bp）

### Task 11: subject_id 生成器

**Files:**
- Create: `back/api/patient.py`
- Create: `back/tests/test_patients.py`

> subject_id 采用 `'#%05d' % patient.id`：先插入拿自增 id，再回填 subject_id，借主键保证全局唯一、无冲突。

- [ ] **Step 1: 写生成器测试（先失败）**

`back/tests/test_patients.py`：

```python
from api.patient import format_subject_id


def test_format_subject_id():
    assert format_subject_id(1) == '#00001'
    assert format_subject_id(427) == '#00427'
    assert format_subject_id(123456) == '#123456'
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_patients.py -v`
Expected: FAIL —— ImportError。

- [ ] **Step 3: 创建 patient.py + 生成器**

`back/api/patient.py`：

```python
from flask import Blueprint, request, jsonify, g
from config import db
from models.models import Patient, PatientPII, DeviceRawData, DeviceTransformedData
from utils import Response, token_required

patient_bp = Blueprint('patient', __name__)


def format_subject_id(n: int) -> str:
    return '#%05d' % n
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_patients.py -v`
Expected: PASS。

- [ ] **Step 5: 注册 patient_bp**

在 `back/config.py` 蓝图段追加：

```python
    from api.patient import patient_bp
    app.register_blueprint(patient_bp)
```

- [ ] **Step 6: Commit**

```bash
git add back/api/patient.py back/tests/test_patients.py back/config.py
git commit -m "feat: 患者蓝图 + subject_id 生成器"
```

### Task 12: POST /patients 新建（phone 必填 + 查重 + PII 分表）

**Files:**
- Modify: `back/api/patient.py`
- Modify: `back/tests/test_patients.py`

- [ ] **Step 1: 追加测试（先失败）**

在 `back/tests/test_patients.py` 末尾追加：

```python
def _token(client):
    resp = client.post('/clinician/enable', json={
        'hospital': 'H', 'dept': 'D', 'name': 'Dr', 'phone': '1',
        'terminal_code': 't', 'passcode': '1234'})
    return resp.get_json()['data']['token']


def _auth(client):
    return {'Authorization': f'Bearer {_token(client)}'}


def test_create_patient_assigns_subject_id(client):
    resp = client.post('/patients', headers=_auth(client),
                       json={'name': '张三', 'phone': '13900000000', 'gender': 'M', 'age': 40})
    data = resp.get_json()['data']
    assert data['subject_id'] == '#00001'
    assert data['id'] == 1
    assert data['existed'] is False


def test_create_patient_phone_required(client):
    resp = client.post('/patients', headers=_auth(client), json={'name': '张三'})
    assert resp.get_json()['code'] == 400


def test_create_patient_dedup_returns_existing(client):
    auth = _auth(client)
    client.post('/patients', headers=auth, json={'name': '张三', 'phone': '13900000000'})
    resp = client.post('/patients', headers=auth, json={'name': '张三', 'phone': '13900000000'})
    data = resp.get_json()['data']
    assert data['subject_id'] == '#00001'   # 命中既有，不新建
    assert data['existed'] is True
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_patients.py -k create -v`
Expected: FAIL —— 404。

- [ ] **Step 3: 追加 POST /patients**

在 `back/api/patient.py` 末尾追加：

```python
def _patient_public(p, existed=False):
    pii = p.pii
    return {
        'id': p.id, 'subject_id': p.subject_id,
        'gender': p.gender, 'age': p.age,
        'name': pii.name if pii else None,
        'phone': pii.phone if pii else None,
        'last_collected_at': p.last_collected_at.isoformat() if p.last_collected_at else None,
        'existed': existed,
    }


@patient_bp.route('/patients', methods=['POST'])
@token_required()
def create_patient():
    data = request.json or {}
    name = data.get('name')
    phone = data.get('phone')
    if not name or not phone:
        return jsonify(Response.error(400, "姓名与手机号为必填")), 400

    # 同医护下按 phone 查重（查 PII.phone，限本医护患者）
    dup = (db.session.query(Patient).join(PatientPII, PatientPII.patient_id == Patient.id)
           .filter(Patient.clinician_id == g.clinician_id, PatientPII.phone == phone).first())
    if dup:
        return jsonify(Response.success(data=_patient_public(dup, existed=True), msg="患者已存在"))

    p = Patient(clinician_id=g.clinician_id, subject_id='pending',
                gender=data.get('gender'), age=data.get('age'))
    db.session.add(p)
    db.session.flush()                       # 拿自增 id
    p.subject_id = format_subject_id(p.id)
    db.session.add(PatientPII(patient_id=p.id, name=name, phone=phone,
                              email=data.get('email'), address=data.get('address')))
    db.session.commit()
    return jsonify(Response.success(data=_patient_public(p), msg="新建患者成功"))
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_patients.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add back/api/patient.py back/tests/test_patients.py
git commit -m "feat: POST /patients 新建（phone 必填 + 同医护查重 + PII 分表 + 后端发 subject_id）"
```

### Task 13: GET /patients 列表 + GET /patients/<id> 详情（限本医护）

**Files:**
- Modify: `back/api/patient.py`
- Modify: `back/tests/test_patients.py`

- [ ] **Step 1: 追加测试（先失败）**

在 `back/tests/test_patients.py` 末尾追加：

```python
def test_list_patients_only_own(client):
    auth = _auth(client)
    client.post('/patients', headers=auth, json={'name': 'A', 'phone': '111'})
    client.post('/patients', headers=auth, json={'name': 'B', 'phone': '222'})
    resp = client.get('/patients', headers=auth)
    items = resp.get_json()['data']
    assert len(items) == 2


def test_get_patient_detail(client):
    auth = _auth(client)
    pid = client.post('/patients', headers=auth,
                      json={'name': 'A', 'phone': '111'}).get_json()['data']['id']
    resp = client.get(f'/patients/{pid}', headers=auth)
    assert resp.get_json()['data']['name'] == 'A'


def test_get_other_clinician_patient_forbidden(client):
    auth1 = _auth(client)
    pid = client.post('/patients', headers=auth1,
                      json={'name': 'A', 'phone': '111'}).get_json()['data']['id']
    # 第二个医护（不同 terminal_code）
    token2 = client.post('/clinician/enable', json={
        'hospital': 'H', 'dept': 'D', 'name': 'Dr2', 'phone': '2',
        'terminal_code': 't2', 'passcode': '1234'}).get_json()['data']['token']
    resp = client.get(f'/patients/{pid}', headers={'Authorization': f'Bearer {token2}'})
    assert resp.get_json()['code'] == 403
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_patients.py -k "list or detail or forbidden" -v`
Expected: FAIL —— 404。

- [ ] **Step 3: 追加列表与详情**

在 `back/api/patient.py` 末尾追加：

```python
@patient_bp.route('/patients', methods=['GET'])
@token_required()
def list_patients():
    patients = (Patient.query.filter_by(clinician_id=g.clinician_id)
                .order_by(Patient.last_collected_at.desc().nullslast(),
                          Patient.created_at.desc()).all())
    return jsonify(Response.success(data=[_patient_public(p) for p in patients]))


@patient_bp.route('/patients/<int:patient_id>', methods=['GET'])
@token_required()
def get_patient(patient_id):
    p = Patient.query.get(patient_id)
    if not p:
        return jsonify(Response.error(404, "患者不存在")), 404
    if p.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "无权访问该患者")), 403
    return jsonify(Response.success(data=_patient_public(p)))
```

> 注：SQLite 不支持 `nullslast()`；若测试报错，改用 `Patient.created_at.desc()` 单一排序（last_collected_at 排序留待 MySQL）。本计划测试不校验排序，安全起见可直接用 `.order_by(Patient.created_at.desc())`。

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_patients.py -v`
Expected: PASS（若 nullslast 报错，按上注改单一排序后再跑）。

- [ ] **Step 5: Commit**

```bash
git add back/api/patient.py back/tests/test_patients.py
git commit -m "feat: GET /patients 列表 + 详情（限本医护，越权 403）"
```

---

## Phase 5 — 设备 API（device_bp）

### Task 14: POST/GET/DELETE /devices（蓝牙注册，限本医护）

**Files:**
- Create: `back/api/device.py`（**先备份旧文件再重写**）
- Create: `back/tests/test_devices.py`

> 旧 `device.py` 用 `@app.route` + user_id，全部废弃。本任务重写为蓝图。SVM 与 raw_data 在 Task 15/16 加入。

- [ ] **Step 1: 写设备测试（先失败）**

`back/tests/test_devices.py`：

```python
def _auth(client):
    token = client.post('/clinician/enable', json={
        'hospital': 'H', 'dept': 'D', 'name': 'Dr', 'phone': '1',
        'terminal_code': 't', 'passcode': '1234'}).get_json()['data']['token']
    return {'Authorization': f'Bearer {token}'}


def test_register_device_via_bluetooth(client):
    resp = client.post('/devices', headers=_auth(client),
                       json={'device_code': 'INSOLE-001', 'device_name': '左脚鞋垫'})
    data = resp.get_json()['data']
    assert data['device_code'] == 'INSOLE-001'
    assert data['is_enabled'] is True


def test_register_device_requires_code(client):
    resp = client.post('/devices', headers=_auth(client), json={'device_name': 'x'})
    assert resp.get_json()['code'] == 400


def test_list_and_delete_device(client):
    auth = _auth(client)
    did = client.post('/devices', headers=auth,
                      json={'device_code': 'INSOLE-001'}).get_json()['data']['id']
    assert len(client.get('/devices', headers=auth).get_json()['data']) == 1
    assert client.delete(f'/devices/{did}', headers=auth).get_json()['code'] == 200
    assert len(client.get('/devices', headers=auth).get_json()['data']) == 0
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_devices.py -v`
Expected: FAIL —— 404。

- [ ] **Step 3: 备份旧 device.py 并重写为蓝图**

```bash
git mv back/api/device.py back/api/device_legacy.py.bak
```

新建 `back/api/device.py`：

```python
from flask import Blueprint, request, jsonify, g
from config import db
from models.models import Device
from utils import Response, token_required

device_bp = Blueprint('device', __name__)


def _device_public(d):
    return {'id': d.id, 'device_code': d.device_code,
            'device_name': d.device_name, 'is_enabled': d.is_enabled}


@device_bp.route('/devices', methods=['POST'])
@token_required()
def register_device():
    """蓝牙连接成功后注册鞋垫（非扫码）。"""
    data = request.json or {}
    device_code = data.get('device_code')
    if not device_code:
        return jsonify(Response.error(400, "device_code 为必填")), 400

    existing = Device.query.filter_by(device_code=device_code).first()
    if existing:
        # 已注册：归属到当前医护并返回（设备换医护时更新归属）
        existing.clinician_id = g.clinician_id
        if data.get('device_name'):
            existing.device_name = data['device_name']
        db.session.commit()
        return jsonify(Response.success(data=_device_public(existing), msg="设备已注册"))

    d = Device(device_code=device_code, device_name=data.get('device_name'),
               clinician_id=g.clinician_id, is_enabled=True)
    db.session.add(d)
    db.session.commit()
    return jsonify(Response.success(data=_device_public(d), msg="设备注册成功"))


@device_bp.route('/devices', methods=['GET'])
@token_required()
def list_devices():
    devices = Device.query.filter_by(clinician_id=g.clinician_id).all()
    return jsonify(Response.success(data=[_device_public(d) for d in devices]))


@device_bp.route('/devices/<int:device_id>', methods=['DELETE'])
@token_required()
def delete_device(device_id):
    d = Device.query.get(device_id)
    if not d:
        return jsonify(Response.error(404, "设备不存在")), 404
    if d.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "无权删除该设备")), 403
    db.session.delete(d)
    db.session.commit()
    return jsonify(Response.success(msg="设备已删除"))
```

- [ ] **Step 4: 注册 device_bp**

在 `back/config.py` 蓝图段追加：

```python
    from api.device import device_bp
    app.register_blueprint(device_bp)
```

- [ ] **Step 5: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_devices.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 6: Commit**

```bash
git add back/api/device.py back/api/device_legacy.py.bak back/tests/test_devices.py back/config.py
git commit -m "feat: 设备蓝图（蓝牙注册/列表/删除，限本医护）"
```

---

## Phase 6 — 采集上传 + SVM + 历史

### Task 15: analysis.py 抽出 SVM 推理

**Files:**
- Create: `back/api/analysis.py`
- Create: `back/tests/test_analysis.py`

> 从旧 `device_legacy.py.bak` 把 `DataAnalysisTwo` / `load_or_train_model` / 模块级 `model` 搬到独立模块，device.py 只调用，保持上传逻辑专注。

- [ ] **Step 1: 写 analysis 测试（先失败）**

`back/tests/test_analysis.py`：

```python
from api.analysis import analyze


def test_analyze_returns_five_floats():
    t = analyze(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert len(t) == 5
    assert all(isinstance(x, float) for x in t)
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_analysis.py -v`
Expected: FAIL —— ImportError。

- [ ] **Step 3: 写 analysis.py**

`back/api/analysis.py`：

```python
import os
import pickle
import numpy as np
from sklearn.svm import SVC
from sklearn.multioutput import MultiOutputClassifier

_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'my_svm_model.pkl')


def _load_or_train_model(model_path=_MODEL_PATH):
    if os.path.exists(model_path):
        try:
            with open(model_path, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    # 无 pkl 时用假数据训练占位模型（与旧实现一致；真实模型由研发提供 pkl）
    X_fake = np.random.rand(10, 6)
    y_fake = np.random.randint(0, 2, size=(10, 5))
    m = MultiOutputClassifier(SVC(probability=True))
    m.fit(X_fake, y_fake)
    return m


_model = _load_or_train_model()


def analyze(ax, ay, az, gx, gy, gz):
    """返回 (T1..T5)，取每个输出类别为 1 的概率。"""
    x = np.array([[ax, ay, az, gx, gy, gz]], dtype=np.float32)
    probas = _model.predict_proba(x)
    return tuple(float(probas[i][0][1]) for i in range(5))
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_analysis.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add back/api/analysis.py back/tests/test_analysis.py
git commit -m "feat: analysis 模块抽出 SVM 推理（analyze）"
```

### Task 16: POST /devices/<code>/raw_data 上传（带 patient_id + 归属 + SVM）

**Files:**
- Modify: `back/api/device.py`
- Create: `back/tests/test_raw_data.py`

- [ ] **Step 1: 写上传测试（先失败）**

`back/tests/test_raw_data.py`：

```python
def _setup(client):
    auth = {'Authorization': f"Bearer {client.post('/clinician/enable', json={'hospital':'H','dept':'D','name':'Dr','phone':'1','terminal_code':'t','passcode':'1234'}).get_json()['data']['token']}"}
    pid = client.post('/patients', headers=auth, json={'name': 'A', 'phone': '111'}).get_json()['data']['id']
    client.post('/devices', headers=auth, json={'device_code': 'INSOLE-001'})
    return auth, pid


def _sensor(**over):
    d = {'ax': 1, 'ay': 2, 'az': 3, 'gx': 4, 'gy': 5, 'gz': 6}
    d.update(over)
    return d


def test_upload_raw_data_attributes_and_runs_svm(client):
    auth, pid = _setup(client)
    body = _sensor(); body['patient_id'] = pid
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=body)
    data = resp.get_json()['data']
    assert data['raw_data_id'] >= 1
    assert 'T1' in data['transformed']


def test_upload_requires_patient_id(client):
    auth, pid = _setup(client)
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=_sensor())
    assert resp.get_json()['code'] == 400


def test_upload_unknown_device_404(client):
    auth, pid = _setup(client)
    body = _sensor(); body['patient_id'] = pid
    resp = client.post('/devices/NOPE/raw_data', headers=auth, json=body)
    assert resp.get_json()['code'] == 404


def test_upload_extra_38_fields_ignored(client):
    auth, pid = _setup(client)
    body = _sensor(lp1=9, right_ax=8); body['patient_id'] = pid   # 多余字段不报错
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=body)
    assert resp.get_json()['code'] == 200
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_raw_data.py -v`
Expected: FAIL —— 404。

- [ ] **Step 3: 在 device.py 追加 raw_data 上传**

先在 `back/api/device.py` 顶部 import 区补充：

```python
import datetime
from models.models import Patient, DeviceRawData, DeviceTransformedData
from api.analysis import analyze
```

在文件末尾追加：

```python
@device_bp.route('/devices/<string:device_code>/raw_data', methods=['POST'])
@token_required()
def upload_raw_data(device_code):
    device = Device.query.filter_by(device_code=device_code,
                                    clinician_id=g.clinician_id).first()
    if not device:
        return jsonify(Response.error(404, "设备不存在或不属于当前医护")), 404

    data = request.json or {}
    patient_id = data.get('patient_id')
    if not patient_id:
        return jsonify(Response.error(400, "patient_id 为必填")), 400

    patient = Patient.query.get(patient_id)
    if not patient or patient.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "患者不存在或不属于当前医护")), 403

    # scope A 只落 6 维；38 维其余字段后端先忽略
    try:
        ax = float(data['ax']); ay = float(data['ay']); az = float(data['az'])
        gx = float(data['gx']); gy = float(data['gy']); gz = float(data['gz'])
    except (KeyError, TypeError, ValueError):
        return jsonify(Response.error(400, "缺少或非法的 6 轴传感器字段")), 400

    now = datetime.datetime.utcnow()
    raw = DeviceRawData(device_id=device.id, patient_id=patient.id,
                        clinician_id=g.clinician_id,
                        ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz,
                        collected_at=now, uploaded_at=now)
    db.session.add(raw)
    db.session.flush()

    T1, T2, T3, T4, T5 = analyze(ax, ay, az, gx, gy, gz)
    db.session.add(DeviceTransformedData(raw_data_id=raw.id,
                                         T1=T1, T2=T2, T3=T3, T4=T4, T5=T5))
    patient.last_collected_at = now
    db.session.commit()

    return jsonify(Response.success(
        data={'raw_data_id': raw.id,
              'transformed': {'T1': T1, 'T2': T2, 'T3': T3, 'T4': T4, 'T5': T5}},
        msg="数据上传成功"))
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_raw_data.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
git add back/api/device.py back/tests/test_raw_data.py
git commit -m "feat: 上传原始数据带 patient_id，归属 clinician+patient+device，内联跑 SVM"
```

### Task 17: GET /patients/<id>/data 按患者历史（分页 + 时间范围）

**Files:**
- Modify: `back/api/patient.py`
- Create: `back/tests/test_history.py`

- [ ] **Step 1: 写历史测试（先失败）**

`back/tests/test_history.py`：

```python
def _setup_with_data(client, n=3):
    auth = {'Authorization': f"Bearer {client.post('/clinician/enable', json={'hospital':'H','dept':'D','name':'Dr','phone':'1','terminal_code':'t','passcode':'1234'}).get_json()['data']['token']}"}
    pid = client.post('/patients', headers=auth, json={'name': 'A', 'phone': '111'}).get_json()['data']['id']
    client.post('/devices', headers=auth, json={'device_code': 'INSOLE-001'})
    for i in range(n):
        client.post('/devices/INSOLE-001/raw_data', headers=auth,
                    json={'ax': i, 'ay': 2, 'az': 3, 'gx': 4, 'gy': 5, 'gz': 6, 'patient_id': pid})
    return auth, pid


def test_history_returns_items_with_transformed(client):
    auth, pid = _setup_with_data(client, n=3)
    resp = client.get(f'/patients/{pid}/data', headers=auth)
    data = resp.get_json()['data']
    assert data['total'] == 3
    assert len(data['items']) == 3
    assert 'T1' in data['items'][0]['transformed']
    assert data['items'][0]['ax'] is not None


def test_history_pagination(client):
    auth, pid = _setup_with_data(client, n=5)
    resp = client.get(f'/patients/{pid}/data?page=1&page_size=2', headers=auth)
    data = resp.get_json()['data']
    assert data['total'] == 5
    assert len(data['items']) == 2


def test_history_other_clinician_forbidden(client):
    auth, pid = _setup_with_data(client, n=1)
    token2 = client.post('/clinician/enable', json={
        'hospital':'H','dept':'D','name':'Dr2','phone':'2','terminal_code':'t2','passcode':'1234'}).get_json()['data']['token']
    resp = client.get(f'/patients/{pid}/data', headers={'Authorization': f'Bearer {token2}'})
    assert resp.get_json()['code'] == 403
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd back && python -m pytest tests/test_history.py -v`
Expected: FAIL —— 404。

- [ ] **Step 3: 在 patient.py 追加历史接口**

在 `back/api/patient.py` 末尾追加：

```python
@patient_bp.route('/patients/<int:patient_id>/data', methods=['GET'])
@token_required()
def patient_history(patient_id):
    p = Patient.query.get(patient_id)
    if not p:
        return jsonify(Response.error(404, "患者不存在")), 404
    if p.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "无权访问该患者")), 403

    q = (db.session.query(DeviceRawData, DeviceTransformedData)
         .outerjoin(DeviceTransformedData,
                    DeviceRawData.id == DeviceTransformedData.raw_data_id)
         .filter(DeviceRawData.patient_id == patient_id))

    start = request.args.get('start')
    end = request.args.get('end')
    if start:
        q = q.filter(DeviceRawData.collected_at >= start)
    if end:
        q = q.filter(DeviceRawData.collected_at <= end)

    total = q.count()
    page = max(int(request.args.get('page', 1)), 1)
    page_size = min(max(int(request.args.get('page_size', 50)), 1), 500)
    rows = (q.order_by(DeviceRawData.collected_at.desc())
            .offset((page - 1) * page_size).limit(page_size).all())

    items = []
    for raw, tr in rows:
        items.append({
            'id': raw.id,
            'collected_at': raw.collected_at.isoformat() if raw.collected_at else None,
            'ax': raw.ax, 'ay': raw.ay, 'az': raw.az,
            'gx': raw.gx, 'gy': raw.gy, 'gz': raw.gz,
            'transformed': ({'T1': tr.T1, 'T2': tr.T2, 'T3': tr.T3, 'T4': tr.T4, 'T5': tr.T5}
                            if tr else None),
        })
    return jsonify(Response.success(
        data={'items': items, 'total': total, 'page': page, 'page_size': page_size}))
```

- [ ] **Step 4: 运行，确认通过**

Run: `cd back && python -m pytest tests/test_history.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
git add back/api/patient.py back/tests/test_history.py
git commit -m "feat: GET /patients/<id>/data 按患者历史（分页 + 时间范围，限本医护）"
```

---

## Phase 7 — 接线、清理、文档

### Task 18: app.py 收尾 + 删除旧文件

**Files:**
- Modify: `back/app.py`
- Delete: `back/api/admin.py`, `back/api/user.py`, `back/api/weekly_schedule.py`, `back/api/device_legacy.py.bak`

- [ ] **Step 1: 重写 app.py**

把 `back/app.py` 整体替换为：

```python
from config import create_app, db

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)
```

> CORS 已在 `create_app` 内启用；蓝图也在 `create_app` 内注册，app.py 不再单独 import 各 api 模块。

- [ ] **Step 2: 删除旧 api 文件**

```bash
git rm back/api/admin.py back/api/user.py back/api/weekly_schedule.py back/api/device_legacy.py.bak
```

- [ ] **Step 3: 确认无残留旧引用**

Run: `cd back && python -m pytest -v`
Expected: 全部 PASS。若报 `ImportError`（旧模块被引用）或 `api/__init__.py` 仍 import 旧模块，修正后重跑。

> 排查点：`back/api/__init__.py`（应为空）；`config.py` 蓝图段是否四个 import 都对应已存在模块；无任何文件再 `from models.models import User`。

- [ ] **Step 4: Commit**

```bash
git add back/app.py back/api/
git commit -m "refactor: app.py 走 create_app；删除 admin/user/weekly_schedule/旧 device 备份"
```

### Task 19: 全量测试 + 启动冒烟 + 文档同步

**Files:**
- Modify: `CLAUDE.md`
- Modify: `系统架构方案.md`

- [ ] **Step 1: 全量测试**

Run: `cd back && python -m pytest -v`
Expected: 全绿（clinician/patients/devices/raw_data/history/auth/models/analysis/smoke）。

- [ ] **Step 2: 真实 MySQL 建表冒烟（可选，需 .env 指向测试库）**

Run: `cd back && python -c "from app import app, db; ctx=app.app_context(); ctx.push(); db.create_all(); print('MySQL create_all OK'); ctx.pop()"`
Expected: 打印 `MySQL create_all OK`（确认模型对 MySQL 也建得起来）。无测试库则跳过，靠 `database_schema_mysql.sql` 人工核对。

- [ ] **Step 3: 更新 CLAUDE.md**

在 `CLAUDE.md` 的「关键代码索引」与「当前优先级」处，将后端相关条目改为新结构：
- 登录/鉴权：`back/api/clinician.py`（enable/login/me，bcrypt + JWT）、`back/utils.py`（`token_required` 基于 `clinician_id`）、`back/auth.py`。
- 患者/历史：`back/api/patient.py`。
- 设备/上传：`back/api/device.py`；SVM：`back/api/analysis.py`。
- 阶段 1「登录加密码」标记为**已完成（App 侧 clinician 口令认证）**；标注「6→38 维落库、批量上传、去标识化导出、SVM 异步化、admin 管理台」仍待后续。

- [ ] **Step 4: 更新 系统架构方案.md**

在阶段 1 / 数据模型小节记录：后端已净重设为 clinicians/devices/patients/patient_pii/device_raw_data/device_transformed_data 六表；口令 bcrypt + JWT(clinician_id)；采集归属 clinician+patient+device；按患者历史只读 API 就绪。延后项同上。

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md 系统架构方案.md
git commit -m "docs: 同步后端重构进展（scope A 采集链路打通）"
```

---

## 验收对照（对应 spec 第 8 节）

| spec 验收项 | 覆盖任务 |
|---|---|
| 1. 空库建表成功 | Task 5（schema）+ Task 19 Step 2 |
| 2. 启用建医护、错口令拒签 | Task 8 + Task 9 |
| 3. 患者 phone 必填/查重/全局 subject_id | Task 11 + Task 12 |
| 4. 蓝牙注册鞋垫归属医护 | Task 14 |
| 5. 上传落库归属 + T1–T5 | Task 16 |
| 6. 按患者历史（范围/分页/限本医护） | Task 17 |
| 7. 无/错 token 拒绝 | Task 7 + 各接口 `@token_required` |
| 8. schema 与模型一致 | Task 4 + Task 5 + Task 19 Step 2 |

---

## 后续计划（独立，不在本计划）

1. **前端接入**（采集端 App）：按 `2026-06-07-frontend-backend-alignment.md` 改 enable/login/患者/上传补 patient_id/蓝牙注册设备/历史/旧接口清理；需真机蓝牙回归，单独写计划。
2. 6→38 维全量落库（先与硬件核对字段顺序）。
3. 批量/会话上传 + 离线重传。
4. 实验室只读 API + 去标识化导出。
5. SVM 推理异步化。
6. admin 管理台与新模型对接。

---

## Self-Review 记录

- **Spec 覆盖**：spec 第 3 节 6 表 → Task 4/5；第 4 节认证 → Task 6/7/8/9；第 5 节 API 全部 → Task 8–17；第 6 节红线（bcrypt/PII 分表/append-only/越权 403）→ Task 6/12/16/13/17；第 8 节验收 → 上表。无遗漏。
- **占位符扫描**：无 TBD/TODO；每个代码步骤含完整代码。
- **类型/命名一致**：`format_subject_id`、`analyze`、`_patient_public(existed=)`、`g.clinician_id`、`_device_public`、`Response.success/error` 在各任务间一致；蓝图名 `clinician_bp/patient_bp/device_bp` 与 config 注册一致。
- **已知环境差异**：SQLite 测试不支持 `nullslast()`（Task 13 已给降级注记）；`my_svm_model.pkl` 缺失时 analysis 用假数据训练占位模型（与旧实现一致）。
