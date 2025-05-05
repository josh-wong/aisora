import phonenumbers
from phonenumbers import geocoder, carrier
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import os

# Keep track of phone number to location mappings to avoid inconsistencies.
phone_location_cache = {}

def clear_location_cache():
    """Clear the location cache to force fresh lookups"""
    global phone_location_cache
    phone_location_cache = {}
    
def get_location_from_phone_number(phone_number, force_refresh=False):
    """
    Extract location information from a phone number.
    Returns a dictionary with country, city, possible carrier, and location coordinates if available.
    
    Args:
        phone_number (str): The phone number in international format
        force_refresh (bool): Whether to ignore cached data and perform a new lookup
    """
    global phone_location_cache
    
    if not phone_number or not isinstance(phone_number, str):
        return None
    
    # If we have cached data and we're not forcing a refresh, return it.
    if phone_number in phone_location_cache and not force_refresh:
        return phone_location_cache[phone_number]
    
    try:
        # Make sure we have a properly formatted phone number with a country code.
        if not phone_number.startswith('+'):
            # If no country code is provided, we can't determine the location.
            return None
            
        # Parse the phone number.
        parsed_number = phonenumbers.parse(phone_number)
        
        # Get country.
        country = geocoder.country_name_for_number(parsed_number, "en")
        phone_carrier = carrier.name_for_number(parsed_number, "en")
        
        # Get region, which is used to extract the city.
        region = geocoder.description_for_number(parsed_number, "en")
        
        # Try to get more specific city information by using geopy.
        city = None
        location_string = None
        
        try:
            # Only proceed if there's a country.
            if country:
                # Method 1: Use the region and country together for geocoding.
                if region and region != country:
                    search_query = f"{region}, {country}"
                    
                    # Use the Nominatim geocoding service.
                    geolocator = Nominatim(user_agent="signal-ai-assistant")
                    location = geolocator.geocode(search_query, exactly_one=True, timeout=10)
                    
                    if location:
                        # Try to extract the city from the address.
                        address_components = location.raw.get('address', {})
                        
                        # Look for a city in various address fields.
                        city = (address_components.get('city') or 
                               address_components.get('town') or 
                               address_components.get('village') or
                               address_components.get('hamlet') or
                               address_components.get('county'))
                        
                        # Add location coordinates as a string.
                        if hasattr(location, 'latitude') and hasattr(location, 'longitude'):
                            location_string = f"{location.latitude},{location.longitude}"
                
                # Method 2: Try to use the area code if the city is still not found or is the same as the country.
                if not city or city == country:
                    # Extract the area code (format depends on the country).
                    area_code = None
                    if len(phone_number) > 5:
                        # For most countries, the first 5 characters include country code + area code.
                        area_code = phone_number[0:5] # Include the country code and the first few digits.
                        
                    if area_code:
                        # Try to look up just the area code in the country.
                        area_search = f"{area_code} {country}"
                        area_location = geolocator.geocode(area_search, exactly_one=True, timeout=10)
                        if area_location:
                            address = area_location.raw.get('address', {})
                            area_city = (address.get('city') or 
                                       address.get('town') or 
                                       address.get('village') or
                                       address.get('county'))
                            
                            # Only update if we found something.
                            if area_city and area_city != country:
                                city = area_city
                                
                                # Update the coordinates if there are have new ones.
                                if not location_string and hasattr(area_location, 'latitude') and hasattr(area_location, 'longitude'):
                                    location_string = f"{area_location.latitude},{area_location.longitude}"
                
                # Method 3: If a city is still not found, try the region as a direct lookup.
                if not city and region:
                    region_location = geolocator.geocode(region, exactly_one=True, timeout=10)
                    if region_location:
                        address = region_location.raw.get('address', {})
                        region_city = (address.get('city') or 
                                     address.get('town') or 
                                     address.get('village') or 
                                     address.get('county'))
                                     
                        if region_city and region_city != country:
                            city = region_city
                            if not location_string and hasattr(region_location, 'latitude') and hasattr(region_location, 'longitude'):
                                location_string = f"{region_location.latitude},{region_location.longitude}"
                
                # If a city still can't be determined, use the region as a fallback.
                if not city and region and region != country:
                    city = region
        
        except (GeocoderTimedOut, GeocoderServiceError, Exception) as e:
            print(f"Geocoding error: {e}")
            if region and region != country:
                city = region
        
        # Only use an IP-based location as a last resort when there is no city information available.
        # This avoids the VPN issue since it's only used when phone-based methods have failed.
        if (not city or city == country) and os.environ.get('ALLOW_IP_FALLBACK') == 'true':
            try:
                # Try to get a general city from the IP address (only as last resort).
                response = requests.get("https://ipinfo.io/json", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if 'city' in data and data['city'] != city:
                        # Only use an IP-based city if a better location can't be found.
                        if not city or city == country:
                            city = data['city']
                    if 'loc' in data and not location_string:
                        location_string = data['loc']
            except Exception as e:
                print(f"Error getting location from IP: {e}")
        
        location_info = {
            "country": country if country else None,
            "city": city if city and city != country else None,
            "possible_carrier": phone_carrier if phone_carrier else None,
            "location": location_string
        }
        
        # If we have at least one piece of information, cache and return the dict.
        if any(location_info.values()):
            # Update the cache.
            phone_location_cache[phone_number] = location_info
            return location_info
        return None
        
    except Exception as e:
        print(f"Error extracting location from phone number: {e}")
        return None

def get_location_from_ip(ip_address=None):
    """
    Get approximate location from IP address using a free geolocation API
    If ip_address is None, gets the server's public IP location
    """
    try:
        url = "https://ipinfo.io/json" if ip_address is None else f"https://ipinfo.io/{ip_address}/json"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return {
                "city": data.get("city"),
                "region": data.get("region"),
                "country": data.get("country"),
                "location": data.get("loc") # This value is a string with "latitude,longitude".
            }
    except Exception as e:
        print(f"Error retrieving location from IP: {e}")
    
    return None