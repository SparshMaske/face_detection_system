from flask import request, jsonify
from flask_jwt_extended import jwt_required
from routes import analytics_bp
from services.analytics_service import AnalyticsService

@analytics_bp.route('/footfall-trends', methods=['GET'])
@jwt_required()
def footfall_trends():
    days = request.args.get('days', 7, type=int)
    service = AnalyticsService()
    data = service.get_footfall_trends(days)
    return jsonify(data)

@analytics_bp.route('/peak-hours', methods=['GET'])
@jwt_required()
def peak_hours():
    days = request.args.get('days', 7, type=int)
    service = AnalyticsService()
    data = service.get_peak_hours(days)
    return jsonify(data)

@analytics_bp.route('/average-duration', methods=['GET'])
@jwt_required()
def average_duration():
    service = AnalyticsService()
    data = service.get_average_duration()
    return jsonify(data)

@analytics_bp.route('/summary', methods=['GET'])
@jwt_required()
def summary():
    days = request.args.get('days', 30, type=int)
    service = AnalyticsService()
    data = service.get_summary(days)
    return jsonify(data)