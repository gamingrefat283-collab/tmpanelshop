import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime, timedelta
import os

# Bot configuration - USE ENVIRONMENT VARIABLES IN PRODUCTION
BOT_TOKEN = os.getenv('BOT_TOKEN', "7767040819:AAFJfbJr2qFFVzeQCPkF54QeesYjAl7ssAw")
ADMIN_IDS = [5798359099]  # Your user ID
STORE_NAME = "TM Panel Store"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        # Users table with ban support
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance REAL DEFAULT 0,
                user_type TEXT DEFAULT 'user',
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                banned_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Products table
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Product plans table (multiple validity options)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS product_plans (
                plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                validity_days INTEGER NOT NULL,
                base_price REAL NOT NULL,
                stock INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (product_id) REFERENCES products (product_id)
            )
        ''')
        
        # Product keys table
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS product_keys (
                key_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                plan_id INTEGER,
                key_value TEXT NOT NULL,
                is_used BOOLEAN DEFAULT 0,
                used_by INTEGER,
                used_at TIMESTAMP,
                order_id INTEGER,
                expires_at TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (product_id),
                FOREIGN KEY (plan_id) REFERENCES product_plans (plan_id)
            )
        ''')
        
        # Orders table
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                plan_id INTEGER,
                quantity INTEGER DEFAULT 1,
                total_price REAL,
                status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (product_id) REFERENCES products (product_id),
                FOREIGN KEY (plan_id) REFERENCES product_plans (plan_id)
            )
        ''')
        
        # Reseller specific prices
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS reseller_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reseller_id INTEGER,
                plan_id INTEGER,
                custom_price REAL,
                FOREIGN KEY (reseller_id) REFERENCES users (user_id),
                FOREIGN KEY (plan_id) REFERENCES product_plans (plan_id)
            )
        ''')
        
        # Balance transactions log
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS balance_transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                transaction_type TEXT,
                admin_id INTEGER,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.conn.commit()

    def get_user(self, user_id):
        cursor = self.conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        if not user:
            # Create new user
            self.conn.execute(
                'INSERT INTO users (user_id, first_name, username) VALUES (?, ?, ?)', 
                (user_id, "User", "username")
            )
            self.conn.commit()
            cursor = self.conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            user = cursor.fetchone()
        return user

    def is_user_banned(self, user_id):
        user = self.get_user(user_id)
        return user[6] if user else False  # is_banned field

    def ban_user(self, user_id, reason="No reason provided", admin_id=None):
        self.conn.execute(
            'UPDATE users SET is_banned = 1, ban_reason = ?, banned_at = ? WHERE user_id = ?',
            (reason, datetime.now(), user_id)
        )
        # Log the action
        if admin_id:
            self.conn.execute(
                'INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, reason) VALUES (?, ?, ?, ?, ?)',
                (user_id, 0, 'ban', admin_id, reason)
            )
        self.conn.commit()

    def unban_user(self, user_id, admin_id=None):
        self.conn.execute(
            'UPDATE users SET is_banned = 0, ban_reason = NULL, banned_at = NULL WHERE user_id = ?',
            (user_id,)
        )
        # Log the action
        if admin_id:
            self.conn.execute(
                'INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, reason) VALUES (?, ?, ?, ?, ?)',
                (user_id, 0, 'unban', admin_id, 'User unbanned')
            )
        self.conn.commit()

    def delete_user(self, user_id, admin_id=None):
        # Log before deletion
        if admin_id:
            self.conn.execute(
                'INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, reason) VALUES (?, ?, ?, ?, ?)',
                (user_id, 0, 'delete_user', admin_id, 'User account deleted')
            )
        # Actually delete user
        self.conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        self.conn.commit()

    def update_user_balance(self, user_id, amount, transaction_type="admin_adjustment", admin_id=None, reason=""):
        # Update balance
        self.conn.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ?',
            (amount, user_id)
        )
        
        # Log transaction
        self.conn.execute(
            'INSERT INTO balance_transactions (user_id, amount, transaction_type, admin_id, reason) VALUES (?, ?, ?, ?, ?)',
            (user_id, amount, transaction_type, admin_id, reason)
        )
        self.conn.commit()

    def get_balance_transactions(self, user_id=None, limit=50):
        if user_id:
            return self.conn.execute('''
                SELECT * FROM balance_transactions 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit)).fetchall()
        else:
            return self.conn.execute('''
                SELECT bt.*, u.username, u.first_name 
                FROM balance_transactions bt
                LEFT JOIN users u ON bt.user_id = u.user_id
                ORDER BY bt.created_at DESC 
                LIMIT ?
            ''', (limit,)).fetchall()

    def get_products(self):
        return self.conn.execute('SELECT * FROM products WHERE is_active = 1').fetchall()

    def get_all_products(self):
        return self.conn.execute('SELECT * FROM products').fetchall()

    def get_product_plans(self, product_id):
        return self.conn.execute('''
            SELECT * FROM product_plans 
            WHERE product_id = ? AND is_active = 1 
            ORDER BY validity_days
        ''', (product_id,)).fetchall()

    def get_all_product_plans(self, product_id):
        return self.conn.execute('''
            SELECT * FROM product_plans 
            WHERE product_id = ?
            ORDER BY validity_days
        ''', (product_id,)).fetchall()

    def get_plan_price(self, plan_id, user_id):
        # Check if user is reseller with custom price
        reseller_price = self.conn.execute(
            'SELECT custom_price FROM reseller_prices WHERE reseller_id = ? AND plan_id = ?',
            (user_id, plan_id)
        ).fetchone()
        
        if reseller_price:
            return reseller_price[0]
        
        # Get base price
        plan = self.conn.execute(
            'SELECT base_price FROM product_plans WHERE plan_id = ?', 
            (plan_id,)
        ).fetchone()
        
        return plan[0] if plan else None

    def create_order(self, user_id, plan_id, quantity=1):
        # Check if user is banned
        if self.is_user_banned(user_id):
            return False, "Your account has been banned. Contact admin."
        
        price = self.get_plan_price(plan_id, user_id)
        if price is None:
            return False, "Plan not found"
            
        total_price = price * quantity
        
        # Check user balance
        user = self.get_user(user_id)
        if user[4] < total_price:
            return False, "Insufficient balance"
        
        # Get available key
        key = self.conn.execute(
            'SELECT key_id, key_value FROM product_keys WHERE plan_id = ? AND is_used = 0 LIMIT 1',
            (plan_id,)
        ).fetchone()
        
        if not key:
            return False, "Product out of stock"
        
        # Get plan validity
        plan = self.conn.execute('SELECT validity_days FROM product_plans WHERE plan_id = ?', (plan_id,)).fetchone()
        validity_days = plan[0] if plan else 30
        expires_at = datetime.now() + timedelta(days=validity_days)
        
        # Create order first to get order_id
        cursor = self.conn.execute(
            'INSERT INTO orders (user_id, plan_id, quantity, total_price) VALUES (?, ?, ?, ?)',
            (user_id, plan_id, quantity, total_price)
        )
        order_id = cursor.lastrowid
        
        # Update key as used with order_id and expiry
        self.conn.execute(
            'UPDATE product_keys SET is_used = 1, used_by = ?, used_at = ?, order_id = ?, expires_at = ? WHERE key_id = ?',
            (user_id, datetime.now(), order_id, expires_at, key[0])
        )
        
        # Update plan stock
        self.conn.execute(
            'UPDATE product_plans SET stock = stock - 1 WHERE plan_id = ?',
            (plan_id,)
        )
        
        # Deduct balance
        self.conn.execute(
            'UPDATE users SET balance = balance - ? WHERE user_id = ?',
            (total_price, user_id)
        )
        
        # Log transaction
        self.conn.execute(
            'INSERT INTO balance_transactions (user_id, amount, transaction_type, reason) VALUES (?, ?, ?, ?)',
            (user_id, -total_price, 'purchase', f'Purchase order #{order_id}')
        )
        
        self.conn.commit()
        return True, key[1]

    def add_product(self, name, description):
        cursor = self.conn.execute(
            'INSERT INTO products (name, description) VALUES (?, ?)',
            (name, description)
        )
        product_id = cursor.lastrowid
        self.conn.commit()
        return product_id

    def update_product(self, product_id, name, description):
        self.conn.execute(
            'UPDATE products SET name = ?, description = ? WHERE product_id = ?',
            (name, description, product_id)
        )
        self.conn.commit()

    def delete_product(self, product_id):
        self.conn.execute(
            'UPDATE products SET is_active = 0 WHERE product_id = ?',
            (product_id,)
        )
        self.conn.commit()

    def add_product_plan(self, product_id, validity_days, price, keys):
        cursor = self.conn.execute(
            'INSERT INTO product_plans (product_id, validity_days, base_price, stock) VALUES (?, ?, ?, ?)',
            (product_id, validity_days, price, len(keys))
        )
        plan_id = cursor.lastrowid
        
        for key in keys:
            self.conn.execute(
                'INSERT INTO product_keys (product_id, plan_id, key_value) VALUES (?, ?, ?)',
                (product_id, plan_id, key.strip())
            )
        
        self.conn.commit()
        return plan_id

    def update_product_plan(self, plan_id, validity_days, price):
        self.conn.execute(
            'UPDATE product_plans SET validity_days = ?, base_price = ? WHERE plan_id = ?',
            (validity_days, price, plan_id)
        )
        self.conn.commit()

    def delete_product_plan(self, plan_id):
        self.conn.execute(
            'UPDATE product_plans SET is_active = 0 WHERE plan_id = ?',
            (plan_id,)
        )
        self.conn.commit()

    def add_keys_to_plan(self, plan_id, keys):
        for key in keys:
            self.conn.execute(
                'INSERT INTO product_keys (product_id, plan_id, key_value) VALUES ((SELECT product_id FROM product_plans WHERE plan_id = ?), ?, ?)',
                (plan_id, plan_id, key.strip())
            )
        
        self.conn.execute(
            'UPDATE product_plans SET stock = stock + ? WHERE plan_id = ?',
            (len(keys), plan_id)
        )
        
        self.conn.commit()
        return len(keys)

    def delete_key(self, key_id):
        key = self.conn.execute('SELECT is_used, plan_id FROM product_keys WHERE key_id = ?', (key_id,)).fetchone()
        if key and key[0] == 0:
            self.conn.execute('DELETE FROM product_keys WHERE key_id = ?', (key_id,))
            self.conn.execute('UPDATE product_plans SET stock = stock - 1 WHERE plan_id = ?', (key[1],))
            self.conn.commit()
            return True
        return False

    def set_reseller_price(self, reseller_id, plan_id, price):
        self.conn.execute(
            '''INSERT OR REPLACE INTO reseller_prices (reseller_id, plan_id, custom_price) 
               VALUES (?, ?, ?)''',
            (reseller_id, plan_id, price)
        )
        self.conn.commit()

    def get_reseller_prices(self, reseller_id):
        return self.conn.execute('''
            SELECT rp.plan_id, rp.custom_price, pl.validity_days, p.name 
            FROM reseller_prices rp
            JOIN product_plans pl ON rp.plan_id = pl.plan_id
            JOIN products p ON pl.product_id = p.product_id
            WHERE rp.reseller_id = ?
        ''', (reseller_id,)).fetchall()

    def set_user_type(self, user_id, user_type):
        self.conn.execute(
            'UPDATE users SET user_type = ? WHERE user_id = ?',
            (user_type, user_id)
        )
        self.conn.commit()

    def get_all_users(self):
        return self.conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()

    def get_user_by_id(self, user_id):
        return self.conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()

    def get_orders(self, user_id=None):
        if user_id:
            return self.conn.execute('''
                SELECT o.*, p.name, pl.validity_days FROM orders o 
                JOIN product_plans pl ON o.plan_id = pl.plan_id
                JOIN products p ON pl.product_id = p.product_id
                WHERE o.user_id = ? 
                ORDER BY o.created_at DESC
            ''', (user_id,)).fetchall()
        else:
            return self.conn.execute('''
                SELECT o.*, p.name, pl.validity_days, u.first_name FROM orders o 
                JOIN product_plans pl ON o.plan_id = pl.plan_id
                JOIN products p ON pl.product_id = p.product_id
                JOIN users u ON o.user_id = u.user_id 
                ORDER BY o.created_at DESC
            ''').fetchall()

    def get_purchased_keys(self, user_id):
        return self.conn.execute('''
            SELECT k.key_value, k.used_at, p.name, pl.validity_days, o.order_id, k.expires_at
            FROM product_keys k
            JOIN product_plans pl ON k.plan_id = pl.plan_id
            JOIN products p ON pl.product_id = p.product_id
            JOIN orders o ON k.order_id = o.order_id
            WHERE k.used_by = ?
            ORDER BY k.used_at DESC
        ''', (user_id,)).fetchall()

    def get_all_keys(self, plan_id=None):
        if plan_id:
            return self.conn.execute('''
                SELECT k.key_id, k.key_value, k.is_used, 
                       CASE WHEN k.is_used = 1 THEN u.user_id ELSE NULL END as used_by,
                       CASE WHEN k.is_used = 1 THEN u.first_name ELSE NULL END as user_name,
                       p.name as product_name, pl.validity_days,
                       k.used_at, k.expires_at
                FROM product_keys k
                JOIN product_plans pl ON k.plan_id = pl.plan_id
                JOIN products p ON pl.product_id = p.product_id
                LEFT JOIN users u ON k.used_by = u.user_id
                WHERE k.plan_id = ?
                ORDER BY k.is_used, k.key_id
            ''', (plan_id,)).fetchall()
        else:
            return self.conn.execute('''
                SELECT k.key_id, k.key_value, k.is_used, 
                       CASE WHEN k.is_used = 1 THEN u.user_id ELSE NULL END as used_by,
                       CASE WHEN k.is_used = 1 THEN u.first_name ELSE NULL END as user_name,
                       p.name as product_name, pl.validity_days,
                       k.used_at, k.expires_at
                FROM product_keys k
                JOIN product_plans pl ON k.plan_id = pl.plan_id
                JOIN products p ON pl.product_id = p.product_id
                LEFT JOIN users u ON k.used_by = u.user_id
                ORDER BY p.name, pl.validity_days, k.is_used, k.key_id
            ''').fetchall()

    def get_sales_statistics(self):
        total_sales = self.conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        total_revenue = self.conn.execute('SELECT SUM(total_price) FROM orders').fetchone()[0] or 0
        total_users = self.conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_products = self.conn.execute('SELECT COUNT(*) FROM products WHERE is_active = 1').fetchone()[0]
        banned_users = self.conn.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1').fetchone()[0]
        
        total_keys = self.conn.execute('SELECT COUNT(*) FROM product_keys').fetchone()[0]
        used_keys = self.conn.execute('SELECT COUNT(*) FROM product_keys WHERE is_used = 1').fetchone()[0]
        available_keys = total_keys - used_keys
        
        return {
            'total_sales': total_sales,
            'total_revenue': total_revenue,
            'total_users': total_users,
            'banned_users': banned_users,
            'total_products': total_products,
            'total_keys': total_keys,
            'used_keys': used_keys,
            'available_keys': available_keys
        }

    def get_product_stats(self, product_id):
        sold = self.conn.execute(
            'SELECT COUNT(*) FROM orders o JOIN product_plans pl ON o.plan_id = pl.plan_id WHERE pl.product_id = ?', (product_id,)
        ).fetchone()[0]
        
        available = self.conn.execute(
            'SELECT COUNT(*) FROM product_keys k JOIN product_plans pl ON k.plan_id = pl.plan_id WHERE pl.product_id = ? AND k.is_used = 0', (product_id,)
        ).fetchone()[0]
        
        total_keys = self.conn.execute(
            'SELECT COUNT(*) FROM product_keys k JOIN product_plans pl ON k.plan_id = pl.plan_id WHERE pl.product_id = ?', (product_id,)
        ).fetchone()[0]
        
        revenue = self.conn.execute(
            'SELECT SUM(total_price) FROM orders o JOIN product_plans pl ON o.plan_id = pl.plan_id WHERE pl.product_id = ?', (product_id,)
        ).fetchone()[0] or 0
        
        return {
            'sold': sold,
            'available': available,
            'total_keys': total_keys,
            'revenue': revenue
        }

    def get_plan_stats(self, plan_id):
        sold = self.conn.execute(
            'SELECT COUNT(*) FROM orders WHERE plan_id = ?', (plan_id,)
        ).fetchone()[0]
        
        available = self.conn.execute(
            'SELECT COUNT(*) FROM product_keys WHERE plan_id = ? AND is_used = 0', (plan_id,)
        ).fetchone()[0]
        
        total_keys = self.conn.execute(
            'SELECT COUNT(*) FROM product_keys WHERE plan_id = ?', (plan_id,)
        ).fetchone()[0]
        
        revenue = self.conn.execute(
            'SELECT SUM(total_price) FROM orders WHERE plan_id = ?', (plan_id,)
        ).fetchone()[0] or 0
        
        return {
            'sold': sold,
            'available': available,
            'total_keys': total_keys,
            'revenue': revenue
        }

    def search_users(self, search_term):
        try:
            user_id = int(search_term)
            return self.conn.execute(
                'SELECT * FROM users WHERE user_id = ?', (user_id,)
            ).fetchall()
        except ValueError:
            return self.conn.execute(
                'SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ?', 
                (f'%{search_term}%', f'%{search_term}%')
            ).fetchall()

    def set_admin(self, user_id):
        self.conn.execute(
            'UPDATE users SET user_type = ? WHERE user_id = ?',
            ('admin', user_id)
        )
        self.conn.commit()

# Initialize database
db = Database()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user is banned
    if db.is_user_banned(user_id):
        user = db.get_user(user_id)
        ban_reason = user[7] or "No reason provided"
        banned_at = user[8] or "Unknown"
        await update.message.reply_text(
            f"🚫 **Your account has been banned!**\n\n"
            f"**Reason:** {ban_reason}\n"
            f"**Banned on:** {banned_at}\n\n"
            f"Contact admin for more information.",
            parse_mode='Markdown'
        )
        return
    
    user = db.get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🛍️ View Products", callback_data="view_products")],
        [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance")],
        [InlineKeyboardButton("📊 Order History", callback_data="order_history")],
        [InlineKeyboardButton("🔑 My Purchased Keys", callback_data="my_keys")]
    ]
    
    if user_id in ADMIN_IDS or user[5] == 'admin':
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""🤖 **Welcome to {STORE_NAME}!**

🆔 **Your ID:** `{user_id}`
👤 **Account Type:** {user[5].title()}
💰 **Balance:** ${user[4]:.2f}

Choose an option below:"""
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # Check if user is banned for all callbacks except admin panel
    if not data.startswith("admin_") and db.is_user_banned(user_id):
        user = db.get_user(user_id)
        ban_reason = user[7] or "No reason provided"
        await query.edit_message_text(
            f"🚫 **Your account has been banned!**\n\n"
            f"**Reason:** {ban_reason}\n\n"
            f"Contact admin for more information.",
            parse_mode='Markdown'
        )
        return
    
    try:
        # Main menu handlers
        if data == "view_products":
            await show_products_menu(query)
        elif data == "check_balance":
            await show_balance(query)
        elif data == "order_history":
            await show_order_history(query)
        elif data == "my_keys":
            await show_my_keys(query)
        elif data == "main_menu":
            await show_main_menu(query)
        
        # Product handlers
        elif data.startswith("product_"):
            product_id = int(data.split("_")[1])
            await show_product_plans(query, product_id)
        elif data.startswith("plan_"):
            plan_id = int(data.split("_")[1])
            await show_plan_details(query, plan_id)
        elif data.startswith("buy_"):
            plan_id = int(data.split("_")[1])
            await process_purchase(query, plan_id)
        elif data == "back_to_products":
            await show_products_menu(query)
        
        # Admin handlers
        elif data == "admin_panel":
            await show_admin_panel(query)
        elif data == "admin_manage_products":
            await admin_manage_products(query)
        elif data == "admin_manage_users":
            await admin_manage_users(query)
        elif data == "admin_statistics":
            await admin_show_statistics(query)
        elif data == "admin_all_orders":
            await admin_show_all_orders(query)
        elif data == "admin_add_product":
            await admin_add_product_start(query, context)
        elif data == "admin_back_to_panel":
            await show_admin_panel(query)
        elif data == "admin_view_all_users":
            await admin_view_all_users(query)
        elif data == "admin_manage_keys":
            await admin_manage_keys(query)
        elif data == "admin_balance_transactions":
            await admin_show_balance_transactions(query)
        elif data.startswith("admin_view_keys_"):
            plan_id = int(data.split("_")[3])
            await admin_view_plan_keys(query, plan_id)
        elif data.startswith("admin_add_keys_"):
            plan_id = int(data.split("_")[3])
            await admin_add_keys_start(query, context, plan_id)
        elif data.startswith("admin_delete_key_"):
            key_id = int(data.split("_")[3])
            await admin_delete_key(query, key_id)
        elif data.startswith("admin_add_plan_"):
            product_id = int(data.split("_")[3])
            await admin_add_plan_start(query, context, product_id)
        elif data.startswith("admin_manage_plans_"):
            product_id = int(data.split("_")[3])
            await admin_manage_product_plans(query, product_id)
        elif data.startswith("admin_edit_product_"):
            product_id = int(data.split("_")[3])
            await admin_edit_product_start(query, context, product_id)
        elif data.startswith("admin_delete_product_"):
            product_id = int(data.split("_")[3])
            await admin_delete_product(query, product_id)
        elif data.startswith("admin_edit_plan_"):
            plan_id = int(data.split("_")[3])
            await admin_edit_plan_start(query, context, plan_id)
        elif data.startswith("admin_delete_plan_"):
            plan_id = int(data.split("_")[3])
            await admin_delete_plan(query, plan_id)
        
        # User management handlers
        elif data.startswith("admin_search_user"):
            await admin_search_user(query, context)
        elif data.startswith("admin_view_user_"):
            user_id_to_view = int(data.split("_")[3])
            await admin_view_user_details(query, user_id_to_view)
        elif data.startswith("admin_set_reseller_"):
            user_id_to_set = int(data.split("_")[3])
            db.set_user_type(user_id_to_set, 'reseller')
            await query.edit_message_text(f"✅ User `{user_id_to_set}` has been set as **Reseller**!", parse_mode='Markdown')
        elif data.startswith("admin_set_user_"):
            user_id_to_set = int(data.split("_")[3])
            db.set_user_type(user_id_to_set, 'user')
            await query.edit_message_text(f"✅ User `{user_id_to_set}` has been set as **Regular User**!", parse_mode='Markdown')
        elif data.startswith("admin_set_admin_"):
            user_id_to_set = int(data.split("_")[3])
            db.set_admin(user_id_to_set)
            await query.edit_message_text(f"✅ User `{user_id_to_set}` has been set as **Admin**!", parse_mode='Markdown')
        elif data.startswith("admin_add_balance_"):
            user_id_to_add = int(data.split("_")[3])
            context.user_data['add_balance_user'] = user_id_to_add
            await query.edit_message_text(f"💵 Please enter the amount to add for user `{user_id_to_add}`:\n\nExample: `50` or `25.99`", parse_mode='Markdown')
        elif data.startswith("admin_minus_balance_"):
            user_id_to_minus = int(data.split("_")[3])
            context.user_data['minus_balance_user'] = user_id_to_minus
            await query.edit_message_text(f"💵 Please enter the amount to deduct from user `{user_id_to_minus}`:\n\nExample: `50` or `25.99`", parse_mode='Markdown')
        elif data.startswith("admin_set_price_"):
            user_id_to_set = int(data.split("_")[3])
            context.user_data['set_price_user'] = user_id_to_set
            await admin_set_reseller_price_start(query, context, user_id_to_set)
        elif data.startswith("admin_set_plan_price_"):
            parts = data.split("_")
            target_user_id = int(parts[4])
            plan_id = int(parts[5])
            await admin_set_individual_price_start(query, context, target_user_id, plan_id)
        elif data.startswith("admin_ban_user_"):
            user_id_to_ban = int(data.split("_")[3])
            context.user_data['ban_user_id'] = user_id_to_ban
            await query.edit_message_text(f"🚫 Please enter the ban reason for user `{user_id_to_ban}`:", parse_mode='Markdown')
        elif data.startswith("admin_unban_user_"):
            user_id_to_unban = int(data.split("_")[3])
            db.unban_user(user_id_to_unban, admin_id=user_id)
            await query.edit_message_text(f"✅ User `{user_id_to_unban}` has been **unbanned**!", parse_mode='Markdown')
        elif data.startswith("admin_delete_user_"):
            user_id_to_delete = int(data.split("_")[3])
            context.user_data['delete_user_id'] = user_id_to_delete
            keyboard = [
                [InlineKeyboardButton("✅ Confirm Delete", callback_data=f"admin_confirm_delete_{user_id_to_delete}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"admin_view_user_{user_id_to_delete}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"⚠️ **Are you sure you want to DELETE user `{user_id_to_delete}`?**\n\n"
                f"❌ This action cannot be undone!\n"
                f"📝 All user data including orders and balance will be permanently removed.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        elif data.startswith("admin_confirm_delete_"):
            user_id_to_delete = int(data.split("_")[3])
            db.delete_user(user_id_to_delete, admin_id=user_id)
            await query.edit_message_text(f"✅ User `{user_id_to_delete}` has been **permanently deleted**!", parse_mode='Markdown')
    
    except Exception as e:
        logging.error(f"Error in callback handler: {e}")
        await query.edit_message_text("❌ An error occurred. Please try again.")

async def show_main_menu(query):
    user_id = query.from_user.id
    user = db.get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🛍️ View Products", callback_data="view_products")],
        [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance")],
        [InlineKeyboardButton("📊 Order History", callback_data="order_history")],
        [InlineKeyboardButton("🔑 My Purchased Keys", callback_data="my_keys")]
    ]
    
    if user_id in ADMIN_IDS or user[5] == 'admin':
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🏠 **Main Menu - {STORE_NAME}**\n\n🆔 **Your ID:** `{user_id}`\n💰 **Balance:** ${user[4]:.2f}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_products_menu(query):
    try:
        products = db.get_products()
        
        if not products:
            keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📭 No products available at the moment.", reply_markup=reply_markup)
            return
        
        keyboard = []
        for product in products:
            keyboard.append([
                InlineKeyboardButton(
                    f"📦 {product[1]}", 
                    callback_data=f"product_{product[0]}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🛍️ **Available Products - {STORE_NAME}**\n\nSelect a product to view available plans:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in show_products_menu: {e}")
        await query.edit_message_text("❌ Error loading products. Please try again.")

async def show_product_plans(query, product_id):
    try:
        product = db.conn.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
        if not product:
            await query.edit_message_text("❌ Product not found.")
            return
        
        plans = db.get_product_plans(product_id)
        
        if not plans:
            keyboard = [[InlineKeyboardButton("🔙 Back to Products", callback_data="back_to_products")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"📦 **{product[1]}**\n\n📭 No plans available for this product.", reply_markup=reply_markup)
            return
        
        keyboard = []
        for plan in plans:
            price = db.get_plan_price(plan[0], query.from_user.id)
            keyboard.append([
                InlineKeyboardButton(
                    f"⏰ {plan[2]} days - ${price:.2f}", 
                    callback_data=f"plan_{plan[0]}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Products", callback_data="back_to_products")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📦 **{product[1]}**\n\n📝 *{product[2]}*\n\nSelect a plan:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in show_product_plans: {e}")
        await query.edit_message_text("❌ Error loading plans. Please try again.")

async def show_plan_details(query, plan_id):
    try:
        plan = db.conn.execute('''
            SELECT pl.*, p.name, p.description 
            FROM product_plans pl 
            JOIN products p ON pl.product_id = p.product_id 
            WHERE pl.plan_id = ?
        ''', (plan_id,)).fetchone()
        
        if not plan:
            await query.edit_message_text("❌ Plan not found.")
            return
        
        price = db.get_plan_price(plan_id, query.from_user.id)
        stock = db.conn.execute(
            'SELECT COUNT(*) FROM product_keys WHERE plan_id = ? AND is_used = 0', 
            (plan_id,)
        ).fetchone()[0]
        
        keyboard = [
            [InlineKeyboardButton("🛒 Buy Now", callback_data=f"buy_{plan_id}")],
            [InlineKeyboardButton("🔙 Back to Plans", callback_data=f"product_{plan[1]}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📦 **{plan[6]}**\n\n"
            f"📝 *{plan[7]}*\n\n"
            f"⏰ **Validity:** {plan[2]} days\n"
            f"💰 **Price:** ${price:.2f}\n"
            f"📊 **Stock Available:** {stock}\n"
            f"🆔 **Plan ID:** `{plan_id}`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in show_plan_details: {e}")
        await query.edit_message_text("❌ Error loading plan details. Please try again.")

async def process_purchase(query, plan_id):
    try:
        user_id = query.from_user.id
        success, result = db.create_order(user_id, plan_id)
        
        if success:
            user = db.get_user(user_id)
            keyboard = [
                [InlineKeyboardButton("🛍️ Buy More", callback_data="view_products")],
                [InlineKeyboardButton("🔑 View My Keys", callback_data="my_keys")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ **Purchase Successful!**\n\n"
                f"🎯 **Your Key:** `{result}`\n\n"
                f"💰 **Remaining Balance:** ${user[4]:.2f}\n\n"
                f"⚠️ *Keep this key safe and don't share it!*\n"
                f"📋 *You can view all your purchased keys in 'My Purchased Keys' section*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            keyboard = [[InlineKeyboardButton("🔙 Back to Plans", callback_data=f"plan_{plan_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ **Purchase Failed!**\n\n"
                f"**Reason:** {result}\n\n"
                f"Please try again or contact support.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except Exception as e:
        logging.error(f"Error in process_purchase: {e}")
        await query.edit_message_text("❌ Error processing purchase. Please try again.")

async def show_balance(query):
    try:
        user = db.get_user(query.from_user.id)
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💰 **Your Balance:** ${user[4]:.2f}\n\n"
            f"💳 *Contact admin to add balance.*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in show_balance: {e}")
        await query.edit_message_text("❌ Error loading balance. Please try again.")

async def show_order_history(query):
    try:
        user_id = query.from_user.id
        orders = db.get_orders(user_id)
        
        if not orders:
            keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📭 You haven't made any orders yet.", reply_markup=reply_markup)
            return
        
        text = "📊 **Your Order History**\n\n"
        for order in orders[:15]:
            text += f"🆔 **Order #{order[0]}**\n"
            text += f"📦 **Product:** {order[7]} ({order[8]} days)\n"
            text += f"💵 **Amount:** ${order[5]:.2f}\n"
            text += f"🔢 **Quantity:** {order[4]}\n"
            text += f"🕒 **Date:** {order[6]}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("🔑 View Purchased Keys", callback_data="my_keys")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in show_order_history: {e}")
        await query.edit_message_text("❌ Error loading order history. Please try again.")

async def show_my_keys(query):
    try:
        user_id = query.from_user.id
        purchased_keys = db.get_purchased_keys(user_id)
        
        if not purchased_keys:
            keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("🔑 **Your Purchased Keys**\n\n📭 You haven't purchased any keys yet.", reply_markup=reply_markup)
            return
        
        text = "🔑 **Your Purchased Keys**\n\n"
        for key in purchased_keys:
            expires_text = f"⏰ **Expires:** {key[5]}" if key[5] else f"⏰ **Validity:** {key[3]} days"
            text += f"📦 **Product:** {key[2]} ({key[3]} days)\n"
            text += f"🔑 **Key:** `{key[0]}`\n"
            text += f"🕒 **Purchased:** {key[1]}\n"
            text += f"{expires_text}\n"
            text += f"🆔 **Order ID:** #{key[4]}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in show_my_keys: {e}")
        await query.edit_message_text("❌ Error loading purchased keys. Please try again.")

# ==================== ADMIN FUNCTIONS ====================

async def show_admin_panel(query):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        stats = db.get_sales_statistics()
        
        keyboard = [
            [InlineKeyboardButton("📦 Manage Products", callback_data="admin_manage_products")],
            [InlineKeyboardButton("👥 Manage Users", callback_data="admin_manage_users")],
            [InlineKeyboardButton("🔑 Manage Keys", callback_data="admin_manage_keys")],
            [InlineKeyboardButton("💰 Balance Transactions", callback_data="admin_balance_transactions")],
            [InlineKeyboardButton("📊 Statistics", callback_data="admin_statistics")],
            [InlineKeyboardButton("📋 All Orders", callback_data="admin_all_orders")],
            [InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        admin_text = f"""👑 **Admin Panel - {STORE_NAME}**

📈 **Quick Stats:**
💰 Total Revenue: ${stats['total_revenue']:.2f}
🛒 Total Sales: {stats['total_sales']}
👥 Total Users: {stats['total_users']}
🚫 Banned Users: {stats['banned_users']}
📦 Total Products: {stats['total_products']}
🔑 Total Keys: {stats['total_keys']}
✅ Used Keys: {stats['used_keys']}
🟢 Available Keys: {stats['available_keys']}

Choose an option below:"""
        
        await query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in show_admin_panel: {e}")
        await query.edit_message_text("❌ Error loading admin panel. Please try again.")

async def admin_manage_users(query):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        keyboard = [
            [InlineKeyboardButton("🔍 Search User by ID/Username", callback_data="admin_search_user")],
            [InlineKeyboardButton("👥 View All Users", callback_data="admin_view_all_users")],
            [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_back_to_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "👥 **User Management**\n\n"
            "Choose an option to manage users:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in admin_manage_users: {e}")
        await query.edit_message_text("❌ Error loading user management. Please try again.")

async def admin_view_all_users(query):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        users = db.get_all_users()
        
        text = "👥 **All Users**\n\n"
        keyboard = []
        
        for user in users[:15]:
            ban_status = "🚫" if user[6] else "✅"
            text += f"{ban_status} `{user[0]}` | 👤 {user[5]} | 💰 ${user[4]:.2f}\n"
            keyboard.append([InlineKeyboardButton(f"Manage User {user[0]}", callback_data=f"admin_view_user_{user[0]}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_manage_users")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_view_all_users: {e}")
        await query.edit_message_text("❌ Error loading users. Please try again.")

async def admin_view_user_details(query, user_id_to_view):
    try:
        current_user_id = query.from_user.id
        current_user = db.get_user(current_user_id)
        
        if current_user_id not in ADMIN_IDS and current_user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        user = db.get_user_by_id(user_id_to_view)
        if not user:
            await query.edit_message_text("❌ User not found!")
            return
        
        user_orders = db.get_orders(user_id_to_view)
        total_spent = sum(order[5] for order in user_orders) if user_orders else 0
        purchased_keys = db.get_purchased_keys(user_id_to_view)
        
        reseller_prices = []
        if user[5] == 'reseller':
            reseller_prices = db.get_reseller_prices(user_id_to_view)
        
        ban_status = "🚫 **BANNED**" if user[6] else "✅ **Active**"
        ban_info = f"\n🚫 **Ban Reason:** {user[7]}\n⏰ **Banned On:** {user[8]}" if user[6] else ""
        
        text = f"""👤 **User Details**

🆔 **User ID:** `{user[0]}`
👤 **Username:** @{user[1] or 'N/A'}
📛 **Name:** {user[2] or 'N/A'}
💰 **Balance:** ${user[4]:.2f}
🎫 **Account Type:** {user[5]}
📅 **Joined:** {user[9]}
🔒 **Status:** {ban_status}{ban_info}

📊 **Statistics:**
🛒 **Total Orders:** {len(user_orders)}
💵 **Total Spent:** ${total_spent:.2f}
🔑 **Keys Purchased:** {len(purchased_keys)}"""

        if reseller_prices:
            text += "\n\n💰 **Reseller Prices:**\n"
            for price in reseller_prices:
                text += f"• {price[3]} - {price[2]} days: ${price[1]:.2f}\n"

        keyboard = [
            [
                InlineKeyboardButton("💵 Add Balance", callback_data=f"admin_add_balance_{user_id_to_view}"),
                InlineKeyboardButton("➖ Minus Balance", callback_data=f"admin_minus_balance_{user_id_to_view}")
            ]
        ]
        
        if user[6]:  # If user is banned
            keyboard.append([InlineKeyboardButton("✅ Unban User", callback_data=f"admin_unban_user_{user_id_to_view}")])
        else:
            keyboard.append([InlineKeyboardButton("🚫 Ban User", callback_data=f"admin_ban_user_{user_id_to_view}")])
        
        keyboard.append([
            InlineKeyboardButton("💰 Set Prices", callback_data=f"admin_set_price_{user_id_to_view}"),
        ])
        
        if current_user_id in ADMIN_IDS:
            keyboard[-1].append(InlineKeyboardButton("👑 Set Admin", callback_data=f"admin_set_admin_{user_id_to_view}"))
        
        if user[5] == 'user':
            keyboard.append([InlineKeyboardButton("🎫 Set Reseller", callback_data=f"admin_set_reseller_{user_id_to_view}")])
        elif user[5] == 'reseller':
            keyboard.append([InlineKeyboardButton("👤 Set Regular", callback_data=f"admin_set_user_{user_id_to_view}")])
        
        keyboard.append([InlineKeyboardButton("🗑️ Delete User", callback_data=f"admin_delete_user_{user_id_to_view}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_manage_users")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_view_user_details: {e}")
        await query.edit_message_text("❌ Error loading user details. Please try again.")

async def admin_show_balance_transactions(query):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        transactions = db.get_balance_transactions(limit=20)
        
        text = "💰 **Balance Transactions**\n\n"
        
        if not transactions:
            text += "📭 No transactions found."
        else:
            for tx in transactions:
                user_info = f"@{tx[8]}" if tx[8] else f"User {tx[1]}"
                amount_color = "🟢" if tx[2] > 0 else "🔴"
                text += f"{amount_color} **{tx[4]}** - ${tx[2]:.2f}\n"
                text += f"👤 {user_info} | 🆔 {tx[1]}\n"
                text += f"📝 {tx[5]}\n"
                text += f"🕒 {tx[6]}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_back_to_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_show_balance_transactions: {e}")
        await query.edit_message_text("❌ Error loading transactions. Please try again.")

async def admin_show_statistics(query):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        stats = db.get_sales_statistics()
        products = db.get_products()
        
        text = f"""📊 **Store Statistics - {STORE_NAME}**

💰 **Financial:**
Total Revenue: ${stats['total_revenue']:.2f}
Total Sales: {stats['total_sales']}

👥 **Users:**
Total Users: {stats['total_users']}
Banned Users: {stats['banned_users']}
Active Users: {stats['total_users'] - stats['banned_users']}

📦 **Inventory:**
Total Products: {stats['total_products']}
Total Keys: {stats['total_keys']}
Used Keys: {stats['used_keys']}
Available Keys: {stats['available_keys']}
Stock Rate: {(stats['available_keys']/stats['total_keys']*100):.1f}%

📈 **Product Performance:**\n"""
        
        for product in products:
            product_stats = db.get_product_stats(product[0])
            text += f"\n📦 **{product[1]}**\n"
            text += f"   Sold: {product_stats['sold']} | Revenue: ${product_stats['revenue']:.2f}\n"
            text += f"   Available: {product_stats['available']}/{product_stats['total_keys']}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_back_to_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_show_statistics: {e}")
        await query.edit_message_text("❌ Error loading statistics. Please try again.")

# ==================== MESSAGE HANDLERS ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message_text = update.message.text
    
    try:
        # Handle user search
        if context.user_data.get('searching_user'):
            await handle_user_search(update, context, message_text)
            return
        
        # Handle balance addition
        if 'add_balance_user' in context.user_data:
            await handle_add_balance(update, context, message_text)
            return
        
        # Handle balance deduction
        if 'minus_balance_user' in context.user_data:
            await handle_minus_balance(update, context, message_text)
            return
        
        # Handle ban user
        if 'ban_user_id' in context.user_data:
            await handle_ban_user(update, context, message_text)
            return
        
        # Handle product addition
        if context.user_data.get('adding_product'):
            await handle_add_product_stages(update, context, message_text)
            return
        
        # Handle plan addition
        if context.user_data.get('adding_plan'):
            await handle_add_plan_stages(update, context, message_text)
            return
        
        # Handle keys addition
        if context.user_data.get('adding_keys'):
            await handle_add_keys(update, context, message_text)
            return
        
        # Handle individual price setting
        if context.user_data.get('setting_individual_price'):
            await handle_set_individual_price(update, context, message_text)
            return
        
        await update.message.reply_text("Please use the menu buttons to navigate.")
    
    except Exception as e:
        logging.error(f"Error in handle_message: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")

async def handle_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user_id not in ADMIN_IDS and user[5] != 'admin':
        await update.message.reply_text("❌ Access denied!")
        return
    
    users = db.search_users(message_text)
    
    if not users:
        await update.message.reply_text("❌ No users found with that search term.")
        context.user_data.pop('searching_user', None)
        return
    
    text = "🔍 **Search Results**\n\n"
    keyboard = []
    
    for user in users[:10]:
        ban_status = "🚫" if user[6] else "✅"
        text += f"{ban_status} `{user[0]}` | 👤 {user[5]} | 💰 ${user[4]:.2f}\n"
        keyboard.append([InlineKeyboardButton(f"Manage User {user[0]}", callback_data=f"admin_view_user_{user[0]}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_manage_users")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    context.user_data.pop('searching_user', None)

async def handle_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    target_user_id = context.user_data['add_balance_user']
    
    try:
        amount = float(message_text)
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive. Please try again:")
            return
        
        db.update_user_balance(
            target_user_id, 
            amount, 
            "admin_add", 
            admin_id=user_id,
            reason=f"Admin balance addition: ${amount:.2f}"
        )
        
        target_user = db.get_user(target_user_id)
        await update.message.reply_text(
            f"✅ **Balance added successfully!**\n\n"
            f"👤 User: `{target_user_id}`\n"
            f"💵 Amount: +${amount:.2f}\n"
            f"💰 New Balance: ${target_user[4]:.2f}",
            parse_mode='Markdown'
        )
        
        context.user_data.pop('add_balance_user', None)
        
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a valid number:")

async def handle_minus_balance(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    target_user_id = context.user_data['minus_balance_user']
    
    try:
        amount = float(message_text)
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive. Please try again:")
            return
        
        target_user = db.get_user(target_user_id)
        if target_user[4] < amount:
            await update.message.reply_text(
                f"❌ User only has ${target_user[4]:.2f} balance. Cannot deduct ${amount:.2f}. Please try again:"
            )
            return
        
        db.update_user_balance(
            target_user_id, 
            -amount, 
            "admin_deduct", 
            admin_id=user_id,
            reason=f"Admin balance deduction: ${amount:.2f}"
        )
        
        target_user = db.get_user(target_user_id)
        await update.message.reply_text(
            f"✅ **Balance deducted successfully!**\n\n"
            f"👤 User: `{target_user_id}`\n"
            f"💵 Amount: -${amount:.2f}\n"
            f"💰 New Balance: ${target_user[4]:.2f}",
            parse_mode='Markdown'
        )
        
        context.user_data.pop('minus_balance_user', None)
        
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a valid number:")

async def handle_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    target_user_id = context.user_data['ban_user_id']
    
    db.ban_user(target_user_id, reason=message_text, admin_id=user_id)
    
    await update.message.reply_text(
        f"✅ **User has been banned!**\n\n"
        f"👤 User ID: `{target_user_id}`\n"
        f"🚫 Reason: {message_text}",
        parse_mode='Markdown'
    )
    
    context.user_data.pop('ban_user_id', None)

# ==================== PRODUCT MANAGEMENT HANDLERS ====================

async def admin_add_product_start(query, context):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        context.user_data['adding_product'] = True
        context.user_data['add_product_stage'] = 'name'
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_manage_products")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📦 **Add New Product**\n\nPlease enter the product name:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error in admin_add_product_start: {e}")
        await query.edit_message_text("❌ Error starting product addition. Please try again.")

async def handle_add_product_stages(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user_id not in ADMIN_IDS and user[5] != 'admin':
        await update.message.reply_text("❌ Access denied!")
        context.user_data.clear()
        return
    
    if context.user_data['add_product_stage'] == 'name':
        context.user_data['product_name'] = message_text
        context.user_data['add_product_stage'] = 'description'
        await update.message.reply_text("📝 Please enter the product description:")
    
    elif context.user_data['add_product_stage'] == 'description':
        product_name = context.user_data['product_name']
        product_description = message_text
        
        product_id = db.add_product(product_name, product_description)
        
        await update.message.reply_text(
            f"✅ **Product added successfully!**\n\n"
            f"📦 **Name:** {product_name}\n"
            f"📝 **Description:** {product_description}\n"
            f"🆔 **Product ID:** `{product_id}`\n\n"
            f"You can now add plans to this product.",
            parse_mode='Markdown'
        )
        
        context.user_data.clear()

async def admin_add_plan_start(query, context, product_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        context.user_data['adding_plan'] = True
        context.user_data['add_plan_product_id'] = product_id
        context.user_data['add_plan_stage'] = 'validity'
        
        product = db.conn.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_manage_plans_{product_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⏰ **Add New Plan for {product[1]}**\n\nPlease enter the validity in days:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error in admin_add_plan_start: {e}")
        await query.edit_message_text("❌ Error starting plan addition. Please try again.")

async def handle_add_plan_stages(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user_id not in ADMIN_IDS and user[5] != 'admin':
        await update.message.reply_text("❌ Access denied!")
        context.user_data.clear()
        return
    
    if context.user_data['add_plan_stage'] == 'validity':
        try:
            validity_days = int(message_text)
            if validity_days <= 0:
                await update.message.reply_text("❌ Validity must be positive. Please enter valid days:")
                return
            
            context.user_data['plan_validity'] = validity_days
            context.user_data['add_plan_stage'] = 'price'
            await update.message.reply_text("💰 Please enter the base price (e.g., 9.99):")
        
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please enter valid days:")
    
    elif context.user_data['add_plan_stage'] == 'price':
        try:
            price = float(message_text)
            if price <= 0:
                await update.message.reply_text("❌ Price must be positive. Please enter valid price:")
                return
            
            context.user_data['plan_price'] = price
            context.user_data['add_plan_stage'] = 'keys'
            await update.message.reply_text("🔑 Please enter the product keys (one key per line):")
        
        except ValueError:
            await update.message.reply_text("❌ Invalid price. Please enter valid amount:")
    
    elif context.user_data['add_plan_stage'] == 'keys':
        keys = [key.strip() for key in message_text.split('\n') if key.strip()]
        
        if not keys:
            await update.message.reply_text("❌ No valid keys provided. Please enter at least one key:")
            return
        
        product_id = context.user_data['add_plan_product_id']
        validity_days = context.user_data['plan_validity']
        price = context.user_data['plan_price']
        
        plan_id = db.add_product_plan(product_id, validity_days, price, keys)
        
        product = db.conn.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
        
        await update.message.reply_text(
            f"✅ **Plan added successfully!**\n\n"
            f"📦 **Product:** {product[1]}\n"
            f"⏰ **Validity:** {validity_days} days\n"
            f"💰 **Price:** ${price:.2f}\n"
            f"🔑 **Keys Added:** {len(keys)}\n"
            f"🆔 **Plan ID:** `{plan_id}`",
            parse_mode='Markdown'
        )
        
        context.user_data.clear()

async def admin_add_keys_start(query, context, plan_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        context.user_data['adding_keys'] = True
        context.user_data['add_keys_plan_id'] = plan_id
        
        plan = db.conn.execute('''
            SELECT pl.*, p.name 
            FROM product_plans pl 
            JOIN products p ON pl.product_id = p.product_id 
            WHERE pl.plan_id = ?
        ''', (plan_id,)).fetchone()
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_view_keys_{plan_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🔑 **Add Keys to {plan[6]} - {plan[2]} days**\n\nPlease enter the product keys (one key per line):",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error in admin_add_keys_start: {e}")
        await query.edit_message_text("❌ Error starting keys addition. Please try again.")

async def handle_add_keys(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user_id not in ADMIN_IDS and user[5] != 'admin':
        await update.message.reply_text("❌ Access denied!")
        context.user_data.clear()
        return
    
    plan_id = context.user_data['add_keys_plan_id']
    keys = [key.strip() for key in message_text.split('\n') if key.strip()]
    
    if not keys:
        await update.message.reply_text("❌ No valid keys provided. Please enter at least one key:")
        return
    
    added_count = db.add_keys_to_plan(plan_id, keys)
    
    plan = db.conn.execute('''
        SELECT pl.*, p.name 
        FROM product_plans pl 
        JOIN products p ON pl.product_id = p.product_id 
        WHERE pl.plan_id = ?
    ''', (plan_id,)).fetchone()
    
    await update.message.reply_text(
        f"✅ **Keys added successfully!**\n\n"
        f"📦 **Product:** {plan[6]}\n"
        f"⏰ **Plan:** {plan[2]} days\n"
        f"🔑 **Keys Added:** {added_count}\n"
        f"📊 **New Stock:** {plan[4] + added_count}",
        parse_mode='Markdown'
    )
    
    context.user_data.clear()

async def admin_search_user(query, context):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        context.user_data['searching_user'] = True
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_manage_users")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔍 **Search User**\n\nPlease enter User ID or Username to search:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error in admin_search_user: {e}")
        await query.edit_message_text("❌ Error starting user search. Please try again.")

async def admin_set_individual_price_start(query, context, target_user_id, plan_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        plan = db.conn.execute('''
            SELECT pl.*, p.name 
            FROM product_plans pl 
            JOIN products p ON pl.product_id = p.product_id 
            WHERE pl.plan_id = ?
        ''', (plan_id,)).fetchone()
        
        if not plan:
            await query.edit_message_text("❌ Plan not found!")
            return
        
        context.user_data['setting_individual_price'] = True
        context.user_data['price_user_id'] = target_user_id
        context.user_data['price_plan_id'] = plan_id
        
        current_price = db.get_plan_price(plan_id, target_user_id)
        base_price = plan[3]
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_set_price_{target_user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💰 **Set Price for {plan[6]} - {plan[2]} days**\n\n"
            f"👤 User ID: `{target_user_id}`\n"
            f"🏷️ Base Price: ${base_price:.2f}\n"
            f"💵 Current Price: ${current_price:.2f}\n\n"
            f"Please enter the new custom price (e.g., 20.99):",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in admin_set_individual_price_start: {e}")
        await query.edit_message_text("❌ Error starting price setting. Please try again.")

async def handle_set_individual_price(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user_id not in ADMIN_IDS and user[5] != 'admin':
        await update.message.reply_text("❌ Access denied!")
        context.user_data.clear()
        return
    
    try:
        price = float(message_text)
        if price < 0:
            await update.message.reply_text("❌ Price cannot be negative. Please enter valid price:")
            return
        
        target_user_id = context.user_data['price_user_id']
        plan_id = context.user_data['price_plan_id']
        
        db.set_reseller_price(target_user_id, plan_id, price)
        
        plan = db.conn.execute('''
            SELECT pl.*, p.name 
            FROM product_plans pl 
            JOIN products p ON pl.product_id = p.product_id 
            WHERE pl.plan_id = ?
        ''', (plan_id,)).fetchone()
        
        await update.message.reply_text(
            f"✅ **Price set successfully!**\n\n"
            f"👤 User: `{target_user_id}`\n"
            f"📦 Product: {plan[6]}\n"
            f"⏰ Plan: {plan[2]} days\n"
            f"💰 New Price: ${price:.2f}",
            parse_mode='Markdown'
        )
        
        context.user_data.clear()
        
    except ValueError:
        await update.message.reply_text("❌ Invalid price. Please enter a valid number:")

# ==================== OTHER ADMIN FUNCTIONS ====================

async def admin_manage_products(query):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        products = db.get_products()
        
        text = "📦 **Product Management**\n\n"
        
        if not products:
            text += "📭 No products available.\n"
        else:
            for product in products:
                stats = db.get_product_stats(product[0])
                plans = db.get_product_plans(product[0])
                
                text += f"📦 **{product[1]}** (ID: `{product[0]}`)\n"
                text += f"📝 {product[2]}\n"
                
                if plans:
                    for plan in plans:
                        plan_stats = db.get_plan_stats(plan[0])
                        text += f"   ⏰ {plan[2]} days - ${plan[3]:.2f} | Stock: {plan_stats['available']}/{plan_stats['total_keys']}\n"
                else:
                    text += f"   📭 No plans added\n"
                
                text += f"💰 Revenue: ${stats['revenue']:.2f} | 📊 Sold: {stats['sold']}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Add New Product", callback_data="admin_add_product")],
        ]
        
        if products:
            keyboard.append([InlineKeyboardButton("🔧 Manage All Plans", callback_data="admin_manage_keys")])
            for product in products:
                keyboard.append([
                    InlineKeyboardButton(f"⚙️ {product[1]}", callback_data=f"admin_manage_plans_{product[0]}"),
                    InlineKeyboardButton("✏️ Edit", callback_data=f"admin_edit_product_{product[0]}"),
                    InlineKeyboardButton("🗑️ Delete", callback_data=f"admin_delete_product_{product[0]}")
                ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_back_to_panel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_manage_products: {e}")
        await query.edit_message_text("❌ Error loading products management. Please try again.")

async def admin_manage_product_plans(query, product_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        product = db.conn.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
        if not product:
            await query.edit_message_text("❌ Product not found!")
            return
        
        plans = db.get_product_plans(product_id)
        
        text = f"📦 **Plans for {product[1]}**\n\n"
        keyboard = []
        
        if not plans:
            text += "📭 No plans available.\n"
        else:
            for plan in plans:
                stats = db.get_plan_stats(plan[0])
                text += f"⏰ **{plan[2]} days** (ID: `{plan[0]}`)\n"
                text += f"💰 ${plan[3]} | 📊 Sold: {stats['sold']} | 📦 Stock: {stats['available']}/{stats['total_keys']}\n"
                text += f"💵 Revenue: ${stats['revenue']:.2f}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"🔑 {plan[2]}d Keys", callback_data=f"admin_view_keys_{plan[0]}"),
                    InlineKeyboardButton(f"➕ Add Keys", callback_data=f"admin_add_keys_{plan[0]}")
                ])
                keyboard.append([
                    InlineKeyboardButton(f"✏️ Edit {plan[2]}d", callback_data=f"admin_edit_plan_{plan[0]}"),
                    InlineKeyboardButton(f"🗑️ Delete {plan[2]}d", callback_data=f"admin_delete_plan_{plan[0]}")
                ])
        
        keyboard.append([InlineKeyboardButton("➕ Add New Plan", callback_data=f"admin_add_plan_{product_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Products", callback_data="admin_manage_products")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_manage_product_plans: {e}")
        await query.edit_message_text("❌ Error loading product plans. Please try again.")

async def admin_manage_keys(query):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        products = db.get_products()
        
        text = "🔑 **Key Management**\n\n"
        keyboard = []
        
        for product in products:
            plans = db.get_product_plans(product[0])
            for plan in plans:
                stats = db.get_plan_stats(plan[0])
                keyboard.append([
                    InlineKeyboardButton(f"🔑 {product[1]} {plan[2]}d", callback_data=f"admin_view_keys_{plan[0]}")
                ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_back_to_panel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_manage_keys: {e}")
        await query.edit_message_text("❌ Error loading key management. Please try again.")

async def admin_view_plan_keys(query, plan_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        plan = db.conn.execute('''
            SELECT pl.*, p.name 
            FROM product_plans pl 
            JOIN products p ON pl.product_id = p.product_id 
            WHERE pl.plan_id = ?
        ''', (plan_id,)).fetchone()
        
        if not plan:
            await query.edit_message_text("❌ Plan not found!")
            return
        
        keys = db.get_all_keys(plan_id)
        stats = db.get_plan_stats(plan_id)
        
        text = f"🔑 **Keys for {plan[6]} - {plan[2]} days**\n\n"
        text += f"📊 **Statistics:**\n"
        text += f"• Total Keys: {stats['total_keys']}\n"
        text += f"• Used Keys: {stats['sold']}\n"
        text += f"• Available Keys: {stats['available']}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Add More Keys", callback_data=f"admin_add_keys_{plan_id}")],
        ]
        
        if keys:
            text += "🔑 **Key List:**\n"
            for key in keys[:10]:  # Show first 10 keys
                status = "✅ Used" if key[2] else "🟢 Available"
                user_info = f"by {key[4]} ({key[3]})" if key[2] else ""
                text += f"• `{key[1]}` - {status} {user_info}\n"
            
            if len(keys) > 10:
                text += f"\n... and {len(keys) - 10} more keys"
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Plans", callback_data=f"admin_manage_plans_{plan[1]}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_view_plan_keys: {e}")
        await query.edit_message_text("❌ Error loading keys. Please try again.")

async def admin_delete_key(query, key_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        success = db.delete_key(key_id)
        
        if success:
            await query.edit_message_text("✅ Key deleted successfully!")
        else:
            await query.edit_message_text("❌ Cannot delete used key or key not found!")
    except Exception as e:
        logging.error(f"Error in admin_delete_key: {e}")
        await query.edit_message_text("❌ Error deleting key. Please try again.")

async def admin_edit_product_start(query, context, product_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        product = db.conn.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
        if not product:
            await query.edit_message_text("❌ Product not found!")
            return
        
        context.user_data['editing_product'] = True
        context.user_data['edit_product_id'] = product_id
        context.user_data['edit_product_stage'] = 'name'
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_manage_products")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📦 **Edit Product: {product[1]}**\n\n"
            f"Current name: {product[1]}\n"
            f"Current description: {product[2]}\n\n"
            "Please enter the new product name:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in admin_edit_product_start: {e}")
        await query.edit_message_text("❌ Error starting product edit. Please try again.")

async def handle_edit_product_stages(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user_id not in ADMIN_IDS and user[5] != 'admin':
        await update.message.reply_text("❌ Access denied!")
        context.user_data.clear()
        return
    
    if context.user_data['edit_product_stage'] == 'name':
        context.user_data['new_product_name'] = message_text
        context.user_data['edit_product_stage'] = 'description'
        await update.message.reply_text("📝 Please enter the new product description:")
    
    elif context.user_data['edit_product_stage'] == 'description':
        product_id = context.user_data['edit_product_id']
        new_name = context.user_data['new_product_name']
        new_description = message_text
        
        db.update_product(product_id, new_name, new_description)
        
        await update.message.reply_text(
            f"✅ **Product updated successfully!**\n\n"
            f"📦 **New Name:** {new_name}\n"
            f"📝 **New Description:** {new_description}\n"
            f"🆔 **Product ID:** `{product_id}`",
            parse_mode='Markdown'
        )
        
        context.user_data.clear()

async def admin_delete_product(query, product_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        product = db.conn.execute('SELECT * FROM products WHERE product_id = ?', (product_id,)).fetchone()
        if not product:
            await query.edit_message_text("❌ Product not found!")
            return
        
        orders_count = db.conn.execute(
            'SELECT COUNT(*) FROM orders o JOIN product_plans pl ON o.plan_id = pl.plan_id WHERE pl.product_id = ?', 
            (product_id,)
        ).fetchone()[0]
        
        if orders_count > 0:
            await query.edit_message_text(
                f"❌ Cannot delete product **{product[1]}**!\n\n"
                f"This product has {orders_count} orders associated with it.\n"
                f"Please deactivate it instead or contact support.",
                parse_mode='Markdown'
            )
            return
        
        db.delete_product(product_id)
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Products", callback_data="admin_manage_products")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Product Deleted Successfully!**\n\n"
            f"📦 **Product:** {product[1]}\n"
            f"🆔 **Product ID:** `{product_id}`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in admin_delete_product: {e}")
        await query.edit_message_text("❌ Error deleting product. Please try again.")

async def admin_edit_plan_start(query, context, plan_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        plan = db.conn.execute('''
            SELECT pl.*, p.name 
            FROM product_plans pl 
            JOIN products p ON pl.product_id = p.product_id 
            WHERE pl.plan_id = ?
        ''', (plan_id,)).fetchone()
        
        if not plan:
            await query.edit_message_text("❌ Plan not found!")
            return
        
        context.user_data['editing_plan'] = True
        context.user_data['edit_plan_id'] = plan_id
        context.user_data['edit_plan_stage'] = 'validity'
        
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data=f"admin_manage_plans_{plan[1]}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⏰ **Edit Plan: {plan[6]} - {plan[2]} days**\n\n"
            f"Current validity: {plan[2]} days\n"
            f"Current price: ${plan[3]:.2f}\n\n"
            "Please enter the new validity in days:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in admin_edit_plan_start: {e}")
        await query.edit_message_text("❌ Error starting plan edit. Please try again.")

async def handle_edit_plan_stages(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if user_id not in ADMIN_IDS and user[5] != 'admin':
        await update.message.reply_text("❌ Access denied!")
        context.user_data.clear()
        return
    
    if context.user_data['edit_plan_stage'] == 'validity':
        try:
            new_validity = int(message_text)
            if new_validity <= 0:
                await update.message.reply_text("❌ Validity must be positive. Please enter valid days:")
                return
            
            context.user_data['new_plan_validity'] = new_validity
            context.user_data['edit_plan_stage'] = 'price'
            await update.message.reply_text("💰 Please enter the new price (e.g., 9.99):")
        
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please enter valid days:")
    
    elif context.user_data['edit_plan_stage'] == 'price':
        try:
            new_price = float(message_text)
            if new_price <= 0:
                await update.message.reply_text("❌ Price must be positive. Please enter valid price:")
                return
            
            plan_id = context.user_data['edit_plan_id']
            new_validity = context.user_data['new_plan_validity']
            
            db.update_product_plan(plan_id, new_validity, new_price)
            
            plan = db.conn.execute('''
                SELECT pl.*, p.name 
                FROM product_plans pl 
                JOIN products p ON pl.product_id = p.product_id 
                WHERE pl.plan_id = ?
            ''', (plan_id,)).fetchone()
            
            await update.message.reply_text(
                f"✅ **Plan updated successfully!**\n\n"
                f"📦 **Product:** {plan[6]}\n"
                f"⏰ **New Validity:** {new_validity} days\n"
                f"💰 **New Price:** ${new_price:.2f}\n"
                f"🆔 **Plan ID:** `{plan_id}`",
                parse_mode='Markdown'
            )
            
            context.user_data.clear()
        
        except ValueError:
            await update.message.reply_text("❌ Invalid price. Please enter valid amount:")

async def admin_delete_plan(query, plan_id):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        plan = db.conn.execute('''
            SELECT pl.*, p.name 
            FROM product_plans pl 
            JOIN products p ON pl.product_id = p.product_id 
            WHERE pl.plan_id = ?
        ''', (plan_id,)).fetchone()
        
        if not plan:
            await query.edit_message_text("❌ Plan not found!")
            return
        
        orders_count = db.conn.execute(
            'SELECT COUNT(*) FROM orders WHERE plan_id = ?', 
            (plan_id,)
        ).fetchone()[0]
        
        if orders_count > 0:
            await query.edit_message_text(
                f"❌ Cannot delete plan **{plan[6]} - {plan[2]} days**!\n\n"
                f"This plan has {orders_count} orders associated with it.\n"
                f"Please deactivate it instead or contact support.",
                parse_mode='Markdown'
            )
            return
        
        db.delete_product_plan(plan_id)
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Plans", callback_data=f"admin_manage_plans_{plan[1]}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"✅ **Plan Deleted Successfully!**\n\n"
            f"📦 **Product:** {plan[6]}\n"
            f"⏰ **Plan:** {plan[2]} days\n"
            f"🆔 **Plan ID:** `{plan_id}`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logging.error(f"Error in admin_delete_plan: {e}")
        await query.edit_message_text("❌ Error deleting plan. Please try again.")

async def admin_set_reseller_price_start(query, context, user_id):
    try:
        current_user_id = query.from_user.id
        current_user = db.get_user(current_user_id)
        
        if current_user_id not in ADMIN_IDS and current_user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        products = db.get_products()
        
        if not products:
            await query.edit_message_text("❌ No products available to set prices!")
            return
        
        text = "💰 **Set Reseller Prices**\n\n"
        keyboard = []
        
        for product in products:
            plans = db.get_product_plans(product[0])
            for plan in plans:
                current_price = db.get_plan_price(plan[0], user_id)
                base_price = plan[3]
                text += f"📦 {product[1]} - {plan[2]} days\n"
                text += f"   Base: ${base_price:.2f} | Current: ${current_price:.2f}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"💰 {product[1]} {plan[2]}d", callback_data=f"admin_set_plan_price_{user_id}_{plan[0]}")
                ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to User", callback_data=f"admin_view_user_{user_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_set_reseller_price_start: {e}")
        await query.edit_message_text("❌ Error starting price setting. Please try again.")

async def admin_show_all_orders(query):
    try:
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        if user_id not in ADMIN_IDS and user[5] != 'admin':
            await query.edit_message_text("❌ Access denied!")
            return
        
        orders = db.get_orders()
        
        text = "📋 **All Orders**\n\n"
        
        if not orders:
            text += "📭 No orders found."
        else:
            for order in orders[:15]:
                text += f"🆔 **Order #{order[0]}**\n"
                text += f"👤 **User:** {order[8]} (ID: `{order[1]}`)\n"
                text += f"📦 **Product:** {order[7]} ({order[8]} days)\n"
                text += f"💵 **Amount:** ${order[5]:.2f}\n"
                text += f"🕒 **Date:** {order[6]}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_back_to_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error in admin_show_all_orders: {e}")
        await query.edit_message_text("❌ Error loading orders. Please try again.")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    print("🤖 Bot is starting...")
    print(f"👑 Admin ID: {ADMIN_IDS[0]}")
    print(f"🏪 Store Name: {STORE_NAME}")
    print("📊 Database initialized successfully!")
    application.run_polling()

if __name__ == '__main__':
    main()