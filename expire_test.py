import sqlite3

client_id = "WL0005"

connection = sqlite3.connect("worklab.db")
cursor = connection.cursor()

cursor.execute("""
    UPDATE subscriptions
    SET end_date = '2026-09-20 10:00:00'
    WHERE id = (
        SELECT id
        FROM subscriptions
        WHERE client_id = ?
        ORDER BY id DESC
        LIMIT 1
    )
""", (client_id,))

connection.commit()

if cursor.rowcount > 0:
    print(f"SUCCESS: Subscription for {client_id} is now expired.")
else:
    print(f"ERROR: No subscription found for {client_id}.")

connection.close()