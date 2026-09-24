from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
import re
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database import db


admin_bp = Blueprint('admin', __name__)

MAIN_FIELDS = (
    'name', 'category', 'area', 'address', 'rating', 'reviews_count',
    'main_image', 'opening_hours',
)
DETAIL_TEXT_FIELDS = (
    'overview_text', 'best_time', 'transportation', 'top_experiences',
    'notices', 'gallery_images', 'map_embed_url',
)
DETAIL_PRICE_FIELDS = ('ticket_adult', 'ticket_child')
FORM_FIELDS = MAIN_FIELDS + DETAIL_TEXT_FIELDS + DETAIL_PRICE_FIELDS
FIELD_LIMITS = {
    'name': 255,
    'category': 100,
    'area': 100,
    'opening_hours': 100,
    'best_time': 255,
    'transportation': 255,
}
FIELD_LABELS = {
    'name': 'Tên địa điểm',
    'category': 'Danh mục',
    'area': 'Khu vực',
    'opening_hours': 'Giờ mở cửa',
    'best_time': 'Thời điểm phù hợp',
    'transportation': 'Phương tiện di chuyển',
}


def _list_destinations(keyword):
    query = """
        SELECT destination_id, name, category, area, address, main_image, opening_hours
        FROM TouristDestinations
    """
    params = {}
    if keyword:
        query += " WHERE name LIKE :keyword"
        params['keyword'] = f'%{keyword}%'
    query += " ORDER BY destination_id DESC"
    return db.session.execute(text(query), params).mappings().all()


def _load_destination(destination_id):
    destination = db.session.execute(
        text("""
            SELECT destination_id, name, category, area, address, rating,
                   reviews_count, main_image, opening_hours
            FROM TouristDestinations
            WHERE destination_id = :destination_id
        """),
        {'destination_id': destination_id},
    ).mappings().first()
    if destination is None:
        abort(404)

    detail = db.session.execute(
        text("""
            SELECT detail_id, overview_text, best_time, transportation,
                   top_experiences, notices, gallery_images, map_embed_url,
                   ticket_adult, ticket_child
            FROM DestinationDetails
            WHERE destination_id = :destination_id
            ORDER BY detail_id ASC
            LIMIT 1
        """),
        {'destination_id': destination_id},
    ).mappings().first()
    return destination, detail


def _form_from_rows(destination, detail):
    values = {}
    for field in FORM_FIELDS:
        source = detail if field in DETAIL_TEXT_FIELDS + DETAIL_PRICE_FIELDS else destination
        value = source.get(field) if source is not None else None
        values[field] = '' if value is None else str(value)
    return values


def _validate_form(values):
    cleaned = {field: values.get(field, '').strip() for field in FORM_FIELDS}
    errors = []

    if not cleaned['name']:
        errors.append('Vui lòng nhập tên địa điểm.')
    for field, limit in FIELD_LIMITS.items():
        if len(cleaned[field]) > limit:
            errors.append(f"{FIELD_LABELS[field]} không được vượt quá {limit} ký tự.")

    rating_text = cleaned['rating']
    try:
        rating = Decimal(rating_text) if rating_text else Decimal('4.5')
        if not rating.is_finite() or not 0 <= rating <= 5:
            raise ValueError
    except (InvalidOperation, ValueError):
        errors.append('Đánh giá phải là số từ 0 đến 5.')
        rating = None

    reviews_text = cleaned['reviews_count']
    try:
        reviews_count = int(reviews_text) if reviews_text else 0
        if not 0 <= reviews_count <= 2147483647:
            raise ValueError
    except ValueError:
        errors.append('Số lượt đánh giá phải là số nguyên từ 0 đến 2147483647.')
        reviews_count = None

    prices = {}
    for field, label in (
        ('ticket_adult', 'Giá vé người lớn'),
        ('ticket_child', 'Giá vé trẻ em'),
    ):
        try:
            price = Decimal(cleaned[field]) if cleaned[field] else Decimal('0.00')
            if (
                not price.is_finite()
                or not 0 <= price < 100000000
                or price != price.quantize(Decimal('0.01'))
            ):
                raise ValueError
            prices[field] = str(price)
        except (InvalidOperation, ValueError):
            errors.append(f'{label} phải là số không âm, tối đa 2 chữ số thập phân và nhỏ hơn 100000000.')

    main_values = {
        'name': cleaned['name'],
        'category': cleaned['category'] or None,
        'area': cleaned['area'] or None,
        'address': cleaned['address'] or None,
        'rating': float(rating) if rating is not None else None,
        'reviews_count': reviews_count,
        'main_image': cleaned['main_image'] or None,
        'opening_hours': cleaned['opening_hours'] or None,
    }
    detail_values = {
        field: cleaned[field] or None for field in DETAIL_TEXT_FIELDS
    }
    detail_values.update(prices)
    has_details = any(
        cleaned[field] for field in DETAIL_TEXT_FIELDS + DETAIL_PRICE_FIELDS
    )
    return main_values, detail_values, has_details, errors


def _save_details(destination_id, detail_id, values, has_details):
    params = {**values, 'destination_id': destination_id}
    if detail_id is not None:
        params['detail_id'] = detail_id
        db.session.execute(
            text("""
                UPDATE DestinationDetails
                SET overview_text = :overview_text,
                    best_time = :best_time,
                    transportation = :transportation,
                    top_experiences = :top_experiences,
                    notices = :notices,
                    gallery_images = :gallery_images,
                    map_embed_url = :map_embed_url,
                    ticket_adult = :ticket_adult,
                    ticket_child = :ticket_child
                WHERE detail_id = :detail_id AND destination_id = :destination_id
            """),
            params,
        )
    elif has_details:
        db.session.execute(
            text("""
                INSERT INTO DestinationDetails (
                    destination_id, overview_text, best_time, transportation,
                    top_experiences, notices, gallery_images, map_embed_url,
                    ticket_adult, ticket_child
                ) VALUES (
                    :destination_id, :overview_text, :best_time, :transportation,
                    :top_experiences, :notices, :gallery_images, :map_embed_url,
                    :ticket_adult, :ticket_child
                )
            """),
            params,
        )


def _render_form(mode, values, errors=(), destination_id=None, status=200):
    return render_template(
        'admin/destinations_management.html',
        view='form',
        form_mode=mode,
        form_values=values,
        destination_id=destination_id,
        errors=errors,
    ), status


@admin_bp.route('/admin/destinations', methods=['GET'])
def destinations():
    keyword = request.args.get('keyword', '').strip()
    return render_template(
        'admin/destinations_management.html',
        view='list',
        destinations=_list_destinations(keyword),
        keyword=keyword,
        errors=(),
    )


@admin_bp.route('/admin/destinations/new', methods=['GET', 'POST'])
def create_destination():
    if request.method == 'GET':
        values = {field: '' for field in FORM_FIELDS}
        values.update(rating='4.5', reviews_count='0')
        return _render_form('create', values)

    values = {field: request.form.get(field, '') for field in FORM_FIELDS}
    main_values, detail_values, _has_details, errors = _validate_form(values)
    if errors:
        return _render_form('create', values, errors, status=400)

    try:
        result = db.session.execute(
            text("""
                INSERT INTO TouristDestinations (
                    name, category, area, address, rating, reviews_count,
                    main_image, opening_hours
                ) VALUES (
                    :name, :category, :area, :address, :rating, :reviews_count,
                    :main_image, :opening_hours
                )
            """),
            main_values,
        )
        # The public detail page formats ticket prices as numbers, so every
        # new destination needs a details row even when optional fields are blank.
        _save_details(result.lastrowid, None, detail_values, True)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _render_form(
            'create', values,
            ['Không thể lưu địa điểm. Vui lòng thử lại.'],
            status=500,
        )
    except Exception:
        db.session.rollback()
        raise
    return redirect(url_for('admin.destinations'))


@admin_bp.route('/admin/destinations/<int:destination_id>/edit', methods=['GET', 'POST'])
def edit_destination(destination_id):
    destination, detail = _load_destination(destination_id)
    if request.method == 'GET':
        return _render_form(
            'edit', _form_from_rows(destination, detail),
            destination_id=destination_id,
        )

    values = {field: request.form.get(field, '') for field in FORM_FIELDS}
    main_values, detail_values, has_details, errors = _validate_form(values)
    if errors:
        return _render_form('edit', values, errors, destination_id, 400)

    try:
        db.session.execute(
            text("""
                UPDATE TouristDestinations
                SET name = :name, category = :category, area = :area,
                    address = :address, rating = :rating,
                    reviews_count = :reviews_count, main_image = :main_image,
                    opening_hours = :opening_hours
                WHERE destination_id = :destination_id
            """),
            {**main_values, 'destination_id': destination_id},
        )
        _save_details(
            destination_id, detail['detail_id'] if detail else None,
            detail_values, has_details,
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _render_form(
            'edit', values,
            ['Không thể cập nhật địa điểm. Vui lòng thử lại.'],
            destination_id, 500,
        )
    except Exception:
        db.session.rollback()
        raise
    return redirect(url_for('admin.destinations'))


@admin_bp.route('/admin/destinations/<int:destination_id>/delete', methods=['POST'])
def delete_destination(destination_id):
    try:
        result = db.session.execute(
            text("""
                DELETE FROM TouristDestinations
                WHERE destination_id = :destination_id
            """),
            {'destination_id': destination_id},
        )
        if result.rowcount == 0:
            abort(404)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return render_template(
            'admin/destinations_management.html',
            view='list',
            destinations=_list_destinations(''),
            keyword='',
            errors=['Không thể xóa địa điểm. Vui lòng thử lại.'],
        ), 500
    except Exception:
        db.session.rollback()
        raise
    return redirect(url_for('admin.destinations'))


# Accommodation statuses that have an established meaning in this project:
# Pending is the database default; the public home page displays Approved.
ACCOMMODATION_STATUSES = ('Pending', 'Approved')
ACCOMMODATION_FIELDS = (
    'host_id', 'name', 'property_type', 'address', 'description', 'policies',
    'amenities', 'images', 'check_in_time', 'check_out_time', 'cancel_policy',
    'children_policy', 'map_distance_info',
)
ACCOMMODATION_LIMITS = {
    'name': 255, 'property_type': 100, 'check_in_time': 50,
    'check_out_time': 50, 'map_distance_info': 255,
}
ACCOMMODATION_LABELS = {
    'name': 'Tên cơ sở', 'property_type': 'Loại cơ sở',
    'check_in_time': 'Giờ nhận phòng', 'check_out_time': 'Giờ trả phòng',
    'map_distance_info': 'Thông tin khoảng cách',
}
ACCOMMODATION_DEFAULT_FIELDS = (
    'property_type', 'check_in_time', 'check_out_time', 'map_distance_info',
)


def _accommodation_hosts():
    return db.session.execute(text("""
        SELECT u.user_id, u.full_name, u.email, u.role,
               a.accommodation_id AS assigned_accommodation_id
        FROM Users u
        LEFT JOIN Accommodations a ON a.host_id = u.user_id
        ORDER BY u.full_name, u.user_id
    """)).mappings().all()


def _accommodation_form_values(row=None):
    return {
        field: '' if row is None or row[field] is None else str(row[field])
        for field in ACCOMMODATION_FIELDS
    }


def _validate_accommodation(values, accommodation_id=None):
    cleaned = {field: values.get(field, '').strip() for field in ACCOMMODATION_FIELDS}
    errors = []
    if not cleaned['name']:
        errors.append('Vui lòng nhập tên cơ sở.')
    if not cleaned['address']:
        errors.append('Vui lòng nhập địa chỉ cơ sở.')
    for field, limit in ACCOMMODATION_LIMITS.items():
        if len(cleaned[field]) > limit:
            errors.append(f'{ACCOMMODATION_LABELS[field]} không được vượt quá {limit} ký tự.')

    host_id = None
    if cleaned['host_id']:
        try:
            host_id = int(cleaned['host_id'])
            if host_id <= 0:
                raise ValueError
        except ValueError:
            errors.append('Tài khoản chủ cơ sở không hợp lệ.')
        else:
            host = db.session.execute(text("""
                SELECT u.user_id, a.accommodation_id AS assigned_accommodation_id
                FROM Users u
                LEFT JOIN Accommodations a ON a.host_id = u.user_id
                WHERE u.user_id = :host_id
            """), {'host_id': host_id}).mappings().first()
            if host is None:
                errors.append('Tài khoản chủ cơ sở không tồn tại.')
            elif (host['assigned_accommodation_id'] is not None
                  and host['assigned_accommodation_id'] != accommodation_id):
                errors.append('Tài khoản này đã sở hữu một cơ sở khác.')

    params = {field: cleaned[field] or None for field in ACCOMMODATION_FIELDS}
    params.update(host_id=host_id, name=cleaned['name'], address=cleaned['address'])
    return params, errors


def _load_accommodation(accommodation_id, lock=False):
    if lock:
        suffix = ' FOR UPDATE' if db.engine.dialect.name == 'mysql' else ''
        locked_id = db.session.execute(text("""
            SELECT accommodation_id FROM Accommodations
            WHERE accommodation_id = :accommodation_id
        """ + suffix), {'accommodation_id': accommodation_id}).scalar_one_or_none()
        if locked_id is None:
            abort(404)
    row = db.session.execute(text("""
        SELECT a.*, u.full_name AS host_name, u.email AS host_email,
               u.phone AS host_phone, u.role AS host_role,
               u.status AS host_status,
               (SELECT COUNT(*) FROM Rooms r
                WHERE r.accommodation_id = a.accommodation_id) AS room_count,
               (SELECT COUNT(*) FROM Reviews v
                WHERE v.accommodation_id = a.accommodation_id) AS review_count
        FROM Accommodations a
        LEFT JOIN Users u ON u.user_id = a.host_id
        WHERE a.accommodation_id = :accommodation_id
    """), {'accommodation_id': accommodation_id}).mappings().first()
    if row is None:
        abort(404)
    return row


def _render_accommodation_form(mode, values, errors=(), accommodation_id=None,
                               status=200):
    return render_template(
        'admin/accommodations_management.html', view='form', mode=mode,
        form_values=values, accommodation_id=accommodation_id,
        hosts=_accommodation_hosts(), errors=errors,
        statuses=ACCOMMODATION_STATUSES,
    ), status


def _render_accommodation_detail(accommodation_id, errors=(), status=200):
    accommodation = _load_accommodation(accommodation_id)
    rooms = db.session.execute(text("""
        SELECT room_id, room_name, room_type, status
        FROM Rooms WHERE accommodation_id = :accommodation_id
        ORDER BY room_id
    """), {'accommodation_id': accommodation_id}).mappings().all()
    return render_template(
        'admin/accommodations_management.html', view='detail',
        accommodation=accommodation, rooms=rooms,
        statuses=ACCOMMODATION_STATUSES, errors=errors,
    ), status


@admin_bp.route('/admin/accommodations', methods=['GET'])
def accommodations():
    keyword = request.args.get('keyword', '').strip()
    status_filter = request.args.get('status', '').strip()
    params = {}
    query = """
        SELECT a.accommodation_id, a.name, a.property_type, a.address,
               a.status, a.images, u.full_name AS host_name,
               u.email AS host_email,
               (SELECT COUNT(*) FROM Rooms r
                WHERE r.accommodation_id = a.accommodation_id) AS room_count
        FROM Accommodations a
        LEFT JOIN Users u ON u.user_id = a.host_id
        WHERE 1 = 1
    """
    if keyword:
        query += " AND (a.name LIKE :keyword OR a.address LIKE :keyword OR u.full_name LIKE :keyword OR u.email LIKE :keyword)"
        params['keyword'] = f'%{keyword}%'
    if status_filter:
        query += ' AND a.status = :status'
        params['status'] = status_filter
    query += ' ORDER BY a.accommodation_id DESC'
    rows = db.session.execute(text(query), params).mappings().all()
    counts = db.session.execute(text("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'Approved' THEN 1 ELSE 0 END) AS approved,
               SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) AS pending
        FROM Accommodations
    """)).mappings().one()
    existing_statuses = db.session.execute(text("""
        SELECT DISTINCT status FROM Accommodations
        WHERE status IS NOT NULL ORDER BY status
    """)).scalars().all()
    filter_statuses = list(dict.fromkeys((*ACCOMMODATION_STATUSES, *existing_statuses)))
    return render_template(
        'admin/accommodations_management.html', view='list',
        accommodations=rows, keyword=keyword, status_filter=status_filter,
        filter_statuses=filter_statuses, counts=counts,
        notice=request.args.get('notice', ''), errors=(),
    )


@admin_bp.route('/admin/accommodations/<int:accommodation_id>', methods=['GET'])
def accommodation_detail(accommodation_id):
    return _render_accommodation_detail(accommodation_id)


@admin_bp.route('/admin/accommodations/new', methods=['GET', 'POST'])
def create_accommodation():
    if request.method == 'GET':
        return _render_accommodation_form('create', _accommodation_form_values())
    values = {field: request.form.get(field, '') for field in ACCOMMODATION_FIELDS}
    params, errors = _validate_accommodation(values)
    if errors:
        return _render_accommodation_form('create', values, errors, status=400)
    # Leave columns with database defaults out of INSERT when not provided.
    fields = [field for field in ACCOMMODATION_FIELDS
              if field not in ACCOMMODATION_DEFAULT_FIELDS or params[field] is not None]
    columns = ', '.join(fields)
    placeholders = ', '.join(':' + field for field in fields)
    try:
        db.session.execute(text(
            f'INSERT INTO Accommodations ({columns}) VALUES ({placeholders})'
        ), {field: params[field] for field in fields})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _render_accommodation_form(
            'create', values, ['Tài khoản chủ cơ sở đã được gán hoặc dữ liệu không hợp lệ.'],
            status=409,
        )
    except SQLAlchemyError:
        db.session.rollback()
        return _render_accommodation_form(
            'create', values, ['Không thể lưu cơ sở. Vui lòng thử lại.'], status=500,
        )
    return redirect(url_for('admin.accommodations', notice='created'))


@admin_bp.route('/admin/accommodations/<int:accommodation_id>/edit', methods=['GET', 'POST'])
def edit_accommodation(accommodation_id):
    accommodation = _load_accommodation(accommodation_id)
    if request.method == 'GET':
        return _render_accommodation_form(
            'edit', _accommodation_form_values(accommodation),
            accommodation_id=accommodation_id,
        )
    values = {field: request.form.get(field, '') for field in ACCOMMODATION_FIELDS}
    params, errors = _validate_accommodation(values, accommodation_id)
    if errors:
        return _render_accommodation_form(
            'edit', values, errors, accommodation_id, 400,
        )
    assignments = ', '.join(f'{field} = :{field}' for field in ACCOMMODATION_FIELDS)
    try:
        result = db.session.execute(text(
            f'UPDATE Accommodations SET {assignments} WHERE accommodation_id = :accommodation_id'
        ), {**params, 'accommodation_id': accommodation_id})
        if result.rowcount == 0:
            db.session.rollback()
            abort(404)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _render_accommodation_form(
            'edit', values, ['Tài khoản chủ cơ sở đã được gán hoặc dữ liệu không hợp lệ.'],
            accommodation_id, 409,
        )
    except SQLAlchemyError:
        db.session.rollback()
        return _render_accommodation_form(
            'edit', values, ['Không thể cập nhật cơ sở. Vui lòng thử lại.'],
            accommodation_id, 500,
        )
    return redirect(url_for('admin.accommodation_detail', accommodation_id=accommodation_id))


@admin_bp.route('/admin/accommodations/<int:accommodation_id>/status', methods=['POST'])
def change_accommodation_status(accommodation_id):
    new_status = request.form.get('status', '').strip()
    if new_status not in ACCOMMODATION_STATUSES:
        return _render_accommodation_detail(
            accommodation_id, ['Trạng thái không được hỗ trợ.'], 400,
        )
    try:
        accommodation = _load_accommodation(accommodation_id, lock=True)
        if accommodation['status'] != new_status:
            db.session.execute(text("""
                UPDATE Accommodations SET status = :status
                WHERE accommodation_id = :accommodation_id
            """), {'status': new_status, 'accommodation_id': accommodation_id})
            db.session.commit()
        else:
            db.session.rollback()
    except SQLAlchemyError:
        db.session.rollback()
        return _render_accommodation_detail(
            accommodation_id, ['Không thể đổi trạng thái. Vui lòng thử lại.'], 500,
        )
    return redirect(url_for('admin.accommodation_detail', accommodation_id=accommodation_id))


@admin_bp.route('/admin/accommodations/<int:accommodation_id>/delete', methods=['POST'])
def delete_accommodation(accommodation_id):
    try:
        accommodation = _load_accommodation(accommodation_id, lock=True)
        reasons = []
        if accommodation['room_count']:
            reasons.append(f"Cơ sở còn {accommodation['room_count']} phòng; xóa có thể kéo theo lịch sử đặt phòng và thanh toán.")
        if accommodation['review_count']:
            reasons.append(f"Cơ sở còn {accommodation['review_count']} đánh giá.")
        if reasons:
            db.session.rollback()
            return _render_accommodation_detail(accommodation_id, reasons, 409)
        result = db.session.execute(text("""
            DELETE FROM Accommodations
            WHERE accommodation_id = :accommodation_id
        """), {'accommodation_id': accommodation_id})
        if result.rowcount == 0:
            db.session.rollback()
            abort(404)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _render_accommodation_detail(
            accommodation_id, ['Không thể xóa cơ sở. Vui lòng thử lại.'], 500,
        )
    return redirect(url_for('admin.accommodations', notice='deleted'))


@admin_bp.route('/admin/', methods=['GET'])
@admin_bp.route('/admin/dashboard', methods=['GET'])
def dashboard():
    user_roles = db.session.execute(text("""
        SELECT role, COUNT(*) AS total
        FROM Users GROUP BY role ORDER BY total DESC, role
    """)).mappings().all()
    accommodation_statuses = db.session.execute(text("""
        SELECT status, COUNT(*) AS total
        FROM Accommodations GROUP BY status ORDER BY total DESC, status
    """)).mappings().all()
    booking_statuses = db.session.execute(text("""
        SELECT status, COUNT(*) AS total
        FROM Bookings GROUP BY status ORDER BY total DESC, status
    """)).mappings().all()
    room_count = db.session.execute(text('SELECT COUNT(*) FROM Rooms')).scalar_one()

    start_day = date.today() - timedelta(days=6)
    end_day = date.today() + timedelta(days=1)
    daily_rows = db.session.execute(text("""
        SELECT DATE(created_at) AS booking_day, COUNT(*) AS total
        FROM Bookings
        WHERE created_at >= :start_day AND created_at < :end_day
        GROUP BY DATE(created_at) ORDER BY booking_day
    """), {'start_day': start_day, 'end_day': end_day}).mappings().all()
    daily_counts = {str(row['booking_day']): row['total'] for row in daily_rows}
    chart_days = [
        {'label': (start_day + timedelta(days=offset)).strftime('%d/%m'),
         'count': daily_counts.get(str(start_day + timedelta(days=offset)), 0)}
        for offset in range(7)
    ]
    chart_max = max((day['count'] for day in chart_days), default=0)
    for day in chart_days:
        day['percent'] = round(day['count'] * 100 / chart_max) if chart_max else 0

    activities = []
    for row in db.session.execute(text("""
        SELECT user_id, full_name, role, status, created_at
        FROM Users WHERE created_at IS NOT NULL
        ORDER BY created_at DESC, user_id DESC LIMIT 8
    """)).mappings():
        activities.append({
            'kind': 'Tài khoản mới', 'title': row['full_name'],
            'detail': row['role'], 'status': row['status'],
            'time': row['created_at'],
            'url': url_for('admin.user_detail', user_id=row['user_id']),
        })
    for row in db.session.execute(text("""
        SELECT accommodation_id, name, status, updated_at
        FROM Accommodations WHERE updated_at IS NOT NULL
        ORDER BY updated_at DESC, accommodation_id DESC LIMIT 8
    """)).mappings():
        activities.append({
            'kind': 'Cơ sở cập nhật', 'title': row['name'],
            'detail': 'Cơ sở lưu trú', 'status': row['status'],
            'time': row['updated_at'],
            'url': url_for('admin.accommodation_detail',
                           accommodation_id=row['accommodation_id']),
        })
    for row in db.session.execute(text("""
        SELECT b.booking_id, b.status, b.created_at,
               u.full_name AS customer_name, r.room_name,
               a.name AS accommodation_name
        FROM Bookings b
        JOIN Users u ON u.user_id = b.customer_id
        JOIN Rooms r ON r.room_id = b.room_id
        JOIN Accommodations a ON a.accommodation_id = r.accommodation_id
        WHERE b.created_at IS NOT NULL
        ORDER BY b.created_at DESC, b.booking_id DESC LIMIT 8
    """)).mappings():
        activities.append({
            'kind': 'Đặt phòng mới',
            'title': f"Đặt phòng #{row['booking_id']}: {row['room_name']}",
            'detail': f"{row['accommodation_name']} · {row['customer_name']}",
            'status': row['status'], 'time': row['created_at'],
            'url': None,
        })
    activities = sorted(
        activities, key=lambda item: str(item['time']), reverse=True,
    )[:8]

    return render_template(
        'admin/dashboard.html', user_roles=user_roles,
        accommodation_statuses=accommodation_statuses,
        booking_statuses=booking_statuses, room_count=room_count,
        user_count=sum(row['total'] for row in user_roles),
        accommodation_count=sum(row['total'] for row in accommodation_statuses),
        booking_count=sum(row['total'] for row in booking_statuses),
        chart_days=chart_days, has_chart_data=chart_max > 0,
        activities=activities,
    )


@admin_bp.route('/admin/users', methods=['GET'])
def users():
    keyword = request.args.get('keyword', '').strip()
    role_filter = request.args.get('role', '').strip()
    status_filter = request.args.get('status', '').strip()
    params = {}
    query = """
        SELECT user_id, full_name, email, phone, role, status, created_at
        FROM Users WHERE 1 = 1
    """
    if keyword:
        query += ' AND (full_name LIKE :keyword OR email LIKE :keyword)'
        params['keyword'] = f'%{keyword}%'
    if role_filter:
        query += ' AND role = :role'
        params['role'] = role_filter
    if status_filter:
        query += ' AND status = :status'
        params['status'] = status_filter
    query += ' ORDER BY user_id DESC'
    user_rows = db.session.execute(text(query), params).mappings().all()
    counts = db.session.execute(text("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) AS active,
               SUM(CASE WHEN role = 'Host' THEN 1 ELSE 0 END) AS hosts,
               SUM(CASE WHEN role = 'Admin' THEN 1 ELSE 0 END) AS admins
        FROM Users
    """)).mappings().one()
    roles = db.session.execute(text(
        'SELECT DISTINCT role FROM Users WHERE role IS NOT NULL ORDER BY role'
    )).scalars().all()
    statuses = db.session.execute(text(
        'SELECT DISTINCT status FROM Users WHERE status IS NOT NULL ORDER BY status'
    )).scalars().all()
    admin_id = _current_admin_id()
    return render_template(
        'admin/users_management.html', view='list', users=user_rows,
        keyword=keyword, role_filter=role_filter, status_filter=status_filter,
        roles=roles, statuses=statuses, counts=counts,
        current_admin_id=admin_id, delete_csrf_token=_user_delete_token(admin_id),
        notice=request.args.get('notice', ''),
    )


USER_CONTACT_FIELDS = ('full_name', 'email', 'phone')


def _load_user(user_id, lock=False):
    if lock:
        suffix = ' FOR UPDATE' if db.engine.dialect.name == 'mysql' else ''
        locked_id = db.session.execute(text("""
            SELECT user_id FROM Users WHERE user_id = :user_id
        """ + suffix), {'user_id': user_id}).scalar_one_or_none()
        if locked_id is None:
            abort(404)
    # Select only fields the admin screen needs; never select password_hash.
    user = db.session.execute(text("""
        SELECT user_id, full_name, email, phone, role, status, created_at
        FROM Users WHERE user_id = :user_id
    """), {'user_id': user_id}).mappings().first()
    if user is None:
        abort(404)
    return user


def _render_user_form(user_id, values, errors=(), status=200):
    return render_template(
        'admin/users_management.html', view='form', user_id=user_id,
        form_values=values, errors=errors,
    ), status


def _user_delete_token(admin_id):
    if admin_id is None:
        return None
    token = session.get('admin_delete_user_token')
    if session.get('admin_delete_user_id') != admin_id or not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session['admin_delete_user_id'] = admin_id
        session['admin_delete_user_token'] = token
    return token


def _render_user_detail(user, admin_id, errors=(), status=200):
    return render_template(
        'admin/users_management.html', view='detail', user=user, errors=errors,
        current_admin_id=admin_id, delete_csrf_token=_user_delete_token(admin_id),
    ), status


@admin_bp.route('/admin/users/<int:user_id>', methods=['GET'])
def user_detail(user_id):
    return _render_user_detail(_load_user(user_id), _current_admin_id())


# Each of these foreign keys currently cascades from Users. Refuse deletion if
# the live schema differs, or if even one related row exists.
USER_DELETE_DEPENDENCIES = (
    ('Accommodations', 'host_id',
     'Tài khoản còn cơ sở lưu trú; xóa có thể kéo theo phòng, đặt phòng, thanh toán và đánh giá.'),
    ('Bookings', 'customer_id',
     'Tài khoản còn đặt phòng; xóa có thể kéo theo thanh toán và đánh giá.'),
    ('Reviews', 'customer_id', 'Tài khoản còn đánh giá.'),
    ('Notifications', 'user_id', 'Tài khoản còn thông báo.'),
    ('Wishlists', 'customer_id', 'Tài khoản còn mục yêu thích.'),
)


def _user_delete_reasons(user_id):
    schema = db.session.execute(text('SELECT DATABASE()')).scalar_one()
    foreign_keys = db.session.execute(text("""
        SELECT k.TABLE_SCHEMA, k.TABLE_NAME, k.COLUMN_NAME,
               k.REFERENCED_COLUMN_NAME, r.DELETE_RULE
        FROM information_schema.KEY_COLUMN_USAGE k
        JOIN information_schema.REFERENTIAL_CONSTRAINTS r
          ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
         AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
         AND r.TABLE_NAME = k.TABLE_NAME
        WHERE k.REFERENCED_TABLE_SCHEMA = DATABASE()
          AND k.REFERENCED_TABLE_NAME = 'Users'
    """)).all()
    expected = {
        (schema, table, column, 'user_id', 'CASCADE')
        for table, column, _ in USER_DELETE_DEPENDENCIES
    }
    if set(foreign_keys) != expected:
        return ['Các khóa ngoại liên kết với Users đã thay đổi; cần kiểm tra lại cấu trúc dữ liệu trước khi xóa.']

    tables = {'Users', *(table for table, _, _ in USER_DELETE_DEPENDENCIES)}
    engines = dict(db.session.execute(text("""
        SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
    """)).all())
    if any(engines.get(table) != 'InnoDB' for table in tables):
        return ['Không thể xác nhận các bảng liên quan dùng giao dịch InnoDB; dừng xóa để giữ an toàn dữ liệu.']

    has_delete_trigger = db.session.execute(text("""
        SELECT 1 FROM information_schema.TRIGGERS
        WHERE EVENT_OBJECT_SCHEMA = DATABASE()
          AND EVENT_OBJECT_TABLE = 'Users'
          AND EVENT_MANIPULATION = 'DELETE'
        LIMIT 1
    """)).scalar_one_or_none()
    if has_delete_trigger:
        return ['Bảng Users có trigger DELETE; cần kiểm tra tác động của trigger trước khi xóa.']

    reasons = []
    for table, column, reason in USER_DELETE_DEPENDENCIES:
        # These identifiers are fixed above, never taken from the request.
        exists = db.session.execute(text(
            f'SELECT 1 FROM `{table}` WHERE `{column}` = :user_id LIMIT 1 FOR UPDATE'
        ), {'user_id': user_id}).scalar_one_or_none()
        if exists:
            reasons.append(reason)
    return reasons


@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    admin_id = _authenticated_admin_principal_id()
    if admin_id is None:
        abort(403, description='Chỉ quản trị viên đã đăng nhập mới được xóa người dùng.')
    if user_id == admin_id:
        return _render_user_detail(
            _load_user(user_id), admin_id,
            ['Không thể xóa tài khoản quản trị viên đang sử dụng.'], 409,
        )
    token = session.get('admin_delete_user_token')
    if (
        session.get('admin_delete_user_id') != admin_id
        or not isinstance(token, str)
        or not secrets.compare_digest(token, request.form.get('csrf_token', ''))
    ):
        abort(400, description='Phiên xác nhận xóa không hợp lệ. Vui lòng tải lại trang và thử lại.')

    try:
        locked_admin = db.session.execute(text("""
            SELECT user_id FROM Users
            WHERE user_id = :admin_id AND role = 'Admin' FOR UPDATE
        """), {'admin_id': admin_id}).scalar_one_or_none()
        if locked_admin is None:
            db.session.rollback()
            abort(403, description='Tài khoản hiện tại không có quyền quản trị.')
        user = db.session.execute(text("""
            SELECT user_id, full_name, email, phone, role, status, created_at
            FROM Users WHERE user_id = :user_id FOR UPDATE
        """), {'user_id': user_id}).mappings().first()
        if user is None:
            db.session.rollback()
            abort(404)
        reasons = _user_delete_reasons(user_id)
        if reasons:
            db.session.rollback()
            return _render_user_detail(user, admin_id, reasons, 409)

        result = db.session.execute(text("""
            DELETE FROM Users WHERE user_id = :user_id AND user_id <> :admin_id
        """), {'user_id': user_id, 'admin_id': admin_id})
        if result.rowcount != 1:
            db.session.rollback()
            return _render_user_detail(
                user, admin_id, ['Không thể xác nhận tài khoản cần xóa; dữ liệu được giữ nguyên.'], 409,
            )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        if 'user' in locals() and user is not None:
            return _render_user_detail(
                user, admin_id,
                ['Không thể hoàn tất thao tác do lỗi cơ sở dữ liệu. Vui lòng tải lại danh sách để kiểm tra.'],
                503,
            )
        abort(503, description='Không thể kiểm tra tài khoản và dữ liệu liên quan; thao tác xóa bị dừng.')

    session.pop('admin_delete_user_token', None)
    session.pop('admin_delete_user_id', None)
    return redirect(url_for('admin.users', notice='deleted'))


@admin_bp.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
def edit_user(user_id):
    user = _load_user(user_id)
    if request.method == 'GET':
        values = {
            field: '' if user[field] is None else str(user[field])
            for field in USER_CONTACT_FIELDS
        }
        return _render_user_form(user_id, values)

    values = {field: request.form.get(field, '').strip() for field in USER_CONTACT_FIELDS}
    errors = []
    if not values['full_name']:
        errors.append('Vui lòng nhập họ tên.')
    elif len(values['full_name']) > 255:
        errors.append('Họ tên không được vượt quá 255 ký tự.')
    if not values['email']:
        errors.append('Vui lòng nhập email.')
    elif len(values['email']) > 255 or not re.fullmatch(
        r'[^\s@]+@[^\s@]+\.[^\s@]+', values['email']
    ):
        errors.append('Email không hợp lệ hoặc vượt quá 255 ký tự.')
    if len(values['phone']) > 20:
        errors.append('Số điện thoại không được vượt quá 20 ký tự.')
    elif values['phone'] and (
        not re.fullmatch(r'[+()\d\s.\-]+', values['phone'])
        or not any(char.isdigit() for char in values['phone'])
    ):
        errors.append('Số điện thoại chỉ được chứa chữ số và các ký tự + ( ) . -.')
    if not errors:
        duplicate = db.session.execute(text("""
            SELECT user_id FROM Users
            WHERE LOWER(email) = LOWER(:email) AND user_id <> :user_id
            LIMIT 1
        """), {'email': values['email'], 'user_id': user_id}).scalar_one_or_none()
        if duplicate is not None:
            errors.append('Email đã được tài khoản khác sử dụng.')
    if errors:
        return _render_user_form(user_id, values, errors, 400)

    try:
        _load_user(user_id, lock=True)
        db.session.execute(text("""
            UPDATE Users SET full_name = :full_name, email = :email,
                             phone = :phone
            WHERE user_id = :user_id
        """), {
            'full_name': values['full_name'], 'email': values['email'],
            'phone': values['phone'] or None, 'user_id': user_id,
        })
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _render_user_form(
            user_id, values, ['Email đã được tài khoản khác sử dụng.'], 409,
        )
    except SQLAlchemyError:
        db.session.rollback()
        return _render_user_form(
            user_id, values, ['Không thể cập nhật tài khoản. Vui lòng thử lại.'], 500,
        )
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/admin/hosts', methods=['GET'])
def hosts():
    keyword = request.args.get('keyword', '').strip()
    status_filter = request.args.get('status', '').strip()
    params = {'host_role': 'Host'}
    query = """
        SELECT u.user_id, u.full_name, u.email, u.phone,
               u.status AS user_status, u.created_at,
               a.accommodation_id, a.name AS accommodation_name,
               a.property_type, a.address, a.status AS accommodation_status
        FROM Users u
        LEFT JOIN Accommodations a ON a.host_id = u.user_id
        WHERE u.role = :host_role
    """
    if keyword:
        query += """
            AND (u.full_name LIKE :keyword OR u.email LIKE :keyword
                 OR u.phone LIKE :keyword OR a.name LIKE :keyword
                 OR a.address LIKE :keyword)
        """
        params['keyword'] = f'%{keyword}%'
    if status_filter == 'unassigned':
        query += ' AND a.accommodation_id IS NULL'
    elif status_filter:
        query += ' AND a.status = :status_filter'
        params['status_filter'] = status_filter
    query += ' ORDER BY u.user_id DESC'
    host_rows = db.session.execute(text(query), params).mappings().all()
    counts = db.session.execute(text("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN a.accommodation_id IS NULL THEN 1 ELSE 0 END) AS unassigned,
               SUM(CASE WHEN a.status = 'Pending' THEN 1 ELSE 0 END) AS pending,
               SUM(CASE WHEN a.status = 'Approved' THEN 1 ELSE 0 END) AS approved
        FROM Users u
        LEFT JOIN Accommodations a ON a.host_id = u.user_id
        WHERE u.role = :host_role
    """), {'host_role': 'Host'}).mappings().one()
    actual_statuses = db.session.execute(text("""
        SELECT DISTINCT a.status
        FROM Accommodations a
        JOIN Users u ON u.user_id = a.host_id
        WHERE u.role = :host_role AND a.status IS NOT NULL
        ORDER BY a.status
    """), {'host_role': 'Host'}).scalars().all()
    filter_statuses = list(dict.fromkeys((*ACCOMMODATION_STATUSES, *actual_statuses)))
    return render_template(
        'admin/hosts_approval.html', view='list', hosts=host_rows,
        keyword=keyword, status_filter=status_filter, counts=counts,
        filter_statuses=filter_statuses,
    )


def _host_and_accommodation(user_id):
    host = db.session.execute(text("""
        SELECT user_id, full_name, email, phone, role, status, created_at
        FROM Users WHERE user_id = :user_id AND role = :host_role
    """), {'user_id': user_id, 'host_role': 'Host'}).mappings().first()
    if host is None:
        abort(404)
    accommodation = db.session.execute(text("""
        SELECT a.*,
               (SELECT COUNT(*) FROM Rooms r
                WHERE r.accommodation_id = a.accommodation_id) AS room_count
        FROM Accommodations a WHERE a.host_id = :user_id
    """), {'user_id': user_id}).mappings().first()
    return host, accommodation


def _render_host_detail(user_id, errors=(), status=200):
    host, accommodation = _host_and_accommodation(user_id)
    return render_template(
        'admin/hosts_approval.html', view='detail', host=host,
        accommodation=accommodation, errors=errors,
    ), status


@admin_bp.route('/admin/hosts/<int:user_id>', methods=['GET'])
def host_detail(user_id):
    return _render_host_detail(user_id)


@admin_bp.route('/admin/hosts/<int:user_id>/accommodation/approve', methods=['POST'])
def approve_host_accommodation(user_id):
    _host, accommodation = _host_and_accommodation(user_id)
    if accommodation is None:
        return _render_host_detail(
            user_id, ['Tài khoản chủ này chưa có cơ sở lưu trú để duyệt.'], 409,
        )
    accommodation_id = accommodation['accommodation_id']
    try:
        suffix = ' FOR UPDATE' if db.engine.dialect.name == 'mysql' else ''
        current_row = db.session.execute(text("""
            SELECT accommodation_id, status FROM Accommodations
            WHERE accommodation_id = :accommodation_id AND host_id = :user_id
        """ + suffix), {
            'accommodation_id': accommodation_id, 'user_id': user_id,
        }).mappings().first()
        if current_row is None:
            db.session.rollback()
            return _render_host_detail(
                user_id, ['Cơ sở không còn liên kết với chủ này.'], 409,
            )
        if current_row['status'] != 'Pending':
            db.session.rollback()
            return _render_host_detail(
                user_id, ['Chỉ có thể duyệt cơ sở đang ở trạng thái Pending.'], 409,
            )
        result = db.session.execute(text("""
            UPDATE Accommodations SET status = :approved
            WHERE accommodation_id = :accommodation_id
              AND host_id = :user_id AND status = :pending
        """), {
            'approved': 'Approved', 'pending': 'Pending',
            'accommodation_id': accommodation_id, 'user_id': user_id,
        })
        if result.rowcount != 1:
            db.session.rollback()
            return _render_host_detail(
                user_id, ['Trạng thái cơ sở đã thay đổi. Vui lòng tải lại trang.'], 409,
            )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return _render_host_detail(
            user_id, ['Không thể duyệt cơ sở. Vui lòng thử lại.'], 500,
        )
    return redirect(url_for('admin.hosts'))


@admin_bp.route('/admin/reviews', methods=['GET'])
def reviews():
    keyword = request.args.get('q', '').strip()
    rating_filter = request.args.get('rating', '').strip()
    accommodation_text = request.args.get('accommodation_id', '').strip()
    errors = []
    if len(keyword) > 100:
        errors.append('Từ khóa không được vượt quá 100 ký tự.')
    if rating_filter not in ('', '5', '4', '3', '1-2'):
        errors.append('Bộ lọc điểm đánh giá không hợp lệ.')
    if accommodation_text and (
        not re.fullmatch(r'[0-9]{1,10}', accommodation_text)
        or int(accommodation_text) < 1
    ):
        errors.append('Mã cơ sở lưu trú không hợp lệ.')

    summary = db.session.execute(text("""
        SELECT COUNT(*) AS total, AVG(rating) AS average_rating FROM Reviews
    """)).mappings().one()
    accommodations = db.session.execute(text("""
        SELECT accommodation_id, name FROM Accommodations
        ORDER BY name, accommodation_id
    """)).mappings().all()
    if errors:
        return render_template(
            'admin/reviews_moderation.html', view='list', reviews=[],
            summary=summary, accommodations=accommodations, keyword=keyword,
            rating_filter=rating_filter, accommodation_text=accommodation_text,
            errors=errors,
        ), 400

    params = {}
    conditions = []
    if keyword:
        conditions.append("""(
            LOWER(COALESCE(r.comment, '')) LIKE :keyword
            OR LOWER(COALESCE(u.full_name, '')) LIKE :keyword
            OR LOWER(COALESCE(u.email, '')) LIKE :keyword
            OR LOWER(COALESCE(a.name, '')) LIKE :keyword
        )""")
        params['keyword'] = f'%{keyword.lower()}%'
    if rating_filter:
        if rating_filter == '1-2':
            conditions.append('r.rating BETWEEN :rating_min AND :rating_max')
            params.update(rating_min=1, rating_max=2)
        else:
            conditions.append('r.rating = :rating')
            params['rating'] = int(rating_filter)
    if accommodation_text:
        conditions.append('r.accommodation_id = :accommodation_id')
        params['accommodation_id'] = int(accommodation_text)
    where_clause = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    rows = db.session.execute(text("""
        SELECT r.review_id, r.booking_id, r.customer_id, r.accommodation_id,
               r.rating, r.comment, r.created_at,
               u.full_name AS customer_name, u.email AS customer_email,
               a.name AS accommodation_name
        FROM Reviews r
        LEFT JOIN Users u ON u.user_id = r.customer_id
        LEFT JOIN Accommodations a ON a.accommodation_id = r.accommodation_id
    """ + where_clause + " ORDER BY r.created_at DESC, r.review_id DESC"), params).mappings().all()
    return render_template(
        'admin/reviews_moderation.html', view='list', reviews=rows,
        summary=summary, accommodations=accommodations, keyword=keyword,
        rating_filter=rating_filter, accommodation_text=accommodation_text,
        errors=[],
    )


@admin_bp.route('/admin/reviews/<int:review_id>', methods=['GET'])
def review_detail(review_id):
    review = db.session.execute(text("""
        SELECT r.review_id, r.booking_id, r.customer_id, r.accommodation_id,
               r.rating, r.comment, r.images, r.created_at,
               u.full_name AS customer_name, u.email AS customer_email,
               a.name AS accommodation_name, a.address AS accommodation_address,
               b.room_id, b.check_in_date, b.check_out_date,
               b.total_price, b.status AS booking_status
        FROM Reviews r
        LEFT JOIN Users u ON u.user_id = r.customer_id
        LEFT JOIN Accommodations a ON a.accommodation_id = r.accommodation_id
        LEFT JOIN Bookings b ON b.booking_id = r.booking_id
        WHERE r.review_id = :review_id
    """), {'review_id': review_id}).mappings().first()
    if review is None:
        abort(404)
    return render_template('admin/reviews_moderation.html', view='detail', review=review)


@admin_bp.route('/admin/reports', methods=['GET'])
def reports():
    start_text = request.args.get('start_date', '').strip()
    end_text = request.args.get('end_date', '').strip()
    status_filter = request.args.get('status', '').strip()
    accommodation_text = request.args.get('accommodation_id', '').strip()
    room_text = request.args.get('room_id', '').strip()

    status_options = db.session.execute(text("""
        SELECT DISTINCT status FROM Bookings ORDER BY status
    """)).scalars().all()
    accommodations = db.session.execute(text("""
        SELECT accommodation_id, name FROM Accommodations ORDER BY name, accommodation_id
    """)).mappings().all()
    rooms = db.session.execute(text("""
        SELECT r.room_id, r.room_name, a.name AS accommodation_name
        FROM Rooms r JOIN Accommodations a
          ON a.accommodation_id = r.accommodation_id
        ORDER BY a.name, r.room_name, r.room_id
    """)).mappings().all()

    errors = []
    parsed_dates = {}
    for field, value, label in (
        ('start_date', start_text, 'Ngày bắt đầu'),
        ('end_date', end_text, 'Ngày kết thúc'),
    ):
        try:
            if value and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError
            parsed_dates[field] = date.fromisoformat(value) if value else None
        except ValueError:
            parsed_dates[field] = None
            errors.append(f'{label} phải có dạng YYYY-MM-DD.')
    if (parsed_dates['start_date'] and parsed_dates['end_date']
            and parsed_dates['start_date'] > parsed_dates['end_date']):
        errors.append('Ngày bắt đầu không được sau ngày kết thúc.')

    if status_filter and status_filter not in {
        '__null__' if value is None else value for value in status_options
    }:
        errors.append('Trạng thái đặt phòng không hợp lệ.')

    selected_ids = {}
    for field, value, valid_ids, label in (
        ('accommodation_id', accommodation_text,
         {row['accommodation_id'] for row in accommodations}, 'Cơ sở lưu trú'),
        ('room_id', room_text, {row['room_id'] for row in rooms}, 'Phòng'),
    ):
        if not value:
            selected_ids[field] = None
            continue
        try:
            selected_ids[field] = int(value)
        except ValueError:
            selected_ids[field] = None
        if selected_ids[field] not in valid_ids:
            errors.append(f'{label} không hợp lệ.')

    summary = None
    daily_rows = []
    status_rows = []
    accommodation_rows = []
    room_rows = []
    if not errors:
        params = {
            'start_date': parsed_dates['start_date'],
            'end_date': parsed_dates['end_date'],
            'status': status_filter or None,
            'accommodation_id': selected_ids['accommodation_id'],
            'room_id': selected_ids['room_id'],
        }
        booking_scope = """
            FROM Bookings b
            JOIN Rooms r ON r.room_id = b.room_id
            JOIN Accommodations a ON a.accommodation_id = r.accommodation_id
            WHERE b.created_at IS NOT NULL
              AND (:start_date IS NULL OR b.created_at >= :start_date)
              AND (:end_date IS NULL OR DATE(b.created_at) <= :end_date)
              AND (:status IS NULL OR b.status = :status
                   OR (:status = '__null__' AND b.status IS NULL))
              AND (:accommodation_id IS NULL
                   OR a.accommodation_id = :accommodation_id)
              AND (:room_id IS NULL OR r.room_id = :room_id)
        """
        summary = db.session.execute(text("""
            SELECT COUNT(*) AS booking_count,
                   COUNT(DISTINCT b.customer_id) AS customer_count,
                   COUNT(DISTINCT a.accommodation_id) AS accommodation_count,
                   COUNT(DISTINCT r.room_id) AS room_count
        """ + booking_scope), params).mappings().one()
        daily_rows = db.session.execute(text("""
            SELECT DATE(b.created_at) AS report_day, COUNT(*) AS total
        """ + booking_scope + """
            GROUP BY DATE(b.created_at) ORDER BY report_day
        """), params).mappings().all()
        status_rows = db.session.execute(text("""
            SELECT b.status, COUNT(*) AS total
        """ + booking_scope + """
            GROUP BY b.status ORDER BY total DESC, b.status
        """), params).mappings().all()
        accommodation_rows = db.session.execute(text("""
            SELECT a.accommodation_id, a.name, COUNT(*) AS total
        """ + booking_scope + """
            GROUP BY a.accommodation_id, a.name ORDER BY total DESC, a.name
        """), params).mappings().all()
        room_rows = db.session.execute(text("""
            SELECT r.room_id, r.room_name, a.accommodation_id,
                   a.name AS accommodation_name, COUNT(*) AS total
        """ + booking_scope + """
            GROUP BY r.room_id, r.room_name, a.accommodation_id, a.name
            ORDER BY total DESC, a.name, r.room_name
        """), params).mappings().all()

    chart_max = max((row['total'] for row in daily_rows), default=0)
    daily_chart = [
        {'day': str(row['report_day']), 'total': row['total'],
         'percent': round(row['total'] * 100 / chart_max)}
        for row in daily_rows
    ] if chart_max else []
    return render_template(
        'admin/system_reports.html', start_date=start_text, end_date=end_text,
        status_filter=status_filter, accommodation_filter=accommodation_text,
        room_filter=room_text, status_options=status_options,
        accommodations=accommodations, rooms=rooms, errors=errors,
        summary=summary, daily_chart=daily_chart, status_rows=status_rows,
        accommodation_rows=accommodation_rows, room_rows=room_rows,
    ), 400 if errors else 200


def _authenticated_admin_principal_id():
    """Return the user ID supplied by the project's authenticated admin session.

    Authentication is not implemented or registered in this repository yet.
    Replace this return only when the login flow supplies a verified principal;
    do not accept an ID from the request or assume a session key here.
    """
    return None


def _current_admin_id():
    user_id = _authenticated_admin_principal_id()
    if user_id is None:
        return None
    # Recheck the role in the database even after authentication is wired in.
    return db.session.execute(text("""
        SELECT user_id FROM Users
        WHERE user_id = :user_id AND role = :role
    """), {'user_id': user_id, 'role': 'Admin'}).scalar_one_or_none()


@admin_bp.route('/admin/notifications', methods=['GET'])
def notifications():
    user_id = _current_admin_id()
    if user_id is None:
        return render_template('admin/notifications.html', auth_unavailable=True), 403

    unread_only = request.args.get('filter') == 'unread'
    params = {'user_id': user_id}
    counts = db.session.execute(text("""
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END), 0) AS unread
        FROM Notifications WHERE user_id = :user_id
    """), params).mappings().one()
    query = """
        SELECT notification_id, title, message, is_read, created_at
        FROM Notifications WHERE user_id = :user_id
    """
    if unread_only:
        query += ' AND is_read = 0'
    query += ' ORDER BY created_at DESC, notification_id DESC'
    rows = db.session.execute(text(query), params).mappings().all()
    return render_template(
        'admin/notifications.html', auth_unavailable=False,
        notifications=rows, counts=counts, unread_only=unread_only,
    )


@admin_bp.route('/admin/notifications/<int:notification_id>/read', methods=['POST'])
def mark_notification_read(notification_id):
    user_id = _current_admin_id()
    if user_id is None:
        abort(403)
    try:
        owned_id = db.session.execute(text("""
            SELECT notification_id FROM Notifications
            WHERE notification_id = :notification_id AND user_id = :user_id
            FOR UPDATE
        """), {'notification_id': notification_id, 'user_id': user_id}).scalar_one_or_none()
        if owned_id is None:
            db.session.rollback()
            abort(404)
        db.session.execute(text("""
            UPDATE Notifications SET is_read = 1
            WHERE notification_id = :notification_id AND user_id = :user_id
        """), {'notification_id': notification_id, 'user_id': user_id})
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        abort(500)
    return redirect(url_for('admin.notifications', filter=request.form.get('filter')))


@admin_bp.route('/admin/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    user_id = _current_admin_id()
    if user_id is None:
        abort(403)
    try:
        # Lock only this admin's unread rows before updating them.
        db.session.execute(text("""
            SELECT notification_id FROM Notifications
            WHERE user_id = :user_id AND is_read = 0 FOR UPDATE
        """), {'user_id': user_id}).all()
        db.session.execute(text("""
            UPDATE Notifications SET is_read = 1
            WHERE user_id = :user_id AND is_read = 0
        """), {'user_id': user_id})
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        abort(500)
    return redirect(url_for('admin.notifications', filter=request.form.get('filter')))


def _profile_user(user_id, lock=False):
    suffix = ' FOR UPDATE' if lock and db.engine.dialect.name == 'mysql' else ''
    return db.session.execute(text("""
        SELECT user_id, full_name, email, phone, role, status, created_at
        FROM Users WHERE user_id = :user_id AND role = :role
    """ + suffix), {'user_id': user_id, 'role': 'Admin'}).mappings().first()


def _render_profile(user, values, errors=(), status=200):
    return render_template(
        'admin/profile.html', auth_unavailable=False, user=user,
        form_values=values, errors=errors,
    ), status


@admin_bp.route('/admin/profile', methods=['GET', 'POST'])
def profile():
    user_id = _current_admin_id()
    if user_id is None:
        if request.method == 'POST':
            abort(403)
        return render_template('admin/profile.html', auth_unavailable=True), 403

    user = _profile_user(user_id)
    if user is None:
        abort(403)
    if request.method == 'GET':
        values = {
            field: '' if user[field] is None else str(user[field])
            for field in USER_CONTACT_FIELDS
        }
        return _render_profile(user, values)

    values = {field: request.form.get(field, '').strip() for field in USER_CONTACT_FIELDS}
    errors = []
    if not values['full_name']:
        errors.append('Vui lòng nhập họ tên.')
    elif len(values['full_name']) > 255:
        errors.append('Họ tên không được vượt quá 255 ký tự.')
    if not values['email']:
        errors.append('Vui lòng nhập email.')
    elif len(values['email']) > 255 or not re.fullmatch(
        r'[^\s@]+@[^\s@]+\.[^\s@]+', values['email']
    ):
        errors.append('Email không hợp lệ hoặc vượt quá 255 ký tự.')
    if len(values['phone']) > 20:
        errors.append('Số điện thoại không được vượt quá 20 ký tự.')
    elif values['phone'] and (
        not re.fullmatch(r'[+()\d\s.\-]+', values['phone'])
        or not any(char.isdigit() for char in values['phone'])
    ):
        errors.append('Số điện thoại chỉ được chứa chữ số và các ký tự + ( ) . -.')
    if errors:
        return _render_profile(user, values, errors, 400)

    try:
        duplicate = db.session.execute(text("""
            SELECT user_id FROM Users
            WHERE LOWER(email) = LOWER(:email) AND user_id <> :user_id
            LIMIT 1
        """), {'email': values['email'], 'user_id': user_id}).scalar_one_or_none()
        if duplicate is not None:
            db.session.rollback()
            return _render_profile(user, values, ['Email đã được tài khoản khác sử dụng.'], 409)

        if _profile_user(user_id, lock=True) is None:
            db.session.rollback()
            abort(403)
        result = db.session.execute(text("""
            UPDATE Users SET full_name = :full_name, email = :email, phone = :phone
            WHERE user_id = :user_id AND role = :role
        """), {
            'full_name': values['full_name'], 'email': values['email'],
            'phone': values['phone'] or None, 'user_id': user_id, 'role': 'Admin',
        })
        if result.rowcount != 1:
            db.session.rollback()
            return _render_profile(user, values, ['Tài khoản quản trị đã thay đổi. Vui lòng tải lại trang.'], 409)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _render_profile(user, values, ['Email đã được tài khoản khác sử dụng.'], 409)
    except SQLAlchemyError:
        db.session.rollback()
        return _render_profile(user, values, ['Không thể cập nhật tài khoản. Vui lòng thử lại.'], 500)

    flash('Đã cập nhật thông tin cá nhân.', 'profile_success')
    return redirect(url_for('admin.profile'))
