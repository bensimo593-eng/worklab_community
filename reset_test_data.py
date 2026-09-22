import sqlite3
import shutil
import os
from datetime import datetime


DATABASE = "worklab.db"


def reset_test_data():

    if not os.path.exists(DATABASE):
        print("ERROR: worklab.db was not found.")
        return

    # ==========================================
    # CREATE BACKUP FIRST
    # ==========================================

    os.makedirs("backups", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_file = os.path.join(
        "backups",
        f"worklab_before_reset_{timestamp}.db"
    )

    shutil.copy2(
        DATABASE,
        backup_file
    )

    print("")
    print("Backup created:")
    print(backup_file)
    print("")

    # ==========================================
    # CONFIRM RESET
    # ==========================================

    print("WARNING")
    print("--------------------------------------")
    print("This will DELETE:")
    print("- Clients")
    print("- Visits")
    print("- Subscriptions")
    print("- Payments")
    print("- Expenses")
    print("- Additional Services")
    print("")
    print("Admin / Manager / Staff users")
    print("and their permissions WILL BE KEPT.")
    print("--------------------------------------")
    print("")

    confirmation = input(
        "Type RESET WORKLAB to continue: "
    )

    if confirmation != "RESET WORKLAB":
        print("")
        print("Reset cancelled.")
        return

    connection = sqlite3.connect(DATABASE)

    try:

        cursor = connection.cursor()

        # Child/business records first

        cursor.execute(
            "DELETE FROM additional_services"
        )

        cursor.execute(
            "DELETE FROM payments"
        )

        cursor.execute(
            "DELETE FROM visits"
        )

        cursor.execute(
            "DELETE FROM subscriptions"
        )

        cursor.execute(
            "DELETE FROM expenses"
        )

        # Clients last
        cursor.execute(
            "DELETE FROM clients"
        )

        # ======================================
        # RESET AUTOINCREMENT COUNTERS
        # ======================================

        tables_to_reset = [
            "clients",
            "visits",
            "subscriptions",
            "payments",
            "expenses",
            "additional_services"
        ]

        for table in tables_to_reset:

            cursor.execute(
                "DELETE FROM sqlite_sequence WHERE name = ?",
                (table,)
            )

        connection.commit()

        print("")
        print("======================================")
        print("WORKLAB TEST DATA RESET SUCCESSFULLY")
        print("======================================")
        print("")
        print("Clients:             0")
        print("Visits:              0")
        print("Subscriptions:       0")
        print("Payments:            0")
        print("Expenses:            0")
        print("Additional Services: 0")
        print("")
        print("Users were preserved.")
        print("Permissions were preserved.")
        print("")
        print("Next client will start from WL0001.")
        print("")
        print("Backup:")
        print(backup_file)

    except Exception as error:

        connection.rollback()

        print("")
        print("RESET FAILED.")
        print(error)

    finally:

        connection.close()


if __name__ == "__main__":
    reset_test_data()