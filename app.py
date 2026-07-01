from flask import Flask, render_template

from hms.database import initialize_database

app = Flask(__name__)

# Initialize the database once when the app starts
initialize_database()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


if __name__ == "__main__":
    app.run(debug=True)
