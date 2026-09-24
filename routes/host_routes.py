from flask import Blueprint, render_template, request, flash, redirect, url_for
from sqlalchemy import text
from database import db
from datetime import datetime
import json
import csv
from io import StringIO
from werkzeug.security import generate_password_hash, check_password_hash

host_bp = Blueprint('host', __name__, url_prefix='/host')

@host_bp.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    current_host_id = 101 # Hardcode ID của Host hiện tại

    # 1. Lấy thông tin cơ sở
    acc_query = """
        SELECT a.accommodation_id, a.name, u.full_name, a.status
        FROM Accommodations a
        JOIN Users u ON a.host_id = u.user_id
        WHERE a.host_id = :host_id
    """
    acc = db.session.execute(text(acc_query), {'host_id': current_host_id}).fetchone()
    if not acc:
        return "Bạn chưa có cơ sở lưu trú nào.", 404
    
    acc_id = acc.accommodation_id
    host_initials = "".join([p[0] for p in (acc.full_name or "NV").split()[:2]]).upper()

    # 2. XỬ LÝ POST: THÊM ĐƠN THỦ CÔNG
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_booking':
            room_id = request.form.get('room_id')
            guest_name = request.form.get('guest_name')
            guest_phone = request.form.get('guest_phone')
            check_in = request.form.get('check_in_date')
            check_out = request.form.get('check_out_date')
            total_price = request.form.get('total_price', 0)
            
            # ĐÃ THÊM customer_id VÀO LỆNH INSERT
            insert_query = """
                INSERT INTO Bookings (customer_id, room_id, guest_name, guest_phone, check_in_date, check_out_date, total_price, status)
                VALUES (:customer_id, :room_id, :name, :phone, :check_in, :check_out, :price, 'Confirmed')
            """
            db.session.execute(text(insert_query), {
                'customer_id': current_host_id, # Truyền ID của Host làm ID người đặt
                'room_id': room_id, 
                'name': guest_name, 
                'phone': guest_phone, 
                'check_in': check_in, 
                'check_out': check_out, 
                'price': float(total_price)
            })
            db.session.commit()
            flash('Tạo đơn đặt phòng thành công!', 'success')

    # 3. TÍNH TOÁN KPI THÁNG NÀY
    now = datetime.now()
    start_of_month = now.replace(day=1)
    
    kpi_query = """
        SELECT 
            SUM(b.total_price) as total_revenue,
            COUNT(DISTINCT b.booking_id) as total_bookings
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        WHERE r.accommodation_id = :acc_id 
        AND b.status IN ('Confirmed', 'Completed')
        AND b.created_at >= :start_of_month
    """
    kpi_data = db.session.execute(text(kpi_query), {'acc_id': acc_id, 'start_of_month': start_of_month}).fetchone()
    
    # Tính công suất phòng (Tỷ lệ lấp đầy)
    total_rooms_query = "SELECT COUNT(*) as count FROM Rooms WHERE accommodation_id = :acc_id"
    total_rooms = db.session.execute(text(total_rooms_query), {'acc_id': acc_id}).fetchone().count or 1
    booked_rooms = kpi_data.total_bookings or 0
    occupancy_rate = round((booked_rooms / total_rooms) * 100, 1) if total_rooms > 0 else 0

    # Lấy đánh giá trung bình
    rating_query = "SELECT AVG(rating) as avg_rating, COUNT(review_id) as total_reviews FROM Reviews WHERE accommodation_id = :acc_id"
    rating_data = db.session.execute(text(rating_query), {'acc_id': acc_id}).fetchone()
    avg_rating = round(rating_data.avg_rating or 0, 1)
    total_reviews = rating_data.total_reviews or 0

    stats = {
        'host_name': acc.full_name,
        'acc_name': acc.name,
        'acc_status': acc.status,
        'initials': host_initials,
        'revenue': float(kpi_data.total_revenue or 0),
        'bookings': booked_rooms,
        'occupancy': occupancy_rate,
        'avg_rating': avg_rating,
        'total_reviews': total_reviews
    }

    # 4. TRUY VẤN LẤY DANH SÁCH ĐƠN ĐẶT PHÒNG
    bookings_query = """
        SELECT b.*, r.room_name, r.room_type, r.capacity
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        WHERE r.accommodation_id = :acc_id
        ORDER BY b.created_at DESC
    """
    raw_bookings = db.session.execute(text(bookings_query), {'acc_id': acc_id}).fetchall()

    bookings_list = []
    for b in raw_bookings:
        nights = 1
        if b.check_in_date and b.check_out_date:
            delta = b.check_out_date - b.check_in_date
            nights = delta.days if delta.days > 0 else 1
            
        bookings_list.append({
            'id': b.booking_id,
            'guest_name': b.guest_name or "Khách chưa nhập",
            'guest_phone': b.guest_phone or "N/A",
            'guest_initials': "".join([word[0] for word in (b.guest_name or "K").split()[:2]]).upper(),
            'room_name': b.room_name,
            'room_type': getattr(b, 'room_type', 'Khác'),
            'capacity': getattr(b, 'capacity', 2),
            'check_in': b.check_in_date.strftime("%d/%m/%Y") if getattr(b, 'check_in_date', None) else "",
            'check_out': b.check_out_date.strftime("%d/%m/%Y") if getattr(b, 'check_out_date', None) else "",
            'nights': nights,
            'total_price': float(b.total_price) if getattr(b, 'total_price', None) else 0.0,
            'status': b.status, # Pending, Confirmed, Completed, Cancelled
            'created_at': b.created_at.strftime("%Y%m%d%H%M%S") if getattr(b, 'created_at', None) else "" 
        })

    # 5. Dữ liệu phòng trống (Cho Modal tạo đơn)
    available_rooms = db.session.execute(text("SELECT room_id, room_name, room_type, price_per_night FROM Rooms WHERE accommodation_id = :acc_id"), {'acc_id': acc_id}).fetchall()

    return render_template('host/dashboard.html', stats=stats, bookings=bookings_list, available_rooms=available_rooms)


# ROUTE XỬ LÝ NÚT XUẤT EXCEL TẠI DASHBOARD
@host_bp.route('/dashboard/export')
def export_dashboard_bookings():
    current_host_id = 101
    acc = db.session.execute(text("SELECT accommodation_id FROM Accommodations WHERE host_id = :host_id"), {'host_id': current_host_id}).fetchone()
    
    query = """
        SELECT b.booking_id, b.guest_name, b.guest_phone, r.room_name, b.check_in_date, b.check_out_date, b.total_price, b.status
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        WHERE r.accommodation_id = :acc_id
        ORDER BY b.created_at DESC
    """
    data = db.session.execute(text(query), {'acc_id': acc.accommodation_id}).fetchall()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Mã Đơn', 'Khách Hàng', 'Số Điện Thoại', 'Phòng', 'Ngày Nhận', 'Ngày Trả', 'Tổng Tiền (VND)', 'Trạng Thái'])
    
    for row in data:
        cw.writerow([f"#BK-{row.booking_id}", row.guest_name, row.guest_phone, row.room_name, row.check_in_date, row.check_out_date, float(row.total_price), row.status])

    from flask import Response
    output = Response(si.getvalue().encode('utf-8-sig'), mimetype='text/csv')
    output.headers["Content-Disposition"] = "attachment; filename=Don_Dat_Phong_Gan_Day.csv"
    return output

@host_bp.route('/accommodation-info', methods=['GET', 'POST'])
def accommodation_info():
    current_host_id = 101 # Hardcode tạm thời chờ có Auth

    # Lấy thông tin hiện tại từ DB
    query = "SELECT * FROM Accommodations WHERE host_id = :host_id"
    acc = db.session.execute(text(query), {'host_id': current_host_id}).fetchone()

    if not acc:
        return "Chưa có cơ sở lưu trú nào được liên kết với tài khoản này.", 404

    # 1. XỬ LÝ KHI BẤM NÚT LƯU THAY ĐỔI (POST METHOD)
    if request.method == 'POST':
        # Lấy các trường dữ liệu chung từ Form
        new_name = request.form.get('name')
        new_type = request.form.get('property_type')
        new_address = request.form.get('address')
        new_desc = request.form.get('description')
        
        # Lấy các trường Chính sách
        new_checkin = request.form.get('check_in')
        new_checkout = request.form.get('check_out')
        new_cancel = request.form.get('cancel_policy')
        new_children = request.form.get('children_policy')
        
        # Lấy mảng Tiện ích (Checkbox) -> Ghép thành chuỗi cách nhau bằng dấu phẩy
        selected_amenities = request.form.getlist('amenities')
        amenities_str = ','.join(selected_amenities)
        
        # Lấy mảng URL hình ảnh -> Ghép thành chuỗi cách nhau bằng dấu |
        image_urls = request.form.getlist('images[]')
        images_str = '|'.join([img for img in image_urls if img.strip() != '']) # Lọc bỏ link rỗng
        
        # Câu lệnh Update DB
        update_query = """
            UPDATE Accommodations 
            SET name=:name, property_type=:property_type, address=:address, description=:description,
                check_in_time=:checkin, check_out_time=:checkout, cancel_policy=:cancel, 
                children_policy=:children, amenities=:amenities, images=:images
            WHERE host_id = :host_id
        """
        db.session.execute(text(update_query), {
            'name': new_name, 'property_type': new_type, 'address': new_address, 'description': new_desc,
            'checkin': new_checkin, 'checkout': new_checkout, 'cancel': new_cancel, 
            'children': new_children, 'amenities': amenities_str, 'images': images_str,
            'host_id': current_host_id
        })
        db.session.commit() # Lưu thay đổi vào DB
        
        flash('Đã cập nhật thông tin cơ sở lưu trú thành công!', 'success')
        return redirect(url_for('host.accommodation_info')) # Tải lại trang để thấy DB mới

    # 2. XỬ LÝ HIỂN THỊ DỮ LIỆU LÊN GIAO DIỆN (GET METHOD)
    images_list = acc.images.split('|') if acc.images else []
    amenities_list = [a.strip() for a in acc.amenities.split(',')] if acc.amenities else []
    map_distances = acc.map_distance_info.split('|') if getattr(acc, 'map_distance_info', None) else ['Cách sân bay: --', 'Cách biển: --']

    # Xử lý thời gian cập nhật lần cuối (Định dạng lại ngày giờ)
    updated_time_str = "Vừa xong"
    if getattr(acc, 'updated_at', None):
        updated_time_str = acc.updated_at.strftime("%H:%M - %d/%m/%Y")

    accommodation_data = {
        'id': acc.accommodation_id,
        'name': acc.name,
        'property_type': getattr(acc, 'property_type', 'Khách sạn'),
        'address': acc.address,
        'description': acc.description,
        'status': acc.status,
        'images': images_list,
        'check_in': getattr(acc, 'check_in_time', ''),
        'check_out': getattr(acc, 'check_out_time', ''),
        'cancel_policy': getattr(acc, 'cancel_policy', ''),
        'children_policy': getattr(acc, 'children_policy', ''),
        'dist_airport': map_distances[0].strip() if len(map_distances) > 0 else '',
        'dist_beach': map_distances[1].strip() if len(map_distances) > 1 else '',
        'amenities_list': amenities_list,
        'updated_at': updated_time_str
    }

    # Danh sách chuẩn các tiện ích
    all_amenities = [
        ('Hồ bơi ngoài trời', 'Hồ bơi ngoài trời', 'pool'),
        ('Spa & Xông hơi', 'Spa & Xông hơi', 'spa'),
        ('Nhà hàng & Bar', 'Nhà hàng & Bar', 'restaurant'),
        ('Bãi biển riêng / Ghế tắm nắng', 'Bãi biển riêng / Ghế tắm nắng', 'umbrella'),
        ('Phòng tập Gym', 'Phòng tập Gym', 'fitness_center'),
        ('Bãi đỗ xe miễn phí', 'Bãi đỗ xe miễn phí', 'local_parking')
    ]

    return render_template('host/accommodation_info.html', acc=accommodation_data, all_amenities=all_amenities)

@host_bp.route('/rooms-management', methods=['GET', 'POST'])
def rooms_management():
    current_host_id = 101 # Hardcode ID của Host hiện tại

    # 1. Lấy ID cơ sở lưu trú của Host này
    acc_query = "SELECT accommodation_id FROM Accommodations WHERE host_id = :host_id"
    acc = db.session.execute(text(acc_query), {'host_id': current_host_id}).fetchone()
    if not acc:
        return "Bạn chưa có cơ sở lưu trú nào.", 404
    acc_id = acc.accommodation_id

    # 2. XỬ LÝ FORM THÊM / SỬA / XÓA
    if request.method == 'POST':
        action = request.form.get('action')
        
        # Dữ liệu gốc
        room_name = request.form.get('room_name')
        room_type = request.form.get('room_type')
        price = request.form.get('price', 0)
        status_vi = request.form.get('status')
        images = request.form.get('images', '')
        amenities = request.form.get('amenities', '')

        # DỮ LIỆU MỚI BỔ SUNG ĐỂ ĐỒNG BỘ VỚI ROOM DETAIL
        capacity = request.form.get('capacity', 2)
        room_area = request.form.get('room_area', '30m²')
        bed_type = request.form.get('bed_type', '1 Giường đôi')
        room_view = request.form.get('room_view', 'Hướng thành phố')
        detailed_description = request.form.get('detailed_description', '')
        original_price = float(price) * 1.2 # Giả sử giá gốc luôn cao hơn giá bán 20% (để làm hiệu ứng sale)

        # Chuyển đổi trạng thái
        db_status = 'Available'
        if status_vi == 'Đang ở': db_status = 'Booked'
        elif status_vi == 'Bảo trì': db_status = 'Maintenance'

        if action == 'add':
            insert_query = """
                INSERT INTO Rooms (
                    accommodation_id, room_name, room_type, price_per_night, original_price, 
                    capacity, status, images, amenities, room_area, bed_type, room_view, detailed_description
                )
                VALUES (
                    :acc_id, :name, :type, :price, :original_price, 
                    :capacity, :status, :images, :amenities, :area, :bed, :view, :desc
                )
            """
            db.session.execute(text(insert_query), {
                'acc_id': acc_id, 'name': room_name, 'type': room_type, 'price': float(price), 'original_price': original_price,
                'capacity': int(capacity), 'status': db_status, 'images': images, 'amenities': amenities,
                'area': room_area, 'bed': bed_type, 'view': room_view, 'desc': detailed_description
            })
            flash('Đã thêm phòng mới thành công!', 'success')

        elif action == 'edit':
            room_id = request.form.get('room_id')
            update_query = """
                UPDATE Rooms 
                SET room_name=:name, room_type=:type, price_per_night=:price, original_price=:original_price, 
                    capacity=:capacity, status=:status, images=:images, amenities=:amenities,
                    room_area=:area, bed_type=:bed, room_view=:view, detailed_description=:desc
                WHERE room_id=:rid AND accommodation_id=:acc_id
            """
            db.session.execute(text(update_query), {
                'name': room_name, 'type': room_type, 'price': float(price), 'original_price': original_price,
                'capacity': int(capacity), 'status': db_status, 'images': images, 'amenities': amenities,
                'area': room_area, 'bed': bed_type, 'view': room_view, 'desc': detailed_description,
                'rid': room_id, 'acc_id': acc_id
            })
            flash('Đã cập nhật thông tin phòng!', 'success')

        elif action == 'delete':
            room_id = request.form.get('room_id')
            db.session.execute(text("DELETE FROM Rooms WHERE room_id=:rid AND accommodation_id=:acc_id"), {'rid': room_id, 'acc_id': acc_id})
            flash('Đã xóa phòng khỏi hệ thống!', 'success')

        db.session.commit()
        return redirect(url_for('host.rooms_management'))

    # 3. TRUY VẤN LẤY DANH SÁCH PHÒNG (GET METHOD)
    rooms_query = "SELECT * FROM Rooms WHERE accommodation_id = :acc_id ORDER BY room_id DESC"
    rooms_data = db.session.execute(text(rooms_query), {'acc_id': acc_id}).fetchall()

    # Tính toán thống kê
    stats = {
        'total': len(rooms_data),
        'available': sum(1 for r in rooms_data if r.status == 'Available'),
        'booked': sum(1 for r in rooms_data if r.status == 'Booked'),
        'maintenance': sum(1 for r in rooms_data if r.status == 'Maintenance')
    }

    # Định dạng lại dữ liệu để truyền ra HTML
    rooms_list = []
    for r in rooms_data:
        img = r.images.split('|')[0] if getattr(r, 'images', None) else 'https://images.unsplash.com/photo-1611892440504-42a792e24d32?q=80&w=800'
        ui_status = 'Trống'
        if r.status == 'Booked': ui_status = 'Đang ở'
        elif r.status == 'Maintenance': ui_status = 'Bảo trì'

        rooms_list.append({
            'id': r.room_id,
            'name': r.room_name,
            'type': getattr(r, 'room_type', 'Khác'),
            'price': float(r.price_per_night),
            'status': ui_status,
            'image': img,
            'amenities': r.amenities if getattr(r, 'amenities', None) else 'Tiện nghi tiêu chuẩn',
            
            # Bổ sung dữ liệu mới để truyền vào Modal Edit
            'capacity': getattr(r, 'capacity', 2),
            'area': getattr(r, 'room_area', ''),
            'bed': getattr(r, 'bed_type', ''),
            'view': getattr(r, 'room_view', ''),
            'desc': getattr(r, 'detailed_description', ''),
            'images_full': getattr(r, 'images', '')
        })

    # Lấy danh sách các Loại phòng hiện có để đưa lên thanh Bộ lọc
    unique_types = list(set([r['type'] for r in rooms_list]))

    return render_template('host/rooms_management.html', rooms=rooms_list, stats=stats, unique_types=unique_types)

@host_bp.route('/bookings-management', methods=['GET', 'POST'])
def bookings_management():
    current_host_id = 101 # Hardcode ID của Host hiện tại

    # Lấy accommodation_id của Host
    acc = db.session.execute(text("SELECT accommodation_id FROM Accommodations WHERE host_id = :host_id"), {'host_id': current_host_id}).fetchone()
    if not acc:
        return "Bạn chưa có cơ sở lưu trú nào.", 404
    acc_id = acc.accommodation_id

    # 1. XỬ LÝ POST: THÊM ĐƠN HOẶC CẬP NHẬT TRẠNG THÁI
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_booking':
            room_id = request.form.get('room_id')
            guest_name = request.form.get('guest_name')
            guest_phone = request.form.get('guest_phone')
            check_in = request.form.get('check_in_date')
            check_out = request.form.get('check_out_date')
            total_price = request.form.get('total_price', 0)
            
            # ĐÃ THÊM customer_id VÀO LỆNH INSERT
            insert_query = """
                INSERT INTO Bookings (customer_id, room_id, guest_name, guest_phone, check_in_date, check_out_date, total_price, status)
                VALUES (:customer_id, :room_id, :name, :phone, :check_in, :check_out, :price, 'Confirmed')
            """
            db.session.execute(text(insert_query), {
                'customer_id': current_host_id, # Truyền ID của Host làm ID người đặt
                'room_id': room_id, 
                'name': guest_name, 
                'phone': guest_phone, 
                'check_in': check_in, 
                'check_out': check_out, 
                'price': float(total_price)
            })
            db.session.commit()
            flash('Tạo đơn đặt phòng thành công!', 'success')
            
        elif action == 'update_status':
            # Xử lý Cập nhật trạng thái (Duyệt/Hủy đơn)
            booking_id = request.form.get('booking_id')
            new_status = request.form.get('status') # 'Confirmed' hoặc 'Cancelled'
            
            update_query = "UPDATE Bookings SET status = :status WHERE booking_id = :bid"
            db.session.execute(text(update_query), {'status': new_status, 'bid': booking_id})
            flash(f"Đã cập nhật trạng thái đơn hàng #{booking_id} thành {'Đã xác nhận' if new_status=='Confirmed' else 'Đã hủy'}", 'success')

        db.session.commit()
        return redirect(url_for('host.bookings_management'))

    # 2. TRUY VẤN LẤY DANH SÁCH ĐƠN ĐẶT PHÒNG KÈM THÔNG TIN PHÒNG
    bookings_query = """
        SELECT b.*, r.room_name, r.room_type, r.capacity
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        WHERE r.accommodation_id = :acc_id
        ORDER BY b.created_at DESC
    """
    raw_bookings = db.session.execute(text(bookings_query), {'acc_id': acc_id}).fetchall()

    # Tính toán Thống kê
    stats = {
        'total': len(raw_bookings),
        'pending': sum(1 for b in raw_bookings if b.status == 'Pending'),
        'confirmed': sum(1 for b in raw_bookings if b.status == 'Confirmed'),
        'cancelled': sum(1 for b in raw_bookings if b.status == 'Cancelled')
    }

    # Định dạng dữ liệu truyền ra View
    bookings_list = []
    for b in raw_bookings:
        # Tính số đêm (nếu ngày hợp lệ)
        nights = 1
        if b.check_in_date and b.check_out_date:
            delta = b.check_out_date - b.check_in_date
            nights = delta.days if delta.days > 0 else 1
            
        # Format ngày
        ci_str = b.check_in_date.strftime("%d/%m/%Y") if getattr(b, 'check_in_date', None) else ""
        co_str = b.check_out_date.strftime("%d/%m/%Y") if getattr(b, 'check_out_date', None) else ""

        bookings_list.append({
            'id': b.booking_id,
            'guest_name': b.guest_name or "Khách chưa nhập tên",
            'guest_phone': b.guest_phone or "N/A",
            'guest_initials': "".join([word[0] for word in (b.guest_name or "K").split()[:2]]).upper(),
            'room_name': b.room_name,
            'room_type': getattr(b, 'room_type', 'Khác'),
            'capacity': getattr(b, 'capacity', 2),
            'check_in': ci_str,
            'check_out': co_str,
            'nights': nights,
            'total_price': float(b.total_price) if getattr(b, 'total_price', None) else 0.0,
            'status': b.status, # Pending, Confirmed, Cancelled
            'created_at': b.created_at.strftime("%Y%m%d%H%M%S") if getattr(b, 'created_at', None) else "" # Phục vụ sắp xếp
        })

    # Truy vấn lấy danh sách phòng để làm dropdown cho form "Tạo đơn mới"
    rooms_query = "SELECT room_id, room_name, room_type, price_per_night FROM Rooms WHERE accommodation_id = :acc_id"
    available_rooms = db.session.execute(text(rooms_query), {'acc_id': acc_id}).fetchall()

    return render_template('host/bookings_management.html', 
                           bookings=bookings_list, 
                           stats=stats,
                           available_rooms=available_rooms)

@host_bp.route('/reviews', methods=['GET', 'POST'])
def reviews():
    current_host_id = 101 # Hardcode ID của Host hiện tại

    # Lấy ID của cơ sở lưu trú thuộc Host này
    acc = db.session.execute(text("SELECT accommodation_id, name FROM Accommodations WHERE host_id = :host_id"), {'host_id': current_host_id}).fetchone()
    if not acc:
        return "Bạn chưa có cơ sở lưu trú nào.", 404
    acc_id = acc.accommodation_id
    acc_name = acc.name

    # 1. XỬ LÝ POST: HOST GỬI PHẢN HỒI
    if request.method == 'POST':
        review_id = request.form.get('review_id')
        reply_text = request.form.get('host_reply')

        if review_id and reply_text:
            update_query = """
                UPDATE Reviews 
                SET host_reply = :reply, reply_created_at = CURRENT_TIMESTAMP
                WHERE review_id = :rid AND accommodation_id = :acc_id
            """
            db.session.execute(text(update_query), {'reply': reply_text, 'rid': review_id, 'acc_id': acc_id})
            db.session.commit()
            flash('Đã gửi phản hồi thành công!', 'success')
            
        return redirect(url_for('host.reviews_management'))

    # 2. LẤY DANH SÁCH ĐÁNH GIÁ (KÈM THÔNG TIN KHÁCH & PHÒNG)
    reviews_query = """
        SELECT r.*, u.full_name, rm.room_type
        FROM Reviews r
        JOIN Users u ON r.customer_id = u.user_id
        JOIN Bookings b ON r.booking_id = b.booking_id
        JOIN Rooms rm ON b.room_id = rm.room_id
        WHERE r.accommodation_id = :acc_id
        ORDER BY r.created_at DESC
    """
    raw_reviews = db.session.execute(text(reviews_query), {'acc_id': acc_id}).fetchall()

    # Tính toán số liệu tổng quan
    total_reviews = len(raw_reviews)
    unanswered_count = sum(1 for rv in raw_reviews if rv.host_reply is None or rv.host_reply.strip() == '')
    
    # Tính sao trung bình và số lượng 5 sao, 4 sao
    avg_rating = 0
    five_stars = 0
    four_stars = 0
    
    if total_reviews > 0:
        total_score = sum(rv.rating for rv in raw_reviews)
        avg_rating = round(total_score / total_reviews, 1)
        five_stars = sum(1 for rv in raw_reviews if rv.rating == 5)
        four_stars = sum(1 for rv in raw_reviews if rv.rating == 4)

    # Tính % Tuyệt vời (>=4 sao)
    excellent_pct = 0
    if total_reviews > 0:
        excellent_pct = int(((five_stars + four_stars) / total_reviews) * 100)

    # Chuyển đổi dữ liệu ra List Dict để Jinja2 dễ đọc, đồng thời format lại thời gian
    reviews_list = []
    for rv in raw_reviews:
        # Lấy 2 chữ cái đầu của tên khách để làm Avatar
        name_parts = rv.full_name.split() if rv.full_name else ["K"]
        initials = "".join([p[0] for p in name_parts[:2]]).upper()
        
        # Định dạng thời gian (ví dụ: dd/mm/yyyy)
        created_str = rv.created_at.strftime("%d/%m/%Y") if rv.created_at else ""
        reply_date_str = rv.reply_created_at.strftime("%d/%m/%Y") if getattr(rv, 'reply_created_at', None) else ""

        reviews_list.append({
            'id': rv.review_id,
            'guest_name': rv.full_name or "Khách hàng",
            'guest_initials': initials,
            'room_type': rv.room_type,
            'rating': int(rv.rating),
            'comment': rv.comment,
            'created_at': created_str,
            'created_raw': rv.created_at.strftime("%Y%m%d%H%M%S") if rv.created_at else "", # Để JS sắp xếp
            'host_reply': rv.host_reply,
            'reply_date': reply_date_str
        })

    stats = {
        'total': total_reviews,
        'avg': avg_rating,
        'excellent_pct': excellent_pct,
        'five_stars': five_stars,
        'four_stars': four_stars,
        'unanswered': unanswered_count,
        'acc_name': acc_name
    }

    return render_template('host/reviews.html', reviews=reviews_list, stats=stats)

@host_bp.route('/analytics', methods=['GET'])
def analytics():
    current_host_id = 101 # Hardcode tạm thời chờ Auth

    # 1. Lấy ID và tên cơ sở lưu trú của Host
    acc = db.session.execute(text("SELECT accommodation_id, name FROM Accommodations WHERE host_id = :host_id"), {'host_id': current_host_id}).fetchone()
    if not acc:
        return "Bạn chưa có cơ sở lưu trú nào.", 404
    acc_id = acc.accommodation_id
    acc_name = acc.name

    # 2. Xử lý khoảng thời gian (Mặc định lấy tháng hiện tại)
    filter_type = request.args.get('filter', 'month') # month, quarter, year
    now = datetime.now()
    if filter_type == 'month':
        start_date = now.replace(day=1)
    elif filter_type == 'quarter':
        quarter_start_month = 3 * ((now.month - 1) // 3) + 1
        start_date = datetime(now.year, quarter_start_month, 1)
    else: # year
        start_date = datetime(now.year, 1, 1)

    # 3. TÍNH TOÁN KPI (Chỉ tính các đơn hàng Đã Hoàn Thành 'Completed' hoặc 'Confirmed')
    kpi_query = """
        SELECT 
            SUM(b.total_price) as total_revenue,
            COUNT(DISTINCT b.booking_id) as total_bookings,
            SUM(r.capacity) as total_guests
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        WHERE r.accommodation_id = :acc_id 
        AND b.status IN ('Confirmed', 'Completed')
        AND b.check_in_date >= :start_date
    """
    kpi_data = db.session.execute(text(kpi_query), {'acc_id': acc_id, 'start_date': start_date}).fetchone()
    
    total_rev = kpi_data.total_revenue or 0
    total_guests = kpi_data.total_guests or 0

    # 4. TÍNH CÔNG SUẤT PHÒNG (Occupancy Rate)
    # Tạm tính: Tổng số phòng đã đặt / Tổng số phòng hiện có
    total_rooms_query = "SELECT COUNT(*) as count FROM Rooms WHERE accommodation_id = :acc_id"
    total_rooms = db.session.execute(text(total_rooms_query), {'acc_id': acc_id}).fetchone().count or 1
    booked_rooms = kpi_data.total_bookings or 0
    occupancy_rate = round((booked_rooms / total_rooms) * 100, 1) if total_rooms > 0 else 0

    # 5. ĐÁNH GIÁ TRUNG BÌNH (Từ bảng Reviews)
    rating_query = """
        SELECT AVG(rating) as avg_rating, COUNT(review_id) as total_reviews
        FROM Reviews 
        WHERE accommodation_id = :acc_id
    """
    rating_data = db.session.execute(text(rating_query), {'acc_id': acc_id}).fetchone()
    avg_rating = round(rating_data.avg_rating or 0, 1)
    total_reviews = rating_data.total_reviews or 0

    stats = {
        'revenue': float(total_rev),
        'guests': total_guests,
        'occupancy': occupancy_rate,
        'avg_rating': avg_rating,
        'total_reviews': total_reviews,
        'acc_name': acc_name,
        'filter': filter_type
    }

    # 6. DỮ LIỆU CƠ CẤU DOANH THU THEO LOẠI PHÒNG
    breakdown_query = """
        SELECT r.room_type, SUM(b.total_price) as type_revenue
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        WHERE r.accommodation_id = :acc_id 
        AND b.status IN ('Confirmed', 'Completed')
        AND b.check_in_date >= :start_date
        GROUP BY r.room_type
        ORDER BY type_revenue DESC
    """
    room_breakdown_raw = db.session.execute(text(breakdown_query), {'acc_id': acc_id, 'start_date': start_date}).fetchall()
    
    room_breakdown = []
    colors = ['bg-primary', 'bg-secondary-container', 'bg-primary-container', 'bg-surface-tint']
    
    for i, row in enumerate(room_breakdown_raw):
        type_rev = float(row.type_revenue or 0)
        percentage = round((type_rev / float(total_rev)) * 100) if total_rev > 0 else 0
        color = colors[i % len(colors)]
        room_breakdown.append({
            'type': row.room_type,
            'revenue': type_rev,
            'percentage': percentage,
            'color': color
        })

    # 7. DỮ LIỆU BẢNG BÁO CÁO TỔNG QUAN THEO THÁNG
    monthly_query = """
        SELECT 
            DATE_FORMAT(b.check_in_date, '%Y-%m') as month_period,
            SUM(b.total_price) as monthly_revenue,
            SUM(r.capacity) as monthly_guests,
            COUNT(DISTINCT b.booking_id) as booked_count
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        WHERE r.accommodation_id = :acc_id 
        AND b.status IN ('Confirmed', 'Completed')
        GROUP BY month_period
        ORDER BY month_period DESC
        LIMIT 6
    """
    monthly_raw = db.session.execute(text(monthly_query), {'acc_id': acc_id}).fetchall()
    
    reports = []
    for m in monthly_raw:
        m_rev = float(m.monthly_revenue or 0)
        m_guests = m.monthly_guests or 0
        m_booked = m.booked_count or 0
        m_occ = round((m_booked / total_rooms) * 100, 1)
        
        # Tách chuỗi YYYY-MM
        year, month = m.month_period.split('-')
        
        reports.append({
            'period': f"Tháng {month} / {year}",
            'raw_period': m.month_period, # Để xuất file excel
            'guests': m_guests,
            'occupancy': m_occ,
            'room_revenue': m_rev,
            'total_revenue': m_rev # Tạm bằng doanh thu phòng vì chưa có bảng phụ thu
        })

    return render_template('host/analytics.html', stats=stats, room_breakdown=room_breakdown, reports=reports)

# ROUTE XỬ LÝ XUẤT FILE EXCEL / CSV
@host_bp.route('/export-analytics')
def export_analytics():
    current_host_id = 101
    acc = db.session.execute(text("SELECT accommodation_id FROM Accommodations WHERE host_id = :host_id"), {'host_id': current_host_id}).fetchone()
    if not acc: return "Không tìm thấy dữ liệu", 404

    # Truy vấn lấy lại dữ liệu các tháng
    monthly_query = """
        SELECT DATE_FORMAT(b.check_in_date, '%m/%Y') as month_period,
               SUM(r.capacity) as monthly_guests,
               SUM(b.total_price) as monthly_revenue
        FROM Bookings b
        JOIN Rooms r ON b.room_id = r.room_id
        WHERE r.accommodation_id = :acc_id AND b.status IN ('Confirmed', 'Completed')
        GROUP BY month_period ORDER BY month_period DESC
    """
    data = db.session.execute(text(monthly_query), {'acc_id': acc.accommodation_id}).fetchall()

    # Tạo file CSV
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Kỳ Báo Cáo', 'Tổng Khách', 'Tổng Doanh Thu (VND)'])
    
    for row in data:
        cw.writerow([row.month_period, row.monthly_guests, float(row.monthly_revenue)])

    from flask import Response
    output = Response(si.getvalue().encode('utf-8-sig'), mimetype='text/csv')
    output.headers["Content-Disposition"] = "attachment; filename=Bao_Cao_Doanh_Thu.csv"
    return output

@host_bp.route('/notifications', methods=['GET', 'POST'])
def notifications():
    current_host_id = 101 # Hardcode ID của Host hiện tại

    # XỬ LÝ POST (Đánh dấu đã đọc)
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'mark_read':
            notif_id = request.form.get('notif_id')
            db.session.execute(
                text("UPDATE Notifications SET is_read = 1 WHERE notification_id = :nid AND user_id = :uid"), 
                {'nid': notif_id, 'uid': current_host_id}
            )
        elif action == 'mark_all_read':
            db.session.execute(
                text("UPDATE Notifications SET is_read = 1 WHERE user_id = :uid"), 
                {'uid': current_host_id}
            )
            
        db.session.commit()
        return redirect(url_for('host.notifications'))

    # TRUY VẤN LẤY DANH SÁCH THÔNG BÁO TỪ DB (GET)
    query = """
        SELECT * FROM Notifications 
        WHERE user_id = :uid 
        ORDER BY is_read ASC, created_at DESC
    """
    raw_notifs = db.session.execute(text(query), {'uid': current_host_id}).fetchall()

    # Xử lý tính toán thời gian và format
    notifications_list = []
    now = datetime.now()
    
    stats = {
        'total': len(raw_notifs),
        'unread': 0,
        'booking': 0,
        'review': 0,
        'system': 0
    }

    for n in raw_notifs:
        # Tính khoảng thời gian trôi qua (VD: 10 phút trước, 1 giờ trước)
        time_diff = now - n.created_at
        if time_diff.days > 0:
            time_ago = f"{time_diff.days} ngày trước"
        elif time_diff.seconds >= 3600:
            time_ago = f"{time_diff.seconds // 3600} giờ trước"
        elif time_diff.seconds >= 60:
            time_ago = f"{time_diff.seconds // 60} phút trước"
        else:
            time_ago = "Vừa xong"

        # Đếm thống kê
        category = getattr(n, 'category', 'system')
        if not n.is_read:
            stats['unread'] += 1
        stats[category] = stats.get(category, 0) + 1

        notifications_list.append({
            'id': n.notification_id,
            'title': n.title,
            'message': n.message,
            'is_read': bool(n.is_read),
            'category': category, # 'booking', 'review', 'system'
            'time_ago': time_ago
        })

    return render_template('host/notifications.html', notifs=notifications_list, stats=stats)

@host_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    current_host_id = 101 # Hardcode ID của Host

    # XỬ LÝ POST (KHI NHẤN NÚT LƯU THAY ĐỔI / ĐỔI MẬT KHẨU)
    if request.method == 'POST':
        action = request.form.get('action')
        
        # 1. Nếu là Lưu thông tin cá nhân
        if action == 'update_profile':
            new_name = request.form.get('full_name')
            new_email = request.form.get('email')
            new_phone = request.form.get('phone')
            new_address = request.form.get('address')
            
            # Cập nhật bảng Users
            db.session.execute(
                text("UPDATE Users SET full_name=:name, email=:email, phone=:phone WHERE user_id=:uid"),
                {'name': new_name, 'email': new_email, 'phone': new_phone, 'uid': current_host_id}
            )
            # Cập nhật địa chỉ ở bảng Accommodations
            db.session.execute(
                text("UPDATE Accommodations SET address=:address WHERE host_id=:uid"),
                {'address': new_address, 'uid': current_host_id}
            )
            db.session.commit()
            flash('Cập nhật thông tin cá nhân thành công!', 'success')
            
        # 2. Nếu là Đổi mật khẩu
        elif action == 'change_password':
            old_pass = request.form.get('old_password')
            new_pass = request.form.get('new_password')
            confirm_pass = request.form.get('confirm_password')
            
            # Lấy mật khẩu cũ từ DB để kiểm tra
            user = db.session.execute(text("SELECT password_hash FROM Users WHERE user_id=:uid"), {'uid': current_host_id}).fetchone()
            
            if not user or not check_password_hash(user.password_hash, old_pass):
                flash('Mật khẩu hiện tại không đúng!', 'error')
            elif new_pass != confirm_pass:
                flash('Xác nhận mật khẩu mới không khớp!', 'error')
            else:
                # Mã hóa pass mới và lưu
                new_hash = generate_password_hash(new_pass)
                db.session.execute(
                    text("UPDATE Users SET password_hash=:hash WHERE user_id=:uid"),
                    {'hash': new_hash, 'uid': current_host_id}
                )
                db.session.commit()
                flash('Đổi mật khẩu thành công!', 'success')
                
        return redirect(url_for('host.profile'))

    # TRUY VẤN LẤY DỮ LIỆU HIỂN THỊ (GET)
    query = """
        SELECT u.full_name, u.email, u.phone, u.updated_at, a.address, a.status as acc_status
        FROM Users u
        LEFT JOIN Accommodations a ON u.user_id = a.host_id
        WHERE u.user_id = :uid
    """
    user_data = db.session.execute(text(query), {'uid': current_host_id}).fetchone()
    
    # Xử lý avatar chữ cái và thời gian cập nhật
    initials = "".join([p[0] for p in user_data.full_name.split()[:2]]).upper() if user_data and user_data.full_name else "NV"
    
    updated_str = "Hôm nay"
    if user_data and user_data.updated_at:
        diff = datetime.now() - user_data.updated_at
        if diff.days == 0:
            updated_str = "Hôm nay"
        elif diff.days == 1:
            updated_str = "Hôm qua"
        else:
            updated_str = user_data.updated_at.strftime("%d/%m/%Y")

    profile_info = {
        'name': user_data.full_name if user_data else "",
        'email': user_data.email if user_data else "",
        'phone': user_data.phone if user_data else "",
        'address': user_data.address if user_data else "",
        'initials': initials,
        'updated_at': updated_str,
        'acc_status': user_data.acc_status if user_data else "Pending"
    }

    return render_template('host/profile.html', profile=profile_info)
