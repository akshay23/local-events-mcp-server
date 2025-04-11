"""
Ticketmaster MCP Server

This MCP server connects to the Ticketmaster Discover API to find upcoming events
by artist, venue, or location with ticket availability.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context

# Load environment variables
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("Local Events Assistant")

# Constants
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")
TICKETMASTER_API_BASE = "https://app.ticketmaster.com/discovery/v2"

if not TICKETMASTER_API_KEY:
    raise ValueError("TICKETMASTER_API_KEY not found in environment variables")

async def make_ticketmaster_request(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Make a request to the Ticketmaster API with proper error handling."""

    # Add API key to parameters
    params["apikey"] = TICKETMASTER_API_KEY
    url = f"{TICKETMASTER_API_BASE}/{endpoint}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return {"error": "Rate limit exceeded. Please try again later."}
            elif e.response.status_code == 401:
                return {"error": "Unauthorized. Please check your API key."}
            else:
                return {"error": f"HTTP error: {e.response.status_code}"}
        except httpx.RequestError:
            return {"error": "Failed to connect to Ticketmaster API."}
        except Exception as e:
            return {"error": f"An unexpected error occurred: {str(e)}"}
        
def format_event(event: Dict[str, Any]) -> str:
    """Format an event into a readable string."""
    name = event.get("name", "Unknown Event")
    
    # Format date
    date_info = ""
    if "dates" in event and "start" in event["dates"]:
        start_date = event["dates"]["start"]
        if "localDate" in start_date:
            date = start_date["localDate"]
            if "localTime" in start_date:
                date += f" {start_date['localTime']}"
            date_info = f"Date: {date}\n"
    
    # Format venue
    venue_info = ""
    if "embedded" in event and "_embedded" in event["embedded"] and "venues" in event["embedded"]["_embedded"]:
        venues = event["embedded"]["_embedded"]["venues"]
        if venues and len(venues) > 0:
            venue = venues[0]
            venue_name = venue.get("name", "Unknown Venue")
            city = venue.get("city", {}).get("name", "")
            state = venue.get("state", {}).get("name", "")
            country = venue.get("country", {}).get("name", "")
            location = ", ".join([part for part in [city, state, country] if part])
            venue_info = f"Venue: {venue_name}, {location}\n"
    
    # Format pricing
    price_info = ""
    if "priceRanges" in event:
        price_ranges = event["priceRanges"]
        if price_ranges and len(price_ranges) > 0:
            min_price = price_ranges[0].get("min")
            max_price = price_ranges[0].get("max")
            currency = price_ranges[0].get("currency", "USD")
            if min_price and max_price:
                price_info = f"Price Range: {min_price}-{max_price} {currency}\n"
            elif min_price:
                price_info = f"Starting Price: {min_price} {currency}\n"
    
    # Format ticket status
    ticket_info = ""
    if "dates" in event and "status" in event["dates"]:
        status = event["dates"]["status"]
        status_code = status.get("code", "")
        if status_code == "onsale":
            ticket_info = "Ticket Status: On Sale\n"
        elif status_code == "offsale":
            ticket_info = "Ticket Status: Off Sale\n"
        elif status_code == "cancelled":
            ticket_info = "Ticket Status: Cancelled\n"
        elif status_code == "postponed":
            ticket_info = "Ticket Status: Postponed\n"
        elif status_code == "rescheduled":
            ticket_info = "Ticket Status: Rescheduled\n"
    
    # Format URL
    url_info = ""
    if "url" in event:
        url_info = f"Tickets: {event['url']}\n"
    
    # Format genre
    genre_info = ""
    if "classifications" in event and event["classifications"]:
        classification = event["classifications"][0]
        segments = []
        
        if "segment" in classification and classification["segment"]:
            segment_name = classification["segment"].get("name")
            if segment_name and segment_name.lower() != "undefined":
                segments.append(segment_name)
                
        if "genre" in classification and classification["genre"]:
            genre_name = classification["genre"].get("name")
            if genre_name and genre_name.lower() != "undefined":
                segments.append(genre_name)
                
        if "subGenre" in classification and classification["subGenre"]:
            subgenre_name = classification["subGenre"].get("name")
            if subgenre_name and subgenre_name.lower() != "undefined":
                segments.append(subgenre_name)
                
        if segments:
            genre_info = f"Genre: {' | '.join(segments)}\n"
    
    # Build the formatted event string
    return f"""
Event: {name}
{date_info}{venue_info}{genre_info}{price_info}{ticket_info}{url_info}
"""

def extract_events(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract events from the API response."""
    events = []
    
    # Check if the response contains the embedded section with events
    if "_embedded" in data and "events" in data["_embedded"]:
        events = data["_embedded"]["events"]
    
    return events

# MCP Tools
@mcp.tool()
async def search_events_by_artist(artist: str, size: int = 5) -> str:
    """Search for upcoming events by artist name.

    Args:
        artist: Name of the artist or performer
        size: Number of results to return (default: 5)
    """
    params = {
        "keyword": artist,
        "size": size,
        "sort": "date,asc"
    }
    
    data = await make_ticketmaster_request("events.json", params)
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    events = extract_events(data)
    
    if not events:
        return f"No upcoming events found for artist: {artist}"
    
    formatted_events = [format_event(event) for event in events]
    
    return f"Upcoming events for {artist}:\n\n" + "\n".join(formatted_events)

@mcp.tool()
async def search_events_by_venue(venue: str, size: int = 5) -> str:
    """Search for upcoming events by venue name.

    Args:
        venue: Name of the venue
        size: Number of results to return (default: 5)
    """
    params = {
        "venueId": venue if venue.startswith("KovZ") else None,
        "keyword": None if venue.startswith("KovZ") else venue,
        "size": size,
        "sort": "date,asc"
    }
    
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}
    
    data = await make_ticketmaster_request("events.json", params)
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    events = extract_events(data)
    
    if not events:
        return f"No upcoming events found for venue: {venue}"
    
    formatted_events = [format_event(event) for event in events]
    
    return f"Upcoming events at {venue}:\n\n" + "\n".join(formatted_events)

@mcp.tool()
async def search_events_by_location(city: str, state: Optional[str] = None, country: str = "US", size: int = 5) -> str:
    """Search for upcoming events by location.

    Args:
        city: City name
        state: State code (optional, for US locations)
        country: Country code (default: US)
        size: Number of results to return (default: 5)
    """
    # Build the location string
    location = city
    if state:
        location = f"{city},{state}"
    
    params = {
        "city": city,
        "stateCode": state,
        "countryCode": country,
        "size": size,
        "sort": "date,asc"
    }
    
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}
    
    data = await make_ticketmaster_request("events.json", params)
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    events = extract_events(data)
    
    if not events:
        return f"No upcoming events found in {location}"
    
    formatted_events = [format_event(event) for event in events]
    
    return f"Upcoming events in {location}:\n\n" + "\n".join(formatted_events)

@mcp.tool()
async def get_event_details(event_id: str) -> str:
    """Get detailed information about a specific event.

    Args:
        event_id: Ticketmaster event ID
    """
    params = {}
    
    data = await make_ticketmaster_request(f"events/{event_id}.json", params)
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    return format_event(data)

@mcp.tool()
async def search_events_by_genre(genre: str, city: Optional[str] = None, size: int = 5) -> str:
    """Search for upcoming events by genre.

    Args:
        genre: Genre name (e.g., rock, pop, sports)
        city: City name for location filtering (optional)
        size: Number of results to return (default: 5)
    """
    params = {
        "classificationName": genre,
        "city": city,
        "size": size,
        "sort": "date,asc"
    }
    
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}
    
    data = await make_ticketmaster_request("events.json", params)
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    events = extract_events(data)
    
    if not events:
        location_info = f" in {city}" if city else ""
        return f"No upcoming {genre} events found{location_info}"
    
    formatted_events = [format_event(event) for event in events]
    
    location_info = f" in {city}" if city else ""
    return f"Upcoming {genre} events{location_info}:\n\n" + "\n".join(formatted_events)

@mcp.tool()
async def check_ticket_availability(event_id: str) -> str:
    """Check ticket availability for a specific event.

    Args:
        event_id: Ticketmaster event ID
    """
    params = {}
    
    data = await make_ticketmaster_request(f"events/{event_id}.json", params)
    
    if "error" in data:
        return f"Error: {data['error']}"
    
    # Get ticket status
    ticket_status = "Unknown"
    if "dates" in data and "status" in data["dates"]:
        status = data["dates"]["status"]
        status_code = status.get("code", "")
        if status_code == "onsale":
            ticket_status = "On Sale"
        elif status_code == "offsale":
            ticket_status = "Off Sale"
        elif status_code == "cancelled":
            ticket_status = "Cancelled"
        elif status_code == "postponed":
            ticket_status = "Postponed"
        elif status_code == "rescheduled":
            ticket_status = "Rescheduled"
    
    # Get ticket price range
    price_info = "Price information not available"
    if "priceRanges" in data:
        price_ranges = data["priceRanges"]
        if price_ranges and len(price_ranges) > 0:
            min_price = price_ranges[0].get("min")
            max_price = price_ranges[0].get("max")
            currency = price_ranges[0].get("currency", "USD")
            if min_price and max_price:
                price_info = f"Price Range: {min_price}-{max_price} {currency}"
            elif min_price:
                price_info = f"Starting Price: {min_price} {currency}"
    
    # Get ticket link
    ticket_link = data.get("url", "No ticket link available")
    
    event_name = data.get("name", "Unknown Event")
    
    return f"""
Ticket Availability for: {event_name}
Status: {ticket_status}
{price_info}
Ticket Link: {ticket_link}
"""

# Run the server
if __name__ == "__main__":
    mcp.run(transport='stdio')
