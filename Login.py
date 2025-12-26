from flask import Flask, render_template, redirect, request, session
from flask_session import Session
import mysql.connector
from datetime import timedelta, datetime
import string
import re
import random




app = Flask(__name__)

app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR="flask_session_data",   # עדיף תיקייה יחסית בפרויקט
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=10),
    SESSION_REFRESH_EACH_REQUEST=True,
    SESSION_COOKIE_SECURE=False              # אם אתה עובד על localhost (לא https)
)

Session(app)

mydb = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
    database="flytau",
    autocommit=True
)

@app.route("/")
def homepage():
        return render_template("Homepage.html")


@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        pw = request.form.get("password")

        cur = mydb.cursor()
        cur.execute("SELECT `password` FROM `registered_customers` WHERE `email` = %s",(email,))
        row = cur.fetchone()
        cur.close()

        if row is None:
            return render_template("login.html", message="Email not found")

        db_password = row[0]

        if db_password == pw:
            session["username"] = email
            return redirect("/")
        else:
            return render_template("login.html", message="Incorrect password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect("/login")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email")
        first_name = request.form.get("fname")
        last_name = request.form.get("lname")
        date_of_birth = request.form.get("date_of_birth")
        passport_number = request.form.get("passport")
        password = request.form.get("password")
        now = datetime.now()

        cur = mydb.cursor()

        cur.execute("SELECT 1 FROM `registered_customers` WHERE `email` = %s", (email,))
        exists = cur.fetchone()

        if exists:
            cur.close()
            return render_template("signup.html", message="Email already exists")

        cur.execute(
            "INSERT INTO `registered_customers` (`email`,`fname`, `lname`, `date_of_birth`, `passport`, `password`, `registration_date`) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (email,first_name, last_name, date_of_birth, passport_number, password, now)
        )
        cur.close()

        session["username"] = email
        return redirect("/")

    return render_template("signup.html")


@app.route("/flights", methods=["GET"])
def flights():
    # אם אתה רוצה שרק משתמש מחובר יראה:

    flight_date = request.args.get("flight_date", "").strip()          # YYYY-MM-DD
    dep = request.args.get("departure_airport", "").strip().upper()    # TLV
    dest = request.args.get("destination_airport", "").strip().upper() # ATH

    # בונים query דינמי לפי מה שהמשתמש מילא
    sql = """
        SELECT Flight_Date, Departure_Time, Landing_Time,
               Departure_Airport, Destination_Airport, Plane_ID, status
        FROM Flights
        WHERE status = 'active'
    """
    params = []

    if flight_date:
        sql += " AND Flight_Date = %s"
        params.append(flight_date)

    if dep:
        sql += " AND Departure_Airport = %s"
        params.append(dep)

    if dest:
        sql += " AND Destination_Airport = %s"
        params.append(dest)

    sql += " ORDER BY Flight_Date, Departure_Time"

    cur = mydb.cursor(dictionary=True)
    cur.execute(sql, params)
    flights_rows = cur.fetchall()
    cur.close()

    return render_template(
        "flights.html",
        flights=flights_rows,
        flight_date=flight_date,
        departure_airport=dep,
        destination_airport=dest
    )

def col_labels(n: int):
    # A, B, C, ... (עד 26 טורים מספיק לרוב)
    letters = list(string.ascii_uppercase)
    return letters[:n]

@app.route("/seats")
def seats():
    flight_date = request.args.get("flight_date")
    departure_time = request.args.get("departure_time")

    cur = mydb.cursor(dictionary=True)

    # 1️⃣ שליפת המטוס של הטיסה
    cur.execute("""
        SELECT Plane_ID, Departure_Airport, Destination_Airport
        FROM Flights
        WHERE Flight_Date = %s AND Departure_Time = %s
    """, (flight_date, departure_time))
    flight = cur.fetchone()

    if not flight:
        cur.close()
        return "Flight not found"

    plane_id = flight["Plane_ID"]

    # 2️⃣ שליפת המחלקות לפי סדר: Business ואז Economy
    cur.execute("""
        SELECT Class_Type, Number_of_Rows, Number_of_Columns
        FROM Classes
        WHERE Plane_ID = %s
        ORDER BY
          CASE
            WHEN Class_Type = 'Business' THEN 1
            WHEN Class_Type = 'Economy' THEN 2
          END
    """, (plane_id,))
    classes = cur.fetchall()

    # 3️⃣ שליפת מושבים שכבר נמכרו (עם מספור רציף!)
    cur.execute("""
        SELECT `row`, `col`
        FROM Tickets
        WHERE flight_date = %s AND departure_time = %s
    """, (flight_date, departure_time))
    sold = {(r["row"], r["col"]) for r in cur.fetchall()}

    cur.close()

    # 4️⃣ בניית מפת מושבים — כאן קורה ה־B+1 עד B+E
    sections = []
    offset = 0   # כמה שורות כבר היו במטוס

    for c in classes:
        class_type = c["Class_Type"]
        rows = int(c["Number_of_Rows"])
        cols = int(c["Number_of_Columns"])
        labels = [chr(ord('A') + i) for i in range(cols)]

        start_row = offset + 1        # Business: 1, Economy: B+1
        end_row = offset + rows       # Business: B, Economy: B+E

        grid = []
        for r in range(start_row, end_row + 1):
            row_seats = []
            for col_i in range(1, cols + 1):
                row_seats.append({
                    "row": r,
                    "col": col_i,
                    "label": labels[col_i - 1],
                    "sold": (r, col_i) in sold
                })
            grid.append({"row": r, "seats": row_seats})

        sections.append({
            "class_type": class_type,
            "grid": grid
        })

        offset += rows   # ⬅️ זה מה שגורם לאקונומי להתחיל מ־B+1

    return render_template(
        "seats.html",
        sections=sections,
        flight=flight,
        flight_date=flight_date,
        departure_time=departure_time
    )

def seat_to_row_col(seat_code: str):
    m = re.match(r"^(\d+)([A-Z])$", seat_code.strip().upper())
    if not m:
        return None
    row = int(m.group(1))
    col = ord(m.group(2)) - ord('A') + 1
    return row, col

@app.route("/booking/new", methods=["GET"])
def booking_new():
    flight_date = request.args.get("flight_date", "").strip()
    departure_time = request.args.get("departure_time", "").strip()
    if not flight_date or not departure_time:
        return "Missing flight_date or departure_time", 400

    cur = mydb.cursor(dictionary=True)

    # flight + plane
    cur.execute("""
        SELECT Plane_ID, Departure_Airport, Destination_Airport, status
        FROM Flights
        WHERE Flight_Date=%s AND Departure_Time=%s
        LIMIT 1
    """, (flight_date, departure_time))
    flight = cur.fetchone()
    if not flight:
        cur.close()
        return "Flight not found", 404
    plane_id = flight["Plane_ID"]

    # classes ordered Business -> Economy
    cur.execute("""
        SELECT Class_Type, Number_of_Rows, Number_of_Columns
        FROM Classes
        WHERE Plane_ID=%s
        ORDER BY CASE
          WHEN Class_Type='Business' THEN 1
          WHEN Class_Type='Economy' THEN 2
          ELSE 3 END
    """, (plane_id,))
    classes = cur.fetchall()

    # sold seats (ignore cancelled)
    cur.execute("""
        SELECT t.`row`, t.`col`
        FROM Tickets t
        JOIN Bookings b ON b.booking_code=t.booking_code
        WHERE t.flight_date=%s AND t.departure_time=%s
          AND LOWER(b.status) <> 'cancelled'
    """, (flight_date, departure_time))
    sold_set = {(x["row"], x["col"]) for x in cur.fetchall()}
    cur.close()

    # build sections with continuous rows across classes
    import string
    def col_labels(n): return list(string.ascii_uppercase)[:n]

    sections = []
    offset = 0
    total_seats = 0
    sold_count = 0

    for c in classes:
        r = int(c["Number_of_Rows"])
        k = int(c["Number_of_Columns"])
        labels = col_labels(k)

        start_row = offset + 1
        end_row = offset + r

        sector = {"class_type": c["Class_Type"], "col_labels": labels, "grid": []}

        for row_i in range(start_row, end_row + 1):
            row_seats = []
            for col_i in range(1, k + 1):
                row_seats.append({
                    "row": row_i,
                    "col": col_i,
                    "label": labels[col_i - 1],
                    "sold": (row_i, col_i) in sold_set
                })
            sector["grid"].append({"row": row_i, "seats": row_seats})

        sections.append(sector)
        offset += r
        total_seats += r * k
        sold_count += sum(1 for (rr, cc) in sold_set if start_row <= rr <= end_row and 1 <= cc <= k)

    available = total_seats - sold_count

    return render_template(
        "seats_select.html",
        flight_date=flight_date,
        departure_time=departure_time,
        flight=flight,
        plane_id=plane_id,
        sections=sections,
        available=available,
        message=""
    )
def seat_to_row_col(seat_code: str):
    m = re.match(r"^(\d+)([A-Z])$", seat_code.strip().upper())
    if not m:
        return None
    row = int(m.group(1))
    col = ord(m.group(2)) - ord('A') + 1
    return row, col

def generate_booking_code(cur):
    # booking_code אצלך INT => נייצר 6 ספרות שלא קיימות
    while True:
        code = random.randint(100000, 999999)
        cur.execute("SELECT 1 FROM Bookings WHERE booking_code=%s LIMIT 1", (code,))
        if not cur.fetchone():
            return code

def get_class_ranges(cur, plane_id):
    # מחזיר טווחי שורות רציפים לכל מחלקה (Business ואז Economy)
    cur.execute("""
        SELECT Class_Type, Number_of_Rows, Number_of_Columns
        FROM Classes
        WHERE Plane_ID=%s
        ORDER BY CASE
          WHEN Class_Type='Business' THEN 1
          WHEN Class_Type='Economy' THEN 2
          ELSE 3 END
    """, (plane_id,))
    classes = cur.fetchall()

    ranges = []  # [{"class":"Business","start":1,"end":6,"cols":4}, ...]
    offset = 0
    for c in classes:
        rows = int(c["Number_of_Rows"])
        cols = int(c["Number_of_Columns"])
        start = offset + 1
        end = offset + rows
        ranges.append({"class": c["Class_Type"], "start": start, "end": end, "cols": cols})
        offset += rows
    return ranges

def class_for_row(ranges, row):
    for rg in ranges:
        if rg["start"] <= row <= rg["end"]:
            return rg["class"]
    return None

# @app.route("/booking/create", methods=["GET", "POST"])
@app.route("/booking/preview", methods=[ "POST"])
def booking_preview():
    flight_date = request.form.get("flight_date", "").strip()
    departure_time = request.form.get("departure_time", "").strip()
    selected = request.form.get("selected_seats", "").strip()

    if not flight_date or not departure_time:
        return "Missing flight info", 400
    if not selected:
        return redirect(f"/booking/new?flight_date={flight_date}&departure_time={departure_time}")

    # מי הלקוח?
    email = session.get("username")
    if not email:
        email = request.form.get("guest_email", "").strip()
        if not email:
            return "Missing email", 400

    seat_codes = [x.strip().upper() for x in selected.split(",") if x.strip()]
    seats = []
    for code in seat_codes:
        rc = seat_to_row_col(code)
        if rc is None:
            return f"Bad seat code: {code}", 400
        seats.append(rc)  # (row,col)

    cur = mydb.cursor(dictionary=True)

    # flight + plane
    cur.execute("""
        SELECT Plane_ID, Departure_Airport, Destination_Airport, status
        FROM Flights
        WHERE Flight_Date=%s AND Departure_Time=%s
        LIMIT 1
    """, (flight_date, departure_time))
    flight = cur.fetchone()
    if not flight:
        cur.close()
        return "Flight not found", 404

    plane_id = flight["Plane_ID"]
    ranges = get_class_ranges(cur, plane_id)

    # בדיקת תפוסה בזמן preview (מומלץ)
    cur.execute("""
        SELECT t.`row`, t.`col`
        FROM Tickets t
        JOIN Bookings b ON b.booking_code=t.booking_code
        WHERE t.flight_date=%s AND t.departure_time=%s
          AND LOWER(b.status) <> 'cancelled'
    """, (flight_date, departure_time))
    sold_set = {(x["row"], x["col"]) for x in cur.fetchall()}

    for (r, c) in seats:
        if (r, c) in sold_set:
            cur.close()
            return f"Seat already taken: {r},{c}", 400

    # האם האימייל מוכר?
    cur.execute("SELECT 1 FROM Registered_customers WHERE email=%s LIMIT 1", (email,))
    is_registered = cur.fetchone() is not None

    cur.execute("SELECT 1 FROM Unregistered_customers WHERE email=%s LIMIT 1", (email,))
    is_unregistered = cur.fetchone() is not None

    need_unreg_details = (not is_registered) and (not is_unregistered)

    # תמחור: Business=200, Economy=100
    seat_items = []
    total_price = 0
    for (r, c) in seats:
        cls = class_for_row(ranges, r)
        if cls == "Business":
            price = 200
        else:
            price = 100
        total_price += price
        seat_items.append({
            "seat": f"{r}{chr(ord('A') + c - 1)}",
            "row": r,
            "col": c,
            "class": cls,
            "price": price
        })

    # קוד הזמנה ייחודי (עדיין לא נכתב ל-DB)
    cur2 = mydb.cursor()
    booking_code = generate_booking_code(cur2)
    cur2.close()
    cur.close()

    # נשמור את כל מה שצריך ל-confirm בתוך session (כדי שלא יסמכו על hidden)
    session["pending_booking"] = {
        "booking_code": booking_code,
        "email": email,
        "flight_date": flight_date,
        "departure_time": departure_time,
        "seats": [(r, c) for (r, c) in seats],
        "total_price": total_price
    }

    return render_template(
        "booking_preview.html",
        booking_code=booking_code,
        email=email,
        flight=flight,
        flight_date=flight_date,
        departure_time=departure_time,
        seat_items=seat_items,
        total_price=total_price,
        need_unreg_details=need_unreg_details
    )
@app.route("/booking/confirm", methods=["POST"])
def booking_confirm():
    pending = session.get("pending_booking")
    if not pending:
        return "No pending booking", 400

    booking_code = pending["booking_code"]
    email = pending["email"]
    flight_date = pending["flight_date"]
    departure_time = pending["departure_time"]
    seats = pending["seats"]
    total_price = pending["total_price"]

    # אם צריך ליצור unregistered_customer — נקבל פרטים מהטופס
    fname = request.form.get("fname", "").strip()
    lname = request.form.get("lname", "").strip()
    phone_number = request.form.get("phone_number", "").strip()

    cur = mydb.cursor(dictionary=True)

    try:
        mydb.start_transaction()

        # האם email רשום / לא רשום?
        cur.execute("SELECT 1 FROM Registered_customers WHERE email=%s LIMIT 1", (email,))
        is_registered = cur.fetchone() is not None

        cur.execute("SELECT 1 FROM Unregistered_customers WHERE email=%s LIMIT 1", (email,))
        is_unregistered = cur.fetchone() is not None

        if (not is_registered) and (not is_unregistered):
            if not fname or not lname or not phone_number:
                mydb.rollback()
                cur.close()
                return "Missing guest details", 400

            cur.execute("""
                INSERT INTO Unregistered_customers (email, fname, lname)
                VALUES (%s,%s,%s)
            """, (email, fname, lname))

            # נשמור טלפון
            cur.execute("""
                INSERT INTO Phone_numbers (email, phone_number)
                VALUES (%s,%s)
            """, (email, phone_number))

        # בדיקת תפוסה מחדש (חשוב!) לפני כתיבה
        cur.execute("""
            SELECT t.`row`, t.`col`
            FROM Tickets t
            JOIN Bookings b ON b.booking_code=t.booking_code
            WHERE t.flight_date=%s AND t.departure_time=%s
              AND LOWER(b.status) <> 'cancelled'
        """, (flight_date, departure_time))
        sold_set = {(x["row"], x["col"]) for x in cur.fetchall()}

        for (r, c) in seats:
            if (r, c) in sold_set:
                raise ValueError(f"Seat already taken: {r},{c}")

        # יצירת Booking (העמודות החדשות שלך: total_price, booking_date)
        cur.execute("""
            INSERT INTO Bookings (booking_code, email, status, total_price)
            VALUES (%s,%s,%s,%s)
        """, (booking_code, email, "paid", total_price))

        # הכנסת Tickets
        for (r, c) in seats:
            cur.execute("""
                INSERT INTO Tickets (`row`, `col`, booking_code, flight_date, departure_time)
                VALUES (%s,%s,%s,%s,%s)
            """, (r, c, booking_code, flight_date, departure_time))

        mydb.commit()
        cur.close()

        # ניקוי pending
        session.pop("pending_booking", None)

        return redirect(f"/booking/success?code={booking_code}")

    except Exception as e:
        mydb.rollback()
        cur.close()
        return f"Booking failed: {e}", 400
@app.route("/booking/success")
def booking_success():
    code = request.args.get("code")
    return render_template("booking_success.html", code=code)

if __name__ == "__main__":
    app.run(debug=True)
