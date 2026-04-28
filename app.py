import os
import random
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

load_dotenv()

DATABASE = "database.db"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
app.secret_key = os.getenv("SECRET_KEY", "запасной-секретный-ключ")

SEED_LETTERS = [
    "Ты не один. Даже если кажется, что весь мир отвернулся, где-то есть человек, которому ты важен.",
    "Это чувство не навсегда. Оно как гроза — может быть страшным и долгим, но дождь обязательно закончится.",
    "Разреши себе просто быть. Прямо сейчас от тебя не требуется быть продуктивным или счастливым. Просто дыши.",
    "Твоя история ещё не дописана. Самая важная глава может начаться завтра. Останься, чтобы её прочитать.",
    "Спасибо, что ты всё ещё здесь. Это уже говорит о твоей огромной внутренней силе.",
    "Маленький шаг — тоже шаг. Выпить стакан воды, умыться, открыть окно — это победа.",
    "Ты больше, чем твои ошибки. Прошлое не определяет твоё будущее, каким бы тяжёлым оно ни было.",
    "Мир станет тусклее без тебя. Твой свет уникален, даже если ты сам его пока не видишь.",
    "Обратиться за помощью — это смелость. Пожалуйста, не бойся протянуть руку специалисту.",
    "Ты — не обуза для близких. Твои чувства важны, и ты имеешь право говорить о них.",
]


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS letters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            helpful_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mood_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            score INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            helped TEXT DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    try:
        cursor.execute("ALTER TABLE letters ADD COLUMN needs_review INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE letters ADD COLUMN report_reason TEXT")
    except sqlite3.OperationalError:
        pass

    cursor.execute("SELECT COUNT(*) FROM letters")
    count = cursor.fetchone()[0]

    if count == 0:
        for letter_text in SEED_LETTERS:
            cursor.execute(
                "INSERT INTO letters (content, status) VALUES (?, ?)",
                (letter_text, "approved"),
            )
        print(f"[DB] Загружено {len(SEED_LETTERS)} начальных писем.")

    conn.commit()
    conn.close()
    print("[DB] База данных готова к работе.")


with app.app_context():
    init_db()


@app.route("/")
def home():
    return render_template("index.html")


@app.route('/api/letter')
def get_letter():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        'SELECT id, content, helpful_count FROM letters WHERE status = ? ORDER BY RANDOM() LIMIT 1',
        ('approved',)
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return jsonify({'id': None, 'content': 'Пока нет одобренных писем. Загляни позже.', 'helpful_count': 0})

    return jsonify({'id': row['id'], 'content': row['content'], 'helpful_count': row['helpful_count']})


@app.route("/api/feedback", methods=["POST"])
def send_feedback():
    data = request.get_json()
    letter_id = data.get("id")

    if letter_id is None:
        return jsonify({"status": "error", "message": "Не указан id письма"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE letters SET helpful_count = helpful_count + 1 WHERE id = ?",
        (letter_id,),
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok", "message": "Спасибо за твой отклик!"})


@app.route("/api/report", methods=["POST"])
def report_letter():
    data = request.get_json()
    letter_id = data.get("id")
    reason = data.get("reason", "не указана")

    if letter_id is None:
        return jsonify({"status": "error", "message": "Не указан id письма"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE letters SET needs_review = 1, reported_at = CURRENT_TIMESTAMP, report_reason = ? WHERE id = ?",
        (reason, letter_id),
    )
    conn.commit()
    conn.close()

    return jsonify(
        {"status": "ok", "message": "Спасибо, письмо отправлено на проверку."}
    )


@app.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        captcha_answer = request.form.get("captcha_answer", "")
        captcha_sum = request.form.get("captcha_sum", "")

        if not content:
            return render_template(
                "submit.html",
                error="Поле не может быть пустым. Напиши хотя бы пару слов.",
                captcha_a=random.randint(1, 10),
                captcha_b=random.randint(1, 10),
            )
        if len(content) < 10:
            return render_template(
                "submit.html",
                error="Письмо слишком короткое. Пожалуйста, напиши чуть больше — хотя бы 10 символов.",
                captcha_a=random.randint(1, 10),
                captcha_b=random.randint(1, 10),
            )
        if len(content) > 1500:
            return render_template(
                "submit.html",
                error="Письмо слишком длинное. Максимум 1500 символов.",
                captcha_a=random.randint(1, 10),
                captcha_b=random.randint(1, 10),
            )

        try:
            if int(captcha_answer) != int(captcha_sum):
                return render_template(
                    "submit.html",
                    error="Неверный ответ на проверочный вопрос. Попробуй ещё раз.",
                    captcha_a=random.randint(1, 10),
                    captcha_b=random.randint(1, 10),
                )
        except (ValueError, TypeError):
            return render_template(
                "submit.html",
                error="Пожалуйста, введи число.",
                captcha_a=random.randint(1, 10),
                captcha_b=random.randint(1, 10),
            )

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO letters (content, status) VALUES (?, ?)", (content, "pending")
        )
        conn.commit()
        conn.close()

        return render_template("submit.html", success=True)

    a = random.randint(1, 10)
    b = random.randint(1, 10)
    return render_template("submit.html", captcha_a=a, captcha_b=b)


@app.route("/moderate", methods=["GET", "POST"])
def moderate():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        letter_id = request.form.get("id")
        action = request.form.get("action")

        if action == "approve":
            cursor.execute(
                "UPDATE letters SET status = ?, needs_review = 0 WHERE id = ?",
                ("approved", letter_id),
            )
        elif action == "reject":
            cursor.execute(
                "UPDATE letters SET status = ?, needs_review = 0 WHERE id = ?",
                ("rejected", letter_id),
            )

        conn.commit()

    cursor.execute(
        "SELECT id, content, created_at FROM letters WHERE status = ? ORDER BY created_at DESC LIMIT 20",
        ("pending",),
    )
    pending_letters_raw = cursor.fetchall()

    cursor.execute(
        "SELECT id, content, created_at, report_reason, helpful_count FROM letters WHERE needs_review = 1 AND status = ? ORDER BY created_at DESC LIMIT 10",
        ("approved",),
    )
    flagged_letters_raw = cursor.fetchall()

    def format_time(letters_list):
        result = []
        for letter in letters_list:
            letter_dict = dict(letter)
            raw_time = letter_dict.get("created_at")
            if raw_time:
                try:
                    dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
                    letter_dict["created_at"] = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass
            result.append(letter_dict)
        return result

    pending_letters = format_time(pending_letters_raw)
    flagged_letters = format_time(flagged_letters_raw)

    cursor.execute("SELECT COUNT(*) FROM letters WHERE status = ?", ("approved",))
    approved_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM letters WHERE status = ?", ("pending",))
    pending_count = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM letters WHERE needs_review = 1 AND status = ?",
        ("approved",),
    )
    flagged_count = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "moderate.html",
        approved_count=approved_count,
        pending_count=pending_count,
        flagged_count=flagged_count,
        pending_letters=pending_letters,
        flagged_letters=flagged_letters,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("moderate"))
        else:
            error = "Неверный пароль"

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Вход — Тихая гавань</title>
        <link rel="stylesheet" href="/static/css/style.css">
    </head>
    <body>
        <div class="moderation-login">
            <h2>Вход в админку</h2>
            {'<div class="error-message">' + error + '</div>' if error else ''}
            <form method="POST">
                <input type="password" name="password" placeholder="Пароль" required>
                <button type="submit" class="btn btn-primary btn-full" style="margin-top: 0.5rem;">Войти</button>
            </form>
            <a href="/" class="back-link">На главную</a>
        </div>
    </body>
    </html>
    """


@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))


@app.route("/api/stats")
def get_stats():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM letters WHERE status = ?", ("approved",))
    total_approved = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM letters")
    total_all = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(helpful_count), 0) FROM letters")
    total_helpful = cursor.fetchone()[0]

    conn.close()

    return jsonify(
        {
            "total_approved": total_approved,
            "total_all": total_all,
            "total_helpful": total_helpful,
        }
    )

@app.route('/robots.txt')
def robots():
    return '''User-agent: *
Allow: /
Sitemap: https://thequietharbor.ru/sitemap.xml
''', 200, {'Content-Type': 'text/plain'}

@app.route('/sitemap.xml')
def sitemap():
    pages = [
        {'loc': 'https://thequietharbor.ru/', 'priority': '1.0'},
        {'loc': 'https://thequietharbor.ru/submit', 'priority': '0.8'},
    ]
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for page in pages:
        xml += '  <url>\n'
        xml += f'    <loc>{page["loc"]}</loc>\n'
        xml += f'    <priority>{page["priority"]}</priority>\n'
        xml += '  </url>\n'
    xml += '</urlset>'
    
    return xml, 200, {'Content-Type': 'application/xml'}

@app.route('/mood')
def mood():
    return render_template('mood.html')


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
