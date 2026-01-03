# Simple Flask app ONLY for PythonAnywhere to enable game save transfers
# Upload this file to PythonAnywhere instead of your main flask_app.py

from flask import Flask, render_template

app = Flask(__name__)
app.secret_key = 'transfer-only-app'

@app.route('/')
@app.route('/transfer-saves')
def transfer_saves():
    return render_template('transfer_saves.html')

if __name__ == '__main__':
    app.run(debug=True)
