from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    # Mock data - in the future this comes from your SQL database
    items = [
        {"title": "Hyundai Elantra 2021", "price": "241,000", "type": "sell", "loc": "Ashgabat"},
        {"title": "Modern Office", "price": "500", "type": "rent", "loc": "Mary"}
    ]
    return render_template('index.html', items=items)

if __name__ == '__main__':
    app.run(debug=True)