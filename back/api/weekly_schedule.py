from flask import request, jsonify, g
from config import app, db
from models import WeeklySchedule
from utils import Response, token_required
import datetime

@app.route('/weekly-schedules', methods=['POST'])
@token_required()
def create_or_replace_weekly_schedule():
    """创建/替换周计划表（每次新增会删除旧数据）"""
    user_id = g.user_id
    data = request.json

    required_fields = [
        'monday_title', 'monday_description',
        'tuesday_title', 'tuesday_description',
        'wednesday_title', 'wednesday_description',
        'thursday_title', 'thursday_description',
        'friday_title', 'friday_description',
        'saturday_title', 'saturday_description',
        'sunday_title', 'sunday_description'
    ]

    if not all(field in data for field in required_fields):
        return jsonify(Response.error(400, "所有字段都是必填项"))

    try:
        # 删除旧数据（无论是否存在）
        WeeklySchedule.query.delete()
        
        # 创建新记录
        schedule = WeeklySchedule(
            **{field: data[field] for field in required_fields},
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        db.session.add(schedule)
        db.session.commit()
        return jsonify(Response.success(data={"id": schedule.id}, msg="周计划已更新"))
    
    except Exception as e:
        db.session.rollback()
        return jsonify(Response.error(500, f"操作失败: {str(e)}"))

@app.route('/weekly-schedules', methods=['GET'])
@token_required()
def get_current_weekly_schedule():
    """获取当前生效的周计划（唯一记录）"""
    user_id = g.user_id
    schedule = WeeklySchedule.query.first()  # 只取第一条（唯一数据）
    
    if not schedule:
        return jsonify(Response.success(data={}, msg="当前无周计划"))
    
    data = {
        "id": schedule.id,
        "days": {
            day: {
                "title": getattr(schedule, f"{day}_title"),
                "description": getattr(schedule, f"{day}_description")
            } for day in ['monday', 'tuesday', 'wednesday', 
                         'thursday', 'friday', 'saturday', 'sunday']
        },
        "created_at": schedule.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        "updated_at": schedule.updated_at.strftime('%Y-%m-%d %H:%M:%S')
    }
    return jsonify(Response.success(data=data, msg="周计划获取成功"))
