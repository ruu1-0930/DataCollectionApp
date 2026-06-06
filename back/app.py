from config import app
from models.models import db
import api.admin
import api.device
import api.user
import api.weekly_schedule
from flask_cors import CORS  

# 启用跨域支持
CORS(app)

if __name__ == '__main__':
    with app.app_context():
        db.create_all() 

    app.run(host='0.0.0.0', port=5000)
