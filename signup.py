from flask import Flask, render_template, redirect, request, session
from flask_session import Session
from datetime import timedelta
import mysql.connector
from datetime import datetime

app = Flask(__name__)

mydb = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
    database="flytau",
    autocommit=True)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email_address = request.form.get("email address")
        first_name = request.form.get("first name")
        last_name = request.form.get("last name")
        date_of_birth = request.form.get("date of birth")
        passport_number = request.form.get("passport number")
        password = request.form.get("password")
        now = datetime.now()

        cur = mydb.cursor()

        cur.execute("SELECT 1 FROM `registered_customers` WHERE `email address` = %s", (email,))
        exists = cur.fetchone()

        if exists:
            cur.close()
            return render_template("register.html", message="Email already exists")

        cur.execute(
            "INSERT INTO `registered_customers` (`email address`,`first name`, `last name`, `date of birth`, `passport number`, `password`, `registration date`) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (email_address,first_name, last_name, date_of_birth, passport_number, password, now)
        )
        cur.close()

        session["username"] = email_address
        return redirect("/")

    return render_template("register.html")
