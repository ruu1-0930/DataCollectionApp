from flask import request, jsonify, g
from config import app, db
from utils import Response,token_required
from utils import Response
from models import User
import jwt
import datetime

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    gender = data.get('gender')
    age = data.get('age')
    address = data.get('address')
    phone = data.get('phone')
    email = data.get('email')
    emergency_email = data.get('emergency_email')
    emergency_phone = data.get('emergency_phone')
    avatar = data.get('avatar')

    # 如果 avatar 为空，使用默认值
    if not avatar:
        avatar = 'uploads/user.jpg'

    if not all([name, gender, age, address, phone, email]):
        return jsonify(Response.error(400, "所有字段均为必填项"))

    # 校验姓名和电话是否重复
    if User.query.filter_by(name=name).first():
        return jsonify(Response.error(400, "姓名已存在"))
    if User.query.filter_by(phone=phone).first():
        return jsonify(Response.error(400, "电话已存在"))

    user = User(
        name=name,
        gender=gender,
        age=age,
        address=address,
        phone=phone,
        email=email,
        emergency_email=emergency_email,
        emergency_phone=emergency_phone,
        avatar=avatar  # 使用传来的头像字段，或默认值
    )

    try:
        db.session.add(user)
        db.session.commit()
        return jsonify(Response.success(msg="注册成功"))
    except Exception as e:
        db.session.rollback()
        return jsonify(Response.error(500, "注册失败: " + str(e)))

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    identifier = data.get('identifier')  # 姓名或电话

    user = User.query.filter((User.name == identifier) | (User.phone == identifier)).first()

    if user:
        # 生成 token，有效期7天
        token = jwt.encode({
            'user_id': user.id,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }, app.config['SECRET_KEY'], algorithm='HS256')

        return jsonify(Response.success(
            data={"name": user.name, "role": user.role,"gender": user.gender,"age":user.age,"address":user.address,"avatar":user.avatar,"email":user.email,"phone":user.phone,"emergency_email":user.emergency_email,"emergency_phone":user.emergency_phone,"token": token},
            msg="登录成功"
        ))
    else:
        return jsonify(Response.error(401, "登录失败，用户名或手机号码不存在"))


@app.route('/user', methods=['PUT'])
@token_required()  # 验证用户的身份，确保是登录用户
def update_user():
    
    user_id = g.user_id
    data = request.json
    name = data.get('name')  # 姓名不可修改
    phone = data.get('phone')  # 电话不可修改
    gender = data.get('gender')
    age = data.get('age')
    address = data.get('address')
    email = data.get('email')
    emergency_email = data.get('emergency_email')
    emergency_phone = data.get('emergency_phone')
    avatar = data.get('avatar')

    user = User.query.get(user_id)

    if not user:
        return jsonify(Response.error(404, "用户未找到")), 404

    # 只允许修改可修改的字段
    if gender:
        user.gender = gender
    if age:
        user.age = age
    if address:
        user.address = address
    if email:
        user.email = email
    if emergency_email:
        user.emergency_email = emergency_email
    if emergency_phone:
        user.emergency_phone = emergency_phone
    if avatar:
        user.avatar = avatar

    try:
        db.session.commit()
        
         # 返回修改后的用户信息
        updated_user = {
            "id": user.id,
            "name": user.name,
            "gender": user.gender,
            "age": user.age,
            "address": user.address,
            "phone": user.phone,
            "email": user.email,
            "emergency_email": user.emergency_email,
            "emergency_phone": user.emergency_phone,
            "avatar": user.avatar
        }
        return jsonify(Response.success(data=updated_user, msg="用户信息更新成功"))
    except Exception as e:
        db.session.rollback()
        return jsonify(Response.error(500, "更新失败: " + str(e)))
