from flask import Blueprint, jsonify, request

from app.services.thumbnails import UPLOAD_DIR, image_size, make_thumbnail

bp = Blueprint("images", __name__)


@bp.post("/images")
def upload_image():
    file = request.files["image"]
    file.save(UPLOAD_DIR / file.filename)
    thumb = make_thumbnail(file.filename)
    return jsonify({"thumbnail": thumb.name, "size": image_size(UPLOAD_DIR / file.filename)})
