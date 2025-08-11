import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler, ContextTypes
from telegram.helpers import escape_markdown
import telegram.error

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Настройка базы данных ---
def setup_database():
    """Инициализирует базу данных SQLite и создает таблицы, если они не существуют."""
    conn = sqlite3.connect("rootzsu_bot.db")
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT
    )
    """)

    # Таблица услуг (Прайс-лист)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS services (
        service_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        price_usd REAL,
        price_btc REAL,
        price_stars INTEGER
    )
    """)

    # Таблица заказов
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        service_id INTEGER,
        payment_method TEXT,
        status TEXT DEFAULT 'pending_payment',
        payment_proof TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id),
        FOREIGN KEY (service_id) REFERENCES services (service_id)
    )
    """)
    conn.commit()
    conn.close()

def add_initial_services():
    """Добавляет начальные услуги в базу данных, если они отсутствуют."""
    conn = sqlite3.connect("rootzsu_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM services")
    if cursor.fetchone()[0] == 0:
        services_data = [
            ("Разблокировка загрузчика", "Для мобильных устройств", 15.0, 0.00015, 1000),
            ("Установка root-прав", "Для мобильных устройств", 3.0, 0.00002478, 100),
            ("Прошивка устройств", "Полная переустановка системы", 27.0, 0.000223, 2800),
            ("Установка ОС (ПК)", "Windows, Linux", 11.0, 0.00009085, 1280),
            ("Восстановление файлов", "С жестких дисков и SSD", 20.0, 0.00016518, 2200),
            ("Реанимация флеш-накопителей", "Восстановление USB-накопителей", 25.0, 0.00042, 2050)
        ]
        cursor.executemany("INSERT INTO services (name, description, price_usd, price_btc, price_stars) VALUES (?, ?, ?, ?, ?)", services_data)
        conn.commit()
    conn.close()

# --- Конфигурация админа ---
ADMIN_IDS = [7498691085]  # Замените на ваш реальный ID Telegram

# --- Состояния беседы ---
SELECTING_SERVICE, SELECTING_PAYMENT, UPLOADING_PROOF, ADMIN_CHAT = range(4)

# --- Вспомогательные функции ---
def get_db_connection():
    """Устанавливает соединение с базой данных."""
    conn = sqlite3.connect("rootzsu_bot.db")
    conn.row_factory = sqlite3.Row
    return conn

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_IDS

# --- Обработчики команд пользователя ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает команду /start и показывает главное меню."""
    user = update.effective_user
    user_id = user.id
    username = user.username
    first_name = user.first_name

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                       (user_id, username, first_name))
        conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("📋 Прайс-лист", callback_data="price_list")],
        [InlineKeyboardButton("🛒 Заказать услугу", callback_data="order_service")],
        [InlineKeyboardButton("👤 Мой кабинет", callback_data="my_account")],
        [InlineKeyboardButton("💬 Связаться с админом", callback_data="contact_admin")],
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    safe_first_name = escape_markdown(first_name)
    welcome_text = f"Добро пожаловать в *rootzsu*, {safe_first_name}!\n\nВыберите действие:"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    return 0

async def price_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список услуг и их цены."""
    query = update.callback_query
    await query.answer()

    conn = get_db_connection()
    services = conn.execute("SELECT * FROM services").fetchall()
    conn.close()

    if not services:
        await query.edit_message_text("Прайс-лист пока пуст.")
        return

    message_text = "*📋 НАШ ПРАЙС-ЛИСТ 📋*\n\n"
    for service in services:
        safe_name = escape_markdown(service['name'])
        safe_desc = escape_markdown(service['description'])
        message_text += (
            f"🔹 *{safe_name}*\n"
            f"   _{safe_desc}_\n"
            f"   *Цена:* ${service['price_usd']} | {service['price_btc']} BTC | {service['price_stars']} ⭐\n\n"
        )

    keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')

# --- Процесс заказа ---
async def order_service_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс создания заказа, показывая услуги."""
    query = update.callback_query
    await query.answer()

    conn = get_db_connection()
    services = conn.execute("SELECT service_id, name FROM services").fetchall()
    conn.close()

    if not services:
        await query.edit_message_text("Извините, в данный момент нет доступных услуг для заказа.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(s['name'], callback_data=f"select_service_{s['service_id']}")] for s in services]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_order")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("Пожалуйста, выберите услугу из списка:", reply_markup=reply_markup)
    return SELECTING_SERVICE

async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает варианты оплаты для выбранной услуги."""
    query = update.callback_query
    service_id = int(query.data.split('_')[-1])
    context.user_data['service_id'] = service_id
    await query.answer()

    conn = get_db_connection()
    service = conn.execute("SELECT * FROM services WHERE service_id = ?", (service_id,)).fetchone()
    conn.close()
    
    safe_name = escape_markdown(service['name'])
    text = f"Вы выбрали: *{safe_name}*\n\nВыберите способ оплаты:"
    keyboard = [
        [InlineKeyboardButton(f"💵 USD (${service['price_usd']})", callback_data=f"pay_usd_{service_id}")],
        [InlineKeyboardButton(f"🪙 BTC ({service['price_btc']})", callback_data=f"pay_btc_{service_id}")],
        [InlineKeyboardButton(f"⭐ Stars ({service['price_stars']})", callback_data=f"pay_stars_{service_id}")],
        [InlineKeyboardButton("⬅️ Назад к услугам", callback_data="order_service")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='Markdown')
    return SELECTING_PAYMENT

async def process_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор способа оплаты и запрашивает подтверждение оплаты."""
    query = update.callback_query
    parts = query.data.split('_')
    payment_method = parts[1].upper()
    service_id = int(parts[2])

    context.user_data['payment_method'] = payment_method
    await query.answer()

    # Создаем заказ в базе данных
    user_id = query.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO orders (user_id, service_id, payment_method) VALUES (?, ?, ?)",
                   (user_id, service_id, payment_method))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    context.user_data['order_id'] = order_id

    payment_details = {
        'USD': "Пожалуйста, переведите оплату на `UQCKtm0RoDtPCyObq18G-FKehsDPaVIiVX5Z8q78P_XfmTUh`.",
        'BTC': "Пожалуйста, переведите оплату на `UQCKtm0RoDtPCyObq18G-FKehsDPaVIiVX5Z8q78P_XfmTUh`.",
        'STARS': "Пожалуйста, используйте встроенную функцию Telegram для отправки Stars."
    }

    text = (
        f"Ваш заказ `#{order_id}` создан.\n\n"
        f"{payment_details[payment_method]}\n\n"
        "После оплаты, пожалуйста, *отправьте скриншот или фото чека* в этот чат для подтверждения."
    )
    await query.edit_message_text(text=text, parse_mode='Markdown')
    return UPLOADING_PROOF

async def upload_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает загрузку подтверждения оплаты."""
    photo = update.message.photo[-1]  # Берем фото с самым высоким разрешением
    file_id = photo.file_id
    order_id = context.user_data.get('order_id')

    if not order_id:
        await update.message.reply_text("Произошла ошибка. Пожалуйста, начните процесс заказа заново.")
        return ConversationHandler.END

    # Обновляем заказ с подтверждением и меняем статус
    conn = get_db_connection()
    conn.execute("UPDATE orders SET payment_proof = ?, status = 'pending_approval' WHERE order_id = ?",
                 (file_id, order_id))
    conn.commit()
    service = conn.execute(
        "SELECT s.name FROM services s JOIN orders o ON s.service_id = o.service_id WHERE o.order_id = ?",
        (order_id,)
    ).fetchone()
    conn.close()

    await update.message.reply_text(
        "✅ Спасибо! Ваше подтверждение получено и отправлено на проверку администратору.\n"
        "Вы получите уведомление, как только ваш заказ будет одобрен."
    )

    # Уведомляем админа
    safe_service_name = escape_markdown(service['name'], version=2)
    admin_text = (
        f"🔔 *Новое подтверждение оплаты\\!*\n\n"
        f"Заказ: `#{order_id}`\n"
        f"Пользователь: {update.effective_user.mention_markdown_v2()}\n"
        f"Услуга: *{safe_service_name}*"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"admin_approve_{order_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_decline_{order_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text="Пользователь прислал подтверждение оплаты. Фото ниже:")
            await context.bot.send_photo(
                chat_id=admin_id, 
                photo=file_id, 
                caption=admin_text, 
                reply_markup=reply_markup, 
                parse_mode='MarkdownV2'
            )
        except telegram.error.BadRequest as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

    return ConversationHandler.END

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет процесс создания заказа."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Заказ отменен.")
    context.user_data.clear()
    await start(update, context)
    return ConversationHandler.END

# --- Личный кабинет и админ-панель ---
async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает информацию о пользователе и историю заказов."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    conn = get_db_connection()
    orders = conn.execute("""
        SELECT o.order_id, o.status, s.name
        FROM orders o
        JOIN services s ON o.service_id = s.service_id
        WHERE o.user_id = ?
    """, (user_id,)).fetchall()
    conn.close()

    status_translation = {
        'pending_payment': 'Ожидает оплаты',
        'pending_approval': 'На проверке',
        'approved': 'Одобрен',
        'declined': 'Отклонен'
    }

    if not orders:
        message_text = "У вас пока нет заказов."
    else:
        message_text = "*👤 ВАШИ ЗАКАЗЫ 👤*\n\n"
        for order in orders:
            safe_name = escape_markdown(order['name'])
            message_text += f"🔹 Заказ `#{order['order_id']}` - *{safe_name}*\n   Статус: _{status_translation.get(order['status'], 'Неизвестно')}_\n"

    keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает админ-панель."""
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("У вас нет доступа.", show_alert=True)
        return

    await query.answer()
    keyboard = [
        [InlineKeyboardButton("👥 Все пользователи", callback_data="admin_view_users")],
        [InlineKeyboardButton("📦 Все заказы", callback_data="admin_view_orders")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("👑 *Админ-панель*", reply_markup=reply_markup, parse_mode='Markdown')

async def admin_view_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ: показывает всех пользователей."""
    query = update.callback_query
    await query.answer()

    conn = get_db_connection()
    users = conn.execute("SELECT user_id, first_name, username FROM users").fetchall()
    conn.close()

    message_text = "*👥 Список пользователей:*\n\n"
    for user in users:
        safe_name = escape_markdown(user['first_name'] or "N/A")
        safe_username = escape_markdown(user['username'] or "N/A")
        message_text += f"ID: `{user['user_id']}` - {safe_name} (@{safe_username})\n"

    keyboard = [[InlineKeyboardButton("⬅️ Назад в админку", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ: показывает все заказы."""
    query = update.callback_query
    await query.answer()

    conn = get_db_connection()
    orders = conn.execute("""
        SELECT o.order_id, o.user_id, o.status, s.name, u.first_name, u.username
        FROM orders o
        JOIN services s ON o.service_id = s.service_id
        JOIN users u ON o.user_id = u.user_id
    """).fetchall()
    conn.close()

    if not orders:
        message_text = "Заказов пока нет."
    else:
        message_text = "*📦 Список всех заказов:*\n\n"
        for order in orders:
            safe_service_name = escape_markdown(order['name'])
            user_info = []
            if order['first_name']:
                user_info.append(escape_markdown(order['first_name']))
            if order['username']:
                user_info.append(f"(@{escape_markdown(order['username'])})")
            
            user_display = " ".join(user_info) if user_info else f"ID: {order['user_id']}"

            message_text += (
                f"🔹 *Заказ `#{order['order_id']}`* | {user_display}\n"
                f"   Услуга: *{safe_service_name}*\n"
                f"   Статус: _{order['status']}_\n\n"
            )

    keyboard = [[InlineKeyboardButton("⬅️ Назад в админку", callback_data="admin_panel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def admin_handle_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает решение админа по заказу (одобрить/отклонить)."""
    query = update.callback_query
    action, order_id_str = query.data.split('_')[1:]
    order_id = int(order_id_str)
    await query.answer(f"Заказ #{order_id} был обработан.")

    new_status = 'approved' if action == 'approve' else 'declined'
    
    conn = get_db_connection()
    conn.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
    conn.commit()
    order_info = conn.execute(
        "SELECT user_id, s.name FROM orders o JOIN services s ON o.service_id = s.service_id WHERE o.order_id = ?", 
        (order_id,)
    ).fetchone()
    conn.close()

    if not order_info:
        await query.edit_message_caption(
            caption=f"{query.message.caption}\n\n--- ОШИБКА: Заказ #{order_id} не найден в базе данных. ---", 
            reply_markup=None
        )
        return

    user_id = order_info['user_id']
    service_name = escape_markdown(order_info['name'], version=2)
    
    user_message = ""
    if new_status == 'approved':
        user_message = f"✅ Ваш заказ `#{order_id}` на услугу *{service_name}* был *одобрен*! Администратор скоро свяжется с вами для уточнения деталей."
    else:
        user_message = f"❌ К сожалению, ваш заказ `#{order_id}` на услугу *{service_name}* был *отклонен*. Пожалуйста, свяжитесь с администратором для выяснения причин."
    
    try:
        await context.bot.send_message(
            chat_id=user_id, 
            text=user_message, 
            parse_mode='MarkdownV2'
        )
    except telegram.error.BadRequest as e:
        logger.error(f"Не удалось отправить обновление статуса пользователю {user_id}: {e}")
        
    original_caption = query.message.caption_markdown_v2
    status_text = escape_markdown(f"Статус обновлен на: {new_status.upper()}", version=2)

    await query.edit_message_caption(
        caption=f"{original_caption}\n\n\\-\\-\\-\n*{status_text}*",
        parse_mode='MarkdownV2', 
        reply_markup=None
    )

# --- Чат с админом ---
async def contact_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает чат с администратором."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Вы вошли в режим чата с администратором. "
        "Напишите ваше сообщение, и оно будет переслано. "
        "Для выхода из чата отправьте /cancel."
    )
    return ADMIN_CHAT

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пересылает сообщение пользователя всем админам."""
    user = update.effective_user
    text_to_forward = (
        f"💬 *Сообщение от пользователя {user.mention_markdown_v2()}* \\(ID: `{user.id}`\\):\n\n"
        f"{escape_markdown(update.message.text, version=2)}"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id, 
                text=text_to_forward, 
                parse_mode='MarkdownV2'
            )
        except telegram.error.BadRequest as e:
            logger.error(f"Не удалось переслать сообщение админу {admin_id}: {e}")

    await update.message.reply_text("Ваше сообщение отправлено администратору.")
    return ADMIN_CHAT

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Позволяет админу ответить на сообщение пользователя."""
    if not is_admin(update.effective_user.id):
        return

    reply_msg = update.message.reply_to_message
    if reply_msg and reply_msg.from_user and reply_msg.from_user.is_bot:
        original_msg = reply_msg.text or ""
        try:
            # Парсим ID из текста, ищем шаблон (ID: `123456789`)
            user_id_str = original_msg.split("(ID: `")[1].split("`)")[0]
            user_id = int(user_id_str)
        except (IndexError, ValueError):
            await update.message.reply_text(
                "Не удалось определить пользователя для ответа. Убедитесь, что вы отвечаете на сообщение, где есть (ID: `user_id`)"
            )
            return

        reply_text = (
            f"✉️ *Ответ от администратора:*\n\n"
            f"{escape_markdown(update.message.text, version=2)}"
        )
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=reply_text,
                parse_mode='MarkdownV2'
            )
            await update.message.reply_text("✅ Ваш ответ отправлен пользователю.")
        except Exception as e:
            await update.message.reply_text(f"Ошибка при отправке сообщения: {e}")
    else:
        await update.message.reply_text(
            "Пожалуйста, ответьте на сообщение бота, чтобы отправить ответ пользователю."
        )

async def cancel_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выходит из режима чата с админом."""
    await update.message.reply_text("Вы вышли из режима чата с администратором.")
    await start(update, context)
    return ConversationHandler.END

def main() -> None:
    """Запускает бота."""
    application = Application.builder().token("8243984344:AAH3SFyuy4I_O62Ml8KcxCgyZTQ4ZVYKep0").build()

    setup_database()
    add_initial_services()
    # Обработчик процесса заказа
    order_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(order_service_start, pattern='^order_service$')],
        states={
            SELECTING_SERVICE: [CallbackQueryHandler(select_payment_method, pattern='^select_service_')],
            SELECTING_PAYMENT: [CallbackQueryHandler(process_payment_selection, pattern='^pay_')],
            UPLOADING_PROOF: [MessageHandler(filters.PHOTO, upload_proof)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_order, pattern='^cancel_order$'),
            CallbackQueryHandler(order_service_start, pattern='^order_service$')
        ],
        map_to_parent={ConversationHandler.END: 0},
        per_message=False
    )
    
    # Обработчик чата с админом
    admin_chat_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(contact_admin_start, pattern='^contact_admin$')],
        states={
            ADMIN_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_admin)]
        },
        fallbacks=[CommandHandler('cancel', cancel_chat)],
        map_to_parent={ConversationHandler.END: 0},
        per_message=False
    )

    # Главный обработчик
    main_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            0: [
                CallbackQueryHandler(start, pattern='^main_menu$'),
                CallbackQueryHandler(price_list, pattern='^price_list$'),
                CallbackQueryHandler(my_account, pattern='^my_account$'),
                CallbackQueryHandler(admin_panel, pattern='^admin_panel$'),
                CallbackQueryHandler(admin_view_users, pattern='^admin_view_users$'),
                CallbackQueryHandler(admin_view_orders, pattern='^admin_view_orders$'),
                CallbackQueryHandler(admin_handle_order, pattern='^admin_(approve|decline)_'),
                order_conv_handler,
                admin_chat_conv_handler,
            ]
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False
    )

    application.add_handler(main_handler)
    application.add_handler(MessageHandler(filters.REPLY & filters.User(user_id=ADMIN_IDS), reply_to_user))

    application.run_polling()

if __name__ == "__main__":
    main()