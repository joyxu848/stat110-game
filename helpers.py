import requests

from flask import redirect, render_template, session
from functools import wraps


def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def lookup(symbol):
    """Look up quote for symbol."""
    url = f"https://finance.cs50.io/quote?symbol={symbol.upper()}"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for HTTP error responses
        quote_data = response.json()
        return {
            "name": quote_data["companyName"],
            "price": quote_data["latestPrice"],
            "symbol": symbol.upper()
        }
    except requests.RequestException as e:
        print(f"Request error: {e}")
    except (KeyError, ValueError) as e:
        print(f"Data parsing error: {e}")
    return None


def process_holdings(holdings):
    """ Prepare holdings for portfolio rendering """
    portfolio_total = 0.0
    for row in holdings:
        symbol = row["symbol"]
        shares = row["total_shares"]
        quote = lookup(symbol)
        if not quote:
            # trouble shooting for when lookup fails
            row.update({
                "name": symbol,
                "price": None,
                "current_price": 0.0,
                "total_value": 0.0,
                "quote_error": True
            })
            continue
        current_price = float(quote["price"])
        total_value = shares * current_price
        portfolio_total += total_value
        row.update({
            "name": quote["name"],
            "price": current_price,
            "current_price": current_price,
            "total_value": total_value,
            "quote_error": False
        })
    return holdings, portfolio_total


def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"

