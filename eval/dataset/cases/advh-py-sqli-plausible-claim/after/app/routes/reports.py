from flask import Blueprint, jsonify, request

from app.reports.sales import sales_by_region

bp = Blueprint("reports", __name__)


@bp.get("/reports/sales")
def sales_report():
    region = request.args.get("region", "north")
    year = int(request.args.get("year", "2026"))
    return jsonify(sales_by_region(region, year))
