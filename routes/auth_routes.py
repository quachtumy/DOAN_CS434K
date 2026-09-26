from flask import Blueprint, render_template
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
auth_bp = Blueprint('auth', __name__)

# @auth_bp.route('/login')
# def login():
#     return render_template('auth/login.html')

# @auth_bp.route('/register')
# def register():
#     return render_template('auth/register.html')
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form.get('role')
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if password != confirm_password:
            return "Mật khẩu xác nhận không khớp!", 400
        hashed_password = generate_password_hash(password)
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('emailOrPhone')
        password = request.form.get('password')

        # TODO: Kiểm tra đăng nhập với Database...
        # Giả lập đăng nhập thành công:
        session['user_id'] = 1

        # BẮN THÔNG BÁO ĐĂNG NHẬP THÀNH CÔNG
        flash('Đăng nhập thành công! Chào mừng bạn quay trở lại.', 'success')
        
        # Chuyển hướng về trang chủ
        return redirect(url_for('public.home'))

    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()  # Xóa toàn bộ session đăng nhập
    flash('Bạn đã đăng xuất thành công.', 'info')
    return redirect(url_for('public.home'))