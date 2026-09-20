from flask import Blueprint, render_template, request
from database import db
from sqlalchemy import text

public_bp = Blueprint('public', __name__)

# Trang chủ - Quách Tú Mỹ
@public_bp.route('/')
def home():
    # 1. LẤY 4 ĐỊA ĐIỂM DU LỊCH BIỂU TƯỢNG (Giữ nguyên)
    destinations_query = """
        SELECT * FROM TouristDestinations 
        ORDER BY rating DESC, reviews_count DESC 
        LIMIT 4
    """
    dest_result = db.session.execute(text(destinations_query)).fetchall()
    
    top_destinations = []
    for d in dest_result:
        top_destinations.append({
            'id': d.destination_id,
            'name': d.name,
            'category': d.category,
            'main_image': d.main_image if d.main_image else 'https://images.unsplash.com/photo-1555854877-bab0e564b8d5',
            'description': getattr(d, 'description', f'Khám phá vẻ đẹp của {d.name} tại Đà Nẵng.')
        })

    # 2. LẤY 3 KHÁCH SẠN NỔI BẬT VÀ TÌM 1 PHÒNG ĐẠI DIỆN ĐỂ LẤY ROOM_ID VÀ GIÁ
    acc_query = """
        SELECT a.*, 
               (SELECT room_id FROM Rooms WHERE accommodation_id = a.accommodation_id LIMIT 1) AS representative_room_id,
               (SELECT MIN(price_per_night) FROM Rooms WHERE accommodation_id = a.accommodation_id) AS min_price
        FROM Accommodations a
        WHERE a.status = 'Approved' 
        LIMIT 3
    """
    acc_result = db.session.execute(text(acc_query)).fetchall()
    
    top_accommodations = []
    for a in acc_result:
        first_image = a.images.split('|')[0] if getattr(a, 'images', None) else 'https://images.unsplash.com/photo-1566665797739-1674de7a421a'
        
        top_accommodations.append({
            'id': a.accommodation_id,
            'name': a.name,
            'area': a.address.split(',')[0] if a.address else 'Đà Nẵng',
            'description': getattr(a, 'description', 'Khách sạn cao cấp tại Đà Nẵng.'),
            'image': first_image,
            # Lấy room_id để truyền sang trang chi tiết phòng
            'room_id': getattr(a, 'representative_room_id', None),
            # Lấy giá thấp nhất để hiển thị
            'min_price': float(getattr(a, 'min_price', 0)) if getattr(a, 'min_price', None) else 0
        })

    return render_template(
        'public/home.html', 
        top_destinations=top_destinations,
        top_accommodations=top_accommodations
    )

# Tìm kiếm địa điểm du lịch - Quách Tú Mỹ
@public_bp.route('/search-destinations', methods=['GET'])
def search_destinations():
    # 1. Nhận tham số
    keyword = request.args.get('keyword', '').strip()
    area = request.args.get('area', 'all')
    category = request.args.get('category', '')
    
    # 2. Câu truy vấn gốc
    query = "SELECT * FROM TouristDestinations WHERE 1=1"
    params = {}

    # 3. Lọc từ khóa (Đã bỏ description ra khỏi điều kiện tìm kiếm)
    if keyword:
        query += " AND (name LIKE :keyword OR address LIKE :keyword)"
        params['keyword'] = f"%{keyword}%"

    # 4. Lọc Khu vực
    if area and area != 'all':
        query += " AND area = :area"
        params['area'] = area

    # 5. Lọc Danh mục 
    if category:
        query += " AND category LIKE :category"
        params['category'] = f"%{category}%"

    # Thực thi truy vấn
    result = db.session.execute(text(query), params).fetchall()

    # Ánh xạ dữ liệu đúng theo các cột trong bảng TouristDestinations MỚI
    destination_list = []
    for row in result:
        destination_list.append({
            'id': row.destination_id,
            'name': row.name,
            'category': row.category,
            'address': getattr(row, 'address', ''),
            'rating': getattr(row, 'rating', 4.5), 
            'reviews_count': getattr(row, 'reviews_count', 0),
            'image_url': getattr(row, 'main_image', '') # Bảng mới dùng main_image
        })

    return render_template('public/search_destinations.html', destinations=destination_list)

# Chi tiết địa điểm du lịch - Quách Tú Mỹ
@public_bp.route('/destination-detail')
def destination_detail():
    dest_id = request.args.get('id')
    if not dest_id:
        dest_id = 1 

    # 1. LẤY THÔNG TIN ĐỊA ĐIỂM (Bảng TouristDestinations + DestinationDetails)
    query = """
        SELECT t.*, d.* 
        FROM TouristDestinations t
        LEFT JOIN DestinationDetails d ON t.destination_id = d.destination_id
        WHERE t.destination_id = :dest_id
    """
    row = db.session.execute(text(query), {'dest_id': dest_id}).fetchone()

    if not row:
        return "Không tìm thấy địa điểm", 404

    # Xử lý chuỗi lưu ý và hình ảnh
    raw_notices = getattr(row, 'notices', '')
    notices_list = raw_notices.split('|') if raw_notices else []
    
    raw_gallery = getattr(row, 'gallery_images', '')
    gallery_list = raw_gallery.split('|') if raw_gallery else []

    dest = {
        'id': row.destination_id,
        'name': row.name,
        'area': row.area,
        'address': getattr(row, 'address', ''),
        'rating': getattr(row, 'rating', 5.0),
        'reviews_count': getattr(row, 'reviews_count', 0),
        'main_image': getattr(row, 'main_image', ''),
        'opening_hours': getattr(row, 'opening_hours', ''),
        'overview_text': getattr(row, 'overview_text', ''),
        'best_time': getattr(row, 'best_time', ''),
        'transportation': getattr(row, 'transportation', ''),
        'top_experiences': getattr(row, 'top_experiences', ''),
        'notices': notices_list,
        'gallery': gallery_list,
        'ticket_adult': getattr(row, 'ticket_adult', 0),
        'ticket_child': getattr(row, 'ticket_child', 0),
        'map_embed_url': getattr(row, 'map_embed_url', '')
    }

    # 2. LẤY DANH SÁCH 3 PHÒNG LƯU TRÚ (Sử dụng JOIN giữa bảng Rooms và Accommodations)
    nearby_rooms = []
    try:
        # Giả định bảng Accommodations của bạn có cột 'name' và 'address'
        rooms_query = """
            SELECT r.room_id, r.room_name, r.price_per_night, r.images, 
                   a.name AS accommodation_name, 
                   a.address AS accommodation_address
            FROM Rooms r
            JOIN Accommodations a ON r.accommodation_id = a.accommodation_id
            WHERE r.status = 'Available'
            ORDER BY RAND() 
            LIMIT 3
        """
        rooms_result = db.session.execute(text(rooms_query)).fetchall()
        
        for r in rooms_result:
            # Lấy ảnh đầu tiên nếu cột images lưu nhiều ảnh cách nhau bằng dấu phẩy
            first_image = r.images.split(',')[0] if r.images else 'https://via.placeholder.com/400x300'
            
            nearby_rooms.append({
                'room_id': r.room_id,
                'accommodation_name': r.accommodation_name,
                'accommodation_address': getattr(r, 'accommodation_address', 'Đà Nẵng'),
                'room_name': r.room_name,
                'price_per_night': float(r.price_per_night),
                'images': first_image,
                'rating': 4.8  # Fake rating vì bảng chưa có
            })
    except Exception as e:
        print("Lỗi khi tải phòng đề xuất:", e)
        # Nếu có lỗi (ví dụ sai tên cột của bảng Accommodations), nó sẽ bỏ qua và hiển thị danh sách rỗng

    # 3. TRUYỀN DỮ LIỆU SANG GIAO DIỆN
    return render_template('public/destination_detail.html', dest=dest, nearby_rooms=nearby_rooms)

# Tìm kiếm phòng - Quách Tú Mỹ
@public_bp.route('/search-rooms', methods=['GET'])
def search_rooms():
    # 1. Lấy tham số từ form tìm kiếm trên giao diện
    keyword = request.args.get('keyword', '').strip()       
    price_range = request.args.get('price_range', '').strip() 
    
    # Bắt tham số Khách từ thẻ <input type="hidden"> (Mặc định 2 người lớn, 0 trẻ em)
    try:
        adults = int(request.args.get('adults', 2))
        children = int(request.args.get('children', 0))
    except ValueError:
        adults = 2
        children = 0
        
    total_guests = adults + children # Tổng số người
    
    # 2. Xây dựng câu truy vấn cơ bản
    query = """
        SELECT r.*, a.name AS accommodation_name, a.address AS accommodation_address, a.images AS accommodation_images
        FROM Rooms r
        JOIN Accommodations a ON r.accommodation_id = a.accommodation_id
        WHERE r.status = 'Available'
    """
    params = {}

    # Lọc theo Khu vực hoặc Tên cơ sở lưu trú
    if keyword:
        query += " AND (a.address LIKE :keyword OR a.name LIKE :keyword)"
        params['keyword'] = f"%{keyword}%"
        
    # Lọc theo Sức chứa (Chỉ hiện phòng chứa đủ tổng số người)
    query += " AND r.capacity >= :total_guests"
    params['total_guests'] = total_guests

    # Lọc theo Khoảng giá 
    if price_range and '-' in price_range:
        try:
            parts = price_range.replace('VNĐ', '').replace('.', '').replace('đ', '').replace(',', '').split('-')
            min_p = float(parts[0].strip())
            max_p = float(parts[1].strip())
            query += " AND r.price_per_night BETWEEN :min_p AND :max_p"
            params['min_p'] = min_p
            params['max_p'] = max_p
        except (ValueError, IndexError):
            pass # Bỏ qua nếu chuỗi bị lỗi định dạng

    query += " ORDER BY r.price_per_night ASC"

    # Thực thi truy vấn
    result = db.session.execute(text(query), params).fetchall()

    rooms_list = []
    for row in result:
        # Xử lý chuỗi ảnh (Phòng trường hợp DB lưu nhiều ảnh kiểu URL1|URL2 hoặc URL1,URL2)
        raw_images = getattr(row, 'images', '')
        if '|' in raw_images:
            first_image = raw_images.split('|')[0]
        elif ',' in raw_images:
            first_image = raw_images.split(',')[0]
        else:
            first_image = raw_images

        # Nếu không có ảnh nào, trả về ảnh mặc định xịn xò để không bị lỗi thẻ <img src="">
        if not first_image or first_image.strip() == '':
            first_image = 'https://images.unsplash.com/photo-1566665797739-1674de7a421a?q=80&w=800'

        rooms_list.append({
            'room_id': row.room_id,
            'room_name': row.room_name,
            'room_type': row.room_type,
            'price_per_night': row.price_per_night,
            'capacity': row.capacity,
            'amenities': row.amenities.split(',') if row.amenities else [],
            'accommodation_name': row.accommodation_name,
            'accommodation_address': row.accommodation_address,
            'images': first_image # Truyền thẳng 1 link ảnh duy nhất ra ngoài HTML
        })

    return render_template(
        'public/search_rooms.html',
        rooms=rooms_list,
        total_rooms=len(rooms_list),
        keyword=keyword,
        price_range=price_range
    )

# Chi tiết phòng - Quách Tú Mỹ
@public_bp.route('/room-detail')
def room_detail():
    room_id = request.args.get('id')
    if not room_id:
        room_id = 1 # Mặc định lấy phòng id=1 nếu không truyền tham số

    query = """
        SELECT r.*, a.name AS accommodation_name, a.address AS accommodation_address, rd.*
        FROM Rooms r
        JOIN Accommodations a ON r.accommodation_id = a.accommodation_id
        LEFT JOIN RoomDetails rd ON r.room_id = rd.room_id
        WHERE r.room_id = :room_id
    """
    row = db.session.execute(text(query), {'room_id': room_id}).fetchone()

    if not row:
        return "Không tìm thấy phòng", 404

    # Xử lý cắt chuỗi ảnh gallery và tiện ích
    gallery_list = row.gallery_images.split('|') if getattr(row, 'gallery_images', None) else []
    amenities_list = row.amenities.split(',') if row.amenities else []

    # XỬ LÝ LỖI DECIMAL VÀ FLOAT Ở ĐÂY
    base_price = float(row.price_per_night)
    # Lấy original_price từ DB, nếu không có thì lấy giá hiện tại nhân 1.3
    db_original_price = getattr(row, 'original_price', None)
    final_original_price = float(db_original_price) if db_original_price else (base_price * 1.3)

    room_data = {
        'room_id': row.room_id,
        'accommodation_name': row.accommodation_name,
        'accommodation_address': row.accommodation_address,
        'room_name': row.room_name,
        'room_type': row.room_type,
        'price_per_night': base_price,
        'capacity': row.capacity,
        'amenities': amenities_list,
        'main_image': row.images,
        
        # Dữ liệu từ bảng RoomDetails
        'room_code': getattr(row, 'room_code', f'ROOM-{row.room_id}'),
        'room_area': getattr(row, 'room_area', 'Đang cập nhật...'),
        'bed_type': getattr(row, 'bed_type', 'Đang cập nhật...'),
        'room_view': getattr(row, 'room_view', 'Đang cập nhật...'),
        'detailed_description': getattr(row, 'detailed_description', 'Chưa có mô tả chi tiết.'),
        'gallery': gallery_list,
        'original_price': final_original_price,
        'rating_score': getattr(row, 'rating_score', 9.0),
        'review_count': getattr(row, 'review_count', 0)
    }

    return render_template('public/room_detail.html', room=room_data)