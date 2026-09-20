from flask_sqlalchemy import SQLAlchemy

# Khởi tạo đối tượng SQLAlchemy chung cho toàn ứng dụng
db = SQLAlchemy()

def init_db(app):
    """
    Hàm liên kết SQLAlchemy với ứng dụng Flask và tự động tạo bảng (nếu chưa có).
    Được gọi ở file app.py chính khi khởi chạy app.
    """
    db.init_app(app)
    
    with app.app_context():
        # Lệnh này giúp tạo các bảng theo model nếu bạn dùng cú pháp ORM của Flask,
        # hoặc giữ nguyên để đồng bộ với cơ sở dữ liệu MySQL bạn đã tạo thủ công.
        db.create_all()
        print("[*] Kết nối cơ sở dữ liệu MySQL thành công!")