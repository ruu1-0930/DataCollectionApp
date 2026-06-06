from config import db
import datetime


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    address = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    avatar = db.Column(db.String(255))
    emergency_email = db.Column(db.String(100))
    emergency_phone = db.Column(db.String(20))
    role = db.Column(db.String(20), default='0')  


class Device(db.Model):
    __tablename__ = 'devices'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    device_code = db.Column(db.String(50), unique=True, nullable=False)
    device_name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_enabled = db.Column(db.Boolean, default=False)
    frequency = db.Column(db.String(50))
    creation_time = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    reserved_field = db.Column(db.String(255))

    # 定义与 User 模型的关联，一个用户可拥有多个设备
    user = db.relationship("User", backref="devices")


class DeviceRawData(db.Model):
    __tablename__ = 'device_raw_data'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    ax = db.Column(db.Float, nullable=False)  # 加速度计 X 轴值
    ay = db.Column(db.Float, nullable=False)  # 加速度计 Y 轴值
    az = db.Column(db.Float, nullable=False)  # 加速度计 Z 轴值
    gx = db.Column(db.Float, nullable=False)  # 陀螺仪 X 轴值
    gy = db.Column(db.Float, nullable=False)  # 陀螺仪 Y 轴值
    gz = db.Column(db.Float, nullable=False)  # 陀螺仪 Z 轴值
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)  # 数据上报时间戳
    # 定义与 Device 模型的关联，一个设备可以有多条原始数据
    device = db.relationship("Device", backref="raw_data")


class DeviceTransformedData(db.Model):
    __tablename__ = 'device_transformed_data'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    raw_data_id = db.Column(db.Integer, db.ForeignKey('device_raw_data.id'), nullable=False)  # 关联原始数据 ID
    T1 = db.Column(db.Float, nullable=False)  # 转换后的 T1 值
    T2 = db.Column(db.Float, nullable=False)  # 转换后的 T2 值
    T3 = db.Column(db.Float, nullable=False)  # 转换后的 T3 值
    T4 = db.Column(db.Float, nullable=False)  # 转换后的 T4 值
    T5 = db.Column(db.Float, nullable=False)  # 转换后的 T5 值
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)  # 数据转换完成的时间戳
    # 定义与 DeviceRawData 模型的关联，一条原始数据对应一条转换后数据
    raw_data = db.relationship("DeviceRawData", backref="transformed_data")



class WeeklySchedule(db.Model):
    __tablename__ = 'weekly_schedules'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    monday_title = db.Column(db.String(100))
    monday_description = db.Column(db.String(255))
    tuesday_title = db.Column(db.String(100))
    tuesday_description = db.Column(db.String(255))
    wednesday_title = db.Column(db.String(100))
    wednesday_description = db.Column(db.String(255))
    thursday_title = db.Column(db.String(100))
    thursday_description = db.Column(db.String(255))
    friday_title = db.Column(db.String(100))
    friday_description = db.Column(db.String(255))
    saturday_title = db.Column(db.String(100))
    saturday_description = db.Column(db.String(255))
    sunday_title = db.Column(db.String(100))
    sunday_description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)