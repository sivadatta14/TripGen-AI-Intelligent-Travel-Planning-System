// =========================
// API BASE URL
// Change this if your backend runs on a different port or host.
// =========================

const API_BASE = ""; // Use relative path for deployed app


// =========================
// GENERATE TRIP
// =========================

async function generateTrip(formData) {

    const response = await fetch(`${API_BASE}/api/generate`, {
        method: "POST",
        credentials: "include",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(formData)
    });

    if (!response.ok) {
        const error = await response.json();
        if (error.budget_error) {
            throw error;
        }
        throw new Error(error.error || "Failed to generate trip");
    }

    return response.json();

}


// =========================
// GET TRIP BY ID
// =========================

async function getTrip(tripId) {

    const response = await fetch(`${API_BASE}/api/trip/${tripId}`, {
        credentials: "include"
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Trip not found");
    }

    return response.json();

}


// =========================
// SAVE TRIP
// =========================

async function saveTrip(tripId) {

    const response = await fetch(`${API_BASE}/api/save-trip`, {
        method: "POST",
        credentials: "include",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ trip_id: tripId })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Failed to save trip");
    }

    return response.json();

}


// =========================
// GET SAVED TRIPS
// =========================

async function getSavedTrips() {

    const response = await fetch(`${API_BASE}/api/saved-trips`, {
        credentials: "include"
    });

    if (!response.ok) {
        throw new Error("Failed to load saved trips");
    }

    return response.json();

}


// =========================
// DELETE SAVED TRIP
// =========================

async function deleteSavedTrip(tripId) {

    const response = await fetch(`${API_BASE}/api/saved-trips/${tripId}`, {
        method: "DELETE",
        credentials: "include"
    });

    if (!response.ok) {
        throw new Error("Failed to remove trip");
    }

    return response.json();

}

// =========================
// AUTHENTICATION
// =========================

async function signUp(name, email, password) {
    const response = await fetch(`${API_BASE}/api/auth/signup`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Failed to sign up");
    }
    return response.json();
}

async function signIn(email, password) {
    const response = await fetch(`${API_BASE}/api/auth/signin`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
    });
    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "Failed to sign in");
    }
    return response.json();
}

async function logOut() {
    await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        credentials: "include"
    });
    window.location.href = "signin.html";
}

async function checkAuth() {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
        credentials: "include"
    });
    if (!response.ok) {
        return null;
    }
    return response.json();
}
