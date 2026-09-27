from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from sqlalchemy import text
from database import db
from werkzeug.security import generate_password_hash, check_password_hash

# Tạo Blueprint cho luồng xác thực (nếu bạn chưa có)
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # 1. Lấy dữ liệu từ Form gửi lên dựa vào thẻ 'name'
        role_input = request.form.get('role') # 'guest' hoặc 'host'
        full_name = request.form.get('fullname')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        terms = request.form.get('terms')

        # 2. Validate dữ liệu cơ bản
        if not terms:
            flash('Bạn phải đồng ý với Điều khoản dịch vụ và Chính sách bảo mật.', 'error')
            return redirect(url_for('auth.register'))
        
        if password != confirm_password:
            flash('Mật khẩu xác nhận không khớp.', 'error')
            return redirect(url_for('auth.register'))

        # 3. Kiểm tra Email đã tồn tại trong hệ thống chưa
        check_query = "SELECT user_id FROM Users WHERE email = :email"
        existing_user = db.session.execute(text(check_query), {'email': email}).fetchone()
        
        if existing_user:
            flash('Email này đã được sử dụng. Vui lòng sử dụng email khác!', 'error')
            return redirect(url_for('auth.register'))

        # 4. Xác định Role và Status theo đặc tả Use Case của bạn
        db_role = 'Customer' if role_input == 'guest' else 'Host'
        # Theo Use Case: Host thì Pending chờ duyệt, Customer thì Active luôn
        db_status = 'Active' if db_role == 'Customer' else 'Pending'

        # 5. Mã hóa mật khẩu
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # 6. Lưu vào CSDL
        try:
            insert_query = """
                INSERT INTO Users (full_name, email, password_hash, phone, role, status)
                VALUES (:name, :email, :pass, :phone, :role, :status)
            """
            db.session.execute(text(insert_query), {
                'name': full_name,
                'email': email,
                'pass': hashed_password,
                'phone': phone,
                'role': db_role,
                'status': db_status
            })
            db.session.commit()
            
            # Thông báo thành công và chuyển hướng đến trang đăng nhập
            if db_role == 'Host':
                flash('Đăng ký tài khoản Chủ cơ sở thành công! Tài khoản đang chờ Admin phê duyệt.', 'success')
            else:
                flash('Đăng ký tài khoản thành công! Bạn có thể đăng nhập ngay.', 'success')
                
            # Thay 'auth.login' bằng route trang đăng nhập thực tế của bạn
            return redirect(url_for('auth.login')) 
            
        except Exception as e:
            db.session.rollback()
            flash('Đã xảy ra lỗi hệ thống khi đăng ký. Vui lòng thử lại!', 'error')
            print(f"Lỗi đăng ký: {e}")
            return redirect(url_for('auth.register'))

    # Hiển thị giao diện khi là phương thức GET
    return render_template('auth/register.html')

from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from sqlalchemy import text
from database import db
from werkzeug.security import check_password_hash

# Giả sử bạn đã khai báo auth_bp
# auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 1. Lấy dữ liệu từ form
        email_or_phone = request.form.get('emailOrPhone')
        password = request.form.get('password')

        # 2. Truy vấn tìm người dùng bằng Email HOẶC Số điện thoại
        query = "SELECT * FROM Users WHERE email = :val OR phone = :val"
        user = db.session.execute(text(query), {'val': email_or_phone}).fetchone()

        # 3. Kiểm tra tài khoản và mật khẩu
        if not user or not check_password_hash(user.password_hash, password):
            flash('Tài khoản hoặc mật khẩu không chính xác!')
            return redirect(url_for('auth.login'))

        # 4. Kiểm tra trạng thái tài khoản
        if user.status == 'Pending':
            flash('Tài khoản của bạn đang chờ Admin phê duyệt. Vui lòng quay lại sau.')
            return redirect(url_for('auth.login'))
        elif user.status in ['Suspended', 'Locked']:
            flash('Tài khoản của bạn đã bị khóa. Vui lòng liên hệ bộ phận hỗ trợ.')
            return redirect(url_for('auth.login'))

        # 5. Đăng nhập thành công -> Lưu thông tin vào session
        session['user_id'] = user.user_id
        session['role'] = user.role
        session['full_name'] = user.full_name

        # 6. PHÂN QUYỀN CHUYỂN HƯỚNG THEO Ý BẠN
        if user.role == 'Customer':
            # Chuyển qua trang của khách hàng (Mặc định là Trang chủ)
            return redirect(url_for('customer.home')) 
        elif user.role == 'Host':
            # Chuyển qua trang quản lý của chủ cơ sở
            return redirect(url_for('host.dashboard'))
        elif user.role == 'Admin':
            return redirect(url_for('admin.dashboard'))

    # Nếu là phương thức GET, hiển thị trang đăng nhập
    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))