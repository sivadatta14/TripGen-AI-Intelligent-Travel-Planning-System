from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from groq import Groq
import os
import uuid
import urllib.request
import urllib.parse
import json
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

# Create Flask app and configure it to serve the frontend directory
frontend_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
app = Flask(__name__, static_folder=frontend_folder, static_url_path='/')
app.secret_key = "ai-travel-planner-secret-key"

CORS(app, supports_credentials=True)

# Serve frontend static files
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'signin.html')

@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'signin.html')


def get_db_connection():
    conn = sqlite3.connect('travel_planner.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            trip_id TEXT PRIMARY KEY,
            user_id INTEGER,
            current_location TEXT,
            destination TEXT,
            days TEXT,
            travelers TEXT,
            budget TEXT,
            travel_style TEXT,
            transport_style TEXT,
            preferences TEXT,
            itinerary TEXT,
            restaurants TEXT,
            hotels TEXT,
            budget_breakdown TEXT,
            is_saved BOOLEAN DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# =========================
# AUTH ROUTES
# =========================

@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    
    if not name or not email or not password:
        return jsonify({"error": "Missing fields"}), 400
        
    hashed_password = generate_password_hash(password)
    
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, hashed_password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Email already exists"}), 400
        
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    
    return jsonify({"success": True})


@app.route("/api/auth/signin", methods=["POST"])
def signin():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    
    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]
        return jsonify({"success": True, "name": user["name"]})
        
    return jsonify({"error": "Invalid email or password"}), 401


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    if "user_id" in session:
        return jsonify({"logged_in": True, "name": session.get("user_name"), "email": session.get("user_email")})
    return jsonify({"logged_in": False}), 401



# =========================
# GROQ CLIENT
# =========================

client = Groq(
    api_key=os.environ.get("GROQ_API_KEY")
)

GROQ_MODEL = "openai/gpt-oss-120b"


def get_route_distance(origin, destination):
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return None
        
    try:
        url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={urllib.parse.quote(origin)}&destinations={urllib.parse.quote(destination)}&key={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'OK':
                element = data['rows'][0]['elements'][0]
                if element.get('status') == 'OK':
                    distance_value = element['distance']['value'] / 1000.0
                    return distance_value
    except Exception as e:
        print(f"Error fetching distance: {e}")
    return None


def ask_groq(prompt):

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=4096,
    )

    return response.choices[0].message.content


def ask_groq_json(prompt):

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
        max_tokens=2048,
    )

    return response.choices[0].message.content



# =========================
# GENERATE ITINERARY
# =========================

def generate_itinerary(
    current_location,
    destination,
    days,
    travelers,
    budget,
    travel_style,
    transport_style,
    preferences,
    budget_breakdown
):

    transport_cost = budget_breakdown.get("Transport", 0)
    transport_source = budget_breakdown.get("Transport Source", "Estimated")
    remaining_budget = max(0, float(budget) - transport_cost)

    prompt = f"""
Create a personalized travel itinerary.

Current Location: {current_location}
Destination: {destination}
Number of days: {days}
Number of travelers: {travelers}
Total Budget for ALL travelers for the ENTIRE trip: ₹{budget}
Transport Cost (already deducted): ₹{transport_cost} ({transport_source})
Remaining Budget for Accommodation, Food, Activities: ₹{remaining_budget}
Travel style: {travel_style}
Transport style: {transport_style}
Preferences: {", ".join(preferences)}

Requirements:

- Create exactly {days} days.
- Each day must have Morning, Afternoon, and Evening.
- Suggest realistic places and activities in {destination}.
- Match the travel style, transport style, and selected preferences.
- CRITICAL: Use the remaining budget of ₹{remaining_budget} across accommodation, food, and activities.
- Ensure the estimated costs align with the remaining budget.
- Avoid repeating the same attraction.
- Keep the plan practical for the number of days.
- Give useful descriptions for each activity.
- Do not include places that are obviously outside the destination.
- Keep travel time between nearby places practical.
- Include approximate times for activities.
- Make the itinerary easy for a traveler to follow.

IMPORTANT FORMAT:

DAY 1 — Short Day Title

MORNING
Time: 08:00 AM - 11:00 AM
Place: Name of place
Description: Explain what to do and why it is worth visiting.
Estimated Cost: ₹ amount

AFTERNOON
Time: 12:00 PM - 03:30 PM
Place: Name of place
Description: Explain the activity.
Estimated Cost: ₹ amount

EVENING
Time: 04:30 PM - 07:30 PM
Place: Name of place
Description: Explain the activity.
Estimated Cost: ₹ amount

Continue the same format for every day.

IMPORTANT:
- Put each DAY on a separate line.
- Put MORNING, AFTERNOON and EVENING on separate lines.
- Leave a blank line between sections.
- Do not combine multiple days into one paragraph.
- Do not use Markdown tables.
- Do not repeat attractions.
- Return only the itinerary.
"""

    try:
        return ask_groq(prompt)

    except Exception as error:
        return (
            "AI is temporarily unavailable. "
            "Please try generating your trip again in a moment. "
            f"Error: {str(error)}"
        )


# =========================
# GENERATE RESTAURANTS
# =========================

def generate_restaurants(
    destination,
    budget,
    preferences
):

    prompt = f"""
Recommend 5 restaurants or food places in {destination} for a traveler.

Budget: ₹{budget}
Preferences: {", ".join(preferences)}

Requirements:
- Recommend places that are actually associated with {destination}.
- Do not invent ratings or review counts.
- Give realistic approximate price ranges.
- Include different food options where possible.
- Prefer local and well-known food places.
- Do not repeat the same restaurant.
- Keep the recommendations useful for tourists.

IMPORTANT FORMAT:

RESTAURANT 1
Name: Restaurant name
Cuisine: Cuisine type
Price: ₹200 - ₹500
Description: Short description of what the place is known for.

RESTAURANT 2
Name: Restaurant name
Cuisine: Cuisine type
Price: ₹300 - ₹600
Description: Short description.

RESTAURANT 3
Name: Restaurant name
Cuisine: Cuisine type
Price: ₹200 - ₹500
Description: Short description.

RESTAURANT 4
Name: Restaurant name
Cuisine: Cuisine type
Price: ₹300 - ₹600
Description: Short description.

RESTAURANT 5
Name: Restaurant name
Cuisine: Cuisine type
Price: ₹200 - ₹500
Description: Short description.

Return only the restaurant recommendations.
"""

    try:
        return ask_groq(prompt)

    except Exception:
        return "Restaurant recommendations are temporarily unavailable."


# =========================
# GENERATE HOTELS
# =========================

def generate_hotels(
    destination,
    budget,
    preferences
):

    prompt = f"""
Recommend 5 hotels or accommodation options in {destination} for a traveler.

Budget: ₹{budget}
Preferences: {", ".join(preferences)}

Requirements:
- Recommend hotels that are actually associated with {destination}.
- Do not invent ratings or review counts.
- Give realistic approximate prices per night.
- Include different budget levels where possible.
- Prefer well-known and useful accommodation options for tourists.
- Do not repeat the same hotel.
- Consider the traveler's budget.
- Keep the recommendations practical.

IMPORTANT FORMAT:

HOTEL 1
Name: Hotel name
Category: Budget / Mid-range / Luxury
Price: ₹1,500 - ₹3,000 per night
Description: Short description of the hotel and its location.

HOTEL 2
Name: Hotel name
Category: Budget / Mid-range / Luxury
Price: ₹2,000 - ₹4,000 per night
Description: Short description.

HOTEL 3
Name: Hotel name
Category: Budget / Mid-range / Luxury
Price: ₹3,000 - ₹5,000 per night
Description: Short description.

HOTEL 4
Name: Hotel name
Category: Budget / Mid-range / Luxury
Price: ₹2,500 - ₹5,000 per night
Description: Short description.

HOTEL 5
Name: Hotel name
Category: Budget / Mid-range / Luxury
Price: ₹4,000 - ₹8,000 per night
Description: Short description.

Return only the hotel recommendations.
"""

    try:
        return ask_groq(prompt)

    except Exception:
        return "Hotel recommendations are temporarily unavailable."


# =========================
# API: GENERATE TRIP
# =========================

@app.route("/api/generate", methods=["POST"])
def api_generate():

    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    current_location= data.get("current_location", "")
    destination     = data.get("destination", "")
    days            = data.get("days", "1")
    travelers       = data.get("travelers", "1")
    budget          = data.get("budget", "0")
    travel_style    = data.get("travel_style", "Balanced")
    transport_style = data.get("transport_style", "Car")
    preferences     = data.get("preferences", [])

    # Validate days
    try:
        days_number = int(days)
    except Exception:
        days_number = 1

    if days_number < 1:
        days_number = 1


    # Validate budget
    try:
        budget_number = float(budget)
    except Exception:
        budget_number = 0


    real_distance_km = get_route_distance(current_location, destination)
    
    if real_distance_km:
        distance_context = f"The actual driving/route distance is precisely {real_distance_km:.1f} km. You MUST use this exact distance for all transport calculations."
    else:
        distance_context = f"Estimate the real driving/rail distance between {current_location} and {destination} in km."

    budget_prompt = f"""
Calculate realistic minimum costs and validate the budget for this trip. Return ONLY a valid JSON object.

Current Location: {current_location}
Destination: {destination}
Number of days: {days_number}
Number of travelers: {travelers}
Total Budget: ₹{budget_number} (for ALL travelers and the ENTIRE trip)
Transport Style: {transport_style}

Rules for Transportation Cost:
1. {distance_context}
2. Based on {transport_style}:
   - Bus / RTC: Estimate official RTC/government bus fare for {travelers} people (round trip).
   - Train: Estimate official Indian Railways fare (Sleeper/3AC) for {travelers} people (round trip).
   - Bike / Car: Calculate fuel cost (round trip) assuming current Indian petrol/diesel prices (approx ₹100/L) and standard mileage (Bike ~40kmpl, Car ~15kmpl).
3. Provide a 'transport_source' string explaining the calculation. DO NOT invent official government fares if unsure; label it clearly as an estimate.

Rules for Other Costs:
4. min_accommodation: Realistic minimum hotel/stay cost for {travelers} people for {max(1, days_number - 1)} nights in {destination}.
5. min_food: Realistic minimum food cost for {travelers} people for {days_number} days.
6. min_activities: Realistic minimum for entry fees and local transit.

Output JSON format exactly like this:
{{
  "distance_km": number,
  "transport_cost": number,
  "transport_source": "string",
  "min_accommodation": number,
  "min_food": number,
  "min_activities": number,
  "total_minimum_required": number,
  "is_budget_sufficient": boolean
}}
"""

    import json
    try:
        validation_text = ask_groq_json(budget_prompt)
        val = json.loads(validation_text)
    except Exception as e:
        return jsonify({"error": "Failed to validate budget: " + str(e)}), 500

    if not val.get("is_budget_sufficient", True):
        return jsonify({
            "budget_error": True,
            "minimum_required": val.get("total_minimum_required", 0),
            "transport_cost": val.get("transport_cost", 0),
            "accommodation": val.get("min_accommodation", 0),
            "food": val.get("min_food", 0),
            "activities": val.get("min_activities", 0),
            "transport_source": val.get("transport_source", "Estimated calculation")
        }), 400


    # Budget breakdown
    budget_breakdown = {
        "Accommodation": val.get("min_accommodation", 0),
        "Food":          val.get("min_food", 0),
        "Transport":     val.get("transport_cost", 0),
        "Transport Source": val.get("transport_source", ""),
        "Activities":    val.get("min_activities", 0),
        "Shopping":      0,
    }
    
    # Put remaining budget into "Shopping / Other"
    remaining = max(0, budget_number - val.get("total_minimum_required", 0))
    budget_breakdown["Shopping"] = remaining


    # Generate AI content
    itinerary   = generate_itinerary(current_location, destination, days_number, travelers, budget, travel_style, transport_style, preferences, budget_breakdown)
    restaurants = generate_restaurants(destination, budget, preferences)
    hotels      = generate_hotels(destination, budget, preferences)


    # Store trip in DB
    trip_id = str(uuid.uuid4())
    user_id = session.get("user_id")
    
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO trips (
            trip_id, user_id, current_location, destination, days, travelers, budget, 
            travel_style, transport_style, preferences, itinerary, restaurants, hotels, 
            budget_breakdown, is_saved
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    ''', (
        trip_id, user_id, current_location, destination, days_number, travelers, budget,
        travel_style, transport_style, json.dumps(preferences), itinerary, restaurants, hotels,
        json.dumps(budget_breakdown)
    ))
    conn.commit()
    conn.close()

    session["trip_id"] = trip_id

    return jsonify({
        "trip_id":          trip_id,
        "current_location": current_location,
        "destination":      destination,
        "days":             days_number,
        "travelers":        travelers,
        "budget":           budget,
        "travel_style":     travel_style,
        "transport_style":  transport_style,
        "preferences":      preferences,
        "itinerary":        itinerary,
        "restaurants":      restaurants,
        "hotels":           hotels,
        "budget_breakdown": budget_breakdown,
    })


# =========================
# API: GET TRIP
# =========================

@app.route("/api/trip/<trip_id>", methods=["GET"])
def api_get_trip(trip_id):

    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE trip_id = ?", (trip_id,)).fetchone()
    conn.close()
    
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    trip_dict = dict(trip)
    trip_dict["preferences"] = json.loads(trip_dict["preferences"])
    trip_dict["budget_breakdown"] = json.loads(trip_dict["budget_breakdown"])
    return jsonify(trip_dict)


# =========================
# API: SAVE TRIP
# =========================

@app.route("/api/save-trip", methods=["POST"])
def api_save_trip():

    data    = request.get_json()
    trip_id = data.get("trip_id") if data else None

    if not trip_id:
        return jsonify({"error": "Trip ID required"}), 400
        
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    trip = conn.execute("SELECT * FROM trips WHERE trip_id = ?", (trip_id,)).fetchone()
    if not trip:
        conn.close()
        return jsonify({"error": "Trip not found"}), 404
        
    conn.execute("UPDATE trips SET is_saved = 1, user_id = ? WHERE trip_id = ?", (user_id, trip_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True})


# =========================
# API: SAVED TRIPS LIST
# =========================

@app.route("/api/saved-trips", methods=["GET"])
def api_saved_trips():

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    trips = conn.execute("SELECT * FROM trips WHERE user_id = ? AND is_saved = 1 ORDER BY ROWID DESC", (user_id,)).fetchall()
    conn.close()
    
    trips_list = []
    for trip in trips:
        td = dict(trip)
        td["preferences"] = json.loads(td["preferences"])
        td["budget_breakdown"] = json.loads(td["budget_breakdown"])
        td["id"] = td["trip_id"]
        trips_list.append(td)

    return jsonify({"trips": trips_list})


# =========================
# API: DELETE SAVED TRIP
# =========================

@app.route("/api/saved-trips/<trip_id>", methods=["DELETE"])
def api_delete_saved_trip(trip_id):

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    conn.execute("UPDATE trips SET is_saved = 0 WHERE trip_id = ? AND user_id = ?", (trip_id, user_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True})


# =========================
# RUN
# =========================

if __name__ == "__main__":

    app.run(debug=True, port=5000)
