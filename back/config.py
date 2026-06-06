import os
from urllib.parse import quote_plus
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv

# 本地/单机部署时从 back/.env 读取；生产用 systemd 注入环境变量时该文件可不存在
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))


def _require(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，请在 back/.env 或部署环境中配置（参考 .env.example）"
        )
    return value


def create_app():
    app = Flask(__name__, static_folder='uploads', static_url_path='/uploads')

    db_user = _require('DB_USER')
    db_pass = _require('DB_PASS')
    db_host = _require('DB_HOST')
    db_port = os.environ.get('DB_PORT', '3306')
    db_name = os.environ.get('DB_NAME', 'lanya')

    # 账号/口令做 URL 编码：口令含 @ : / # 等特殊字符时不会破坏连接串结构
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f'mysql+pymysql://{quote_plus(db_user)}:{quote_plus(db_pass)}@{db_host}:{db_port}/{db_name}'
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = _require('SECRET_KEY')

    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)  
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    app.static_folder = UPLOAD_FOLDER

    CORS(app)

    return app

app = create_app()
db = SQLAlchemy(app)
