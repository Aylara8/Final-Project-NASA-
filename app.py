import os
import base64
import binascii
import hashlib
import secrets
import smtplib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from email.message import EmailMessage
from io import BytesIO
from flask_migrate import Migrate
from sqlalchemy import inspect, or_, text
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs):
        return False
from ai_logic import HandshakeLiveEngine

load_dotenv()

app = Flask(__name__)
app.secret_key = 'handshake_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///handshake.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads/passports'
app.config['UPLOAD_FOLDER_ITEMS'] = 'static/uploads/items'
app.config['UPLOAD_FOLDER_PROFILES'] = 'static/uploads/profiles'
app.config['MAX_CONTENT_LENGTH'] = 24 * 1024 * 1024

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
expert_executor = ThreadPoolExecutor(max_workers=4)
live_engine = HandshakeLiveEngine()
PASSWORD_RESET_TOKEN_TTL_MINUTES = 20
ADMIN_EMAIL = (os.getenv('ADMIN_EMAIL') or '').strip().lower()
ALLOW_LOCAL_RESET_LINK = os.getenv('ALLOW_LOCAL_RESET_LINK', 'true').lower() == 'true'
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'tm': 'Turkmen',
    'ru': 'Russian',
}
TRANSLATIONS = {
    'en': {
        'nav.search_placeholder': 'Search for anything...',
        'nav.marketplace': 'Marketplace',
        'nav.messages': 'Messages',
        'nav.post_item': 'Post Item',
        'nav.edit_profile': 'Edit Profile',
        'nav.my_listings': 'My Listings',
        'nav.logout': 'Log out',
        'nav.login': 'Log in',
        'nav.signup': 'Sign up',
        'lang.label': 'Language',
        'market.title': 'Find What You Need',
        'market.subtitle': 'Use keywords and location filters to narrow listings fast.',
        'market.keyword': 'Keyword',
        'market.keyword_placeholder': 'Camera, toolkit, car, apartment...',
        'market.velayat': 'Velayat',
        'market.district': 'District',
        'market.neighborhood': 'Neighborhood',
        'market.all_velayats': 'All velayats',
        'market.all_districts': 'All districts',
        'market.all_neighborhoods': 'All neighborhoods / streets',
        'market.all_streets': 'All streets / avenues',
        'market.search': 'Search',
        'market.clear': 'Clear',
        'market.showing': 'Showing {count} listing{suffix}{query_suffix}.',
        'market.no_results': 'No listings matched the current filters.',
        'auth.login_title': 'Secure Sign In',
        'auth.login_subtitle': 'Enter your credentials to access your HandShake account.',
        'auth.email_address': 'Email Address',
        'auth.password': 'Password',
        'auth.remember_me': 'Remember me',
        'auth.forgot_password': 'Forgot password?',
        'auth.secure_login': 'Secure Login',
        'auth.no_account': "Don't have an account?",
        'auth.start_kyc': 'Start KYC Verification',
        'auth.recovery_title': 'Secure Password Recovery',
        'auth.recovery_subtitle': 'This flow requires a one-time reset token. Tokens expire after 20 minutes and can be used once.',
        'auth.step1': '1. Request reset token',
        'auth.step2': '2. Reset password with token',
        'auth.email_placeholder': 'Your account email',
        'auth.generate_token': 'Generate Token',
        'auth.token_placeholder': 'One-time reset token',
        'auth.new_password': 'New password',
        'auth.confirm_new_password': 'Confirm new password',
        'auth.reset_password': 'Reset Password',
        'auth.no_email_notice': 'No email sender is configured in this app, so token delivery is handled by admin/server logs.',
        'auth.back_to_login': 'Back to',
        'auth.reset_intro': 'Enter your email and new password. If you do not have a token yet, submit once to generate one.',
        'auth.reset_token': 'Reset token',
        'auth.generate_or_reset': 'Generate Token / Reset',
        'auth.forgot_intro': 'Enter your Gmail/email and we will send a verification link.',
        'auth.send_verification': 'Send verification email',
        'auth.check_email_msg': 'If the account exists, a verification email has been sent.',
        'auth.email_service_off': 'Email service is not configured on server. Contact admin.',
        'auth.reset_from_email': 'Create new password',
        'flash.invalid_login': 'Invalid email/username or password.',
        'flash.email_required': 'Email is required.',
        'flash.new_password_len': 'New password must be at least 6 characters.',
        'flash.passwords_mismatch': 'Passwords do not match.',
        'flash.no_account_email': 'No account found with that email.',
        'flash.token_generated': 'Reset token generated: {token}. Use it within {minutes} minutes.',
        'flash.invalid_token': 'Invalid or expired reset token.',
        'flash.reset_success': 'Password reset successful. Please sign in with your new password.',
    },
    'tm': {
        'nav.search_placeholder': 'Islendik zady gozle...',
        'nav.marketplace': 'Bazar',
        'nav.messages': 'Habarlar',
        'nav.post_item': 'Haryt Gos',
        'nav.edit_profile': 'Profili Uytget',
        'nav.my_listings': 'Bildirislerim',
        'nav.logout': 'Cyk',
        'nav.login': 'Gir',
        'nav.signup': 'Hasap Ac',
        'lang.label': 'Dil',
        'market.title': 'Gerek Zadyny Tap',
        'market.subtitle': 'Netijeleri calt daraltmak ucin acar soz we yerlesis suzguclerini ulanyn.',
        'market.keyword': 'Acar soz',
        'market.keyword_placeholder': 'Kamera, gurallar, ulag, oy...',
        'market.velayat': 'Welayat',
        'market.district': 'Etrap',
        'market.neighborhood': 'Yer / koce',
        'market.all_velayats': 'Ahli welayatlar',
        'market.all_districts': 'Ahli etraplar',
        'market.all_neighborhoods': 'Ahli yerler / koceler',
        'market.all_streets': 'Ahli koceler / sayollar',
        'market.search': 'Gozle',
        'market.clear': 'Arassala',
        'market.showing': '{count} bildiris gorkezilyar{query_suffix}.',
        'market.no_results': 'Su suzguclere layyk bildiris tapylmady.',
        'auth.login_title': 'Howpsuz Giris',
        'auth.login_subtitle': 'HandShake hasabynyza girmek ucin maglumatlarynyzy girizin.',
        'auth.email_address': 'Email salgy',
        'auth.password': 'Parol',
        'auth.remember_me': 'Yatda sakla',
        'auth.forgot_password': 'Acar sozunizi unutdynyzmy?',
        'auth.secure_login': 'Howpsuz Giris',
        'auth.no_account': 'Hasabynyz yokmy?',
        'auth.start_kyc': 'KYC barlagyny basla',
        'auth.recovery_title': 'Howpsuz Parol Dikeldis',
        'auth.recovery_subtitle': 'Bu akym bir gezeklik token talap edýär. Token 20 minutda mohleti gecyar we dine bir gezek ulanylyar.',
        'auth.step1': '1. Dikeldis tokenini sora',
        'auth.step2': '2. Token bilen paroly tazele',
        'auth.email_placeholder': 'Hasabynyzyn emaili',
        'auth.generate_token': 'Token Doret',
        'auth.token_placeholder': 'Bir gezeklik dikeldis tokeni',
        'auth.new_password': 'Taze parol',
        'auth.confirm_new_password': 'Taze paroly tassyklap',
        'auth.reset_password': 'Paroly Tazele',
        'auth.no_email_notice': 'Bu programmada email iberis yok, token serwer loglary arkaly berilyar.',
        'auth.back_to_login': 'Yza dolan',
        'auth.reset_intro': 'Email we taze paroly girizin. Token yok bolsa, ilki token doretmek ucin ugrat.',
        'auth.reset_token': 'Dikeldis tokeni',
        'auth.generate_or_reset': 'Token Doret / Tazele',
        'auth.forgot_intro': 'Gmail/email salgyňyzy giriziň, barlag salgysy ugradylar.',
        'auth.send_verification': 'Barlag emailini ugrat',
        'auth.check_email_msg': 'Hasap bar bolsa, barlag emaili ugradyldy.',
        'auth.email_service_off': 'Serwerde email hyzmaty sazlanmady. Admin bilen habarlaşyň.',
        'auth.reset_from_email': 'Taze parol doret',
        'flash.invalid_login': 'Email/ulanyjy ady ya-da parol nadogry.',
        'flash.email_required': 'Email hokmanydyr.',
        'flash.new_password_len': 'Taze parol azyndan 6 nyshan bolmaly.',
        'flash.passwords_mismatch': 'Parollar gabat gelenok.',
        'flash.no_account_email': 'Bu email bilen hasap tapylmady.',
        'flash.token_generated': 'Token doredildi: {token}. Ony {minutes} minut icinde ulanyn.',
        'flash.invalid_token': 'Token nadogry ya-da mohleti gecdi.',
        'flash.reset_success': 'Parol ustunlikli tazelendi. Taze parol bilen girin.',
    },
    'ru': {
        'nav.search_placeholder': 'Искать что угодно...',
        'nav.marketplace': 'Маркетплейс',
        'nav.messages': 'Сообщения',
        'nav.post_item': 'Добавить товар',
        'nav.edit_profile': 'Редактировать профиль',
        'nav.my_listings': 'Мои объявления',
        'nav.logout': 'Выйти',
        'nav.login': 'Войти',
        'nav.signup': 'Регистрация',
        'lang.label': 'Язык',
        'market.title': 'Найдите то, что нужно',
        'market.subtitle': 'Используйте ключевые слова и фильтры по локации для быстрого поиска.',
        'market.keyword': 'Ключевое слово',
        'market.keyword_placeholder': 'Камера, инструменты, машина, квартира...',
        'market.velayat': 'Велаят',
        'market.district': 'Этрап',
        'market.neighborhood': 'Район / улица',
        'market.all_velayats': 'Все велаяты',
        'market.all_districts': 'Все этрапы',
        'market.all_neighborhoods': 'Все районы / улицы',
        'market.all_streets': 'Все улицы / проспекты',
        'market.search': 'Поиск',
        'market.clear': 'Сброс',
        'market.showing': 'Показано {count} объявлений{query_suffix}.',
        'market.no_results': 'По текущим фильтрам ничего не найдено.',
        'auth.login_title': 'Безопасный вход',
        'auth.login_subtitle': 'Введите данные для входа в аккаунт HandShake.',
        'auth.email_address': 'Email адрес',
        'auth.password': 'Пароль',
        'auth.remember_me': 'Запомнить меня',
        'auth.forgot_password': 'Забыли пароль?',
        'auth.secure_login': 'Безопасный вход',
        'auth.no_account': 'Нет аккаунта?',
        'auth.start_kyc': 'Начать KYC проверку',
        'auth.recovery_title': 'Безопасное восстановление пароля',
        'auth.recovery_subtitle': 'Этот процесс требует одноразовый токен. Токен действует 20 минут и используется один раз.',
        'auth.step1': '1. Запросите токен восстановления',
        'auth.step2': '2. Сбросьте пароль с токеном',
        'auth.email_placeholder': 'Email вашего аккаунта',
        'auth.generate_token': 'Создать токен',
        'auth.token_placeholder': 'Одноразовый токен',
        'auth.new_password': 'Новый пароль',
        'auth.confirm_new_password': 'Подтвердите новый пароль',
        'auth.reset_password': 'Сбросить пароль',
        'auth.no_email_notice': 'Почтовый сервис не настроен, поэтому токен передается через логи сервера/админа.',
        'auth.back_to_login': 'Назад к',
        'auth.reset_intro': 'Введите email и новый пароль. Если токена нет, отправьте форму один раз для генерации.',
        'auth.reset_token': 'Токен сброса',
        'auth.generate_or_reset': 'Создать токен / Сбросить',
        'auth.forgot_intro': 'Введите Gmail/email, и мы отправим ссылку подтверждения.',
        'auth.send_verification': 'Отправить письмо',
        'auth.check_email_msg': 'Если аккаунт существует, письмо подтверждения отправлено.',
        'auth.email_service_off': 'Почтовый сервис не настроен на сервере. Обратитесь к администратору.',
        'auth.reset_from_email': 'Создать новый пароль',
        'flash.invalid_login': 'Неверный email/логин или пароль.',
        'flash.email_required': 'Требуется email.',
        'flash.new_password_len': 'Новый пароль должен быть не менее 6 символов.',
        'flash.passwords_mismatch': 'Пароли не совпадают.',
        'flash.no_account_email': 'Аккаунт с таким email не найден.',
        'flash.token_generated': 'Токен создан: {token}. Используйте его в течение {minutes} минут.',
        'flash.invalid_token': 'Неверный или просроченный токен.',
        'flash.reset_success': 'Пароль успешно обновлен. Войдите с новым паролем.',
    },
}

LOCALIZED_UI = {
    'dashboard.page_title': {'en': 'Home', 'tm': 'Baş sahypa', 'ru': 'Главная'},
    'dashboard.hero_title': {'en': 'Rent everything.', 'tm': 'Islendik zady kärendesine al.', 'ru': 'Арендуйте что угодно.'},
    'dashboard.hero_accent': {'en': 'One HandShake away.', 'tm': 'Bir HandShake aralykda.', 'ru': 'Всего в одном HandShake.'},
    'dashboard.hero_text': {
        'en': 'A secure peer-to-peer rental platform for hobbies, cars, homes, and tools with KYC-backed trust.',
        'tm': 'Hobbi, ulag, ýaşaýyş jaýy we gurallar üçin KYC bilen güýçlendirilen ynamly, howpsuz kärende platformasy.',
        'ru': 'Безопасная P2P-платформа аренды для хобби, авто, жилья и инструментов с проверкой KYC.',
    },
    'dashboard.verified_title': {'en': 'Verified KYC', 'tm': 'Tassyklanan KYC', 'ru': 'Проверенный KYC'},
    'dashboard.verified_text': {
        'en': 'Every member is verified with identity documents to keep the community safer.',
        'tm': 'Jemgyýeti has howpsuz etmek üçin her ulanyjynyň şahsyýeti resminamalar arkaly barlanýar.',
        'ru': 'Каждый пользователь проходит проверку документов, чтобы сообщество было безопаснее.',
    },
    'dashboard.earn_title': {'en': 'Earn from Assets', 'tm': 'Emläkden girdeji al', 'ru': 'Зарабатывайте на активах'},
    'dashboard.earn_text': {
        'en': 'Turn idle items like cameras, consoles, or tools into extra income.',
        'tm': 'Boş duran kameraňyzy, konsolyňyzy ýa-da gurallaryňyzy goşmaça girdejä öwüriň.',
        'ru': 'Превратите простаивающие камеры, консоли и инструменты в дополнительный доход.',
    },
    'dashboard.eco_title': {'en': 'Eco-Friendly', 'tm': 'Ekologiýa taýdan peýdaly', 'ru': 'Экологично'},
    'dashboard.eco_text': {
        'en': 'Renting instead of buying reduces waste and supports a more sustainable economy.',
        'tm': 'Satyn almagyň ýerine kärendesine almak galyndylary azaldýar we durnukly ykdysadyýeti goldaýar.',
        'ru': 'Аренда вместо покупки сокращает отходы и поддерживает устойчивую экономику.',
    },
    'dashboard.banner_title': {'en': 'Safe. Secure. Sustainable.', 'tm': 'Howpsuz. Ynamly. Durnukly.', 'ru': 'Безопасно. Надежно. Устойчиво.'},
    'dashboard.banner_text': {'en': 'The future of sharing is here.', 'tm': 'Paýlaşmagyň geljegi şu ýerde.', 'ru': 'Будущее совместного пользования уже здесь.'},
    'upload.page_title': {'en': 'Post Item', 'tm': 'Haryt goş', 'ru': 'Добавить товар'},
    'upload.title': {'en': 'List your item', 'tm': 'Harydyňyzy ýerleşdiriň', 'ru': 'Разместите свой товар'},
    'upload.subtitle': {'en': 'Fill in the details to start renting.', 'tm': 'Kärendä bermek üçin maglumatlary dolduryň.', 'ru': 'Заполните данные, чтобы начать сдавать в аренду.'},
    'upload.what_listing': {'en': 'What are you listing?', 'tm': 'Näme ýerleşdirýärsiňiz?', 'ru': 'Что вы размещаете?'},
    'upload.title_placeholder': {'en': 'e.g. PlayStation 5, Canon EOS R5', 'tm': 'mysal üçin: PlayStation 5, Canon EOS R5', 'ru': 'например: PlayStation 5, Canon EOS R5'},
    'upload.category': {'en': 'Category', 'tm': 'Kategoriýa', 'ru': 'Категория'},
    'upload.type': {'en': 'Type', 'tm': 'Görnüşi', 'ru': 'Тип'},
    'upload.price': {'en': 'Price (TMT)', 'tm': 'Baha (TMT)', 'ru': 'Цена (TMT)'},
    'upload.velayat_city': {'en': 'Velayat / City', 'tm': 'Welaýat / şäher', 'ru': 'Велаят / город'},
    'upload.select_velayat': {'en': 'Select velayat', 'tm': 'Welaýaty saýlaň', 'ru': 'Выберите велаят'},
    'upload.district': {'en': 'District', 'tm': 'Etrap', 'ru': 'Этрап'},
    'upload.select_district': {'en': 'Select district', 'tm': 'Etraby saýlaň', 'ru': 'Выберите этрап'},
    'upload.neighborhood': {'en': 'Neighborhood / Street', 'tm': 'Ýer / köçe', 'ru': 'Район / улица'},
    'upload.select_neighborhood': {'en': 'Select neighborhood or street', 'tm': 'Ýeri ýa-da köçäni saýlaň', 'ru': 'Выберите район или улицу'},
    'upload.select_street': {'en': 'Select street or avenue', 'tm': 'Köçäni ýa-da şaýoly saýlaň', 'ru': 'Выберите улицу или проспект'},
    'upload.description': {'en': 'Description', 'tm': 'Düşündiriş', 'ru': 'Описание'},
    'upload.description_placeholder': {'en': 'Tell us more about the item...', 'tm': 'Haryt barada giňişleýin ýazyň...', 'ru': 'Расскажите подробнее о товаре...'},
    'upload.photo': {'en': 'Item Photo', 'tm': 'Harydyň suraty', 'ru': 'Фото товара'},
    'upload.capture': {'en': 'Capture', 'tm': 'Surata al', 'ru': 'Снять'},
    'upload.use_camera': {'en': 'Use Camera', 'tm': 'Kamerany ulan', 'ru': 'Использовать камеру'},
    'upload.file_upload': {'en': 'Upload File', 'tm': 'Faýl ýükläň', 'ru': 'Загрузить файл'},
    'upload.change_photo': {'en': 'Change Photo', 'tm': 'Suraty çalyş', 'ru': 'Изменить фото'},
    'upload.submit': {'en': 'Post to Marketplace', 'tm': 'Bazara ýerleşdir', 'ru': 'Опубликовать в маркетплейсе'},
    'upload.camera_denied': {'en': 'Camera access denied.', 'tm': 'Kamera rugsady berilmedi.', 'ru': 'Доступ к камере запрещен.'},
    'market.ai_title': {'en': 'Live Expert', 'tm': 'Göni ekspert', 'ru': 'Онлайн-эксперт'},
    'market.ai_heading': {'en': 'Ask AI about this search', 'tm': 'Bu gözleg boýunça AI-den soraň', 'ru': 'Спросите ИИ об этом поиске'},
    'market.ai_idle': {'en': 'Nothing runs until you ask.', 'tm': 'Siz sorançyňyz hiç zat işlemeýär.', 'ru': 'Пока вы не спросите, ничего не запускается.'},
    'market.ai_learn': {'en': 'Learn these results', 'tm': 'Şu netijeleri öwren', 'ru': 'Разобрать результаты'},
    'market.ai_setup': {'en': 'Setup help', 'tm': 'Gurnamak boýunça kömek', 'ru': 'Помощь с настройкой'},
    'market.ai_input': {'en': 'Ask about setup, inspection, or usage', 'tm': 'Gurnama, barlag ýa-da ulanyş barada soraň', 'ru': 'Спросите о настройке, проверке или использовании'},
    'market.ai_button': {'en': 'Ask AI', 'tm': 'AI-den sora', 'ru': 'Спросить ИИ'},
    'market.ai_launcher': {'en': 'AI chat', 'tm': 'AI çat', 'ru': 'Чат с ИИ'},
    'market.category_all': {'en': 'All Items', 'tm': 'Ähli harytlar', 'ru': 'Все товары'},
    'market.filters': {'en': 'Filters', 'tm': 'Süzgüçler', 'ru': 'Фильтры'},
    'market.filters_hint': {'en': 'Location filters stay hidden until you open them.', 'tm': 'Ýerleşiş süzgüçleri siz açýança gizlin galýar.', 'ru': 'Фильтры местоположения скрыты, пока вы их не откроете.'},
    'market.close_filters': {'en': 'Close filters', 'tm': 'Süzgüçleri ýap', 'ru': 'Закрыть фильтры'},
    'market.per_hour': {'en': 'hr', 'tm': 'sagat', 'ru': 'час'},
    'market.per_day': {'en': 'day', 'tm': 'gün', 'ru': 'день'},
    'detail.ai_heading': {'en': 'Ask how to learn or set it up', 'tm': 'Öwrenmek ýa-da gurnamak barada soraň', 'ru': 'Спросите, как освоить или настроить'},
    'detail.ai_learn': {'en': 'Learn this item', 'tm': 'Şu harydy öwren', 'ru': 'Изучить товар'},
    'detail.ai_setup': {'en': 'How to set it up', 'tm': 'Nädip gurnamaly', 'ru': 'Как настроить'},
    'detail.hosted_by': {'en': 'Hosted by', 'tm': 'Eýesi', 'ru': 'Владелец'},
    'detail.unknown_owner': {'en': 'Hosted by Unknown user', 'tm': 'Eýesi näbelli ulanyjy', 'ru': 'Владелец: неизвестный пользователь'},
    'detail.owner_unavailable': {'en': 'Owner account is unavailable', 'tm': 'Eýesiniň hasaby elýeterli däl', 'ru': 'Аккаунт владельца недоступен'},
    'detail.duration': {'en': 'Duration', 'tm': 'Möhlet', 'ru': 'Длительность'},
    'detail.total': {'en': 'Total', 'tm': 'Jemi', 'ru': 'Итого'},
    'detail.rent_now': {'en': 'Rent Now', 'tm': 'Häzir kärendesine al', 'ru': 'Арендовать'},
    'detail.buy_now': {'en': 'Buy Now', 'tm': 'Häzir satyn al', 'ru': 'Купить'},
    'detail.negotiate': {'en': 'Negotiate Price', 'tm': 'Bahany ylalaş', 'ru': 'Торговаться'},
    'detail.proposed_price': {'en': 'Proposed Price (TMT)', 'tm': 'Teklip edilýän baha (TMT)', 'ru': 'Предлагаемая цена (TMT)'},
    'detail.send_offer': {'en': 'Send Offer', 'tm': 'Teklip ugrat', 'ru': 'Отправить предложение'},
    'detail.open_chat': {'en': 'Open Chat', 'tm': 'Çaty aç', 'ru': 'Открыть чат'},
    'detail.request_pending': {'en': 'Request Pending', 'tm': 'Haýyş garaşylýar', 'ru': 'Запрос ожидает'},
    'detail.accept_chat_request': {'en': 'Accept Chat Request', 'tm': 'Çat haýyşyny kabul et', 'ru': 'Принять запрос чата'},
    'detail.request_chat': {'en': 'Request Chat', 'tm': 'Çat sora', 'ru': 'Запросить чат'},
    'detail.description': {'en': 'Description', 'tm': 'Düşündiriş', 'ru': 'Описание'},
    'detail.no_description': {'en': 'No description provided.', 'tm': 'Düşündiriş berilmedi.', 'ru': 'Описание не указано.'},
    'detail.reviews_title': {'en': 'Product Reviews', 'tm': 'Haryt baradaky teswirler', 'ru': 'Отзывы о товаре'},
    'detail.your_rating': {'en': 'Your Rating (1-5)', 'tm': 'Siziň bahaňyz (1-5)', 'ru': 'Ваша оценка (1-5)'},
    'detail.review_placeholder': {'en': 'Share your experience with this item...', 'tm': 'Bu haryt boýunça tejribäňizi paýlaşyň...', 'ru': 'Поделитесь впечатлением об этом товаре...'},
    'detail.submit_review': {'en': 'Submit Review', 'tm': 'Teswiri ugrat', 'ru': 'Отправить отзыв'},
    'detail.no_reviews': {'en': 'No reviews for this product yet.', 'tm': 'Bu haryt barada entek teswir ýok.', 'ru': 'Пока нет отзывов об этом товаре.'},
    'login.encryption': {'en': 'AES-256 Bit Encryption Active', 'tm': 'AES-256 bit şifrleme işjeň', 'ru': 'Шифрование AES-256 активно'},
    'register.page_title': {'en': 'KYC Registration', 'tm': 'KYC hasap açmak', 'ru': 'KYC-регистрация'},
    'register.step1_title': {'en': 'Select Your Region', 'tm': 'Sebitiňizi saýlaň', 'ru': 'Выберите регион'},
    'register.step1_desc': {'en': 'Choose the country where your passport was issued.', 'tm': 'Pasportyňyz berlen ýurdy saýlaň.', 'ru': 'Выберите страну, где выдан ваш паспорт.'},
    'register.select_country': {'en': 'Select Country', 'tm': 'Ýurdy saýlaň', 'ru': 'Выберите страну'},
    'register.continue': {'en': 'Continue', 'tm': 'Dowam et', 'ru': 'Продолжить'},
    'register.manual_verification': {'en': 'Manual Verification:', 'tm': 'El bilen barlag:', 'ru': 'Ручная проверка:'},
    'register.manual_verification_text': {'en': 'Please provide a clear photo of your passport. Our administrators will verify your identity manually.', 'tm': 'Pasportyňyzyň düşnükli suratyny ýükläň. Administratorlar şahsyýetiňizi el bilen barlar.', 'ru': 'Пожалуйста, загрузите четкое фото паспорта. Администраторы проверят вашу личность вручную.'},
    'register.preparing_document': {'en': 'Preparing document...', 'tm': 'Resminama taýýarlanýar...', 'ru': 'Подготовка документа...'},
    'register.full_name_passport': {'en': 'Full Name (as in passport)', 'tm': 'Doly ady (pasportdaky ýaly)', 'ru': 'Полное имя (как в паспорте)'},
    'register.full_name': {'en': 'Full Name', 'tm': 'Doly ady', 'ru': 'Полное имя'},
    'register.age': {'en': 'Age', 'tm': 'Ýaşy', 'ru': 'Возраст'},
    'register.matches_passport': {'en': 'Please ensure the information matches your uploaded passport exactly.', 'tm': 'Maglumatlaryň ýüklän pasportyňyz bilen doly gabat gelýändigine göz ýetiriň.', 'ru': 'Убедитесь, что данные полностью совпадают с загруженным паспортом.'},
    'register.confirm_details': {'en': 'Confirm Details', 'tm': 'Maglumatlary tassyklamak', 'ru': 'Подтвердить данные'},
    'register.agreement_title': {'en': 'HandShake Rental Agreement', 'tm': 'HandShake kärende şertnamasy', 'ru': 'Договор аренды HandShake'},
    'register.agreement_intro': {'en': 'By using HandShake, you agree to the following terms:', 'tm': 'HandShake ulanmak bilen şu şertlere razy bolýarsyňyz:', 'ru': 'Используя HandShake, вы соглашаетесь со следующими условиями:'},
    'register.agreement_item': {'en': 'Item Condition:', 'tm': 'Harydyň ýagdaýy:', 'ru': 'Состояние товара:'},
    'register.agreement_item_text': {'en': 'You must return items in the same condition as received.', 'tm': 'Harydy alan ýagdaýyňyzda yzyna gaýtarmaly.', 'ru': 'Вы должны вернуть товар в том же состоянии, в котором получили.'},
    'register.agreement_late': {'en': 'Late Fees:', 'tm': 'Giçikme jerimesi:', 'ru': 'Штраф за просрочку:'},
    'register.agreement_late_text': {'en': 'A late fee of 15% per day will be applied to delayed returns.', 'tm': 'Giç tabşyrylan haryt üçin her gün 15% jerime ulanylýar.', 'ru': 'За просроченный возврат взимается штраф 15% в день.'},
    'register.agreement_damage': {'en': 'Damages:', 'tm': 'Zeperler:', 'ru': 'Повреждения:'},
    'register.agreement_damage_text': {'en': 'You are fully responsible for any damages incurred during the rental period.', 'tm': 'Kärende döwründe dörän ähli zeperler üçin doly jogapkär siz.', 'ru': 'Вы полностью отвечаете за любой ущерб в период аренды.'},
    'register.agreement_verify': {'en': 'Verification:', 'tm': 'Barlag:', 'ru': 'Проверка:'},
    'register.agreement_verify_text': {'en': 'You confirm that all identity documents provided are genuine.', 'tm': 'Berlen ähli şahsyýet resminamalarynyň hakykylygyny tassyklaýarsyňyz.', 'ru': 'Вы подтверждаете подлинность всех предоставленных документов.'},
    'register.agreement_outro': {'en': 'Failure to comply with these rules will result in immediate account suspension and potential legal action.', 'tm': 'Bu düzgünleriň bozulmagy hasabyň derrew togtadylmagyna we kanuny çäreleriň görülmegine getirip biler.', 'ru': 'Нарушение этих правил приведет к немедленной блокировке аккаунта и возможным юридическим мерам.'},
    'register.verification_question': {'en': 'Verification Question: What is the late fee percentage mentioned above?', 'tm': 'Barlag soragy: Ýokarda görkezilen giçikme göterimi näçe?', 'ru': 'Проверочный вопрос: какой процент штрафа за просрочку указан выше?'},
    'register.answer_placeholder': {'en': 'Type the percentage (e.g. 50%)', 'tm': 'Göterimi ýazyň (mysal üçin 50%)', 'ru': 'Введите процент (например, 50%)'},
    'register.accept_sign': {'en': 'Accept & Sign', 'tm': 'Kabul et we gol çek', 'ru': 'Принять и подписать'},
    'register.finish': {'en': 'Finish Registration', 'tm': 'Hasaby tamamlap döret', 'ru': 'Завершить регистрацию'},
    'register.have_account': {'en': 'Already have an account?', 'tm': 'Hasabyňyz eýýäm barmy?', 'ru': 'Уже есть аккаунт?'},
    'register.passport_kyc': {'en': 'Passport KYC', 'tm': 'Pasport KYC', 'ru': 'Паспортный KYC'},
    'register.passport_photo': {'en': "Take a clear photo of your passport's main page.", 'tm': 'Pasportyň esasy sahypasynyň düşnükli suratyny alyň.', 'ru': 'Сделайте четкое фото основной страницы паспорта.'},
    'register.personal_details': {'en': 'Personal Details', 'tm': 'Şahsy maglumatlar', 'ru': 'Личные данные'},
    'register.personal_details_desc': {'en': 'Enter the information as it appears on your document.', 'tm': 'Maglumatlary resminamadaky ýaly giriziň.', 'ru': 'Введите данные так, как они указаны в документе.'},
    'register.legal_agreement': {'en': 'Legal Agreement', 'tm': 'Kanuny ylalaşyk', 'ru': 'Юридическое соглашение'},
    'register.legal_agreement_desc': {'en': 'Please read the rental contract carefully.', 'tm': 'Kärende şertnamasyny üns bilen okaň.', 'ru': 'Пожалуйста, внимательно прочитайте договор аренды.'},
    'register.create_account': {'en': 'Create Account', 'tm': 'Hasap döret', 'ru': 'Создать аккаунт'},
    'register.create_account_desc': {'en': 'Set your login credentials to finish.', 'tm': 'Tamamlamak üçin giriş maglumatlaryny düzüň.', 'ru': 'Укажите данные для входа, чтобы завершить.'},
    'register.fill_all': {'en': 'Please fill in all details.', 'tm': 'Ähli maglumatlary dolduryň.', 'ru': 'Пожалуйста, заполните все данные.'},
    'register.incorrect_answer': {'en': 'Incorrect answer. Please read the contract carefully to find the late fee percentage.', 'tm': 'Jogap nädogry. Giçikme göterimini tapmak üçin şertnamany üns bilen okaň.', 'ru': 'Неверный ответ. Внимательно прочитайте договор, чтобы найти процент штрафа.'},
    'profile.edit_title': {'en': 'Edit Profile', 'tm': 'Profili üýtget', 'ru': 'Редактировать профиль'},
    'profile.edit_subtitle': {'en': 'Update your photo and personal details.', 'tm': 'Suratyňyzy we şahsy maglumatlaryňyzy täzeläň.', 'ru': 'Обновите фото и личные данные.'},
    'profile.profile_picture': {'en': 'Profile Picture', 'tm': 'Profil suraty', 'ru': 'Фото профиля'},
    'profile.camera': {'en': 'Camera', 'tm': 'Kamera', 'ru': 'Камера'},
    'profile.upload': {'en': 'Upload', 'tm': 'Ýükle', 'ru': 'Загрузить'},
    'profile.full_name': {'en': 'Full Name', 'tm': 'Doly ady', 'ru': 'Полное имя'},
    'profile.location_city': {'en': 'Location (City)', 'tm': 'Ýerleşýän ýeri (şäher)', 'ru': 'Местоположение (город)'},
    'profile.about_you': {'en': 'About You (Bio)', 'tm': 'Özüňiz barada (bio)', 'ru': 'О себе (био)'},
    'profile.bio_placeholder': {'en': 'Tell the community about yourself...', 'tm': 'Jemgyýetçilige özüňiz barada ýazyň...', 'ru': 'Расскажите сообществу о себе...'},
    'profile.save_changes': {'en': 'Save Changes', 'tm': 'Üýtgeşmeleri ýatda sakla', 'ru': 'Сохранить изменения'},
    'profile.cancel': {'en': 'Cancel', 'tm': 'Ýatyr', 'ru': 'Отмена'},
    'profile.page_title': {'en': 'Profile', 'tm': 'Profil', 'ru': 'Профиль'},
    'profile.unknown_location': {'en': 'Unknown location', 'tm': 'Näbelli ýer', 'ru': 'Неизвестное местоположение'},
    'profile.listings_count': {'en': 'listings', 'tm': 'bildiriş', 'ru': 'объявления'},
    'profile.rating': {'en': 'Rating', 'tm': 'Baha', 'ru': 'Рейтинг'},
    'profile.kyc_verified': {'en': 'KYC Verified', 'tm': 'KYC tassyklandy', 'ru': 'KYC подтвержден'},
    'profile.unblock': {'en': 'Unblock', 'tm': 'Blokdan çykarmak', 'ru': 'Разблокировать'},
    'profile.you_blocked': {'en': 'You are blocked', 'tm': 'Siz bloklanypsyňyz', 'ru': 'Вы заблокированы'},
    'profile.send_message': {'en': 'Send Message', 'tm': 'Habar ugrat', 'ru': 'Отправить сообщение'},
    'profile.accept_request': {'en': 'Accept Request', 'tm': 'Haýyşy kabul et', 'ru': 'Принять запрос'},
    'profile.decline': {'en': 'Decline', 'tm': 'Ret et', 'ru': 'Отклонить'},
    'profile.request_chat': {'en': 'Request Chat', 'tm': 'Çat sora', 'ru': 'Запросить чат'},
    'profile.block': {'en': 'Block', 'tm': 'Blokla', 'ru': 'Заблокировать'},
    'profile.about': {'en': 'About', 'tm': 'Barada', 'ru': 'О пользователе'},
    'profile.default_bio': {'en': "This user is a proud member of the HandShake community but hasn't written a bio yet.", 'tm': 'Bu ulanyjy HandShake jemgyýetiniň agzasy, ýöne entek bio ýazmady.', 'ru': 'Этот пользователь является участником сообщества HandShake, но пока не добавил описание.'},
    'profile.service_agreement': {'en': 'Service Agreement', 'tm': 'Hyzmat ylalaşygy', 'ru': 'Сервисное соглашение'},
    'profile.important': {'en': 'Important:', 'tm': 'Möhüm:', 'ru': 'Важно:'},
    'profile.commission_notice': {'en': 'HandShake charges a 5% commission on every successful rental transaction. By requesting this chat, you agree to these terms.', 'tm': 'HandShake her üstünlikli kärende geleşigi üçin 5% hyzmat tölegini alýar. Bu çaty soramak bilen şol şertlere razy bolýarsyňyz.', 'ru': 'HandShake взимает 5% комиссии с каждой успешной сделки аренды. Запрашивая этот чат, вы соглашаетесь с этими условиями.'},
    'profile.type_i_read': {'en': 'Type "I READ" to confirm:', 'tm': 'Tassyklamak üçin "I READ" ýazyň:', 'ru': 'Введите "I READ" для подтверждения:'},
    'profile.confirm_request': {'en': 'Confirm & Request', 'tm': 'Tassykla we sora', 'ru': 'Подтвердить и запросить'},
    'profile.pending_requests': {'en': 'Pending Chat Requests', 'tm': 'Garaşylýan çat haýyşlary', 'ru': 'Ожидающие запросы чата'},
    'profile.waiting': {'en': 'waiting', 'tm': 'garaşýar', 'ru': 'ожидают'},
    'profile.listings': {'en': 'Listings', 'tm': 'Bildirişler', 'ru': 'Объявления'},
    'profile.items_total': {'en': 'items total', 'tm': 'haryt jemi', 'ru': 'товаров всего'},
    'profile.no_items': {'en': 'No items listed yet.', 'tm': 'Entäk hiç hili haryt ýerleşdirilmedi.', 'ru': 'Пока нет размещенных товаров.'},
    'profile.incoming_offers': {'en': 'Incoming Offers (Items you own)', 'tm': 'Gelýän teklipler (öz harytlaryňyz)', 'ru': 'Входящие предложения (ваши товары)'},
    'profile.wants_rent': {'en': 'wants to rent', 'tm': 'kärendesine almak isleýär', 'ru': 'хочет арендовать'},
    'profile.offer': {'en': 'Offer', 'tm': 'Teklip', 'ru': 'Предложение'},
    'profile.accept_qr': {'en': 'Accept & Give QR', 'tm': 'Kabul et we QR ber', 'ru': 'Принять и показать QR'},
    'profile.show_qr': {'en': 'Show QR Code', 'tm': 'QR kody görkez', 'ru': 'Показать QR-код'},
    'profile.cancel_deal': {'en': 'Cancel Deal', 'tm': 'Ylalaşygy ýatyr', 'ru': 'Отменить сделку'},
    'profile.no_incoming_offers': {'en': 'No incoming offers yet.', 'tm': 'Entäk gelýän teklip ýok.', 'ru': 'Пока нет входящих предложений.'},
    'profile.sent_offers': {'en': 'My Sent Offers', 'tm': 'Ugradan tekliplerim', 'ru': 'Мои отправленные предложения'},
    'profile.offering_for': {'en': 'Offering for', 'tm': 'Şu zat üçin teklip', 'ru': 'Предложение за'},
    'profile.you_proposed': {'en': 'You proposed', 'tm': 'Siziň teklibiňiz', 'ru': 'Вы предложили'},
    'profile.pending_owner': {'en': 'Pending Owner Approval', 'tm': 'Eýesiniň tassygy garaşylýar', 'ru': 'Ожидается одобрение владельца'},
    'profile.cancel_offer': {'en': 'Cancel Offer', 'tm': 'Teklibi ýatyr', 'ru': 'Отменить предложение'},
    'profile.owner_accepted': {'en': 'Owner Accepted!', 'tm': 'Eýesi kabul etdi!', 'ru': 'Владелец принял!'},
    'profile.meet_owner': {'en': 'Meet the owner & scan their QR', 'tm': 'Eýesi bilen duşuşyň we onuň QR koduny skaneriň', 'ru': 'Встретьтесь с владельцем и отсканируйте его QR'},
    'profile.no_sent_offers': {'en': "You haven't sent any offers yet.", 'tm': 'Entäk hiç hili teklip ugratmadyňyz.', 'ru': 'Вы еще не отправляли предложений.'},
    'profile.orders_rentals': {'en': 'My Orders & Rentals', 'tm': 'Sargytlarym we kärendelerim', 'ru': 'Мои заказы и аренды'},
    'profile.status': {'en': 'Status', 'tm': 'Ýagdaý', 'ru': 'Статус'},
    'profile.renting': {'en': 'Renting', 'tm': 'Kärendede', 'ru': 'В аренде'},
    'profile.calculating': {'en': 'Calculating...', 'tm': 'Hasaplanýar...', 'ru': 'Расчет...'},
    'profile.overdue': {'en': 'OVERDUE', 'tm': 'MÖHLETI GEÇDI', 'ru': 'ПРОСРОЧЕНО'},
    'profile.left': {'en': 'left', 'tm': 'galdy', 'ru': 'осталось'},
    'profile.no_orders': {'en': "You haven't ordered anything yet.", 'tm': 'Entäk hiç zat sargyt etmediňiz.', 'ru': 'Вы еще ничего не заказывали.'},
    'profile.show_to_renter': {'en': 'Show this to Renter', 'tm': 'Muny kärende alýana görkeziň', 'ru': 'Покажите это арендатору'},
    'profile.scan_qr_notice': {'en': 'They should scan this with their phone camera to confirm the hand-off.', 'tm': 'Tabşyryşy tassyklamak üçin muny telefon kamerasy bilen skanerlemeli.', 'ru': 'Они должны отсканировать это камерой телефона, чтобы подтвердить передачу.'},
    'profile.close': {'en': 'Close', 'tm': 'Ýap', 'ru': 'Закрыть'},
    'profile.community_feedback': {'en': 'Community Feedback', 'tm': 'Jemgyýetiň pikirleri', 'ru': 'Отзывы сообщества'},
    'profile.no_reviews': {'en': 'No reviews yet.', 'tm': 'Entäk teswir ýok.', 'ru': 'Пока нет отзывов.'},
    'profile.confirm_i_read': {'en': "Please type 'I READ' to confirm.", 'tm': "Tassyklaň üçin 'I READ' ýazyň.", 'ru': "Введите 'I READ' для подтверждения."},
    'chat.page_title': {'en': 'Chat', 'tm': 'Çat', 'ru': 'Чат'},
    'chat.chats': {'en': 'Chats', 'tm': 'Çatlar', 'ru': 'Чаты'},
    'chat.requests': {'en': 'Requests', 'tm': 'Haýyşlar', 'ru': 'Запросы'},
    'chat.open_messages': {'en': 'Click to open messages', 'tm': 'Habarlary açmak üçin basyň', 'ru': 'Нажмите, чтобы открыть сообщения'},
    'chat.no_active': {'en': 'No active chats yet.', 'tm': 'Entäk işjeň çat ýok.', 'ru': 'Пока нет активных чатов.'},
    'chat.accept': {'en': 'Accept', 'tm': 'Kabul et', 'ru': 'Принять'},
    'chat.decline': {'en': 'Decline', 'tm': 'Ret et', 'ru': 'Отклонить'},
    'chat.no_requests': {'en': 'No pending requests.', 'tm': 'Garaşylýan haýyş ýok.', 'ru': 'Нет ожидающих запросов.'},
    'chat.active_now': {'en': 'Active now', 'tm': 'Häzir işjeň', 'ru': 'Сейчас в сети'},
    'chat.view_profile': {'en': 'View Profile', 'tm': 'Profili gör', 'ru': 'Посмотреть профиль'},
    'chat.write_message': {'en': 'Write a message...', 'tm': 'Habar ýazyň...', 'ru': 'Напишите сообщение...'},
    'chat.your_messages': {'en': 'Your Messages', 'tm': 'Siziň habarlaryňyz', 'ru': 'Ваши сообщения'},
    'chat.select_chat': {'en': 'Select a chat from the left to start messaging or accept new requests.', 'tm': 'Habarlaşmagy başlamak ýa-da täze haýyşlary kabul etmek üçin çepden çaty saýlaň.', 'ru': 'Выберите чат слева, чтобы начать переписку или принять новые запросы.'},
    'payment.page_title': {'en': 'Secure Checkout', 'tm': 'Howpsuz töleg', 'ru': 'Безопасная оплата'},
    'payment.select_method': {'en': 'Select Payment Method', 'tm': 'Töleg usulyny saýlaň', 'ru': 'Выберите способ оплаты'},
    'payment.cardholder': {'en': 'Cardholder Name', 'tm': 'Kart eýesiniň ady', 'ru': 'Имя владельца карты'},
    'payment.cardholder_placeholder': {'en': 'Full Name on Card', 'tm': 'Kartdaky doly ady', 'ru': 'Полное имя на карте'},
    'payment.card_number': {'en': 'Card Number', 'tm': 'Kart belgisi', 'ru': 'Номер карты'},
    'payment.expiration': {'en': 'Expiration Date', 'tm': 'Möhleti', 'ru': 'Срок действия'},
    'payment.insufficient': {'en': 'Insufficient Balance', 'tm': 'Balans ýeterlik däl', 'ru': 'Недостаточно средств'},
    'payment.pay': {'en': 'Pay', 'tm': 'Töle', 'ru': 'Оплатить'},
    'payment.encrypted': {'en': 'Your payment data is encrypted and secure.', 'tm': 'Töleg maglumatlaryňyz şifrlenen we howpsuz saklanýar.', 'ru': 'Ваши платежные данные зашифрованы и защищены.'},
    'payment.summary': {'en': 'Order Summary', 'tm': 'Sargyt gysgaça mazmuny', 'ru': 'Сводка заказа'},
    'payment.by': {'en': 'by', 'tm': 'eýesi', 'ru': 'владелец'},
    'payment.base_rent': {'en': 'Base Rent', 'tm': 'Esasy kärende', 'ru': 'Базовая аренда'},
    'payment.fee': {'en': 'HandShake Fee (5%)', 'tm': 'HandShake hyzmat tölegi (5%)', 'ru': 'Комиссия HandShake (5%)'},
    'payment.deposit': {'en': 'Security Deposit', 'tm': 'Gorag goýumy', 'ru': 'Гарантийный депозит'},
    'payment.deposit_refund': {'en': 'Refundable upon return', 'tm': 'Gaýtarylanyňyzda yzyna berilýär', 'ru': 'Возвращается после возврата'},
    'payment.total': {'en': 'Total to Pay', 'tm': 'Tölemeli jemi', 'ru': 'Итого к оплате'},
    'payment.wallet': {'en': 'YOUR WALLET', 'tm': 'SIZIŇ GAPJYGYŇYZ', 'ru': 'ВАШ КОШЕЛЕК'},
    'payment.cancel_back': {'en': 'Cancel and go back', 'tm': 'Ýatyryp yza gaýdyň', 'ru': 'Отменить и вернуться'},
    'flash.image_too_large': {'en': 'The uploaded image is too large. Please use a smaller or compressed image.', 'tm': 'Ýüklenen surat örän uly. Has kiçi ýa-da gysylan surat ulanyň.', 'ru': 'Загруженное изображение слишком большое. Используйте более маленькое или сжатое изображение.'},
    'flash.sign_in_switch': {'en': 'Sign in below to switch to another account.', 'tm': 'Başga hasaba geçmek üçin aşakdan giriň.', 'ru': 'Войдите ниже, чтобы переключиться на другой аккаунт.'},
    'flash.select_region': {'en': 'Please select your region.', 'tm': 'Sebitiňizi saýlaň.', 'ru': 'Пожалуйста, выберите свой регион.'},
    'flash.full_name_required': {'en': 'Full name is required.', 'tm': 'Doly ady hökmany.', 'ru': 'Полное имя обязательно.'},
    'flash.valid_age_required': {'en': 'Valid age is required.', 'tm': 'Dogry ýaş girizmek hökmany.', 'ru': 'Необходимо указать корректный возраст.'},
    'flash.email_required_general': {'en': 'Email is required.', 'tm': 'Email hökmany.', 'ru': 'Email обязателен.'},
    'flash.password_len': {'en': 'Password must be at least 6 characters.', 'tm': 'Parol azyndan 6 nyşandan ybarat bolmaly.', 'ru': 'Пароль должен содержать минимум 6 символов.'},
    'flash.passwords_no_match': {'en': 'Passwords do not match.', 'tm': 'Parollar gabat gelenok.', 'ru': 'Пароли не совпадают.'},
    'flash.email_exists': {'en': 'Email already exists', 'tm': 'Bu email eýýäm bar', 'ru': 'Этот email уже существует'},
    'flash.passport_required': {'en': 'Passport photo is required for KYC verification.', 'tm': 'KYC barlagy üçin pasport suraty hökmany.', 'ru': 'Для KYC-проверки требуется фото паспорта.'},
    'flash.invalid_passport': {'en': 'Invalid passport image. Please upload again.', 'tm': 'Pasport suraty nädogry. Täzeden ýükläň.', 'ru': 'Некорректное изображение паспорта. Загрузите снова.'},
    'flash.registration_complete': {'en': 'Registration complete. We sent your information to admin. Your KYC status is processing.', 'tm': 'Hasap açyş tamamlandy. Maglumatlaryňyz admina ugradyldy. KYC ýagdaýyňyz işlenýär.', 'ru': 'Регистрация завершена. Ваши данные отправлены администратору. Статус KYC обрабатывается.'},
    'flash.valid_neighborhood': {'en': 'Please select a valid neighborhood or street.', 'tm': 'Dogry ýer ýa-da köçe saýlaň.', 'ru': 'Пожалуйста, выберите корректный район или улицу.'},
    'flash.own_item': {'en': 'You cannot rent/buy your own item!', 'tm': 'Öz harydyňyzy kärendesine alyp ýa-da satyn alyp bilmersiňiz!', 'ru': 'Нельзя арендовать или покупать собственный товар!'},
    'flash.item_rented': {'en': 'This item is currently rented out.', 'tm': 'Bu haryt häzir kärendededir.', 'ru': 'Этот товар сейчас в аренде.'},
    'flash.rental_request_sent': {'en': 'Rental request sent to the owner! Wait for their approval and meet to scan the QR code.', 'tm': 'Kärende haýyşy eýesine ugradyldy! Tassyklamagyna garaşyň we QR kody skanerlemek üçin duşuşyň.', 'ru': 'Запрос на аренду отправлен владельцу! Дождитесь одобрения и встретьтесь для сканирования QR-кода.'},
    'flash.negotiate_self': {'en': 'You cannot negotiate with yourself!', 'tm': 'Özüňiz bilen söwdalaşyp bilmersiňiz!', 'ru': 'Нельзя торговаться с самим собой!'},
    'flash.enter_price': {'en': 'Please enter a proposed price.', 'tm': 'Teklip edilýän bahany giriziň.', 'ru': 'Введите предлагаемую цену.'},
    'flash.negotiation_sent': {'en': 'Negotiation request sent to the owner!', 'tm': 'Söwdalaşyk haýyşy eýesine ugradyldy!', 'ru': 'Запрос на торг отправлен владельцу!'},
    'flash.unauthorized': {'en': 'Unauthorized.', 'tm': 'Rugsat ýok.', 'ru': 'Нет доступа.'},
    'flash.deal_accepted': {'en': 'Deal accepted! Show the QR code to the renter when you meet.', 'tm': 'Ylalaşyk kabul edildi! Duşuşanda kärende alýana QR kody görkeziň.', 'ru': 'Сделка принята! При встрече покажите арендатору QR-код.'},
    'flash.negotiation_cancelled': {'en': 'Negotiation cancelled.', 'tm': 'Söwdalaşyk ýatyryldy.', 'ru': 'Торг отменен.'},
    'flash.only_renter_confirm': {'en': 'Only the renter can confirm the hand-off.', 'tm': 'Tabşyryşy diňe kärende alyjy tassyk edip biler.', 'ru': 'Только арендатор может подтвердить передачу.'},
    'flash.deal_not_ready': {'en': 'This deal is not ready for confirmation.', 'tm': 'Bu ylalaşyk entek tassyk üçin taýyn däl.', 'ru': 'Эта сделка пока не готова к подтверждению.'},
    'flash.verified_required': {'en': 'You must be a verified user to rent high-value items. Please wait for admin approval.', 'tm': 'Gymmat bahaly harytlary kärendesine almak üçin tassyklanan ulanyjy bolmaly. Admin tassygyňa garaşyň.', 'ru': 'Чтобы арендовать дорогие товары, вы должны быть подтвержденным пользователем. Дождитесь одобрения администратора.'},
    'flash.insufficient_funds': {'en': 'Insufficient funds!', 'tm': 'Ýeterlik serişdeler ýok!', 'ru': 'Недостаточно средств!'},
    'flash.payment_success': {'en': 'Payment successful! HandShake is holding the deposit. Rental started!', 'tm': 'Töleg üstünlikli boldy! HandShake goýumy saklaýar. Kärende başlandy!', 'ru': 'Оплата прошла успешно! HandShake удерживает депозит. Аренда началась!'},
    'flash.transaction_failed': {'en': 'Transaction failed.', 'tm': 'Amal şowsuz boldy.', 'ru': 'Транзакция не удалась.'},
    'flash.only_owner_return': {'en': 'Only the owner can confirm return.', 'tm': 'Gaýtarylyşy diňe eýesi tassyk edip biler.', 'ru': 'Только владелец может подтвердить возврат.'},
    'flash.invalid_action': {'en': 'Invalid action.', 'tm': 'Nädogry amal.', 'ru': 'Недопустимое действие.'},
    'flash.return_confirmed': {'en': 'Item return confirmed! Security deposit released back to the renter.', 'tm': 'Harydyň gaýtarylyşy tassyklandy! Gorag goýumy kärende alýana yzyna goýberildi.', 'ru': 'Возврат товара подтвержден! Гарантийный депозит возвращен арендатору.'},
    'flash.return_error': {'en': 'Error processing return.', 'tm': 'Gaýtarylyşy işlemekde ýalňyşlyk boldy.', 'ru': 'Ошибка при обработке возврата.'},
    'flash.location_required': {'en': 'Location is required.', 'tm': 'Ýerleşýän ýer hökmany.', 'ru': 'Местоположение обязательно.'},
    'flash.chat_self': {'en': 'You cannot chat-request yourself.', 'tm': 'Özüňiz bilen çat sorap bilmersiňiz.', 'ru': 'Нельзя запросить чат с самим собой.'},
    'flash.chat_blocked': {'en': 'Chat request unavailable because one of you is blocked.', 'tm': 'Sizden biri bloklananlygy sebäpli çat haýyşy elýeterli däl.', 'ru': 'Запрос чата недоступен, потому что один из вас заблокирован.'},
    'flash.chat_request_sent': {'en': 'Chat request sent!', 'tm': 'Çat haýyşy ugradyldy!', 'ru': 'Запрос чата отправлен!'},
    'flash.chat_active_exists': {'en': 'You already have an active chat with this user.', 'tm': 'Bu ulanyjy bilen eýýäm işjeň çatyňyz bar.', 'ru': 'У вас уже есть активный чат с этим пользователем.'},
    'flash.chat_request_exists': {'en': 'Chat request already exists.', 'tm': 'Çat haýyşy eýýäm bar.', 'ru': 'Запрос чата уже существует.'},
    'flash.chat_request_incoming': {'en': 'This user already sent you a request. Open Messages to accept it.', 'tm': 'Bu ulanyjy size eýýäm haýyş iberdi. Kabul etmek üçin Habarlary açyň.', 'ru': 'Этот пользователь уже отправил вам запрос. Откройте сообщения, чтобы принять его.'},
    'flash.chat_request_unavailable': {'en': 'This chat request is no longer available.', 'tm': 'Bu çat haýyşy indi elýeterli däl.', 'ru': 'Этот запрос чата больше недоступен.'},
    'flash.block_self': {'en': 'You cannot block yourself.', 'tm': 'Özüňizi bloklap bilmersiňiz.', 'ru': 'Нельзя заблокировать себя.'},
    'flash.user_blocked': {'en': 'User blocked.', 'tm': 'Ulanyjy bloklandy.', 'ru': 'Пользователь заблокирован.'},
    'flash.user_unblocked': {'en': 'User unblocked.', 'tm': 'Ulanyjy blokdan çykaryldy.', 'ru': 'Пользователь разблокирован.'},
    'flash.accept_request_first': {'en': 'This user requested to chat with you. Accept it in Requests first.', 'tm': 'Bu ulanyjy size çat sorady. Ilki Haýyşlar bölüminde kabul ediň.', 'ru': 'Этот пользователь запросил чат с вами. Сначала примите его в запросах.'},
    'flash.request_pending': {'en': 'Your chat request is still pending approval.', 'tm': 'Çat haýyşyňyz heniz tassyk garaşýar.', 'ru': 'Ваш запрос чата все еще ожидает одобрения.'},
    'flash.send_request_first': {'en': 'Send a chat request first before messaging this user.', 'tm': 'Bu ulanyja ýazmazdan öň ilki çat haýyşyny iberiň.', 'ru': 'Сначала отправьте запрос чата, прежде чем писать этому пользователю.'},
    'flash.invalid_recipient': {'en': 'Invalid message recipient.', 'tm': 'Nädogry habar alyjy.', 'ru': 'Недопустимый получатель сообщения.'},
    'flash.messaging_blocked': {'en': 'Messaging is unavailable because one of you is blocked.', 'tm': 'Sizden biri bloklananlygy sebäpli habarlaşmak elýeterli däl.', 'ru': 'Переписка недоступна, потому что один из вас заблокирован.'},
    'flash.accepted_chat_required': {'en': 'You need an accepted chat request before sending messages.', 'tm': 'Habar ugratmazdan öň kabul edilen çat haýyşy gerek.', 'ru': 'Перед отправкой сообщений нужен принятый запрос чата.'},
    'flash.rating_range': {'en': 'Rating must be between 1 and 5.', 'tm': 'Baha 1 bilen 5 aralygynda bolmaly.', 'ru': 'Оценка должна быть от 1 до 5.'},
    'flash.review_empty': {'en': 'Review cannot be empty.', 'tm': 'Teswir boş bolup bilmez.', 'ru': 'Отзыв не может быть пустым.'},
}

LOCALIZED_CHOICES = {
    'category': {
        'hobbies': {'en': 'Hobbies', 'tm': 'Hobbi', 'ru': 'Хобби'},
        'tech': {'en': 'Tech', 'tm': 'Tehnika', 'ru': 'Техника'},
        'cars': {'en': 'Cars', 'tm': 'Ulaglar', 'ru': 'Авто'},
        'houses': {'en': 'Houses', 'tm': 'Jaýlar', 'ru': 'Жилье'},
        'tools': {'en': 'Tools', 'tm': 'Gurallar', 'ru': 'Инструменты'},
        'books': {'en': 'Books', 'tm': 'Kitaplar', 'ru': 'Книги'},
    },
    'type': {
        'rent': {'en': 'Rent', 'tm': 'Kärende', 'ru': 'Аренда'},
        'sell': {'en': 'Sell', 'tm': 'Satmak', 'ru': 'Продажа'},
        'exchange': {'en': 'Exchange', 'tm': 'Çalyşmak', 'ru': 'Обмен'},
    },
    'tx_status': {
        'active': {'en': 'Renting', 'tm': 'Kärendede', 'ru': 'В аренде'},
        'returned': {'en': 'Returned', 'tm': 'Gaýtaryldy', 'ru': 'Возвращено'},
        'completed': {'en': 'Completed', 'tm': 'Tamamlandy', 'ru': 'Завершено'},
        'accepted': {'en': 'Accepted', 'tm': 'Kabul edildi', 'ru': 'Принято'},
        'negotiating': {'en': 'Negotiating', 'tm': 'Ylalaşylýar', 'ru': 'Торг'},
    },
}

SEEDED_LOCALIZED_TEXT = {
    'Sony A7III Camera': {'tm': 'Sony A7III kamera', 'ru': 'Камера Sony A7III'},
    'DJI Mavic Air 2': {'tm': 'DJI Mavic Air 2 dron', 'ru': 'Дрон DJI Mavic Air 2'},
    'Toyota Camry 2022': {'tm': 'Toyota Camry 2022', 'ru': 'Toyota Camry 2022'},
    'BMW X5': {'tm': 'BMW X5', 'ru': 'BMW X5'},
    'Mercedes-Benz G-Class': {'tm': 'Mercedes-Benz G-Class', 'ru': 'Mercedes-Benz G-Class'},
    'Rare Art History Collection': {'tm': 'Seýrek sungat taryhy ýygyndysy', 'ru': 'Редкая коллекция по истории искусства'},
    'Bosch Drill Set': {'tm': 'Bosch buraw toplumy', 'ru': 'Набор дрелей Bosch'},
    'Professional Toolkit': {'tm': 'Professional gural toplumy', 'ru': 'Профессиональный набор инструментов'},
    'PlayStation 5 + 2 Controllers': {'tm': 'PlayStation 5 + 2 pult', 'ru': 'PlayStation 5 + 2 геймпада'},
    'Canon EOS R5': {'tm': 'Canon EOS R5 kamera', 'ru': 'Canon EOS R5'},
    'Electric Skateboard': {'tm': 'Elektrik skeytbord', 'ru': 'Электроскейт'},
    'Table Tennis Rackets (Pair)': {'tm': 'Stol tennisi raketkalary (jübüt)', 'ru': 'Ракетки для настольного тенниса (пара)'},
    'Mountain Bike - Trek': {'tm': 'Dag welosipedi - Trek', 'ru': 'Горный велосипед Trek'},
    'Perfect for professional shoots.': {'tm': 'Professional surata alyş üçin örän amatly.', 'ru': 'Идеально подходит для профессиональных съемок.'},
    '4K drone for amazing aerial shots.': {'tm': 'Howa arkaly ajaýyp 4K düşüriliş üçin dron.', 'ru': '4K-дрон для впечатляющих аэрофотосъемок.'},
    'Clean, reliable, and comfortable.': {'tm': 'Arassa, ygtybarly we amatly ulag.', 'ru': 'Чистый, надежный и комфортный автомобиль.'},
    'Luxury SUV for special occasions.': {'tm': 'Aýratyn ýagdaýlar üçin kaşaň krossower.', 'ru': 'Премиальный SUV для особых случаев.'},
    'The ultimate luxury off-roader.': {'tm': 'Ýokary derejeli kaşaň ýolagdan çykýan ulag.', 'ru': 'Максимально роскошный внедорожник.'},
    'Set of 5 books about Renaissance art.': {'tm': 'Galkynyş döwrüniň sungaty barada 5 kitapdan ybarat toplum.', 'ru': 'Набор из 5 книг об искусстве эпохи Возрождения.'},
    'Heavy duty drill with all attachments.': {'tm': 'Ähli goşundylary bilen güýçli buraw.', 'ru': 'Мощная дрель со всеми насадками.'},
    '150-piece tool set for all home repairs.': {'tm': 'Öý abatlaýyş işleri üçin 150 bölekli gural toplumy.', 'ru': 'Набор из 150 инструментов для домашнего ремонта.'},
    'Latest games included: GOW, Spider-Man.': {'tm': 'Soňky oýunlar hem bar: GOW, Spider-Man.', 'ru': 'В комплекте последние игры: GOW, Spider-Man.'},
    'High-resolution full-frame mirrorless camera.': {'tm': 'Ýokary durulykdaky doly kadrly aynasuz kamera.', 'ru': 'Полнокадровая беззеркальная камера высокого разрешения.'},
    'Fast and fun city commuting.': {'tm': 'Şäher içinde çalt we gyzykly gatnaw üçin.', 'ru': 'Быстрое и веселое передвижение по городу.'},
    'Professional grade rackets for competitive play.': {'tm': 'Bäsdeşlik oýny üçin professional derejeli raketkalar.', 'ru': 'Профессиональные ракетки для соревновательной игры.'},
    'Durable bike for trail riding.': {'tm': 'Dag ýollarynda sürmek üçin berk welosiped.', 'ru': 'Надежный велосипед для поездок по трассам.'},
    'Excellent camera, very well maintained!': {'tm': 'Örän gowy saklanan ajaýyp kamera!', 'ru': 'Отличная камера, очень ухоженная!'},
}

# Seeded from current official administrative references for Turkmenistan,
# with Ashgabat streets and avenues taken from official city transport notices.
TURKMEN_LOCATION_DATA = [
    {
        "name": "Ashgabat",
        "kind": "city",
        "districts": [
            {
                "name": "Bagtyyarlyk",
                "category": "city_district",
                "neighborhoods": [
                    "Teke Bazar",
                    "A. Niyazov Avenue",
                    "M. Kashgari Street",
                    "D. Azady Street",
                ],
            },
            {
                "name": "Berkararlyk",
                "category": "city_district",
                "neighborhoods": [
                    "Central Ashgabat",
                    "Garashsyzlyk Avenue",
                    "Turkmenbashy Avenue",
                    "Ataturk Street",
                ],
            },
            {
                "name": "Kopetdag",
                "category": "city_district",
                "neighborhoods": [
                    "Archabil Avenue",
                    "Bitarap Turkmenistan Avenue",
                    "Chandybil Avenue",
                ],
            },
            {
                "name": "Buzmeyin",
                "category": "city_district",
                "neighborhoods": [
                    "Arzuv",
                    "10 yyl Abadanchylyk Street",
                    "B. Annanov Street",
                    "H.A. Yasavi Street",
                    "N. Andalib Street",
                ],
            },
        ],
    },
    {
        "name": "Ahal",
        "kind": "velayat",
        "districts": [
            {"name": "Ak bugday", "category": "district", "neighborhoods": ["Anau"]},
            {"name": "Altyn Asyr", "category": "district", "neighborhoods": ["Altyn Asyr"]},
            {"name": "Babadayhan", "category": "district", "neighborhoods": ["Babadayhan"]},
            {"name": "Baharly", "category": "district", "neighborhoods": ["Baharly"]},
            {"name": "Gokdepe", "category": "district", "neighborhoods": ["Gokdepe"]},
            {"name": "Kaka", "category": "district", "neighborhoods": ["Kaka"]},
            {"name": "Sarahs", "category": "district", "neighborhoods": ["Sarahs"]},
            {"name": "Tejen", "category": "district", "neighborhoods": ["Tejen"]},
        ],
    },
    {"name": "Balkan", "kind": "velayat", "districts": []},
    {"name": "Dashoguz", "kind": "velayat", "districts": []},
    {"name": "Lebap", "kind": "velayat", "districts": []},
    {"name": "Mary", "kind": "velayat", "districts": []},
    {"name": "Arkadag", "kind": "city", "districts": []},
]


def save_data_url_image(data_url, destination_path):
    if not data_url or ',' not in data_url:
        raise ValueError("Missing image data")

    _, encoded = data_url.split(',', 1)
    try:
        image_bytes = base64.b64decode(encoded)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid image data") from exc

    with open(destination_path, "wb") as fh:
        fh.write(image_bytes)


def find_chat_request_between(user_a_id, user_b_id):
    return ChatRequest.query.filter(
        ((ChatRequest.sender_id == user_a_id) & (ChatRequest.recipient_id == user_b_id)) |
        ((ChatRequest.sender_id == user_b_id) & (ChatRequest.recipient_id == user_a_id))
    ).order_by(ChatRequest.timestamp.desc()).first()


def has_accepted_chat_between(user_a_id, user_b_id):
    return ChatRequest.query.filter(
        (
            ((ChatRequest.sender_id == user_a_id) & (ChatRequest.recipient_id == user_b_id)) |
            ((ChatRequest.sender_id == user_b_id) & (ChatRequest.recipient_id == user_a_id))
        ) &
        (ChatRequest.status == 'accepted')
    ).first()


def find_pending_chat_request(sender_id, recipient_id):
    return ChatRequest.query.filter_by(
        sender_id=sender_id,
        recipient_id=recipient_id,
        status='pending'
    ).order_by(ChatRequest.timestamp.desc()).first()


def get_chat_connection_state(user_a_id, user_b_id):
    accepted = has_accepted_chat_between(user_a_id, user_b_id)
    if accepted:
        return 'accepted', accepted

    outgoing_pending = find_pending_chat_request(user_a_id, user_b_id)
    if outgoing_pending:
        return 'outgoing_pending', outgoing_pending

    incoming_pending = find_pending_chat_request(user_b_id, user_a_id)
    if incoming_pending:
        return 'incoming_pending', incoming_pending

    return 'none', None


def normalize_profile_pic_url(image_url):
    if not image_url:
        return image_url

    normalized = image_url.strip().replace("\\", "/")
    if normalized.startswith("http://") or normalized.startswith("https://") or normalized.startswith("/static/"):
        return normalized

    static_index = normalized.lower().find("static/")
    if static_index >= 0:
        return "/" + normalized[static_index:]

    if normalized.startswith("uploads/"):
        return url_for('static', filename=normalized)

    return normalized


def normalize_user_profile_pic(user):
    if not user:
        return
    user.profile_pic = normalize_profile_pic_url(user.profile_pic)


def hash_password_reset_token(raw_token):
    payload = f"{app.secret_key}:{raw_token}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_locale():
    lang = session.get('lang', 'en')
    return lang if lang in SUPPORTED_LANGUAGES else 'en'


def tr(key, **kwargs):
    locale = get_locale()
    value = TRANSLATIONS.get(locale, {}).get(key)
    if value is None:
        value = TRANSLATIONS['en'].get(key, key)
    if kwargs:
        return value.format(**kwargs)
    return value


def ui_text(key, **kwargs):
    locale = get_locale()
    value = LOCALIZED_UI.get(key, {}).get(locale)
    if value is None:
        value = LOCALIZED_UI.get(key, {}).get('en', key)
    if kwargs:
        return value.format(**kwargs)
    return value


def choice_label(group, key):
    locale = get_locale()
    group_values = LOCALIZED_CHOICES.get(group, {})
    value = group_values.get(key, {}).get(locale)
    if value is None:
        value = group_values.get(key, {}).get('en', key)
    return value


def localized_seeded_text(value):
    locale = get_locale()
    if locale == 'en':
        return value
    translated = SEEDED_LOCALIZED_TEXT.get(value, {}).get(locale)
    return translated or value


def is_admin_email(email):
    normalized = (email or '').strip().lower()
    return bool(ADMIN_EMAIL) and normalized == ADMIN_EMAIL


def get_reset_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt='password-reset-v1')


def build_reset_token(user):
    serializer = get_reset_serializer()
    return serializer.dumps({'uid': user.id, 'email': user.email})


def verify_reset_token(token, max_age_seconds):
    serializer = get_reset_serializer()
    try:
        return serializer.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None


def send_password_reset_email(to_email, reset_link):
    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    smtp_from = os.getenv('SMTP_FROM') or smtp_user
    use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'

    if not smtp_host or not smtp_user or not smtp_pass or not smtp_from:
        return False

    msg = EmailMessage()
    msg['Subject'] = 'HandShake password reset verification'
    msg['From'] = smtp_from
    msg['To'] = to_email
    msg.set_content(
        f"Open this link to reset your password:\n\n{reset_link}\n\n"
        f"This link expires in {PASSWORD_RESET_TOKEN_TTL_MINUTES} minutes."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    return True


def get_location_tree():
    velayats = Velayat.query.order_by(
        db.case(
            (Velayat.name == 'Ashgabat', 0),
            (Velayat.name == 'Ahal', 1),
            else_=2
        ),
        Velayat.name.asc()
    ).all()
    tree = []
    for velayat in velayats:
        districts = []
        for district in sorted(velayat.districts, key=lambda item: item.name):
            neighborhoods = [
                {"id": neighborhood.id, "name": neighborhood.name}
                for neighborhood in sorted(district.neighborhoods, key=lambda item: item.name)
            ]
            districts.append(
                {
                    "id": district.id,
                    "name": district.name,
                    "category": district.category,
                    "neighborhoods": neighborhoods,
                }
            )
        tree.append(
            {
                "id": velayat.id,
                "name": velayat.name,
                "kind": velayat.kind,
                "districts": districts,
            }
        )
    return tree


def find_seeded_neighborhood(velayat_name, district_name, neighborhood_name):
    return Neighborhood.query.join(District).join(Velayat).filter(
        Velayat.name == velayat_name,
        District.name == district_name,
        Neighborhood.name == neighborhood_name
    ).first()


def resolve_legacy_location(legacy_loc):
    normalized = (legacy_loc or '').strip().lower()
    if not normalized:
        return find_seeded_neighborhood('Ashgabat', 'Berkararlyk', 'Central Ashgabat')

    mapping = [
        ('ashgabat', ('Ashgabat', 'Berkararlyk', 'Central Ashgabat')),
        ('anau', ('Ahal', 'Ak bugday', 'Anau')),
        ('ak bugday', ('Ahal', 'Ak bugday', 'Anau')),
        ('altyn asyr', ('Ahal', 'Altyn Asyr', 'Altyn Asyr')),
        ('babadayhan', ('Ahal', 'Babadayhan', 'Babadayhan')),
        ('baharly', ('Ahal', 'Baharly', 'Baharly')),
        ('gokdepe', ('Ahal', 'Gokdepe', 'Gokdepe')),
        ('kaka', ('Ahal', 'Kaka', 'Kaka')),
        ('sarahs', ('Ahal', 'Sarahs', 'Sarahs')),
        ('tejen', ('Ahal', 'Tejen', 'Tejen')),
    ]
    for token, target in mapping:
        if token in normalized:
            return find_seeded_neighborhood(*target)
    return find_seeded_neighborhood('Ashgabat', 'Berkararlyk', 'Central Ashgabat')


def ensure_location_schema():
    Velayat.__table__.create(bind=db.engine, checkfirst=True)
    District.__table__.create(bind=db.engine, checkfirst=True)
    Neighborhood.__table__.create(bind=db.engine, checkfirst=True)

    inspector = inspect(db.engine)
    item_columns = {column['name'] for column in inspector.get_columns('item')}
    if 'neighborhood_id' not in item_columns:
        db.session.execute(text('ALTER TABLE item ADD COLUMN neighborhood_id INTEGER'))
        db.session.commit()

    user_columns = {column['name'] for column in inspector.get_columns('user')}
    if 'kyc_status' not in user_columns:
        db.session.execute(text("ALTER TABLE user ADD COLUMN kyc_status VARCHAR(20) DEFAULT 'pending'"))
        db.session.commit()


def seed_location_data():
    for velayat_data in TURKMEN_LOCATION_DATA:
        velayat = Velayat.query.filter_by(name=velayat_data['name']).first()
        if not velayat:
            velayat = Velayat(name=velayat_data['name'], kind=velayat_data['kind'])
            db.session.add(velayat)
            db.session.flush()
        else:
            velayat.kind = velayat_data['kind']

        for district_data in velayat_data['districts']:
            district = District.query.filter_by(
                velayat_id=velayat.id,
                name=district_data['name']
            ).first()
            if not district:
                district = District(
                    name=district_data['name'],
                    category=district_data['category'],
                    velayat_id=velayat.id
                )
                db.session.add(district)
                db.session.flush()
            else:
                district.category = district_data['category']

            for neighborhood_name in district_data['neighborhoods']:
                neighborhood = Neighborhood.query.filter_by(
                    district_id=district.id,
                    name=neighborhood_name
                ).first()
                if not neighborhood:
                    db.session.add(Neighborhood(name=neighborhood_name, district_id=district.id))

    db.session.commit()


def backfill_item_locations():
    inspector = inspect(db.engine)
    item_columns = {column['name'] for column in inspector.get_columns('item')}
    has_legacy_loc = 'loc' in item_columns
    if has_legacy_loc:
        rows = db.session.execute(text('SELECT id, loc, neighborhood_id FROM item')).mappings().all()
        for row in rows:
            if row['neighborhood_id']:
                continue
            neighborhood = resolve_legacy_location(row['loc'])
            if neighborhood:
                db.session.execute(
                    text('UPDATE item SET neighborhood_id = :neighborhood_id WHERE id = :item_id'),
                    {"neighborhood_id": neighborhood.id, "item_id": row['id']}
                )
        db.session.commit()
        return

    items = Item.query.filter(Item.neighborhood_id.is_(None)).all()
    for item in items:
        neighborhood = resolve_legacy_location(None)
        if neighborhood:
            item.neighborhood_id = neighborhood.id
    db.session.commit()


def rebuild_item_table_without_legacy_loc():
    inspector = inspect(db.engine)
    item_columns = {column['name'] for column in inspector.get_columns('item')}
    if 'loc' not in item_columns:
        return

    db.session.execute(text('PRAGMA foreign_keys=OFF'))
    db.session.execute(text('DROP TABLE IF EXISTS item_new'))
    db.session.execute(text("""
        CREATE TABLE item_new (
            id INTEGER NOT NULL PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            price VARCHAR(50) NOT NULL,
            price_unit VARCHAR(20) DEFAULT "day",
            type VARCHAR(50) NOT NULL,
            description TEXT,
            image_url VARCHAR(500),
            category VARCHAR(100) NOT NULL,
            rating FLOAT,
            num_ratings INTEGER,
            user_id INTEGER,
            neighborhood_id INTEGER
        )
    """))
    db.session.execute(text("""
        INSERT INTO item_new (
            id, title, price, price_unit, type, description, image_url,
            category, rating, num_ratings, user_id, neighborhood_id
        )
        SELECT
            id, title, price, "day", type, description, image_url,
            category, rating, num_ratings, user_id, neighborhood_id
        FROM item
    """))
    db.session.execute(text('DROP TABLE item'))
    db.session.execute(text('ALTER TABLE item_new RENAME TO item'))
    db.session.execute(text('PRAGMA foreign_keys=ON'))
    db.session.commit()


def update_rent_duration_schema():
    inspector = inspect(db.engine)
    item_columns = {column['name'] for column in inspector.get_columns('item')}
    if 'price_unit' not in item_columns:
        db.session.execute(text('ALTER TABLE item ADD COLUMN price_unit VARCHAR(20) DEFAULT "day"'))
        db.session.commit()
    
    transaction_columns = {column['name'] for column in inspector.get_columns('transaction')}
    if 'duration' not in transaction_columns:
        db.session.execute(text('ALTER TABLE "transaction" ADD COLUMN duration INTEGER DEFAULT 1'))
        db.session.commit()

def apply_database_updates():
    db.create_all()
    update_rent_duration_schema()
    ensure_location_schema()
    seed_location_data()
    backfill_item_locations()
    rebuild_item_table_without_legacy_loc()


@app.errorhandler(RequestEntityTooLarge)
def handle_request_too_large(_error):
    flash(ui_text('flash.image_too_large'))

    if request.path == url_for('register'):
        return redirect(url_for('register'))
    if request.path == url_for('login'):
        return redirect(url_for('login'))
    if request.path == url_for('upload'):
        return redirect(url_for('upload'))
    if request.path == url_for('edit_profile'):
        return redirect(url_for('edit_profile'))
    return redirect(url_for('index'))

# Models
class Velayat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    kind = db.Column(db.String(20), nullable=False, default='velayat')
    districts = db.relationship('District', backref='velayat', lazy=True, cascade='all, delete-orphan')


class District(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(20), nullable=False, default='district')
    velayat_id = db.Column(db.Integer, db.ForeignKey('velayat.id'), nullable=False)
    neighborhoods = db.relationship('Neighborhood', backref='district', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('velayat_id', 'name', name='uq_district_velayat_name'),
    )


class Neighborhood(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    district_id = db.Column(db.Integer, db.ForeignKey('district.id'), nullable=False)
    items = db.relationship('Item', backref='neighborhood', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('district_id', 'name', name='uq_neighborhood_district_name'),
    )

    @property
    def display_name(self):
        return f"{self.name}, {self.district.name}"

    @property
    def full_path(self):
        return f"{self.name}, {self.district.name}, {self.district.velayat.name}"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=True)
    full_name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    region = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=True)
    bio = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Float, default=5.0)
    num_ratings = db.Column(db.Integer, default=1)
    passport_img = db.Column(db.String(200), nullable=False)
    profile_pic = db.Column(db.String(500), nullable=True)
    kyc_status = db.Column(db.String(20), default='pending') # pending, processing, verified, rejected
    wallet_balance = db.Column(db.Float, default=1000.0) # Mock money for transactions
    items = db.relationship('Item', backref='owner', lazy=True)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy=True)


class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship('User', backref='password_reset_tokens')


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    price = db.Column(db.String(50), nullable=False)
    price_unit = db.Column(db.String(20), default='day') # 'hour' or 'day'
    deposit_price = db.Column(db.Float, default=0.0) # Added for theft protection
    type = db.Column(db.String(50), nullable=False) # 'rent' or 'sell'
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    category = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Float, default=5.0)
    num_ratings = db.Column(db.Integer, default=1)
    is_available = db.Column(db.Boolean, default=True) # Added to track active rentals
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    neighborhood_id = db.Column(db.Integer, db.ForeignKey('neighborhood.id'), nullable=True)

    @property
    def location_label(self):
        if self.neighborhood:
            return self.neighborhood.full_path
        return "Ashgabat"

    @property
    def localized_title(self):
        return localized_seeded_text(self.title)

    @property
    def localized_description(self):
        return localized_seeded_text(self.description) if self.description else None

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    commission = db.Column(db.Float, default=0.0)
    deposit_amount = db.Column(db.Float, default=0.0) # Escrowed deposit
    total_amount = db.Column(db.Float, nullable=False)
    duration = db.Column(db.Integer, default=1) # Number of hours/days
    status = db.Column(db.String(20), default='active') # active, completed, disputed, returned
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    buyer = db.relationship('User', foreign_keys=[buyer_id], backref='purchases')
    seller = db.relationship('User', foreign_keys=[seller_id], backref='sales')
    item = db.relationship('Item', backref='transactions')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('item.id'), nullable=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    reviewer = db.relationship('User', foreign_keys=[reviewer_id], backref='reviews_written')

    @property
    def localized_content(self):
        return localized_seeded_text(self.content)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    body = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)

class ChatRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, accepted, rejected
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_requests')
    recipient = db.relationship('User', foreign_keys=[recipient_id], backref='received_requests')

class BlockedUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocked_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    normalize_user_profile_pic(user)
    return user


@app.context_processor
def inject_chat_request_count():
    pending_chat_request_count = 0
    if current_user.is_authenticated:
        pending_chat_request_count = ChatRequest.query.filter_by(
            recipient_id=current_user.id,
            status='pending'
        ).count()
    return {
        'pending_chat_request_count': pending_chat_request_count,
        't': tr,
        'ui': ui_text,
        'choice_label': choice_label,
        'current_locale': get_locale(),
        'supported_languages': SUPPORTED_LANGUAGES,
    }


@app.route('/set-language/<lang_code>')
def set_language(lang_code):
    code = (lang_code or '').strip().lower()
    if code in SUPPORTED_LANGUAGES:
        session['lang'] = code
    next_url = request.args.get('next') or request.referrer or url_for('index')
    return redirect(next_url)

# Initialize Database with dummy data
with app.app_context():
    apply_database_updates()
    
    if not User.query.filter_by(email="nepes@handshake.com").first():
        # Create Dummy Users
        dummy_users = [
            {"name": "Nepes", "email": "nepes@handshake.com", "pass": "nepes123", "region": "Turkmenistan", "bio": "Photography enthusiast and tech geek.", "pic": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=400"},
            {"name": "Aman", "email": "aman@handshake.com", "pass": "aman123", "region": "Turkmenistan", "bio": "Professional driver, renting out my spare cars.", "pic": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400"},
            {"name": "Selbi", "email": "selbi@handshake.com", "pass": "selbi123", "region": "Turkmenistan", "bio": "I love books and sharing knowledge.", "pic": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400"},
            {"name": "Maral", "email": "maral@handshake.com", "pass": "maral123", "region": "Turkmenistan", "bio": "Home renovation expert. Rent my tools!", "pic": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400"},
            {"name": "Arslan", "email": "arslan@handshake.com", "pass": "arslan123", "region": "Turkmenistan", "bio": "Gaming is my life. renting my PS5 and games.", "pic": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400"},
            {"name": "User1", "email": "user1@handshake.com", "pass": "user1", "region": "Turkmenistan", "bio": "New HandShake member ready to rent!", "pic": "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400"}
        ]
        
        db_users = []
        for u in dummy_users:
            new_u = User(
                username=u['name'].lower(), full_name=u['name'], email=u['email'],
                password_hash=generate_password_hash(u['pass'], method='scrypt'),
                region=u['region'], bio=u['bio'], age=25, passport_img="verified.png",
                profile_pic=u['pic']
            )
            db.session.add(new_u)
            db_users.append(new_u)
        db.session.commit()

        items_data = [
            {"title": "Sony A7III Camera", "price": "200", "type": "rent", "cat": "hobbies", "user_idx": 0, "desc": "Perfect for professional shoots.", "img": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=800"},
            {"title": "DJI Mavic Air 2", "price": "150", "type": "rent", "cat": "hobbies", "user_idx": 0, "desc": "4K drone for amazing aerial shots.", "img": "https://images.unsplash.com/photo-1508614589041-895b88991e3e?w=800"},
            {"title": "Toyota Camry 2022", "price": "500", "type": "rent", "cat": "cars", "user_idx": 1, "desc": "Clean, reliable, and comfortable.", "img": "https://images.unsplash.com/photo-1621007947382-bb3c3994e3fb?w=800"},
            {"title": "BMW X5", "price": "800", "type": "rent", "cat": "cars", "user_idx": 1, "desc": "Luxury SUV for special occasions.", "img": "https://images.unsplash.com/photo-1555215695-3004980ad54e?w=800"},
            {"title": "Mercedes-Benz G-Class", "price": "1500", "type": "rent", "cat": "cars", "user_idx": 1, "desc": "The ultimate luxury off-roader.", "img": "https://images.unsplash.com/photo-1520031441872-265e4ff70366?w=800"},
            {"title": "Rare Art History Collection", "price": "20", "type": "exchange", "cat": "books", "user_idx": 2, "desc": "Set of 5 books about Renaissance art.", "img": "https://images.unsplash.com/photo-1512820790803-83ca734da794?w=800"},
            {"title": "Bosch Drill Set", "price": "50", "type": "rent", "cat": "tools", "user_idx": 3, "desc": "Heavy duty drill with all attachments.", "img": "https://images.unsplash.com/photo-1504148455328-c376907d081c?w=800"},
            {"title": "Professional Toolkit", "price": "75", "type": "rent", "cat": "tools", "user_idx": 3, "desc": "150-piece tool set for all home repairs.", "img": "https://images.unsplash.com/photo-1581244277943-fe4a9c777189?w=800"},
            {"title": "PlayStation 5 + 2 Controllers", "price": "100", "type": "rent", "cat": "hobbies", "user_idx": 4, "desc": "Latest games included: GOW, Spider-Man.", "img": "https://images.unsplash.com/photo-1606813907291-d86efa9b94db?w=800"},
            {"title": "Canon EOS R5", "price": "350", "type": "rent", "cat": "hobbies", "user_idx": 5, "desc": "High-resolution full-frame mirrorless camera.", "img": "https://images.unsplash.com/photo-1510127034890-ba27508e9f1c?w=800"},
            {"title": "Electric Skateboard", "price": "80", "type": "rent", "cat": "hobbies", "user_idx": 5, "desc": "Fast and fun city commuting.", "img": "https://images.unsplash.com/photo-1547447134-cd3f5c716030?w=800"},
            {"title": "Table Tennis Rackets (Pair)", "price": "15", "type": "rent", "cat": "hobbies", "user_idx": 5, "desc": "Professional grade rackets for competitive play.", "img": "https://images.unsplash.com/photo-1534158914592-062992fbe900?w=800"},
            {"title": "Mountain Bike - Trek", "price": "60", "type": "rent", "cat": "hobbies", "user_idx": 5, "desc": "Durable bike for trail riding.", "img": "https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=800"}
        ]

        for item in items_data:
            new_item = Item(
                title=item['title'], price=item['price'], type=item['type'],
                neighborhood_id=find_seeded_neighborhood('Ashgabat', 'Berkararlyk', 'Central Ashgabat').id,
                description=item['desc'], category=item['cat'],
                user_id=db_users[item['user_idx']].id,
                image_url=item['img']
            )
            db.session.add(new_item)
        db.session.commit()

        review = Review(content="Excellent camera, very well maintained!", rating=5, reviewer_id=db_users[1].id, item_id=1)
        db.session.add(review)
        db.session.commit()

    if not User.query.filter_by(email="friend@handshake.com").first():
        friend_user = User(
            username="friend",
            full_name="Message Friend",
            email="friend@handshake.com",
            password_hash=generate_password_hash("friend123", method='scrypt'),
            region="Ashgabat",
            bio="Seeded test account for chat checks.",
            age=27,
            passport_img="verified.png"
        )
        db.session.add(friend_user)
        db.session.commit()

@app.route('/')
def dashboard():
    all_items = Item.query.order_by(Item.id.desc()).all()
    return render_template('dashboard.html', items=all_items)


def render_marketplace():
    query = (request.args.get('q') or "").strip()
    raw_velayat_id = request.args.get('velayat_id') or ''
    raw_district_id = request.args.get('district_id') or ''
    raw_neighborhood_id = request.args.get('neighborhood_id') or ''

    try:
        velayat_id = int(raw_velayat_id) if raw_velayat_id else None
    except ValueError:
        velayat_id = None

    try:
        district_id = int(raw_district_id) if raw_district_id else None
    except ValueError:
        district_id = None

    try:
        neighborhood_id = int(raw_neighborhood_id) if raw_neighborhood_id else None
    except ValueError:
        neighborhood_id = None

    items_query = Item.query.outerjoin(Neighborhood).outerjoin(District)

    if velayat_id:
        items_query = items_query.filter(District.velayat_id == velayat_id)
    if district_id:
        items_query = items_query.filter(Neighborhood.district_id == district_id)
    if neighborhood_id:
        items_query = items_query.filter(Item.neighborhood_id == neighborhood_id)

    items = items_query.order_by(Item.id.desc()).all()
    if query:
        normalized_query = query.casefold()
        items = [
            item for item in items
            if any(
                normalized_query in (value or '').casefold()
                for value in (
                    item.title,
                    item.description,
                    item.localized_title,
                    item.localized_description,
                    item.category,
                    choice_label('category', item.category),
                )
            )
        ]
    location_tree = get_location_tree()
    selected_location = {
        "velayat_id": velayat_id,
        "district_id": district_id,
        "neighborhood_id": neighborhood_id,
    }
    return render_template(
        'index.html',
        items=items,
        search_query=query,
        location_tree=location_tree,
        selected_location=selected_location,
        expert_query=query if query else ''
    )


@app.route('/market')
def index():
    return render_marketplace()

@app.route('/search')
def search():
    return render_marketplace()

@app.route('/api/expert', methods=['POST'])
def expert_api():
    payload = request.get_json(silent=True) or {}
    item_query = (payload.get('item_query') or '').strip()
    user_request = (payload.get('question') or '').strip()
    if not item_query:
        return jsonify({'error': 'item_query is required'}), 400

    future = expert_executor.submit(live_engine.generate_live_expert_result, item_query, user_request)
    try:
        result = future.result(timeout=30)
    except FuturesTimeoutError:
        future.cancel()
        fallback = live_engine.generate_live_expert_result(item_query, user_request)
        response = jsonify(fallback['payload'])
        response.headers['X-Expert-Source'] = fallback.get('source', 'fallback')
        response.headers['X-Live-Provider-Available'] = 'true' if fallback.get('live_provider_available') else 'false'
        return response
    except Exception:
        return jsonify({'error': 'Expert engine failed'}), 502

    if not result or not result.get('payload'):
        return jsonify({'error': 'No expert data available'}), 503

    response = jsonify(result['payload'])
    response.headers['X-Expert-Source'] = result.get('source', 'unknown')
    response.headers['X-Live-Provider-Available'] = 'true' if result.get('live_provider_available') else 'false'
    return response

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identity = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = User.query.filter(
            (User.email == identity) | (User.username == identity)
        ).first()
        if user and check_password_hash(user.password_hash, password):
            if current_user.is_authenticated:
                logout_user()
            login_user(user)
            return redirect(url_for('index'))
        flash(tr('flash.invalid_login'))
    elif current_user.is_authenticated:
        flash(ui_text('flash.sign_in_switch'))
    return render_template('login.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        if not email:
            flash(tr('flash.email_required'))
            return redirect(url_for('forgot_password'))

        user = User.query.filter_by(email=email).first()
        if user:
            token = build_reset_token(user)
            reset_link = url_for('reset_password', token=token, _external=True)
            try:
                sent = send_password_reset_email(user.email, reset_link)
            except Exception:
                sent = False
                app.logger.exception("Password reset email failed for %s", user.email)
            if not sent:
                app.logger.warning("Email service unavailable. Reset link for %s: %s", user.email, reset_link)
                if ALLOW_LOCAL_RESET_LINK and is_admin_email(user.email):
                    flash(f"Admin local reset link: {reset_link}")
                else:
                    flash(tr('auth.email_service_off'))
                return redirect(url_for('forgot_password', email=email))

        flash(tr('auth.check_email_msg'))
        return redirect(url_for('login'))

    prefill_email = (request.args.get('email') or '').strip().lower()
    return render_template('forgot_password.html', prefill_email=prefill_email)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    payload = verify_reset_token(token, PASSWORD_RESET_TOKEN_TTL_MINUTES * 60)
    if not payload:
        flash(tr('flash.invalid_token'))
        return redirect(url_for('forgot_password'))

    user = User.query.filter_by(id=payload.get('uid'), email=payload.get('email')).first()
    if not user:
        flash(tr('flash.no_account_email'))
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''
        if len(new_password) < 6:
            flash(tr('flash.new_password_len'))
            return redirect(url_for('reset_password', token=token))
        if new_password != confirm_password:
            flash(tr('flash.passwords_mismatch'))
            return redirect(url_for('reset_password', token=token))

        user.password_hash = generate_password_hash(new_password, method='scrypt')
        db.session.commit()
        flash(tr('flash.reset_success'))
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = (request.form.get('email') or "").strip().lower()
        region = (request.form.get('region') or "").strip()
        full_name = (request.form.get('full_name') or "").strip()
        age_value = request.form.get('age')
        password = request.form.get('password') or ""
        confirm_password = request.form.get('confirm_password') or ""

        if not region:
            flash(ui_text('flash.select_region'))
            return redirect(url_for('register'))
        if not full_name:
            flash(ui_text('flash.full_name_required'))
            return redirect(url_for('register'))
        if not age_value or not age_value.isdigit():
            flash(ui_text('flash.valid_age_required'))
            return redirect(url_for('register'))
        if not email:
            flash(ui_text('flash.email_required_general'))
            return redirect(url_for('register'))
        if len(password) < 6:
            flash(ui_text('flash.password_len'))
            return redirect(url_for('register'))
        if password != confirm_password:
            flash(ui_text('flash.passwords_no_match'))
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash(ui_text('flash.email_exists'))
            return redirect(url_for('register'))

        passport_data = request.form.get('passport_image')
        if not passport_data:
            flash(ui_text('flash.passport_required'))
            return redirect(url_for('register'))

        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

        try:
            filename = secure_filename(f"{email}_passport.png")
            passport_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            save_data_url_image(passport_data, passport_path)
        except ValueError:
            flash(ui_text('flash.invalid_passport'))
            return redirect(url_for('register'))

        parsed_age = int(age_value)
        new_user = User(
            username=email.split("@")[0],
            full_name=full_name,
            email=email,
            password_hash=generate_password_hash(password, method='scrypt'),
            region=region,
            age=parsed_age,
            passport_img=filename,
            kyc_status='processing',
            wallet_balance=1000.0 # Start with some mock money
        )
        db.session.add(new_user)
        db.session.commit()
        if current_user.is_authenticated:
            logout_user()
        flash(ui_text('flash.registration_complete'))
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        neighborhood_id = request.form.get('neighborhood_id')
        neighborhood = None
        try:
            neighborhood = Neighborhood.query.get(int(neighborhood_id))
        except (TypeError, ValueError):
            neighborhood = None

        if not neighborhood:
            flash(ui_text('flash.valid_neighborhood'))
            return redirect(url_for('upload'))

        file = request.files.get('item_image')
        camera_image = request.form.get('camera_image')
        image_url = "https://images.unsplash.com/photo-1555685812-4b943f1cb0eb?w=800"

        if not os.path.exists(app.config['UPLOAD_FOLDER_ITEMS']):
            os.makedirs(app.config['UPLOAD_FOLDER_ITEMS'])

        if file and file.filename != '':
            filename = secure_filename(f"{current_user.id}_{datetime.now().timestamp()}_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER_ITEMS'], filename)
            file.save(file_path)
            image_url = url_for('static', filename=f'uploads/items/{filename}')
        elif camera_image:
            filename = secure_filename(f"{current_user.id}_{datetime.now().timestamp()}_capture.png")
            file_path = os.path.join(app.config['UPLOAD_FOLDER_ITEMS'], filename)
            save_data_url_image(camera_image, file_path)
            image_url = url_for('static', filename=f'uploads/items/{filename}')
            
        new_item = Item(
            title=request.form.get('title'), price=request.form.get('price'),
            price_unit=request.form.get('price_unit', 'day'),
            type=request.form.get('type'), neighborhood_id=neighborhood.id,
            description=request.form.get('description'), image_url=image_url,
            category=request.form.get('category'), user_id=current_user.id
        )
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('upload.html', location_tree=get_location_tree())

def parse_price(price_str):
    if not price_str:
        return 0.0
    import re
    cleaned = re.sub(r'[^\d.]', '', price_str)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

@app.route('/buy/<int:item_id>')
@login_required
def buy_item(item_id):
    item = Item.query.get_or_404(item_id)
    duration = request.args.get('duration', 1, type=int)
    
    if item.user_id == current_user.id:
        flash(ui_text('flash.own_item'))
        return redirect(url_for('item_detail', item_id=item_id))

    if not item.is_available:
        flash(ui_text('flash.item_rented'))
        return redirect(url_for('item_detail', item_id=item_id))

    price_val = parse_price(item.price)
    rental_total = price_val * duration if item.type == 'rent' else price_val
    commission = rental_total * 0.05
    deposit = item.deposit_price or (rental_total * 2 if item.type == 'rent' else 0)
    total_val = rental_total + commission + deposit

    # Create a pending negotiation at the listed price
    new_tx = Transaction(
        buyer_id=current_user.id,
        seller_id=item.user_id,
        item_id=item.id,
        amount=price_val,
        duration=duration,
        status='negotiating',
        commission=commission,
        deposit_amount=deposit,
        total_amount=total_val
    )
    db.session.add(new_tx)
    db.session.commit()
    flash(ui_text('flash.rental_request_sent'))
    return redirect(url_for('profile', user_id=current_user.id))

@app.route('/negotiate/<int:item_id>', methods=['POST'])
@login_required
def negotiate(item_id):
    item = Item.query.get_or_404(item_id)
    if item.user_id == current_user.id:
        flash(ui_text('flash.negotiate_self'))
        return redirect(url_for('item_detail', item_id=item_id))

    duration = request.form.get('duration', 1, type=int)
    proposed_price = request.form.get('proposed_price', type=float)

    if not proposed_price:
        flash(ui_text('flash.enter_price'))
        return redirect(url_for('item_detail', item_id=item_id))

    rental_total = proposed_price * duration if item.type == 'rent' else proposed_price
    commission = rental_total * 0.05
    deposit = item.deposit_price or (rental_total * 2 if item.type == 'rent' else 0)
    total_val = rental_total + commission + deposit

    # Create a pending negotiation
    new_tx = Transaction(
        buyer_id=current_user.id,
        seller_id=item.user_id,
        item_id=item.id,
        amount=proposed_price,
        duration=duration,
        status='negotiating',
        commission=commission,
        deposit_amount=deposit,
        total_amount=total_val
    )
    db.session.add(new_tx)
    db.session.commit()
    flash(ui_text('flash.negotiation_sent'))
    return redirect(url_for('profile', user_id=current_user.id))

@app.route('/accept_negotiation/<int:transaction_id>')
@login_required
def accept_negotiation(transaction_id):
    tx = Transaction.query.get_or_404(transaction_id)
    if tx.seller_id != current_user.id:
        flash(ui_text('flash.unauthorized'))
        return redirect(url_for('profile', user_id=current_user.id))

    tx.status = 'accepted'
    db.session.commit()
    flash(ui_text('flash.deal_accepted'))
    return redirect(url_for('profile', user_id=current_user.id))

@app.route('/decline_negotiation/<int:transaction_id>')
@login_required
def decline_negotiation(transaction_id):
    tx = Transaction.query.get_or_404(transaction_id)
    if tx.seller_id != current_user.id and tx.buyer_id != current_user.id:
        flash(ui_text('flash.unauthorized'))
        return redirect(url_for('profile', user_id=current_user.id))

    db.session.delete(tx)
    db.session.commit()
    flash(ui_text('flash.negotiation_cancelled'))
    return redirect(url_for('profile', user_id=current_user.id))

@app.route('/confirm_deal/<int:transaction_id>')
@login_required
def confirm_deal(transaction_id):
    tx = Transaction.query.get_or_404(transaction_id)
    if tx.buyer_id != current_user.id:
        flash(ui_text('flash.only_renter_confirm'))
        return redirect(url_for('index'))
    
    if tx.status != 'accepted':
        flash(ui_text('flash.deal_not_ready'))
        return redirect(url_for('profile', user_id=current_user.id))

    # Calculate final amounts based on negotiated price
    price_val = tx.amount
    
    # SECURITY: Prevent unverified users from renting expensive items
    if price_val > 100 and current_user.kyc_status != 'verified':
        flash(ui_text('flash.verified_required'))
        return redirect(url_for('profile', user_id=current_user.id))

    duration = tx.duration
    rental_total = price_val * duration if tx.item.type == 'rent' else price_val
    commission = rental_total * 0.05
    deposit = tx.item.deposit_price or (rental_total * 2 if tx.item.type == 'rent' else 0)
    total_val = rental_total + commission + deposit
    
    return render_template('payment.html', item=tx.item, price_val=rental_total, commission=commission, deposit=deposit, total_val=total_val, duration=duration, transaction_id=tx.id)

@app.route('/process_negotiated_payment/<int:transaction_id>', methods=['POST'])
@login_required
def process_negotiated_payment(transaction_id):
    tx = Transaction.query.get_or_404(transaction_id)
    if tx.buyer_id != current_user.id:
        flash(ui_text('flash.unauthorized'))
        return redirect(url_for('index'))

    # Recalculate to be sure
    price_val = tx.amount
    duration = tx.duration
    rental_total = price_val * duration if tx.item.type == 'rent' else price_val
    commission = rental_total * 0.05
    deposit = tx.item.deposit_price or (rental_total * 2 if tx.item.type == 'rent' else 0)
    total_val = rental_total + commission + deposit

    if current_user.wallet_balance < total_val:
        flash(ui_text('flash.insufficient_funds'))
        return redirect(url_for('confirm_deal', transaction_id=tx.id))

    try:
        current_user.wallet_balance -= total_val
        seller = User.query.get(tx.seller_id)
        if seller:
            seller.wallet_balance += rental_total

        tx.item.is_available = False
        
        # Cancel all other pending/accepted negotiations for this item
        Transaction.query.filter(
            Transaction.item_id == tx.item_id,
            Transaction.id != tx.id,
            Transaction.status.in_(['negotiating', 'accepted'])
        ).delete()

        tx.commission = commission
        tx.deposit_amount = deposit
        tx.total_amount = total_val
        tx.status = 'active'
        tx.timestamp = datetime.utcnow()
        db.session.commit()

        flash(ui_text('flash.payment_success'))
        return redirect(url_for('profile', user_id=current_user.id))
    except Exception as e:
        db.session.rollback()
        flash(ui_text('flash.transaction_failed'))
        return redirect(url_for('confirm_deal', transaction_id=tx.id))


@app.route('/return_item/<int:transaction_id>')
@login_required
def return_item(transaction_id):
    # This route is used by the SELLER to confirm they got their item back
    tx = Transaction.query.get_or_404(transaction_id)
    if tx.seller_id != current_user.id:
        flash(ui_text('flash.only_owner_return'))
        return redirect(url_for('dashboard'))
    
    if tx.status != 'active':
        flash(ui_text('flash.invalid_action'))
        return redirect(url_for('dashboard'))

    try:
        # Return Deposit to Buyer
        buyer = User.query.get(tx.buyer_id)
        buyer.wallet_balance += tx.deposit_amount
        
        # Mark Item as available
        item = Item.query.get(tx.item_id)
        item.is_available = True
        
        tx.status = 'returned'
        db.session.commit()
        flash(ui_text('flash.return_confirmed'))
    except:
        db.session.rollback()
        flash(ui_text('flash.return_error'))
    return redirect(url_for('dashboard'))

@app.route('/profile/<int:user_id>')
def profile(user_id):
    user = User.query.get_or_404(user_id)
    normalize_user_profile_pic(user)
    reviews = Review.query.filter_by(target_user_id=user_id).all()
    for review in reviews:
        normalize_user_profile_pic(review.reviewer)

    chat_request = None
    has_blocked_user = False
    blocked_by_user = False
    profile_pending_requests = []

    if current_user.is_authenticated:
        if current_user.id != user_id:
            _, chat_request = get_chat_connection_state(current_user.id, user_id)
        has_blocked_user = BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first() is not None
        blocked_by_user = BlockedUser.query.filter_by(blocker_id=user_id, blocked_id=current_user.id).first() is not None
        if current_user.id == user_id:
            profile_pending_requests = ChatRequest.query.filter_by(
                recipient_id=current_user.id,
                status='pending'
            ).order_by(ChatRequest.timestamp.desc()).all()
            for req in profile_pending_requests:
                normalize_user_profile_pic(req.sender)

    return render_template(
        'profile.html',
        user=user,
        reviews=reviews,
        chat_request=chat_request,
        has_blocked_user=has_blocked_user,
        blocked_by_user=blocked_by_user,
        profile_pending_requests=profile_pending_requests
    )

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        full_name = (request.form.get('full_name') or '').strip()
        region = (request.form.get('region') or '').strip()
        bio = (request.form.get('bio') or '').strip()

        if not full_name:
            flash(ui_text('flash.full_name_required'))
            return redirect(url_for('edit_profile'))
        if not region:
            flash(ui_text('flash.location_required'))
            return redirect(url_for('edit_profile'))

        current_user.full_name = full_name
        current_user.bio = bio
        current_user.region = region
        
        # Profile Picture
        file = request.files.get('profile_pic')
        camera_image = request.form.get('camera_image')
        
        if not os.path.exists(app.config['UPLOAD_FOLDER_PROFILES']):
            os.makedirs(app.config['UPLOAD_FOLDER_PROFILES'])
            
        if file and file.filename != '':
            filename = secure_filename(f"profile_{current_user.id}_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER_PROFILES'], filename)
            file.save(file_path)
            current_user.profile_pic = url_for('static', filename=f'uploads/profiles/{filename}')
        elif camera_image:
            filename = secure_filename(f"profile_{current_user.id}_capture.png")
            file_path = os.path.join(app.config['UPLOAD_FOLDER_PROFILES'], filename)
            save_data_url_image(camera_image, file_path)
            current_user.profile_pic = url_for('static', filename=f'uploads/profiles/{filename}')

        normalize_user_profile_pic(current_user)
        db.session.commit()
        return redirect(url_for('profile', user_id=current_user.id))
    return render_template('edit_profile.html')

# Chat Logic
@app.route('/send-chat-request/<int:recipient_id>')
@login_required
def send_chat_request(recipient_id):
    User.query.get_or_404(recipient_id)

    if recipient_id == current_user.id:
        flash(ui_text('flash.chat_self'))
        return redirect(url_for('profile', user_id=recipient_id))

    if BlockedUser.query.filter(
        ((BlockedUser.blocker_id == current_user.id) & (BlockedUser.blocked_id == recipient_id)) |
        ((BlockedUser.blocker_id == recipient_id) & (BlockedUser.blocked_id == current_user.id))
    ).first():
        flash(ui_text('flash.chat_blocked'))
        return redirect(url_for('profile', user_id=recipient_id))

    state, existing = get_chat_connection_state(current_user.id, recipient_id)
    if state == 'none':
        req = ChatRequest(sender_id=current_user.id, recipient_id=recipient_id)
        db.session.add(req)
        db.session.commit()
        flash(ui_text('flash.chat_request_sent'))
    elif state == 'accepted':
        flash(ui_text('flash.chat_active_exists'))
        return redirect(url_for('chat', recipient_id=recipient_id))
    elif state == 'outgoing_pending':
        flash(ui_text('flash.chat_request_exists'))
    else:
        flash(ui_text('flash.chat_request_incoming'))
        return redirect(url_for('chat', tab='requests'))
    return redirect(url_for('profile', user_id=recipient_id))

@app.route('/accept-chat-request/<int:request_id>')
@login_required
def accept_chat_request(request_id):
    req = ChatRequest.query.get_or_404(request_id)
    if req.recipient_id == current_user.id and req.status == 'pending':
        req.status = 'accepted'
        db.session.commit()
        return redirect(url_for('chat', recipient_id=req.sender_id))
    flash(ui_text('flash.chat_request_unavailable'))
    return redirect(url_for('chat'))

@app.route('/reject-chat-request/<int:request_id>')
@login_required
def reject_chat_request(request_id):
    req = ChatRequest.query.get_or_404(request_id)
    if req.recipient_id == current_user.id and req.status == 'pending':
        req.status = 'rejected'
        db.session.delete(req)
        db.session.commit()
    else:
        flash(ui_text('flash.chat_request_unavailable'))
    return redirect(url_for('chat'))

@app.route('/block-user/<int:user_id>')
@login_required
def block_user(user_id):
    if user_id == current_user.id:
        flash(ui_text('flash.block_self'))
        return redirect(url_for('profile', user_id=current_user.id))

    existing = BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).first()
    if not existing:
        block = BlockedUser(blocker_id=current_user.id, blocked_id=user_id)
        db.session.add(block)
        # Also delete any chat requests
        ChatRequest.query.filter(
            ((ChatRequest.sender_id == current_user.id) & (ChatRequest.recipient_id == user_id)) |
            ((ChatRequest.sender_id == user_id) & (ChatRequest.recipient_id == current_user.id))
        ).delete()
        db.session.commit()
    flash(ui_text('flash.user_blocked'))
    return redirect(url_for('index'))

@app.route('/unblock-user/<int:user_id>')
@login_required
def unblock_user(user_id):
    BlockedUser.query.filter_by(blocker_id=current_user.id, blocked_id=user_id).delete()
    db.session.commit()
    flash(ui_text('flash.user_unblocked'))
    return redirect(url_for('profile', user_id=user_id))

@app.route('/chat')
@app.route('/chat/<int:recipient_id>')
@login_required
def chat(recipient_id=None):
    # Only show accepted chats
    accepted_requests = ChatRequest.query.filter(
        ((ChatRequest.sender_id == current_user.id) | (ChatRequest.recipient_id == current_user.id)) &
        (ChatRequest.status == 'accepted')
    ).order_by(ChatRequest.timestamp.desc()).all()
    
    active_chat_users = []
    seen_user_ids = set()
    for req in accepted_requests:
        other_user = req.recipient if req.sender_id == current_user.id else req.sender
        if other_user and other_user.id not in seen_user_ids:
            normalize_user_profile_pic(other_user)
            active_chat_users.append(other_user)
            seen_user_ids.add(other_user.id)

    pending_requests = ChatRequest.query.filter_by(
        recipient_id=current_user.id,
        status='pending'
    ).order_by(ChatRequest.timestamp.desc()).all()
    for req in pending_requests:
        normalize_user_profile_pic(req.sender)

    messages = []
    active_recipient = None
    initial_tab = request.args.get('tab', 'chats')
    if initial_tab not in ('chats', 'requests'):
        initial_tab = 'chats'
    if 'tab' not in request.args and pending_requests:
        initial_tab = 'requests'

    if recipient_id:
        state, _ = get_chat_connection_state(current_user.id, recipient_id)

        if state == 'accepted':
            active_recipient = User.query.get_or_404(recipient_id)
            normalize_user_profile_pic(active_recipient)
            messages = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.recipient_id == recipient_id)) |
                ((Message.sender_id == recipient_id) & (Message.recipient_id == current_user.id))
            ).order_by(Message.timestamp.asc()).all()
            initial_tab = 'chats'
        elif state == 'incoming_pending':
            flash(ui_text('flash.accept_request_first'))
            return redirect(url_for('chat', tab='requests'))
        elif state == 'outgoing_pending':
            flash(ui_text('flash.request_pending'))
            return redirect(url_for('chat'))
        else:
            flash(ui_text('flash.send_request_first'))
            return redirect(url_for('profile', user_id=recipient_id))

    if initial_tab == 'chats' and not active_recipient and pending_requests and not active_chat_users:
        initial_tab = 'requests'

    return render_template(
        'chat.html',
        active_chat_users=active_chat_users,
        pending_requests=pending_requests,
        messages=messages,
        active_recipient=active_recipient,
        initial_tab=initial_tab
    )

@app.route('/send_message', methods=['POST'])
@login_required
def send_message():
    recipient_id = request.form.get('recipient_id')
    body = (request.form.get('body') or '').strip()

    try:
        recipient_id = int(recipient_id)
    except (TypeError, ValueError):
        flash(ui_text('flash.invalid_recipient'))
        return redirect(url_for('chat'))
    
    # Check if either side has blocked the other.
    if BlockedUser.query.filter(
        ((BlockedUser.blocker_id == recipient_id) & (BlockedUser.blocked_id == current_user.id)) |
        ((BlockedUser.blocker_id == current_user.id) & (BlockedUser.blocked_id == recipient_id))
    ).first():
        flash(ui_text('flash.messaging_blocked'))
        return redirect(url_for('chat'))

    if not has_accepted_chat_between(current_user.id, recipient_id):
        flash(ui_text('flash.accepted_chat_required'))
        return redirect(url_for('profile', user_id=recipient_id))

    if recipient_id and body:
        msg = Message(sender_id=current_user.id, recipient_id=recipient_id, body=body)
        db.session.add(msg)
        db.session.commit()
        return redirect(url_for('chat', recipient_id=recipient_id))
    return redirect(url_for('chat'))

@app.route('/item/<int:item_id>')
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)
    reviews = Review.query.filter_by(item_id=item_id).all()
    chat_request = None
    chat_state = 'none'
    if current_user.is_authenticated and item.owner and current_user.id != item.owner.id:
        chat_state, chat_request = get_chat_connection_state(current_user.id, item.owner.id)
    return render_template('item_detail.html', item=item, reviews=reviews, chat_request=chat_request, chat_state=chat_state)

@app.route('/rate_item/<int:item_id>', methods=['POST'])
@login_required
def rate_item(item_id):
    item = Item.query.get_or_404(item_id)
    rating = int(request.form.get('rating') or 0)
    content = (request.form.get('content') or '').strip()
    if rating < 1 or rating > 5:
        flash(ui_text('flash.rating_range'))
        return redirect(url_for('item_detail', item_id=item_id))
    if not content:
        flash(ui_text('flash.review_empty'))
        return redirect(url_for('item_detail', item_id=item_id))
    review = Review(content=content, rating=rating, reviewer_id=current_user.id, item_id=item_id)
    item.rating = (item.rating * item.num_ratings + rating) / (item.num_ratings + 1)
    item.num_ratings += 1
    db.session.add(review)
    db.session.commit()
    return redirect(url_for('item_detail', item_id=item_id))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))






    



if __name__ == '__main__':
    app.run(debug=True)
