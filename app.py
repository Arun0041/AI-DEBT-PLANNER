import google.generativeai as genai
from flask import Flask, render_template, request, session
from flask_session import Session
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-here")
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# Debt planner function with enhanced calculations
def calculate_debt_plan(debt_amount, interest_rate, monthly_payment):
    monthly_interest = interest_rate / 100 / 12
    months = 0
    total_interest = 0
    remaining_debt = debt_amount
    monthly_details = []
    
    while remaining_debt > 0 and months < 600:  # Add safety limit of 50 years
        interest = remaining_debt * monthly_interest
        total_interest += interest
        principal_payment = monthly_payment - interest
        
        if principal_payment <= 0:
            return None
            
        if principal_payment > remaining_debt:
            principal_payment = remaining_debt
            monthly_payment = principal_payment + interest
        
        remaining_debt -= principal_payment
        months += 1
        
        if months <= 12 or months % 12 == 0 or remaining_debt <= 0:  
            monthly_details.append({
                "month": months,
                "payment": monthly_payment,
                "principal": principal_payment,
                "interest": interest,
                "remaining": remaining_debt
            })
    
    total_paid = debt_amount + total_interest
    return {
        "months": months,
        "years": months / 12,
        "total_paid": total_paid,
        "total_interest": total_interest,
        "original_debt": debt_amount,
        "interest_rate": interest_rate,
        "monthly_payment": monthly_payment,
        "monthly_details": monthly_details
    }

# Route for the homepage
@app.route("/", methods=["GET", "POST"])
def index():
    # Initialize or reset session variables on GET request
    if request.method == "GET":
        session.pop("chat_history", None)
        session.pop("show_chat_button", None)
        session.pop("chat_mode", None)
        session.pop("debt_data", None)
        session.pop("message", None) 
        session.pop("explanation", None) 
        session["chat_history"] = []
        session["show_chat_button"] = False
        session["chat_mode"] = False
    elif "chat_history" not in session:
        session["chat_history"] = []
        session["show_chat_button"] = False
        session["chat_mode"] = False

    if request.method == "POST":
        
        if "reset" in request.form:
            session["chat_history"] = []
            session["show_chat_button"] = False
            session["chat_mode"] = False
            session["debt_data"] = {}
            session["message"] = None
            session["explanation"] = None
            session.modified = True
            return render_template("index.html", 
                                  chat_history=session["chat_history"], 
                                  show_chat_button=session["show_chat_button"],
                                  chat_mode=session["chat_mode"])

        elif "debt" in request.form:
            debt = float(request.form["debt"])
            interest = float(request.form["interest"])
            monthly = float(request.form["monthly"])

            result = calculate_debt_plan(debt, interest, monthly)
            if result:
                months = result["months"]
                years = result["years"]
                total_paid = result["total_paid"]
                total_interest = result["total_interest"]
                
                message = (f"It will take {months} months ({years:.1f} years) to pay off your ${debt:,.2f} debt. "
                          f"You'll pay ${total_paid:,.2f} in total, which includes ${total_interest:,.2f} in interest.")
                
                model = genai.GenerativeModel("gemini-1.5-flash")
                current_date = datetime.now().strftime("%B %d, %Y")
                prompt = (
                    f"Today is {current_date}. I have a debt of ${debt:,.2f} with an annual interest rate of {interest}%. "
                    f"I can afford to pay ${monthly:,.2f} per month. Based on these numbers:\n\n"
                    f"1. It will take me {months} months ({years:.1f} years) to pay off this debt\n"
                    f"2. I'll pay ${total_interest:,.2f} in interest charges\n"
                    f"3. My total payment will be ${total_paid:,.2f}\n\n"
                    f"As a financial advisor, please:\n"
                    f"1. Explain this plan in a clear, friendly way\n"
                    f"2. Suggest 2-3 actionable strategies to pay off this debt faster\n"
                    f"3. Explain how much I could save by implementing these strategies\n"
                    f"Make your response conversational but concise (3-4 paragraphs maximum). "
                    f"Don't use bullet points or numbered lists."
                )
                
                response = model.generate_content(prompt)
                explanation = response.text
                
                session["debt_data"] = {
                    "debt": debt,
                    "interest": interest, 
                    "monthly": monthly, 
                    "months": months,
                    "years": years,
                    "total_interest": total_interest,
                    "total_paid": total_paid,
                    "monthly_details": result["monthly_details"]
                }
                
                session["chat_history"] = [{"user": "Initial Plan", "ai": explanation}]
                session["message"] = message  # Store initial message
                session["explanation"] = explanation  # Store initial explanation
                session["show_chat_button"] = True
                
            else:
                message = "Your monthly payment is too low to cover the interest! You'll never pay off this debt with that payment."
                monthly_min = debt * (interest / 100 / 12)
                explanation = f"You need to increase your monthly payment to at least ${monthly_min:.2f} to cover the monthly interest. With your current payment of ${monthly:.2f}, your debt will continue to grow instead of shrink."
                session["message"] = message
                session["explanation"] = explanation
                session["show_chat_button"] = False
            
            session.modified = True
            return render_template("index.html", 
                                  message=session["message"], 
                                  explanation=session["explanation"], 
                                  chat_history=session["chat_history"], 
                                  show_chat_button=session["show_chat_button"],
                                  chat_mode=True)

        # Handle follow-up chat input
        elif "chat_input" in request.form:
            user_input = request.form["chat_input"]
            debt_data = session.get("debt_data", {})
            
            model = genai.GenerativeModel("gemini-1.5-flash")
            current_date = datetime.now().strftime("%B %d, %Y")
            chat_history_text = ""
            recent_history = session["chat_history"][-3:] if len(session["chat_history"]) > 3 else session["chat_history"]
            for chat in recent_history:
                if chat["user"] != "Initial Plan":
                    chat_history_text += f"User: {chat['user']}\nAI: {chat['ai']}\n\n"
            
            prompt = (
                f"Today is {current_date}. User asked: '{user_input}'\n\n"
                f"Recent conversation:\n{chat_history_text}\n"
                f"Context: User has a debt of ${debt_data.get('debt', 0):,.2f} with {debt_data.get('interest', 0)}% annual interest. "
                f"Their monthly payment is ${debt_data.get('monthly', 0):,.2f}. "
                f"It will take {debt_data.get('months', 0)} months ({debt_data.get('years', 0):.1f} years) to pay off. "
                f"They'll pay ${debt_data.get('total_interest', 0):,.2f} in interest and ${debt_data.get('total_paid', 0):,.2f} total.\n\n"
                f"Response guidelines:\n"
                f"1. Answer in a friendly, conversational, and helpful tone\n"
                f"2. If they ask about paying off debt faster, provide specific actionable advice\n"
                f"3. If they ask about impact of additional payments, provide calculations\n"
                f"4. If they ask about financial concepts, explain them simply\n"
                f"5. Keep responses concise (2-3 paragraphs)\n"
                f"6. If the question isn't related to personal finance, gently guide them back to debt topics\n"
                f"7. Don't use bullet points or numbered lists\n"
                f"8. Start your response directly answering their question without any preamble"
            )
            
            response = model.generate_content(prompt)
            session["chat_history"].append({"user": user_input, "ai": response.text})
            session.modified = True
            
            return render_template("index.html", 
                                  message=session.get("message", ""),  
                                  explanation=session.get("explanation", ""),
                                  chat_history=session["chat_history"], 
                                  show_chat_button=True,
                                  chat_mode=True)

    return render_template("index.html", 
                          chat_history=session["chat_history"], 
                          show_chat_button=session["show_chat_button"],
                          chat_mode=session["chat_mode"])

if __name__ == "__main__":
    app.run(debug=True)