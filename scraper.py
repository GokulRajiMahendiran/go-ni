from flask import Flask, jsonify, render_template
import requests
import pandas as pd
from bs4 import BeautifulSoup
import json

app = Flask(__name__)

def scrape_nifty_option_chain():
    url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
    headers = {
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36 OPR/68.0.3618.206",
        "Cookie": "8A87B46ABA4CAFF3B69F913708597828~xM8YKIspOw4k2OTekhqVI8Ft8AHi/RYKbvLqfKirkbafd1XOqJELenPBKr4Y+FAgbqei34v6NKmWyp1RWvhDhh2jrLXAela7ZdmyrHShEPCaVopVDul8R91B2SbFshwrUsS7yKn5+cmpmaF25zGeiAjHTfTMnii7F2E1slCnkEo="
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print("Failed to retrieve data from NSE API.")
        return None

def format_option_chain(option_chain_data):
    if "filtered" in option_chain_data and "data" in option_chain_data["filtered"]:
        data = option_chain_data["filtered"]["data"]
        formatted_data = []
        
        underlying_value = None  # Initialize underlying value
        max_ce_oi = 0
        max_ce_strike = None
        max_pe_oi = 0
        max_pe_strike = None
        
        for entry in data:
            # Extract underlying value
            if not underlying_value and "underlyingValue" in entry["PE"]:
                underlying_value = entry["PE"]["underlyingValue"]
            
            # Calculate interpretations for CE and PE sides
            ce_interpretation = ""
            pe_interpretation = ""
            if entry["CE"].get("changeinOpenInterest") > 0 and entry["CE"].get("pChange") > 0:
                ce_interpretation = "FRESH LONG"
            elif entry["CE"].get("changeinOpenInterest") < 0 and entry["CE"].get("pChange") < 0:
                ce_interpretation = "LONG UNWIND"
            elif entry["CE"].get("changeinOpenInterest") > 0 and entry["CE"].get("pChange") < 0:
                ce_interpretation = "FRESH SHORT"
            elif entry["CE"].get("changeinOpenInterest") < 0 and entry["CE"].get("pChange") > 0:
                ce_interpretation = "SHORT COVERING"
            else:
                ce_interpretation = "-"
                
            if entry["PE"].get("changeinOpenInterest") > 0 and entry["PE"].get("pChange") > 0:
                pe_interpretation = "FRESH LONG"
            elif entry["PE"].get("changeinOpenInterest") < 0 and entry["PE"].get("pChange") < 0:
                pe_interpretation = "LONG UNWIND"
            elif entry["PE"].get("changeinOpenInterest") > 0 and entry["PE"].get("pChange") < 0:
                pe_interpretation = "FRESH SHORT"
            elif entry["PE"].get("changeinOpenInterest") < 0 and entry["PE"].get("pChange") > 0:
                pe_interpretation = "SHORT COVERING"
            else:
                pe_interpretation = "-"
                
            formatted_data.append({
                "CE_Sign": ce_interpretation,
                "CE_OI": entry["CE"].get("openInterest"),
                "CE_COI": entry["CE"].get("changeinOpenInterest"),
                "CE_Volume": entry["CE"].get("totalTradedVolume"),
                "CE_IV": entry["CE"].get("impliedVolatility"),
                "CE_LTP": entry["CE"].get("lastPrice"),
                "CE_PChange": entry["CE"].get("change"),
                "Strike": round(entry["CE"].get("strikePrice") / 50) * 50,  # Round off the strike price for sorting
                "PE_PChange": entry["PE"].get("change"),
                "PE_LTP": entry["PE"].get("lastPrice"),
                "PE_IV": entry["PE"].get("impliedVolatility"),
                "PE_Volume": entry["PE"].get("totalTradedVolume"),
                "PE_COI": entry["PE"].get("changeinOpenInterest"),
                "PE_OI": entry["PE"].get("openInterest"),
                "PE_Sign": pe_interpretation
            })
            
        # Round off the underlying value and filter the strikes within ±350
        rounded_underlying_value = round(underlying_value / 50) * 50
        filtered_data = [entry for entry in formatted_data if rounded_underlying_value - 350 <= entry["Strike"] <= rounded_underlying_value + 350]
        
        # Calculate max CE and PE open interest after filtering
        for entry in filtered_data:
            if entry["CE_OI"] > max_ce_oi:
                max_ce_oi = entry["CE_OI"]
                max_ce_strike = entry["Strike"]
            if entry["PE_OI"] > max_pe_oi:
                max_pe_oi = entry["PE_OI"]
                max_pe_strike = entry["Strike"]
        
        # Calculate the sum of the last 9 rows for CE_ChangeInOI
        ce_change_in_oi_sum = sum(entry["CE_COI"] for entry in filtered_data[-9:])
        # Calculate the sum of the top 9 rows for PE_ChangeInOI
        pe_change_in_oi_sum = sum(entry["PE_COI"] for entry in filtered_data[:9])
        
        # Calculate the percentage change between CE and PE
        if pe_change_in_oi_sum != 0:
            ce_pe_percentage_change = abs(ce_change_in_oi_sum - pe_change_in_oi_sum) / pe_change_in_oi_sum * 100
        else:
            ce_pe_percentage_change = 0
        
        # Calculate the comparison value based on the provided formula
        if (ce_change_in_oi_sum - pe_change_in_oi_sum) / pe_change_in_oi_sum * 100 > 50:
            if ce_change_in_oi_sum >= pe_change_in_oi_sum:
                ce_pe_comparison = "CE is {:.2f}% higher".format(ce_pe_percentage_change)
            else:
                ce_pe_comparison = "PE is {:.2f}% higher".format(ce_pe_percentage_change)
        elif (pe_change_in_oi_sum - ce_change_in_oi_sum) / ce_change_in_oi_sum * 100 > 50:
            ce_pe_comparison = "PE is {:.2f}% higher".format(ce_pe_percentage_change)
        else:
            ce_pe_comparison = "Sideways ({:.2f}% change)".format(ce_pe_percentage_change)
        
        return filtered_data, ce_pe_comparison, underlying_value, ce_change_in_oi_sum, pe_change_in_oi_sum, max_ce_oi, max_ce_strike, max_pe_oi, max_pe_strike
    
    else:
        print("Unexpected data format:", option_chain_data)
        return None, None, None, None, None, None, None, None, None



@app.route("/")
def index():
    option_chain_data = scrape_nifty_option_chain()
    if option_chain_data:
        formatted_data, ce_pe_comparison, nifty_underlying, ce_change_in_oi_sum, pe_change_in_oi_sum, max_ce_oi, max_ce_strike, max_pe_oi, max_pe_strike = format_option_chain(option_chain_data)
        if formatted_data:
            ce_higher = True
            if "PE is" in ce_pe_comparison:
                ce_higher = False
            df = pd.DataFrame(formatted_data)
            sideways_percentage = ce_pe_comparison.split('(')[1][:-2] if "Sideways" in ce_pe_comparison else None
            return render_template('index.html', table=df.to_html(index=False), comparison=ce_pe_comparison, ce_higher=ce_higher, nifty_underlying=nifty_underlying, ce_change_in_oi_sum=ce_change_in_oi_sum, pe_change_in_oi_sum=pe_change_in_oi_sum, max_ce_details={'Strike': max_ce_strike, 'CE_OI': max_ce_oi}, max_pe_details={'Strike': max_pe_strike, 'PE_OI': max_pe_oi}, sideways_percentage=sideways_percentage)
    return jsonify({"error": "Failed to fetch or format data"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
