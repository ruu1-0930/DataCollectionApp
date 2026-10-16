import os
import time
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
    app.config.setdefault('LOGIN_FAILURE_LIMIT', 5)
    app.config.setdefault('LOGIN_FAILURE_WINDOW_SECONDS', 300)
    app.config.setdefault('LOGIN_RATE_LIMIT_CLOCK', time.monotonic)
    # 仅进程内限流；多 worker 部署仍须由网关或共享存储统一限流。
    app.extensions['login_failure_windows'] = {}

    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.static_folder = UPLOAD_FOLDER

    db.init_app(app)
    CORS(app)

    # 蓝图在 create_app 内注册，避免循环 import
    from api.clinician import clinician_bp
    app.register_blueprint(clinician_bp)

    from api.patient import patient_bp
    app.register_blueprint(patient_bp)

    from api.device import device_bp
    app.register_blueprint(device_bp)


    from api.gait import gait_bp
    app.register_blueprint(gait_bp)

    from api.snapshot import snapshot_bp
    app.register_blueprint(snapshot_bp)

    from api.account import account_bp
    app.register_blueprint(account_bp)
    from api.admin_business import admin_business_bp
    app.register_blueprint(admin_business_bp)
    from api.workbench import workbench_bp
    app.register_blueprint(workbench_bp)
    from account_cli import register_account_cli
    register_account_cli(app)

    return app

