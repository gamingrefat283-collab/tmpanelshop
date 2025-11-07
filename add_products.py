#!/usr/bin/env python3
"""
Product Management Script for Telegram Bot
Use this script to quickly add products and plans to the database
"""

import sqlite3
import sys
import os

def add_sample_products():
    """Add sample products to the database for testing"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        # Sample products
        products = [
            {
                'name': 'Netflix Premium',
                'description': 'High-quality streaming service with 4K support',
                'plans': [
                    {'validity': 30, 'price': 15.99, 'keys': [
                        'NETFLIX-30D-001-ABC123',
                        'NETFLIX-30D-002-DEF456',
                        'NETFLIX-30D-003-GHI789',
                        'NETFLIX-30D-004-JKL012',
                        'NETFLIX-30D-005-MNO345'
                    ]},
                    {'validity': 90, 'price': 39.99, 'keys': [
                        'NETFLIX-90D-001-ABC123',
                        'NETFLIX-90D-002-DEF456',
                        'NETFLIX-90D-003-GHI789'
                    ]},
                    {'validity': 180, 'price': 69.99, 'keys': [
                        'NETFLIX-180D-001-ABC123',
                        'NETFLIX-180D-002-DEF456'
                    ]}
                ]
            },
            {
                'name': 'Spotify Premium',
                'description': 'Ad-free music streaming with offline downloads',
                'plans': [
                    {'validity': 30, 'price': 9.99, 'keys': [
                        'SPOTIFY-30D-001-ABC123',
                        'SPOTIFY-30D-002-DEF456',
                        'SPOTIFY-30D-003-GHI789',
                        'SPOTIFY-30D-004-JKL012'
                    ]},
                    {'validity': 90, 'price': 24.99, 'keys': [
                        'SPOTIFY-90D-001-ABC123',
                        'SPOTIFY-90D-002-DEF456'
                    ]}
                ]
            },
            {
                'name': 'YouTube Premium',
                'description': 'Ad-free YouTube with background play and downloads',
                'plans': [
                    {'validity': 30, 'price': 12.99, 'keys': [
                        'YOUTUBE-30D-001-ABC123',
                        'YOUTUBE-30D-002-DEF456',
                        'YOUTUBE-30D-003-GHI789'
                    ]},
                    {'validity': 180, 'price': 59.99, 'keys': [
                        'YOUTUBE-180D-001-ABC123',
                        'YOUTUBE-180D-002-DEF456'
                    ]}
                ]
            },
            {
                'name': 'Disney+ Premium',
                'description': 'Stream Disney, Marvel, Star Wars, and more',
                'plans': [
                    {'validity': 30, 'price': 10.99, 'keys': [
                        'DISNEY-30D-001-ABC123',
                        'DISNEY-30D-002-DEF456',
                        'DISNEY-30D-003-GHI789'
                    ]},
                    {'validity': 365, 'price': 99.99, 'keys': [
                        'DISNEY-365D-001-ABC123'
                    ]}
                ]
            }
        ]
        
        for product_data in products:
            # Add product
            cursor.execute(
                'INSERT INTO products (name, description) VALUES (?, ?)',
                (product_data['name'], product_data['description'])
            )
            product_id = cursor.lastrowid
            print(f"✅ Added product: {product_data['name']} (ID: {product_id})")
            
            # Add plans for this product
            for plan_data in product_data['plans']:
                cursor.execute(
                    'INSERT INTO product_plans (product_id, validity_days, base_price, stock) VALUES (?, ?, ?, ?)',
                    (product_id, plan_data['validity'], plan_data['price'], len(plan_data['keys']))
                )
                plan_id = cursor.lastrowid
                
                # Add keys for this plan
                for key in plan_data['keys']:
                    cursor.execute(
                        'INSERT INTO product_keys (product_id, plan_id, key_value) VALUES (?, ?, ?)',
                        (product_id, plan_id, key)
                    )
                
                print(f"  ⏰ Added plan: {plan_data['validity']} days - ${plan_data['price']} (Keys: {len(plan_data['keys'])})")
        
        conn.commit()
        print("\n🎉 Sample products added successfully!")
        print("\n📊 Summary:")
        cursor.execute('SELECT COUNT(*) FROM products')
        product_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM product_plans')
        plan_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM product_keys')
        key_count = cursor.fetchone()[0]
        
        print(f"📦 Products: {product_count}")
        print(f"⏰ Plans: {plan_count}")
        print(f"🔑 Keys: {key_count}")
        
    except Exception as e:
        print(f"❌ Error adding products: {e}")
        conn.rollback()
    finally:
        conn.close()

def add_custom_product():
    """Add a custom product through user input"""
    print("\n🎯 Add Custom Product")
    print("=" * 30)
    
    name = input("Product name: ").strip()
    if not name:
        print("❌ Product name is required!")
        return
    
    description = input("Product description: ").strip()
    if not description:
        print("❌ Product description is required!")
        return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        # Add product
        cursor.execute(
            'INSERT INTO products (name, description) VALUES (?, ?)',
            (name, description)
        )
        product_id = cursor.lastrowid
        print(f"✅ Product added! ID: {product_id}")
        
        # Add plans
        while True:
            print(f"\n📋 Adding plans for: {name}")
            add_another = input("Add a plan? (y/n): ").lower().strip()
            if add_another != 'y':
                break
            
            try:
                validity = int(input("Validity (days): "))
                price = float(input("Price: "))
                
                keys_input = input("Enter keys (one per line, empty line to finish):\n")
                keys = [key.strip() for key in keys_input.split('\n') if key.strip()]
                
                if not keys:
                    print("❌ At least one key is required!")
                    continue
                
                # Add plan
                cursor.execute(
                    'INSERT INTO product_plans (product_id, validity_days, base_price, stock) VALUES (?, ?, ?, ?)',
                    (product_id, validity, price, len(keys))
                )
                plan_id = cursor.lastrowid
                
                # Add keys
                for key in keys:
                    cursor.execute(
                        'INSERT INTO product_keys (product_id, plan_id, key_value) VALUES (?, ?, ?)',
                        (product_id, plan_id, key)
                    )
                
                print(f"✅ Plan added: {validity} days - ${price} (Keys: {len(keys)})")
                
            except ValueError:
                print("❌ Invalid input! Please enter valid numbers.")
            except Exception as e:
                print(f"❌ Error adding plan: {e}")
        
        conn.commit()
        print("\n🎉 Custom product added successfully!")
        
    except Exception as e:
        print(f"❌ Error adding product: {e}")
        conn.rollback()
    finally:
        conn.close()

def view_products():
    """View all products in the database"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        print("\n📦 Current Products")
        print("=" * 50)
        
        cursor.execute('''
            SELECT p.product_id, p.name, p.description, 
                   COUNT(DISTINCT pl.plan_id) as plan_count,
                   COUNT(k.key_id) as total_keys,
                   SUM(CASE WHEN k.is_used = 0 THEN 1 ELSE 0 END) as available_keys
            FROM products p
            LEFT JOIN product_plans pl ON p.product_id = pl.product_id
            LEFT JOIN product_keys k ON pl.plan_id = k.plan_id
            WHERE p.is_active = 1
            GROUP BY p.product_id
        ''')
        
        products = cursor.fetchall()
        
        if not products:
            print("📭 No products found in database.")
            return
        
        for product in products:
            print(f"\n🆔 ID: {product[0]}")
            print(f"📦 Name: {product[1]}")
            print(f"📝 Description: {product[2]}")
            print(f"⏰ Plans: {product[3]}")
            print(f"🔑 Keys: {product[5]} available / {product[4]} total")
            
            # Show plans for this product
            cursor.execute('''
                SELECT pl.plan_id, pl.validity_days, pl.base_price, 
                       COUNT(k.key_id) as total_keys,
                       SUM(CASE WHEN k.is_used = 0 THEN 1 ELSE 0 END) as available_keys
                FROM product_plans pl
                LEFT JOIN product_keys k ON pl.plan_id = k.plan_id
                WHERE pl.product_id = ? AND pl.is_active = 1
                GROUP BY pl.plan_id
            ''', (product[0],))
            
            plans = cursor.fetchall()
            for plan in plans:
                print(f"  ⏰ {plan[1]} days - ${plan[2]:.2f} | Stock: {plan[4]}/{plan[3]}")
        
        print(f"\n📊 Total Products: {len(products)}")
        
    except Exception as e:
        print(f"❌ Error viewing products: {e}")
    finally:
        conn.close()

def reset_database():
    """Reset database (delete all data) - USE WITH CAUTION!"""
    print("\n⚠️  DANGER ZONE - RESET DATABASE")
    print("=" * 40)
    print("This will delete ALL data including:")
    print("• All products and plans")
    print("• All user accounts and balances")
    print("• All orders and transaction history")
    print("• ALL DATA WILL BE PERMANENTLY LOST!")
    
    confirmation = input("\nType 'RESET' to confirm: ").strip()
    if confirmation != 'RESET':
        print("❌ Reset cancelled.")
        return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        # Delete all data from all tables
        tables = [
            'balance_transactions',
            'product_keys', 
            'orders',
            'reseller_prices',
            'product_plans',
            'products',
            'users'
        ]
        
        for table in tables:
            cursor.execute(f'DELETE FROM {table}')
            print(f"✅ Cleared table: {table}")
        
        # Reset autoincrement counters
        cursor.execute("DELETE FROM sqlite_sequence")
        
        conn.commit()
        print("\n🎉 Database reset successfully!")
        print("💾 All data has been cleared.")
        
    except Exception as e:
        print(f"❌ Error resetting database: {e}")
        conn.rollback()
    finally:
        conn.close()

def main():
    """Main menu for product management"""
    while True:
        print("\n🛍️ Product Management System")
        print("=" * 30)
        print("1. Add Sample Products")
        print("2. Add Custom Product")
        print("3. View All Products")
        print("4. Reset Database (DANGER)")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == '1':
            add_sample_products()
        elif choice == '2':
            add_custom_product()
        elif choice == '3':
            view_products()
        elif choice == '4':
            reset_database()
        elif choice == '5':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice! Please select 1-5.")

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists('bot_database.db'):
        print("❌ Database not found! Please run the bot first to create the database.")
        sys.exit(1)
    
    main()