from flask import Flask, jsonify, request, session, redirect, send_from_directory
from flask_cors import CORS
from database import Session, User, Chat, Code, Setting, init_db
from datetime import datetime, timedelta
import config, os, logging

logging.basicConfig(level=logging.INFO)
app = Flask(__name__, template_folder='templates')
app.secret_key = config.SECRET_KEY
CORS(app)
init_db()

from bot import start_bot, bot_running
start_bot()

def auth():
    return session.get('authenticated', False)

@app.route('/')
def index():
    if not auth(): return redirect('/login')
    return send_from_directory('templates', 'index.html')

@app.route('/login')
def login_page():
    return send_from_directory('templates', 'login.html')

@app.route('/settings')
def settings_page():
    if not auth(): return redirect('/login')
    return send_from_directory('templates', 'settings.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    db = Session()
    s = db.query(Setting).filter_by(key='admin_password').first()
    stored = s.value if s else config.ADMIN_PASSWORD
    db.close()
    if data.get('password') == stored:
        session['authenticated'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'كلمة المرور غير صحيحة'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/stats')
def stats():
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    db = Session()
    result = {
        'total_users': db.query(User).count(),
        'total_chats': db.query(Chat).count(),
        'total_codes': db.query(Code).count(),
        'active_today': db.query(User).filter(User.last_active >= datetime.utcnow() - timedelta(days=1)).count(),
        'bot_active': bot_running
    }
    db.close()
    return jsonify(result)

@app.route('/api/chats')
def chats():
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    db = Session()
    limit = int(request.args.get('limit', 50))
    rows = db.query(Chat).order_by(Chat.timestamp.desc()).limit(limit).all()
    result = []
    for c in rows:
        u = db.query(User).filter_by(id=c.user_id).first()
        result.append({'id': c.id, 'user': u.first_name if u else 'مجهول', 'username': u.username if u else '', 'message': c.message, 'response': (c.response or '')[:200], 'timestamp': c.timestamp.isoformat() if c.timestamp else '', 'type': c.type})
    db.close()
    return jsonify(result)

@app.route('/api/codes')
def codes():
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    db = Session()
    rows = db.query(Code).order_by(Code.timestamp.desc()).limit(30).all()
    result = []
    for c in rows:
        u = db.query(User).filter_by(id=c.user_id).first()
        result.append({'id': c.id, 'user': u.first_name if u else 'مجهول', 'language': c.language, 'description': c.description, 'timestamp': c.timestamp.isoformat() if c.timestamp else ''})
    db.close()
    return jsonify(result)

@app.route('/api/users')
def users():
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    db = Session()
    rows = db.query(User).order_by(User.last_active.desc()).all()
    result = [{'id': u.id, 'telegram_id': u.telegram_id, 'username': u.username, 'first_name': u.first_name, 'last_name': u.last_name, 'first_seen': u.first_seen.isoformat() if u.first_seen else '', 'last_active': u.last_active.isoformat() if u.last_active else '', 'chats_count': u.chats_count, 'codes_count': u.codes_count, 'is_banned': u.is_banned} for u in rows]
    db.close()
    return jsonify(result)

@app.route('/api/users/<int:uid>/ban', methods=['POST'])
def ban_user(uid):
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    db = Session()
    u = db.query(User).filter_by(id=uid).first()
    if u:
        u.is_banned = not u.is_banned
        db.commit()
        status = u.is_banned
    db.close()
    return jsonify({'success': True, 'banned': status})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    db = Session()
    result = {s.key: s.value for s in db.query(Setting).all() if s.key != 'admin_password'}
    db.close()
    return jsonify(result)

@app.route('/api/settings', methods=['POST'])
def update_settings():
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    db = Session()
    for key, value in request.json.items():
        s = db.query(Setting).filter_by(key=key).first()
        if s:
            s.value = value
        else:
            db.add(Setting(key=key, value=value))
    db.commit()
    db.close()
    return jsonify({'success': True})

@app.route('/api/bot/toggle', methods=['POST'])
def toggle_bot():
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    db = Session()
    s = db.query(Setting).filter_by(key='bot_active').first()
    new_val = 'false' if (s and s.value == 'true') else 'true'
    if s:
        s.value = new_val
    else:
        db.add(Setting(key='bot_active', value=new_val))
    db.commit()
    db.close()
    return jsonify({'success': True, 'active': new_val == 'true'})

@app.route('/api/broadcast', methods=['POST'])
def broadcast():
    if not auth(): return jsonify({'error': 'غير مصرح'}), 401
    import asyncio
    from telegram import Bot
    message = request.json.get('message', '')
    if not message: return jsonify({'error': 'الرسالة فارغة'}), 400
    db = Session()
    ids = [u.telegram_id for u in db.query(User).filter_by(is_banned=False).all()]
    db.close()
    async def send_all():
        bot = Bot(token=config.BOT_TOKEN)
        sent = 0
        for tid in ids:
            try:
                await bot.send_message(chat_id=tid, text=message)
                sent += 1
            except: pass
        return sent
    try:
        sent = asyncio.run(send_all())
        return jsonify({'success': True, 'sent': sent})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'bot_running': bot_running})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config.PORT, debug=False)
