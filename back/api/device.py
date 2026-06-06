from flask import request, jsonify, g
from config import app, db
from models import Device, DeviceRawData, DeviceTransformedData, User
from utils import Response,token_required
from werkzeug.utils import secure_filename
import os
from functools import wraps
import datetime

from sklearn.svm import SVC
from sklearn.multioutput import MultiOutputClassifier
import pickle
import numpy as np
from datetime import datetime, time, timedelta  


from dateutil import parser  

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """检查文件是否符合要求"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_avatar', methods=['POST'])
def upload_avatar():
    """用户上传头像"""
    if 'file' not in request.files:
        return jsonify(Response.error(400, "未检测到文件")), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify(Response.error(400, "文件名不能为空")), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        file_url = f"/uploads/{filename}" 
        return jsonify(Response.success(data={"avatar_url": file_url}, msg="头像上传成功"))

    return jsonify(Response.error(400, "不支持的文件格式")), 400

# 创建设备接口
@app.route('/devices', methods=['POST'])
@token_required()
def create_device():
    user_id = g.user_id
    data = request.json
    device_code = data.get('device_code')
    device_name = data.get('device_name')
    is_enabled = data.get('is_enabled', False)
    frequency = data.get('frequency')
    reserved_field = data.get('reserved_field')

    if not device_code or not device_name:
        return jsonify(Response.error(400, "设备编码和设备名称为必填项")), 400

    if Device.query.filter_by(device_code=device_code).first():
        return jsonify(Response.error(400, "该设备编码已被绑定，请核对重新添加")), 400

    device = Device(
        device_code=device_code,
        device_name=device_name,
        user_id=user_id,
        is_enabled=is_enabled,
        frequency=frequency,
        reserved_field=reserved_field
    )
    try:
        db.session.add(device)
        db.session.commit()
        return jsonify(Response.success(data={"device_id": device.id}, msg="设备创建成功"))
    except Exception as e:
        db.session.rollback()
        return jsonify(Response.error(500, "设备创建失败: " + str(e)))

# 获取当前用户的所有设备
@app.route('/devices', methods=['GET'])
@token_required()
def list_devices():
    user_id = g.user_id
    devices = Device.query.filter_by(user_id=user_id).all()
    devices_list = []
    for d in devices:
        devices_list.append({
            "id": d.id,
            "device_code": d.device_code,
            "device_name": d.device_name,
            "is_enabled": d.is_enabled,
            "frequency": d.frequency,
            "creation_time": d.creation_time.strftime('%Y-%m-%d %H:%M:%S') if d.creation_time else None,
            "reserved_field": d.reserved_field
        })
    return jsonify(Response.success(data=devices_list, msg="设备列表获取成功"))


# 获取单个设备详情（仅限当前用户拥有的设备）
@app.route('/devices/<int:device_id>', methods=['GET'])
@token_required()
def get_device(device_id):
    user_id = g.user_id
    device = Device.query.filter_by(id=device_id, user_id=user_id).first()
    if not device:
        return jsonify(Response.error(404, "设备未找到")), 404
    device_data = {
        "id": device.id,
        "device_code": device.device_code,
        "device_name": device.device_name,
        "is_enabled": device.is_enabled,
        "frequency": device.frequency,
        "creation_time": device.creation_time.strftime('%Y-%m-%d %H:%M:%S') if device.creation_time else None,
        "reserved_field": device.reserved_field
    }
    return jsonify(Response.success(data=device_data, msg="设备获取成功"))

# 更新设备（仅限当前用户拥有的设备）
@app.route('/devices/<int:device_id>', methods=['PUT'])
@token_required()
def update_device(device_id):
    user_id = g.user_id
    device = Device.query.filter_by(id=device_id, user_id=user_id).first()
    if not device:
        return jsonify(Response.error(404, "设备未找到")), 404

    data = request.json
    new_device_code = data.get('device_code')
    device_name = data.get('device_name')
    is_enabled = data.get('is_enabled')
    frequency = data.get('frequency')
    reserved_field = data.get('reserved_field')

    # 如果更新设备编码，则需检查是否有重复
    if new_device_code and new_device_code != device.device_code:
        if Device.query.filter_by(device_code=new_device_code).first():
            return jsonify(Response.error(400, "该设备编码已被绑定，请核对重新添加")), 400
        device.device_code = new_device_code

    if device_name:
        device.device_name = device_name
    if is_enabled is not None:
        device.is_enabled = is_enabled
    if frequency is not None:
        device.frequency = frequency
    if reserved_field is not None:
        device.reserved_field = reserved_field

    try:
        db.session.commit()
        return jsonify(Response.success(msg="设备更新成功"))
    except Exception as e:
        db.session.rollback()
        return jsonify(Response.error(500, "设备更新失败: " + str(e)))

# 删除设备（仅限当前用户拥有的设备）
@app.route('/devices/<int:device_id>', methods=['DELETE'])
@token_required()
def delete_device(device_id):
    user_id = g.user_id
    device = Device.query.filter_by(id=device_id, user_id=user_id).first()
    if not device:
        return jsonify(Response.error(404, "设备未找到")), 404

    try:
        db.session.delete(device)
        db.session.commit()
        return jsonify(Response.success(msg="设备删除成功"))
    except Exception as e:
        db.session.rollback()
        return jsonify(Response.error(500, "设备删除失败: " + str(e)))

# 查询用户拥有设备
@app.route('/user/devices/<int:user_id>', methods=['GET'])
@token_required(role_required=1)  # 仅管理员（1）和超级管理员（2）可访问
def get_user_devices(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify(Response.error(404, "用户不存在"))

    devices = Device.query.filter_by(user_id=user_id).all()
    device_list = [{"id": d.id, "device_code": d.device_code, "device_name": d.device_name,"is_enabled":d.is_enabled,"frequency":d.frequency,"creation_time":d.creation_time} for d in devices]

    return jsonify(Response.success(data=device_list, msg="获取设备列表成功"))


@app.route('/devices/<string:device_code>/raw_data', methods=['POST'])
@token_required()
def create_raw_data(device_code):
    """为指定设备创建原始数据"""
    user_id = g.user_id
    device = Device.query.filter_by(device_code=device_code, user_id=user_id).first()
    if not device:
        return jsonify(Response.error(404, "Device not found")), 404

    data = request.json
    ax = data.get('ax')
    ay = data.get('ay')
    az = data.get('az')
    gx = data.get('gx')
    gy = data.get('gy')
    gz = data.get('gz')

    if not all([ax, ay, az, gx, gy, gz]):
        return jsonify(Response.error(400, "All fields (ax, ay, az, gx, gy, gz) are required")), 400

    # 创建原始数据记录
    raw_data = DeviceRawData(
        device_id=device.id,  # 使用设备的 ID 存储到数据库
        ax=ax,
        ay=ay,
        az=az,
        gx=gx,
        gy=gy,
        gz=gz,
        timestamp=datetime.now() 
    )
    try:
        db.session.add(raw_data)
        db.session.commit()

        # 调用 DataAnalysis 函数计算 T1-T5
        T1, T2, T3, T4, T5 = DataAnalysisTwo(ax, ay, az, gx, gy, gz)
        # T1, T2, T3, T4, T5 = DataAnalysis(ax, ay, az, gx, gy, gz)

        # 创建转换后数据记录
        transformed_data = DeviceTransformedData(
            raw_data_id=raw_data.id,
            T1=T1,
            T2=T2,
            T3=T3,
            T4=T4,
            T5=T5,
            timestamp=datetime.now()  # 自动获取时间戳
        )
        db.session.add(transformed_data)
        db.session.commit()

        return jsonify(Response.success(data={"raw_data_id": raw_data.id}, msg="数据上传成功！"))
    except Exception as e:
        db.session.rollback()
        return jsonify(Response.error(500, "数据上传失败，数据为：: " + str(e)))


@app.route('/devices/<string:device_code>/raw_data/<int:raw_data_id>', methods=['DELETE'])
@token_required()
def delete_raw_data(device_code, raw_data_id):
    """删除指定设备的原始数据及其关联的转换后数据"""
    user_id = g.user_id
    device = Device.query.filter_by(device_code=device_code, user_id=user_id).first()
    if not device:
        return jsonify(Response.error(404, "设备未找到！")), 404

    raw_data = DeviceRawData.query.filter_by(id=raw_data_id, device_id=device.id).first()
    if not raw_data:
        return jsonify(Response.error(404, "数据未找到！")), 404

    try:
        # 删除与原始数据关联的转换后数据
        transformed_data = DeviceTransformedData.query.filter_by(raw_data_id=raw_data_id).first()
        if transformed_data:
            db.session.delete(transformed_data)

        # 删除原始数据
        db.session.delete(raw_data)
        db.session.commit()
        return jsonify(Response.success(msg="设备原始数据及关联数据删除成功！"))
    except Exception as e:
        db.session.rollback()
        return jsonify(Response.error(500, "删除失败！: " + str(e)))
    

@app.route('/devices/<string:device_code>/data', methods=['GET'])
@token_required()
def get_device_data(device_code):
    """获取指定设备的所有原始数据及对应的转换后数据"""
    user_id = g.user_id
    device = Device.query.filter_by(device_code=device_code, user_id=user_id).first()
    if not device:
        return jsonify(Response.error(404, "设备未找到！")), 404

    raw_data_list = (
        db.session.query(DeviceRawData, DeviceTransformedData)
        .outerjoin(DeviceTransformedData, DeviceRawData.id == DeviceTransformedData.raw_data_id)
        .filter(DeviceRawData.device_id == device.id)
        .all()
    )

    result = []
    for raw_data, transformed_data in raw_data_list:
        data_entry = {
            "ParameterSet1": {  # 原始数据
                "id": raw_data.id,
                "ax": raw_data.ax,
                "ay": raw_data.ay,
                "az": raw_data.az,
                "gx": raw_data.gx,
                "gy": raw_data.gy,
                "gz": raw_data.gz,
                "timestamp": raw_data.timestamp.strftime('%Y-%m-%d %H:%M:%S') if raw_data.timestamp else None
            },
            "ParameterSet2": {  # 转换后数据
                "T1": transformed_data.T1,
                "T2": transformed_data.T2,
                "T3": transformed_data.T3,
                "T4": transformed_data.T4,
                "T5": transformed_data.T5,
                "timestamp": transformed_data.timestamp.strftime('%Y-%m-%d %H:%M:%S') if transformed_data and transformed_data.timestamp else None
            } if transformed_data else None,
            "Timestamp": raw_data.timestamp.strftime('%Y-%m-%d %H:%M:%S') if raw_data.timestamp else None
        }
        result.append(data_entry)

    return jsonify(Response.success(data=result, msg="设备及数据查询成功！"))



@app.route('/devices/latest_t1_t2', methods=['GET'])
@token_required()
def get_latest_t1_t2():
    """
    获取所有设备的最新 T1 和 T2 值
    """
    user_id = g.user_id

    # 查询当前用户的所有设备
    devices = Device.query.filter_by(user_id=user_id).all()
    if not devices:
        return jsonify(Response.error(404, "未找到任何设备")), 404

    result = []

    for device in devices:
        # 查询设备的最新原始数据
        latest_raw_data = (
            DeviceRawData.query
            .filter_by(device_id=device.id)
            .order_by(DeviceRawData.timestamp.desc())
            .first()
        )

        if not latest_raw_data:
            # 如果设备没有原始数据，跳过该设备
            continue

        # 查询与最新原始数据关联的转换后数据
        transformed_data = (
            DeviceTransformedData.query
            .filter_by(raw_data_id=latest_raw_data.id)
            .first()
        )

        if not transformed_data:
            # 如果没有转换后数据，跳过该设备
            continue

        # 构造返回结果
        result.append({
            "device_id": device.id,
            "device_code": device.device_code,
            "device_name": device.device_name,
            "latest_T1": transformed_data.T1,
            "latest_T2": transformed_data.T2,
            "timestamp": latest_raw_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })

    return jsonify(Response.success(data=result, msg="获取所有设备的最新 T1 和 T2 值成功"))



@app.route('/devices/statistics', methods=['GET'])
@token_required()
def get_device_statistics():
    """
    获取所有设备的本周 T2 均值、上周 T2 均值和上一个月 T3 均值
    """
    user_id = g.user_id

    # 获取当前用户的所有设备
    devices = Device.query.filter_by(user_id=user_id).all()
    if not devices:
        return jsonify(Response.error(404, "未找到任何设备")), 404

    # 定义时间范围
    now = datetime.now()
    start_of_week = now - timedelta(days=now.weekday())  # 本周开始时间（周一）
    end_of_last_week = start_of_week - timedelta(days=1)  # 上周结束时间（上周日）
    start_of_last_week = end_of_last_week - timedelta(days=6)  # 上周开始时间（上周一）
    start_of_last_month = (now.replace(day=1) - timedelta(days=1)).replace(day=1)  # 上个月第一天
    end_of_last_month = now.replace(day=1) - timedelta(days=1)  # 上个月最后一天

    result = []

    for device in devices:
        # 查询设备的转换后数据
        transformed_data = (
            DeviceTransformedData.query
            .join(DeviceRawData, DeviceRawData.id == DeviceTransformedData.raw_data_id)
            .filter(DeviceRawData.device_id == device.id)
        )

        # 本周 T2 均值
        this_week_t2 = (
            transformed_data
            .filter(DeviceTransformedData.timestamp >= start_of_week)
            .with_entities(db.func.avg(DeviceTransformedData.T2))
            .scalar()
        )
        this_week_t2 = float(this_week_t2) if this_week_t2 else None

        # 上周 T2 均值
        last_week_t2 = (
            transformed_data
            .filter(DeviceTransformedData.timestamp.between(start_of_last_week, end_of_last_week))
            .with_entities(db.func.avg(DeviceTransformedData.T2))
            .scalar()
        )
        last_week_t2 = float(last_week_t2) if last_week_t2 else None

        # 上个月 T3 均值
        last_month_t3 = (
            transformed_data
            .filter(DeviceTransformedData.timestamp.between(start_of_last_month, end_of_last_month))
            .with_entities(db.func.avg(DeviceTransformedData.T3))
            .scalar()
        )
        last_month_t3 = float(last_month_t3) if last_month_t3 else None

        # 构造返回结果
        result.append({
            "device_code": device.device_code,
            "device_name": device.device_name,
            "this_week_T2_avg": this_week_t2,
            "last_week_T2_avg": last_week_t2,
            "last_month_T3_avg": last_month_t3
        })

    return jsonify(Response.success(data=result, msg="获取设备统计信息成功"))



@app.route('/devices/raw_data/today', methods=['GET'])
@token_required()
def get_today_raw_data():
    """获取当前用户当天所有设备的原始数据及转换数据"""
    user_id = g.user_id

    # 计算当天时间范围（UTC时间）
    today = datetime.now()
    start_of_day = datetime.combine(today, time.min)
    end_of_day = datetime.combine(today, time.max)

    # 查询当前用户设备的当天原始数据
    raw_data_query = DeviceRawData.query.join(Device).filter(
        Device.user_id == user_id,
        DeviceRawData.timestamp.between(start_of_day, end_of_day)
    ).order_by(DeviceRawData.timestamp.desc())

    # 序列化响应数据
    results = []
    for raw_data in raw_data_query:
        # 获取转换数据的第一个元素（如果有）
        transformed_data = raw_data.transformed_data[0] if raw_data.transformed_data else None
        results.append({
            "raw_data": {
                "id": raw_data.id,
                "device_info": {
                    "device_code": raw_data.device.device_code,
                    "device_name": raw_data.device.device_name
                },
                "ax": raw_data.ax,
                "ay": raw_data.ay,
                "az": raw_data.az,
                "gx": raw_data.gx,
                "gy": raw_data.gy,
                "gz": raw_data.gz,
                "timestamp": raw_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            },
            "transformed_data": {
                "T1": transformed_data.T1,
                "T2": transformed_data.T2,
                "T3": transformed_data.T3,
                "T4": transformed_data.T4,
                "T5": transformed_data.T5,
                "timestamp": transformed_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            } if transformed_data else None
        })

    return jsonify(Response.success(data=results, msg="当日数据获取成功"))

@app.route('/devices/raw_data/latest', methods=['GET'])
@token_required()
def get_latest_raw_and_transformed():
    """获取当前用户所有设备中最新一条原始数据及转换数据"""
    user_id = g.user_id
    
    # 查询最新原始数据（带设备信息预加载）
    latest_raw = DeviceRawData.query.join(Device).filter(
        Device.user_id == user_id
    ).order_by(DeviceRawData.timestamp.desc()).first()
    
    if not latest_raw:
        return jsonify(Response.error(404, "未找到任何数据"))
    
    # 获取对应的转换数据（修正部分）
    transformed_data = DeviceTransformedData.query.filter_by(
        raw_data_id=latest_raw.id
    ).order_by(DeviceTransformedData.timestamp.desc()).first()
    
    data = {
        "raw_data": {
            "id": latest_raw.id,
            "device_info": {
                "device_code": latest_raw.device.device_code,
                "device_name": latest_raw.device.device_name
            },
            "ax": latest_raw.ax,
            "ay": latest_raw.ay,
            "az": latest_raw.az,
            "gx": latest_raw.gx,
            "gy": latest_raw.gy,
            "gz": latest_raw.gz,
            "timestamp": latest_raw.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        },
        "transformed_data": {
            "T1": transformed_data.T1,
            "T2": transformed_data.T2,
            "T3": transformed_data.T3,
            "T4": transformed_data.T4,
            "T5": transformed_data.T5,
            "timestamp": transformed_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } if transformed_data else None
    }
    
    return jsonify(Response.success(data=data, msg="最新数据获取成功"))

@app.route('/devices/data/range', methods=['GET'])
@token_required()
def get_data_by_time_range():
    user_id = g.user_id
    # 获取并验证时间参数
    start_time_str = request.args.get('start_time')
    end_time_str = request.args.get('end_time')
    if not all([start_time_str, end_time_str]):
        return jsonify(Response.error(400, "必须提供start_time和end_time参数"))
    
    try:
        start_time = parser.isoparse(start_time_str)  
        end_time = parser.isoparse(end_time_str)     
    except ValueError:
        return jsonify(Response.error(400, "时间格式错误，应为ISO 8601格式（如：2023-10-01T00:00:00）"))
    # 查询当前用户设备在时间范围内的数据
    raw_data_query = DeviceRawData.query.join(Device).filter(
        Device.user_id == user_id,
        DeviceRawData.timestamp.between(start_time, end_time)
    ).order_by(DeviceRawData.timestamp.desc())

    # 序列化响应数据
    results = []
    for raw_data in raw_data_query:
        transformed_data = DeviceTransformedData.query.filter_by(
            raw_data_id=raw_data.id
        ).order_by(
            DeviceTransformedData.timestamp.desc()
        ).first()  
        
        # 构建返回格式
        data_entry = {
            "raw_data": {
                "id": raw_data.id,
                "device_info": {
                    "device_code": raw_data.device.device_code,
                    "device_name": raw_data.device.device_name
                },
                "ax": raw_data.ax,
                "ay": raw_data.ay,
                "az": raw_data.az,
                "gx": raw_data.gx,
                "gy": raw_data.gy,
                "gz": raw_data.gz,
                "timestamp": raw_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            },
            "transformed_data": {
                "T1": transformed_data.T1,
                "T2": transformed_data.T2,
                "T3": transformed_data.T3,
                "T4": transformed_data.T4,
                "T5": transformed_data.T5,
                "timestamp": transformed_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            } if transformed_data else None
        }
        results.append(data_entry)

    return jsonify(Response.success(data=results, msg="时间范围数据获取成功"))


def DataAnalysis(ax, ay, az, gx, gy, gz):
    """
    根据原始数据计算转换后的 T1-T5
    """
    T1 = ax + ay + az 
    T2 = gx + gy + gz 
    T3 = (ax**2 + ay**2 + az**2)**0.5
    T4 = (gx**2 + gy**2 + gz**2)**0.5
    T5 = ax * gx + ay * gy + az * gz
    return T1, T2, T3, T4, T5


# 数据处理函数
def DataAnalysisTwo(ax, ay, az, gx, gy, gz):

    x_input = np.array([[ax, ay, az, gx, gy, gz]], dtype=np.float32)
    
    
    probas = model.predict_proba(x_input)

    T1 = probas[0][0][1]
    T2 = probas[1][0][1]
    T3 = probas[2][0][1]
    T4 = probas[3][0][1]
    T5 = probas[4][0][1]

    return T1, T2, T3, T4, T5


def load_or_train_model(model_path="my_svm_model.pkl"):
    if os.path.exists(model_path):
        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)

            return model
        except Exception as e:
            print("")


    X_fake = np.random.rand(10, 6)
    y_fake = np.random.randint(0, 2, size=(10, 5))

    base_svm = SVC(probability=True)
    model = MultiOutputClassifier(base_svm)


    model.fit(X_fake, y_fake)

    return model


model = load_or_train_model("my_svm_model.pkl")

