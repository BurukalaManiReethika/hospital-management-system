from flask import Flask, render_template

from hms.database import initialize_database
from flask import Flask, render_template, request, redirect, url_for, flash
from hms.database import initialize_database
from hms import patients

app = Flask(__name__)

# Initialize the database once when the app starts
initialize_database()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)
