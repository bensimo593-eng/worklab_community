import sqlite3


def create_database():

    connection = sqlite3.connect("worklab.db")
    cursor = connection.cursor()

    # =====================================================
    # 1. CLIENTS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT UNIQUE,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            status TEXT NOT NULL,
            registration_date TEXT NOT NULL
        )
    """)


    # =====================================================
    # 2. VISITS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            visit_date TEXT NOT NULL,
            plan TEXT NOT NULL,
            price REAL NOT NULL,

            FOREIGN KEY (client_id)
            REFERENCES clients(client_id)
        )
    """)


    # =====================================================
    # 3. SUBSCRIPTIONS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            subscription_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            price REAL NOT NULL,

            FOREIGN KEY (client_id)
            REFERENCES clients(client_id)
        )
    """)


    # =====================================================
    # 4. PAYMENTS TABLE
    # =====================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            payment_type TEXT NOT NULL,
            amount REAL NOT NULL,

            FOREIGN KEY (client_id)
            REFERENCES clients(client_id)
        )
    """)


    connection.commit()
    connection.close()

    print("WORKLAB database updated successfully!")


create_database()