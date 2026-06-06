-- 数据库表结构创建脚本 (MySQL版本)
-- 基于 Flask-SQLAlchemy 模型定义生成

-- 创建用户表
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50) NOT NULL,
    gender VARCHAR(10) NOT NULL,
    age INT NOT NULL,
    address VARCHAR(255) NOT NULL,
    phone VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    avatar VARCHAR(255),
    emergency_email VARCHAR(100),
    emergency_phone VARCHAR(20),
    role VARCHAR(20) DEFAULT '0'
);

-- 创建设备表
CREATE TABLE devices (
    id INT PRIMARY KEY AUTO_INCREMENT,
    device_code VARCHAR(50) UNIQUE NOT NULL,
    device_name VARCHAR(100) NOT NULL,
    user_id INT NOT NULL,
    is_enabled BOOLEAN DEFAULT FALSE,
    frequency VARCHAR(50),
    creation_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    reserved_field VARCHAR(255),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 创建设备原始数据表
CREATE TABLE device_raw_data (
    id INT PRIMARY KEY AUTO_INCREMENT,
    device_id INT NOT NULL,
    ax FLOAT NOT NULL,
    ay FLOAT NOT NULL,
    az FLOAT NOT NULL,
    gx FLOAT NOT NULL,
    gy FLOAT NOT NULL,
    gz FLOAT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id)
);

-- 创建设备转换数据表
CREATE TABLE device_transformed_data (
    id INT PRIMARY KEY AUTO_INCREMENT,
    raw_data_id INT NOT NULL,
    T1 FLOAT NOT NULL,
    T2 FLOAT NOT NULL,
    T3 FLOAT NOT NULL,
    T4 FLOAT NOT NULL,
    T5 FLOAT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (raw_data_id) REFERENCES device_raw_data(id)
);

-- 创建周计划表
CREATE TABLE weekly_schedules (
    id INT PRIMARY KEY AUTO_INCREMENT,
    monday_title VARCHAR(100),
    monday_description VARCHAR(255),
    tuesday_title VARCHAR(100),
    tuesday_description VARCHAR(255),
    wednesday_title VARCHAR(100),
    wednesday_description VARCHAR(255),
    thursday_title VARCHAR(100),
    thursday_description VARCHAR(255),
    friday_title VARCHAR(100),
    friday_description VARCHAR(255),
    saturday_title VARCHAR(100),
    saturday_description VARCHAR(255),
    sunday_title VARCHAR(100),
    sunday_description VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 创建索引以提高查询性能
CREATE INDEX idx_devices_user_id ON devices(user_id);
CREATE INDEX idx_device_raw_data_device_id ON device_raw_data(device_id);
CREATE INDEX idx_device_raw_data_timestamp ON device_raw_data(timestamp);
CREATE INDEX idx_device_transformed_data_raw_data_id ON device_transformed_data(raw_data_id);
CREATE INDEX idx_device_transformed_data_timestamp ON device_transformed_data(timestamp);
CREATE INDEX idx_users_phone ON users(phone);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_devices_device_code ON devices(device_code); 