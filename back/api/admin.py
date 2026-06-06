from flask import request, jsonify
from config import app, db
from models import User
from utils import Response,token_required
from functools import wraps 
@app.route('/users', methods=['GET'])
@token_required(role_required=1)  # 仅管理员（1）和超级管理员（2）可访问
def get_all_users():
    users = User.query.filter_by(role='0').all()
    user_list = [{"id": u.id, "name": u.name, "phone": u.phone, "email": u.email,"avatar": u.avatar} for u in users]
    return jsonify(Response.success(data=user_list, msg="获取普通用户列表成功"))

@app.route('/admin', methods=['POST'])
@token_required(role_required=2)  # 仅超级管理员可访问
def create_admin():
    data = request.json
    name = data.get('name')
    gender = data.get('gender')
    age = data.get('age')
    address = data.get('address')
    phone = data.get('phone')
    email = data.get('email')
    emergency_email = data.get('emergency_email')
    emergency_phone = data.get('emergency_phone')

    if not all([name, gender, age, address, phone, email]):
        return jsonify(Response.error(400, "所有字段均为必填项"))

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
        role="1",
    )

    db.session.add(user)
    db.session.commit()
    return jsonify(Response.success(msg="管理员创建成功"))

@app.route('/admins', methods=['GET'])
@token_required(role_required=2)  # 仅超级管理员可访问
def get_admins():
    admins = User.query.filter_by(role='1').all()
    admin_list = [
        {
            "id": a.id,
            "name": a.name,
            "gender": a.gender,
            "age": a.age,
            "address": a.address,
            "phone": a.phone,
            "email": a.email,
            "emergency_email": a.emergency_email,
            "emergency_phone": a.emergency_phone
        }
        for a in admins
    ]
    return jsonify(Response.success(data=admin_list, msg="获取管理员列表成功"))

@app.route('/admin/<int:admin_id>', methods=['DELETE'])
@token_required(role_required=2)  # 仅超级管理员可访问
def delete_admin(admin_id):
    admin = User.query.filter_by(id=admin_id, role='1').first()

    if not admin:
        return jsonify(Response.error(404, "管理员不存在"))

    db.session.delete(admin)
    db.session.commit()
    return jsonify(Response.success(msg="管理员删除成功"))

@app.route('/admin/<int:admin_id>', methods=['PUT'])
@token_required(role_required=2)  # 仅超级管理员可访问
def update_admin(admin_id):
    data = request.json
    admin = User.query.filter_by(id=admin_id, role='1').first()

    if not admin:
        return jsonify(Response.error(404, "管理员不存在"))

    admin.name = data.get('name')
    admin.gender = data.get('gender')
    admin.age = data.get('age')
    admin.address = data.get('address')
    admin.phone = data.get('phone')
    admin.email = data.get('email')
    admin.emergency_email = data.get('emergency_email')
    admin.emergency_phone = data.get('emergency_phone')

    db.session.commit()
    return jsonify(Response.success(msg="管理员信息更新成功"))
