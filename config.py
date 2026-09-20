import os

class Config:
    """Cấu hình chung cho ứng dụng Flask."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'do_an_dat_phong_danang_secret_key_2026'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:FBWIjbpQrQBmrCTBJbUXFZUIEzFMRMHW@hopper.proxy.rlwy.net:50949/railway?charset=utf8mb4'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

# ĐẢM BẢO CÓ DÒNG NÀY Ở CUỐI FILE CONFIG.PY
config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}