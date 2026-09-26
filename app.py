from flask import Flask
from config import config_dict
from database import init_db

# Import các Blueprint đã tạo
from routes.public_routes import public_bp
# from routes.auth_routes import auth_bp
# from routes.customer_routes import customer_bp
from routes.host_routes import host_bp
from routes.admin_routes import admin_bp
from routes.auth_routes import auth_bp


def create_app(config_name='default'):
    """Khởi tạo ứng dụng Flask."""
    app = Flask(__name__)
    
    # 1. Nạp cấu hình từ file config.py
    app.config.from_object(config_dict[config_name])
    
    # 2. Khởi tạo kết nối cơ sở dữ liệu MySQL
    init_db(app)
    
    # 3. Đăng ký các Blueprints (Nhóm module chức năng)
    app.register_blueprint(public_bp) # Xử lý các link như /, /search-rooms, /room-detail
    
    # app.register_blueprint(auth_bp)
    # app.register_blueprint(customer_bp)
    app.register_blueprint(host_bp)   # Xử lý các link bắt đầu bằng /host/ (ví dụ: /host/accommodation-info)
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)
    
    # Route điều hướng trang chủ tạm thời
    @app.route('/')
    def index():
        return """
        <h1>Hệ thống Đặt phòng Khách sạn Đà Nẵng đang hoạt động!</h1>
        <p><a href='/search-rooms' style='color: blue; text-decoration: underline;'>Đến trang Tìm kiếm phòng (đã kết nối DB)</a></p>
        """
    return app

# Khởi chạy ứng dụng
app = create_app('development')

if __name__ == '__main__':
    app.run(debug=True, port=5000)