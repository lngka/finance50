from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import gettempdir

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = gettempdir()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    # get user's current balance:
    # check user cash
    cash = db.execute("SELECT cash FROM users WHERE UserID = :UserID", UserID=session["user_id"])
    # db.execute return a list of 1 element, which contains a dict of 1 element, e.g. [{'cash': 10000}]
    cash = cash[0]["cash"]
    
    # get user's portfolio
    portfolio = db.execute("SELECT Symbol, Ammount FROM portfolio WHERE UserID = :UserID", UserID=session["user_id"])
    
    # calculate shares value of the whole portfolio
    shares_value = 0
    
    # update portfolio with current price and total value of each holding
    for item in portfolio:
        current_price = lookup(item["Symbol"]).get("price")
        total_value = round(item["Ammount"]*current_price, 2)
        shares_value += total_value
        item.update({"current_price":current_price, "total_value":total_value})
    
    return render_template("index.html", portfolio=portfolio, shares_value=round(shares_value,2), cash=round(cash,2))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # ensure input of symbol
        if not request.form.get("symbol"):
            return apology("Missing symbol")
            
        # ensure input of ammount    
        if not request.form.get("ammount"):
            return apology("Invalid ammount")
            
        # if user come direct from index page
        if request.form.get("ammount") == "direct":
            return render_template("buy.html", symbol=request.form.get("symbol"))
        
        # lookup symbol
        symbol = request.form.get("symbol").upper()
        result = lookup(symbol)
        if not result:
            return apology("Could not find symbol")
            
        # current price of symbol
        price = result.get("price")
        
        # check user cash
        cash = db.execute("SELECT cash FROM users WHERE UserID = :UserID", UserID=session["user_id"])
        # db.execute return a list of 1 element, which contains a dict of 1 element, e.g. [{'cash': 10000}]
        cash = cash[0]["cash"]
        
        # check if user can afford the purchase
        ammount = int(request.form.get("ammount"))
        if cash < ammount*price:
            return apology("Not enough cash")
        
        # else if enough cash
        # calculate & update user's cash
        cash = cash - ammount*price
        db.execute("UPDATE users SET cash = :cash WHERE UserID = :UserID",cash=cash, UserID=session["user_id"])
        
        # update user's history
        db.execute("INSERT INTO history(UserID, 'Transaction Type', Symbol, Ammount, Price) VALUES(:UserID, 'Buy', :symbol, :ammount, :price)",
                    UserID=session["user_id"], symbol=symbol, ammount=ammount,price=price)
                    
        # update user's portfolio
        rows = db.execute("SELECT * FROM  portfolio WHERE UserID = :UserID AND Symbol = :symbol", UserID=session["user_id"], symbol=symbol)
        if len(rows) == 1:
            current_share = rows[0]["Ammount"]
            db.execute("UPDATE portfolio SET ammount = :ammount WHERE UserID = :UserID AND Symbol = :symbol", 
                        ammount=current_share+ammount, UserID=session["user_id"], symbol=symbol)
            flash("Purchased!")
        else:
            db.execute("INSERT INTO portfolio(UserID, Symbol, Ammount) VALUES(:UserID, :symbol, :ammount)",
                        UserID=session["user_id"], symbol=symbol, ammount=ammount)
            flash("Purchased!")
        
        # bring user back to index page
        return redirect(url_for("index"))
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    
    """Show history of transactions."""
    history = db.execute("SELECT * FROM history WHERE UserID = :UserID", UserID=session["user_id"])
    return render_template("history.html", history=history)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["UserID"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("Must provide stock symbol")
        
        # lookup symbol
        symbol = request.form.get("symbol")
        result = lookup(symbol)
        
        # if no result
        if not symbol:
            return apology("Could not find symbol")
        
        # show result to user
        else:
            return render_template("quoted.html", stock=result.get("name"), symbol=result.get("symbol"), price=result.get("price"))
        
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # ensure username was submitted
        if not request.form.get("username"):
            return apology("Missing username")
            
        # ensure password was submitted    
        if not request.form.get("password") or not request.form.get("password_confirm"):
            return apology("Missing password")
       
        # ensure password and password_confirm match:
        if not request.form.get("password") == request.form.get("password_confirm"):
            return apology("Password confirmation doesn't match")
        
        # get data:
        username = request.form.get("username")
        password = request.form.get("password")
        hash = pwd_context.encrypt(password)
        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)
        
        if not result:
            return apology("Exsisting username")
        
        else:
            # query database for username
            rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
            
            # remember which user has logged in
            session["user_id"] = rows[0]["UserID"]
            
            # bring user to homepage
            return redirect(url_for("index"))
        
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # ensure input of symbol
        if not request.form.get("symbol"):
            return apology("Missing symbol")
            
        # ensure input of ammount    
        if not request.form.get("ammount"):
            return apology("Invalid ammount")
            
        # if user come direct from index page
        if request.form.get("ammount") == "direct":
            return render_template("sell.html", symbol=request.form.get("symbol"))
        
        # lookup symbol
        symbol = request.form.get("symbol")
        rows = db.execute("SELECT * FROM portfolio WHERE UserID = :UserID AND Symbol = :symbol", UserID=session["user_id"], symbol=symbol)
        if len(rows) !=1:
            return apology("Selected Stock does not exist in your portfolio")
            
        # current price of symbol
        price = lookup(symbol).get("price")
        
        # check user cash
        cash = db.execute("SELECT cash FROM users WHERE UserID = :UserID", UserID=session["user_id"])
        # db.execute return a list of 1 element, which contains a dict of 1 element, e.g. [{'cash': 10000}]
        cash = cash[0]["cash"]
        
        #get user's current shares of selected stock
        current_shares = db.execute("SELECT * FROM portfolio WHERE UserID = :UserID AND Symbol = :symbol", UserID=session["user_id"], symbol=symbol)
        current_shares = current_shares[0].get("Ammount")
        
        # check if user have enough to sell
        sell_ammount = int(request.form.get("ammount"))
        if sell_ammount > current_shares:
            return apology("Not enough shares to sell")
        
        # calculate & update user's cash
        cash = cash + sell_ammount*price
        db.execute("UPDATE users SET cash = :cash WHERE UserID = :UserID",cash=cash, UserID=session["user_id"])
        
        # update user's history
        db.execute("INSERT INTO history(UserID, 'Transaction Type', Symbol, Ammount, Price) VALUES(:UserID, 'Sell', :symbol, :ammount, :price)",
                    UserID=session["user_id"], symbol=symbol, ammount=sell_ammount,price=price)
        
        #update user's portfolio:
        if sell_ammount == current_shares:
            db.execute("DELETE FROM portfolio WHERE UserID = :UserID AND Symbol = :symbol", UserID=session["user_id"], symbol=symbol)
            flash("Sold!")
            return redirect(url_for("index"))
            
        if sell_ammount < current_shares:
            db.execute("UPDATE portfolio SET ammount = :ammount WHERE UserID = :UserID AND Symbol = :symbol", 
                        ammount=current_shares - sell_ammount, UserID=session["user_id"], symbol=symbol)
            flash("Sold!")
            return redirect(url_for("index"))
            
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html")

@app.route("/change", methods=["GET", "POST"])
@login_required
def change():
    """Empower user to change password"""
    # if user submited the form
    if request.method == "POST":
        
        # ensure form is filled:
        if not request.form.get("password"):
            return apology("Missing password")
        if not request.form.get("newpassword"):
            return apology("Missing new password")
        if not request.form.get("password_confirm"):
            return apology("Missing password confirmation")
        
        # get hash of the old password
        hash = db.execute("SELECT hash FROM users WHERE UserID = :UserID", UserID=session["user_id"])
        # because previous function return a dict inside a list:
        hash = hash[0]["hash"] 
        
        # check if old password is correct
        if not pwd_context.verify(request.form.get("password"), hash):
            return apology("Wrong password")
            
        # check if password confirmation is correct
        if request.form.get("newpassword") != request.form.get("password_confirm"):
            return apology("Password confirmation doesn't match")
            
        else:
            #else change user password
            newhash = pwd_context.encrypt(request.form.get("newpassword"))
            db.execute("UPDATE users SET hash= :newhash WHERE UserID = :UserID", newhash=newhash, UserID=session["user_id"])
            
            #inform and logout
            flash("Password changed! Please login again")
            return render_template("login.html")
    
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("change.html")